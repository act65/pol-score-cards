"""The scheduler's contract with the runner: a finished stage must exit EX_DONE.

`tonight.py` drops a stage from its rotation ONLY on EX_DONE. Any other code —
including 0 — means "made progress, offer it another turn". So a stage that is
already at its target has to report completion through the exit code, not just
in its log line.

Regression: on 2026-09-24 `windows` reached 5,548/5,548 and exited 0 while
printing "finished (complete)". The two used different conditions — the label
tested `stage_complete or done() >= target`, the exit tested `stage_complete`
alone, and that flag is only set inside a loop guarded by `done() < target`.
tonight.py handed the finished stage 1,864 further turns over four hours.
"""

import overnight_run


def _run_windows(monkeypatch, rows, target, pass_code=0):
    """Call run() for the `windows` stage with the world stubbed out.

    No LLM call, no audit, no disk: `_pass` is what spends quota and `_audit`
    is what re-reads the 66 MB scores file, and neither is under test here.
    """
    monkeypatch.setattr(overnight_run, "_count", lambda _p: rows)
    monkeypatch.setattr(overnight_run, "_plan_size", lambda *a, **k: target)
    monkeypatch.setattr(overnight_run, "_audit", lambda _s: None)
    calls = []

    def _fake_pass(stage, remaining, model, backend):
        calls.append(stage)
        return pass_code

    monkeypatch.setattr(overnight_run, "_pass", _fake_pass)
    # An unfinished stage returns normally, which the caller sees as exit 0;
    # only a finished (or failing) one raises. Both are valid outcomes here,
    # so normalise them to the code tonight.py would actually observe.
    try:
        overnight_run.run(hours=0.01, stage="windows")
    except SystemExit as exc:
        return exc.code, calls
    return 0, calls


def test_stage_already_at_target_exits_done(monkeypatch):
    """The bug. Nothing to do, so the loop body never runs — still EX_DONE."""
    code, calls = _run_windows(monkeypatch, rows=5548, target=5548)
    assert code == overnight_run.EX_DONE
    assert calls == [], "a stage at its target must not spend a pass"


def test_stage_past_its_target_exits_done(monkeypatch):
    code, _ = _run_windows(monkeypatch, rows=5600, target=5548)
    assert code == overnight_run.EX_DONE


def test_unfinished_stage_does_not_claim_done(monkeypatch):
    """The other half of the contract: EX_DONE must not be over-reported.

    A stage stopped by its deadline with work left has to exit non-DONE, or
    tonight.py drops it for good and the remaining windows are never scored.
    """
    code, calls = _run_windows(monkeypatch, rows=100, target=5548)
    assert code != overnight_run.EX_DONE
    assert calls, "an unfinished stage should have attempted at least one pass"
