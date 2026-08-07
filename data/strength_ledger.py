"""Per-MP legislative work ledger — the evidence base for Strength.

Strength asks whether a politician turns stated priorities into law. That is only
answerable from the legislative record, and only for people with a lever to pull.
This joins the three deterministic sources built by `scrapers/bills.py` into one
row per MP:

    corpus/bills.jsonl            bill in charge          -> delivery
    corpus/proposed_bills.jsonl   lodged in the ballot    -> initiative
    corpus/amendment_papers.jsonl Amendment Paper by them -> engagement

    cd data
    python strength_ledger.py run     # -> corpus/strength_ledger.jsonl + summary
    python strength_ledger.py stats   # summary only

Two design rules, both deliberate (see data/VOTES.md and TODOs):

**No evidence is not low Strength.** An MP with no bills has not failed to
deliver — they had no opportunity. Those rows carry `insufficient_evidence:
true` and no score, rather than a zero. Widening beyond bills-in-charge is what
makes this workable: it takes coverage from 72 of 135 MPs to about 121.

**Amendment Papers are counted as distinct bills engaged, not raw papers.**
Tabling forty near-identical amendments during a committee stage is a filibuster
tactic, not forty units of legislative work: the top author has 111 papers
across far fewer bills. Raw counts would rank that above everything else.

This module deliberately writes **no score**. It emits the components; choosing
and normalising the weights is a scoring decision, and the summary reports the
government/opposition skew you have to confront before making it.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")
DEFAULT_POLITICIANS = os.path.join(HERE, "..", "site", "static", "politicians.jsonl")
DEFAULT_OUT = os.path.join(CORPUS, "strength_ledger.jsonl")

# First sitting of the 54th Parliament. A bill introduced in the 53rd but carried
# over and progressed after this date is still work done in this term.
TERM_START = "2023-10-06"


def _key(title: str) -> str:
    """Normalised bill title, for counting distinct bills across sources."""
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _load(name: str) -> list[dict]:
    path = os.path.join(CORPUS, name)
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} — run scrapers/bills.py first")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _in_term(bill: dict, term_start: str) -> bool:
    """54th-Parliament bills, plus 53rd-Parliament bills still moving in this term."""
    if bill.get("parliament") == 54:
        return True
    dates = [d for d in (bill.get("dates") or {}).values() if d]
    dates += [s.get("date") for s in (bill.get("stages") or []) if s.get("date")]
    return any(d[:10] >= term_start for d in dates)


def build(politicians: str = DEFAULT_POLITICIANS,
          term_start: str = TERM_START) -> list[dict]:
    with open(politicians) as f:
        mps = [json.loads(line) for line in f if line.strip()]

    bills = [b for b in _load("bills.jsonl") if _in_term(b, term_start)]
    proposed = _load("proposed_bills.jsonl")
    amendments = _load("amendment_papers.jsonl")

    by_charge: dict[str, list] = defaultdict(list)
    for b in bills:
        if b.get("member_in_charge_id"):
            by_charge[b["member_in_charge_id"]].append(b)
    by_proposed: dict[str, list] = defaultdict(list)
    for p in proposed:
        if p.get("member_id"):
            by_proposed[p["member_id"]].append(p)
    by_amendment: dict[str, list] = defaultdict(list)
    for a in amendments:
        if a.get("member_id"):
            by_amendment[a["member_id"]].append(a)

    rows = []
    for mp in mps:
        pid = mp["id"]
        charge = by_charge.get(pid, [])
        prop = by_proposed.get(pid, [])
        amend = by_amendment.get(pid, [])

        enacted = sum(b["outcome"] == "enacted" for b in charge)
        terminated = sum(b["outcome"] == "terminated" for b in charge)
        in_progress = sum(b["outcome"] == "in_progress" for b in charge)
        resolved = enacted + terminated
        govt_bills = sum(b["bill_type"] == "Government" for b in charge)

        # Only a minister may be in charge of a Government bill, so this is a
        # reliable read of who actually had a delivery lever.
        scope = "minister" if govt_bills else ("member" if (charge or prop or amend)
                                               else "none")

        amended_keys = {_key(a["bill_title"]) for a in amend if a.get("bill_title")}
        charge_keys = {_key(b["title"]) for b in charge if b.get("title")}
        engaged = charge_keys | amended_keys

        evidence_n = len(charge) + len(prop) + len(amend)
        rows.append({
            "politician_id": pid,
            "name": mp.get("name"),
            "party": mp.get("party"),
            "delivery_scope": scope,
            "bills_in_charge": {
                "total": len(charge),
                "government": govt_bills,
                "members": len(charge) - govt_bills,
                "enacted": enacted,
                "terminated": terminated,
                "in_progress": in_progress,
                "titles": [b["title"] for b in charge],
            },
            "proposed_bills": {
                "total": len(prop),
                "titles": [p["title"] for p in prop],
            },
            "amendment_papers": {
                "total": len(amend),
                "distinct_bills": len(amended_keys),
                "bills": sorted({a["bill_title"] for a in amend if a.get("bill_title")}),
            },
            "components": {
                # Of the bills this MP owned that have finished, how many became
                # law. `null` when nothing has resolved — not zero.
                "delivery_rate": (enacted / resolved) if resolved else None,
                "resolved_in_charge": resolved,
                # Bills they chose to put up, whether or not luck or the House
                # let them through.
                "initiative": len(charge) + len(prop),
                # Distinct bills touched, in charge or by amendment.
                "engagement": len(engaged),
            },
            "evidence_n": evidence_n,
            "insufficient_evidence": evidence_n == 0,
        })
    return rows


def run(out: str = DEFAULT_OUT, politicians: str = DEFAULT_POLITICIANS,
        term_start: str = TERM_START) -> None:
    rows = build(politicians, term_start)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} MP rows -> {out}")
    _summarise(rows)


def stats(politicians: str = DEFAULT_POLITICIANS, term_start: str = TERM_START) -> None:
    _summarise(build(politicians, term_start))


GOVT_PARTIES = {"National", "ACT", "NZ First"}


def _summarise(rows: list[dict]) -> None:
    n = len(rows)
    with_ev = [r for r in rows if not r["insufficient_evidence"]]
    print(f"\nMPs: {n}   with evidence: {len(with_ev)}   "
          f"insufficient evidence: {n - len(with_ev)}")

    print("\ncoverage by source (cumulative):")
    charge = {r["politician_id"] for r in rows if r["bills_in_charge"]["total"]}
    prop = {r["politician_id"] for r in rows if r["proposed_bills"]["total"]}
    amend = {r["politician_id"] for r in rows if r["amendment_papers"]["total"]}
    print(f"  bill in charge only          {len(charge):3}")
    print(f"  + proposed (ballot)          {len(charge | prop):3}")
    print(f"  + amendment paper            {len(charge | prop | amend):3}")

    print("\ndelivery scope:")
    for s, c in Counter(r["delivery_scope"] for r in rows).most_common():
        print(f"  {c:5}  {s}")

    print("\nno evidence at all:")
    for r in rows:
        if r["insufficient_evidence"]:
            print(f"  {r['name']} ({r['party']})")

    # The confound to face before choosing weights: ministers deliver, oppositions
    # amend. A Strength score weighted on delivery alone is a government detector.
    print("\ngovernment vs opposition (the weighting confound):")
    for label, sel in (("Government", [r for r in rows if r["party"] in GOVT_PARTIES]),
                       ("Opposition", [r for r in rows if r["party"] not in GOVT_PARTIES])):
        if not sel:
            continue
        rates = [r["components"]["delivery_rate"] for r in sel
                 if r["components"]["delivery_rate"] is not None]
        eng = [r["components"]["engagement"] for r in sel]
        init = [r["components"]["initiative"] for r in sel]
        print(f"  {label:11} n={len(sel):3}  "
              f"mean delivery_rate={sum(rates)/len(rates):.2f} (n={len(rates)})  "
              f"mean engagement={sum(eng)/len(eng):.1f}  "
              f"mean initiative={sum(init)/len(init):.1f}")

    print("\nraw amendment papers vs distinct bills engaged (why we weight by bills):")
    top = sorted(rows, key=lambda r: -r["amendment_papers"]["total"])[:6]
    for r in top:
        ap = r["amendment_papers"]
        print(f"  {r['name']:26} {ap['total']:4} papers across {ap['distinct_bills']:3} bills")

    print("\nmost bills enacted (in charge):")
    for r in sorted(rows, key=lambda r: -r["bills_in_charge"]["enacted"])[:8]:
        b = r["bills_in_charge"]
        print(f"  {r['name']:26} {b['enacted']:3} enacted / {b['total']:3} in charge  ({r['party']})")


if __name__ == "__main__":
    fire.Fire({"run": run, "stats": stats, "build": build})
