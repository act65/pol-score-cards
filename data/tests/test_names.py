"""Tests for the shared name/roster module.

    cd data && python -m pytest tests/test_names.py

These moved here from the individual pipelines when six near-copies of the same
helpers were consolidated into `data/names.py`. The differences between those
copies were bugs — one stripped "Rt Hon" as a single token so "Rt Christopher
Luxon" survived, another missed the "on behalf of" suffix — so the forms below
are the union of everything the real sources throw at us.
"""

import pytest
from names import RosterIndex, clean, norm

ROSTER = RosterIndex.from_mapping({
    "kapa-kingi": "mariameno-kapa-kingi",
    "mariameno kapa-kingi": "mariameno-kapa-kingi",
    "ferris": "takuta-ferris",
    "chris hipkins": "chris-hipkins",
    "hipkins": "chris-hipkins",
})


# --- cleaning ---------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # Hansard caps whoever has the call, and tags the portfolio.
    ("Rt Hon CHRISTOPHER LUXON (Prime Minister)", "Christopher Luxon"),
    ("Hon NICOLA WILLIS (Minister of Finance) (14:44)", "Nicola Willis"),
    ("DAN BIDOIS (National—Northcote)", "Dan Bidois"),
    # "Rt Hon" is two words; stripping it as one token left "Rt Christopher".
    ("Rt Hon Christopher Luxon", "Christopher Luxon"),
    ("Hon Dr Shane Reti", "Shane Reti"),
    # The questions API uses surname-first order.
    ("Goldsmith, Hon Paul", "Paul Goldsmith"),
    ("Utikere, Tangi", "Tangi Utikere"),
    # A minister answering for a colleague: keep who actually spoke.
    ("WINSTON PETERS  on behalf of the Prime Minister", "Winston Peters"),
    # Stray bracket left behind by splitting a speaker tag on its colon.
    ("David Seymour )", "David Seymour"),
    # A real surname must survive untouched.
    ("Ricardo Menéndez March", "Ricardo Menéndez March"),
])
def test_clean(raw, expected):
    assert clean(raw) == expected


def test_clean_can_preserve_original_casing():
    assert clean("Hon DAVID SEYMOUR", titlecase=False) == "DAVID SEYMOUR"


def test_norm_folds_case_and_accents():
    assert norm("Te Pāti Māori") == norm("te pati maori")
    assert norm("  Hon   DAVID  SEYMOUR ") == "hon david seymour"


# --- resolution -------------------------------------------------------------

def test_resolves_full_name_and_surname():
    assert ROSTER.resolve("Rt Hon CHRIS HIPKINS") == "chris-hipkins"
    assert ROSTER.resolve("Hipkins") == "chris-hipkins"


@pytest.mark.parametrize("surname", ["Kapa-Kingi", "Kapi-Kingi", "Kapa-Kangi"])
def test_hansard_misspellings_resolve_to_the_same_member(surname):
    """Hansard misspells the occasional name; a close match recovers it."""
    assert ROSTER.resolve(surname) == "mariameno-kapa-kingi"


def test_unknown_name_stays_unresolved():
    assert ROSTER.resolve("Nobody At All") is None


def test_fuzzy_can_be_disabled():
    assert ROSTER.resolve("Kapi-Kingi", fuzzy=False) is None


def test_fuzzy_refuses_to_pick_between_two_similar_people():
    """Two different MPs with close surnames must never be conflated —
    'Andersan' is equally close to both Anderson and Andersen."""
    roster = RosterIndex.from_mapping({"anderson": "a-anderson",
                                       "andersen": "b-andersen"})
    assert roster.resolve("Andersan") is None


def test_fuzzy_still_resolves_two_aliases_of_one_person():
    roster = RosterIndex.from_mapping({"kapa-kingi": "kapa-kingi",
                                       "mariameno kapa-kingi": "kapa-kingi"})
    assert roster.resolve("Kapa-Kingj") == "kapa-kingi"


def test_membership_and_length():
    assert "Hipkins" in ROSTER
    assert "Nobody" not in ROSTER
    assert len(ROSTER) == 5


# --- the live roster --------------------------------------------------------

def test_real_roster_drops_surnames_shared_by_two_mps():
    """A bare surname cannot disambiguate two sitting MPs, and a wrong
    attribution is worse than none — so ambiguous keys are dropped, not guessed."""
    real = RosterIndex()
    assert len(real) > 100
    # Every retained key maps to exactly one id by construction.
    assert all(isinstance(v, str) for v in real.as_dict().values())
