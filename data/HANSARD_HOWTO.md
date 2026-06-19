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

## 2. Find transcript URLs

Open <https://hansard.parliament.nz/hansard-debates> and pick recent debates —
**"Questions to Ministers" (Oral Questions)** are the gold for us (verbatim Q&A →
Forthrightness, Civility, Veracity). Copy each transcript URL. They look like:

```
https://hansard.parliament.nz/hansard-transcript/2026-06-18/oral-question-2-prime-minister
https://hansard.parliament.nz/hansard-transcript/2026-06-18/general-debate
```

## 3. Fetch them into the dataset

Run from `data/scrapers/`. Save into `../data/data/mvp_hansard.json` so the
existing pipeline glob (`mvp_*.json`) picks it up. Each call **appends** one
transcript:

```bash
cd data/scrapers
python hansard.py fetch "https://hansard.parliament.nz/hansard-transcript/2026-06-18/oral-question-2-prime-minister" ../data/data/mvp_hansard.json
python hansard.py fetch "<next url>" ../data/data/mvp_hansard.json
# ... a handful of recent Question Time transcripts is plenty for the MVP
```

**If a fetch returns "page had no transcript (challenge/shell)"** the headless
browser was blocked by Radware. Retry with a visible window — it passes the
challenge far more reliably:

```bash
python hansard.py fetch "<url>" ../data/data/mvp_hansard.json --headless=False
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
