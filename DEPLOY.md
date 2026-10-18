# Deploying the site

The site serves **committed data** — no API key, no database, no scraping at
runtime — so it can be published as plain files. That is the recommended path
and what CI does.

## Option A — GitHub Pages, built by Actions ✅ recommended

`.github/workflows/pages.yml` renders the site to static HTML and publishes it.
**Nothing generated is committed**: `freeze.py` writes `site/_site/` (gitignored),
the workflow uploads it as a Pages artifact and `actions/deploy-pages` serves it.
There is no `gh-pages` branch and no HTML in the repo's history.

One-time setup: **Settings → Pages → Source: GitHub Actions**. After that every
push touching `site/` republishes, and the site lands at
`https://act65.github.io/pol-score-cards/`.

Build it locally exactly as CI does:

```bash
cd site
python freeze.py                                  # -> _site/, served at /
SITE_BASE=/pol-score-cards python freeze.py       # as CI builds it
cd _site && python -m http.server 8000            # check it
```

`freeze.py` walks the real routes with Flask's test client, so there is one
definition of what a page contains and a route that 500s **fails the build**
rather than shipping a broken page. Current output: **933 pages, ~240 MB, ~4
seconds** (the limit is 1 GB).

### Why static

The Flask process holds the 54 MB example set in memory: **187 MB RSS per
worker**, two workers, against Render's 512 MB free tier — and that number grows
with every extraction pass. Static removes the memory ceiling, the ~40 s cold
start, and the single point of failure on election night.

### Paths

A GitHub *project* page is served from `/<repo>/`, so every absolute URL needs
that prefix. `SITE_BASE` supplies it via `SCRIPT_NAME`, which is why templates
must link with `url_for` and never a literal `href="/…"`. `SITE_ORIGIN` is only
used where a fully-qualified URL is required: `sitemap.xml` and the Open Graph
tags.

**Moving to a custom domain:** set `SITE_BASE` to `''` in the workflow, add a
`CNAME` file to `site/static/`, and point `SITE_ORIGIN` at the new host.

## Option B — Docker / any container host

`Dockerfile` copies only `site/` and runs gunicorn. Still useful if you want the
dynamic app (it listens on `$PORT`, default 8080):

```bash
docker build -t scorecards .
docker run -p 8080:8080 scorecards
```

Mind the memory figure above when sizing the instance.

## Option C — Render

`render.yaml` is still here and still works (free plan, cold-starts after ~15
min idle). Superseded by Option A for anything public-facing.

## Updating the data

Regenerate `site/static/{politicians,scores,examples,attributes}.jsonl` with
`attribute-extraction/build_v2_dataset.py`, refresh `dataset_stats.json` with
`site/gen_data_stats.py`, commit, push. CI rebuilds and redeploys. No LLM calls
ever happen at serve time.

The `.jsonl` files under `site/static/` are **build inputs** — Flask reads them
in-process and no page fetches them from the browser — so `freeze.py` leaves
them out of the published tree. The copies offered on `/data` are published
under `/download/`.

## Share image and favicon

`site/make_og.py` generates `static/img/og.png` (1200×630, with the live House
means on it) and `static/favicon.svg`. Re-run it if the site's name, palette or
headline numbers change.

## The dataset is hosted, not committed (18 October 2026)

`site/static/*.jsonl` are **build inputs fetched at build time**, not files in
the repository.

### Why

They are generated — every one is reproduced by an extraction run or by
`build_v2_dataset.py` — and they had taken over the repository:

| path | total across git history |
|---|---|
| `attribute-extraction/hansard_scores_v3.jsonl` | ~1,088 MB (18 revisions) |
| `site/static/examples.jsonl` | ~601 MB |
| `attribute-extraction/site_data_full/examples.jsonl` | ~119 MB |
| others | ~350 MB |

`.git` was **624 MB**, so every clone paid for 2 GB of superseded copies of
files nobody reads. And `examples.jsonl` had reached **92 MB** against GitHub's
**100 MB hard push limit** — the next extraction pass would simply have been
rejected.

Git LFS was considered and rejected: it does not shrink existing history, and
its 1 GB/month free bandwidth is a tighter ceiling than the problem being
solved. A requester-pays bucket was rejected too — requester-pays bills the
*downloader*, who must therefore be an authenticated cloud principal, which
breaks both CI-without-secrets and the public download links on `/data`, since
an anonymous visitor has no account to bill.

### How a build gets its data

```
site/data_manifest.json   committed, small, one sha256 per file
        │
        ├── site/fetch_data.py            downloads + VERIFIES against it
        └── .github/workflows/pages.yml   cache → fetch → freeze
```

The manifest being committed is the point: a truncated download, a stale cache
or a dataset repo that has moved on all fail loudly in `fetch_data.py` rather
than producing a website quietly built from the wrong numbers. CI caches on
`hashFiles('site/data_manifest.json')`, so a push that only touches a template
restores 92 MB from cache instead of re-downloading it.

```bash
cd site && python fetch_data.py          # fetch what is missing or stale
cd site && python fetch_data.py --check  # verify only, download nothing
cd site && python fetch_data.py --force  # re-fetch everything
```

`fetch_data.py` needs no credentials and no `huggingface_hub` — it uses the
library when present (caching, resume) and falls back to a plain HTTPS GET of
the same public URL.

### Publishing a new dataset

After any extraction run or dataset rebuild:

```bash
cd attribute-extraction
python publish_scores.py package                  # stage + manifest + card
python publish_scores.py package --push --repo act65/nz-pol-scorecards
git add site/data_manifest.json && git commit      # the new hashes
```

The commit of `data_manifest.json` is what makes the new data live: CI keys its
cache on that file and `fetch_data.py` verifies against it. Publishing without
committing the manifest leaves CI building the previous dataset;
`site/tests/test_data_hosting.py::test_the_working_copy_matches_the_manifest`
catches the reverse mistake (regenerating locally and forgetting to publish).

### `/data` downloads point off-site

The download buttons link to HuggingFace rather than to `/download/<key>`.
Serving them locally meant `freeze.py` copied a 92 MB `examples.jsonl` into the
Pages artifact on every build — paid for in artifact size and CDN bandwidth, to
hand over a file the dataset host serves better and with versioning. The
artifact went from 323 MB to 231 MB.
