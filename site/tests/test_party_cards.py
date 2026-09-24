"""The /party aggregate: what a party card is allowed to claim.

These test the aggregation, not Flask. The rules worth pinning are the ones a
future edit could quietly break in a way that still renders: a one-MP "party"
must not be ranked against real caucuses, an aggregate of unverified guesses
must stay marked as unverified, the overall has to be recomputable from the six
numbers printed on the card, and the deviation bars have to share one scale
across cards or a long bar means a different thing on each.
"""

import pytest

import app


@pytest.fixture(autouse=True)
def _restore_attribute_set():
    """`_attrs()` below points the module's attribute set at a test-local one.

    It is module state, so without this the stub leaks into every later test in
    the session — including other files, where `_featured()` then finds no
    scored attributes and returns an empty grid.
    """
    original = app.ATTR_NAMES
    yield
    app.ATTR_NAMES = original


def _mp(pid, party, scores, geo=None):
    """A minimal _featured() item."""
    item = {"politician": {"id": pid, "name": pid, "party": party},
            "scores": scores, "n_attrs": len(scores)}
    item["geo"] = geo if geo is not None else app._geo_mean(scores)
    return item


def _attrs(*names):
    """Point the module's attribute set at a test-local one."""
    app.ATTR_NAMES = set(names)


def test_a_party_needs_enough_mps_to_be_aggregated(monkeypatch):
    _attrs("Civility")
    monkeypatch.setattr(app, "MIN_PARTY_MPS", 3)
    shown = [_mp("a", "Big", {"Civility": 50}), _mp("b", "Big", {"Civility": 60}),
             _mp("c", "Big", {"Civility": 70}), _mp("solo", "Independent", {"Civility": 99})]

    cards, too_small, _house = app._party_cards(shown)

    assert [c["party"] for c in cards] == ["Big"]
    assert too_small == [("Independent", 1)]


def test_the_overall_is_recomputable_from_the_printed_numbers():
    # The card prints rounded attribute means; its overall must be the geometric
    # mean OF THOSE, not of the members' own overalls — otherwise the number on
    # the card cannot be checked against the card.
    _attrs("Civility", "Rigor")
    shown = [_mp("a", "P", {"Civility": 40, "Rigor": 90}),
             _mp("b", "P", {"Civility": 60, "Rigor": 10}),
             _mp("c", "P", {"Civility": 50, "Rigor": 50})]

    (card,), _too_small, _house = app._party_cards(shown)

    assert card["scores"] == {"Civility": 50, "Rigor": 50}
    assert card["overall"] == round(app._geo_mean({"Civility": 50, "Rigor": 50}))


def test_an_aggregate_of_guesses_is_still_marked_a_guess():
    # prior_score must never be published as a resolved answer (CLAUDE.md), and
    # averaging it over a caucus does not resolve it.
    _attrs("Veracity")
    shown = [_mp(p, "P", {"Veracity": 70, "Veracity_tier": "unresolved"})
             for p in "abc"]

    (card,), _too_small, _house = app._party_cards(shown)

    assert card["unver"]["Veracity"] is True


def test_a_resolved_majority_is_not_marked_a_guess():
    _attrs("Veracity")
    shown = [_mp("a", "P", {"Veracity": 70, "Veracity_tier": "resolved"}),
             _mp("b", "P", {"Veracity": 70, "Veracity_tier": "resolved"}),
             _mp("c", "P", {"Veracity": 70, "Veracity_tier": "unresolved"})]

    (card,), _too_small, _house = app._party_cards(shown)

    assert card["unver"]["Veracity"] is False


def test_an_attribute_counts_only_the_mps_that_have_it():
    # Forthrightness reaches only MPs who answer questions, so its party mean
    # rests on a fraction of the caucus; the card needs the count to say so.
    _attrs("Forthrightness")
    shown = [_mp("a", "P", {"Forthrightness": 60}),
             _mp("b", "P", {"Forthrightness": 80}),
             _mp("c", "P", {})]

    (card,), _too_small, _house = app._party_cards(shown)

    assert card["n"] == 3 and card["counts"]["Forthrightness"] == 2
    assert card["scores"]["Forthrightness"] == 70


def test_the_bars_measure_distance_from_the_house_mean():
    _attrs("Civility")
    shown = ([_mp(p, "Low", {"Civility": 40}) for p in "abc"]
             + [_mp(p, "High", {"Civility": 80}) for p in "def"])

    cards, _too_small, house = app._party_cards(shown)

    assert house == {"Civility": 60}
    by_party = {c["party"]: c["dev_by_attr"]["Civility"]["delta"] for c in cards}
    assert by_party == {"Low": -20, "High": 20}


def test_every_card_shares_one_bar_scale():
    # A bar is only readable against the card beside it if the widest deviation
    # on the PAGE sets the scale, not the widest on each card.
    _attrs("Civility", "Rigor")
    shown = ([_mp(p, "Swingy", {"Civility": 20, "Rigor": 50}) for p in "abc"]
             + [_mp(p, "Flat", {"Civility": 60, "Rigor": 50}) for p in "def"])

    cards, _too_small, _house = app._party_cards(shown)

    widest = max(d["width"] for c in cards for d in c["dev"])
    assert widest == 50, "the largest deviation fills half the track"
    swingy = {c["party"]: c for c in cards}["Swingy"]
    flat = {c["party"]: c for c in cards}["Flat"]
    # Same absolute deviation from the house mean -> same bar width.
    assert swingy["dev_by_attr"]["Civility"]["width"] == flat["dev_by_attr"]["Civility"]["width"]
    # No deviation -> no bar.
    assert swingy["dev_by_attr"]["Rigor"]["width"] == 0


def test_a_single_party_does_not_divide_by_zero():
    # With one party on the page it IS the House, so every deviation is zero and
    # the bar scale has nothing to normalise by. That 500'd the page.
    _attrs("Civility")
    shown = [_mp(p, "Only", {"Civility": 50}) for p in "abc"]

    (card,), _too_small, house = app._party_cards(shown)

    assert house == {"Civility": 50}
    assert card["dev_by_attr"]["Civility"] == {"attr": "Civility", "delta": 0, "width": 0.0}
