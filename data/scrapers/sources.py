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

import datetime
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


# Some sites carry the publish date only in the article URL (Newsroom uses
# /YYYY/MM/DD/slug, The Spinoff uses /section/DD-MM-YYYY/slug). Used as a
# last-resort fallback so the date window still works for them.
_URL_YMD = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/")
_URL_DMY = re.compile(r"/(\d{2})-(\d{2})-(20\d{2})/")


def _date_from_url(url: str) -> str:
    m = _URL_YMD.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _URL_DMY.search(url)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


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
    # A single page that crashes the browser (e.g. a Chromium segfault) must not
    # abort the whole source — swallow it and move on.
    try:
        return hansard.fetch_via_playwright(url)
    except Exception as e:  # noqa: BLE001
        print(f"  [browser] failed {url}: {e}")
        return None


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

    # Any single-segment /news/<slug> is an article. National has used several
    # slug schemes over time — 6-digit (260529-foo), 8-digit (20260521-foo) and
    # bare (boost-for-law-and-order) — so we must NOT key off the date prefix, or
    # whole pages of older articles look empty. Excludes /news, /news?page=, and
    # nested paths like /news/category/x.
    _article_href = re.compile(r"^/news/[^/?#]+$")

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        seen, urls = set(), []
        for a in soup.find_all("a", href=self._article_href):
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


