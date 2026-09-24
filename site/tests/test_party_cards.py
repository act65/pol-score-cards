"""The /party aggregate: what a party card is allowed to claim.

These test the aggregation, not Flask. The rules worth pinning are the ones a
future edit could quietly break in a way that still renders: a one-MP "party"
must not be ranked against real caucuses, an aggregate of unverified guesses
must stay marked as unverified, and the overall printed on a card has to be
recomputable from the six numbers printed beside it.
"""

import app


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

    cards, _lo, _hi, too_small = app._party_cards(shown)

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

    (card,), _lo, _hi, _ = app._party_cards(shown)

    assert card["scores"] == {"Civility": 50, "Rigor": 50}
    assert card["overall"] == round(app._geo_mean({"Civility": 50, "Rigor": 50}))


def test_an_aggregate_of_guesses_is_still_marked_a_guess():
    # prior_score must never be published as a resolved answer (CLAUDE.md), and
    # averaging it over a caucus does not resolve it.
    _attrs("Veracity")
    shown = [_mp(p, "P", {"Veracity": 70, "Veracity_tier": "unresolved"})
             for p in "abc"]

    (card,), _lo, _hi, _ = app._party_cards(shown)

    assert card["unver"]["Veracity"] is True


def test_a_resolved_majority_is_not_marked_a_guess():
    _attrs("Veracity")
    shown = [_mp("a", "P", {"Veracity": 70, "Veracity_tier": "resolved"}),
             _mp("b", "P", {"Veracity": 70, "Veracity_tier": "resolved"}),
             _mp("c", "P", {"Veracity": 70, "Veracity_tier": "unresolved"})]

    (card,), _lo, _hi, _ = app._party_cards(shown)

    assert card["unver"]["Veracity"] is False


def test_an_attribute_counts_only_the_mps_that_have_it():
    # Forthrightness reaches only MPs who answer questions, so its party mean
    # rests on a fraction of the caucus; the card needs the count to say so.
    _attrs("Forthrightness")
    shown = [_mp("a", "P", {"Forthrightness": 60}),
             _mp("b", "P", {"Forthrightness": 80}),
             _mp("c", "P", {})]

    (card,), _lo, _hi, _ = app._party_cards(shown)

    assert card["n"] == 3 and card["counts"]["Forthrightness"] == 2
    assert card["scores"]["Forthrightness"] == 70


def test_mps_on_the_same_score_stack_instead_of_overprinting():
    _attrs("Civility")
    shown = [_mp(p, "P", {"Civility": 50}) for p in "abcd"]

    (card,), _lo, _hi, _ = app._party_cards(shown)

    bottoms = [d["bottom"] for d in card["dots"]]
    assert len(set(bottoms)) == 4, "four MPs on one score must be four dots"
    assert bottoms == sorted(bottoms)


def test_every_card_shares_one_axis():
    # The blocks are only comparable if a dot's position means the same thing on
    # each card, so the scale is global, not per-party.
    _attrs("Civility")
    shown = ([_mp(p, "Low", {"Civility": 40}) for p in "abc"]
             + [_mp(p, "High", {"Civility": 80}) for p in "def"])

    cards, lo, hi, _ = app._party_cards(shown)

    assert lo < 40 and hi > 80
    assert {c["party"] for c in cards} == {"Low", "High"}
    assert all(0 <= d["x"] <= 100 for c in cards for d in c["dots"])
