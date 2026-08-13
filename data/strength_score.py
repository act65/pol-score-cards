"""Turn the Strength ledger into a score.

    cd data
    python strength_score.py run                 # -> corpus/strength_scores.jsonl
    python strength_score.py explain --name "Chris Bishop"

`strength_ledger.py` deliberately stops at components and writes no score,
because the weighting is where the government/opposition confound bites. This
module is that weighting step, and every choice in it exists to stop Strength
becoming a detector for holding office.

**The confound, measured.** Across the ledger, government MPs average a 0.91
delivery rate and opposition MPs 0.28. Score on delivery alone and Strength
reports which side of the House someone sits on.

Worse, within the minister cohort `delivery_rate` runs 0.88–1.00 with a median
of **1.00** — it has almost no variance, so it cannot discriminate between
ministers either. And only 28 of 92 non-ministers have *any* resolved bill,
because ballot bills are drawn by lot and rarely pass. Delivery is close to a
constant within each cohort and a step function between them.

**So: rank within cohort, never across.**

* **Cohort** is `delivery_scope` — `minister`, `member`, `none`. A minister and
  a backbencher are not attempting the same task and cannot share a scale.
* **Rank, not raw values.** The components are on incomparable scales
  (`initiative` spans 0–49 for ministers and 0–4 for members). Percentile rank
  within cohort makes them commensurable, and it handles the zero-variance case
  correctly for free: when every minister delivers 100%, they all tie, the
  component contributes nothing, and the score falls to the components that do
  vary. A raw weighted mean would instead hand every minister the same large
  delivery bonus and call it an achievement.
* **A `null` delivery rate is excluded from the blend, not zeroed.** `null`
  means nothing has resolved yet. Pending is not failure — the same rule as
  `uncheckable` in the resolver.
* **`insufficient_evidence` produces no score, ever.** 14 MPs have no
  legislative output; that includes the Speaker and the Prime Minister, whose
  roles do not hold bills. Scoring them zero would say they failed to deliver
  when they had no lever to pull.

**What this score is not.** It does not compare a minister to a backbencher, and
the output says so: every row carries its `cohort` and `cohort_n`, and the site
must show them. A Strength of 0.9 means "delivered more than most of their
cohort", never "delivered more than an MP in another cohort".
"""

from __future__ import annotations

import json
import os

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "corpus", "strength_ledger.jsonl")
OUT = os.path.join(HERE, "corpus", "strength_scores.jsonl")

# Components blended into the score. All are ranked within cohort before
# blending; the weights apply to those ranks.
#
# **These are the ledger's raw counts, not its `components` block.** The ledger
# offers derived `initiative` and `engagement` figures and they cannot both be
# used: they correlate at r=0.969. Worse, `initiative` tracks `bills_in_charge`
# at **r=0.996** — it is misnamed, and measures bills a member was *handed*
# rather than work they started. Blending the two would have counted
# `bills_in_charge` three times (once through delivery_rate, twice more through
# the derived pair) and called the result three kinds of evidence.
#
# The raw counts below are genuinely distinct acts, and measurably so:
#
#   proposed / in_charge   r = -0.34   (ministers do not need the ballot)
#   proposed / ap_bills    r = -0.13
#   ap_bills / in_charge   r = +0.71   (related, not redundant)
#
# `delivery_rate` carries the most weight because it is the attribute's actual
# question ("did commitments become law?"), but it self-neutralises when a
# cohort is uniform — which it is for ministers — so the other two are load-
# bearing, not tiebreaks.
WEIGHTS = {
    "delivery_rate": 0.5,   # enacted / resolved bills in charge
    "proposed": 0.25,       # ballot bills lodged — self-started work
    "ap_bills": 0.25,       # distinct bills engaged via amendment papers
}


def _components(row: dict) -> dict[str, float | None]:
    """The three scored components for one ledger row.

    Pulled from the raw counts rather than the ledger's `components` block —
    see WEIGHTS for why the derived `initiative`/`engagement` pair is not used.
    """
    return {
        "delivery_rate": row.get("components", {}).get("delivery_rate"),
        "proposed": (row.get("proposed_bills") or {}).get("total"),
        "ap_bills": (row.get("amendment_papers") or {}).get("distinct_bills"),
    }


