"""Combined 9-attribute extraction over the party press-release corpus, gated to a
nightly window (like extract_pressers.py) so it never collides with daytime use.

Party releases are short (~2-6k chars), so one-call-per-release would be thousands
of tiny subscription calls. Instead we BATCH several releases into each ~window
and re-attribute every extracted quote back to its source release by verbatim
text match — so each statement keeps the exact release URL/date, while the call
count stays low. One output record is emitted PER RELEASE (empty if it yielded
nothing) so the run is cleanly resumable.

Attribution: a release names its speaker in-text ("ACT Leader David Seymour
says…"), and the benchmark showed the extractor attributes to the named person
without speaker prep — so releases are fed as-is (headline + body).

NIGHT GATE: LLM calls only run when the local hour is in [start_hour, end_hour)
(default 00:00-06:00). Run at any other time it exits immediately.

    python extract_releases.py --dry_run
    python extract_releases.py --ignore_window --limit_windows 1   # one-window test
    python extract_releases.py                                     # real run, night-gated
"""

import collections
import datetime
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import fire

import extract

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "data", "corpus")
PARTY_FILES = {"national": "National", "labour": "Labour", "greens": "Green",
               "act": "ACT", "nzfirst": "NZ First", "tpm": "Te Pāti Māori"}


def _load(path):
    t = open(path, encoding="utf-8").read().strip()
    if not t:
        return []
    try:
        d = json.loads(t)
        return d if isinstance(d, list) else [d]
    except json.JSONDecodeError:
        return [json.loads(l) for l in t.splitlines() if l.strip()]


def _load_releases():
    rel = []
    for key, party in PARTY_FILES.items():
        f = os.path.join(CORPUS, f"{key}.json")
        if not os.path.exists(f):
            continue
        for a in _load(f):
            if a.get("content"):
                rel.append({"party": party, "url": a["url"], "date": a.get("date", ""),
                            "headline": a.get("headline", ""), "content": a["content"]})
    rel.sort(key=lambda r: r["url"])                     # stable order for resumable batching
    return rel


def _windows(releases, window_tokens):
    """Batch releases into ~window_tokens windows (each window = list of releases)."""
    limit = window_tokens * 4
    wins, cur, cur_len = [], [], 0
    for r in releases:
        rlen = len(r["content"]) + len(r["headline"]) + 60
        if cur and cur_len + rlen > limit:
            wins.append(cur)
            cur, cur_len = [], 0
        cur.append(r)
        cur_len += rlen
    if cur:
        wins.append(cur)
    return wins


def _window_text(window):
    return "\n\n".join(
        f"=== PRESS RELEASE {i} | {r['party']} | {r['date']} ===\n"
        f"Headline: {r['headline']}\n{r['content']}"
        for i, r in enumerate(window))


def _norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def _match_release(statement, norm_contents):
    """Which release in the window a quote came from, by verbatim (normalised)
    substring; falls back to best word-overlap. -1 if nothing plausible."""
    key = _norm(statement)[:60]
    if not key:
        return -1
    hits = [i for i, nc in enumerate(norm_contents) if key in nc]
    if hits:
        return hits[0]
    words = set(key.split())
    best, best_ov = -1, 0
    for i, nc in enumerate(norm_contents):
        ov = len(words & set(nc.split()))
        if ov > best_ov:
            best, best_ov = i, ov
    return best if best_ov >= 5 else -1


def _saved_urls(path):
    urls = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    urls.add(json.loads(line)["url"])
                except Exception:
                    pass
    return urls


def _in_window(start_hour, end_hour):
    return start_hour <= datetime.datetime.now().hour < end_hour


def run(out="release_scores.jsonl", window_tokens=6000, workers=2,
        model=extract.DEFAULT_MODEL, backend="claude_cli",
        start_hour=0, end_hour=6, ignore_window=False,
        dry_run=False, limit_windows=0):
    prompts_dir = os.path.join(HERE, "prompts")
    NON_ATTRS = {"true", "promises"}
    attrs = sorted(os.path.splitext(f)[0] for f in os.listdir(prompts_dir)
                   if f.endswith(".txt") and os.path.splitext(f)[0] not in NON_ATTRS)
    valid = set(attrs)
    system = extract.build_combined_system(attrs, prompts_dir, examples=True)
    out = out if os.path.isabs(out) else os.path.join(HERE, out)

    releases = _load_releases()
    done = _saved_urls(out)
    todo_rel = [r for r in releases if r["url"] not in done]
    windows = _windows(todo_rel, window_tokens)
    if limit_windows:
        windows = windows[:limit_windows]

    print(f"releases: {len(releases)}   done: {len(done)}   to do: {len(todo_rel)}   "
          f"windows: {len(windows)}", flush=True)
    if dry_run:
        by_party = collections.Counter(r["party"] for r in todo_rel)
        print(f"[dry run] window≈{window_tokens} tok (~{len(todo_rel)/max(1,len(windows)):.1f} "
              f"releases/window); by party: {dict(by_party)}; night {start_hour:02d}-{end_hour:02d}")
        return
    if not (ignore_window or _in_window(start_hour, end_hour)):
        print(f"outside night window (now {datetime.datetime.now():%H:%M}); exiting.", flush=True)
        return

    client = extract._client() if backend == "anthropic" else None

    def work(window):
        by_attr = extract.extract_all_attributes(
            client, system, {"content": _window_text(window)}, valid, model=model, backend=backend)
        norm_contents = [_norm(r["headline"] + " " + r["content"]) for r in window]
        buckets = [collections.defaultdict(list) for _ in window]
        for attr, exs in by_attr.items():
            for e in exs:
                idx = _match_release(e.statement, norm_contents)
                if idx >= 0:
                    buckets[idx][attr].append(e.model_dump())
        recs = []
        for i, r in enumerate(window):
            recs.append({"window_id": r["url"], "date": r["date"], "source": "Party release",
                         "party": r["party"], "url": r["url"],
                         "examples_by_attribute": {a: v for a, v in buckets[i].items()}})
        return recs

    written_win = written_ex = 0
    capped = False  # once the subscription's session cap is hit, further calls all
                    # fail — stop submitting instead of burning the night on retries.

    def _submit_ok():
        return not capped and (ignore_window or _in_window(start_hour, end_hour))

    with open(out, "a", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        it = iter(windows)
        futures = {}
        for _ in range(max(1, workers)):
            try:
                w = next(it)
            except StopIteration:
                break
            if _submit_ok():
                futures[ex.submit(work, w)] = 1
        while futures:
            for fut in as_completed(list(futures)):
                futures.pop(fut)
                try:
                    for rec in fut.result():
                        fh.write(json.dumps(rec) + "\n")
                        written_ex += sum(len(v) for v in rec["examples_by_attribute"].values())
                    fh.flush()
                    written_win += 1
                    print(f"[{written_win}/{len(windows)}] window done ({written_ex} examples so far)", flush=True)
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    if any(s in msg.lower() for s in ("session limit", "resets", "429")):
                        if not capped:
                            print("session cap hit — stopping new submissions for tonight", flush=True)
                        capped = True
                    else:
                        print(f"\nwindow error: {e}", flush=True)
                if _submit_ok():
                    try:
                        futures[ex.submit(work, next(it))] = 1
                    except StopIteration:
                        pass
                break
    stopped = ("all done" if written_win >= len(windows)
               else "session cap" if capped else "window closed / stopped")
    print(f"done: {written_win} windows this run ({stopped}), {written_ex} examples -> {out}", flush=True)


if __name__ == "__main__":
    fire.Fire(run)
