"""Backfill the whole term corpus: run every in-scope source over the fixed
election-term window into one corpus directory.

Designed to run on a browser-capable VM — labour, nzfirst, rnz, parliament and
hansard go through Playwright/Chromium (see ../CLOUD_SCRAPING.md). The plain-HTTP
sources (greens, national, act, top, tpm, newsroom, spinoff) run anywhere.

News scope is RNZ + Newsroom + The Spinoff by project decision (no Herald/Stuff).

    python backfill.py                                  # all sources, full term
    python backfill.py --only greens,national,tpm       # subset
    python backfill.py --skip hansard --out ../corpus    # everything but Hansard
    python backfill.py --since 2023-10-06 --until 2026-11-07

Each source writes <out>/<source>.json (Hansard: hansard.jsonl). Re-running a
source overwrites its file, so the backfill is resumable source-by-source.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRAPERS = os.path.normpath(os.path.join(HERE, "..", "scrapers"))

# The 54th Parliament term (election day 2023 → election day 2026).
TERM_START = "2023-10-06"
TERM_END = "2026-11-07"

# In-scope sources (sources.py adapters). Browser-path ones are noted for the
# runbook; sources.py auto-routes them through Playwright via needs_browser.
PARTY_SOURCES = ["greens", "national", "act", "top", "tpm", "labour", "nzfirst"]
NEWS_SOURCES = ["rnz", "newsroom", "spinoff"]            # decided scope
OTHER_SOURCES = ["parliament"]                            # press releases
SHORTCUT_ALL = PARTY_SOURCES + NEWS_SOURCES + OTHER_SOURCES

# These are plain-HTTP sites that 403 plain `requests` from datacenter IPs
# (Cloudflare). On a cloud VM we route them through the Playwright browser path,
# which executes Cloudflare's JS challenge and often clears it. (From a
# residential connection they don't need this — override with --browser_sources "".)
CLOUDFLARE_SOURCES = ["greens", "top", "tpm"]


def _months_between(since, until):
    a = datetime.date.fromisoformat(since)
    b = datetime.date.fromisoformat(until)
    return max(1, round((b - a).days / 30) + 1)


def run_source(src, since, out_dir, delay, browser=False):
    out = os.path.join(out_dir, f"{src}.json")
    cmd = [sys.executable, "sources.py", "scrape", "--source", src,
           "--since", since, "--out", out, "--delay", str(delay)]
    if browser:
        cmd.append("--browser")
    print(f"\n══ {src}{' [browser]' if browser else ''} ══\n›› {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=SCRAPERS).returncode == 0


def run_hansard(since, until, out_dir, max_n):
    # hansard.py works in months-from-now, not an explicit since; convert.
    months = _months_between(since, until)
    out = os.path.join(out_dir, "hansard.jsonl")
    # Hansard's Blazor SPA only renders in a HEADFUL browser (headless clears
    # Radware but stays on "Loading…" forever). On a machine with a display run
    # it directly; on a headless VM wrap in xvfb-run (a virtual display — the
    # Playwright image ships xvfb).
    cmd = [sys.executable, "hansard.py", "recent", out,
           "--months", str(months), "--max_n", str(max_n), "--headless=False"]
    if not os.environ.get("DISPLAY"):
        if shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
        else:
            print("  [hansard] WARNING: no DISPLAY and no xvfb-run — the headful "
                  "browser will fail. Install xvfb (apt-get install -y xvfb).")
    print(f"\n══ hansard ══\n›› {' '.join(cmd)}  (≈{months} months)", flush=True)
    return subprocess.run(cmd, cwd=SCRAPERS).returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=TERM_START)
    ap.add_argument("--until", default=TERM_END)
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "corpus")))
    ap.add_argument("--only", help="comma-separated subset of sources to run")
    ap.add_argument("--skip", default="", help="comma-separated sources to skip")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--hansard_max", type=int, default=8000,
                    help="cap on Hansard sections (the term has thousands)")
    ap.add_argument("--browser_sources", default=",".join(CLOUDFLARE_SOURCES),
                    help="comma-separated sources to force through the browser path "
                         "(Cloudflare/datacenter-IP workaround). Set to '' to disable.")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    requested = (args.only.split(",") if args.only else SHORTCUT_ALL + ["hansard"])
    skip = set(s.strip() for s in args.skip.split(",") if s.strip())
    todo = [s.strip() for s in requested if s.strip() and s.strip() not in skip]
    browser_set = set(s.strip() for s in args.browser_sources.split(",") if s.strip())

    print(f"Backfill {args.since} → {args.until} into {args.out}\nSources: {', '.join(todo)}"
          f"\nForced browser: {', '.join(sorted(browser_set)) or '(none)'}")
    results = {}
    for src in todo:
        if src == "hansard":
            results[src] = run_hansard(args.since, args.until, args.out, args.hansard_max)
        else:
            results[src] = run_source(src, args.since, args.out, args.delay,
                                      browser=src in browser_set)

    print("\n════ summary ════")
    for src, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {src}")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
