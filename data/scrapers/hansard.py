"""Hansard (NZ Parliament debate transcript) scraper.

Hansard is the highest-value source for the project — verbatim Question Time
gives clean signal for Forthrightness (did they answer?), Civility, Veracity, and
Rigor. But `hansard.parliament.nz` is hard to fetch:

  * it's a single-page app (the transcript is rendered client-side), and
  * it sits behind a Radware "verifying your browser" anti-bot challenge, so a
    plain HTTP GET returns the challenge page, not the transcript.

(The previous version of this file targeted the old server-rendered
`.body-text--hansard` pages, which now 301-redirect to the SPA — which is why
`hansard_reports.json` came out empty.)

This module provides:
  * `parse_hansard_html(html, url)` — turn a fetched Hansard transcript page into
    the project's standard article record. Pure + unit-tested (test_hansard.py).
  * `fetch_via_playwright(url)` — render the SPA in a real browser engine (passes
    the JS challenge); requires `pip install playwright && playwright install`.
  * `fetch_via_wayback(url)` — fetch a static archived snapshot (avoids Radware),
    when archive.org isn't rate-limiting.
  * a CLI that tries the available fetchers and writes the standard schema.

See data/LIVE_FETCH.md for the current status and why live fetch needs a
browser-capable environment.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DATE_RE = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
                     r"September|October|November|December)\s+(\d{4})", re.I)
_URL_TITLE = re.compile(r"/hansard-transcript/(\d{4}-\d{2}-\d{2})/([^/?#]+)")


def _title_from_url(url: str) -> str:
    """'/hansard-transcript/2026-06-18/oral-question-2-prime-minister' ->
    'Oral Question 2 Prime Minister (2026-06-18)'."""
    m = _URL_TITLE.search(url or "")
    if not m:
        return ""
    return f"{m.group(2).replace('-', ' ').title()} ({m.group(1)})"


def parse_hansard_html(html: str, url: str = "") -> dict | None:
    """Parse a Hansard transcript page into the standard article record
    {headline, date, author, content, url, source}.

    Handles the structured form (speech blocks with a named speaker) and falls
    back to plain paragraph text. Returns None if the page is a bot-challenge or
    an unrendered SPA shell with no transcript.
    """
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required: pip install beautifulsoup4")

    low = html.lower()
    # Only the Radware challenge markers mean "not the real page". Do NOT treat
    # "an unhandled error has occurred" as a shell — Blazor (which Hansard uses)
    # always embeds that text in a hidden reconnect modal, even on fully-rendered
    # pages. A genuinely empty shell still returns None via the content check below.
    if "verifying your browser" in low or "radware" in low:
        return None

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".body-text--hansard, [class*='hansard'], main") or soup

    # Hansard's page heading is often a generic nav label ("Transcript Sections"),
    # so derive a real title from the transcript URL when the heading is generic.
    title_el = root.find(["h1", "h2"]) or soup.find(["h1", "h2"])
    headline = title_el.get_text(strip=True) if title_el else ""
    url_title = _title_from_url(url)
    if headline.strip().lower() in ("transcript sections", "hansard debate", "hansard", "") and url_title:
        headline = url_title
    elif not headline:
        headline = url_title or "Hansard debate"

    date = ""
    m = DATE_RE.search(soup.get_text(" ", strip=True))
    if m:
        date = f"{m.group(1)} {m.group(2)} {m.group(3)}"

    # Structured speeches: a speaker element followed by the speech text.
    turns = []
    speeches = root.select(".Speech, .speech, .Debate, .hansard-speech")
    if speeches:
        for sp in speeches:
            spk = sp.select_one(".Speaker, .speaker, strong, .member")
            speaker = spk.get_text(strip=True) if spk else ""
            body = sp.get_text(" ", strip=True)
            if speaker and body.startswith(speaker):
                body = body[len(speaker):].lstrip(" :—-")
            turn = f"{speaker}: {body}".strip(": ").strip()
            if turn:
                turns.append(turn)
    else:
        turns = [p.get_text(" ", strip=True) for p in root.find_all("p")]

    content = "\n".join(t for t in turns if t)
    if not content.strip():
        return None

    author = turns[0].split(":", 1)[0].strip() if (speeches and turns) else "Hansard"
    return {
        "headline": headline,
        "date": date,
        "author": author or "Hansard",
        "content": content,
        "url": url,
        "source": "hansard",
    }


def _chunks(text, size):
    """Split text into <=size pieces on paragraph boundaries where possible."""
    out, buf = [], ""
    for para in text.split("\n"):
        if buf and len(buf) + len(para) + 1 > size:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n{para}" if buf else para
        while len(buf) > size:  # a single huge paragraph
            out.append(buf[:size])
            buf = buf[size:]
    if buf.strip():
        out.append(buf)
    return out


def parse_hansard_day(html: str, url: str = "", max_chars: int = 30000,
                      max_sections: int = 8, min_day_chars: int = 3000) -> list:
    """Split a full Hansard *day* page (one big combined transcript) into tractable
    records.

    The day page has no `.Speech` classes — it's headings + paragraphs, and the
    section headings aren't reliably h2/h3, so heading-splitting under-splits. We
    therefore split by heading where we can AND chunk any long section to
    `max_chars`, capping at `max_sections` records per day. Non-sitting / "no
    planned meetings" placeholder days (tiny content) return []. """
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required: pip install beautifulsoup4")
    low = html.lower()
    if "verifying your browser" in low or "radware" in low:
        return []

    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", url) or DATE_RE.search(soup.get_text(" ", strip=True))
    date = m.group(1) if m else ""

    sections, head, paras = [], "", []

    def flush():
        body = "\n".join(paras)
        # Keep a titled section with real content, or any large block. This drops
        # the leading head-less nav/header fragment (page chrome before the first
        # heading), which is small and untitled.
        if (head and len(body) > 200) or len(body) > 2000:
            sections.append((head, body))

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
        if el.name != "p":
            flush()
            head, paras = el.get_text(" ", strip=True), []
        else:
            t = el.get_text(" ", strip=True)
            if len(t) > 40:           # substantial -> transcript, not nav chrome
                paras.append(t)
    flush()

    # Non-sitting / placeholder day (e.g. "There are no planned meetings"): skip.
    if sum(len(b) for _, b in sections) < min_day_chars:
        return []

    records = []
    for head, body in sections:
        title = head.strip() if head and 3 < len(head) < 160 else ""
        pieces = _chunks(body, max_chars)
        for i, piece in enumerate(pieces):
            base = title or (_title_from_url(url) or f"Hansard debate {date}")
            suffix = f" — part {i + 1}" if len(pieces) > 1 else ""
            headline = f"{base}{suffix}" if title else f"{base}{suffix}"
            if title and "(" not in base:
                headline = f"{title}{suffix} ({date})"
            records.append({"headline": headline, "date": date, "author": "Hansard",
                            "content": piece, "url": url, "source": "hansard"})
            if len(records) >= max_sections:
                return records
    return records


