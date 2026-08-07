"""Tests for the search-backed resolver and the guess-vs-search comparison.

    cd attribute-extraction && python -m pytest tests/test_resolve.py

The resolver decides published Veracity and Divination scores, so its safety
properties are worth pinning down: a guess must never be published as a resolved
answer, "we couldn't find out" must never become "false", and the prior must
never reach the prompt that is supposed to check it independently.
"""

import json
from collections import Counter

import pytest

import extract
import resolve

SOURCE = __import__("check_quotes").norm(
    "Hon JANE DOE: Unemployment has fallen to 3.2 percent. That is the lowest "
    "figure in a decade."
)


def _sc(**kw):
    kw.setdefault("explanation", "because")
    return kw


# --- the prior is recorded but never becomes the score ----------------------

def test_a_search_tier_prior_is_kept_separately_from_the_score():
    """Both facts matter: we want the guess (to measure whether search helps)
    AND we want it structurally unable to be published."""
    ex = extract._accept(
        "veracity", "Jane Doe", "Unemployment has fallen to 3.2 percent.",
        _sc(attribute="veracity", prior_score=0.8,
            falsification_criterion="Stats NZ HLFS for the quarter."),
        SOURCE, Counter())
    assert ex is not None
    assert ex.prior_score == 0.8
    assert ex.score is None


def test_a_score_offered_instead_of_a_prior_is_treated_as_the_prior():
    """Models sometimes fill `score` out of habit. That number is a guess, so it
    belongs in `prior_score` — but it must not survive as the score."""
    ex = extract._accept(
        "veracity", "Jane Doe", "Unemployment has fallen to 3.2 percent.",
        _sc(attribute="veracity", score=0.9,
            falsification_criterion="Stats NZ HLFS for the quarter."),
        SOURCE, Counter())
    assert ex.score is None
    assert ex.prior_score == 0.9


def test_text_tier_rows_carry_no_prior():
    ex = extract._accept("civility", "Jane Doe",
                         "That is the lowest figure in a decade.",
                         _sc(attribute="civility", score=0.7), SOURCE, Counter())
    assert ex.score == 0.7
    assert ex.prior_score is None


# --- verdicts ---------------------------------------------------------------

@pytest.mark.parametrize("verdict,score", [
    ("true", 1.0), ("correct", 1.0),
    ("partly_true", 0.5), ("partly_correct", 0.5),
    ("false", 0.0), ("wrong", 0.0),
])
def test_verdicts_map_to_fixed_scores(verdict, score):
    """The mapping is a table, not a model choice, so verdict and score cannot
    drift apart between calls."""
    assert resolve.VERDICT_SCORE[verdict] == score


@pytest.mark.parametrize("verdict", ["uncheckable", "not_yet_due"])
def test_not_finding_evidence_is_not_a_failing_grade(verdict):
    """Absence of evidence is not evidence of falsity. These must produce NO
    score — mapping them to 0.0 would silently mark every hard-to-check claim
    as a lie."""
    assert verdict in resolve.UNSCORED_VERDICTS
    assert resolve.VERDICT_SCORE.get(verdict) is None


# --- what the resolver is shown ---------------------------------------------

def test_the_prompt_never_shows_the_prior_score():
    """Anchoring on the guess is the failure being guarded against, so the guess
    is withheld and only rejoined afterwards for the comparison."""
    item = {"item_id": "w1|veracity|0", "attribute": "veracity",
            "date": "2025-10-01", "politician": "Jane Doe",
            "statement": "Unemployment has fallen to 3.2 percent.",
            "criterion": "Stats NZ HLFS for the quarter.",
            "resolve_by": None, "prior_score": 0.05}
    rendered = resolve._render([item])
    assert "0.05" not in rendered
    assert "prior" not in rendered.lower()
    assert item["criterion"] in rendered


def test_the_prompt_states_the_criterion_came_first():
    item = {"item_id": "w1|veracity|0", "attribute": "veracity", "date": "",
            "politician": "A", "statement": "x", "criterion": "check Stats NZ",
            "resolve_by": None, "prior_score": None}
    assert "before any research" in resolve._render([item])


def test_the_system_prompt_forbids_answering_from_memory():
    assert "SEARCH FIRST" in resolve._SYSTEM
    assert "Do not answer from memory" in resolve._SYSTEM
    # Direction-neutral queries: searching "X does not exist" finds what it
    # went looking for.
    assert "never from its direction" in resolve._SYSTEM


# --- loading ----------------------------------------------------------------

def _write(tmp_path, name, obj, jsonl=False):
    p = tmp_path / name
    if jsonl:
        p.write_text("\n".join(json.dumps(o) for o in obj) + "\n")
    else:
        p.write_text(json.dumps(obj))
    return str(p)


CLAIM = {"politician": "A", "statement": "x", "score": None,
         "falsification_criterion": "check it", "prior_score": 0.3}


def test_loads_pending_items_from_extraction_jsonl(tmp_path):
    path = _write(tmp_path, "s.jsonl", [{
        "window_id": "2025-10-01#0", "date": "2025-10-01",
        "examples_by_attribute": {"veracity": [CLAIM]}}], jsonl=True)
    items = resolve.load_pending(path)
    assert len(items) == 1
    assert items[0]["prior_score"] == 0.3
    assert items[0]["criterion"] == "check it"


def test_loads_pending_items_from_a_comparison_run(tmp_path):
    """Lets the guess-vs-search test reuse claims the bake-off already
    extracted, instead of paying to extract them twice."""
    path = _write(tmp_path, "cmp.json", {
        "reference": "claude-opus-5",
        "results": [
            {"model": "claude-opus-5", "repeat": 0, "window_id": "2024-11-05#0",
             "examples": {"veracity": [CLAIM]}},
            {"model": "claude-sonnet-5", "repeat": 0, "window_id": "2024-11-05#0",
             "examples": {"veracity": [CLAIM]}},
        ]})
    items = resolve.load_pending(path)
    assert len(items) == 1, "only the reference model's claims should be taken"
    assert "claude-opus-5" in items[0]["item_id"]


def test_already_resolved_and_criterion_less_rows_are_skipped(tmp_path):
    path = _write(tmp_path, "s.jsonl", [{
        "window_id": "w", "date": "2025-10-01", "examples_by_attribute": {
            "veracity": [
                dict(CLAIM, score=1.0),                      # already resolved
                dict(CLAIM, falsification_criterion=None),   # nothing to check
                CLAIM,                                       # the only keeper
            ]}}], jsonl=True)
    assert len(resolve.load_pending(path)) == 1
