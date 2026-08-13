"""Measure how much the nine attributes actually overlap.

**Why this exists.** The nine attributes are presented as nine independent
readings of conduct, and they are not. Reviewing the v2.0 output turned up
Civility and Charisma correlating at 0.96 — one insult, counted twice, then
compounded by the geometric mean used for card rank. That was found by hand,
once. This makes it a measurement we re-run.

Three separate things get conflated when people say "the attributes overlap",
so this reports them separately:

* **Score correlation** — when two attributes both score the same statement, do
  they give it the same number? High `r` means the rubrics are reading the same
  property. This is the redundancy that inflates a card.
* **Selection overlap** (Jaccard) — do two attributes *pick out* the same
  statements from the corpus? Two attributes can select the same text and still
  grade it differently; that is fine. Selecting differently but grading
  identically is the worse failure.
* **Coverage** — how many statements each attribute finds at all, and how many
  are scored by two or more. An attribute that fires on everything is not
  measuring a distinguishing property.

    cd attribute-extraction
    python attribute_overlap.py run                      # all score files
    python attribute_overlap.py run --scores hansard_scores_full.jsonl
    python attribute_overlap.py run --out ATTRIBUTE_OVERLAP.md

Deterministic: no LLM, no network. Reads extraction output only.
"""

from __future__ import annotations

import glob
import json
import math
import os
from collections import Counter, defaultdict

import fire

HERE = os.path.dirname(os.path.abspath(__file__))

# Extraction output, newest schema first. Each row is one window with an
# `examples_by_attribute` map.
DEFAULT_SCORES = ["hansard_scores_full.jsonl", "presser_scores.jsonl",
                  "release_scores.jsonl"]

# Reported in the order the card shows them, so the matrix is readable against
# the site rather than alphabetical.
# Card order. `charisma` is retained so v2.0 score files still render in a
# sensible order — this tool has to read the old data to show what changed.
CARD_ORDER = ["forthrightness", "strength", "veracity", "authenticity",
              "divination", "focus", "charisma", "civility", "rigor",
              "specificity"]

# Above this, two attributes are not telling a reader anything new. Chosen to
# sit below the observed civility/charisma pair (0.96) and above the merely
# related pairs, so it flags redundancy rather than correlation.
REDUNDANT_R = 0.85


def _key(politician: str, statement: str) -> str:
    """Identity of a scored statement, for joining across attributes.

    Whitespace and case vary between attributes because the model re-quotes the
    statement per call, so normalise before joining or the join silently misses
    most co-scored pairs.
    """
    text = " ".join((statement or "").split()).lower().strip(" .,\"'“”")
    return f"{(politician or '').strip().lower()}|{text}"


def load(paths: list[str]) -> dict[str, dict[str, float]]:
    """{attribute -> {statement_key -> score}} across every score file.

    A statement scored twice for one attribute (the same quote surfacing in two
    overlapping windows) keeps the first score — averaging would invent a value
    that no single call produced.
    """
    by_attr: dict[str, dict[str, float]] = defaultdict(dict)
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                for attr, examples in (row.get("examples_by_attribute") or {}).items():
                    for ex in examples or []:
                        score = ex.get("score")
                        if score is None:
                            continue
                        # v3.0 files an example against whoever it is ABOUT;
                        # only the speaker's own conduct belongs on their card.
                        if ex.get("subject") not in (None, "speaker"):
                            continue
                        k = _key(ex.get("politician", ""), ex.get("statement", ""))
                        by_attr[attr].setdefault(k, float(score))
    return by_attr


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r, or None when it is undefined (n<3 or a constant series)."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def pairwise(by_attr: dict[str, dict[str, float]], min_n: int = 30) -> list[dict]:
    """Score correlation and selection overlap for every attribute pair."""
    attrs = [a for a in CARD_ORDER if a in by_attr]
    attrs += sorted(a for a in by_attr if a not in CARD_ORDER)

    out = []
    for i, a in enumerate(attrs):
        for b in attrs[i + 1:]:
            ka, kb = set(by_attr[a]), set(by_attr[b])
            both = ka & kb
            union = ka | kb
            xs = [by_attr[a][k] for k in both]
            ys = [by_attr[b][k] for k in both]
            r = pearson(xs, ys) if len(both) >= min_n else None
            out.append({
                "a": a, "b": b,
                "n_both": len(both),
                "n_a": len(ka), "n_b": len(kb),
                "r": r,
                # What share of each attribute's own selections is implicated?
                # `r` is computed on the intersection alone, so it says nothing
                # about the statements only one attribute picked. A high r over
                # 5% of an attribute is a different finding from a high r over
                # 80% of it, and the bare number cannot tell them apart.
                "share_a": len(both) / len(ka) if ka else 0.0,
                "share_b": len(both) / len(kb) if kb else 0.0,
                # Jaccard: of every statement either attribute picked, what
                # fraction did both pick?
                "jaccard": len(both) / len(union) if union else 0.0,
                "mean_gap": (sum(abs(x - y) for x, y in zip(xs, ys)) / len(both)
                             if both else None),
            })
    return out


