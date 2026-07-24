"""Tier-2 source: post-Cabinet press-conference transcripts (54th term).

The weekly post-Cabinet press conference is the PM (and often a senior minister)
speaking and taking questions — live, unscripted, public. There's no transcript
feed, but NZ Herald live-streams each one to YouTube (@nzheraldtv), and YouTube
auto-generates captions. We pull those captions (no video download, no ASR),
clean them, and emit the project's standard article schema so the LLM extractor
can attribute the politician's statements exactly as it does for a press release.

Only captions of a *public government event* are taken (not Herald's paywalled
site). Auto-captions are good on clear podium speech; the extractor is robust to
the residual noise.

    python pressers.py run --since 2023-11-27 --until 2026-05-28 --out ../corpus/pressers.json

Two phases, both resumable via on-disk caches:
  1. enumerate @nzheraldtv uploads whose title matches post-Cabinet → index.json
  2. for each, pull ios-client auto-subs + upload_date; keep those in-window.
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
YTDLP = os.path.join(HERE, "..", ".venv-media", "bin", "yt-dlp")
CHANNEL = "https://www.youtube.com/@nzheraldtv/videos"
TITLE_RE = re.compile(r"post.?cabinet", re.I)
IOS = ["--extractor-args", "youtube:player_client=ios", "--ignore-no-formats-error"]


def _run(args, timeout=120):
    return subprocess.run([YTDLP, *args], capture_output=True, text=True, timeout=timeout)


def enumerate_pressers(index_path, n=400):
    """Enumerate via YouTube search (the flat channel-scan under-finds). The query
    is specific enough that search returns the Herald's presser uploads; we keep
    only nzherald videos whose title matches post-Cabinet, deduped by id."""
    if os.path.exists(index_path):
        return json.load(open(index_path))
    print(f"enumerating via ytsearch{n} (Herald post-Cabinet)…", flush=True)
    r = _run([f"ytsearch{n}:Christopher Luxon post cabinet press conference",
              "--flat-playlist", "--print", "%(id)s :: %(channel)s :: %(title)s"],
             timeout=1200)
    rows, seen = [], set()
    for line in r.stdout.splitlines():
        parts = line.split(" :: ", 2)
        if len(parts) != 3:
            continue
        vid, channel, title = (p.strip() for p in parts)
        if "herald" in channel.lower() and TITLE_RE.search(title) and vid not in seen:
            seen.add(vid)
            rows.append({"id": vid, "title": title})
    json.dump(rows, open(index_path, "w"), indent=2)
    print(f"  found {len(rows)} candidate pressers", flush=True)
    return rows


def _clean_vtt(path):
    """VTT auto-captions → plain text. Drops timing/tags and the rolling-caption
    duplication (each cue repeats the prior line before adding a new one)."""
    out = []
    for ln in open(path, encoding="utf-8").read().splitlines():
        if "-->" in ln or not ln.strip() or ln.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()          # strip inline timing tags
        if not ln or (out and ln == out[-1]):
            continue
        out.append(ln)
    text = re.sub(r"\s+", " ", " ".join(out)).strip()
    return text


def fetch_one(vid, tmpdir):
    """Return (upload_date, text) for a video via the ios client, or (None, None)."""
    base = os.path.join(tmpdir, vid)
    for f in (base + ".en.vtt", base + ".en-orig.vtt"):
        if os.path.exists(f):
            os.remove(f)
    # --no-simulate is essential: --print alone implies --simulate, which silently
    # skips the actual subtitle write (prints the date but downloads nothing).
    r = _run(["--skip-download", "--no-simulate", *IOS, "--write-auto-subs",
              "--sub-langs", "en-orig,en", "--sub-format", "vtt", "--print", "upload_date",
              "-o", base + ".%(ext)s", f"https://www.youtube.com/watch?v={vid}"], timeout=180)
    date = next((l.strip() for l in r.stdout.splitlines() if re.fullmatch(r"\d{8}", l.strip())), None)
    vtt = next((f for f in (base + ".en.vtt", base + ".en-orig.vtt") if os.path.exists(f)), None)
    text = _clean_vtt(vtt) if vtt else None
    if vtt:
        os.remove(vtt)
    return date, text


def run(since="2023-11-27", until="2026-05-28", out="../corpus/pressers.json",
        limit=0, delay=2.0):
    since_i, until_i = int(since.replace("-", "")), int(until.replace("-", ""))
    tmpdir = os.path.join(HERE, "_presser_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    index = enumerate_pressers(os.path.join(tmpdir, "index.json"))

    out = out if os.path.isabs(out) else os.path.join(HERE, out)
    records = json.load(open(out)) if os.path.exists(out) else []
    done = {r["url"] for r in records}
    kept = len(records)

    todo = [c for c in index if f"https://www.youtube.com/watch?v={c['id']}" not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(index)} candidates, {len(done)} already fetched, {len(todo)} to try", flush=True)

    for i, c in enumerate(todo, 1):
        vid, title = c["id"], c["title"]
        url = f"https://www.youtube.com/watch?v={vid}"
        try:
            date, text = fetch_one(vid, tmpdir)
        except subprocess.TimeoutExpired:
            print(f"[{i}/{len(todo)}] TIMEOUT {vid}", flush=True)
            continue
        if not date or not text:
            print(f"[{i}/{len(todo)}] no-caption {vid} ({title[:40]})", flush=True)
            continue
        di = int(date)
        iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        if not (since_i <= di <= until_i):
            print(f"[{i}/{len(todo)}] out-of-window {iso}", flush=True)
            continue
        records.append({"headline": title, "date": iso,
                        "author": "Post-Cabinet Press Conference",
                        "content": text, "url": url, "source": "presser"})
        kept += 1
        json.dump(records, open(out, "w"), ensure_ascii=False, indent=1)   # incremental save
        print(f"[{i}/{len(todo)}] KEPT {iso}  {len(text)} chars  ({kept} total)", flush=True)
        time.sleep(delay)

    print(f"done: {kept} pressers -> {out}", flush=True)


if __name__ == "__main__":
    import fire
    fire.Fire({"run": run, "enumerate": enumerate_pressers})
