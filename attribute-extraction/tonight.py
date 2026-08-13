"""Run the two remaining v3.0 extractions overnight, in sequence.

    cd attribute-extraction
    nohup python tonight.py run --at 23:00 --until 06:00 > tonight.log 2>&1 &
    python tonight.py status

Two attributes still have no data, and neither can be produced deterministically:

* **Forthrightness** — 924 calls over `corpus/oral_questions.jsonl`. Evasion is
  a relation between a question and an answer, so it cannot be read off a speech
  window; this is the only pass that produces it.
* **Authenticity** — a stated position per window, which
  `data/authenticity_score.py` joins to the vote record. The join and its tests
  are already built and idle for want of input.

**Why split the night rather than finish one.** Neither has ever run, so neither
has a measured throughput, and committing the whole window to the first one
risks waking up to one attribute done and the other still at zero. Both are
resumable and idempotent, so a half-finished pass is progress, not waste. The
split is deliberately uneven — Forthrightness has ~3.5x the calls.

Nothing is spent before `--at`. The wait is a sleep, not a poll.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# Fraction of the night each stage gets. Forthrightness first and larger: it is
# the attribute the card is missing entirely, and 924 calls will not fit.
PLAN = (("questions", 0.6), ("positions", 0.4))


def _next(hhmm: str, after: dt.datetime | None = None) -> dt.datetime:
    after = after or dt.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    target = after.replace(hour=h, minute=m, second=0, microsecond=0)
    return target + dt.timedelta(days=1) if target <= after else target


def run(at: str = "23:00", until: str = "06:00", model: str | None = None) -> None:
    """Sleep until `at`, then run each stage for its share of the window."""
    start = _next(at)
    stop = _next(until, after=start)
    hours = (stop - start).total_seconds() / 3600

    print(f"scheduled: {start:%Y-%m-%d %H:%M} -> {stop:%H:%M}  ({hours:.2f}h)",
          flush=True)
    for stage, share in PLAN:
        print(f"  {stage:10s} {hours * share:.2f}h", flush=True)
    print(f"sleeping {(start - dt.datetime.now()).total_seconds() / 3600:.2f}h "
          f"— NO subscription quota is used until then", flush=True)

    while True:
        left = (start - dt.datetime.now()).total_seconds()
        if left <= 0:
            break
        time.sleep(min(3600, left))
        left = (start - dt.datetime.now()).total_seconds()
        if left > 0:
            print(f"  {left / 3600:.1f}h until start", flush=True)

    for stage, share in PLAN:
        # Recompute from the real clock each time, so a stage that finishes
        # early hands its remaining time to the next one instead of idling.
        remaining = (stop - dt.datetime.now()).total_seconds() / 3600
        if remaining <= 0.1:
            print(f"\n=== out of time before {stage} — skipped ===", flush=True)
            break
        budget = min(hours * share, remaining)
        print(f"\n=== {dt.datetime.now():%H:%M} — {stage} "
              f"({budget:.2f}h budget) ===", flush=True)
        cmd = [PY, "overnight_run.py", "run", "--hours", f"{budget:.2f}",
               "--stage", stage]
        if model:
            cmd += ["--model", model]
        subprocess.run(cmd, cwd=HERE, env={**os.environ, "PYTHONUNBUFFERED": "1"})

    print(f"\n=== {dt.datetime.now():%H:%M} — night finished ===", flush=True)
    subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)


def status(at: str = "23:00") -> None:
    """What is scheduled and what exists so far. Spends nothing."""
    now = dt.datetime.now()
    start = _next(at)
    print(f"now         {now:%H:%M}")
    print(f"next start  {start:%Y-%m-%d %H:%M} "
          f"(in {(start - now).total_seconds() / 3600:.1f}h)")
    subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)


if __name__ == "__main__":
    fire.Fire({"run": run, "status": status})
