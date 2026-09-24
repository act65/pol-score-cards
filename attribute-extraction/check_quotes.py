"""Check that every scored `statement` is a verbatim quote from its source day.

**Why this exists.** A score is only auditable if the quote behind it is real.
The site's whole promise is "click the number, read the statement it came from",
and the blog post had to withdraw one example because a fragment read as a false
claim once it was lifted out of the sentences around it. Two distinct failures
hide behind "misquotation", and they need different fixes:

* **Splicing** — the model joined non-contiguous fragments with an ellipsis.
  Every fragment is genuine, but the join is the model's, and it can place a
  qualifier next to a claim it never qualified. Traceable, but not a quote.
* **Fabrication** — the text does not appear in the source at all, not even as
  fragments. The model paraphrased or invented it. Nothing defends against this
  except checking.
* **Truncation** — the text appears, but starts or ends mid-thought, so the
  quote means something the speaker did not. The `divination.txt` prompt even
  invites it ("you may resolve pronouns/ambiguity for clarity").

Keeping these apart matters: a headline "15% of quotes are wrong" is false if
most are traceable splices, and reporting it would be the same overstatement the
project is trying to correct.

This measures both on a sample, per attribute, so prompt changes can be graded
on whether they reduce it.

    cd attribute-extraction
    python check_quotes.py run                 # 600-statement sample
    python check_quotes.py run --n 2000 --out QUOTE_AUDIT.md

Deterministic: no LLM, no network.
"""

from __future__ import annotations

import json
import os
import random
import re
from collections import defaultdict

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "data", "corpus")
# v3.0. The default used to be hansard_scores_full.jsonl — the RETIRED v2.0
# file, which predates the hard quote gate in extract.py. Auditing it and
# reading the result as a v3.0 number turns a 100% verbatim rate into 85%.
DEFAULT_SCORES = os.path.join(HERE, "hansard_scores_v3.jsonl")
DEFAULT_CORPUS = os.path.join(CORPUS, "hansard_v2.json")

# Hansard uses curly quotes and en dashes; the model tends to emit straight
# ASCII. Folding these is not leniency — it is the same characters.
_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                       "–": "-", "—": "-", "…": "...",
                       "\xa0": " "})


def norm(text: str) -> str:
    """Collapse to comparable form: folded punctuation, single spaces, lowercase."""
    return " ".join((text or "").translate(_FOLD).lower().split())


# An ellipsis (either form, optionally spaced) is how the model signals it has
# skipped text. Splitting on it recovers the fragments it actually quoted.
_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|…)\s*")

# Fragments this short match almost anything, so finding them proves nothing.
_MIN_FRAGMENT = 25


def _sentence_ends(text: str) -> bool:
    return bool(re.search(r"[.!?][\"')\]]?\s*$", (text or "").strip()))


def _sentence_starts(text: str) -> bool:
    t = (text or "").strip()
    # A quote that opens lowercase, or on a conjunction, was cut from mid-sentence.
    return bool(t) and (t[0].isupper() or t[0] in "\"'“‘(")


def load_days(corpus: str) -> dict[str, str]:
    """{date -> normalised full text of that sitting day}."""
    days: dict[str, list] = defaultdict(list)
    with open(corpus) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("date"):
                days[rec["date"]].append(rec.get("content", ""))
    return {d: norm(" ".join(parts)) for d, parts in days.items()}


def load_statements(scores: str) -> list[dict]:
    out = []
    with open(scores) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            date = row.get("date") or (row.get("window_id") or "")[:10]
            for attr, examples in (row.get("examples_by_attribute") or {}).items():
                for ex in examples or []:
                    if ex.get("statement"):
                        out.append({"attribute": attr, "date": date,
                                    "politician": ex.get("politician", ""),
                                    "statement": ex["statement"]})
    return out


def classify(statement: str, day_text: str) -> str:
    """One of `verbatim` | `spliced` | `missing`, against a day's transcript.

    `spliced` means the statement is an ellipsis-joined set of fragments that
    are each genuinely present. Fragments under `_MIN_FRAGMENT` chars are
    ignored rather than counted as found — "and" occurs in every transcript, so
    matching it is not evidence.
    """
    q = norm(statement)
    if not q:
        return "missing"
    if q in day_text:
        return "verbatim"
    parts = [norm(p) for p in _ELLIPSIS.split(statement)]
    parts = [p for p in parts if len(p) >= _MIN_FRAGMENT]
    if len(parts) >= 2 and all(p in day_text for p in parts):
        return "spliced"
    return "missing"


