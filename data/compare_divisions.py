"""Compare two divisions.jsonl files — the re-scrape check for TODO 1b.

The first Hansard scrape dropped paragraphs under 40 characters, which deleted
the Ayes/Noes labels, most verdict lines, and short tally lines (a small party's
whole side of a vote). This quantifies what the fixed scrape recovered.

    cd data
    python compare_divisions.py run --old corpus/divisions.jsonl \\
                                    --new corpus/divisions_v2.jsonl
"""

from __future__ import annotations

import json
from collections import Counter

import fire


def _load(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _key(d: dict) -> tuple:
    """Divisions are matched on day + question + position within the day, since
    ids renumber if the record count changes."""
    return (d["date"], d["question"], d["division_id"].rsplit("-", 1)[1])


def run(old: str = "corpus/divisions.jsonl",
        new: str = "corpus/divisions_v2.jsonl") -> None:
    a, b = _load(old), _load(new)
    print(f"old: {len(a)} divisions   new: {len(b)} divisions   "
          f"({len(b) - len(a):+d})")

    for label, rows in (("old", a), ("new", b)):
        flags = Counter(f for r in rows for f in r["flags"])
        print(f"\n{label} flags:")
        for f, c in flags.most_common():
            print(f"  {c:5}  {f}")
        print(f"  {sum(bool(r['verdict_line']) for r in rows):5}  (has verdict line)")
        print(f"  {sum(1 for r in rows if r['noes']):5}  (has a Noes tally)")

    # The headline check: votes previously recorded as unopposed because the
    # Noes line was too short to survive the filter.
    old_by_key = {_key(d): d for d in a}
    fixed, still = [], []
    for d in b:
        prev = old_by_key.get(_key(d))
        if prev and "unopposed" in prev["flags"]:
            (fixed if d.get("noes") else still).append((prev, d))
    print(f"\npreviously 'unopposed': {sum('unopposed' in d['flags'] for d in a)}")
    print(f"  now have a Noes tally (were wrong): {len(fixed)}")
    print(f"  still unopposed (were right):       {len(still)}")
    for prev, d in fixed[:10]:
        noes = d["noes"]
        print(f"    {d['date']}  {d['question'][:58]}")
        print(f"      was: ayes {prev['ayes']['total']}, noes none"
              f"   now: ayes {d['ayes']['total']}, noes {noes['total']}"
              f"  -> {d['result']}")

    flipped = [(old_by_key[_key(d)], d) for d in b
               if _key(d) in old_by_key and old_by_key[_key(d)]["result"] != d["result"]]
    print(f"\nresult changed: {len(flipped)}")
    for prev, d in flipped[:10]:
        print(f"    {d['date']}  {prev['result']} -> {d['result']}  {d['question'][:56]}")

    only_new = [d for d in b if _key(d) not in old_by_key]
    only_old = [d for d in a if _key(d) not in {_key(x) for x in b}]
    print(f"\ndivisions only in new: {len(only_new)}   only in old: {len(only_old)}")


if __name__ == "__main__":
    fire.Fire({"run": run})
