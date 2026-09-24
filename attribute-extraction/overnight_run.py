"""Time-bounded overnight v3.0 extraction.

Resumes the extraction (skipping windows already done), runs for at most
MAX_HOURS, then stops itself and reports. Designed so it cannot run past the
time budget it was given, and so killing it at any moment loses nothing.

    cd attribute-extraction
    python overnight_run.py --hours 10 --stage pilot      # 2025-10 only, start here
    nohup python overnight_run.py --hours 10 > overnight.log 2>&1 &
    python overnight_run.py --status                      # progress, no work done

Three stages, in the order they should be run:

  pilot     2025-10 only (~40 windows). Cheap. Run this first, read the gate
            report, and only continue if the quotes and firing rates look right.
  windows   the full term — the four text-only attributes scored, plus veracity
            and divination extracted as resolver candidates.
  questions Forthrightness over Hansard oral Q/A pairs (~920 calls).

**It deliberately does NOT publish.** v3.0 scores are not comparable with v2.0 —
Civility was re-anchored and Charisma was replaced by Focus — so the site must
not be refreshed until the evaluation pass has run. Publishing is a separate,
manual step after labelling.

Written parliamentary questions are NOT included by default: 85,136 distinct
(template, minister) pairs is ~7,100 calls, several times the whole Hansard run.
Run `extract_questions.py run --source written` explicitly if you want them.
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

# v3.0 output. Deliberately a NEW file: the v2.0 scores used a different
# Civility scale and a retired attribute, so appending to them would silently
# blend two instruments.
SCORES = "hansard_scores_v3.jsonl"
POSITIONS = "positions_v3.jsonl"
RESOLVED = "resolved_v3.jsonl"
QA_SCORES = "forthrightness_scores_v3.jsonl"

# Per-call token accounting (claude_cli._record_usage). The subscription cap is
# what limits this project, and until now we only ever saw it indirectly — as
# the point in the night where calls started failing. This records what each
# call actually cost, including whether the 7,469-token system prompt is being
# cache-read or billed in full, which decides whether the window size or the
# repeated rubric is the thing worth fixing. Costs nothing: the numbers are
# already in the response envelope.
USAGE_LOG = os.path.join(HERE, "usage_v3.jsonl")

# Pass the rubric as --system-prompt rather than prepending it to the user
# message. Adopted 2026-09-01 on the ab_prompt.py A/B (see AB_PROMPT.md):
# 24% cheaper per call at list weighting and 22% faster, from -21% output and
# -32% cache writes, because it replaces the CLI's own 20.6k-token default
# prompt (which extraction never uses) with a genuinely reusable prefix.
#
# Adopted only because it measures the SAME. Statement selection agrees with
# arm A at 0.40 while the corpus prompt agrees with ITSELF at only 0.38, score
# correlation is r=0.96 on shared statements, and yield is 94% against ±17%
# run-to-run variation. Set SYSTEM_PROMPT_FLAG = "0" to revert.
SYSTEM_PROMPT_FLAG = "1"

# A ceiling WE put on ourselves, so the overnight run cannot take the whole
# rolling window and leave nothing for daytime work. It is not a quota reading:
# the real cap is readable from nowhere and is shared with interactive sessions
# that never touch our log. See quota_budget.py; edit the dollar figures in
# quota_budget.json. Hitting it raises QuotaExhausted, so the night stops
# exactly the way a real quota block stops it, and the message says which.
BUDGET_CONFIG = os.path.join(HERE, "quota_budget.json")

SINCE = "2023-10-06"
PILOT_MONTH = "2025-10"

# Window size and call timeout are COUPLED — set them together or the run dies
# silently. Measured on the subscription CLI: a 3k-token window returns in
# ~150s, while a 14k-token one does not finish inside claude_cli's old 300s
# default at all. The first v3.0 launch used 14k windows, so every call timed
# out, retried twice and failed; the run looked healthy and produced nothing
# for 20 minutes before it was caught.
#
# 3k is the ONLY size measured to complete reliably: the model bake-off ran 18
# calls at 3k in ~150s each. Cost does not scale linearly with window size —
# a bigger window means more statements to emit, so output grows too. Measured
# on this corpus with Opus 5 via the CLI:
#     3k tokens (~12k chars)  ->  ~150s      reliable
#     6k tokens (~24k chars)  ->  >400s      no window landed in 7 min
#    14k tokens (~56k chars)  ->  >600s      exceeded the old 300s default, so
#                                            every call timed out and the run
#                                            produced nothing while looking fine
#
# Smaller windows mean more calls, but a call that finishes beats a bigger one
# that does not. The timeout is set well above the measured time so a slow call
# waits rather than failing.
# 3,000 — reverted on 2026-08-18 after one night at 14,000 was measured
# against the archived 3k month (pilot_3k/ vs pilot_14k/, same six sitting days
# of 2025-10 scored both ways).
#
# The case for 14k was token overhead: every call resends the 7,469-token system
# prompt, so 5,548 calls carry 41.4M tokens of repeated rubric against 13.9M of
# actual debate, while 1,127 calls carry only 8.4M. That arithmetic is right and
# still true. It is simply outweighed:
#
#   * RECALL. 14k returned 1,045 examples where 3k returned 2,381 on the same
#     days — 44%, and between 0.42 and 0.52 on every individual day. Content
#     input is identical either way (13.90M tokens at both sizes, per --dry_run),
#     so this is the same spend for less than half the evidence: 2.35 examples
#     per 1,000 window tokens against 4.7.
#   * COVERAGE. Rebuilding each window and locating every quote inside it, 3k
#     draws uniformly (20.0/21.0/18.8/19.6/20.7% across window fifths,
#     chi2(4)=5.7, p=0.22). 14k front-loads: 27.1% from the first fifth, 15.9%
#     from the fourth, chi2(4)=49.5, p<1e-9. The model stops reading evenly well
#     before 14k tokens.
#   * STABILITY. Card scores are not window-size invariant — r=0.77 across 57
#     MP-attribute cells with >=4 scores in both runs, 10 moving by more than
#     0.15. Focus was worst hit (30% recall, mean 0.74 -> 0.60), which is the
#     attribute a whole-debate window was most supposed to help.
#
# 14k did halve multi-attribute double-counting (26% -> 19%), but both sizes are
# far inside the <60% target, so that buys nothing we needed.
#
# Not a prompt bug: the preamble says "find EACH statement that bears on any
# attribute", with no cap and no notability filter. It is the model's behaviour
# over long context. Raising this again needs new evidence, not new reasoning.
#
# CALL_TIMEOUT stays at 900s. It only has to exceed the ~150s a 3k window takes,
# and a slow call should wait rather than fail.
WINDOW_TOKENS = "3000"
CALL_TIMEOUT = "900"

# Two settings the 2026-08-07 experiments decided:
#
#   MODEL   — `compare_models.py` treated Opus 5 as ground truth and neither
#             cheaper model reproduced it. Sonnet 5 surfaced only 33% of the
#             same statements (Opus 4.8, 50%), both under the 0.6 bar. Where
#             they overlapped they agreed well (r 0.88-0.93), so the problem is
#             WHICH statements get extracted, not how they are scored — a cheap
#             model yields a different dataset, not a cheaper one.
#   WORKERS — the subscription CLI queues above ~2 concurrent sessions. Six
#             workers managed 9 calls then stalled dead; two is genuinely
#             faster. See MODEL_COMPARISON.md and the memory note.
MODEL = "claude-opus-5"
WORKERS = "2"
BACKEND = "claude_cli"

# Session-cap backoff. Was 75 min, chosen when a stage owned the whole night and
# re-entering cost real calls. Both premises are gone: a blocked pass now aborts
# in seconds (QuotaExhausted), and tonight.py hands each stage a bounded slice,
# so the waiting is done by the rotation rather than by sleeping here. A shorter
# nap just means quota recovery is noticed sooner.
BACKOFF = 20 * 60
SHORT_SLEEP = 60


def _count(path: str) -> int:
    p = os.path.join(HERE, path)
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _plan_size(stage: str, model: str, backend: str) -> int:
    """Ask the extractor how many windows the stage contains, without spending.

    Every stage must be asked about *itself*. This defaulted to the window plan
    for anything that was not `pilot`, so the positions run reported "0/5,548"
    — the Q/A pair count — against a real target of 260.
    """
    if stage == "questions":
        cmd = [PY, "extract_questions.py", "run", "--dry_run",
               "--source", "oral", "--out", QA_SCORES]
        try:
            proc = subprocess.run(cmd, cwd=HERE, capture_output=True,
                                  text=True, timeout=300)
            for line in proc.stdout.splitlines():
                if "calls:" in line:
                    return int(line.split("calls:")[1].split()[0].replace(",", ""))
        except Exception:  # noqa: BLE001
            pass
        return 0

    pilot_scope = stage in ("pilot", "positions")
    cmd = [PY, "extract_hansard.py", "--dry_run",
           "--attrs", "positions" if stage == "positions" else "scores",
           "--since", f"{PILOT_MONTH}-01" if pilot_scope else SINCE,
           "--until", PILOT_MONTH if pilot_scope else "",
           "--window_tokens", WINDOW_TOKENS, "--model", model,
           "--backend", backend]
    try:
        proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                              timeout=300)
        for line in proc.stdout.splitlines():
            if "windows (=API calls):" in line:
                return int(line.split("windows (=API calls):")[1].split()[0])
    except Exception:  # noqa: BLE001
        pass
    return 0


# Exit code a runner uses for "the subscription window is spent". Distinct from
# an ordinary failure because the response is different: waiting may help,
# retrying immediately never does.
EX_QUOTA = 75

# "My todo list is empty" — the stage is genuinely finished. The runner is the
# only thing that knows this reliably: overnight_run counts OUTPUT ROWS, while a
# stage's work is measured in CALLS, and comparing the two silently broke both
# stages on 2026-08-15.
EX_DONE = 64

# How many blocked passes before a stage gives up for the night. With BACKOFF at
# 75 min this spans roughly the whole window, which is what we want: the usage
# cap recovers in ~2-3h and the stage should still be there when it does.
QUOTA_STRIKES = 5

# "This stage is broken." Distinct from EX_QUOTA (blocked, worth waiting for)
# and EX_DONE (finished, drop it for good). The scheduler drops a broken stage
# for the rest of the night so it stops blocking stages that still work.
EX_FAIL = 70


def _pass(stage: str, timeout_s: float, model: str, backend: str) -> int:
    """One resumable pass, hard-capped so it cannot outlive the deadline.

    Returns the runner's exit code, so the caller can tell a stage that failed
    from one that is merely blocked.
    """
    if stage == "ab_prompt":
        # One-off instrument check, not extraction: re-scores 12 already-scored
        # windows under both prompt arrangements so the cheaper one can be
        # adopted (or rejected) on evidence. ~24 calls, then EX_DONE.
        cmd = [PY, "ab_prompt.py", "run", "--n", "10", "--model", model]
    elif stage == "questions":
        cmd = [PY, "extract_questions.py", "run", "--source", "oral",
               "--out", QA_SCORES, "--workers", WORKERS,
               "--model", model, "--backend", backend]
    elif stage in ("resolve_divination", "resolve_veracity"):
        # Search-backed resolution. Divination first: 110 pending against
        # veracity's 1,109, and it is the attribute least able to stand on a
        # guess — "did it come true" has an answer in the world.
        attr = stage.split("_", 1)[1]
        cmd = [PY, "resolve.py", "run", "--scores", SCORES,
               "--attrs", attr, "--workers", WORKERS, "--model", model]
    elif stage == "positions":
        # Record-tier extraction: a stated position and a commitment, no score.
        # Feeds data/authenticity_score.py and the Strength ledger join, and
        # lands in its OWN file — these rows are permanently score-less, so
        # mixing them into the scores dataset would corrupt every aggregate.
        cmd = [PY, "extract_hansard.py", "--attrs", "positions",
               "--since", f"{PILOT_MONTH}-01", "--until", PILOT_MONTH,
               "--window_tokens", WINDOW_TOKENS, "--workers", WORKERS,
               "--timeout", CALL_TIMEOUT,
               "--backend", backend, "--model", model, "--out", POSITIONS]
    else:
        cmd = [PY, "extract_hansard.py",
               "--since", f"{PILOT_MONTH}-01" if stage == "pilot" else SINCE,
               "--until", PILOT_MONTH if stage == "pilot" else "",
               "--window_tokens", WINDOW_TOKENS, "--workers", WORKERS,
               "--timeout", CALL_TIMEOUT,
               "--backend", backend, "--model", model, "--out", SCORES]
    try:
        return subprocess.run(cmd, cwd=HERE,
                              env={**os.environ,
                                   "CLAUDE_CLI_USAGE_LOG": USAGE_LOG,
                                   "CLAUDE_CLI_SYSTEM_FLAG": SYSTEM_PROMPT_FLAG,
                                   "CLAUDE_CLI_BUDGET": BUDGET_CONFIG},
                              timeout=max(30, timeout_s)).returncode
    except subprocess.TimeoutExpired:
        print("  pass hit the deadline — stopping cleanly (resumable)", flush=True)
        return 0


def _audit(stage: str) -> None:
    """Run the label-free instrument audits over whatever was produced.

    These are the checks that decide whether the prompt rewrite worked, so they
    belong at the end of the run rather than in a follow-up someone forgets.
    """
    if stage != "pilot" and stage != "windows" or not _count(SCORES):
        return
    print("\n=== instrument audits ===", flush=True)
    subprocess.run([PY, "attribute_overlap.py", "run", "--scores", SCORES,
                    "--out", "ATTRIBUTE_OVERLAP_v3.md"], cwd=HERE)
    subprocess.run([PY, "check_quotes.py", "run", "--scores", SCORES,
                    "--n", "800", "--out", "QUOTE_AUDIT_v3.md"], cwd=HERE)
    print("\nTargets to check (ATTRIBUTES.md):", flush=True)
    print("  max pairwise r < 0.65   veracity/rigor < 0.55")
    print("  statements with 2+ attributes < 60%   specificity firing < 30%")
    print("  quotes not found = 0 (the gate enforces this)")


def status() -> None:
    """Progress across all stages. Spends nothing."""
    print(f"windows scored:       {_count(SCORES):,}  ({SCORES})")
    print(f"Q/A pairs scored:     {_count(QA_SCORES):,}  ({QA_SCORES})")
    print(f"resolved claims:      {_count(RESOLVED):,}  ({RESOLVED})")
    for name in ("ATTRIBUTE_OVERLAP_v3.md", "QUOTE_AUDIT_v3.md"):
        p = os.path.join(HERE, name)
        print(f"{name}: {'present' if os.path.exists(p) else 'not yet generated'}")


def run(hours: float = 10.0, stage: str = "pilot", model: str = MODEL,
        backend: str = BACKEND, target: int = 0) -> None:
    """Run one stage until it completes or the time budget runs out.

    `--stage all` runs the pilot, writes the audits, then rolls straight on into
    the full term with whatever time is left. That ordering is deliberate: the
    pilot month is a subset of the full term and windows are deduplicated by
    `window_id`, so nothing is extracted twice and an overnight budget is never
    left idle just because the pilot finished at 1am.

    It does NOT replace reading the audits. The extractor's gates run in-process
    (a non-verbatim quote cannot reach disk), so an unattended roll-on cannot
    corrupt the output — but whether the prompts are behaving is still a
    judgement call, and `ATTRIBUTE_OVERLAP_v3.md` is written after the pilot so
    it is waiting in the morning either way.
    """
    if stage == "all":
        deadline = time.time() + hours * 3600
        run(hours=hours, stage="pilot", model=model, backend=backend)
        left = (deadline - time.time()) / 3600
        if left <= 0.2:
            print(f"\n=== pilot done; no time left for the full term ===",
                  flush=True)
            return
        print(f"\n=== rolling on into the full term with {left:.1f}h left ===",
              flush=True)
        run(hours=left, stage="windows", model=model, backend=backend)
        return
    if stage not in ("pilot", "windows", "questions", "positions", "ab_prompt",
                     "resolve_divination", "resolve_veracity"):
        raise SystemExit("--stage must be pilot | windows | questions | "
                         "positions | resolve_divination | resolve_veracity "
                         "| all")

    out_file = {"questions": QA_SCORES,
                "ab_prompt": "ab_prompt_B.jsonl",
                "positions": POSITIONS,
                "resolve_divination": RESOLVED,
                "resolve_veracity": RESOLVED}.get(stage, SCORES)
    deadline = time.time() + hours * 3600
    # Only window stages have a target in the same units as `done()` (rows
    # written == windows scored). For `questions` the plan is in CALLS and for
    # the resolvers it is in ITEMS, neither of which is comparable to a row
    # count — so they get no target and stop when the runner says EX_DONE.
    if stage in ("pilot", "windows"):
        target = target or _plan_size(stage, model, backend)
    else:
        target = 0

    def done() -> int:
        return _count(out_file)

    label = f"{done():,}" + (f"/{target:,}" if target else "")
    print(f"=== v3.0 {stage}: up to {hours}h, {model} via {backend}, "
          f"starting at {label} ===", flush=True)

    quota_strikes = 0
    stage_complete = False
    while (not target or done() < target) and time.time() < deadline:
        before = done()
        code = _pass(stage, deadline - time.time(), model, backend)
        after = done()
        if code == EX_DONE:
            print(f"\n=== {stage}: complete at {after:,} ===", flush=True)
            stage_complete = True
            break
        if code == EX_QUOTA:
            # One retry is worth it: a rolling usage window can reset within the
            # night. Six are not — on 2026-08-14 the loop re-entered the pass
            # every 75 minutes from 23:10 to 06:00 and never recovered, which
            # means the cap was longer than the night, not a rolling window.
            quota_strikes += 1
            # Raised from 2 on 2026-08-17. The cap turned out to be a ROLLING
            # window, not a nightly ceiling: on 2026-08-16 questions was locked
            # out at 00:14, quota returned around 03:00, and the slower resolver
            # spent it instead. Two strikes ended a stage that had ~3h of usable
            # time left.
            #
            # A blocked pass now costs seconds (QuotaExhausted aborts it), so
            # patience is nearly free -- the real cost of stopping early is a
            # whole stage idle for the rest of the night.
            if quota_strikes >= QUOTA_STRIKES:
                print(f"\n=== {stage}: subscription quota exhausted twice — "
                      f"stopping for the night at {after:,}. Resumable. ===",
                      flush=True)
                break
        left = (deadline - time.time()) / 3600
        print(f"[{after:,}{f'/{target:,}' if target else ''}] "
              f"(+{after - before} this pass, {left:.1f}h left)", flush=True)
        if (target and after >= target) or time.time() >= deadline:
            break
        if after == before and code not in (0, EX_QUOTA):
            # A pass that made no progress AND exited non-zero for a reason
            # other than quota is broken, not blocked. Backing off assumes the
            # obstacle is time; a crash is not fixed by waiting. On 2026-08-25
            # ab_prompt raised TypeError on every call and this loop napped 75
            # minutes four times over, holding the front of the rotation for two
            # entire nights while `windows` — which was working — never ran.
            print(f"\n=== {stage}: exited {code} having written nothing. That is "
                  f"a failure, not a quota block, so waiting cannot help. "
                  f"Dropping it for tonight. ===", flush=True)
            _audit(stage)
            raise SystemExit(EX_FAIL)
        if after == before:
            # No progress: almost always the subscription session cap. Back off,
            # but never past the deadline the user set.
            nap = min(BACKOFF, max(0, deadline - time.time()))
            if nap <= 0:
                break
            print(f"  no progress — backing off {nap / 60:.0f} min", flush=True)
            time.sleep(nap)
        else:
            time.sleep(min(SHORT_SLEEP, max(0, deadline - time.time())))

    _audit(stage)
    finished = ("complete" if stage_complete or (target and done() >= target)
                else "deadline reached")
    print(f"\n=== {stage} finished ({finished}) at {done():,} ===", flush=True)
    print("\nNOTHING WAS PUBLISHED. v3.0 scores are not comparable with v2.0 "
          "(Civility re-anchored, Charisma replaced by Focus), so the site is "
          "refreshed only after the evaluation pass.", flush=True)
    if stage == "pilot":
        print("\nNext: read ATTRIBUTE_OVERLAP_v3.md and QUOTE_AUDIT_v3.md. If the "
              "targets hold, run --stage windows.", flush=True)

    # Same condition as the `finished` label above, deliberately. Testing only
    # `stage_complete` here read "complete" in the log but exited 0: that flag is
    # set INSIDE the while loop, whose own guard is `done() < target`, so a stage
    # that was ALREADY at its target never entered the body and never set it. On
    # 2026-09-24 windows hit 5,548/5,548 at 17:24 and tonight.py — which drops a
    # stage only on EX_DONE — kept handing it turns: 1,864 no-op rounds in four
    # hours, each re-running both audits over a 66 MB file. No quota was spent
    # (the pass never ran), but nothing else made progress either.
    if stage_complete or (target and done() >= target):
        # Propagate completion to the caller (tonight.py), which drops the
        # stage from its rotation. Without this the exit code is 0 and a
        # finished stage keeps being offered turns for the rest of the night.
        raise SystemExit(EX_DONE)


if __name__ == "__main__":
    fire.Fire({"run": run, "status": status})
