"""Backfill a party's full-term press-release archive via the Wayback CDX index.

The party sites (Labour, NZ First) are SPA infinite-scroll with no pagination or
sitemap, so a live scrape only reaches recent releases. But every release URL was
archived by the Wayback Machine, and its CDX API lists them all. We:
  1. query CDX for every archived URL under the source's domain,
  2. keep those matching the source adapter's article regex, first-archived in the
     term window (a sound lower bound: archive time >= publish time),
  3. fetch each from the LIVE site (still server-rendered, cleanest), falling back
     to the Wayback snapshot if the live page is gone,
  4. parse with the existing adapter, keep those whose real publish date is in
     window, and merge into the corpus file (dedup by URL).

    python wayback_backfill.py run --source labour  --since 2023-10-14
    python wayback_backfill.py run --source nzfirst --since 2023-10-14

Resumable: URLs already in the output are skipped, and it saves after each fetch.
"""

import json
import os
import time
import urllib.parse
import urllib.request

import fire

import sources

HERE = os.path.dirname(os.path.abspath(__file__))
CDX = "https://web.archive.org/cdx/search/cdx"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# What to ask CDX for; the adapter's link_re does the precise filtering.
CDX_PATTERN = {
    "labour": "labour.org.nz/news/*",
    "nzfirst": "nzfirst.nz/*",
    "act": "act.org.nz/news/*",
}

# Optional per-source article-URL regex that's tighter than the adapter's link_re,
# to exclude old-format URLs the domain reused over the years. Labour's current
# releases are all /news/release-<slug>; pre-2023 posts used other prefixes.
import re as _re
ARTICLE_RE = {
    "labour": _re.compile(r"labour\.org\.nz/news/release-[^/?#]+/?$"),
}


def _get(url, timeout=45, retries=4):
    """GET with backoff on web.archive.org's flaky 503/429 responses."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(6 * (attempt + 1))
                continue
            raise


def cdx_candidates(source, since, cdx_json=None):
    """Unique {url: earliest_timestamp} matching the adapter's article regex and
    first-archived on/after `since` (YYYYMMDD). Reads a cached CDX json file when
    given (avoids re-hitting the rate-limited CDX API)."""
    adapter = sources.ADAPTERS[source]
    art_re = ARTICLE_RE.get(source, adapter.link_re)
    since_ts = since.replace("-", "")
    if cdx_json and os.path.exists(cdx_json):
        data = json.load(open(cdx_json))
    else:
        q = urllib.parse.urlencode({"url": CDX_PATTERN[source], "collapse": "urlkey",
                                    "fl": "original,timestamp", "output": "json"})
        data = json.loads(_get(f"{CDX}?{q}", timeout=180))
    rows = data[1:] if data and data[0] == ["original", "timestamp"] else data
    cands = {}
    for orig, ts in rows:
        u = orig.split("#")[0].split("?")[0]
        u = u.replace("http://", "https://").replace(":80", "").rstrip("/")
        if not art_re.search(u):
            continue
        if ts[:8] < since_ts:                       # archive time >= publish time
            continue
        if u not in cands or ts < cands[u]:
            cands[u] = ts
    return cands


def _fetch_parse(adapter, url, ts):
    """Live HTTP → live browser → Wayback snapshot, first that yields a body."""
    for html in (sources._http_fetch(url),):
        if html:
            rec = adapter.parse_article(html, url)
            if rec and rec.get("content"):
                return rec
    if adapter.needs_browser:
        html = sources._browser_fetch(url)
        if html:
            rec = adapter.parse_article(html, url)
            if rec and rec.get("content"):
                return rec
    try:                                             # Wayback raw snapshot (id_ = no toolbar)
        html = _get(f"https://web.archive.org/web/{ts}id_/{url}").decode("utf-8", "ignore")
        rec = adapter.parse_article(html, url)
        if rec and rec.get("content"):
            rec["url"] = url
            return rec
    except Exception:
        pass
    return None


def run(source, since="2023-10-14", out=None, delay=0.4, limit=0, cdx_json=""):
    adapter = sources.ADAPTERS[source]
    out = out or os.path.join(HERE, "..", "corpus", f"{source}.json")
    out = out if os.path.isabs(out) else os.path.join(HERE, out)

    records = json.load(open(out)) if os.path.exists(out) else []
    done = {r["url"].rstrip("/") for r in records}
    print(f"[{source}] existing: {len(records)} records", flush=True)

    cands = cdx_candidates(source, since, cdx_json=cdx_json or None)
    todo = [(u, ts) for u, ts in sorted(cands.items()) if u.rstrip("/") not in done]
    if limit:
        todo = todo[:limit]
    print(f"[{source}] CDX candidates in window: {len(cands)}; new to fetch: {len(todo)}", flush=True)

    added = kept_out = failed = 0
    for i, (url, ts) in enumerate(todo, 1):
        rec = _fetch_parse(adapter, url, ts)
        if not rec:
            failed += 1
            print(f"[{i}/{len(todo)}] FAIL {url[-55:]}", flush=True)
        elif rec.get("date") and rec["date"] < since:
            kept_out += 1                            # real publish date pre-term → drop
        else:
            records.append(rec)
            added += 1
            json.dump(records, open(out, "w"), ensure_ascii=False, indent=1)
            if added % 20 == 0:
                print(f"[{i}/{len(todo)}] +{added} (last {rec.get('date')})", flush=True)
        time.sleep(delay)

    print(f"[{source}] done: +{added} added ({len(records)} total), "
          f"{kept_out} pre-term dropped, {failed} failed -> {out}", flush=True)


if __name__ == "__main__":
    fire.Fire({"run": run})
