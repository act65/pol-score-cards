"""Tests for the 0-100 -> game-stat normaliser."""

import normalise
from game_logic import config


def test_scale_multiplier_bounds():
    assert normalise.scale_multiplier(0) == 1      # floored at 1, never 0
    assert normalise.scale_multiplier(100) == 10   # capped at 10
    assert normalise.scale_multiplier(50) == 5
    assert 1 <= normalise.scale_multiplier(7) <= 10


def test_precision_alias_maps_to_forthrightness():
    out = normalise.normalise_scores({"Precision": 90})
    assert out["forthrightness"] == 90  # percentage attr, passes through


def test_multipliers_scaled_percentages_passthrough():
    out = normalise.normalise_scores({
        "Strength": 80, "Rigor": 70, "Veracity": 100,   # multipliers -> 1-10
        "Civility": 65, "Specificity": 40,               # percentages -> 0-100
    })
    assert out["strength"] == 8
    assert out["rigor"] == 7
    assert out["veracity"] == 10
    assert out["civility"] == 65
    assert out["specificity"] == 40


def test_missing_attributes_get_default():
    out = normalise.normalise_scores({"Strength": 50}, default=50)
    assert set(out) == set(normalise.GAME_FIELDS)
    assert out["charisma"] == 50          # missing -> default (percentage)
    assert out["rigor"] == 5              # missing -> default 50 -> scaled to 5


def test_card_stats_are_sane():
    # A maxed-out real politician must not produce a 10,000-HP one-shot card.
    scores = {a: 100 for a in ("Strength", "Rigor", "Veracity", "Charisma",
                               "Civility", "Specificity", "Authenticity",
                               "Divination", "Precision")}
    card = normalise.card_from_politician(
        {"id": "x", "name": "Maxed MP", "party": "Test"}, scores)
    # strength scaled to 10 -> max_hp = 100*10 = 1000 (== starting health, not 10x it)
    assert card.max_hp <= config.STARTING_HEALTH_POINTS
    assert card.max_hp == 1000
    assert card.attack_damage_base <= 100     # 10 * 10
    assert card.defense_base <= 100
    # percentage attributes are untouched
    assert card.attributes.civility == 100
    assert card.attributes.forthrightness == 100


def test_real_deck_builds_from_site_data():
    deck = [
        normalise.card_from_politician(p, s)
        for p, s in [
            ({"id": "a", "name": "A", "party": "P"}, {"Strength": 78, "Precision": 65}),
        ]
    ]
    assert deck[0].attributes.strength == 8
    assert deck[0].attributes.forthrightness == 65
