"""Render the whole site to static HTML.

The site has no writes, no logins and no per-request computation that isn't a
pure function of the committed data — sorting and filtering are already
client-side. So it can be served as files, which removes the memory ceiling
(the Flask process holds the 54 MB example set in RAM), the cold start, and
the single point of failure on election night.

This walks the app with Flask's test client rather than reimplementing the
routes, so there is exactly one definition of what a page contains. A route
that 404s here is a broken link in production too.

    python freeze.py                        # -> _site/, served at /
    SITE_BASE=/pol-score-cards python freeze.py   # served under a subpath

BASE PATH. A GitHub *project* page lives at <user>.github.io/<repo>/, so every
absolute URL needs that prefix. Passing SCRIPT_NAME through the test client
makes url_for() emit it, which is why the templates must use url_for and not a
literal href="/". SITE_ORIGIN is only needed for the things that require a
fully-qualified URL: sitemap.xml and the Open Graph tags.
"""
import os
import shutil
import sys
import time
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as site_app                                        # noqa: E402
import data_access_jsonl                                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("SITE_OUT", os.path.join(HERE, "_site"))
BASE = os.environ.get("SITE_BASE", "").rstrip("/")
ORIGIN = os.environ.get("SITE_ORIGIN", "https://act65.github.io").rstrip("/")

# Files copied verbatim rather than rendered. static/ is the whole asset tree;
# the downloads are the same files the /download/<key> route sends.
_STATIC_SRC = os.path.join(HERE, "static")

# The dataset files under static/ are BUILD inputs — Flask reads them in-process
# to render, and no page fetches them from the browser. Shipping them would put
# a second 58 MB copy of examples.jsonl next to the one already offered under
# /download. The downloads are the published copy; these are not.
_BUILD_ONLY = {".jsonl"}
_BUILD_ONLY_NAMES = {"dataset_stats.json", "attribute_icons.json", "manifest.json"}


def _ignore_build_inputs(_dirname, names):
    return {n for n in names
            if os.path.splitext(n)[1] in _BUILD_ONLY or n in _BUILD_ONLY_NAMES}


def _load_stats():
    path = os.path.join(_STATIC_SRC, "dataset_stats.json")
    try:
        with open(path) as f:
            return __import__("json").load(f)
    except (OSError, ValueError):
        return {}


def _urls():
    """Every reachable page, in sitemap order. Built from the data rather than
    from the route table, because the parameterised routes are only as valid as
    the ids behind them."""
    pages = ["/", "/party", "/data", "/about", "/rules"]
    for attr in site_app.RUBRICS:
        pages.append(f"/rubric/{attr}")

    shown, _total = site_app._featured()
    for d in shown:
        pid = d["politician"]["id"]
        pages.append(f"/politician/{pid}")
        for name in site_app.ATTR_NAMES:
            if data_access_jsonl.get_examples(pid, name):
                pages.append(f"/attribute/{pid}/{name}")
    return pages


def _write(path, body):
    """A URL becomes <path>/index.html so it keeps its trailing-slash-free form
    on a static host. '/' is the one exception."""
    rel = "index.html" if path == "/" else path.strip("/") + "/index.html"
    dest = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(body)
    return dest


def _sitemap(urls):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        loc = f"{ORIGIN}{BASE}{'' if u == '/' else u}/" if u != "/" else f"{ORIGIN}{BASE}/"
        # The card grid and the party table are the entry points; evidence pages
        # are deep and numerous, so they get a lower priority rather than being
        # left out (they are the point of the site, and should be indexed).
        pri = "1.0" if u == "/" else ("0.8" if u.count("/") == 1 else "0.5")
        lines.append(f"  <url><loc>{escape(loc)}</loc><priority>{pri}</priority></url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def _robots():
    return (
        "# Every page here is public record, derived from Hansard.\n"
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {ORIGIN}{BASE}/sitemap.xml\n"
    )


def main():
    t0 = time.time()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    site_app.app.config["SERVER_NAME"] = None
    # _head.html reads this to make og:image / og:url / canonical absolute,
    # which they must be or every platform ignores them.
    site_app.app.config["SITE_ORIGIN"] = ORIGIN
    client = site_app.app.test_client()
    env = {"SCRIPT_NAME": BASE} if BASE else {}

    urls = _urls()
    failed = []
    for i, u in enumerate(urls, 1):
        # PATH_INFO is the path AFTER the script name, so the prefix goes in
        # SCRIPT_NAME only — passing it in both makes every route 404.
        resp = client.get(u, environ_overrides=env)
        if resp.status_code != 200:
            failed.append((u, resp.status_code))
            continue
        _write(u, resp.data)
        if i % 100 == 0:
            print(f"  {i}/{len(urls)} pages", flush=True)

    shutil.copytree(_STATIC_SRC, os.path.join(OUT, "static"),
                    ignore=_ignore_build_inputs)

    # Only what the /data page actually advertises. app._DOWNLOADS is a superset
    # (it still routes the raw corpus, which is gitignored and therefore absent
    # from every deploy); copying by the advertised list keeps the built tree and
    # the page that links into it from disagreeing.
    offered = {d["key"] for d in (_load_stats().get("downloads") or []) if d.get("key")}
    missing = []
    for key in sorted(offered):
        src = site_app._DOWNLOADS.get(key)
        if not src or not os.path.exists(src):
            missing.append(key)
            continue
        dest = os.path.join(OUT, "download", key)
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(src, os.path.join(dest, os.path.basename(src)))

    with open(os.path.join(OUT, "sitemap.xml"), "w") as f:
        f.write(_sitemap(urls))
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write(_robots())
    # Jekyll would otherwise swallow any path starting with an underscore.
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _dn, fn in os.walk(OUT) for f in fn)
    print(f"\nfroze {len(urls) - len(failed)}/{len(urls)} pages "
          f"-> {OUT}  ({size / 1e6:.0f} MB, {time.time() - t0:.0f}s)")
    if missing:
        print(f"downloads not present, skipped: {', '.join(missing)}")
    if failed:
        print(f"FAILED ({len(failed)}):")
        for u, code in failed[:20]:
            print(f"  {code}  {u}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
