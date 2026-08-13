"""Sleep until a wall-clock time, then run the overnight extraction.

    cd attribute-extraction
    nohup python start_at.py run --at 00:00 --until 06:00 > scheduled.log 2>&1 &
    python start_at.py status

Why this exists rather than `at` or cron: the run needs a *window*, not just a
start. `--at` is when it may first touch the subscription and `--until` is its
hard stop, and the second is passed through as `overnight_run.py --hours`, so
the deadline is computed from the real start rather than assumed.

**It spends nothing while waiting.** No CLI call is made until `--at` passes;
until then the process is asleep. That is the whole point — the extraction is
resumable and idempotent, so the cost of waiting is zero, but the cost of
starting early is real subscription quota.

Both times are local, in HH:MM. A time already past today means tomorrow.
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


def _next(hhmm: str, after: dt.datetime | None = None) -> dt.datetime:
    """The next occurrence of HH:MM strictly after `after` (default: now)."""
    after = after or dt.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    target = after.replace(hour=h, minute=m, second=0, microsecond=0)
    return target + dt.timedelta(days=1) if target <= after else target


def run(at: str = "00:00", until: str = "06:00", stage: str = "all",
        model: str | None = None) -> None:
    """Wait until `at`, then extract until `until`."""
    start = _next(at)
    stop = _next(until, after=start)
    hours = (stop - start).total_seconds() / 3600
    wait = (start - dt.datetime.now()).total_seconds()

    print(f"scheduled: start {start:%Y-%m-%d %H:%M}  stop {stop:%Y-%m-%d %H:%M}"
          f"  ({hours:.2f}h of extraction)", flush=True)
    print(f"sleeping {wait / 3600:.2f}h — NO subscription quota is used until "
          f"then", flush=True)

    while True:
        remaining = (start - dt.datetime.now()).total_seconds()
        if remaining <= 0:
            break
        # Wake hourly to log, so a long wait is visibly alive rather than hung.
        time.sleep(min(3600, remaining))
        left = (start - dt.datetime.now()).total_seconds()
        if left > 0:
            print(f"  {left / 3600:.1f}h until start", flush=True)

    print(f"\n=== {dt.datetime.now():%H:%M} — starting extraction "
          f"({hours:.2f}h budget) ===", flush=True)
    cmd = [PY, "overnight_run.py", "run", "--hours", f"{hours:.2f}",
           "--stage", stage]
    if model:
        cmd += ["--model", model]
    subprocess.run(cmd, cwd=HERE, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    print(f"=== {dt.datetime.now():%H:%M} — scheduled run finished ===",
          flush=True)


def status(at: str = "00:00", until: str = "06:00") -> None:
    """What is scheduled, and what the extraction has produced so far."""
    start = _next(at)
    now = dt.datetime.now()
    print(f"now            {now:%H:%M}")
    print(f"next start     {start:%Y-%m-%d %H:%M}  "
          f"(in {(start - now).total_seconds() / 3600:.1f}h)")
    subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)


if __name__ == "__main__":
    fire.Fire({"run": run, "status": status})