def run(scores: str | list | None = None, out: str | None = None,
        min_n: int = 30) -> None:
    """Report attribute overlap; optionally write a markdown summary."""
    if scores is None:
        paths = [os.path.join(HERE, p) for p in DEFAULT_SCORES]
    elif isinstance(scores, str):
        paths = sorted(glob.glob(scores)) or [scores]
    else:
        paths = list(scores)

    by_attr = load(paths)
    if not by_attr:
        raise SystemExit(f"no scored examples found in {paths}")

    pairs = pairwise(by_attr, min_n=min_n)
    lines = _render(by_attr, pairs, paths, min_n)
    print("\n".join(lines))

    if out:
        path = out if os.path.isabs(out) else os.path.join(HERE, out)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nwrote {path}")


def _render(by_attr, pairs, paths, min_n) -> list[str]:
    attrs = [a for a in CARD_ORDER if a in by_attr]
    attrs += sorted(a for a in by_attr if a not in CARD_ORDER)

    L = ["# Attribute overlap", ""]
    L.append("How much do the nine attributes measure the same thing? Generated by")
    L.append("`attribute_overlap.py` — deterministic, re-runnable after any prompt change.")
    L.append("")
    L.append("Sources: " + ", ".join(os.path.basename(p) for p in paths
                                     if os.path.exists(p)))
    L.append("")

    # --- coverage ---
    L += ["## Coverage", "",
          "| attribute | statements scored | mean | share of all scored |", "|---|---:|---:|---:|"]
    every = set()
    for a in attrs:
        every |= set(by_attr[a])
    for a in attrs:
        vals = list(by_attr[a].values())
        L.append(f"| {a} | {len(vals):,} | {sum(vals)/len(vals):.2f} | "
                 f"{100*len(vals)/len(every):.0f}% |")
    times = Counter()
    for a in attrs:
        for k in by_attr[a]:
            times[k] += 1
    multi = sum(v for k, v in times.items() if v > 1)
    L += ["", f"{len(every):,} distinct statements, "
              f"{sum(times.values()):,} statement-attribute scores. "
              f"{100*sum(1 for v in times.values() if v > 1)/len(every):.0f}% of "
              f"statements are scored by more than one attribute.", ""]

    # --- correlation matrix ---
    rmap = {(p["a"], p["b"]): p["r"] for p in pairs}
    rmap.update({(p["b"], p["a"]): p["r"] for p in pairs})
    L += ["## Score correlation (Pearson r on co-scored statements)", "",
          "Blank = fewer than "f"{min_n} statements in common.", "",
          "| | " + " | ".join(a[:4] for a in attrs) + " |",
          "|---" * (len(attrs) + 1) + "|"]
    for a in attrs:
        cells = []
        for b in attrs:
            if a == b:
                cells.append("—")
            else:
                r = rmap.get((a, b))
                cells.append("" if r is None else f"{r:.2f}")
        L.append(f"| **{a}** | " + " | ".join(cells) + " |")
    L.append("")

    # --- the verdict ---
    flagged = sorted((p for p in pairs if p["r"] is not None and p["r"] >= REDUNDANT_R),
                     key=lambda p: -p["r"])
    L += [f"## Redundant pairs (r >= {REDUNDANT_R})", ""]
    if not flagged:
        L.append(f"None. No attribute pair correlates at or above {REDUNDANT_R}.")
    else:
        L.append("These pairs are close to measuring one property twice. Because card")
        L.append("rank is a geometric mean over all nine, a statement penalised by two")
        L.append("correlated attributes costs the MP twice for one act.")
        L += ["", "| pair | r | co-scored | share of each | mean gap | selection overlap |",
              "|---|---:|---:|---:|---:|---:|"]
        for p in flagged:
            L.append(f"| {p['a']} / {p['b']} | **{p['r']:.2f}** | {p['n_both']:,} | "
                     f"{100*p['share_a']:.0f}% / {100*p['share_b']:.0f}% | "
                     f"{p['mean_gap']:.3f} | {p['jaccard']:.2f} |")
    L.append("")

    # --- strongest pairs regardless of threshold ---
    ranked = sorted((p for p in pairs if p["r"] is not None),
                    key=lambda p: -p["r"])[:12]
    L += ["## Most correlated pairs", "",
          "`r` is computed on the co-scored statements **only**. Read it next to",
          "`share of each` — the fraction of each attribute's own selections that",
          "the pair has in common. A high `r` over a small share means the two",
          "agree on a narrow slice and say nothing about each other elsewhere; a",
          "high `r` over a large share is genuine redundancy.", "",
          "| pair | r | co-scored | share of each | selection overlap |",
          "|---|---:|---:|---:|---:|"]
    for p in ranked:
        L.append(f"| {p['a']} / {p['b']} | {p['r']:.2f} | {p['n_both']:,} "
                 f"({p['n_a']:,} / {p['n_b']:,}) | "
                 f"{100*p['share_a']:.0f}% / {100*p['share_b']:.0f}% | "
                 f"{p['jaccard']:.2f} |")
    L.append("")

    # --- selection overlap, which is a different failure ---
    sel = sorted(pairs, key=lambda p: -p["jaccard"])[:8]
    L += ["## Most-shared selections (Jaccard)", "",
          "Two attributes picking the same statements is not itself a problem —",
          "one act can be both uncivil and illogical. It only matters when the",
          "scores are also near-identical (above).", "",
          "| pair | selection overlap | r |", "|---|---:|---:|"]
    for p in sel:
        r = "" if p["r"] is None else f"{p['r']:.2f}"
        L.append(f"| {p['a']} / {p['b']} | {p['jaccard']:.2f} | {r} |")
    L.append("")
    return L


if __name__ == "__main__":
    fire.Fire({"run": run})
