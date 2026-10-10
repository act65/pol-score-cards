"""Calibration's epistemic class is a closed set, and the prompt says so.

The 2025-10 pilot emitted the class and the confidence markers in one
semicolon-joined field, and 3.9% of rows fused two classes ("settled_fact plus
value", "value dressed as settled_fact"). Those rows score sensibly but cannot
be grouped, and the whole measurement is per-class — "is this posture available
to THIS kind of claim" — so an unbucketable class makes the score unauditable.
"""
import json
import pathlib
import re

import pytest
from pydantic import ValidationError

import extract

HERE = pathlib.Path(__file__).resolve().parent.parent
CLASSES = ("value", "settled_fact", "contested_empirical", "forecast")


def _score(**kw):
    """One per-attribute score block — where the model is asked for the class."""
    kw.setdefault("attribute", "calibration")
    kw.setdefault("explanation", "because")
    return extract._AttrScore(**kw)


def test_the_four_classes_are_the_closed_set():
    assert extract.CLAIM_CLASS.__args__ == CLASSES


@pytest.mark.parametrize("cls", CLASSES)
def test_each_class_is_accepted(cls):
    assert _score(claim_class=cls).claim_class == cls


@pytest.mark.parametrize("bad", [
    "settled_fact plus value",          # the fused shape, 10 rows in the pilot
    "value dressed as settled_fact",
    "settled_fact; 'I believe'",        # the pilot's semicolon shape
    "SettledFact",
    "fact",
])
def test_a_fused_or_freetext_class_is_rejected(bad):
    with pytest.raises(ValidationError):
        _score(claim_class=bad)


def test_the_class_stays_optional_for_every_other_attribute():
    """Only calibration requires it; nothing else should be forced to emit."""
    ex = _score()
    assert ex.claim_class is None
    assert ex.confidence_markers is None


def test_markers_are_free_text_because_they_are_a_quote():
    ex = _score(claim_class="forecast",
                confidence_markers="'will inevitably lead to'")
    assert ex.confidence_markers == "'will inevitably lead to'"


def test_the_prompt_agrees_with_the_schema():
    """ATTRIBUTES.md's rule: where the prompt and the contract disagree, the
    prompt is the bug. Same applies to the prompt and the schema."""
    txt = (HERE / "prompts" / "calibration.txt").read_text()
    assert "`confidence_markers`" in txt, "prompt must ask for the new field"
    assert "EXACTLY one of" in txt, "prompt must say the class is a closed set"
    for cls in CLASSES:
        assert f"`{cls}`" in txt
    assert 'Do not write "settled_fact plus value"' in txt, \
        "the prompt must name the fused failure the pilot found"


def test_the_stored_example_carries_both_fields():
    """Internal model is permissive (it also reads the pilot's old rows), but
    both fields must exist or the data is lost on the way to disk."""
    f = extract.Example.model_fields
    assert "claim_class" in f and "confidence_markers" in f


def test_the_pilot_data_still_reads_under_the_old_shape():
    """The pilot predates the split; its rows must stay comparable."""
    pilot = HERE / "pilot_calibration" / "calibration_pilot.jsonl"
    if not pilot.exists():
        pytest.skip("pilot output not present")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "cal_analyse", HERE / "pilot_calibration" / "analyse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = [json.loads(l) for l in pilot.open()]
    ex = [e for r in rows
          for v in r["examples_by_attribute"].values() for e in v]
    assert ex, "pilot file had no examples"
    clean = [e for e in ex if mod._cls(e) in CLASSES]
    # the semicolon split must recover the class for the overwhelming majority
    assert len(clean) / len(ex) > 0.95


# --- settled_fact is ineligible (2026-10-10) ---------------------------------
# The class ran mean 88 / sd 14 in the pilot against sd 24-31 for the other
# three, and per-MP share of it varied 0-45% and correlated +0.39 with the
# score. So it was measuring which subjects an MP talks about, not how well
# they calibrate. It stays in the enum because the prompt still asks the model
# to CLASSIFY it (deciding the class first is the instrument's whole design);
# it is emission that is blocked, which also lets us audit leakage.

def test_settled_fact_is_still_a_classifiable_class():
    assert "settled_fact" in extract.CLAIM_CLASS.__args__
    assert _score(claim_class="settled_fact").claim_class == "settled_fact"


def test_the_prompt_makes_settled_fact_ineligible():
    txt = (HERE / "prompts" / "calibration.txt").read_text()
    assert "INELIGIBLE — EMIT NOTHING" in txt
    assert "A claim whose class is `settled_fact`" in txt
    assert "Still classify it, then emit nothing" in txt, \
        "classify-then-drop, not skip-before-classifying"


def test_the_prompt_keeps_the_two_cases_the_filter_must_not_eat():
    """Dropping settled_fact must not drop asserting a contested claim as fact,
    nor dressing an opinion as a finding — those are the whole point."""
    txt = (HERE / "prompts" / "calibration.txt").read_text()
    assert "a contested claim ASSERTED as settled fact" in txt
    assert "is `contested_empirical`" in txt
    assert "an opinion dressed as a finding is `value`" in txt


def test_the_prompt_drops_the_class_whole_not_just_its_high_scores():
    """Keeping only low-scoring settled_fact rows would make the score depend
    on which MPs we happened to catch erring on a published statistic."""
    txt = (HERE / "prompts" / "calibration.txt").read_text()
    assert "we do not keep the half of it that happens to score" in txt


def _bullets(txt: str) -> list:
    """The worked examples, each rejoined from the lines it wraps across."""
    out, cur = [], None
    for line in txt.splitlines():
        if line.startswith("- "):
            if cur:
                out.append(" ".join(cur))
            cur = [line[2:].strip()]
        elif cur is not None and line.startswith("  "):
            cur.append(line.strip())
        elif cur:
            out.append(" ".join(cur))
            cur = None
    if cur:
        out.append(" ".join(cur))
    return out


def test_no_worked_example_still_scores_a_settled_fact():
    """A prompt that forbids the class but shows it earning 1.0 is a bug."""
    txt = (HERE / "prompts" / "calibration.txt").read_text()
    scored = re.compile(r"\u2192\s*\d?\.?\d")
    offenders = [b for b in _bullets(txt)
                 if "`settled_fact`" in b and scored.search(b)]
    assert not offenders, \
        "worked example gives a settled_fact a score: " + offenders[0][:120]


def test_the_ineligible_settled_fact_examples_are_still_shown():
    """Keep them as examples — the model has to recognise the class to drop
    it, and both the right and the wrong posture on it must be demonstrated."""
    bl = _bullets((HERE / "prompts" / "calibration.txt").read_text())
    shown = [b for b in bl if "`settled_fact`" in b and "INELIGIBLE" in b]
    assert len(shown) >= 2, "show both the plain assertion and the hedged one"
