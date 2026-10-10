"""A stage that writes nothing forever must escalate, not nap forever.

Regression, 2026-10-06. The subscription usage limit was reached at 05:31. Every
`claude -p` then returned instantly with stop_reason "stop_sequence", 0 input
tokens and total_cost_usd 0; resolve.py logged "failed after 3 attempts" and
exited 0 having written nothing. The no-progress branch read that as a quota
block, napped 20 minutes, and retried about 300 times over four days. When the
limit reset the run did not recover, because the wedged process was never
replaced -- 3,526 of 3,895 claims were still unresolved.

The gap: QUOTA_STRIKES only counts EX_QUOTA, which is OUR budget guard
(quota_budget.json). The real subscription cap is readable from nowhere and
arrives as ordinary call failures, so nothing counted them.
"""

import overnight_run


def _run(monkeypatch, codes, rows_each_pass):
    """Drive run() through a scripted sequence of passes.

    `codes[i]` is pass i's exit code; `rows_each_pass[i]` the row count AFTER it.
    """
    state = {"i": 0, "rows": 0}
    monkeypatch.setattr(overnight_run, "_count", lambda _p: state["rows"])
    monkeypatch.setattr(overnight_run, "_plan_size", lambda *a, **k: 0)
    monkeypatch.setattr(overnight_run, "_audit", lambda _s: None)
    monkeypatch.setattr(overnight_run.time, "sleep", lambda _s: None)
    monkeypatch.setattr(overnight_run, "BACKOFF", 1)

    def _fake_pass(stage, remaining, model, backend):
        i = state["i"]
        if i >= len(codes):
            raise AssertionError(f"ran {i + 1} passes; script has {len(codes)}")
        state["rows"] = rows_each_pass[i]
        state["i"] += 1
        return codes[i]

    monkeypatch.setattr(overnight_run, "_pass", _fake_pass)
    try:
        overnight_run.run(hours=10, stage="resolve_veracity")
    except SystemExit as exc:
        return exc.code, state["i"]
    return 0, state["i"]


def test_endless_zero_progress_escalates_to_a_restart(monkeypatch):
    """The bug. Exit 0 + nothing written, forever, must become EX_FAIL."""
    n = overnight_run.IDLE_STRIKES + 4
    code, passes = _run(monkeypatch, [0] * n, [0] * n)
    assert code == overnight_run.EX_FAIL, "a wedged stage must ask to be replaced"
    assert passes == overnight_run.IDLE_STRIKES, (
        f"should escalate on pass {overnight_run.IDLE_STRIKES}, took {passes}")


def test_a_short_block_still_just_backs_off(monkeypatch):
    """Patience is still correct for a real, temporary quota block.

    Five idle passes then progress: the stage must NOT have bailed, because the
    rolling usage window genuinely does recover and a stage that gives up early
    leaves the night idle.
    """
    idle = overnight_run.IDLE_STRIKES - 1
    codes = [0] * idle + [overnight_run.EX_DONE]
    rows = [0] * idle + [42]
    code, passes = _run(monkeypatch, codes, rows)
    assert code == overnight_run.EX_DONE
    assert passes == idle + 1


def test_progress_clears_the_strike_count(monkeypatch):
    """Otherwise a slow stage that writes occasionally still dies eventually."""
    idle = overnight_run.IDLE_STRIKES - 1
    # idle run, one row, then another full idle run, then done.
    codes = [0] * idle + [0] + [0] * idle + [overnight_run.EX_DONE]
    rows = [0] * idle + [1] + [1] * idle + [2]
    code, passes = _run(monkeypatch, codes, rows)
    assert code == overnight_run.EX_DONE, (
        "a pass that wrote something must reset the counter")
    assert passes == len(codes)


def test_a_crash_still_escalates_immediately(monkeypatch):
    """The pre-existing rule: non-zero + nothing written is broken, not blocked.

    This must stay one pass, not IDLE_STRIKES -- waiting cannot fix a crash.
    """
    code, passes = _run(monkeypatch, [70, 0, 0], [0, 0, 0])
    assert code == overnight_run.EX_FAIL
    assert passes == 1
