"""Tests for the two instrument audits — attribute overlap and quote fidelity.

    cd attribute-extraction && python -m pytest tests/test_instrument_audits.py

These audits exist to catch the instrument measuring the wrong thing, so their
own arithmetic has to be right. Both are pure functions over data on disk — no
LLM, no network — which is what makes them cheap enough to gate every prompt
change on.
"""

import pytest

import attribute_overlap as ao
import check_quotes as cq


# --- joining statements across attributes -----------------------------------

def test_key_ignores_whitespace_case_and_edge_punctuation():
    """The model re-quotes a statement per attribute call, so the same text
    arrives with different spacing and casing. If the join key did not fold
    those, co-scored pairs would silently miss and every correlation would be
    computed on a fraction of the real overlap."""
    a = ao._key("Chris Bishop", "That is  TRUE.")
    b = ao._key("chris bishop", '"that is true"')
    assert a == b


def test_key_separates_different_speakers():
    assert ao._key("A Person", "same words") != ao._key("B Person", "same words")


# --- correlation ------------------------------------------------------------

def test_pearson_matches_a_known_value():
    assert ao.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert ao.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


@pytest.mark.parametrize("xs,ys", [
    ([1, 2], [1, 2]),              # n < 3
    ([1, 1, 1], [1, 2, 3]),        # x constant -> undefined, not 0.0
])
def test_pearson_is_none_when_undefined(xs, ys):
    """Returning 0.0 for an undefined correlation would read as 'independent',
    which is the opposite of 'we cannot tell'."""
    assert ao.pearson(xs, ys) is None


def test_pairwise_reports_overlap_and_correlation():
    by_attr = {
        "civility": {f"k{i}": i / 10 for i in range(10)},
        # identical scores on the same statements: perfectly redundant
        "charisma": {f"k{i}": i / 10 for i in range(10)},
        # same statements, unrelated scores
        "rigor": {f"k{i}": (i % 2) / 2 for i in range(10)},
        # no statements in common at all
        "strength": {f"z{i}": i / 10 for i in range(10)},
    }
    pairs = {(p["a"], p["b"]): p for p in ao.pairwise(by_attr, min_n=5)}
    cc = pairs[("charisma", "civility")]
    assert cc["r"] == pytest.approx(1.0)
    assert cc["jaccard"] == 1.0
    assert cc["mean_gap"] == pytest.approx(0.0)

    disjoint = pairs[("strength", "civility")]
    assert disjoint["n_both"] == 0
    assert disjoint["jaccard"] == 0.0
    assert disjoint["r"] is None


def test_load_skips_examples_about_someone_else(tmp_path):
    """Only the speaker's own conduct belongs on their card. An example filed
    against an opponent must not enter the correlation — that is the
    subject-attribution defect leaking into the audit."""
    import json
    path = tmp_path / "scores.jsonl"
    path.write_text(json.dumps({
        "window_id": "2025-10-01#1",
        "examples_by_attribute": {"civility": [
            {"politician": "A", "statement": "own conduct", "score": 0.9},
            {"politician": "A", "statement": "their conduct", "score": 0.1,
             "subject": "other", "subject_name": "B"},
        ]},
    }) + "\n")
    loaded = ao.load([str(path)])
    assert list(loaded["civility"].values()) == [0.9]


def test_load_keeps_the_first_score_for_a_repeated_statement(tmp_path):
    """Overlapping windows can surface one quote twice. Averaging would invent
    a value no single call produced, so the first is kept."""
    import json
    path = tmp_path / "scores.jsonl"
    rows = [
        {"examples_by_attribute": {"rigor": [
            {"politician": "A", "statement": "x y z", "score": 0.8}]}},
        {"examples_by_attribute": {"rigor": [
            {"politician": "A", "statement": "X  Y  Z", "score": 0.2}]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert list(ao.load([str(path)])["rigor"].values()) == [0.8]


# --- quote fidelity ---------------------------------------------------------

DAY = cq.norm(
    "The Minister said the policy would cost twelve million dollars. "
    "That figure has never been published. I ask him to table it today."
)


def test_verbatim_quote_is_recognised():
    assert cq.classify("That figure has never been published.", DAY) == "verbatim"


def test_curly_quotes_and_dashes_are_not_treated_as_differences():
    """Hansard uses typographic punctuation and the model emits ASCII. Counting
    that as a mismatch would report fabrication where there is none."""
    day = cq.norm("He said it wasn’t true — not at all.")
    assert cq.classify("He said it wasn't true - not at all.", day) == "verbatim"


def test_ellipsis_joined_fragments_are_spliced_not_verbatim():
    """Both halves are genuine, but the join is the model's — it can place a
    qualifier beside a claim it never qualified."""
    q = ("The Minister said the policy would cost twelve million dollars. … "
         "I ask him to table it today.")
    assert cq.classify(q, DAY) == "spliced"


def test_paraphrase_is_reported_missing():
    assert cq.classify("The Minister admitted he made the number up.", DAY) == "missing"


def test_short_fragments_do_not_count_as_found():
    """A splice of common short fragments would 'match' any transcript, so it
    must not be credited as traceable."""
    assert cq.classify("The … today.", DAY) == "missing"


@pytest.mark.parametrize("text,whole", [
    ("That figure has never been published.", True),
    ("that figure has never been published.", False),   # opens mid-sentence
    ("That figure has never been", False),              # ends mid-sentence
])
def test_sentence_boundary_detection(text, whole):
    assert (cq._sentence_starts(text) and cq._sentence_ends(text)) is whole
