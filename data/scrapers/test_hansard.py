"""Tests for the Hansard transcript parser (no network)."""

import hansard

STRUCTURED = """
<html><body>
<div class="body-text--hansard">
  <h1>Questions to Ministers</h1>
  <span class="publish-date"><strong>Date:</strong> 19 June 2026</span>
  <div class="Speech"><strong class="Speaker">Hon David Seymour</strong>
    <p>The Government is delivering on its promises to New Zealanders.</p></div>
  <div class="Speech"><strong class="Speaker">Chloe Swarbrick</strong>
    <p>Point of order, Madam Speaker, the Minister did not answer the question.</p></div>
</div></body></html>
"""

CHALLENGE = """<html><head><title>Radware Page</title></head>
<body><p class="verify-message">Verifying your browser before proceeding...</p></body></html>"""

FALLBACK = """<html><body><main><h2>General Debate</h2>
<p>First paragraph of debate.</p><p>Second paragraph.</p></main></body></html>"""


def test_parses_structured_speeches():
    rec = hansard.parse_hansard_html(STRUCTURED, "https://hansard.parliament.nz/x")
    assert rec is not None
    assert rec["headline"] == "Questions to Ministers"
    assert rec["date"] == "19 June 2026"
    assert rec["source"] == "hansard"
    assert rec["author"] == "Hon David Seymour"
    assert "Hon David Seymour: The Government is delivering" in rec["content"]
    assert "Chloe Swarbrick: Point of order" in rec["content"]
    assert rec["url"].endswith("/x")


def test_challenge_page_returns_none():
    assert hansard.parse_hansard_html(CHALLENGE, "u") is None


def test_fallback_paragraphs():
    rec = hansard.parse_hansard_html(FALLBACK, "u")
    assert rec is not None
    assert rec["headline"] == "General Debate"
    assert "First paragraph of debate." in rec["content"]
    assert "Second paragraph." in rec["content"]
