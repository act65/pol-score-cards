"""Run combined 9-attribute extraction over the Hansard corpus, efficiently.

Pipeline per sitting day:
  corpus/hansard.json  --group by day-->  parts
     --hansard_prep.prep_day-->  attributed member-speech blocks (procedural dropped)
     --re-batch to ~window_tokens-->  windows (each block prefixed "SPEAKER: …")
     --extract.extract_all_attributes (ONE cached call, all 9 attributes)-->  examples
     --append--> <out> JSONL  (resumable: skips windows already written)

Why this shape (see HANSARD_EXTRACTION_PLAN.md):
  * combined call = the article text is sent once, not once per attribute (9x);
  * speaker-prep drops ~18% procedural/chrome AND gives every block a known
    speaker, so scores are attributed, not guessed;
  * prompt caching makes the shared 9-rubric system prompt ~free after call 1;
  * re-batching keeps calls (and their fixed overhead) low.

    # estimate cost of the full run WITHOUT spending anything:
    python extract_hansard.py --dry_run
    # real run (subscription backend, no API credits):
    python extract_hansard.py --backend claude_cli --out hansard_scores.jsonl
    # real run (API, with caching):
    export ANTHROPIC_API_KEY=...; python extract_hansard.py --out hansard_scores.jsonl
"""

import collections
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import fire

import extract
import hansard_prep


def _windows(blocks, window_tokens):
    """Pack attributed blocks into ~window_tokens text windows, each block
    rendered as 'SPEAKER: text' so the model never has to guess the speaker."""
    win, cur, cur_tok = [], [], 0
    for b in blocks:
        piece = f"{b['speaker']}: {b['text']}"
        ptok = len(piece) // 4
        if cur and cur_tok + ptok > window_tokens:
            win.append("\n\n".join(cur))
            cur, cur_tok = [], 0
        cur.append(piece)
        cur_tok += ptok
    if cur:
        win.append("\n\n".join(cur))
    return win


def _saved_ids(path):
    ids = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(json.loads(line)["window_id"])
                except Exception:
                    pass
    return ids


def _load_by_day(corpus, since):
    by_day = collections.defaultdict(list)
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("date", "") >= since:
                by_day[r["date"]].append(r)
    return dict(sorted(by_day.items()))


def run(out="hansard_scores.jsonl",
        corpus="../data/corpus/hansard.json",
        since="2023-10-14",
        window_tokens=14000,
        workers=4,
        model=extract.DEFAULT_MODEL,
        backend=extract.DEFAULT_BACKEND,
        dry_run=False,
        limit_days=0,
        examples=True,  # keep few-shot blocks in the (cached) system prompt
        # rough public list rates ($/Mtok) for the estimate only — verify current.
        in_rate=15.0, out_rate=75.0, cache_read_rate=1.5):
    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    # All nine scorecard attributes have a prompt and are scored here (Strength is
    # an LLM-knowledge guess for now; evidence-based verification is a v3.0 goal).
    # `true`/`promises` are helper prompts, not attributes — exclude them.
    NON_ATTRS = {"true", "promises"}
    attrs = sorted(os.path.splitext(f)[0] for f in os.listdir(prompts_dir)
                   if f.endswith(".txt") and os.path.splitext(f)[0] not in NON_ATTRS)
    valid = set(attrs)
    system = extract.build_combined_system(attrs, prompts_dir, examples=examples)
    sys_tok = len(system) // 4

    by_day = _load_by_day(corpus, since)
    days = list(by_day)
    if limit_days:
        days = days[:limit_days]

    # Build all windows first (cheap) so we can report/resume.
    plan = []  # (window_id, date, text, in_tok)
    for date in days:
        blocks = hansard_prep.prep_day(by_day[date])
        for i, text in enumerate(_windows(blocks, window_tokens)):
            wid = f"{date}#{i}"
            plan.append((wid, date, text, len(text) // 4))

    n_win = len(plan)
    content_tok = sum(p[3] for p in plan)

    if dry_run:
        # caching: system prompt billed full once, then cache-read; assume cache
        # stays warm across the back-to-back batch (TTL ~5 min).
        sys_full = sys_tok
        sys_cached = sys_tok * (n_win - 1) if n_win else 0
        # output: assume ~900 output tokens/window (statements+scores+explanations)
        out_tok = n_win * 900
        in_cost = (content_tok + sys_full) / 1e6 * in_rate \
            + sys_cached / 1e6 * cache_read_rate
        in_cost_nocache = (content_tok + sys_tok * n_win) / 1e6 * in_rate
        out_cost = out_tok / 1e6 * out_rate
        print(f"=== Hansard extraction DRY RUN ({model}) ===")
        print(f"days: {len(days)}   windows (=API calls): {n_win}   "
              f"window_tokens≈{window_tokens}")
        print(f"system prompt: {sys_tok:,} tok ({len(attrs)} attrs, cached)")
        print(f"content input: {content_tok:,} tok")
        print(f"est output:    {out_tok:,} tok (~900/window)")
        print(f"--- $ estimate at in={in_rate}/out={out_rate}/cache={cache_read_rate} per Mtok ---")
        print(f"input  $ (caching ON):  {in_cost:8.2f}")
        print(f"input  $ (no caching):  {in_cost_nocache:8.2f}   "
              f"(caching saves ${in_cost_nocache - in_cost:,.2f})")
        print(f"output $:               {out_cost:8.2f}")
        print(f"TOTAL  $ (caching ON):  {in_cost + out_cost:8.2f}")
        print("NB rates are placeholders — set --in_rate/--out_rate to current "
              "pricing, or use --backend claude_cli (subscription, no API $).")
        return

    client = extract._client() if backend == "anthropic" else None
    done = _saved_ids(out)
    if done:
        print(f"resuming: {len(done)} windows already in {out}")
    todo = [p for p in plan if p[0] not in done]
    print(f"{len(todo)} windows to do (of {n_win}) with {workers} worker(s)")

    def work(item):
        wid, date, text, _tok = item
        by_attr = extract.extract_all_attributes(
            client, system, {"date": date, "content": text}, valid,
            model=model, backend=backend)
        return wid, date, by_attr

    # Each claude_cli call is an independent subprocess, so threads parallelise
    # well (they block on the subprocess, releasing the GIL). Results are written
    # from the main thread as they complete, so the JSONL append stays single-
    # threaded and safe; the run remains resumable (window_id dedupe on restart).
    written = 0
    with open(out, "a", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, item): item[0] for item in todo}
        for fut in as_completed(futures):
            wid = futures[fut]
            try:
                wid, date, by_attr = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"\nerror on {wid}: {e}", flush=True)
                continue
            rec = {"window_id": wid, "date": date,
                   "examples_by_attribute":
                       {a: [e.model_dump() for e in exs] for a, exs in by_attr.items()}}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            written += 1
            n = sum(len(v) for v in by_attr.values())
            print(f"[{written}/{len(todo)}] {wid}: {n} scored examples", flush=True)
    print(f"done: wrote {written} windows -> {out}")


if __name__ == "__main__":
    fire.Fire(run)
