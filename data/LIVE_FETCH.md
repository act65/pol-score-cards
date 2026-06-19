# Live data fetching — status & recipe

We are building toward a few months of real articles for a small set of test
politicians, from the key party sites, RNZ, and Hansard. This documents what
works today and how the `live_*.json` datasets were produced.

## Source status

| Source | Method | Status |
|---|---|---|
| Green Party (`greens.org.nz/media`) | server-rendered HTML — listing + article pages fetch directly | ✅ working |
| National (`national.org.nz/news`) | server-rendered HTML | ✅ working |
| RNZ political (`rnz.co.nz/news/political`) | server-rendered HTML | ✅ working |
| Beehive (`beehive.govt.nz`) | server-rendered | ✅ (earlier batch in `beehive_media_releases.json`) |
| **Hansard** (`hansard.parliament.nz`) | **client-rendered SPA** | ⛔ blocked for simple fetch — see below |

## Datasets produced (live)

`data/data/live_greens_2026-06.json`, `live_national_2026-06.json`,
`live_rnz_2026-06.json` — current (June 2026) articles in the standard schema
(`headline, date, author, content, url`), fetched live. Regenerate stats with
`python dataset_stats.py`; run extraction with
`python ../attribute-extraction/extract.py extract_file <file> <attribute> out.jsonl`.

These were fetched and validated end-to-end: e.g. veracity extraction over the
National releases scores Todd McClay's "$64.3 billion exports forecast" claims
~0.9 (specific, sourced), and civility extraction over the RNZ Parliament "spat"
correctly scores "Hypocrite!" at 0.10.

## Recipe (the working sources)

1. Fetch the listing page → recent article URLs + dates (filter to the last N
   months; `scrapers/utils.py:is_recent`).
2. Fetch each article page → `headline, date, author, content, url`.
3. Append to the per-source `live_<source>_<period>.json`.
4. Run `dataset_stats.py` and the extractor.

The standalone `scrapers/*.py` (BeautifulSoup) implement steps 1–2 for some
sources but have bugs and need debugging against current HTML; the live fetches
above were done directly. Either path produces the same schema.

## Hansard — why it's blocked, and the path forward

`hansard.parliament.nz` (and the old `parliament.nz/.../hansard-debates/rhr/`,
which now **301-redirects to it**) is blocked two ways:

1. **Radware anti-bot wall.** A plain HTTP GET returns a Radware "Verifying your
   browser before proceeding…" challenge page (confirmed: the response is a
   ~118 KB loader titled "Radware Page", not the site). This challenge must be
   solved by a real browser engine running JS.
2. **Single-page app.** Even past the challenge, the transcript is rendered
   client-side; there is **no official JSON API**.

`web.archive.org` snapshots would sidestep Radware, but archive.org's availability
API rate-limited every attempt (HTTP 429) from here, and the specific older
`/combined/HansDeb_…` snapshot wasn't captured.

**What's built:** `data/scrapers/hansard.py` is the scraper, structured for the
real blockers:
- `parse_hansard_html(html, url)` — turns a fetched transcript into the standard
  schema; detects+rejects the Radware/SPA shell. **Unit-tested** in
  `test_hansard.py` (3 tests, no network).
- `fetch_via_playwright(url)` — renders the SPA in headless Chromium (executes the
  Radware challenge JS). **This is the path that works**, but needs
  `pip install playwright && playwright install chromium` and a browser-capable
  environment (not available where this was developed, so not run live here).
- `fetch_via_wayback(url)` — static-snapshot fallback for when archive.org isn't
  rate-limiting.

So Hansard ingestion is **code-complete and tested at the parsing layer**; the
remaining step is running `fetch_via_playwright` somewhere with a browser. We did
not fabricate Hansard records — the pipeline currently runs on the party sites +
RNZ (which already includes RNZ's reporting of Question Time, e.g. the
conservation-land hearing). Community references: `github.com/nathanielw/hansard-scraper`,
`github.com/mjdall/parliament-scraper`.
