"""Fetch MP portrait photos from Wikipedia for the scorecard site.

For each politician in site/static/politicians.jsonl, query the MediaWiki
`pageimages` API for the infobox portrait and download it to
site/static/img/portraits/<id>.jpg. To stay clean on licensing we keep ONLY
images hosted on Wikimedia Commons (upload.wikimedia.org/wikipedia/commons/…),
which are freely licensed; non-free "fair use" images (served from /wikipedia/en/)
are skipped. A CREDITS.md and a portraits.json (id -> source page) are written
alongside so attribution is auditable.

    cd data && python scrape_portraits.py                 # all MPs, skip ones already fetched
    cd data && python scrape_portraits.py --force         # re-fetch everything

Best-effort: name collisions / MPs without a Commons photo are logged and left
to fall back to the initials avatar on the card. Edit OVERRIDES for tricky names.
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
POLITICIANS = os.path.join(ROOT, "site", "static", "politicians.jsonl")
OUT_DIR = os.path.join(ROOT, "site", "static", "img", "portraits")
API = "https://en.wikipedia.org/w/api.php"
UA = "NZ-Pol-Scorecards/1.0 (research; contact via project repo)"

# Wikipedia titles for MPs whose plain name is ambiguous or doesn't match.
OVERRIDES = {
    "chris-hipkins": "Chris Hipkins",
    "christopher-luxon": "Christopher Luxon",
    "david-seymour": "David Seymour (New Zealand politician)",
    "winston-peters": "Winston Peters",
    "james-shaw": "James Shaw (New Zealand politician)",
    "marama-davidson": "Marama Davidson",
    "chloe-swarbrick": "Chlöe Swarbrick",
    "rawiri-waititi": "Rawiri Waititi",
    "debbie-ngarewa-packer": "Debbie Ngarewa-Packer",
    "grant-robertson": "Grant Robertson",
}


def _get(url, retries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 5 * (attempt + 1)      # 5s, 10s, 15s backoff
                print(f"    429 — backing off {wait}s")
                time.sleep(wait)
                continue
            raise


def _api_thumb(title, size=500):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "pageimages",
        "piprop": "thumbnail|name", "pithumbsize": size, "redirects": 1,
        "titles": title,
    })
    data = json.loads(_get(f"{API}?{q}"))
    pages = data.get("query", {}).get("pages", {})
    for _pid, page in pages.items():
        thumb = page.get("thumbnail", {}).get("source")
        if thumb:
            return thumb, page.get("title", title)
    return None, None


def resolve(name, pid):
    """Return (thumb_url, source_title) preferring a Commons-hosted image."""
    candidates = []
    if pid in OVERRIDES:
        candidates.append(OVERRIDES[pid])
    candidates += [name, f"{name} (New Zealand politician)", f"{name} (politician)"]
    seen = set()
    for title in candidates:
        if title in seen:
            continue
        seen.add(title)
        try:
            thumb, src = _api_thumb(title)
        except Exception as e:  # network/HTTP hiccup — try next candidate
            print(f"    ! {title!r}: {e}")
            continue
        if thumb and "/wikipedia/commons/" in thumb:
            return thumb, src
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch even if a file exists")
    ap.add_argument("--limit", type=int, default=0, help="only process first N (debug)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    mps = [json.loads(l) for l in open(POLITICIANS) if l.strip()]
    if args.limit:
        mps = mps[:args.limit]

    credits, index = [], {}
    got = miss = skip = 0
    for i, mp in enumerate(mps, 1):
        pid, name = mp["id"], mp["name"]
        dst = os.path.join(OUT_DIR, f"{pid}.jpg")
        if os.path.exists(dst) and not args.force:
            skip += 1
            index[pid] = f"img/portraits/{pid}.jpg"
            continue
        thumb, src = resolve(name, pid)
        if not thumb:
            print(f"[{i}/{len(mps)}] MISS  {name}")
            miss += 1
            time.sleep(1.0)
            continue
        try:
            img = _get(thumb)
            with open(dst, "wb") as f:
                f.write(img)
        except Exception as e:
            print(f"[{i}/{len(mps)}] ERR   {name}: {e}")
            miss += 1
            time.sleep(1.0)
            continue
        got += 1
        index[pid] = f"img/portraits/{pid}.jpg"
        credits.append(f"- **{name}** — [{src}](https://en.wikipedia.org/wiki/"
                       f"{urllib.parse.quote(src.replace(' ', '_'))}), via Wikimedia Commons")
        print(f"[{i}/{len(mps)}] OK    {name}  <- {src}")
        time.sleep(1.0)

    with open(os.path.join(OUT_DIR, "portraits.json"), "w") as f:
        json.dump(index, f, indent=2)
    with open(os.path.join(OUT_DIR, "CREDITS.md"), "w") as f:
        f.write("# Portrait credits\n\nPortraits fetched from Wikipedia infoboxes "
                "(Wikimedia Commons, freely licensed). Each links to its source page.\n\n"
                + "\n".join(sorted(credits)) + "\n")
    print(f"\ndone: {got} fetched, {skip} already present, {miss} missing "
          f"({len(index)}/{len(mps)} have a portrait)")


if __name__ == "__main__":
    main()
