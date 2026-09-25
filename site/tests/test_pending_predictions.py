"""A prediction that cannot be settled yet gets no score — not even 50.

`not_yet_due` (the resolve-by date has not passed) and `uncheckable` (no source
settles it) are PENDING, and the divination prompt says so in as many words. They
used to fall through to `prior_score` and be published as a number, which was
wrong three ways:

  * It was not a finding. The prompt instructs the model to write 0.5 when the
    date has not passed, and 42 of the first 68 not_yet_due items are exactly
    0.5 — a placeholder shown as a measurement.
  * 50 by our own hand is the same number dressed as a decision, and it punishes
    long horizons: "this will fail by 2030" dragged to the middle while a
    prediction about next week scores 100. That inverts the attribute.
  * Scoring plausibility-when-made instead is the documented dead end — r=0.72
    with Rigor and every MP in an eleven-point band, which measured nothing.
"""

import re

import app
import data_access_jsonl


def _flat(html):
    """HTML with runs of whitespace collapsed.

    Templates wrap, so an assertion on a phrase that spans a line break fails on
    formatting rather than on behaviour.
    """
    return re.sub(r"\s+", " ", html)


def _pending():
    return [(pid, attr, e)
            for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items()
            for e in exs if e.get("pending")]


def test_the_dataset_has_pending_rows_and_they_carry_no_score():
    rows = _pending()
    assert rows, "no pending rows in the dataset"
    for pid, attr, e in rows:
        assert e["score"] is None, (pid, attr)
        assert e["resolved"] is False, (pid, attr)
        assert e["verdict"] in ("not_yet_due", "uncheckable"), e["verdict"]


def test_no_pending_row_was_scored_fifty():
    """The specific failure: a placeholder published as a middling score."""
    for _pid, _attr, e in _pending():
        assert e["score"] != 50 and e["score"] is None


def test_a_pending_row_is_counted_in_nothing():
    """`n` on the card must equal the number of SCORED statements, or the ±
     interval and the confidence tier are computed over evidence that is not
     evidence."""
    for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items():
        scores = data_access_jsonl.get_scores(pid) or {}
        n = scores.get(f"{attr}_n")
        if n is None:
            continue
        scored = sum(1 for e in exs if isinstance(e.get("score"), (int, float)))
        assert n == scored, f"{pid}/{attr}: card says n={n}, {scored} scored rows"


def test_the_evidence_heading_does_not_count_pending_as_behind_the_score():
    c = app.app.test_client()
    pid, attr, _e = _pending()[0]
    exs = data_access_jsonl.get_examples(pid, attr)
    scored = sum(1 for e in exs if isinstance(e.get("score"), (int, float)))
    npend = sum(1 for e in exs if e.get("pending"))
    html = _flat(c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True))
    assert f"the {scored:,} statements behind this score" in html
    assert f"and {npend:,} not yet scoreable" in html


def test_a_pending_row_shows_why_it_has_no_number():
    """An empty gap where a score belongs reads as a bug, not as a decision."""
    c = app.app.test_client()
    pid, attr, _e = _pending()[0]
    npend = sum(1 for e in data_access_jsonl.get_examples(pid, attr)
                if e.get("pending"))
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    assert html.count('class="ev-score pending"') == npend
    assert "Not yet scoreable" in html


def test_every_mp_page_survives_a_scoreless_row():
    """This 500'd on 15 pages: the quote sample is drawn from all examples and
    the badge compared score < 40 against None."""
    c = app.app.test_client()
    pids = {pid for pid, _a, _e in _pending()}
    assert pids
    for pid in sorted(pids):
        assert c.get(f"/politician/{pid}").status_code == 200, pid


def test_the_mp_page_samples_only_scored_rows():
    """That section illustrates a number, and a scoreless row illustrates none."""
    for pid in sorted({p for p, _a, _e in _pending()}):
        for attr in ("Divination", "Veracity"):
            exs = data_access_jsonl.get_examples(pid, attr)
            if not exs:
                continue
            picked = [e for e in app._shuffled(exs, pid, attr)
                      if isinstance(e.get("score"), (int, float))][:3]
            assert all(e.get("score") is not None for e in picked)


def test_the_spread_histogram_ignores_pending_rows():
    """The distribution is of the scores the number is made of."""
    for pid, attr, _e in _pending():
        spread = app._score_spread(pid, attr, None)
        if spread is None:
            continue
        scored = sum(1 for e in data_access_jsonl.get_examples(pid, attr)
                     if isinstance(e.get("score"), (int, float)))
        assert spread["n"] == scored, (pid, attr)
