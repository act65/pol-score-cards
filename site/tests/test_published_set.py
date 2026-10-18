"""What the cards claim, and what they no longer claim.

Six attributes are published. As of 2026-10-18 every one of them is scored from
the words of the speech at extraction time: Veracity moved to WITHHELD and
Calibration took its card slot. That is a narrowing of the site's claims, and
it should be impossible to undo by accident.

Two sibling modules (test_evidence_sources, test_pending_predictions) now skip,
because they exercise the search-tier UI and the dataset has no search-tier
rows. A skip that nobody checks is indistinguishable from a feature that
broke, so these tests assert the reason.
"""
import os
import sys

import pytest

import app
import data_access_jsonl

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "attribute-extraction")))
import attributes as registry  # noqa: E402

EXPECTED = {"Focus", "Civility", "Rigor", "Specificity", "Acuity", "Calibration"}


def test_the_published_set_is_the_six_we_think_it_is():
    assert {a["name"] for a in app.attribute_descriptions} == EXPECTED


def test_the_dataset_agrees_with_the_registry():
    """The site reads a BUILT dataset, not the registry — the two drift, and
    that drift is how Charisma survived in the site copy after it was cut."""
    assert {a["name"] for a in app.attribute_descriptions} == \
        {a.name for a in registry.PUBLISHED}


def test_veracity_and_divination_are_withheld_not_deleted():
    """The decision was to return to both in the next version, so the
    definitions, prompts and resolver must all still be there."""
    for attr in ("veracity", "divination"):
        assert attr in registry.WITHHELD
        assert attr in registry.BY_ID, f"{attr} definition was deleted"
        assert registry.BY_ID[attr].tier == "search"


def test_no_published_attribute_is_scored_by_search():
    """The reason the two sibling modules skip. If this fails, they should be
    running again — un-skip them rather than weakening this."""
    assert not [a for a in registry.PUBLISHED if a.tier == "search"]


def test_no_card_shows_an_unverified_guess():
    """`prior_score` is the model's unaided guess. It was on 133 of 133 cards
    while Veracity was published, with 2.6% of claims actually resolved. No
    published row may carry one now."""
    bad = [e for e in data_access_jsonl.get_all_examples()
           if e.get("prior_score") is not None]
    assert not bad, f"{len(bad)} published examples still carry a prior_score"


def test_every_published_score_is_a_real_number():
    """A pending row is never a zero, and now there are no pending rows at
    all — so any score the cards carry must be an actual number."""
    bad = []
    for pol in data_access_jsonl.get_all_politicians():
        row = data_access_jsonl.get_scores(pol["id"]) or {}
        for name in EXPECTED:
            v = row.get(name)
            if v is not None and not isinstance(v, (int, float)):
                bad.append((pol["id"], name, v))
    assert not bad, bad[:5]


def test_no_score_row_mentions_a_withdrawn_attribute():
    for pol in data_access_jsonl.get_all_politicians():
        row = data_access_jsonl.get_scores(pol["id"]) or {}
        for gone in ("Veracity", "Divination", "Charisma"):
            assert gone not in row, f"{pol['id']} still carries {gone}"


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_each_published_attribute_has_an_evidence_page(attr):
    """One MP is enough: the route is per (politician, attribute), and a 500
    here is what fails the CI freeze."""
    c = app.app.test_client()
    pid = data_access_jsonl.get_all_politicians()[0]["id"]
    assert c.get(f"/attribute/{pid}/{attr}").status_code == 200


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_each_published_attribute_has_a_rubric_page(attr):
    c = app.app.test_client()
    assert c.get(f"/rubric/{attr}").status_code == 200


def test_the_withdrawn_attributes_serve_no_rubric():
    c = app.app.test_client()
    for gone in ("Veracity", "Divination", "Charisma", "Forthrightness"):
        assert c.get(f"/rubric/{gone}").status_code == 404, gone
