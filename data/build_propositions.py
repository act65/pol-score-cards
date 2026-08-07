"""Build the canonical policy-proposition vocabulary for Authenticity.

Authenticity asks whether what a politician said matches how their party voted.
Doing that by matching free text to free text does not work: bill titles are
bureaucratic while statements are colloquial, and — fatally — embeddings capture
*topic*, not *stance*. "I will always defend renters" and "renter protections
are red tape" sit almost on top of each other in embedding space, and stance is
the entire question.

So both sides normalise to the same closed vocabulary instead, and the join
becomes a lookup. This builds that vocabulary from the legislative record, which
is exactly the set of things Parliament actually decided:

    corpus/divisions.jsonl + corpus/bills.jsonl  ->  corpus/propositions.jsonl

Each proposition carries how every party voted on it, so once a statement is
tagged with a proposition id and a stance, Authenticity is a table lookup.

    cd data
    python build_propositions.py run     # -> corpus/propositions.jsonl
    python build_propositions.py stats

Deterministic: no LLM, no network.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")
DEFAULT_OUT = os.path.join(CORPUS, "propositions.jsonl")

# A party's stance is clearest at the decisive stages. Earlier stages often see
# a party vote a bill through to select committee while opposing its substance,
# so a third reading outranks a first.
STAGE_WEIGHT = {
    "third_reading": 4,
    "second_reading": 3,
    "first_reading": 2,
    "committee": 1,
    "amendment": 0,      # amendments are about a change, not the bill itself
    "motion": 1,
}


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return re.sub(r"-+", "-", s)


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _load(name: str) -> list[dict]:
    path = os.path.join(CORPUS, name)
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} — see data/VOTES.md for how to build it")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build(min_weight: int = 1) -> list[dict]:
    """One proposition per bill that the House actually divided on.

    `min_weight` drops propositions whose only divisions were amendments — a
    party voting down someone's amendment is not a stance on the bill."""
    divisions = _load("divisions.jsonl")
    bills = {_key(b["title"]): b for b in _load("bills.jsonl")}

    by_bill: dict[str, list] = defaultdict(list)
    for d in divisions:
        if not d.get("substantive"):
            continue
        for title in d.get("bills") or []:
            by_bill[_key(title)].append((title, d))

    props = []
    for bill_key, entries in by_bill.items():
        title = entries[0][0]
        bill = bills.get(bill_key)
        divs = [d for _, d in entries]
        _best = max(STAGE_WEIGHT.get(d["type"], 0) for d in divs)
        if _best < min_weight:
            continue
        _decisive = max(divs, key=lambda d: STAGE_WEIGHT.get(d["type"], 0))["type"]

        # Each party's stance, weighted so decisive stages dominate.
        votes: dict[str, Counter] = defaultdict(Counter)
        for d in divs:
            w = STAGE_WEIGHT.get(d["type"], 0)
            if not w:
                continue
            for side, key in (("ayes", "support"), ("noes", "oppose")):
                tally = d.get(side)
                if not tally:
                    continue
                for party in tally["parties"]:
                    votes[party][key] += w
                for member in tally["members"]:
                    votes[f"member:{member}"][key] += w

        positions = {}
        for who, c in votes.items():
            if c["support"] == c["oppose"]:
                stance = "mixed"
            else:
                stance = "support" if c["support"] > c["oppose"] else "oppose"
            positions[who] = {
                "stance": stance,
                "support_weight": c["support"],
                "oppose_weight": c["oppose"],
            }

        dates = sorted(d["date"] for d in divs if d.get("date"))
        props.append({
            "proposition_id": f"prop:{slug(title)}",
            "label": title,
            "kind": "bill",
            "bill_id": bill.get("bill_id") if bill else None,
            "bill_type": bill.get("bill_type") if bill else None,
            "outcome": bill.get("outcome") if bill else None,
            "member_in_charge_id": bill.get("member_in_charge_id") if bill else None,
            # The bill's own summary is the best short description of what the
            # proposition *is*, and is what a matcher should read.
            "description": ((bill or {}).get("description") or "").strip() or None,
            "first_division": dates[0] if dates else None,
            "last_division": dates[-1] if dates else None,
            "division_ids": [d["division_id"] for d in divs],
            "n_divisions": len(divs),
            "decisive_stage": _decisive,
            # How much weight the stance deserves. A third reading is a party's
            # settled position on the bill; a committee-stage clause vote is not,
            # and opposition parties routinely support individual clauses of
            # bills they vote against overall.
            "stance_confidence": ("high" if _best >= 3 else
                                  "medium" if _best == 2 else "low"),
            "party_positions": {k: v for k, v in positions.items()
                                if not k.startswith("member:")},
            "member_positions": {k.split(":", 1)[1]: v for k, v in positions.items()
                                 if k.startswith("member:")},
        })
    props.sort(key=lambda p: (p["first_division"] or "", p["label"]))
    return props


def run(out: str = DEFAULT_OUT, min_weight: int = 1) -> None:
    props = build(min_weight)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for p in props:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {len(props)} propositions -> {out}")
    _summarise(props)


def stats(min_weight: int = 1) -> None:
    _summarise(build(min_weight))


def _summarise(props: list[dict]) -> None:
    if not props:
        print("no propositions")
        return
    print(f"\npropositions: {len(props)}")
    print(f"with a matched bill record: {sum(bool(p['bill_id']) for p in props)}")
    print(f"with a description: {sum(bool(p['description']) for p in props)}")
    print(f"divisions covered: {sum(p['n_divisions'] for p in props)}")

    print("\nby stance confidence:")
    for s_, c in Counter(p["stance_confidence"] for p in props).most_common():
        print(f"  {c:5}  {s_}")
    print("\nby decisive stage:")
    for s, c in Counter(p["decisive_stage"] for p in props).most_common():
        print(f"  {c:5}  {s}")
    print("\nby outcome:")
    for s, c in Counter(p["outcome"] for p in props).most_common():
        print(f"  {c:5}  {s}")

    print("\nparty stance counts (how often each party supported vs opposed):")
    agg: dict[str, Counter] = defaultdict(Counter)
    for p in props:
        for party, pos in p["party_positions"].items():
            agg[party][pos["stance"]] += 1
    for party, c in sorted(agg.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(c.values())
        print(f"  {party:16} n={total:4}  support={c['support']:4} "
              f"oppose={c['oppose']:4} mixed={c['mixed']:4}")

    ind = Counter(m for p in props for m in p["member_positions"])
    if ind:
        print("\nindividually-recorded members with their own stance:")
        for m, c in ind.most_common(6):
            print(f"  {c:5}  {m}")

    print("\nexamples:")
    for p in props[-3:]:
        parties = ", ".join(f"{k}={v['stance']}" for k, v in
                            list(p["party_positions"].items())[:4])
        print(f"  {p['proposition_id']}")
        print(f"    {p['n_divisions']} divisions, decisive={p['decisive_stage']}, "
              f"outcome={p['outcome']}")
        print(f"    {parties}")


if __name__ == "__main__":
    fire.Fire({"run": run, "stats": stats, "build": build})
