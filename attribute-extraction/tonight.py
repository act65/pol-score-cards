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

# "This stage is broken" — it exited non-zero having written nothing. Unlike
# EX_DONE it is not remembered across nights (tomorrow's code may be fixed), but
# it must leave the rotation NOW: on 2026-08-25/26 a stage that crashed instantly
# was retried every round for two whole nights and starved the stage that worked.
EX_FAIL = 70

# How long one stage may hold the night before the rotation moves on.
#
# Without this the rotation did not rotate. `overnight_run run --hours H` loops
# internally until H is up, so the FIRST stage in the plan owned the whole night
# unless it finished or crashed — and a quota-blocked stage just napped through
# it. Measured on 2026-08-29: quota died at 00:01, ab_prompt backed off 75
# minutes three times, and `windows` never ran at all. It is also why
# `questions` and `resolve_veracity` had no turn in thirteen nights.
#
# Every stage is resumable and idempotent, so being cut off mid-slice costs
# nothing but the tail of one call. overnight_run's own backoff is already
# clamped to its deadline, so a blocked stage yields at the end of its slice
# rather than sleeping past it.
TURN_HOURS = 1.0


# Nightly default. `pilot` is NOT in it: the 2025-10 month is complete at
# window_tokens=3000 (260 windows, 3,703 examples) and audited, so re-running it
# would only spend quota re-deriving numbers we have. It was briefly first in
# this list while the 14,000-token window was under test; that test concluded on
# 2026-08-18 in favour of 3k (see overnight_run.WINDOW_TOKENS for the numbers).
#
# `windows` is the long pole and takes the whole night. `questions` and
# `resolve_veracity` are in the rotation so a night where the extraction is
# quota-blocked still advances something rather than idling.
#
# A stage that finishes reports EX_DONE and drops out, so this list winds down
# to nothing on its own.
# `ab_prompt` leads for one night only: it is ~24 calls (about 1% of a night's
# quota) and decides whether the remaining ~4,930 windows can be extracted at
# roughly double the current rate. Deciding that before spending 70 more nights
# at the current rate is worth an hour. It reports EX_DONE and drops out.
# `ab_prompt` is done (2026-09-01) and its answer is adopted — see AB_PROMPT.md
# and overnight_run.SYSTEM_PROMPT_FLAG. It is out of the rotation; re-add it by
# name only if the prompt arrangement is questioned again.
# `resolve_veracity` was PULLED on 2026-09-08. It could not converge: at 1,235
# of 5,548 windows the pool already held 5,588 pending claims against 389
# resolved. Extraction emits ~4.5 claims per window (~425 a night) and the
# resolver cleared ~58 a night, so the backlog grew about 7x faster than it
# drained — the full term is ~25,000 claims, or ~430 nights — while taking 22%
# of each night's output budget (256 s/call, and 20% of what it returned was
# not_yet_due/uncheckable, which by design carry no score).
#
# It was also not accumulating a usable sample: it works in extraction order,
# so 371 of its 389 resolved claims came from one month (2025-10) out of seven.
# A stratified sample drawn from the FINISHED pool is unbiased, which a
# chronological pass can never be. So: finish extraction first, then resolve a
# designed sample. resolve.py is unchanged and the 389 resolved rows are kept.
# Re-add by name (`--stages windows,questions,resolve_veracity`) to resume it.
#
# Both entry points read this one list. They used to differ — `run` carried a
# two-stage PLAN from the era when `windows` owned the whole night — and on
# 2026-09-06 that silently started a night with no window extraction in it.
NIGHTLY_PLAN = ("windows", "questions")


def _next(hhmm: str, after: dt.datetime | None = None) -> dt.datetime:
    """The next occurrence of HH:MM strictly after `after` (default: now)."""
    after = after or dt.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    target = after.replace(hour=h, minute=m, second=0, microsecond=0)
    return target + dt.timedelta(days=1) if target <= after else target


