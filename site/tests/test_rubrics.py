"""The rubric pages are a reading of the prompts, and readings go stale.

`site/rubrics.json` explains each attribute to a person; `prompts/<id>.txt` is
what the model is actually given. Nothing links them at runtime, so when a
prompt is rewritten the page keeps confidently describing the old instrument
and nothing fails. These tests are that link.
"""

import json
import os
import re

import pytest

import app

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.abspath(os.path.join(HERE, "..", "..",
                                       "attribute-extraction", "prompts"))


def _prompt_question(attribute):
    path = os.path.join(PROMPTS, f"{attribute.lower()}.txt")
    with open(path, encoding="utf-8") as f:
        head = f.read(400)
    m = re.search(r"THE ONE QUESTION:\s*(.+)", head)
    return m.group(1).strip() if m else None


@pytest.fixture(scope="module")
def rubrics():
    with open(app._RUBRICS_PATH, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def test_every_published_attribute_has_a_page(rubrics):
    published = {a["id"] for a in app.attribute_descriptions}
    assert published <= set(rubrics), f"no rubric page for {published - set(rubrics)}"


def test_no_page_for_an_attribute_the_site_does_not_publish(rubrics):
    """A rubric page for a withheld attribute is a live page describing a score
    nobody can see — the way Charisma stayed on the site after it was cut."""
    published = {a["id"] for a in app.attribute_descriptions}
    assert set(rubrics) <= published, f"orphan rubric: {set(rubrics) - published}"


def test_each_page_asks_the_same_question_as_its_prompt(rubrics):
    for attribute, rub in rubrics.items():
        expected = _prompt_question(attribute)
        assert expected, f"{attribute}.txt has no THE ONE QUESTION line"
        assert rub["question"] == expected, (
            f"{attribute}: page asks {rub['question']!r}, "
            f"prompt asks {expected!r}")


def test_each_page_has_a_scale_and_worked_examples(rubrics):
    for attribute, rub in rubrics.items():
        assert len(rub["scale"]) >= 3, attribute
        assert len(rub["examples"]) >= 3, attribute
        assert rub["not_this"], f"{attribute} claims no boundaries with others"
        scores = [s["score"] for s in rub["scale"]]
        assert scores == sorted(scores, reverse=True), f"{attribute}: scale runs high to low"


def test_the_boundaries_point_at_real_attributes(rubrics):
    names = {a["name"] for a in app.attribute_descriptions}
    for attribute, rub in rubrics.items():
        for n in rub["not_this"]:
            assert n["attr"] in names, f"{attribute} -> {n['attr']} is not published"


def test_every_rubric_page_renders(rubrics):
    c = app.app.test_client()
    for attribute in rubrics:
        assert c.get(f"/rubric/{attribute}").status_code == 200, attribute
    assert c.get("/rubric/Charisma").status_code == 404