def _percentile_ranks(values: list[float | None]) -> list[float | None]:
    """Rank each value in [0, 1] against the others, averaging ties.

    `None` stays `None` — a missing component is dropped from that member's
    blend rather than being imputed, so nothing invents evidence.

    Ties average, so a cohort where every value is identical maps to 0.5 for
    everyone. That is the intended behaviour: a component that does not vary
    within a cohort tells you nothing about anyone in it, and 0.5 is neutral.
    """
    present = sorted(v for v in values if v is not None)
    if not present:
        return [None] * len(values)
    if len(present) == 1:
        return [0.5 if v is not None else None for v in values]

    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        # Average rank among equals: (#below + (#equal - 1)/2) / (n - 1).
        below = sum(1 for p in present if p < v)
        equal = sum(1 for p in present if p == v)
        out.append((below + (equal - 1) / 2) / (len(present) - 1))
    return out


def _score_cohort(rows: list[dict]) -> None:
    """Attach `strength` and per-component ranks to each row of one cohort."""
    comps = [_components(r) for r in rows]
    ranks = {
        comp: _percentile_ranks([c.get(comp) for c in comps])
        for comp in WEIGHTS
    }
    for i, row in enumerate(rows):
        parts = {c: ranks[c][i] for c in WEIGHTS if ranks[c][i] is not None}
        if not parts:
            row["strength"] = None
            row["components_used"] = []
            continue
        # Re-normalise over the components this member actually has, so someone
        # with no resolved bill is not silently capped at the other weights.
        total_w = sum(WEIGHTS[c] for c in parts)
        row["strength"] = round(
            sum(WEIGHTS[c] * v for c, v in parts.items()) / total_w, 4)
        row["components_used"] = sorted(parts)
        row["component_ranks"] = {c: round(v, 4) for c, v in parts.items()}


def score(ledger: str = LEDGER) -> list[dict]:
    """Score every member in the ledger file."""
    with open(ledger, encoding="utf-8") as f:
        return _scored([json.loads(line) for line in f if line.strip()])


def _scored(rows: list[dict]) -> list[dict]:
    """Score ledger rows. Pure — no file access, so tests can drive it."""
    scored, skipped = [], []
    for r in rows:
        (skipped if r.get("insufficient_evidence") else scored).append(r)

    cohorts: dict[str, list[dict]] = {}
    for r in scored:
        cohorts.setdefault(r.get("delivery_scope") or "unknown", []).append(r)
    for members in cohorts.values():
        _score_cohort(members)

    out = []
    for r in scored + skipped:
        insufficient = bool(r.get("insufficient_evidence"))
        cohort = r.get("delivery_scope") or "unknown"
        out.append({
            "politician_id": r["politician_id"],
            "name": r["name"],
            "party": r.get("party"),
            "attribute": "strength",
            # No evidence means no score. Never zero: an MP with no bills had
            # no opportunity to deliver, which is not a failure to deliver.
            "score": None if insufficient else r.get("strength"),
            "insufficient_evidence": insufficient,
            "cohort": cohort,
            "cohort_n": len(cohorts.get(cohort, [])) if not insufficient else 0,
            "evidence_n": r.get("evidence_n", 0),
            "components": _components(r),
            "component_ranks": r.get("component_ranks", {}),
            "components_used": r.get("components_used", []),
        })
    return out


def run(ledger: str = LEDGER, out: str = OUT) -> None:
    """Score the ledger and write corpus/strength_scores.jsonl."""
    rows = score(ledger)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    have = [r for r in rows if r["score"] is not None]
    print(f"{len(rows)} members, {len(have)} scored, "
          f"{len(rows) - len(have)} insufficient evidence")
    by_cohort: dict[str, list[float]] = {}
    for r in have:
        by_cohort.setdefault(r["cohort"], []).append(r["score"])
    for c, vals in sorted(by_cohort.items()):
        print(f"  {c:10s} n={len(vals):3d}  mean={sum(vals)/len(vals):.2f}")

    # The check this module exists to pass. Cohort ranking should leave no
    # government/opposition gap; if one appears, the weighting is leaking role.
    gov = {"National", "ACT", "NZ First"}
    g = [r["score"] for r in have if r.get("party") in gov]
    o = [r["score"] for r in have if r.get("party") not in gov]
    if g and o:
        print(f"\nbias check — government {sum(g)/len(g):.3f} (n={len(g)})  "
              f"opposition {sum(o)/len(o):.3f} (n={len(o)})  "
              f"gap {abs(sum(g)/len(g) - sum(o)/len(o)):.3f}")
        print("  (ledger delivery_rate gap before cohort ranking: 0.91 vs 0.28)")
    print(f"\nwrote {out}")


def explain(name: str, ledger: str = LEDGER) -> None:
    """Show how one member's score was built."""
    for r in score(ledger):
        if r["name"].lower() == name.lower():
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return
    raise SystemExit(f"no member named {name!r}")


if __name__ == "__main__":
    fire.Fire({"run": run, "score": score, "explain": explain})
