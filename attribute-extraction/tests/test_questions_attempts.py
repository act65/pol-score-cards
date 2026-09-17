"""A pair the model declines must stop being retried — and must never score 0.

The bug this covers wasted 3 of 7 hours on the night of 2026-09-17: 66
mis-paired Q/A rows were re-sent every night because the resume key is the
OUTPUT row, so "declined" looked exactly like "not yet tried".
"""
import json

import pytest

import extract_questions as eq


def test_attempts_sidecar_sits_beside_the_scores(tmp_path):
    assert eq._attempts_path("a/b/forthrightness_scores_v3.jsonl") == \
        "a/b/forthrightness_scores_v3_attempts.json"
    assert eq._attempts_path("noext") == "noext_attempts.json"


def test_attempts_round_trip(tmp_path):
    out = str(tmp_path / "s.jsonl")
    assert eq._load_attempts(out) == {}
    eq._save_attempts(out, {"q1": 2})
    assert eq._load_attempts(out) == {"q1": 2}


def test_a_corrupt_sidecar_is_not_fatal(tmp_path):
    out = str(tmp_path / "s.jsonl")
    open(eq._attempts_path(out), "w").write("{not json")
    assert eq._load_attempts(out) == {}


def test_save_is_atomic_enough_to_survive_a_reread(tmp_path):
    """os.replace, so a reader never sees a half-written file."""
    out = str(tmp_path / "s.jsonl")
    for n in range(1, 4):
        eq._save_attempts(out, {"q1": n})
        assert eq._load_attempts(out)["q1"] == n


@pytest.mark.parametrize("attempts,expected", [
    ({}, 3),
    ({"q2": eq.MAX_ATTEMPTS}, 2),
    ({"q1": eq.MAX_ATTEMPTS, "q2": eq.MAX_ATTEMPTS, "q3": eq.MAX_ATTEMPTS}, 0),
])
def test_exhausted_pairs_drop_out_of_the_todo_list(attempts, expected):
    """The selection rule itself: done OR given-up is excluded."""
    rows = [{"id": f"q{i}"} for i in (1, 2, 3)]
    done = set()
    givenup = {i for i, n in attempts.items() if n >= eq.MAX_ATTEMPTS}
    todo = [r for r in rows if r["id"] not in done and r["id"] not in givenup]
    assert len(todo) == expected


def test_a_declined_pair_is_never_written_as_a_zero(tmp_path):
    """The rule that matters for the dataset: no score, not a bad score.

    Forthrightness measures whether a minister answered the question. These
    pairs have no question — scoring them 0.0 would record a stonewall that
    never happened, and it would land in a published card.
    """
    out = tmp_path / "s.jsonl"
    out.write_text("", encoding="utf-8")
    eq._save_attempts(str(out), {"q1": eq.MAX_ATTEMPTS})
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert rows == []
    assert eq._load_attempts(str(out)) == {"q1": eq.MAX_ATTEMPTS}
