"""Run the two remaining v3.0 extractions overnight, in sequence.

    cd attribute-extraction
    nohup python tonight.py run --at 23:00 --until 06:00 > tonight.log 2>&1 &
    python tonight.py status

Runs the remaining v3.0 LLM work in order, each stage taking the whole window
until it finishes or the night ends. See PLAN below for what is queued and why.

Everything here is resumable and idempotent, so a half-finished stage is
progress rather than waste, and a stage that is already complete exits in
seconds (EX_DONE) instead of spinning.

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

# Stages in order. Each gets ALL the remaining time and hands over what it does
# not use.
#
# The first version split the night by fixed shares, which was the right hedge
# when neither stage had a measured throughput. It is the wrong shape now, for
# two reasons learnt on 2026-08-13: a share is a cap even when the stage could
# have finished, and — the expensive one — the quota ran out mid-night and the
# second stage ground through 780 calls that could not succeed. Now that
# `claude_cli.QuotaExhausted` aborts a pass immediately, a stage that cannot
# run costs seconds rather than hours, so sequential-until-done is strictly
# better than rationing.
#
# Updated 2026-08-15, after Strength and Authenticity were deferred to v4. The
# `positions` stage extracted exactly what those two consumed, so it is dropped
# — running it now would spend a night producing input for attributes nobody
# will publish.
#
# `questions` first: Forthrightness is the worst-covered live attribute (25% of
# cards) with 569 calls left. It did NO work on 2026-08-15 -- the runner compared
# a row count to a call count and declared itself finished -- so this is its
# first real night.
# `resolve_veracity` second: divination is fully resolved (110/110, all with
# source URLs). Veracity has 1,028 pending after 2026-08-16, and each call does
# several web round-trips, so it is slow — measured at roughly 27 calls in the
# ~2h of usable quota that night. It will take several nights.
#
# The loop below is a ROUND-ROBIN, not one pass per stage: the usage cap
# recovers within a night, and a stage blocked at midnight must still be there
# to use quota that returns at 3am.
PLAN = ("questions", "resolve_veracity")


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
    print(f"  stages, in order: {' -> '.join(PLAN)}", flush=True)
    print("  each runs until it finishes or the window closes", flush=True)
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

    # Round-robin, not one pass each. A stage blocked by the usage cap early in
    # the night must get another turn when the cap recovers — on 2026-08-16
    # Forthrightness was locked out at 00:14 and quota came back at ~03:00, but
    # the plan had already moved on and never returned to it.
    done: set = set()
    round_no = 0
    while (stop - dt.datetime.now()).total_seconds() / 3600 > 0.1:
        round_no += 1
        progressed = False
        for stage in PLAN:
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
            if code == 64:
                # Nothing left in this stage, ever. Do not offer it another turn.
                print(f"  {stage} is complete — dropping it from the rotation",
                      flush=True)
                done.add(stage)
            else:
                progressed = True
        if len(done) == len(PLAN):
            print("\nall stages complete", flush=True)
            break
        if not progressed:
            print("\nno stage can make progress — ending the night", flush=True)
            break

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
