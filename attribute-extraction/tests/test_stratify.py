"""Stratified selection for the resolver: fix the roster AND the calendar.

`load_pending` returns corpus order and `--limit` truncates it, so a capped run
reads the earliest windows and stops. That is why `resolve_veracity` was pulled
on 2026-09-08 — 371 of its 389 resolved claims came from one month out of
seven, which cannot compare MPs however many more you add.

Capping per politician alone is not enough: taking each MP's first n claims
re-introduces the same bias inside every MP. Both are tested here.
"""

import collections

import resolve


def _items(spec):
    """spec: {politician: [dates]} -> items in corpus (date) order."""
    out = []
    for mp, dates in spec.items():
        for i, d in enumerate(dates):
            out.append({"item_id": f"{d}#{i}|veracity|0",
                        "politician": mp, "date": d,
                        "statement": f"{mp} on {d}", "attribute": "veracity"})
    out.sort(key=lambda x: x["date"])
    return out


def test_zero_is_a_no_op():
    """The running divination resolver calls this every slice. It must not move."""
    items = _items({"A": ["2024-01-01", "2024-06-01"], "B": ["2024-02-01"]})
    assert resolve.stratify(items, 0) == items
    assert resolve.stratify(items, -1) == items


def test_caps_each_politician():
    items = _items({"A": [f"2024-{m:02d}-01" for m in range(1, 13)],
                    "B": [f"2025-{m:02d}-01" for m in range(1, 13)]})
    kept = resolve.stratify(items, 4)
    per = collections.Counter(i["politician"] for i in kept)
    assert per == {"A": 4, "B": 4}


def test_an_mp_below_the_cap_keeps_everything():
    items = _items({"A": ["2024-01-01", "2024-02-01"],
                    "B": [f"2024-{m:02d}-01" for m in range(1, 13)]})
    kept = resolve.stratify(items, 5)
    per = collections.Counter(i["politician"] for i in kept)
    assert per == {"A": 2, "B": 5}


def test_spreads_across_the_term_not_just_the_start():
    """The bug that pulled resolve_veracity, in miniature.

    24 months of claims, cap 4. Taking the first 4 would land entirely in
    2024-01..04; an even stride must reach the back half of the term.
    """
    dates = [f"{y}-{m:02d}-01" for y in (2024, 2025) for m in range(1, 13)]
    items = _items({"A": dates})
    kept = sorted(i["date"] for i in resolve.stratify(items, 4))
    assert len(kept) == 4
    assert kept[0] < "2024-07", f"should start early, got {kept}"
    assert kept[-1] >= "2025-07", f"should reach the term's end, got {kept}"
    assert len(set(kept)) == 4, "no duplicates"


def test_is_deterministic():
    """The resolved file is append-only, so a re-run must ask for the same items."""
    items = _items({chr(65 + i): [f"2024-{m:02d}-01" for m in range(1, 13)]
                    for i in range(5)})
    a = [i["item_id"] for i in resolve.stratify(items, 3)]
    b = [i["item_id"] for i in resolve.stratify(list(reversed(items)), 3)]
    assert a == b, "selection must not depend on input order"


def test_any_prefix_is_spread_across_the_term():
    """Because the run keeps getting interrupted.

    This used to assert date ORDER, which was the wrong property: working the
    sample chronologically means a partial run covers every MP but only their
    earliest claims -- the calendar bias one level up. The run really was cut
    off at 369 of 3,895 claims on 2026-10-06, so a prefix has to be usable.
    """
    dates = [f"{y}-{m:02d}-01" for y in (2024, 2025) for m in range(1, 13)]
    items = _items({chr(65 + i): dates for i in range(8)})
    kept = resolve.stratify(items, 12)
    prefix = kept[:len(kept) // 4]
    years = {i["date"][:4] for i in prefix}
    assert years == {"2024", "2025"}, f"prefix covers only {years}"
    late = sum(1 for i in prefix if i["date"] >= "2025-01")
    assert 0.25 < late / len(prefix) < 0.75, (
        f"prefix is {late}/{len(prefix)} late-term — not spread")


def test_unnamed_politicians_are_not_merged_with_a_real_one():
    items = _items({"A": ["2024-01-01"]})
    items.append({"item_id": "x|veracity|0", "politician": None,
                  "date": "2024-02-01", "statement": "?", "attribute": "veracity"})
    kept = resolve.stratify(items, 1)
    assert len(kept) == 2