def run(scores: str = DEFAULT_SCORES, corpus: str = DEFAULT_CORPUS,
        n: int = 600, seed: int = 20260807, out: str | None = None) -> None:
    """Audit a random sample of scored statements against the source corpus."""
    days = load_days(corpus)
    statements = load_statements(scores)
    if not statements:
        raise SystemExit(f"no statements in {scores}")

    rng = random.Random(seed)
    # Only statements whose day we actually hold can be checked; sampling from
    # the rest would report absence of evidence as fabrication.
    checkable = [s for s in statements if s["date"] in days]
    sample = rng.sample(checkable, min(n, len(checkable)))

    per_attr: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "verbatim": 0, "spliced": 0, "missing": 0, "truncated": 0})
    misses = []
    for s in sample:
        day = days[s["date"]]
        a = per_attr[s["attribute"]]
        a["n"] += 1
        kind = classify(s["statement"], day)
        a[kind] += 1
        if kind == "verbatim" and not (_sentence_starts(s["statement"])
                                       and _sentence_ends(s["statement"])):
            a["truncated"] += 1
        if kind == "missing" and len(misses) < 40:
            misses.append(s)

    lines = _render(per_attr, misses, sample, checkable, statements, days)
    print("\n".join(lines))
    if out:
        path = out if os.path.isabs(out) else os.path.join(HERE, out)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nwrote {path}")
        # A machine-readable sidecar beside the report. The site's /data page
        # shows these numbers, and parsing a markdown table to get them would
        # break the first time the table changed shape.
        tot = {k: sum(a[k] for a in per_attr.values())
               for k in ("n", "verbatim", "spliced", "missing", "truncated")}
        side = os.path.splitext(path)[0] + ".json"
        with open(side, "w") as f:
            json.dump({"sampled": len(sample), "checkable": len(checkable),
                       "statements": len(statements), "sitting_days": len(days),
                       "totals": tot,
                       "per_attribute": {k: dict(v) for k, v in per_attr.items()}},
                      f, indent=2)
        print(f"wrote {side}")


def _render(per_attr, misses, sample, checkable, statements, days) -> list[str]:
    L = ["# Quote audit", "",
         "Is every scored statement a verbatim quote from its sitting day?",
         "Generated by `check_quotes.py` — deterministic, re-runnable.", ""]
    L.append(f"Sampled {len(sample):,} of {len(checkable):,} checkable statements "
             f"({len(statements):,} total, {len(days):,} sitting days held).")
    L.append("")
    L += ["| attribute | checked | verbatim | spliced | not found | mid-sentence |",
          "|---|---:|---:|---:|---:|---:|"]
    tot = {"n": 0, "verbatim": 0, "spliced": 0, "missing": 0, "truncated": 0}
    for attr in sorted(per_attr, key=lambda a: -per_attr[a]["n"]):
        a = per_attr[attr]
        for k in tot:
            tot[k] += a[k]
        L.append(f"| {attr} | {a['n']} | {100*a['verbatim']/a['n']:.0f}% | "
                 f"{100*a['spliced']/a['n']:.0f}% | {100*a['missing']/a['n']:.0f}% | "
                 f"{100*a['truncated']/a['n']:.0f}% |")
    if tot["n"]:
        L.append(f"| **all** | **{tot['n']}** | **{100*tot['verbatim']/tot['n']:.0f}%** | "
                 f"**{100*tot['spliced']/tot['n']:.0f}%** | "
                 f"**{100*tot['missing']/tot['n']:.0f}%** | "
                 f"**{100*tot['truncated']/tot['n']:.0f}%** |")
    L += ["",
          "`verbatim` = the exact text occurs in that day's transcript.",
          "`spliced` = ellipsis-joined fragments, each genuinely present, but the "
          "join is the model's — traceable, yet not a quote.",
          "`not found` = does not occur, even as fragments (paraphrase or fabrication).",
          "`mid-sentence` = verbatim, but does not begin and end on a sentence "
          "boundary, so it may not carry the speaker's full meaning.", ""]

    if misses:
        L += ["## Statements not found in the source", ""]
        for m in misses[:15]:
            L.append(f"- **{m['attribute']}** / {m['politician']} / {m['date']}")
            L.append(f"  > {m['statement'][:220]}")
        L.append("")
    return L


if __name__ == "__main__":
    fire.Fire({"run": run})
