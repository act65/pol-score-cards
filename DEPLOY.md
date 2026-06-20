# Deploying the site (the demo)

The public site is a small Flask app that serves **committed data** (no API key,
no database, no scraping at runtime), so it's cheap and easy to host. The game is
still WIP and is **not** deployed here.

Production is served by **gunicorn** (`gunicorn app:app`), not the Flask dev
server. Data files resolve relative to the code, so the app runs from any working
directory / container.

## Option A — Render (easiest, no Docker) ✅ recommended for a demo link

A blueprint (`render.yaml`) is included.

1. Push this repo to GitHub.
2. Go to <https://render.com> → **New** → **Blueprint** → pick the repo.
3. Render reads `render.yaml`, builds from `site/`, and starts gunicorn. Done —
   you get a `https://<name>.onrender.com` URL.

Notes:
- Uses the **free** plan: the service **cold-starts after ~15 min idle** (first
  hit takes ~30–50s, then it's fast). Fine for a link you send to people; upgrade
  to a paid instance ($7/mo) if you want it always-warm.
- `autoDeploy` is on, so pushes to the default branch redeploy automatically.

## Option B — Docker (portable: Fly.io, Railway, your own host)

A `Dockerfile` is included (copies only `site/`).

```bash
docker build -t scorecards .
docker run -p 8080:8080 scorecards     # -> http://localhost:8080
```

- **Fly.io:** `fly launch` (it will detect the Dockerfile) → `fly deploy`.
- **Railway / any container host:** point it at the Dockerfile; it listens on
  `$PORT` (default 8080).

## Updating the data

The site serves `site/static/{politicians,scores,examples,attributes}.jsonl`.
Regenerate them with `attribute-extraction/build_site_data.py` (see the README),
commit the updated `.jsonl` files, and push — the host redeploys with the new data.
No runtime LLM calls happen on the server.
