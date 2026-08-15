"""The attribute registry must agree with everything that renders it.

    cd attribute-extraction && python -m pytest tests/test_registry_consistency.py

Charisma survived in the site copy, the icon map and the dataset builder long
after it was cut from the prompts, because each of those kept its own list.
`attributes.py` is now the single source of truth; these tests fail if a copy
drifts from it again.
"""

import json
import os

import pytest

import attributes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, ".."))


def _json(path):
    with open(path) as f:
        return json.load(f)


def test_icon_map_covers_exactly_the_live_attributes():
    """Every live attribute has an icon, and nothing retired or deferred does.

    This is the test that would have caught Charisma surviving in the site copy
    after it was cut, so it stays strict in BOTH directions: a missing icon
    breaks a card, and a stale one puts a dropped attribute back on the page."""
    icons = _json(os.path.join(REPO, "shared", "attribute_icons.json"))
    keys = {k for k in icons if not k.startswith("_")}
    assert keys == set(attributes.ATTRIBUTES), (
        f"missing: {set(attributes.ATTRIBUTES) - keys}, "
        f"stale: {keys - set(attributes.ATTRIBUTES)}")


def test_every_icon_has_a_drawn_glyph_and_a_blurb():
    icons = _json(os.path.join(REPO, "shared", "attribute_icons.json"))
    for key, spec in icons.items():
        if key.startswith("_"):
            continue
        assert spec.get("svg", "").startswith("<svg"), f"{key} has no svg"
        assert spec.get("blurb"), f"{key} has no blurb"
        assert spec.get("name")


def test_the_synced_copies_match_the_shared_source():
    """shared/sync.py copies the icon map into both apps; a stale copy means one
    surface renders a retired attribute."""
    src = _json(os.path.join(REPO, "shared", "attribute_icons.json"))
    for app in ("site", "game"):
        copy = os.path.join(REPO, app, "static", "attribute_icons.json")
        if os.path.exists(copy):
            assert _json(copy) == src, f"{app}/static is stale — run shared/sync.py"


def test_dataset_builder_reads_the_registry():
    import build_v2_dataset
    assert [a for a, _, _ in build_v2_dataset.ATTRIBUTES] == list(attributes.ATTRIBUTES)


def test_no_definition_is_empty():
    for a in attributes.ALL:
        assert a.definition.strip(), f"{a.id} has no card-facing definition"
        assert a.question.strip(), f"{a.id} has no 'one question'"


def test_tiers_are_valid_and_the_search_tier_declares_its_fields():
    for a in attributes.ALL:
        assert a.tier in ("text", "record", "search"), f"{a.id}: bad tier {a.tier}"
        if a.tier == "search":
            assert "falsification_criterion" in a.requires, (
                f"{a.id} is resolved by search but does not require a criterion — "
                "the resolver would have nothing to check against")
        if a.tier != "text":
            assert a.evidence, f"{a.id} is not text-only but names no evidence source"


@pytest.mark.parametrize("attr", ["civility", "rigor", "specificity", "focus"])
def test_text_tier_prompts_name_their_neighbours(attr):
    """Every rubric has to say what it is NOT, or the attributes collapse into
    one 'was this good' judgement again — that was r=0.96 in v2.0."""
    with open(os.path.join(HERE, "prompts", f"{attr}.txt")) as f:
        text = f.read()
    assert "THE ONE QUESTION" in text
    assert "*NOT*" in text, f"{attr} does not disclaim the neighbouring attributes"


@pytest.mark.parametrize("attr", ["veracity", "divination"])
def test_search_tier_prompts_forbid_scoring(attr):
    with open(os.path.join(HERE, "prompts", f"{attr}.txt")) as f:
        text = f.read()
    assert "YOU DO NOT SCORE" in text
    assert "falsification_criterion" in text


@pytest.mark.parametrize("attr", ["strength", "authenticity"])
def test_record_tier_prompts_are_extraction_only(attr):
    with open(os.path.join(HERE, "prompts", f"{attr}.txt")) as f:
        text = f.read()
    assert "YOU DO NOT SCORE" in text
    assert "subject=" in text, f"{attr} must explain subject attribution — it is " \
                               "the attribute where the v2.0 bug did most damage"


def test_the_civility_prompt_carries_the_new_anchor():
    with open(os.path.join(HERE, "prompts", "civility.txt")) as f:
        text = f.read()
    assert "RE-ANCHORED" in text
    assert "EXPECTED STANDARD" in text


def test_the_focus_prompt_protects_opposition_scrutiny():
    """Focus penalising an MP for holding the government to account would
    re-create the directional bias v3.0 exists to remove."""
    with open(os.path.join(HERE, "prompts", "focus.txt")) as f:
        text = f.read()
    assert "DO NOT PENALISE OPPOSITION" in text
    assert "Specificity" in text, "must warn about the overlap it is most at risk of"
