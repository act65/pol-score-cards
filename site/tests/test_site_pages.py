"""The routes and the two display rules that are easy to break silently.

The grade ramp and the evidence ordering are both things a page will happily
render wrongly: a broken ramp still draws a border, and evidence sorted the
wrong way still shows quotes. Neither raises.
"""

import app


def test_every_featured_card_is_scored_and_ranked():
    shown, total = app._featured()
    assert shown and total >= len(shown)
    for d in shown:
        assert 1 <= d["rank"] <= len(shown)
        assert d["overall"] == round(d["geo"])
    # The border carries nothing now, so nothing should be computing a colour.
    assert not hasattr(app, "_grade_colour")


def test_every_page_with_cards_can_be_read_against_the_house():
    """The grid, a party card and a politician's card all carry the same
    toggle, and all three need both values in the markup or it shows dashes."""
    c = app.app.test_client()
    shown, _ = app._featured()
    pid = shown[0]["politician"]["id"]
    for route in ("/", "/party", f"/politician/{pid}"):
        html = c.get(route).get_data(as_text=True)
        assert html.count('data-rel="') == html.count('data-abs="') > 0, route
        assert 'data-rel="—"' not in html, route


def test_the_card_can_be_read_against_the_house():
    """The politician page toggles its card between absolute scores and each
    attribute's distance from the House average, so both numbers have to reach
    the template or the toggle silently shows em dashes."""
    shown, _ = app._featured()
    pid = shown[0]["politician"]["id"]
    html = app.app.test_client().get(f"/politician/{pid}").get_data(as_text=True)
    assert 'name="mpMode"' in html
    assert html.count('data-rel="') == html.count('data-abs="')
    assert 'data-rel="—"' not in html, "every scored attribute has a House mean"


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
                  f"/politician/{pid}", f"/attribute/{pid}/{attr}",
                  f"/rubric/{attr}"):
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


def test_the_radar_maps_scores_onto_the_rim():
    """0 at the centre, 100 at the rim. A silently wrong radius still draws a
    polygon, so nothing downstream would notice."""
    r = app._radar([("Veracity", 100), ("Focus", 0), ("Civility", 50),
                    ("Rigor", 50), ("Specificity", 50), ("Divination", 50)],
                   size=200, pad=20)
    assert r["r"] == 80
    pts = [tuple(float(v) for v in p.split(",")) for p in r["polygon"].split()]
    c = r["cx"]

    def radius(p):
        return ((p[0] - c) ** 2 + (p[1] - c) ** 2) ** 0.5

    assert abs(radius(pts[0]) - r["r"]) < 0.5, "100 sits on the rim"
    assert radius(pts[1]) < 0.5, "0 sits at the centre"
    assert abs(radius(pts[2]) - r["r"] / 2) < 0.5, "50 is halfway out"


def test_every_radar_vertex_carries_its_glyph():
    """Without the icons the shape is unreadable — nothing says which vertex is
    which. Jinja's `replace` on a Markup value escapes what it inserts, which
    silently dropped the positioning and rendered every glyph at full size."""
    r = app._radar([(a["name"], 50) for a in app.attribute_descriptions])
    for ax in r["axes"]:
        assert ax["icon"].startswith("<svg class='rd-icon'"), ax["label"]
        assert "width='12'" in ax["icon"]


def test_a_card_with_an_unscored_attribute_still_draws():
    r = app._radar([("Veracity", 60), ("Divination", None), ("Focus", 70),
                    ("Civility", 65), ("Rigor", 45), ("Specificity", 63)])
    assert r is not None and len(r["polygon"].split()) == 6
