"""Tests for the v3.0 extraction quality gates.

    cd attribute-extraction && python -m pytest tests/test_extract_gates.py

These gates are the difference between "the prompt asks for X" and "the output
is X". Every one guards a defect measured in the v2.0 run, so each test names
the number it exists to drive to zero.
"""

from collections import Counter

import pytest

import attributes
import check_quotes
import extract

SOURCE = check_quotes.norm(
    "Hon JANE DOE: The Minister said the policy would cost twelve million "
    "dollars. That figure has never been published. I ask him to table it today."
)


def _sc(**kw):
    kw.setdefault("attribute", "civility")
    kw.setdefault("explanation", "because")
    return kw


def _accept(statement, attr="civility", **kw):
    rejects = Counter()
    ex = extract._accept(attr, "Jane Doe", statement,
                         _sc(attribute=attr, **kw), SOURCE, rejects)
    return ex, rejects


# --- quote fidelity: 6% of v2.0 quotes were not in the transcript -----------

def test_a_verbatim_whole_sentence_is_kept():
    ex, _ = _accept("That figure has never been published.", score=0.8)
    assert ex is not None and ex.quote_check == "verbatim"


def test_a_paraphrase_is_rejected():
    ex, rejects = _accept("The Minister admitted he invented the number.", score=0.2)
    assert ex is None
    assert rejects["quote:missing"] == 1


def test_an_ellipsis_splice_is_rejected():
    """Both fragments are real, but the join is the model's — it can put a
    qualifier beside a claim it never qualified. 9% of v2.0 quotes were these."""
    spliced = ("The Minister said the policy would cost twelve million dollars. "
               "… I ask him to table it today.")
    ex, rejects = _accept(spliced, score=0.5)
    assert ex is None
    assert rejects["quote:spliced"] == 1


def test_a_mid_sentence_fragment_is_rejected():
    """25% of v2.0 quotes did not start and end on a sentence boundary, which is
    how a word-order slip in live speech becomes a 'false claim'."""
    ex, rejects = _accept("figure has never been published", score=0.5)
    assert ex is None
    assert rejects["quote:mid_sentence"] == 1


def test_curly_punctuation_does_not_count_as_a_mismatch():
    source = check_quotes.norm("He said it wasn’t true — not at all.")
    rejects = Counter()
    ex = extract._accept("civility", "A", "He said it wasn't true - not at all.",
                         _sc(score=0.7), source, rejects)
    assert ex is not None


# --- the search tier must not carry a model-invented score ------------------

def test_veracity_needs_a_falsification_criterion():
    ex, rejects = _accept("That figure has never been published.",
                          attr="veracity")
    assert ex is None
    assert rejects["veracity:missing_falsification_criterion"] == 1


def test_veracity_with_a_criterion_is_kept_and_left_unscored():
    ex, _ = _accept("That figure has never been published.", attr="veracity",
                    falsification_criterion="Check the Treasury release register.")
    assert ex is not None
    assert ex.score is None
    assert ex.falsification_criterion


def test_a_volunteered_score_on_the_search_tier_is_discarded():
    """The resolver has not run. Keeping a guessed score would quietly become
    the answer the search was supposed to find — the exact ungrounded judgement
    v3.0 removes."""
    ex, _ = _accept("That figure has never been published.", attr="veracity",
                    score=0.9,
                    falsification_criterion="Check the Treasury release register.")
    assert ex is not None
    assert ex.score is None


def test_divination_needs_a_resolve_by_date():
    ex, rejects = _accept("That figure has never been published.",
                          attr="divination",
                          falsification_criterion="Check the register.")
    assert ex is None
    assert rejects["divination:missing_resolve_by"] == 1


# --- the text tier must carry one -------------------------------------------

@pytest.mark.parametrize("bad", [None, "high"])
def test_a_text_attribute_without_a_usable_score_is_rejected(bad):
    ex, rejects = _accept("That figure has never been published.", score=bad)
    assert ex is None
    assert rejects["civility:no_score"] == 1


def test_scores_are_clamped_into_range():
    ex, _ = _accept("That figure has never been published.", score=1.4)
    assert ex.score == 1.0


# --- the registry itself -----------------------------------------------------

def test_charisma_is_retired_not_merely_absent():
    """Old datasets still contain it; reading them must not crash."""
    assert "charisma" not in attributes.ATTRIBUTES
    assert "charisma" in attributes.RETIRED


def test_focus_took_its_place_in_the_text_tier():
    assert "focus" in attributes.SCORED_IN_WINDOWS
    assert attributes.tier_of("focus") == "text"


def test_the_record_tier_is_not_extracted_from_windows():
    """Forthrightness needs a question/answer pair; Strength and Authenticity
    are joined to records. Scoring them off a lone statement is what v2.0 did."""
    for attr in ("forthrightness", "strength", "authenticity"):
        assert attr not in attributes.EXTRACTED_IN_WINDOWS


def test_only_the_text_tier_is_scored_at_extraction():
    assert attributes.is_scored_at_extraction("civility")
    assert not attributes.is_scored_at_extraction("veracity")
    assert not attributes.is_scored_at_extraction("divination")


def test_every_attribute_has_a_prompt_file():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for attr in attributes.ATTRIBUTES:
        path = os.path.join(here, "prompts", f"{attr}.txt")
        assert os.path.exists(path), f"missing prompts/{attr}.txt"


def test_no_prompt_file_is_orphaned():
    """A stray prompt is a prompt nobody reviews. charisma/true/promises were
    all removed in v3.0."""
    import glob
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found = {os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(os.path.join(here, "prompts", "*.txt"))}
    assert found == set(attributes.ATTRIBUTES)


# --- subject attribution: the bug the first smoke test found ----------------

def test_an_insult_stays_on_the_speakers_own_record():
    """An MP hurling an insult is being uncivil HIMSELF, however it is aimed.
    The first v3.0 smoke test filed a Peters attack as subject='other', which
    the speaker-only aggregation filter would have deleted from his card."""
    assert attributes.normalise_subject("civility", "other") == "speaker"
    for attr in ("civility", "rigor", "specificity", "focus"):
        assert attributes.normalise_subject(attr, "other") == "speaker"


def test_strength_and_authenticity_keep_subject_other():
    """Here the distinction is real — scrutiny of an opponent's record."""
    for attr in ("strength", "authenticity", "veracity", "divination"):
        assert attributes.normalise_subject(attr, "other") == "other"


def test_a_nonsense_subject_falls_back_to_speaker():
    assert attributes.normalise_subject("strength", "themself") == "speaker"
    assert attributes.normalise_subject("strength", None) == "speaker"
