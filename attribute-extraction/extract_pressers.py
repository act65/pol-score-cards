"""Combined 9-attribute extraction over the post-Cabinet presser transcripts,
gated to a nightly time window so it never collides with daytime subscription use.

Pipeline per presser (corpus/pressers.json):
  transcript --window to ~window_tokens--> windows
     --extract.extract_all_attributes (ONE call, all 9 attributes)--> examples
     --append--> <out> JSONL   (resumable: skips window_ids already written)

The benchmark (benchmark_diarization.py) showed the raw extractor attributes
speakers well without diarization AND excludes journalists, so transcripts are fed
as-is (no speaker prep). Records carry source="presser" + url so this can later be
built as its own "public / live" arena alongside Hansard.

NIGHT GATE: LLM calls only happen when the local hour is in [start_hour, end_hour)
(default 00:00–06:00). Run by cron at midnight; it self-stops at 06:00 and resumes
the next night. Run at any other time it exits immediately without touching the
subscription — so it can't collide with daytime use however it's triggered.

    python extract_pressers.py --dry_run                          # plan/estimate, no calls
    python extract_pressers.py --ignore_window --limit_windows 1  # one-window test (any time)
    python extract_pressers.py                                    # real run, night-gated
"""

import datetime
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import fire

import extract

HERE = os.path.dirname(os.path.abspath(__file__))
_SENT = re.compile(r"(?<=[.!?])\s+")


def _text_windows(text, window_tokens):
    """Split a transcript into ~window_tokens windows at sentence boundaries
    (~4 chars/token) so a statement is rarely cut mid-sentence."""
    limit = window_tokens * 4
    win, cur = [], ""
    for sent in _SENT.split(text):
        if cur and len(cur) + len(sent) > limit:
            win.append(cur.strip())
            cur = ""
        cur += sent + " "
    if cur.strip():
        win.append(cur.strip())
    return win


def _saved_ids(path):
    ids = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ids.add(json.loads(line)["window_id"])
                    except Exception:
                        pass
    return ids


def _in_window(start_hour, end_hour):
    return start_hour <= datetime.datetime.now().hour < end_hour


def run(out="presser_scores.jsonl",
        corpus="../data/corpus/pressers.json",
        window_tokens=6000,
        workers=2,
        model=extract.DEFAULT_MODEL,
        backend="claude_cli",
        start_hour=0, end_hour=6, ignore_window=False,
        dry_run=False, limit_windows=0):
    prompts_dir = os.path.join(HERE, "prompts")
    NON_ATTRS = {"true", "promises"}
    attrs = sorted(os.path.splitext(f)[0] for f in os.listdir(prompts_dir)
                   if f.endswith(".txt") and os.path.splitext(f)[0] not in NON_ATTRS)
    valid = set(attrs)
    system = extract.build_combined_system(attrs, prompts_dir, examples=True)

    corpus = corpus if os.path.isabs(corpus) else os.path.join(HERE, corpus)
    out = out if os.path.isabs(out) else os.path.join(HERE, out)
    pressers = json.load(open(corpus, encoding="utf-8"))

    plan = []  # (window_id, date, url, text)
    for p in pressers:
        wins = _text_windows(p["content"], window_tokens)
        for i, text in enumerate(wins):
            plan.append((f"{p['url']}#{i}", p.get("date", ""), p["url"], text))

    done = _saved_ids(out)
    todo = [w for w in plan if w[0] not in done]
    if limit_windows:
        todo = todo[:limit_windows]

    print(f"pressers: {len(pressers)}   windows: {len(plan)}   done: {len(done)}   "
          f"to do: {len(todo)}", flush=True)
    if dry_run:
        content_tok = sum(len(w[3]) // 4 for w in plan)
        print(f"[dry run] ~{content_tok:,} content tokens; window≈{window_tokens} tok; "
              f"night gate {start_hour:02d}:00–{end_hour:02d}:00 ({backend})")
        return

    if not (ignore_window or _in_window(start_hour, end_hour)):
        print(f"outside night window {start_hour:02d}:00–{end_hour:02d}:00 "
              f"(now {datetime.datetime.now():%H:%M}); exiting without any calls.", flush=True)
        return

    client = extract._client() if backend == "anthropic" else None

    def work(item):
        wid, date, url, text = item
        by_attr = extract.extract_all_attributes(
            client, system, {"date": date, "content": text}, valid,
            model=model, backend=backend)
        return wid, date, url, by_attr

    written = 0
    with open(out, "a", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        it = iter(todo)
        futures = {}
        # Prime up to `workers` tasks, then top up only while still in the window,
        # so we never *start* a call past the deadline (in-flight ones finish).
        for _ in range(max(1, workers)):
            try:
                item = next(it)
            except StopIteration:
                break
            if ignore_window or _in_window(start_hour, end_hour):
                futures[ex.submit(work, item)] = item[0]
        while futures:
            for fut in as_completed(list(futures)):
                wid = futures.pop(fut)
                try:
                    wid, date, url, by_attr = fut.result()
                    rec = {"window_id": wid, "date": date, "source": "presser", "url": url,
                           "examples_by_attribute":
                               {a: [e.model_dump() for e in exs] for a, exs in by_attr.items()}}
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    written += 1
                    n = sum(len(v) for v in by_attr.values())
                    print(f"[{written}/{len(todo)}] {wid[-45:]}: {n} examples", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"\nerror on {wid}: {e}", flush=True)
                # top up one more task if still in window
                if ignore_window or _in_window(start_hour, end_hour):
                    try:
                        item = next(it)
                        futures[ex.submit(work, item)] = item[0]
                    except StopIteration:
                        pass
                break
    stopped = "all done" if written >= len(todo) else "window closed / stopped"
    print(f"done: wrote {written} windows this run ({stopped}) -> {out}", flush=True)


if __name__ == "__main__":
    fire.Fire(run)
