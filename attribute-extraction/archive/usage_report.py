"""What each `claude -p` call actually costs on the subscription.

    python usage_report.py            # summary
    python usage_report.py --by_night # one row per night

Reads usage_v3.jsonl, written by claude_cli._record_usage during any run made
through overnight_run.py. Spends nothing.

The question this exists to answer: the full term sends 13.9M tokens of debate
and, at window_tokens=3000, 41.4M tokens of the same 7,469-token rubric resent
5,548 times. If the CLI cache-reads that prefix, the rubric is nearly free and
small windows are the right choice. If it is billed in full, three-quarters of
the project's quota is spent re-sending text the model has already seen, and
that — not the window size — is the thing to fix.

Two nights of cap timings pointed at "billed in full" (they capped within 9% of
the same total under that assumption, and 2.2x apart under the other), but that
was inference from when calls started failing. `cache_read` settles it.
"""

from __future__ import annotations

import collections
import json
import os

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM_TOKENS = 7469          # build_combined_system(EXTRACTED_IN_WINDOWS)


def _rows(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _fmt(n):
    return f"{n:,.0f}" if n is not None else "—"


def run(log: str = "usage_v3.jsonl", by_night: bool = False) -> None:
    path = log if os.path.isabs(log) else os.path.join(HERE, log)
    if not os.path.exists(path):
        print(f"no usage log at {path} — it is written by runs made through "
              f"overnight_run.py, so it appears after the next night.")
        return

    rows = list(_rows(path))
    if not rows:
        print("usage log is empty")
        return

    by = collections.defaultdict(list)
    for r in rows:
        key = (r["ts"][:10] if by_night else "") + "|" + (r.get("label") or "?")
        by[key].append(r)

    print(f"{len(rows):,} calls recorded\n")
    hdr = f"{'night':11} " if by_night else ""
    print(f"{hdr}{'stage':10} {'calls':>6} {'fresh in':>11} {'cache read':>11} "
          f"{'output':>9} {'cached %':>9} {'s/call':>7}")
    for key in sorted(by):
        night, label = key.split("|", 1)
        rs = by[key]
        fresh = sum(r.get("input") or 0 for r in rs)
        cached = sum(r.get("cache_read") or 0 for r in rs)
        out = sum(r.get("output") or 0 for r in rs)
        secs = [(r.get("duration_ms") or 0) / 1000 for r in rs if r.get("duration_ms")]
        pct = 100 * cached / (fresh + cached) if (fresh + cached) else 0
        lead = f"{night:11} " if by_night else ""
        print(f"{lead}{label:10} {len(rs):6,} {_fmt(fresh):>11} {_fmt(cached):>11} "
              f"{_fmt(out):>9} {pct:8.1f}% "
              f"{(sum(secs) / len(secs)) if secs else 0:7.0f}")

    # The verdict the log exists to give.
    win = [r for r in rows if (r.get("label") or "") == "windows"]
    if win:
        cached = sum(r.get("cache_read") or 0 for r in win)
        fresh = sum(r.get("input") or 0 for r in win)
        per_call_cached = cached / len(win)
        print(f"\n--- the rubric ({SYSTEM_TOKENS:,} tokens, resent every call) ---")
        print(f"window calls: {len(win):,}   mean cache_read/call: {per_call_cached:,.0f}")
        if per_call_cached >= SYSTEM_TOKENS * 0.8:
            print("CACHED. The repeated rubric is nearly free, so call count is\n"
                  "cheap and small windows cost little. Window size can be chosen\n"
                  "on extraction quality alone.")
        elif per_call_cached < SYSTEM_TOKENS * 0.2:
            print("NOT CACHED. Every call pays the full rubric, so at 3k windows\n"
                  f"~{100 * SYSTEM_TOKENS / (SYSTEM_TOKENS + 3000):.0f}% of every call is "
                  "re-sent instruction. Fixing that\nbeats any window-size choice: "
                  "shrink the prompt, or batch\nseveral windows per call.")
        else:
            print("PARTIAL caching — measure again over more calls before acting.")
        print(f"\nfresh input/call: {fresh / len(win):,.0f} tokens "
              f"(content is ~{3000 if fresh / len(win) < 12000 else 14000:,} + rubric)")


if __name__ == "__main__":
    fire.Fire({"run": run})