def fetch_via_playwright(url: str, timeout_ms: int = 90000, headless: bool = True,
                         settle_s: int = 75, wait_for: str = None) -> str:
    """Render the Hansard SPA in a real browser engine and return the HTML.

    Requires: pip install playwright && playwright install chromium

    NOTE: do NOT wait for "networkidle" — the Radware challenge and the SPA keep
    polling, so the network never goes idle and goto() times out (the common
    failure). Instead we navigate on "domcontentloaded" and then *poll* the page
    until the Radware challenge has cleared and the transcript has rendered.

    If a headless run is still blocked by the challenge, retry with headless=False
    (a visible window passes the check far more reliably).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from e
    import time

    # Anti-automation flags + an init script that hides the obvious headless
    # tells (navigator.webdriver etc.). Radware's challenge often passes headless
    # with these; if it still doesn't, use headless=False (a visible window).
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    stealth = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-NZ', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        window.chrome = {runtime: {}};
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=launch_args)
        context = browser.new_context(
            user_agent=UA, viewport={"width": 1366, "height": 900},
            locale="en-NZ", timezone_id="Pacific/Auckland")
        context.add_init_script(stealth)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass  # even domcontentloaded can race the challenge redirect; poll below

        html = ""
        deadline = time.time() + settle_s
        reloaded = False
        while time.time() < deadline:
            page.wait_for_timeout(2500)
            html = page.content()
            low = html.lower()
            if "verifying your browser" in low or "radware" in low:
                # Radware sometimes sets a cookie then expects a reload before
                # serving the real page — do that once, partway through.
                if not reloaded and time.time() > deadline - settle_s * 0.6:
                    reloaded = True
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
                    except Exception:
                        pass
                continue
            # Break once the page we want has actually rendered. For a listing we
            # wait for transcript links (`wait_for`); for a transcript page we wait
            # for real speech content (not just the nav, which always says "Hansard").
            if wait_for is not None:
                if wait_for.lower() in low:
                    break
                continue
            soup = BeautifulSoup(html, "html.parser")
            if soup.select(".Speech, .speech, .Debate, .hansard-speech") or \
               sum(1 for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40) >= 3:
                break
        browser.close()
        return html


def fetch_via_wayback(url: str) -> str | None:
    """Fetch the closest archived snapshot's raw HTML (bypasses Radware).

    Returns None if no snapshot exists. archive.org rate-limits aggressively;
    retry later on HTTP 429.
    """
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    with urllib.request.urlopen(urllib.request.Request(api, headers={"User-Agent": UA}), timeout=30) as r:
        info = json.load(r)
    snap = info.get("archived_snapshots", {}).get("closest", {})
    if not snap.get("available"):
        return None
    raw = snap["url"].replace("/http", "id_/http", 1)  # id_ -> raw archived bytes
    with urllib.request.urlopen(urllib.request.Request(raw, headers={"User-Agent": UA}), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def fetch(url: str, save_to: str, headless: bool = True, debug: bool = False):
    """Fetch one Hansard transcript URL and append it (standard schema) to save_to.

    Tries: headless browser -> visible browser (auto-fallback when the headless
    run is blocked by Radware) -> Wayback snapshot. `--headless=False` forces the
    visible browser first; `--debug` dumps the fetched HTML next to save_to so you
    can see what the challenge returned.
    """
    def _save_debug(html, tag):
        if debug and html:
            path = f"{save_to}.{tag}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  [debug] wrote {len(html)} bytes -> {path}")

    attempts = []
    if headless:
        attempts.append(("browser (headless)", lambda: fetch_via_playwright(url, headless=True)))
    attempts.append(("browser (visible)", lambda: fetch_via_playwright(url, headless=False)))
    attempts.append(("wayback", lambda: fetch_via_wayback(url)))

    for name, run in attempts:
        try:
            html = run()
        except Exception as e:  # noqa: BLE001
            print(f"{name} failed: {e}")
            continue
        _save_debug(html, name.split()[0] + ("_visible" if "visible" in name else ""))
        record = parse_hansard_html(html, url) if html else None
        if record:
            _append_record(record, save_to)
            print(f"fetched via {name}; appended '{record['headline']}' -> {save_to}")
            return True
        print(f"{name}: no transcript (challenge/shell) — trying next…")

    print("Could not fetch Hansard (Radware wall / no snapshot). "
          "Try --headless=False on a machine with a display, or --debug to inspect. "
          "See data/HANSARD_HOWTO.md.")
    return False


def _append_record(record, save_to):
    parent = os.path.dirname(os.path.abspath(save_to))
    os.makedirs(parent, exist_ok=True)  # don't crash on a missing dir
    with open(save_to, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _render(url, headless=True, wait_for=None, settle_s=75):
    """Render a Hansard page, auto-falling back from headless to a visible browser
    if the Radware challenge doesn't clear headless. `wait_for` is a substring the
    page must contain to count as ready (e.g. a transcript-link path). Returns the
    cleared HTML."""
    html = ""
    for hl in ([True, False] if headless else [False]):
        html = fetch_via_playwright(url, headless=hl, wait_for=wait_for, settle_s=settle_s)
        low = (html or "").lower()
        challenged = "verifying your browser" in low or "radware" in low
        ready = (wait_for.lower() in low) if wait_for else True
        if html and not challenged and ready:
            return html
    return html


_TX_DATE = re.compile(r"/hansard-transcript/(\d{4}-\d{2}-\d{2})/")


def _transcript_links(html):
    """All unique /hansard-transcript/<date>/<section> links in a rendered page."""
    soup = BeautifulSoup(html or "", "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/hansard-transcript/\d{4}-\d{2}-\d{2}/")):
        href = a["href"]
        full = (href if href.startswith("http") else "https://hansard.parliament.nz" + href).split("#")[0]
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


_DAY_LINK = re.compile(r"/hansard-(?:debates|transcript)/.*\d{4}-\d{2}-\d{2}")


def _day_links(html):
    """Hansard links that mention a date but aren't a full transcript section —
    i.e. day / document pages whose sections we still need to harvest."""
    soup = BeautifulSoup(html or "", "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = (href if href.startswith("http") else "https://hansard.parliament.nz" + href).split("#")[0]
        if "hansard" in full and re.search(r"\d{4}-\d{2}-\d{2}", full) \
                and not re.search(r"/hansard-transcript/\d{4}-\d{2}-\d{2}/[^/?#]+", full) \
                and full not in seen:
            seen.add(full)
            out.append(full)
    return out


def _enumerate_day_urls(months, ref_date=None):
    """Generate Hansard day-page URLs (/hansard-transcript/<date>) for every
    weekday from `ref_date` (today) back `months` months. Parliament sits on
    weekdays; non-sitting days simply render no sections and are skipped."""
    import datetime
    ref = ref_date or datetime.date.today()
    cutoff = ref - datetime.timedelta(days=30 * months)
    urls, d = [], ref
    while d >= cutoff:
        if d.weekday() < 5:  # Mon–Fri
            urls.append(f"https://hansard.parliament.nz/hansard-transcript/{d.isoformat()}")
        d -= datetime.timedelta(days=1)
    return urls


def recent(save_to, months=1, max_n=40, headless=True, debug=False,
           enumerate_days=True, ref_date=None,
           listing="https://hansard.parliament.nz/hansard-debates"):
    """One-shot Hansard pull, newest-first, within `--months` (up to `--max_n`):

        python hansard.py recent ../data/mvp_hansard.json --months 1

    Hansard's listing only exposes the most recent day, and the Browse-By-Day day
    list renders without links — so by default we **enumerate** sitting-day pages
    (/hansard-transcript/<date>) across the window and harvest each day's sections.
    Pass --enumerate_days=False to instead scrape only what the landing page links.
    """
    from utils import is_recent

    def in_window(u):
        m = _TX_DATE.search(u) or re.search(r"(\d{4}-\d{2}-\d{2})", u)
        return not (m and months and not is_recent(m.group(1), months))

    if enumerate_days:
        sections, days = [], _enumerate_day_urls(months, ref_date)
        print(f"[hansard] enumerating {len(days)} weekday(s) over {months} month(s)")
    else:
        html = _render(listing, headless=headless, wait_for="/hansard-transcript/")
        if debug:
            with open(f"{save_to}.listing.html", "w", encoding="utf-8") as f:
                f.write(html or "")
            print(f"  [debug] listing -> {save_to}.listing.html ({len(html or '')} bytes)")
        sections = [u for u in _transcript_links(html) if in_window(u)]
        days = [u for u in _day_links(html) if in_window(u)]
        print(f"[hansard] listing: {len(sections)} section link(s), {len(days)} day page(s)")
    seen, fetched = set(), 0

    # 1) Any section links found directly on the listing — fetch each.
    for u in sections:
        if fetched >= max_n:
            break
        if u in seen:
            continue
        seen.add(u)
        if fetch(u, save_to, headless=headless, debug=debug):
            fetched += 1

    # 2) Each day page: try to harvest its section links; if there are none, the
    #    day URL IS (or redirects to) the day's transcript — parse it directly
    #    (we've already rendered it, so no extra fetch).
    for day in days:
        if fetched >= max_n:
            break
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", day)
        wf = f"/hansard-transcript/{dm.group(1)}/" if dm else "/hansard-transcript/"
        dhtml = _render(day, headless=headless, wait_for=wf, settle_s=35)
        if debug:
            with open(f"{save_to}.day-{dm.group(1) if dm else 'x'}.html", "w", encoding="utf-8") as f:
                f.write(dhtml or "")
        found = [u for u in _transcript_links(dhtml) if u not in seen and in_window(u)]
        if found:
            print(f"[hansard] day {dm.group(1) if dm else day}: {len(found)} section link(s)")
            for u in found:
                if fetched >= max_n:
                    break
                seen.add(u)
                if fetch(u, save_to, headless=headless, debug=debug):
                    fetched += 1
        else:
            # No section links: the day page IS the combined transcript — split it
            # into one record per section (Oral Questions, bills, ...).
            records = parse_hansard_day(dhtml, day) if dhtml else []
            if records:
                kept = 0
                for r in records:
                    if fetched >= max_n:
                        break
                    _append_record(r, save_to)
                    fetched += 1
                    kept += 1
                print(f"[hansard] day {dm.group(1) if dm else day}: {len(records)} section(s), kept {kept}")
            else:
                print(f"[hansard] day {dm.group(1) if dm else day}: nothing (likely no sitting)")

    print(f"[hansard] fetched {fetched} transcript(s) -> {save_to}")
    if fetched == 0:
        print("No transcripts fetched. Re-run with --debug and check the dumped "
              "*.listing.html to see the link structure (it may need a selector tweak).")


def links(listing="https://hansard.parliament.nz/hansard-debates", headless=True, n=40):
    """Diagnostic: render a Hansard listing and print the distinct Hansard links it
    contains, so we can see the real day/section link structure. Paste the output:

        python hansard.py links --headless=False
        python hansard.py links "https://hansard.parliament.nz/hansard-debates/rhr?Tab=BrowseByDay&Dir=Desc" --headless=False
    """
    html = _render(listing, headless=headless)  # waits the full settle for the SPA
    soup = BeautifulSoup(html or "", "html.parser")
    hrefs = []
    seen = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "hansard" in h.lower() and h not in seen:
            seen.add(h)
            hrefs.append(h)
    nspeech = len(soup.select(".Speech, .speech, .Debate, .hansard-speech"))
    nparas = sum(1 for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40)
    print(f"rendered {len(html or '')} bytes; {len(hrefs)} distinct hansard links; "
          f"content: {nspeech} speech-elements, {nparas} substantial paragraphs")
    for h in hrefs[:n]:
        print("  ", h)
    if nparas or nspeech:
        body = soup.get_text(" ", strip=True)
        print("  text snippet:", body[:300])
    if not hrefs:
        print("  (no links — the page may still be challenged; try --headless=False)")


if __name__ == "__main__":
    import fire
    fire.Fire({
        "fetch": fetch,
        "recent": recent,
        "links": links,
        "parse_file": lambda path, url="": print(
            json.dumps(parse_hansard_html(open(path).read(), url), ensure_ascii=False, indent=2)),
    })
