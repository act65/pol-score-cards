"""Run the two v3.0 experiments overnight, patiently, on the subscription.

    cd attribute-extraction
    nohup python run_experiments.py run > experiments.log 2>&1 &
    python run_experiments.py status          # progress; spends nothing

Two experiments, run **one after the other** rather than at once:

  1. `compare_models.py` — can a cheaper model reproduce Opus 5?
  2. `resolve.py`        — does searching for evidence beat guessing?

**Sequential on purpose.** Both go through `claude -p`, which authenticates with
the subscription. Past roughly two concurrent CLI sessions the calls start
queueing behind each other and a batch that would take minutes appears to hang —
a 6-worker run managed 9 calls in 15 minutes and then stalled completely. Low
concurrency is faster here, not slower.

**Everything is resumable.** Both tools append each completed call to disk
immediately and skip what is already done on restart, so a kill, a session cap
or a laptop sleep costs at most the calls in flight.

**Backs off instead of hammering.** When a pass makes no progress that is almost
always the subscription's session cap, so it waits an hour and tries again. It
is meant to take all night; that is cheaper than failing fast and losing the
partial work.

Nothing here touches the API — no dollars, only subscription quota.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

BAKEOFF_PARTIAL = os.path.join(HERE, "model_comparison.partial.jsonl")
BAKEOFF_OUT = os.path.join(HERE, "model_comparison.json")
RESOLVED = os.path.join(HERE, "resolved_v3.jsonl")

# Deliberately small. The question each answers is qualitative — "is the cheap
# model close enough", "does searching change the answer" — and neither needs a
# large n to be informative at this stage.
WINDOWS, REPEATS = 3, 2
MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8")
BAKEOFF_TARGET = WINDOWS * REPEATS * len(MODELS)      # 18 calls
RESOLVE_TARGET = 18

WORKERS = 2                 # more than this and the CLI sessions queue
BACKOFF = 60 * 60           # session-cap wait
PASS_TIMEOUT = 90 * 60      # cap one pass so a hung call cannot eat the night


def _count(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return sum(1 for line in f if line.strip())


def _run(cmd: list, timeout: float) -> None:
    try:
        subprocess.run(cmd, cwd=HERE, timeout=max(60, timeout))
    except subprocess.TimeoutExpired:
        print("  pass hit its timeout — stopping cleanly (resumable)", flush=True)


def _stage(name: str, cmd: list, counter, target: int, deadline: float) -> None:
    """Run one experiment to completion, backing off when it stops progressing."""
    print(f"\n=== {name}: starting at {counter()}/{target} ===", flush=True)
    while counter() < target and time.time() < deadline:
        before = counter()
        _run(cmd, min(PASS_TIMEOUT, deadline - time.time()))
        after = counter()
        left = (deadline - time.time()) / 3600
        print(f"[{name}] {after}/{target} (+{after - before} this pass, "
              f"{left:.1f}h left)", flush=True)
        if after >= target or time.time() >= deadline:
            break
        if after == before:
            nap = min(BACKOFF, max(0, deadline - time.time()))
            if nap <= 0:
                break
            print(f"  no progress — almost certainly the session cap. "
                  f"Waiting {nap / 60:.0f} min.", flush=True)
            time.sleep(nap)
        else:
            time.sleep(30)
    print(f"=== {name}: finished at {counter()}/{target} ===", flush=True)


def _assemble_bakeoff() -> None:
    """Build the report input from whatever calls completed."""
    if not os.path.exists(BAKEOFF_PARTIAL):
        return
    with open(BAKEOFF_PARTIAL) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if not rows:
        return
    with open(BAKEOFF_OUT, "w") as f:
        json.dump({"models": sorted({r["model"] for r in rows}),
                   "reference": "claude-opus-5", "month": "2024-11",
                   "results": rows}, f, indent=1)


def run(hours: float = 14.0) -> None:
    """Run both experiments, then write both reports."""
    deadline = time.time() + hours * 3600
    print(f"=== v3.0 experiments: up to {hours}h, subscription backend "
          f"(no API $), {WORKERS} workers ===", flush=True)

    # 1. Model bake-off. Opus 5 is the reference; the others are judged on how
    #    faithfully they reproduce it.
    _stage("bake-off",
           [PY, "compare_models.py", "run",
            "--windows", str(WINDOWS), "--repeats", str(REPEATS),
            "--workers", str(WORKERS), "--window_tokens", "3000",
            "--backend", "claude_cli",
            "--models", ",".join(m for m in MODELS if m != "claude-opus-5")],
           lambda: _count(BAKEOFF_PARTIAL), BAKEOFF_TARGET, deadline)
    _assemble_bakeoff()

    # 2. Guess vs search. Reuses the claims the bake-off already extracted, so
    #    it costs no extra extraction — only the resolver's searches.
    if os.path.exists(BAKEOFF_OUT):
        _stage("resolver",
               [PY, "resolve.py", "run", "--scores", "model_comparison.json",
                "--limit", str(RESOLVE_TARGET), "--per_call", "1",
                "--workers", str(WORKERS), "--timeout", "420"],
               lambda: _count(RESOLVED), RESOLVE_TARGET, deadline)

    print("\n=== reports ===", flush=True)
    if _count(BAKEOFF_PARTIAL):
        _assemble_bakeoff()
        subprocess.run([PY, "compare_models.py", "report",
                        "--out", "MODEL_COMPARISON.md"], cwd=HERE)
    if _count(RESOLVED):
        subprocess.run([PY, "resolve.py", "compare",
                        "--out", "GUESS_VS_SEARCH.md"], cwd=HERE)
    status()
    print("\nNo API credits were used — everything ran on the subscription via "
          "`claude -p`. Both experiments are resumable: re-run this script and "
          "it continues from what is already on disk.", flush=True)


def status() -> None:
    """Progress on both experiments. Spends nothing."""
    b, r = _count(BAKEOFF_PARTIAL), _count(RESOLVED)
    print(f"\nbake-off : {b}/{BAKEOFF_TARGET} calls   ({BAKEOFF_PARTIAL})")
    print(f"resolver : {r}/{RESOLVE_TARGET} verdicts ({RESOLVED})")
    for name in ("MODEL_COMPARISON.md", "GUESS_VS_SEARCH.md"):
        p = os.path.join(HERE, name)
        print(f"{name}: {'written' if os.path.exists(p) else 'not yet'}")


if __name__ == "__main__":
    fire.Fire({"run": run, "status": status})
