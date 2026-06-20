"""Paginating, date-windowed scrapers for the project's sources.

One driver paginates a source's listing pages (newest-first), fetches each
article, and stops once it crosses the date cutoff (`--months`) or hits
`--max`. So you can pull as much history as you like:

    python sources.py scrape --source greens   --months 6  --out ../data/greens_6mo.json
    python sources.py scrape --source national --months 12 --out ../data/national_1yr.json
    python sources.py scrape --source greens   --max 20     --out sample.json

Sources:
  greens, national  — plain HTML, scraped with requests (verified working).
  rnz, parliament   — JS-rendered / behind a Radware anti-bot wall, so they go
                      through the Playwright browser path (needs
                      `pip install playwright && playwright install chromium`;
                      see data/HANSARD_HOWTO.md). Add --browser to force it.

Output is the standard schema: {headline, date, author, content, url}.
"""

from __future__ import annotations

import re
import time

import fire
from bs4 import BeautifulSoup

from utils import format_text, is_recent, make_request, parse_date_loose, save_to_json

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# Month matcher accepts both full names and 3-letter abbreviations ("June" and
# "Jun"), since sites differ (e.g. TOP's listing uses "Jun 19, 2026").
_MON3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_MON_RE = "(" + "|".join(m + r"[a-z]*" for m in _MON3) + r")\.?"
_DATE_TEXT = re.compile(r"(\d{1,2})\s+" + _MON_RE + r"\s+(\d{4})", re.I)
_DATE_TEXT2 = re.compile(_MON_RE + r"\s+(\d{1,2}),?\s+(\d{4})", re.I)


def _to_iso(text: str) -> str:
    """'June 18, 2026' / 'Jun 18, 2026' / '18 June 2026' -> '2026-06-18' (so the
    date window works). Returns the original text if it can't be parsed."""
    if not text:
        return ""
    m = _DATE_TEXT2.search(text)
    if m:
        mon, day, year = m.group(1), m.group(2), m.group(3)
    else:
        m = _DATE_TEXT.search(text)
        if not m:
            return text
        day, mon, year = m.group(1), m.group(2), m.group(3)
    month = _MON3.index(mon.lower()[:3]) + 1
    return f"{year}-{month:02d}-{int(day):02d}"


def _http_fetch(url: str) -> str | None:
    resp = make_request(url, delay_seconds=0)
    if resp is None:
        return None
    # Some sites (e.g. ACT) don't declare a charset, so requests defaults to
    # latin-1 and mangles UTF-8 curly quotes. Detect the real encoding.
    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "latin-1"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _browser_fetch(url: str) -> str | None:
    import hansard  # reuse the Radware/SPA-aware Playwright fetcher
    return hansard.fetch_via_playwright(url)


