"""Offline tests for the manifesto / coalition-agreement scraper (no network).

    cd data/scrapers && python -m pytest test_manifestos.py
"""

import manifestos as m
import pytest


# --- registry integrity ----------------------------------------------------

def test_registry_ids_are_unique():
    ids = [d["doc_id"] for d in m.REGISTRY]
    assert len(ids) == len(set(ids))


def test_registry_entries_are_complete():
    for d in m.REGISTRY:
        assert d["format"] in ("pdf", "html"), d["doc_id"]
        assert d["kind"] in ("coalition_agreement", "policy_platform"), d["doc_id"]
        assert d["url"].startswith("https://"), d["doc_id"]
        assert d["party"] and d["title"]


def test_coalition_agreements_are_not_archive_fetched():
    """They are stable signed PDFs at a fixed URL; a Wayback copy adds nothing."""
    for d in m.REGISTRY:
        if d["kind"] == "coalition_agreement":
            assert d["archive"] is False


# --- HTML extraction -------------------------------------------------------

def test_extract_html_drops_chrome_and_keeps_content():
    html = b"""<html><body>
      <nav>Home Donate Join</nav><script>var x=1;</script><style>p{}</style>
      <main><h1>Housing</h1><p>We will build 10,000 homes.</p></main>
      <footer>Authorised by someone</footer></body></html>"""
    text = m.extract_html(html)
    assert "We will build 10,000 homes." in text
    assert "Donate" not in text and "var x" not in text and "Authorised" not in text


def test_tidy_collapses_whitespace_and_nbsp():
    assert m._tidy("a\xa0 b\n\n\n  c  ") == "a b\nc"


# --- sub-page discovery ----------------------------------------------------

INDEX = b"""<html><body>
  <a href="/policy/housing">Housing</a>
  <a href="/policy/health">Health</a>
  <a href="/policy/housing#top">Housing again</a>
  <a href="/donate">Donate</a>
  <a href="https://other.example/policy/tax">Offsite</a>
  <a href="/policy/a/b/c/d/e">Too deep</a>
</body></html>"""


def test_sub_links_finds_policy_pages_only():
    links = m._sub_links(INDEX, "https://party.example/policy", limit=10)
    assert "https://party.example/policy/housing" in links
    assert "https://party.example/policy/health" in links
    assert not any("donate" in u for u in links)
    assert not any("other.example" in u for u in links)


def test_sub_links_dedupes_fragments_and_respects_limit():
    links = m._sub_links(INDEX, "https://party.example/policy", limit=10)
    assert len(links) == len(set(links))
    assert len(m._sub_links(INDEX, "https://party.example/policy", limit=1)) == 1


def test_sub_links_skips_deep_paths():
    links = m._sub_links(INDEX, "https://party.example/policy", limit=10)
    assert not any(u.endswith("/a/b/c/d/e") for u in links)


WAYBACK_INDEX = b"""<html><body>
  <a href="/web/20231010145455/https://party.example/policy/housing">Housing</a>
  <a href="/web/20231010145455/https://party.example/donate">Donate</a>
</body></html>"""


def test_sub_links_works_inside_a_wayback_snapshot():
    """Wayback rewrites hrefs, so the crawl must stay in the same snapshot."""
    base = "https://web.archive.org/web/20231010145455/https://party.example/policy"
    links = m._sub_links(WAYBACK_INDEX, base, limit=10)
    assert links == ["https://web.archive.org/web/20231010145455/"
                     "https://party.example/policy/housing"]


# --- snapshot dating -------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ("20231010120000", "20231010", 0),
    ("20231002120000", "20231010", 8),
    ("20250708022944", "20231010", 637),
])
def test_days_apart(a, b, expected):
    assert m._days_apart(a, b) == expected


def test_record_keeps_both_urls_apart():
    """The archived URL must never be mistaken for the party's own URL."""
    doc = {"doc_id": "policy-x", "party": "X", "kind": "policy_platform",
           "title": "X policy", "url": "https://x.example/policy"}
    r = m._record(doc, "archive", "https://web.archive.org/web/2023/x", "text")
    assert r["source_url"] == "https://x.example/policy"
    assert r["fetched_url"].startswith("https://web.archive.org/")
    assert r["doc_id"] == "policy-x--archive"
    assert r["chars"] == 4
