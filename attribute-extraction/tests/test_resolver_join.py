"""The resolver's verdict must land on the statement it was about.

`resolve.py` names an item by `<window_id>|<attribute>|<index>`, where the index
is the example's POSITION in that window. That is only a stable identity while
the window is never re-extracted. Re-score a window and the list shifts: index 2
becomes a different statement, and the join would attach searched sources to a
quote they were never about — a reader following authoritative-looking links to
the wrong claim.

Found on 2026-09-25: 14 of 389 verdicts were stale. One pointed past the end of
its list and dropped harmlessly; the other 13 landed on quotes that had moved.
"""

import collections

import build_v2_dataset as b


def _one_window(statements, window_id="2026-01-01#1"):
    """A scores file row: one window, N veracity examples, none pre-scored.

    Veracity is search-tier, so `score` is None and the number on the card comes
    either from the resolver or (with use_prior) from the model's guess.
    """
    return [{
        "window_id": window_id,
        "date": "2026-01-01",
        "examples_by_attribute": {
            "veracity": [{"politician": "Christopher Luxon", "statement": s,
                          "score": None, "prior_score": 0.5, "explanation": ""}
                         for s in statements],
        },
    }]


def _verdict(window_id, index, statement, score=1.0, verdict="true"):
    return {"item_id": f"{window_id}@claude-opus-5|veracity|{index}",
            "attribute": "veracity", "date": "2026-01-01",
            "politician": "Christopher Luxon", "statement": statement,
            "criterion": "", "prior_score": 0.5, "verdict": verdict,
            "resolved_score": score, "reasoning": "",
            "sources": ["https://example.govt.nz/a"]}


def _ingest(rows, resolved_rows):
    """Run the fold and hand back (examples, stale counter)."""
    index = {}
    for r in resolved_rows:
        w, attr, i = r["item_id"].split("|")
        index[(w.split("@")[0], attr, i)] = r
    examples = collections.defaultdict(list)
    stale = collections.Counter()
    b._ingest(rows, "Hansard", "Hansard", lambda rec, date: "", b.Roster(),
              collections.defaultdict(list), examples, collections.Counter(),
              set(), collections.Counter(), use_prior=True,
              resolved=index, stale=stale)
    return [e for v in examples.values() for e in v], stale


def test_a_matching_statement_is_joined():
    rows = _one_window(["The deficit was eighty million dollars.", "Second claim."])
    got, stale = _ingest(rows, [_verdict("2026-01-01#1", 0,
                                         "The deficit was eighty million dollars.")])
    assert not stale
    joined = [e for e in got if e.get("evidence_urls")]
    assert len(joined) == 1
    assert joined[0]["text"] == "The deficit was eighty million dollars."
    assert joined[0]["resolved"] is True
    assert joined[0]["score"] == 100


def test_a_shifted_index_is_dropped_not_misattached():
    """The dangerous case: the index still exists, but it is someone else's
    statement now. The verdict must be discarded, not re-pointed."""
    rows = _one_window(["A brand new first claim.", "Second claim."])
    got, stale = _ingest(rows, [_verdict("2026-01-01#1", 0,
                                        "The deficit was eighty million dollars.")])
    assert stale == collections.Counter({"veracity": 1})
    assert not [e for e in got if e.get("evidence_urls")], \
        "a stale verdict was attached to a statement it was not about"
    # The quote still appears, scored from the prior and marked unresolved.
    assert [e for e in got if e["text"] == "A brand new first claim."][0]["resolved"] is False


def test_an_index_past_the_end_is_simply_absent():
    """The harmless half of the same staleness: the example was removed."""
    rows = _one_window(["Only one claim."])
    got, stale = _ingest(rows, [_verdict("2026-01-01#1", 4, "A removed claim.")])
    assert not stale            # never matched a row, so nothing to flag
    assert not [e for e in got if e.get("evidence_urls")]


def test_whitespace_does_not_count_as_a_mismatch():
    """Re-serialisation can change surrounding whitespace without changing the
    statement, and dropping a good verdict over that would be its own bug."""
    rows = _one_window(["  The deficit was eighty million dollars. "])
    got, stale = _ingest(rows, [_verdict("2026-01-01#1", 0,
                                         "The deficit was eighty million dollars.")])
    assert not stale
    assert len([e for e in got if e.get("evidence_urls")]) == 1


def test_an_unscored_verdict_keeps_its_sources_and_gets_no_score():
    """`uncheckable` / `not_yet_due` searched real sources and found no answer.

    The sources are worth showing. The score is not: this row is PENDING, and it
    must not inherit `prior_score`. The divination prompt tells the model to
    write 0.5 when the resolve-by date has not passed, so the guess on these is
    a placeholder the prompt asked for -- publishing it turned an instruction
    into a measurement.

    Changed 2026-09-25. This test previously asserted score == 50.
    """
    rows = _one_window(["A prediction about 2030."])
    v = _verdict("2026-01-01#1", 0, "A prediction about 2030.",
                 score=None, verdict="not_yet_due")
    got, stale = _ingest(rows, [v])
    assert not stale
    e = got[0]
    assert e["verdict"] == "not_yet_due"
    assert e["evidence_urls"] == ["https://example.govt.nz/a"]
    assert e["resolved"] is False
    assert e["pending"] is True
    assert e["score"] is None, "a pending prediction must carry no score"


def test_a_pending_row_is_kept_out_of_the_score_pool():
    """Not just absent from the row -- absent from the average the card shows."""
    import collections as _c
    rows = _one_window(["Settled claim.", "A prediction about 2030."])
    resolved = [
        _verdict("2026-01-01#1", 0, "Settled claim.", score=1.0, verdict="true"),
        _verdict("2026-01-01#1", 1, "A prediction about 2030.",
                 score=None, verdict="not_yet_due"),
    ]
    index = {}
    for r in resolved:
        w, attr, i = r["item_id"].split("|")
        index[(w.split("@")[0], attr, i)] = r
    per_pair = _c.defaultdict(list)
    b._ingest(rows, "Hansard", "Hansard", lambda rec, date: "", b.Roster(),
              per_pair, _c.defaultdict(list), _c.Counter(), set(), _c.Counter(),
              use_prior=True, resolved=index, stale=_c.Counter())
    pooled = list(per_pair.values())[0]
    assert pooled == [1.0], f"the pending row leaked into the pool: {pooled}"
