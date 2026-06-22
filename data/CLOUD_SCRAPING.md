# Cloud scraping runbook — the historical backfill on a VM

The full-term backfill (2023-10-06 → 2026-11-07, every in-scope source) is too
big and too slow for a laptop, and five of the sources need a real browser
(Playwright/Chromium) to get past JS rendering / the Radware anti-bot wall:

| Path | Sources |
|---|---|
| Plain HTTP (`requests`) | greens, national, act, top, **tpm**, **newsroom**, **spinoff** |
| Browser (Playwright) | labour, nzfirst, rnz, parliament, **hansard** |

News scope is **RNZ + Newsroom + The Spinoff** (project decision — no Herald/Stuff).

## Easiest: GCP via Terraform (one `apply`)

If you just want the corpus, use the Terraform module in **`deploy/gcp/`** — it
provisions a throwaway VM that runs the whole backfill, drops the result in a
bucket (optionally pushing to HuggingFace), and powers itself off. You set your
project ID and run `terraform apply`; you don't SSH in or run scrapers by hand.
See `deploy/gcp/README.md`. The rest of this doc is the manual/DIY path.

## What runs it

`scripts/backfill.py` orchestrates everything — one subprocess per source, each
writing `corpus/<source>.json` (Hansard → `corpus/hansard.jsonl`). Re-running a
single source overwrites just its file, so the job is resumable source-by-source.

```bash
python scripts/backfill.py                              # all sources, full term
python scripts/backfill.py --only greens,national,tpm   # subset
python scripts/backfill.py --skip hansard               # everything but Hansard
python scripts/backfill.py --since 2023-10-06 --until 2026-11-07 --delay 1.0
```

## Option A — Docker (recommended; matches your usual flow)

The `Dockerfile.scraper` is built on Microsoft's Playwright image, so Chromium and
its system libraries are already present.

```bash
cd data
docker build -f Dockerfile.scraper -t pol-scraper .
# mount a host dir so the corpus survives the container
docker run --rm -v "$PWD/corpus:/data/corpus" pol-scraper \
    python scripts/backfill.py --out /data/corpus
```

Run it on any small VM with Docker (a 2 vCPU / 4 GB box is plenty — scraping is
I/O-bound, the limiter is politeness delays, not CPU). For a long run, detach
(`docker run -d …`) and follow logs with `docker logs -f`.

## Option B — bare VM (no Docker)

```bash
sudo apt-get update && sudo apt-get install -y python3-pip
pip install -r requirements.txt playwright
playwright install --with-deps chromium      # pulls the browser + apt libs
python scripts/backfill.py --out corpus
```

If Radware blocks **headless** Chromium for Hansard/Parliament, those scrapers
support a visible browser (`--headless=False`) — which needs a desktop/VNC
session. Run the HTTP + party sources headless anywhere; do the Radware-walled
ones on a desktop-capable VM if needed. See `HANSARD_HOWTO.md`.

## Sizing & etiquette

- **Delay**: keep `--delay 1.0` (1 req/s) or higher — we are a good citizen.
- **Hansard** is the long pole: it enumerates every sitting day across the term
  (thousands of debate sections). Cap with `--hansard_max`, or backfill it in
  chunks by month and concatenate.
- **Time**: expect hours, not minutes, end to end. Detach and let it run.

## After the run

```bash
python dataset_stats.py corpus/*.json          # per-source summary
python corpus_report.py corpus/*.json* --out CORPUS_REPORT.md   # per-politician coverage
python publish_corpus.py --corpus corpus       # package + push to HuggingFace
```
