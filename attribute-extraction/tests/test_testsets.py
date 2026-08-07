"""Offline tests for testset sampling, the dev/test split, and leakage.

    cd attribute-extraction && python -m pytest test_testsets.py
"""

import json

import build_testsets as bt
import pytest


# --- the split must be stable and un-re-rollable ----------------------------

def test_statement_id_is_content_addressed():
    a = bt.statement_id("mp-a", "We will build ten thousand homes.")
    assert a == bt.statement_id("mp-a", "We will build ten thousand homes.")
    assert a != bt.statement_id("mp-b", "We will build ten thousand homes.")


def test_split_is_deterministic():
    sid = bt.statement_id("mp-a", "A statement.")
    assert bt.assign_split(sid) == bt.assign_split(sid)


def test_split_is_roughly_the_requested_proportion():
    ids = [bt.statement_id("mp", f"statement number {i}") for i in range(2000)]
    test = sum(bt.assign_split(s, 0.4) == "test" for s in ids)
    assert 0.35 < test / len(ids) < 0.45


def test_split_respects_a_different_fraction():
    ids = [bt.statement_id("mp", f"s{i}") for i in range(2000)]
    test = sum(bt.assign_split(s, 0.2) == "test" for s in ids)
    assert 0.15 < test / len(ids) < 0.25


# --- passage segmentation ---------------------------------------------------

def test_passages_are_within_the_labellable_size_band():
    text = " ".join(f"This is sentence number {i} of a long speech turn." for i in range(60))
    out = bt.passages(text)
    assert out
    assert all(bt.MIN_CHARS <= len(p) <= bt.MAX_CHARS for p in out)


def test_short_turn_yields_nothing_to_label():
    assert bt.passages("Yes.") == []


def test_passages_do_not_split_mid_sentence():
    text = ("The Government has failed to deliver on housing. "
            "We have seen consent numbers fall for three consecutive quarters. "
            "That is the reality facing New Zealanders today. "
            "The Minister should explain himself to this House.")
    for p in bt.passages(text):
        assert p.rstrip()[-1] in ".!?"


# --- speaker normalisation ---------------------------------------------------
# `clean_speaker` and `_norm` are re-exports of data/names.py; their behaviour is
# covered in data/tests/test_names.py. Here we only check the re-export is wired.

def test_speaker_helpers_are_the_shared_implementation():
    assert bt.clean_speaker("Hon DAVID SEYMOUR") == "David Seymour"
    assert bt._norm("Te Pāti Māori") == bt._norm("te pati maori")


# --- leakage detection ------------------------------------------------------

def test_leakage_detects_a_shared_passage(tmp_path, monkeypatch):
    shared = ("we will always stand up for renters and we will never back down "
              "from that commitment to them")
    prompts = tmp_path / "prompts"; prompts.mkdir()
    (prompts / "civility.txt").write_text(f'Examples:\n- "{shared}" -> 0.2\n')
    tests = tmp_path / "testsets"; tests.mkdir()
    (tests / "civility_testset.jsonl").write_text(
        json.dumps({"statement": shared, "civility_score": 0.2}) + "\n")
    monkeypatch.setattr(bt, "PROMPTS", str(prompts))
    monkeypatch.setattr(bt, "TESTSETS", str(tests))
    hits = bt.check_leakage(quiet=True)
    assert len(hits) == 1
    assert hits[0]["prompt"] == "civility.txt"


def test_no_leakage_when_texts_differ(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"; prompts.mkdir()
    (prompts / "civility.txt").write_text("A rubric about being civil in debate.\n")
    tests = tmp_path / "testsets"; tests.mkdir()
    (tests / "civility_testset.jsonl").write_text(
        json.dumps({"statement": "Something else entirely, about housing policy "
                                 "and the consenting regime in our largest city."}) + "\n")
    monkeypatch.setattr(bt, "PROMPTS", str(prompts))
    monkeypatch.setattr(bt, "TESTSETS", str(tests))
    assert bt.check_leakage(quiet=True) == []


def test_leakage_ignores_short_incidental_overlap(tmp_path, monkeypatch):
    """Common phrasing must not be flagged — only a real shared passage."""
    prompts = tmp_path / "prompts"; prompts.mkdir()
    (prompts / "civility.txt").write_text("the Government has failed to deliver\n")
    tests = tmp_path / "testsets"; tests.mkdir()
    (tests / "t.jsonl").write_text(
        json.dumps({"statement": "the Government has failed to deliver"}) + "\n")
    monkeypatch.setattr(bt, "PROMPTS", str(prompts))
    monkeypatch.setattr(bt, "TESTSETS", str(tests))
    assert bt.check_leakage(k=8, quiet=True) == []      # only 6 words long


# --- the live repo must stay clean ------------------------------------------

def test_repo_testsets_have_no_prompt_leakage():
    """Enforced, not merely documented: few-shot examples that overlap the
    testsets inflate every metric we report."""
    hits = bt.check_leakage(quiet=True)
    assert hits == [], f"prompt/testset leakage: {hits[:5]}"
