# Live data fetching — status & recipe

We are building toward a few months of real articles for a small set of test
politicians, from the key party sites, RNZ, and Hansard. This documents what
works today and how the `live_*.json` datasets were produced.

## Source status

| Source | Method | Status |
|---|---|---|
| Green Party (`greens.org.nz/media`) | server-rendered HTML | ✅ `sources.py --source greens` (verified) |
| National (`national.org.nz/news`) | server-rendered HTML | ✅ `sources.py --source national` (verified) |
| ACT (`act.org.nz/news`) | server-rendered (NationBuilder/Framer) | ✅ `sources.py --source act` (verified) |
| Beehive (`beehive.govt.nz`) | server-rendered | ✅ (batch in `beehive_media_releases.json`) |
| Labour (`labour.org.nz/news`) | **JS-rendered listing** | 🌐 `sources.py --source labour` (browser path) |
| NZ First (`nzfirst.nz/news`) | **JS-rendered** | 🌐 `sources.py --source nzfirst` (browser path) |
| RNZ political (`rnz.co.nz/news/political`) | **now JS-rendered** (0 `<p>` in static HTML) | 🌐 `sources.py --source rnz` (browser path) |
| **Hansard** (`hansard.parliament.nz`) | SPA **+ Radware anti-bot wall** | 🌐 `hansard.py recent` — see below |
| **Parliament press** (`parliament.nz/.../media-releases`) | **Radware anti-bot wall** | 🌐 `sources.py --source parliament` (browser) |
| TOP (`opportunity.org.nz/news`) | server-rendered (NationBuilder) | ✅ `sources.py --source top` (verified) |
| Te Pāti Māori | host unreachable from here | ⬜ not adapted |

## `sources.py` — paginating, date-windowed scrapers

One driver paginates a source newest-first and stops at a date cutoff, so you can
pull arbitrary history:

```
cd data/scrapers
python sources.py scrape --source greens   --months 6  --out ../data/greens_6mo.json
python sources.py scrape --source national --months 12 --out ../data/national_1yr.json
python sources.py scrape --source greens   --max 20      --out sample.json
```

- **greens, national, act, top** — plain `requests`/BeautifulSoup, **verified live**
  (correct headline/date/content; pagination + the `--months` window both work;
  dates normalised to ISO; UTF-8 detected for sites that don't declare a charset).
  Parsing is unit-tested in `test_sources.py`. TOP (NationBuilder) keeps the
  publish date from the listing — its article pages don't carry one.
- **labour, nzfirst, rnz, parliament** — routed through the Playwright browser
  path (JS-rendered listings / Radware wall). Needs
  `pip install playwright && playwright install chromium` and a browser-capable
  machine (see `HANSARD_HOWTO.md`). The generic adapter (og:title/`<h1>` +
  substantial `<p>`s) is best-effort and may need a per-site tweak.

Output is the standard `{headline, date, author, content, url}` schema; feed the
files straight into `attribute-extraction/build_site_data.py`.

The earlier per-site `scrapers/greens.py` / `national.py` / `rnz.py` are superseded
by `sources.py`.

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
