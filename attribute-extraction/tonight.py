"""Schedule the overnight v3.0 extraction work.

    cd attribute-extraction
    # one night
    nohup python tonight.py run --at 23:00 --until 06:00 > tonight.log 2>&1 &
    # every night until the work is finished
    nohup python tonight.py nightly --at 00:00 --until 04:00 > nightly.log 2>&1 &
    python tonight.py status

Everything here is resumable and idempotent, so a half-finished stage is
progress rather than waste, and a finished stage exits in seconds (EX_DONE)
instead of spinning.

**Nothing is spent before `--at`.** The wait is a sleep, not a poll.

## Why the night is a rotation, not a queue

The subscription cap is a *rolling* window that recovers in roughly 2-3 hours,
not a nightly ceiling. Measured on 2026-08-16: Forthrightness ran hard from
23:00, hit the cap at 00:14, and the old one-turn-each plan moved on and never
came back — while quota returned at about 03:00 and was spent by a slower stage.

So each stage runs until it finishes or the window closes, and the plan rotates:
a stage blocked at midnight is still in the rotation when quota returns at 3am.
A stage that reports EX_DONE is dropped for good.
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

# Exit code a runner uses for "my todo list is empty" (see overnight_run.py).
EX_DONE = 64

# Single-night default: finish Forthrightness, then resolve veracity.
PLAN = ("questions", "resolve_veracity")

# Nightly default. `pilot` leads: after the switch to 14,000-token windows on
# 2026-08-17 the instrument is unvalidated, and re-running the SAME month
# (2025-10, 51 windows at 14k against 260 at 3k) is the only comparison that
# isolates window size from everything else. It ends by writing both audits, so
# one night gives a like-for-like read against pilot_3k/.
#
# `windows` is the long pole and takes the whole night once the pilot is done.
# `questions` and `resolve_veracity` are in the rotation so a night where the
# extraction is quota-blocked still advances something rather than idling.
#
# A stage that finishes reports EX_DONE and drops out, so this list winds down
# to nothing on its own.
NIGHTLY_PLAN = ("pilot", "windows", "questions", "resolve_veracity")


def _next(hhmm: str, after: dt.datetime | None = None) -> dt.datetime:
    """The next occurrence of HH:MM strictly after `after` (default: now)."""
    after = after or dt.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    target = after.replace(hour=h, minute=m, second=0, microsecond=0)
    return target + dt.timedelta(days=1) if target <= after else target


def _sleep_until(start: dt.datetime) -> None:
    """Sleep to `start`, waking hourly to log so a long wait looks alive."""
    print(f"sleeping {(start - dt.datetime.now()).total_seconds() / 3600:.2f}h "
          f"— NO subscription quota is used until then", flush=True)
    while True:
        left = (start - dt.datetime.now()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(3600, left))
        left = (start - dt.datetime.now()).total_seconds()
        if left > 0:
            print(f"  {left / 3600:.1f}h until start", flush=True)


def _one_night(stop: dt.datetime, plan, model, done: set) -> set:
    """Rotate through `plan` until `stop`. Returns the set of finished stages."""
    round_no = 0
    while (stop - dt.datetime.now()).total_seconds() / 3600 > 0.1:
        round_no += 1
        progressed = False
        for stage in plan:
            if stage in done:
                continue
            remaining = (stop - dt.datetime.now()).total_seconds() / 3600
            if remaining <= 0.1:
                break
            print(f"\n=== {dt.datetime.now():%H:%M} — {stage} "
                  f"(round {round_no}, {remaining:.2f}h left) ===", flush=True)
            cmd = [PY, "overnight_run.py", "run", "--hours", f"{remaining:.2f}",
                   "--stage", stage]
            if model:
                cmd += ["--model", model]
            code = subprocess.run(
                cmd, cwd=HERE,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}).returncode
            if code == EX_DONE:
                print(f"  {stage} is complete — dropping it from the rotation",
                      flush=True)
                done.add(stage)
            else:
                progressed = True
        if len(done) == len(plan):
            print("\nall stages complete", flush=True)
            break
        if not progressed:
            print("\nno stage can make progress — ending the night", flush=True)
            break
    return done


def run(at: str = "23:00", until: str = "06:00", model: str | None = None,
        stages: str = "") -> None:
    """Wait until `at`, then work the plan until `until`. One night only."""
    plan = tuple(s.strip() for s in stages.split(",") if s.strip()) or PLAN
    start = _next(at)
    stop = _next(until, after=start)

    print(f"scheduled: {start:%Y-%m-%d %H:%M} -> {stop:%H:%M}  "
          f"({(stop - start).total_seconds() / 3600:.2f}h)", flush=True)
    print(f"  stages, rotating: {' -> '.join(plan)}", flush=True)
    _sleep_until(start)
    _one_night(stop, plan, model, set())

    print(f"\n=== {dt.datetime.now():%H:%M} — night finished ===", flush=True)
    subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)


def nightly(at: str = "00:00", until: str = "04:00", model: str | None = None,
            stages: str = "", max_nights: int = 0) -> None:
    """Work the plan in the same window EVERY night until it is finished.

    Stages that report completion are remembered across nights and are not
    started again, so the run winds down on its own rather than needing to be
    stopped by hand. It exits when every stage is done.

    `--max_nights` caps the number of nights (0 = until finished).
    """
    plan = tuple(s.strip() for s in stages.split(",") if s.strip()) or NIGHTLY_PLAN
    done: set = set()
    night = 0

    print(f"nightly schedule: {at} -> {until}, every night until finished",
          flush=True)
    print(f"  stages, rotating: {' -> '.join(plan)}", flush=True)

    while not max_nights or night < max_nights:
        night += 1
        start = _next(at)
        stop = _next(until, after=start)
        print(f"\n########## night {night}: {start:%Y-%m-%d %H:%M} -> "
              f"{stop:%H:%M} ##########", flush=True)
        _sleep_until(start)
        done = _one_night(stop, plan, model, done)

        print(f"\n=== {dt.datetime.now():%H:%M} — night {night} finished "
              f"({len(done)}/{len(plan)} stages complete) ===", flush=True)
        subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)

        if len(done) == len(plan):
            print(f"\n########## all stages finished after {night} night(s) "
                  f"##########", flush=True)
            return


def status(at: str = "00:00") -> None:
    """What is scheduled and what exists so far. Spends nothing."""
    now = dt.datetime.now()
    start = _next(at)
    print(f"now         {now:%H:%M}")
    print(f"next start  {start:%Y-%m-%d %H:%M} "
          f"(in {(start - now).total_seconds() / 3600:.1f}h)")
    subprocess.run([PY, "overnight_run.py", "status"], cwd=HERE)


if __name__ == "__main__":
    fire.Fire({"run": run, "nightly": nightly, "status": status})
