"""The routes and the two display rules that are easy to break silently.

The grade ramp and the evidence ordering are both things a page will happily
render wrongly: a broken ramp still draws a border, and evidence sorted the
wrong way still shows quotes. Neither raises.
"""

import app


def test_the_grade_ramp_gets_monotonically_darker_and_clamps():
    """A higher score is more ink. If the ramp ever stops being monotone the
    border still renders, so nothing else would notice."""
    lo, hi = app.GRADE_WINDOW
    assert app._grade_colour(lo) == app._grade_colour(lo - 50), "clamps below"
    assert app._grade_colour(hi) == app._grade_colour(hi + 50), "clamps above"

    def lightness(score):
        c = app._grade_colour(score)
        return sum(int(c[i:i + 2], 16) for i in (1, 3, 5))

    steps = [lightness(v) for v in range(lo, hi + 1, 4)]
    assert steps == sorted(steps, reverse=True), "higher score, darker border"
    assert steps[0] > steps[-1], "and the ends actually differ"


def test_every_featured_card_gets_a_colour_and_a_rank():
    shown, total = app._featured()
    assert shown and total >= len(shown)
    for d in shown:
        assert d["grade"].startswith("#") and len(d["grade"]) == 7
        assert 1 <= d["rank"] <= len(shown)
        assert d["overall"] == round(d["geo"])


def test_evidence_is_not_served_best_first():
    """Stored order is highest-score first. Serving that order means a card
    scoring 34 opens with a wall of 95s — the opposite of its evidence."""
    import data_access_jsonl as D
    pid, attr = "peters", "Civility"
    stored = D.get_examples(pid, attr)
    if len(stored) < 30:
        return
    assert stored[0]["score"] >= stored[-1]["score"], "precondition: stored high-first"
    served = app._shuffled(stored, pid, attr)
    assert sorted(x["score"] for x in served) == sorted(x["score"] for x in stored)
    head = [x["score"] for x in served[:10]]
    assert head != [x["score"] for x in stored[:10]]


def test_the_shuffle_is_stable_for_a_given_page():
    """A reader who reloads, or shares the link, must see the same page."""
    import data_access_jsonl as D
    ex = D.get_examples("peters", "Civility")
    a = [x["text"] for x in app._shuffled(ex, "peters", "Civility")]
    b = [x["text"] for x in app._shuffled(ex, "peters", "Civility")]
    assert a == b
    c = [x["text"] for x in app._shuffled(ex, "peters", "Rigor")]
    assert a != c, "a different page gets a different order"


def test_every_route_answers():
    c = app.app.test_client()
    shown, _ = app._featured()
    pid = shown[0]["politician"]["id"]
    attr = app.attribute_descriptions[0]["id"]
    for route in ("/", "/party", "/data", "/about", "/rules",
                  f"/politician/{pid}", f"/attribute/{pid}/{attr}"):
        assert c.get(route).status_code == 200, route
    assert c.get("/politician/not-an-mp").status_code == 404
    assert c.get(f"/attribute/{pid}/Charisma").status_code == 404, \
        "a retired attribute must 404, not render an empty page"


def test_the_politician_page_samples_every_scored_attribute():
    c = app.app.test_client()
    shown, _ = app._featured()
    pid = shown[0]["politician"]["id"]
    html = c.get(f"/politician/{pid}").get_data(as_text=True)
    scores = shown[0]["scores"]
    for a in app.attribute_descriptions:
        if isinstance(scores.get(a["name"]), (int, float)):
            assert f'id="{a["id"]}"' in html, a["name"]