class NationBuilderAdapter:
    """NationBuilder blog with card-style listings (e.g. Te Pāti Māori's
    `/panui`). Like TOP, the publish date lives on the *listing* (each
    `.layout-blog_post` card carries it) and articles are top-level slugs whose
    own pages don't reliably show a date — so we carry date + title from the
    listing and read the body from the article. Paginates with `?page=N`."""

    needs_browser = False
    start = 1

    def __init__(self, name, base, listing_path):
        self.name = name
        self.base = base
        self.listing_path = listing_path
        self._meta = {}  # url -> (iso_date, title)

    def listing_url(self, page):
        sep = "&" if "?" in self.listing_path else "?"
        return f"{self.base}{self.listing_path}{sep}page={page}"

    def _abs(self, href):
        return href if href.startswith("http") else self.base + ("" if href.startswith("/") else "/") + href

    def parse_listing(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for card in soup.find_all(class_=re.compile(r"layout-blog_post")):
            a = card.find("a", href=True)
            if not a:
                continue
            url = self._abs(a["href"]).split("#")[0].split("?")[0]
            # date from the card's own date element (its body text can mention
            # other dates, e.g. an excerpt's "...until June 30, 2026").
            de = card.find(class_=re.compile(r"card-published-date|card-date"))
            date = _to_iso(de.get_text(" ", strip=True) if de else card.get_text(" ", strip=True))
            self._meta[url] = date if date and date[0].isdigit() else ""
            urls.append(url)
        return urls

    def parse_article(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        date = self._meta.get(url, "")
        # The listing anchor wraps the whole card (title repeated + excerpt), so
        # take the clean title from the article page's og:title.
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else ""
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
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

    def __init__(self, name, base, listing_path, link_re, needs_browser=False,
                 start=1, page_fmt=None, min_para=40):
        self.name = name
        self.base = base
        self.listing_path = listing_path
        self.link_re = re.compile(link_re)
        self.needs_browser = needs_browser
        self.start = start
        # Min paragraph length for body extraction. Framer/NationBuilder party
        # sites (Labour, NZ First) render a big sidebar of related-release
        # HEADLINES as <p>s (~40-70 chars) with no <article> wrapper, so the
        # default 40 sweeps them in; ~90 keeps only real prose body paragraphs.
        self.min_para = min_para
        # Some sites paginate as a path segment (WordPress: /section/page/2/)
        # rather than a ?page= query. `page_fmt` is a path template taking {n}.
        self.page_fmt = page_fmt

    def listing_url(self, page):
        if self.page_fmt and page > self.start:
            return f"{self.base}{self.page_fmt.format(n=page)}"
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
        # Headline is the trickiest cross-site bit: the first <h1> is sometimes a
        # logo ("The Spinoff") and og:title is sometimes just the site name (ACT).
        # So derive the site "brand" from the <title> suffix and pick the first
        # candidate — og:title, cleaned <title>, <h1> — that isn't the brand.
        title_tag = soup.title.get_text(strip=True) if soup.title else ""
        brand, title_main = "", title_tag
        for sep in (" | ", " — ", " - "):
            if sep in title_tag:
                title_main, brand = (s.strip() for s in title_tag.rsplit(sep, 1))
                break
        og = soup.find("meta", property="og:title")
        og_title = og["content"].strip() if og and og.get("content") else ""
        h1 = soup.find("h1")
        h1_title = h1.get_text(strip=True) if h1 else ""
        candidates = [c.rsplit(" | ", 1)[0].strip() for c in (og_title, title_main, h1_title)]
        headline = next((c for c in candidates if c and len(c) > 10 and c != brand),
                        title_main or og_title or h1_title)

        # Date. The URL slug date is most authoritative when present — Newsroom
        # (/YYYY/MM/DD/) and The Spinoff (/DD-MM-YYYY/) put the real publish date
        # there, whereas their <time>/page text can be a "latest/updated" stamp
        # (Spinoff's rendered <time> reads as *today*, mis-dating every article).
        # Fall back to <time>, then meta, then a date near the article body.
        date = _date_from_url(url)
        if not date:
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
        content = format_text("\n".join(p for p in paras if len(p) > self.min_para and p != headline))
        if not content:
            return None
        return {"headline": headline, "date": date, "author": "", "content": content, "url": url}


class SpinoffSitemapAdapter(GenericAdapter):
    """The Spinoff is a Next.js SPA: its /politics listing is infinite-scroll
    (?page=N just re-serves page 1), so pagination can't reach the archive.
    Instead we read the monthly post sitemaps (/api/sitemap/posts/YYYY-MM.xml),
    which list every article URL — with the publish date in the slug — back to
    2014. Articles are server-rendered, so plain HTTP still parses them.

    Exposes `article_urls()`, which scrape() uses instead of pagination."""

    def __init__(self):
        super().__init__("spinoff", "https://thespinoff.co.nz", "/politics",
                         r"/politics/\d{2}-\d{2}-20\d{2}/[^/?#]+/?$")

    def article_urls(self, since_date, until_date, fetch):
        urls, seen, dropped = [], set(), []
        y, m = since_date.year, since_date.month
        while (y, m) <= (until_date.year, until_date.month):
            sm = f"{self.base}/api/sitemap/posts/{y:04d}-{m:02d}.xml"
            xml = None
            for attempt in range(3):  # the sitemap API throttles bursts -> retry
                xml = fetch(sm)
                if xml:
                    break
                time.sleep(2 * (attempt + 1))
            if xml:
                for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
                    d = _date_from_url(loc)
                    if self.link_re.search(loc) and loc not in seen and \
                            (not d or parse_date_loose(d) >= since_date):
                        seen.add(loc)
                        urls.append(loc)
            else:
                dropped.append(f"{y:04d}-{m:02d}")
            time.sleep(0.4)  # be gentle between monthly sitemaps
            m += 1
            if m > 12:
                m, y = 1, y + 1
        if dropped:
            print(f"  [spinoff] WARNING: no sitemap after retries for: {', '.join(dropped)}")
        return urls


ADAPTERS = {a.name: a for a in (
    GreensAdapter(),
    NationalAdapter(),
    # ACT — server-rendered (NationBuilder), verified.
    GenericAdapter("act", "https://www.act.org.nz", "/news", r"/news/[^/?#]+$"),
    # TOP — NationBuilder; bespoke (date on listing, slug URLs).
    TOPAdapter(),
    # Te Pāti Māori (maoriparty.org.nz/panui) — NationBuilder, card-style listing.
    NationBuilderAdapter("tpm", "https://www.maoriparty.org.nz", "/panui"),
    # News sources beyond RNZ. Server-rendered; date lives in the article URL.
    # Newsroom: /YYYY/MM/DD/slug, WordPress /page/N pagination.
    GenericAdapter("newsroom", "https://newsroom.co.nz", "/category/politics",
                   r"/20\d{2}/\d{2}/\d{2}/[^/]+/?$",
                   page_fmt="/category/politics/page/{n}/"),
    # The Spinoff: Next.js SPA — archive via monthly post sitemaps, not paging.
    SpinoffSitemapAdapter(),
    # Labour & NZ First — listings are JS-rendered, so browser path.
    GenericAdapter("labour", "https://www.labour.org.nz", "/news", r"/news/[^/?#]+/?$", needs_browser=True, min_para=90),
    # NZ First puts articles at root-level long slugs (/news-…, /video-…, /nz_first_…),
    # not under a /news/ path, so match any long root slug (excludes short nav links).
    GenericAdapter("nzfirst", "https://www.nzfirst.nz", "/news",
                   r"nzfirst\.nz/[a-z0-9][a-z0-9_-]{20,}/?$", needs_browser=True, min_para=90),
    # RNZ — now JS-rendered; Parliament — Radware-walled. Both browser path.
    GenericAdapter("rnz", "https://www.rnz.co.nz", "/news/political", r"/news/political/\d+/", needs_browser=True),
    GenericAdapter("parliament", "https://www.parliament.nz",
                   "/en/get-involved/information-for-the-press/media-releases/",
                   r"/en/get-involved/.*media-release", needs_browser=True),
)}


def scrape(source, months=3, out=None, max=None, ref_date=None, delay=1.0,
           browser=False, max_pages=200, since=None, max_empty_pages=2):
    """Paginate `source` newest-first, keeping articles within `months` (or up to
    `max`), writing the standard schema to `out`.

    `since` (ISO 'YYYY-MM-DD') gives an explicit lower bound and takes precedence
    over `months` — use it for the fixed term window, e.g. --since 2023-10-06.

    `max_empty_pages`: how many consecutive pages with no new links to tolerate
    before stopping. >1 lets us skip a gap page (e.g. National's listing has an
    empty page 4 but real articles on page 5+); a looping site (same links every
    page) still stops after this many duplicates."""
    if source not in ADAPTERS:
        raise SystemExit(f"unknown source '{source}'. Choose: {', '.join(ADAPTERS)}")
    adapter = ADAPTERS[source]
    fetch = _browser_fetch if (browser or adapter.needs_browser) else _http_fetch
    since_date = parse_date_loose(since) if since else None
    results, page, stop = [], adapter.start, False
    # Runaway guard: if a date window is requested but we never see an
    # out-of-window article (e.g. dates aren't parsing), don't crawl the whole
    # archive — cap the haul unless the caller set an explicit --max. A --since
    # backfill can legitimately be large, so its guard is higher.
    runaway_cap = int(max) if max else (5000 if since_date else 1000 if not months else 400)
    n_undated = 0
    seen_urls = set()
    empty_streak = 0

    # Sitemap-driven sources (e.g. The Spinoff) list their article URLs directly,
    # so we fetch those instead of paginating a listing.
    if hasattr(adapter, "article_urls"):
        until = parse_date_loose(ref_date) or datetime.date.today()
        lo = since_date or datetime.date(2000, 1, 1)
        art_urls = adapter.article_urls(lo, until, fetch)
        print(f"[{source}] {len(art_urls)} article URLs from sitemap")
        for url in art_urls:
            if len(results) >= runaway_cap:
                break
            ahtml = fetch(url)
            rec = adapter.parse_article(ahtml, url) if ahtml else None
            if not rec:
                continue
            results.append(rec)
            print(f"  + {rec['date'] or '?':12} {rec['headline'][:55]}")
            time.sleep(delay)
        print(f"[{source}] collected {len(results)} articles")
        if out:
            save_to_json(results, out)
        return results

    while page < adapter.start + max_pages and not stop:
        lhtml = fetch(adapter.listing_url(page))
        urls = [u for u in (adapter.parse_listing(lhtml) if lhtml else []) if u not in seen_urls]
        if not urls:
            # No new links: the page is exhausted, a gap, or a site that returns
            # the same links for every ?page=N (e.g. ACT). Tolerate a few such
            # pages so we can step over a gap, but stop if it persists.
            empty_streak += 1
            print(f"[{source}] page {page}: no new links "
                  f"(empty {empty_streak}/{max_empty_pages})")
            if empty_streak >= max_empty_pages:
                print(f"[{source}] stopping after {empty_streak} empty page(s)")
                break
            page += 1
            continue
        empty_streak = 0
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
            out_of_window = (d < since_date) if (since_date and d) else \
                (months and d and not is_recent(rec["date"], months, ref_date))
            if out_of_window:
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


def _cli(source, months=3, out=None, max=None, ref_date=None, delay=1.0,
         browser=False, max_pages=200, since=None, max_empty_pages=2):
    """CLI entry. Wraps scrape() and returns None so python-fire doesn't dump the
    whole article list to stdout (scrape already prints concise progress)."""
    scrape(source, months=months, out=out, max=max, ref_date=ref_date, delay=delay,
           browser=browser, max_pages=max_pages, since=since, max_empty_pages=max_empty_pages)


if __name__ == "__main__":
    fire.Fire({"scrape": _cli})