# --------------------------------------------------------------------------
# Adapters: each knows its listing URLs and how to parse a listing + an article.
# --------------------------------------------------------------------------
class GreensAdapter:
    name = "greens"
    base = "https://www.greens.org.nz"
    start = 1
    needs_browser = False

    def listing_url(self, page):
        return f"{self.base}/media?page={page}"

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for h in soup.find_all("h3", class_="page-excerpt--heading"):
            a = h.find("a")
            if a and a.get("href"):
                urls.append(self.base + a["href"])
        return urls

    def parse_article(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        h = soup.find("h2", class_="headline")
        content = soup.find("div", class_="content")
        if not (h and content):
            return None
        byline = soup.find("div", class_="byline")
        author, date = "", ""
        if byline:
            text = byline.get_text(" ", strip=True)
            m = _DATE_TEXT2.search(text) or _DATE_TEXT.search(text)
            if m:
                date = _to_iso(m.group(0))
                author = text[: m.start()].replace("Posted by", "").strip()
        return {"headline": format_text(h.get_text()), "date": date,
                "author": author, "content": format_text(content.get_text("\n")), "url": url}


class NationalAdapter:
    name = "national"
    base = "https://www.national.org.nz"
    start = 1
    needs_browser = False
    _url_date = re.compile(r"/news/(\d{2})(\d{2})(\d{2})-")

    def listing_url(self, page):
        return f"{self.base}/news?page={page}"

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        seen, urls = set(), []
        for a in soup.find_all("a", href=re.compile(r"^/news/\d{6}-")):
            href = a["href"]
            if href not in seen:
                seen.add(href)
                urls.append(self.base + href)
        return urls

    def parse_article(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        h = soup.find("h1")
        art = soup.find("article")
        if not (h and art):
            return None
        # date: prefer the on-page date (authoritative) over the URL prefix —
        # National's 6-digit prefix isn't always YYMMDD (e.g. 270526 != a date).
        page_date, author = "", ""
        for p in soup.find_all("p", class_=re.compile("uppercase")):
            txt = p.get_text(" ", strip=True)
            if _DATE_TEXT.search(txt) or _DATE_TEXT2.search(txt):
                page_date = page_date or _to_iso(txt)
            elif txt and not author:
                author = txt
        url_date = ""
        m = self._url_date.search(url)
        if m:
            url_date = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
        date = page_date or url_date
        headline = format_text(h.get_text())
        paras = [p.get_text(" ", strip=True) for p in art.find_all("p")]
        paras = [p for p in paras if p and p != headline]
        return {"headline": headline, "date": date, "author": author,
                "content": format_text("\n".join(paras)), "url": url}


class TOPAdapter:
    """The Opportunity Party (opportunity.org.nz), NationBuilder-based. Articles
    are top-level slugs (e.g. /when_the_bill_comes_due); the publish date lives on
    the *listing* (each <article> shows "Jun 19, 2026"), not the article page, and
    the article's <h1> is a NationBuilder sign-in modal — so we carry the title +
    date from the listing and read the body from the article."""

    name = "top"
    base = "https://www.opportunity.org.nz"
    start = 1
    needs_browser = False

    def __init__(self):
        self._meta = {}  # url -> (iso_date, title), captured from the listing

    def listing_url(self, page):
        return f"{self.base}/news?page={page}"

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for art in soup.find_all("article"):
            h = art.find(["h1", "h2", "h3"])
            a = h.find("a", href=True) if h else None
            if not a:
                continue
            url = a["href"] if a["href"].startswith("http") else self.base + a["href"]
            url = url.split("#")[0]
            title = a.get_text(strip=True)
            date = _to_iso(art.get_text(" ", strip=True))  # finds "Jun 19, 2026"
            self._meta[url] = (date if date and date[0].isdigit() else "", title)
            urls.append(url)
        return urls

    def parse_article(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        date, title = self._meta.get(url, ("", ""))
        if not title:
            og = soup.find("meta", property="og:title")
            title = og["content"].strip() if og and og.get("content") else ""
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        # drop the NationBuilder authorisation/copyright footer line
        paras = [p for p in paras if len(p) > 40 and not p.lstrip().startswith("©")
                 and "Authorised by" not in p]
        content = format_text("\n".join(paras))
        if not content:
            return None
        return {"headline": title, "date": date, "author": "",
                "content": content, "url": url}


class GenericAdapter:
    """Configurable adapter for sites without bespoke selectors. Uses og:title (or
    <h1>) for the headline and the page's substantial <p>s for the body — robust
    to sites with unstable/auto-generated classes (e.g. NationBuilder, Framer).
    `needs_browser=True` routes through Playwright (JS-rendered / Radware-walled)."""

    def __init__(self, name, base, listing_path, link_re, needs_browser=False, start=1):
        self.name = name
        self.base = base
        self.listing_path = listing_path
        self.link_re = re.compile(link_re)
        self.needs_browser = needs_browser
        self.start = start

    def listing_url(self, page):
        sep = "&" if "?" in self.listing_path else "?"
        return f"{self.base}{self.listing_path}{sep}page={page}"

    def _abs(self, href):
        if href.startswith("http"):
            return href
        if href.startswith("./"):
            return self.base + href[1:]
        return self.base + ("" if href.startswith("/") else "/") + href

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls, seen = [], set()
        for a in soup.find_all("a", href=True):
            full = self._abs(a["href"]).split("#")[0]
            if self.link_re.search(full) and full not in seen:
                seen.add(full)
                urls.append(full)
        return urls

    def parse_article(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        # Prefer a real <h1> article title; fall back to og:title (which on some
        # sites — e.g. ACT — is just the site name), then <title>.
        h1 = soup.find("h1")
        og = soup.find("meta", property="og:title")
        if h1 and len(h1.get_text(strip=True)) > 10:
            headline = h1.get_text(strip=True)
        elif og and og.get("content"):
            headline = og["content"]
        else:
            headline = soup.title.get_text(strip=True) if soup.title else ""
        headline = headline.rsplit(" | ", 1)[0].strip()  # drop " | RNZ"-style suffix

        # Date, most-reliable first: <time datetime>, then meta, then a date in
        # the *headline's* neighbourhood (NOT a page-wide text search, which can
        # grab a sidebar "latest news" date — that bug made every article look
        # recent and ran the scraper through the whole archive).
        date = ""
        t = soup.find("time")
        if t and t.get("datetime"):
            date = t["datetime"][:10]
        if not date:
            m = soup.find("meta", property="article:published_time")
            if m and m.get("content"):
                date = m["content"][:10]
        if not date:
            scope = soup.find("article") or soup.find("main") or soup
            dm = _DATE_TEXT.search(scope.get_text(" ", strip=True)) or \
                 _DATE_TEXT2.search(scope.get_text(" ", strip=True))
            date = _to_iso(dm.group(0)) if dm else ""

        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        content = format_text("\n".join(p for p in paras if len(p) > 40 and p != headline))
        if not content:
            return None
        return {"headline": headline, "date": date, "author": "", "content": content, "url": url}


ADAPTERS = {a.name: a for a in (
    GreensAdapter(),
    NationalAdapter(),
    # ACT — server-rendered (NationBuilder), verified.
    GenericAdapter("act", "https://www.act.org.nz", "/news", r"/news/[^/?#]+$"),
    # TOP — NationBuilder; bespoke (date on listing, slug URLs).
    TOPAdapter(),
    # Labour & NZ First — listings are JS-rendered, so browser path.
    GenericAdapter("labour", "https://www.labour.org.nz", "/news", r"/news/[^/?#]+$", needs_browser=True),
    GenericAdapter("nzfirst", "https://www.nzfirst.nz", "/news", r"/(news|column)/[^/?#]+$", needs_browser=True),
    # RNZ — now JS-rendered; Parliament — Radware-walled. Both browser path.
    GenericAdapter("rnz", "https://www.rnz.co.nz", "/news/political", r"/news/political/\d+/", needs_browser=True),
    GenericAdapter("parliament", "https://www.parliament.nz",
                   "/en/get-involved/information-for-the-press/media-releases/",
                   r"/en/get-involved/.*media-release", needs_browser=True),
)}


def scrape(source, months=3, out=None, max=None, ref_date=None, delay=1.0,
           browser=False, max_pages=200):
    """Paginate `source` newest-first, keeping articles within `months` (or up to
    `max`), writing the standard schema to `out`."""
    if source not in ADAPTERS:
        raise SystemExit(f"unknown source '{source}'. Choose: {', '.join(ADAPTERS)}")
    adapter = ADAPTERS[source]
    fetch = _browser_fetch if (browser or adapter.needs_browser) else _http_fetch
    results, page, stop = [], adapter.start, False
    # Runaway guard: if a date window is requested but we never see an
    # out-of-window article (e.g. dates aren't parsing), don't crawl the whole
    # archive — cap the haul unless the caller set an explicit --max.
    runaway_cap = int(max) if max else (1000 if not months else 400)
    n_undated = 0
    seen_urls = set()

    while page < adapter.start + max_pages and not stop:
        lhtml = fetch(adapter.listing_url(page))
        urls = [u for u in (adapter.parse_listing(lhtml) if lhtml else []) if u not in seen_urls]
        if not urls:
            # No new links — pagination is exhausted or doesn't advance (some sites,
            # e.g. ACT, return the same page for every ?page=N). Stop rather than loop.
            print(f"[{source}] page {page}: no new links — stopping")
            break
        seen_urls.update(urls)
        print(f"[{source}] page {page}: {len(urls)} new links")
        for url in urls:
            ahtml = fetch(url)
            rec = adapter.parse_article(ahtml, url) if ahtml else None
            if not rec:
                continue
            d = parse_date_loose(rec.get("date"))
            if not d:
                n_undated += 1
            if months and d and not is_recent(rec["date"], months, ref_date):
                stop = True  # newest-first: first out-of-window article ends it
                break
            results.append(rec)
            print(f"  + {rec['date'] or '?':12} {rec['headline'][:55]}")
            if len(results) >= runaway_cap:
                if not max:
                    print(f"  [guard] hit {runaway_cap} articles without crossing the "
                          f"{months}-month cutoff ({n_undated} had unparseable dates). "
                          f"Stopping — check the source's date parsing or pass --max.")
                stop = True
                break
            time.sleep(delay)
        page += 1

    print(f"[{source}] collected {len(results)} articles")
    if out:
        save_to_json(results, out)
    return results


if __name__ == "__main__":
    fire.Fire({"scrape": scrape})
