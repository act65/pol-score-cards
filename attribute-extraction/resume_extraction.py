"""Hands-off resume loop for the Hansard extraction on the Claude Pro subscription.

The Pro session cap (~tens of windows per 5-hour window) means a large run can't
finish in one sitting. extract_hansard.py is resumable, so this just re-runs it
whenever progress is possible, backing off when the session is exhausted, and
rebuilds the dataset bundle at each milestone. Detached (nohup) it survives this
chat ending; it's safe to kill and relaunch (resumable).

Stages: finish the 3-month dataset first (quick, reviewable), then the full term
(seeded from the 3-month results — window ids are per-day, so March is reused).

    nohup python3 resume_extraction.py > resume.log 2>&1 &
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
WINDOW = "14000"
WORKERS = "4"
SHORT_SLEEP = 5 * 60       # progressing — brief pause, session may have budget
BACKOFF = 75 * 60          # no progress — session exhausted, wait for reset

STAGES = [
    # (label, since, scores_file, bundle_dir)
    ("3-month", "2026-03-01", "hansard_scores_3mo.jsonl", "site_data_v2"),
    ("full-term", "2023-10-14", "hansard_scores_full.jsonl", "site_data_full"),
]


def _count(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _expected(since):
    out = subprocess.run(
        [PY, "extract_hansard.py", "--dry_run", "--since", since,
         "--window_tokens", WINDOW], cwd=HERE, capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if "windows (=API calls):" in line:
            return int(line.split("windows (=API calls):")[1].split()[0])
    return 10 ** 9  # unknown -> keep trying


def _seed(dst, src):
    """Seed the full-term file with already-done windows from the 3-month file
    (identical per-day window ids), so March isn't re-extracted."""
    if not os.path.exists(src) or os.path.exists(dst):
        return
    with open(src, encoding="utf-8") as f:
        data = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"  seeded {dst} from {src} ({_count(dst)} windows)", flush=True)


def _run_pass(since, out):
    subprocess.run(
        [PY, "extract_hansard.py", "--since", since, "--window_tokens", WINDOW,
         "--workers", WORKERS, "--backend", "claude_cli",
         "--model", "claude-opus-4-8", "--out", out],
        cwd=HERE)


def _bundle(scores, bundle_dir, stats_md):
    subprocess.run([PY, "hansard_dataset_stats.py", "--scores", scores,
                    "--out", stats_md], cwd=HERE)
    subprocess.run([PY, "build_v2_dataset.py", "--scores", scores,
                    "--out", bundle_dir], cwd=HERE)
    print(f"  ✓ bundled {bundle_dir} + {stats_md}", flush=True)


def main():
    for label, since, scores, bundle in STAGES:
        exp = _expected(since)
        if label == "full-term":
            _seed(scores, "hansard_scores_3mo.jsonl")
        print(f"\n=== stage {label}: target {exp} windows -> {scores} ===", flush=True)
        stale = 0
        while _count(scores) < exp:
            before = _count(scores)
            _run_pass(since, scores)
            after = _count(scores)
            print(f"[{label}] {after}/{exp} windows done", flush=True)
            if after >= exp:
                break
            if after == before:
                stale += 1
                print(f"  no progress (session cap) — backing off "
                      f"{BACKOFF // 60} min [stale x{stale}]", flush=True)
                time.sleep(BACKOFF)
            else:
                stale = 0
                _bundle(scores, bundle, f"STATS_{label}.md")  # refresh as we go
                time.sleep(SHORT_SLEEP)
        _bundle(scores, bundle, f"STATS_{label}.md")
        print(f"=== stage {label} COMPLETE ({_count(scores)} windows) ===", flush=True)
    print("\nALL STAGES COMPLETE", flush=True)


if __name__ == "__main__":
    main()
