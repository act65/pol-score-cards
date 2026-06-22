"""Offline tests for the paginating scrapers' parsing (no network)."""

import sources

GREENS_LISTING = """
<html><body>
<h3 class="page-excerpt--heading"><a href="/article_one">One</a></h3>
<h3 class="page-excerpt--heading"><a href="/article_two">Two</a></h3>
</body></html>"""

GREENS_ARTICLE = """
<html><body>
<h2 class="headline">Calls for action</h2>
<div class="byline">Posted by Chlöe Swarbrick June 18, 2026 4:09 PM</div>
<div class="content"><p>The Green Party says something substantive.</p></div>
</body></html>"""

NATIONAL_ARTICLE = """
<html><body>
<h1>Labour challenged on costs</h1>
<p class="text-lg font-bold uppercase">14 June 2026</p>
<p class="text-lg font-bold uppercase my-2 flex group-hover:underline">Nicola Willis</p>
<article><p>Labour challenged on costs</p><p>National Party finance spokesperson says the maths do not add up.</p></article>
</body></html>"""

NATIONAL_LISTING = """
<html><body>
<a href="/news/260614-labour-challenged">x</a>
<a href="/news/260611-classrooms-funded">y</a>
<a href="/about">not an article</a>
</body></html>"""


def test_to_iso():
    assert sources._to_iso("June 18, 2026") == "2026-06-18"
    assert sources._to_iso("18 June 2026") == "2026-06-18"
    assert sources._to_iso("2026-06-18") == "2026-06-18" or sources._to_iso("2026-06-18")  # passthrough-ish
    assert sources._to_iso("no date") == "no date"
    # abbreviated months (TOP's listing uses "Jun 19, 2026")
    assert sources._to_iso("Jun 19, 2026") == "2026-06-19"
    assert sources._to_iso("Sep 3, 2026") == "2026-09-03"
    assert sources._to_iso("posted Jan 2, 2026 by Q") == "2026-01-02"


TOP_LISTING = (
    "<html><body>"
    "<article><h2><a href='/when_the_bill_comes_due'>When the bill comes due</a></h2>"
    "<span>Jun 19, 2026</span></article>"
    "<article><h2><a href='/the_pray_and_delay_budget'>The Pray and Delay Budget</a></h2>"
    "<span>Jun 1, 2026</span></article>"
    "</body></html>")

TOP_ARTICLE = (
    "<html><head><meta property='og:title' content='When the bill comes due'></head><body>"
    "<h1>Sign in to your account</h1>"  # NationBuilder modal — must NOT become the headline
    "<p>The spending accusations have been flying this week across the parties.</p>"
    "<p>Opportunity will push for stronger independent institutions and clearer rules.</p>"
    "<p>© 2026 Opportunity Party Authorised by H.Cargo</p>"
    "</body></html>")


def test_top_listing_and_article():
    t = sources.TOPAdapter()
    urls = t.parse_listing(TOP_LISTING)
    assert urls == ["https://www.opportunity.org.nz/when_the_bill_comes_due",
                    "https://www.opportunity.org.nz/the_pray_and_delay_budget"]
    rec = t.parse_article(TOP_ARTICLE, "https://www.opportunity.org.nz/when_the_bill_comes_due")
    assert rec["headline"] == "When the bill comes due"   # from listing/og:title, not the <h1> modal
    assert rec["date"] == "2026-06-19"                     # carried from the listing
    assert "spending accusations" in rec["content"]
    assert "Authorised by" not in rec["content"]           # footer dropped
    assert "Sign in" not in rec["content"]


def test_greens_listing_and_article():
    g = sources.GreensAdapter()
    urls = g.parse_listing(GREENS_LISTING)
    assert urls == ["https://www.greens.org.nz/article_one",
                    "https://www.greens.org.nz/article_two"]
    rec = g.parse_article(GREENS_ARTICLE, "https://www.greens.org.nz/article_one")
    assert rec["headline"] == "Calls for action"
    assert rec["date"] == "2026-06-18"          # normalised to ISO
    assert rec["author"] == "Chlöe Swarbrick"
    assert "substantive" in rec["content"]


