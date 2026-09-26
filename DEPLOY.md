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
