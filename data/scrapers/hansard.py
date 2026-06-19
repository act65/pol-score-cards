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
    if "verifying your browser" in low or "radware" in low or "an unhandled error" in low:
        return None

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".body-text--hansard, [class*='hansard'], main") or soup

    title_el = root.find(["h1", "h2"]) or soup.find(["h1", "h2"])
    headline = title_el.get_text(strip=True) if title_el else "Hansard debate"

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


def fetch_via_playwright(url: str, timeout_ms: int = 45000, headless: bool = True) -> str:
    """Render the Hansard SPA in a real browser engine and return the HTML.

    Requires: pip install playwright && playwright install chromium
    A real engine executes the Radware challenge JS and the SPA, so the returned
    HTML contains the transcript. If the Radware challenge still blocks a headless
    run, retry with headless=False (a visible window passes the check far more
    reliably).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from e
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_context(user_agent=UA).new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        page.wait_for_timeout(5000)  # let the Radware challenge + SPA settle
        html = page.content()
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


def fetch(url: str, save_to: str, prefer: str = "playwright", headless: bool = True):
    """Fetch one Hansard transcript URL and append it (standard schema) to save_to.

    If a headless Playwright run is blocked by the Radware challenge, retry with
    --headless=False (a visible browser window).
    """
    order = ["playwright", "wayback"] if prefer == "playwright" else ["wayback", "playwright"]
    html = None
    for method in order:
        try:
            if method == "playwright":
                html = fetch_via_playwright(url, headless=headless)
            else:
                html = fetch_via_wayback(url)
            if html:
                print(f"fetched via {method}")
                break
        except Exception as e:  # noqa: BLE001
            print(f"{method} failed: {e}")
    if not html:
        print("Could not fetch (Radware wall / no snapshot). See data/LIVE_FETCH.md.")
        return
    record = parse_hansard_html(html, url)
    if not record:
        print("Fetched page had no transcript (challenge/shell).")
        return
    with open(save_to, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"appended '{record['headline']}' -> {save_to}")


if __name__ == "__main__":
    import fire
    fire.Fire({
        "fetch": fetch,
        "parse_file": lambda path, url="": print(
            json.dumps(parse_hansard_html(open(path).read(), url), ensure_ascii=False, indent=2)),
    })
