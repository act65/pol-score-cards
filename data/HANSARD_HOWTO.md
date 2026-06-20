# How to run the Hansard scraper (on a browser-capable machine)

Hansard (`hansard.parliament.nz`) is behind a **Radware "verifying your browser"
anti-bot wall** plus a JavaScript single-page app, so a plain HTTP fetch only gets
the challenge page (see `LIVE_FETCH.md`). The scraper (`scrapers/hansard.py`)
handles this by driving a **real browser** via Playwright — but Playwright needs a
machine where it can launch Chromium (your laptop/desktop, not a locked-down
sandbox). This is the one piece that has to run on your side.

## 1. Install (one-time)

```bash
pip install playwright beautifulsoup4 fire
playwright install chromium
```

## TL;DR — the one-liner

After the install in step 1, this pulls recent Hansard transcripts in one go
(renders the listing, finds recent transcript links, fetches each; auto-falls
back from a headless to a visible browser if Radware blocks headless):

```bash
cd data/scrapers
python hansard.py recent ../data/mvp_hansard.json --months 1
```

If it says the listing was challenged, add `--headless=False` (needs a desktop
with a display) and/or `--debug` (dumps the fetched HTML so you can see what came
back). The same auto-fallback applies to a single URL:

```bash
python hansard.py fetch "<transcript-url>" ../data/mvp_hansard.json
```

For RNZ / Parliament press (also browser-path), the equivalent is:

```bash
python sources.py scrape --source rnz        --months 1 --out ../data/rnz_browser.json
python sources.py scrape --source parliament --months 1 --out ../data/parliament.json
```

The rest of this doc explains the pieces.

## 2. Find transcript URLs (manual, if `recent` doesn't find them)

Open <https://hansard.parliament.nz/hansard-debates> and pick recent debates —
**"Questions to Ministers" (Oral Questions)** are the gold for us (verbatim Q&A →
Forthrightness, Civility, Veracity). Copy each transcript URL. They look like:

```
https://hansard.parliament.nz/hansard-transcript/2026-06-18/oral-question-2-prime-minister
https://hansard.parliament.nz/hansard-transcript/2026-06-18/general-debate
```

## 3. Fetch them into the dataset

Run from `data/scrapers/`. Save into `../data/mvp_hansard.json` so the
existing pipeline glob (`mvp_*.json`) picks it up. Each call **appends** one
transcript:

```bash
cd data/scrapers
python hansard.py fetch "https://hansard.parliament.nz/hansard-transcript/2026-06-18/oral-question-2-prime-minister" ../data/mvp_hansard.json
python hansard.py fetch "<next url>" ../data/mvp_hansard.json
# ... a handful of recent Question Time transcripts is plenty for the MVP
```

**If you hit `Page.goto: Timeout … waiting until "networkidle"`** — that was a bug
(the Radware challenge + SPA keep polling, so the network never goes idle). It's
**fixed**: `fetch_via_playwright` now navigates on `domcontentloaded` and polls
until the challenge clears (up to ~75s). Just re-run with the updated code.

**If you saw "page had no transcript (challenge/shell)" even in a visible browser**
— that was a parser bug, now fixed. Hansard's Blazor app always embeds a hidden
`"An unhandled error has occurred. Reload"` modal, and the parser was wrongly
treating that text as an unrendered shell and rejecting every page. It now only
rejects on the actual Radware markers. **Re-run with the updated code** — fetched
transcripts should parse. (`recent` also now reloads once past the Radware cookie
and waits for real speech content before giving up.)

**If it's still blocked by Radware**, retry with a visible window — it passes the
challenge far more reliably:

```bash
python hansard.py fetch "<url>" ../data/mvp_hansard.json --headless=False
```

(You can sanity-check parsing offline without fetching:
`python hansard.py parse_file some_saved_page.html "<url>"`.)

## 4. Feed it into the attribute pipeline

Once `mvp_hansard.json` exists, re-run the extractor — it will include Hansard
alongside the party sites + RNZ:

```bash
cd ../../attribute-extraction
export ANTHROPIC_API_KEY=...
python build_site_data.py build --articles "../data/data/mvp_*.json"
```

That regenerates `site/static/{scores,examples,politicians}.jsonl` with the
Hansard Q&A folded in (and the game deck via `cd ../game && python normalise.py build`).

## Notes
- Be polite: a few transcripts at a time, with a pause between fetches.
- The parser (`parse_hansard_html`) is unit-tested (`test_hansard.py`) so once a
  page is fetched, turning it into the standard `{headline,date,author,content,url}`
  schema is reliable.
- If Playwright is a hassle, the community scrapers
  `github.com/nathanielw/hansard-scraper` and `github.com/mjdall/parliament-scraper`
  solve the same fetch problem; their output can be massaged into the same schema.