def _window_now(at: str, until: str, now: dt.datetime = None) -> tuple:
    """(start, stop) for the window to work, joining one already in progress.

    `_next` alone forfeits a whole night if the scheduler starts a minute late.
    That happened on 2026-09-17: the machine booted at 23:09, nine minutes into
    a 23:00-06:00 window, so `_next("23:00")` returned TOMORROW and it slept
    23.85h with 6.8 usable hours sitting right there.

    So if we are inside a window right now, start now and keep its real end.
    Handles the midnight wrap, where `until` is earlier in the day than `at`.
    """
    now = now or dt.datetime.now()
    todays_at = now.replace(hour=int(at.split(":")[0]),
                            minute=int(at.split(":")[1]),
                            second=0, microsecond=0)
    for begin in (todays_at, todays_at - dt.timedelta(days=1)):
        end = _next(until, after=begin)
        if begin <= now < end:
            return now, end
    start = _next(at, after=now)
    return start, _next(until, after=start)


def _sleep_until(start: dt.datetime) -> None:
    """Sleep to `start`, waking hourly to log so a long wait looks alive."""
    wait = (start - dt.datetime.now()).total_seconds()
    if wait <= 0:
        return                    # already inside the window; joined late
    print(f"sleeping {wait / 3600:.2f}h "
          f"— NO subscription quota is used until then", flush=True)
    while True:
        left = (start - dt.datetime.now()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(3600, left))
        left = (start - dt.datetime.now()).total_seconds()
        if left > 0:
            print(f"  {left / 3600:.1f}h until start", flush=True)
        elif left < -300:
            # Night 4 (2026-08-22) woke at 07:29 for a 00:00 window and lost the
            # whole night in silence. time.sleep() tracks elapsed time, not wall
            # clock, so a suspended laptop overshoots. Say so, rather than
            # printing "night finished" over an empty run.
            print(f"  OVERSHOT the start by {-left / 3600:.1f}h — the machine was "
                  f"probably suspended. This night's window is gone.", flush=True)


def _one_night(stop: dt.datetime, plan, model, done: set) -> set:
    """Rotate through `plan` until `stop`. Returns the set of finished stages."""
    round_no = 0
    broken: set = set()          # failing tonight; retried tomorrow
    while (stop - dt.datetime.now()).total_seconds() / 3600 > 0.1:
        round_no += 1
        progressed = False
        for stage in plan:
            if stage in done or stage in broken:
                continue
            remaining = (stop - dt.datetime.now()).total_seconds() / 3600
            if remaining <= 0.1:
                break
            turn = min(remaining, TURN_HOURS)
            print(f"\n=== {dt.datetime.now():%H:%M} — {stage} "
                  f"(round {round_no}, {turn:.2f}h slice, {remaining:.2f}h "
                  f"left in the night) ===", flush=True)
            cmd = [PY, "overnight_run.py", "run", "--hours", f"{turn:.2f}",
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
            elif code == EX_FAIL:
                print(f"  {stage} is FAILING — out of the rotation for tonight "
                      f"so it stops starving the stages that work", flush=True)
                broken.add(stage)
            else:
                progressed = True
        if len(done) == len(plan):
            print("\nall stages complete", flush=True)
            break
        if len(done | broken) == len(plan):
            print("\nevery stage is finished or failing — ending the night",
                  flush=True)
            break
        if not progressed:
            print("\nno stage can make progress — ending the night", flush=True)
            break
    return done


def run(at: str = "23:00", until: str = "06:00", model: str | None = None,
        stages: str = "") -> None:
    """Wait until `at`, then work the plan until `until`. One night only."""
    plan = tuple(s.strip() for s in stages.split(",") if s.strip()) or NIGHTLY_PLAN
    start, stop = _window_now(at, until)

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
        start, stop = _window_now(at, until)
        joined = "" if start.strftime("%H:%M") == at else "  (joined late)"
        print(f"\n########## night {night}: {start:%Y-%m-%d %H:%M} -> "
              f"{stop:%H:%M} ##########{joined}", flush=True)
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
