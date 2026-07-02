"""Time-bounded overnight full-term extraction.

Resumes the full 54th-term Hansard extraction (skipping windows already done),
runs for at most MAX_HOURS, then STOPS itself and finalizes — bundles the dataset,
refreshes the live site, and regenerates the dataset card from whatever was
completed. Designed so it cannot run past the time budget the user gave.

    nohup python3 overnight_run.py 10 > overnight.log 2>&1 &   # run for 10 hours

Safe to kill anytime (resumable). On exit (deadline OR completion OR kill) the
partial corpus on disk is intact and re-runnable.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SCORES = "hansard_scores_full.jsonl"
SINCE = "2023-10-14"
WINDOW = "14000"
WORKERS = "4"
TARGET = 744
BACKOFF = 75 * 60          # session-cap backoff
SHORT_SLEEP = 60           # brief pause between productive passes


def _count():
    p = os.path.join(HERE, SCORES)
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _seed():
    """Seed the full-term file from the completed 3-month run (identical per-day
    window ids) so March isn't re-extracted."""
    dst = os.path.join(HERE, SCORES)
    src = os.path.join(HERE, "hansard_scores_3mo.jsonl")
    if os.path.exists(dst) or not os.path.exists(src):
        return
    with open(src, encoding="utf-8") as f:
        data = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(data)


def _run_pass(timeout_s):
    """One resumable extraction pass, hard-capped at timeout_s so it can't run
    past the overnight deadline. Killing it mid-pass loses nothing (resumable)."""
    try:
        subprocess.run(
            [PY, "extract_hansard.py", "--since", SINCE, "--window_tokens", WINDOW,
             "--workers", WORKERS, "--backend", "claude_cli",
             "--model", "claude-opus-4-8", "--out", SCORES],
            cwd=HERE, timeout=max(30, timeout_s))
    except subprocess.TimeoutExpired:
        print("  pass hit the overnight deadline — stopping", flush=True)


def _finalize():
    print(f"=== finalizing at {_count()}/{TARGET} windows ===", flush=True)
    subprocess.run([PY, "hansard_dataset_stats.py", "--scores", SCORES,
                    "--out", "STATS_full-term.md"], cwd=HERE)
    subprocess.run([PY, "build_v2_dataset.py", "--scores", SCORES,
                    "--out", "site_data_full"], cwd=HERE)
    subprocess.run([PY, "build_v2_dataset.py", "--scores", SCORES,
                    "--out", "../site/static"], cwd=HERE)          # refresh live site
    subprocess.run([PY, "publish_v2_dataset.py", "--bundle", "site_data_full"], cwd=HERE)
    with open(os.path.join(HERE, "FULL_TERM_STATUS.txt"), "w") as f:
        done = _count()
        f.write(f"stopped at {done}/{TARGET} windows "
                f"({'COMPLETE' if done >= TARGET else 'partial — re-run overnight_run.py to continue'}).\n"
                f"site/static refreshed; site_data_full + dataset card ready to publish.\n")
    print("=== done finalizing ===", flush=True)


def main():
    max_hours = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    deadline = time.time() + max_hours * 3600
    _seed()
    print(f"overnight run: up to {max_hours}h, deadline in {max_hours*3600:.0f}s, "
          f"starting at {_count()}/{TARGET}", flush=True)

    while _count() < TARGET and time.time() < deadline:
        before = _count()
        _run_pass(deadline - time.time())
        after = _count()
        print(f"[{after}/{TARGET}] (+{after - before} this pass, "
              f"{(deadline - time.time())/3600:.1f}h left)", flush=True)
        if after >= TARGET or time.time() >= deadline:
            break
        if after == before:                      # session cap — back off, but not past deadline
            nap = min(BACKOFF, max(0, deadline - time.time()))
            if nap <= 0:
                break
            print(f"  session cap — backing off {nap/60:.0f} min", flush=True)
            time.sleep(nap)
        else:
            time.sleep(min(SHORT_SLEEP, max(0, deadline - time.time())))

    _finalize()
    reason = "complete" if _count() >= TARGET else "deadline reached"
    print(f"=== overnight run finished ({reason}) at {_count()}/{TARGET} ===", flush=True)


if __name__ == "__main__":
    main()