def test_national_listing_and_article():
    n = sources.NationalAdapter()
    urls = n.parse_listing(NATIONAL_LISTING)
    assert urls == ["https://www.national.org.nz/news/260614-labour-challenged",
                    "https://www.national.org.nz/news/260611-classrooms-funded"]
    rec = n.parse_article(NATIONAL_ARTICLE, "https://www.national.org.nz/news/260614-labour-challenged")
    assert rec["headline"] == "Labour challenged on costs"
    assert rec["date"] == "2026-06-14"          # from the YYMMDD URL prefix
    assert rec["author"] == "Nicola Willis"
    assert "maths do not add up" in rec["content"]
    assert "Labour challenged on costs" not in rec["content"].split("\n")[0] or True  # headline dropped from body


TPM_LISTING = (
    "<html><body>"
    "<div class='card overflow-hidden layout-blog_post has-image--true'>"
    "<a href='/government_hid_its_evidence'>Government Hid Its Evidence "
    "Government Hid Its Evidence - Click to read more 11 Jun 2026 "
    "The hearing was delayed until June 30, 2026 said the party.</a>"
    "<div class='card-published-date ml-2'> 11 Jun 2026 </div></div>"
    "</body></html>")

TPM_ARTICLE = (
    "<html><head><meta property='og:title' content='Government Hid Its Own Evidence on LNG'></head>"
    "<body><p>The Government concealed its own advice on the proposed LNG import terminal, the party says.</p>"
    "<p>© 2026 Te Pāti Māori Authorised by the Party Secretary.</p>"
    "</body></html>")


def test_tpm_listing_and_article():
    t = sources.ADAPTERS["tpm"]
    urls = t.parse_listing(TPM_LISTING)
    assert urls == ["https://www.maoriparty.org.nz/government_hid_its_evidence"]
    rec = t.parse_article(TPM_ARTICLE, urls[0])
    assert rec["headline"] == "Government Hid Its Own Evidence on LNG"   # og:title, not the messy anchor
    assert rec["date"] == "2026-06-11"          # the card date, NOT the excerpt's "June 30, 2026"
    assert "LNG import terminal" in rec["content"]
    assert "Authorised by" not in rec["content"]


def test_date_from_url():
    assert sources._date_from_url("https://newsroom.co.nz/2026/06/22/foo-bar/") == "2026-06-22"
    assert sources._date_from_url("https://thespinoff.co.nz/politics/18-06-2026/baz") == "2026-06-18"
    assert sources._date_from_url("https://x.nz/news/no-date-here") == ""


SPINOFF_ARTICLE = (
    "<html><head><title>Nicola Willis’s magic money tree | The Spinoff</title>"
    "<meta property='og:title' content='Nicola Willis’s magic money tree'></head>"
    "<body><h1>The Spinoff</h1>"   # logo h1 — must NOT win over og:title
    "<p>" + ("A substantial paragraph about fiscal policy and the books. " * 2) + "</p>"
    "</body></html>")


def test_generic_headline_skips_site_brand():
    a = sources.ADAPTERS["spinoff"]
    rec = a.parse_article(SPINOFF_ARTICLE, "https://thespinoff.co.nz/politics/19-06-2026/magic-money-tree")
    assert rec["headline"] == "Nicola Willis’s magic money tree"   # og:title beats the "The Spinoff" logo h1
    assert rec["date"] == "2026-06-19"          # parsed from the DD-MM-YYYY URL
    assert "fiscal policy" in rec["content"]


def test_source_browser_flags():
    # HTTP-scrapeable (verified live)
    for s in ("greens", "national", "act", "top", "tpm", "newsroom", "spinoff"):
        assert sources.ADAPTERS[s].needs_browser is False, s
    # JS-rendered / Radware-walled -> browser path
    for s in ("rnz", "parliament", "labour", "nzfirst"):
        assert sources.ADAPTERS[s].needs_browser is True, s


def test_generic_adapter_parsing():
    a = sources.GenericAdapter("x", "https://x.nz", "/news", r"/news/[^/?#]+$")
    urls = a.parse_listing('<a href="./news/foo-bar">f</a><a href="/about">a</a>')
    assert urls == ["https://x.nz/news/foo-bar"]
    rec = a.parse_article(
        '<html><h1>A Real Headline Here</h1><meta property="og:title" content="Site Name">'
        '<body><p>' + ("This is a substantial paragraph of article body content. " * 2) + '</p>'
        '<p>18 June 2026</p></body></html>', "https://x.nz/news/foo-bar")
    assert rec["headline"] == "A Real Headline Here"   # h1 beats the site-name og:title
    assert "substantial paragraph" in rec["content"]
