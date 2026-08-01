"""Check which party press-release URLs still resolve on the live site.

Parties delete/restructure their sites (e.g. the Greens dropped James Shaw's
releases), so a stored live URL can 404 while the article survives in the Wayback
Machine. This HEAD-checks every release URL and writes a status map
(corpus/release_url_status.json: {url: {"live": bool, "date": "..."}}) that the
dataset build reads to point dead links at their Wayback snapshot instead.

    cd data/scrapers && python check_release_urls.py            # all parties
    cd data/scrapers && python check_release_urls.py --workers 16

Re-run after a scrape/top-up so newly-dead links get redirected.
"""

import collections
import json
import os
import threading
import urllib.request
from urllib.parse import urlparse

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "corpus")
PARTY_FILES = ["national", "labour", "act", "greens", "nzfirst", "tpm"]
UA = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")}


import time


def _status(url):
    """'live' (200), 'dead' (confirmed 404/410), or 'unknown' (transient — timeout,
    429/503, connection reset). Only a CONFIRMED 404 counts as dead: rate-limiting
    the smaller party sites otherwise looks like death and would wrongly redirect
    live links to Wayback. Transient failures are retried before giving up."""
    from urllib.parse import quote
    enc = quote(url, safe=":/?&=%#")               # percent-encode non-ASCII (e.g. curly ’)
    for attempt in range(4):
        try:
            req = urllib.request.Request(enc, headers=UA, method="GET")
            with urllib.request.urlopen(req, timeout=30) as r:
                return "live" if r.status == 200 else "unknown"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "dead"
            if e.code in (429, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            return "unknown"
        except Exception:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return "unknown"
    return "unknown"


def run(delay=0.4, out=None):
    out = out or os.path.join(CORPUS, "release_url_status.json")
    urls = {}                                      # url -> date
    for key in PARTY_FILES:
        p = os.path.join(CORPUS, f"{key}.json")
        if not os.path.exists(p):
            continue
        for a in json.load(open(p, encoding="utf-8")):
            if a.get("url"):
                urls[a["url"]] = a.get("date", "")

    # Group by domain and check each domain SERIALLY (one request at a time) in its
    # own thread, so no party site is ever hit concurrently — that's what turned real
    # 404s into rate-limited timeouts. Domains run in parallel, so it's still quick.
    by_domain = collections.defaultdict(list)
    for u, d in urls.items():
        by_domain[urlparse(u).netloc].append((u, d))
    print(f"checking {len(urls)} URLs across {len(by_domain)} domains "
          f"(serial per domain)…", flush=True)

    status = {}
    tally = collections.Counter()
    lock = threading.Lock()
    import time

    def worker(items):
        for u, d in items:
            st = _status(u)
            with lock:
                status[u] = {"live": st != "dead", "status": st, "date": d}
                tally[st] += 1
            time.sleep(delay)

    threads = [threading.Thread(target=worker, args=(items,)) for items in by_domain.values()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    json.dump(status, open(out, "w"), ensure_ascii=False, indent=0)
    print(f"done: {tally['live']} live, {tally['dead']} dead (404), "
          f"{tally['unknown']} unknown(kept live) -> {out}", flush=True)


if __name__ == "__main__":
    fire.Fire(run)
