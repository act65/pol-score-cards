"""The development notes: files in notes/, rendered as pages, built statically.

Three things can break silently here. A post can have malformed front matter and
vanish from the index rather than erroring. A draft can leak into the published
build. And a post can be reachable on the dev server but absent from the static
site, because freeze.py enumerates pages from the data rather than from the route
table — so a new route that nobody adds there is simply not deployed.
"""

import datetime
import re
from html import unescape

import pytest

import app
import notes


def test_there_are_notes_and_every_one_parses():
    """A malformed post raises at load, rather than disappearing quietly."""
    all_ = notes.all_notes(include_drafts=True)
    assert all_, "no notes found"
    for n in all_:
        assert n["title"] and n["summary"]
        assert isinstance(n["date"], datetime.date)
        assert n["html"].strip(), n["slug"]


def test_front_matter_is_required():
    with pytest.raises(ValueError, match="no front matter"):
        notes._parse("# Just a heading\n", "x")
    with pytest.raises(ValueError, match="missing summary"):
        notes._parse("---\ntitle: T\ndate: 2026-01-01\n---\nbody\n", "x")
    with pytest.raises(ValueError, match="bad date"):
        notes._parse("---\ntitle: T\ndate: last tuesday\nsummary: s\n---\nb\n", "x")


def test_notes_are_newest_first():
    dates = [n["date"] for n in notes.all_notes()]
    assert dates == sorted(dates, reverse=True)


def test_drafts_are_not_published():
    published = {n["slug"] for n in notes.all_notes()}
    drafts = {n["slug"] for n in notes.all_notes(include_drafts=True) if n["draft"]}
    assert not (published & drafts)
    for slug in drafts:
        assert notes.get_note(slug) is None, f"draft {slug} is reachable"


def test_the_index_lists_every_published_note():
    html = app.app.test_client().get("/notes").get_data(as_text=True)
    for n in notes.all_notes():
        assert f"/notes/{n['slug']}" in html
        assert n["title"] in html


def test_every_note_renders():
    c = app.app.test_client()
    for n in notes.all_notes():
        r = c.get(f"/notes/{n['slug']}")
        assert r.status_code == 200, n["slug"]
        body = r.get_data(as_text=True)
        assert n["title"] in body
        # The markdown actually became HTML rather than arriving as source.
        assert "<p>" in body


def test_an_unknown_slug_is_404_not_an_error():
    assert app.app.test_client().get("/notes/no-such-note").status_code == 404


def test_tables_survive_the_markdown_pass():
    """These posts carry their argument in tables; the `tables` extension not
    being loaded would render them as literal pipes and nobody would notice."""
    c = app.app.test_client()
    assert any("<table>" in c.get(f"/notes/{n['slug']}").get_data(as_text=True)
               for n in notes.all_notes()), "no note rendered a table"
    assert "|---" not in c.get("/notes").get_data(as_text=True)


def test_notes_carry_their_own_link_preview():
    """The index's description would otherwise be reused for every post."""
    c = app.app.test_client()
    for n in notes.all_notes():
        # Summaries contain apostrophes and dashes, which the template escapes.
        text = unescape(c.get(f"/notes/{n['slug']}").get_data(as_text=True))
        assert n["summary"] in text, n["slug"]


def test_the_header_links_to_the_notes_from_every_page():
    c = app.app.test_client()
    for route in ("/", "/party", "/data", "/about", "/rules", "/notes"):
        assert "/notes" in c.get(route).get_data(as_text=True), route


def test_the_static_build_includes_every_note():
    """freeze.py enumerates pages itself, so a route added to app.py alone would
    work on the dev server and be missing from the deployed site."""
    import freeze
    urls = freeze._urls()
    assert "/notes" in urls
    for n in notes.all_notes():
        assert f"/notes/{n['slug']}" in urls, n["slug"]


def test_internal_links_in_notes_point_at_real_pages():
    """A cross-reference between posts is easy to get wrong and silent."""
    c = app.app.test_client()
    for n in notes.all_notes():
        for href in re.findall(r'href="(/[^"#]*)', n["html"]):
            assert c.get(href).status_code == 200, f"{n['slug']} -> {href}"
