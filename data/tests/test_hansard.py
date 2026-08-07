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


BLAZOR_RENDERED = """
<html><body>
<div id="components-reconnect-modal">An unhandled error has occurred. Reload</div>
<div class="body-text--hansard"><h1>Questions to Ministers</h1>
<div class="Speech"><strong class="Speaker">Hon David Seymour</strong>
  <p>The Government is delivering on its plan for New Zealanders.</p></div>
</div></body></html>"""


def test_blazor_reconnect_modal_not_treated_as_shell():
    # Hansard's Blazor app always embeds this hidden modal; a rendered transcript
    # must NOT be rejected just because that text is present.
    rec = hansard.parse_hansard_html(BLAZOR_RENDERED, "u")
    assert rec is not None
    assert rec["author"] == "Hon David Seymour"
    assert "delivering on its plan" in rec["content"]


def test_generic_heading_falls_back_to_url_title():
    html = ('<html><body><h1>Transcript Sections</h1>'
            '<div class="Speech"><strong class="Speaker">Hon X</strong>'
            '<p>A substantive answer to the question that was asked today.</p></div></body></html>')
    url = "https://hansard.parliament.nz/hansard-transcript/2026-06-18/oral-question-2-prime-minister"
    rec = hansard.parse_hansard_html(html, url)
    assert rec["headline"] == "Oral Question 2 Prime Minister (2026-06-18)"


def test_enumerate_day_urls():
    import datetime
    urls = hansard._enumerate_day_urls(months=1, ref_date=datetime.date(2026, 6, 20))
    assert urls[0].endswith("/hansard-transcript/2026-06-19")   # newest weekday first
    assert all("/hansard-transcript/" in u for u in urls)
    # only weekdays, all within the ~1-month window
    import re
    dates = [re.search(r"(\d{4}-\d{2}-\d{2})", u).group(1) for u in urls]
    assert all(datetime.date.fromisoformat(d).weekday() < 5 for d in dates)
    assert dates[-1] >= "2026-05-21"


DAY_PAGE = ("<html><body><a>Home</a><p>Menu</p><p>Search</p>"
            "<h2>Oral Questions — Questions to Ministers</h2>"
            "<p>" + ("The Prime Minister answered the question on the economy in detail. " * 3) + "</p>"
            "<p>" + ("The Leader of the Opposition pressed for the specific figures. " * 3) + "</p>"
            "<h2>General Debate</h2>"
            "<p>" + ("A member spoke at length on regional housing policy and delivery. " * 6) + "</p>"
            "</body></html>")


def test_parse_hansard_day_splits_into_sections():
    recs = hansard.parse_hansard_day(
        DAY_PAGE, "https://hansard.parliament.nz/hansard-transcript/2026-05-28",
        min_day_chars=0)  # this fixture is small; test splitting, not the junk filter
    assert len(recs) == 2
    assert recs[0]["headline"] == "Oral Questions — Questions to Ministers (2026-05-28)"
    assert recs[1]["headline"] == "General Debate (2026-05-28)"
    assert all(r["date"] == "2026-05-28" and r["source"] == "hansard" for r in recs)
    assert "Menu" not in recs[0]["content"] and "Search" not in recs[0]["content"]  # nav dropped


def test_parse_hansard_day_chunks_and_caps():
    big = "<html><body><h2>Long Section</h2><p>" + ("word " * 40000) + "</p></body></html>"
    recs = hansard.parse_hansard_day(big, "https://hansard.parliament.nz/hansard-transcript/2026-05-28",
                                     max_chars=5000, max_sections=8)
    assert len(recs) == 8                              # capped
    assert all(len(r["content"]) <= 5000 for r in recs)
    assert "part 1" in recs[0]["headline"]            # chunked sections are numbered


def test_parse_hansard_day_skips_nonsitting_placeholder():
    placeholder = ("<html><body><h2>Calendar</h2>"
                   "<p>There are no planned meetings of the House at this time.</p></body></html>")
    assert hansard.parse_hansard_day(placeholder, "https://hansard.parliament.nz/hansard-transcript/2026-06-19") == []


def test_title_from_url():
    assert hansard._title_from_url(
        "https://hansard.parliament.nz/hansard-transcript/2026-05-28/general-debate"
    ) == "General Debate (2026-05-28)"
    assert hansard._title_from_url("https://example.com/x") == ""


def test_fallback_paragraphs():
    rec = hansard.parse_hansard_html(FALLBACK, "u")
    assert rec is not None
    assert rec["headline"] == "General Debate"
    assert "First paragraph of debate." in rec["content"]
    assert "Second paragraph." in rec["content"]


# --- division results must survive the short-paragraph filter ---------------
# Hansard prints a division as a run of SHORT paragraphs. A >40-char length
# filter used to delete the "Ayes N"/"Noes N" labels, the verdict line, and any
# tally line for a small party — silently corrupting the vote record (a 34-strong
# Noes was read as "unopposed"). See data/VOTES.md.

DIVISION_PAGE = (
    "<html><body>"
    "<h2>Education and Training Amendment Bill</h2>"
    "<p><span class='HpsItem'>A party vote was called for on the question, "
    "<span class='HpsCharacterItalics'>That the motion be agreed to</span>.</span></p>"
    "<p><span class='HpsItem'><span class='CharacterBoldCentred'>Ayes 83</span></span></p>"
    "<p><span class='HpsItem'>New Zealand National 48; Green Party of Aotearoa New Zealand 15; "
    "ACT New Zealand 11; New Zealand First 8; Kapa-Kingi.</span></p>"
    "<p><span class='HpsItem'><span class='CharacterBoldCentred'>Noes 34</span></span></p>"
    "<p><span class='HpsItem'>New Zealand Labour 34.</span></p>"
    "<p><span class='HpsItem'>Motion agreed to.</span></p>"
    "<p>Sitting date: 27 May 2026</p>"          # page chrome: no transcript span
    "</body></html>")


def _division_text():
    recs = hansard.parse_hansard_day(
        DIVISION_PAGE, "https://hansard.parliament.nz/hansard-transcript/2026-05-27",
        min_day_chars=0)
    return "\n".join(r["content"] for r in recs)


def test_day_parse_keeps_ayes_noes_labels():
    text = _division_text()
    assert "Ayes 83" in text
    assert "Noes 34" in text


def test_day_parse_keeps_short_tally_line():
    """A small party's tally is under 40 chars and was previously deleted."""
    assert "New Zealand Labour 34." in _division_text()


def test_day_parse_keeps_short_verdict_line():
    assert "Motion agreed to." in _division_text()


def test_day_parse_still_drops_short_page_chrome():
    """Chrome has no Hansard transcript span, so length is not the only test."""
    assert "Sitting date" not in _division_text()
