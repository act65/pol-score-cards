"""The self-imposed budget must actually stop a call, and must not fire early.

These run offline: `claude_cli.subprocess.run` is intercepted, so the gate is
exercised against the real call path with zero spend. The lesson from the
`prompts_dir` TypeError and the `Example is not JSON serializable` bug — both
of which cost whole nights because the test stopped short of the real boundary
— is that testing `gate()` alone proves nothing about whether the pipeline
honours it. So the important test here is the last one: call_structured itself.
"""
import datetime as dt
import json

import pytest

import claude_cli
import quota_budget


def _log(tmp_path, rows):
    p = tmp_path / "usage.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(p)


def _cfg(tmp_path, windows):
    p = tmp_path / "budget.json"
    p.write_text(json.dumps({"windows": windows}), encoding="utf-8")
    return str(p)


def _calls(n, cost, when):
    return [{"ts": when.isoformat(timespec="seconds"), "label": "windows",
             "cost_usd": cost} for _ in range(n)]


def test_spend_counts_only_inside_the_window(tmp_path):
    now = dt.datetime(2026, 9, 17, 3, 0)
    log = _log(tmp_path, _calls(10, 1.0, now - dt.timedelta(hours=1))
               + _calls(10, 1.0, now - dt.timedelta(hours=9)))
    assert quota_budget.spent(5, now, log) == pytest.approx(10.0)
    assert quota_budget.spent(24, now, log) == pytest.approx(20.0)


def test_gate_is_silent_under_budget(tmp_path):
    now = dt.datetime(2026, 9, 17, 3, 0)
    log = _log(tmp_path, _calls(10, 1.0, now - dt.timedelta(hours=1)))
    quota_budget.gate(now, _cfg(tmp_path, [{"hours": 5, "max_cost_usd": 50}]), log)


def test_gate_fires_when_the_window_is_spent(tmp_path):
    now = dt.datetime(2026, 9, 17, 3, 0)
    log = _log(tmp_path, _calls(60, 1.0, now - dt.timedelta(hours=1)))
    with pytest.raises(quota_budget.BudgetExhausted) as e:
        quota_budget.gate(now, _cfg(tmp_path, [{"hours": 5, "max_cost_usd": 50}]), log)
    # The message must say the stop was OURS, or a future reader will spend a
    # night believing the subscription ran out.
    assert "OUR limit" in str(e.value)


def test_a_long_window_can_bind_while_a_short_one_does_not(tmp_path):
    now = dt.datetime(2026, 9, 17, 3, 0)
    log = _log(tmp_path, _calls(5, 1.0, now - dt.timedelta(hours=1))
               + _calls(900, 1.0, now - dt.timedelta(hours=40)))
    cfg = _cfg(tmp_path, [{"hours": 5, "max_cost_usd": 50},
                          {"hours": 168, "max_cost_usd": 800}])
    with pytest.raises(quota_budget.BudgetExhausted):
        quota_budget.gate(now, cfg, log)


def test_a_torn_last_line_does_not_break_accounting(tmp_path):
    """The log is appended to while this reads it."""
    now = dt.datetime(2026, 9, 17, 3, 0)
    p = tmp_path / "usage.jsonl"
    p.write_text(json.dumps({"ts": now.isoformat(), "cost_usd": 3.0}) + "\n"
                 + '{"ts": "2026-09-17T03:00:00", "cost_u', encoding="utf-8")
    assert quota_budget.spent(5, now, str(p)) == pytest.approx(3.0)


def test_missing_log_is_zero_spend_not_a_crash(tmp_path):
    assert quota_budget.spent(5, dt.datetime.now(),
                              str(tmp_path / "nope.jsonl")) == 0.0


def test_call_structured_refuses_to_spawn_when_over_budget(tmp_path, monkeypatch):
    """The one that matters: the pipeline must honour the gate, and must do it
    BEFORE the subprocess, or the budget buys nothing."""
    spawned = []
    monkeypatch.setattr(claude_cli.subprocess, "run",
                        lambda *a, **k: spawned.append(a) or pytest.fail(
                            "spawned claude despite being over budget"))

    now = dt.datetime.now()
    log = _log(tmp_path, _calls(60, 1.0, now - dt.timedelta(minutes=30)))
    monkeypatch.setenv("CLAUDE_CLI_USAGE_LOG", log)
    monkeypatch.setenv("CLAUDE_CLI_BUDGET",
                       _cfg(tmp_path, [{"hours": 5, "max_cost_usd": 50}]))

    # Re-raised as QuotaExhausted so overnight_run's existing clean-stop path
    # handles it — EX_QUOTA, resume tomorrow — with no new branch to maintain.
    with pytest.raises(claude_cli.QuotaExhausted):
        claude_cli.call_structured("sys", "user", {"type": "object"})
    assert not spawned


def test_under_budget_the_call_goes_through(tmp_path, monkeypatch):
    """The mirror image: a budget that binds nothing must change nothing."""
    envelope = {"structured_output": {"ok": True}, "usage": {"output_tokens": 1},
                "total_cost_usd": 0.3, "duration_api_ms": 10}

    class Proc:
        returncode = 0
        stdout = json.dumps(envelope)
        stderr = ""

    monkeypatch.setattr(claude_cli.subprocess, "run", lambda *a, **k: Proc())
    now = dt.datetime.now()
    log = _log(tmp_path, _calls(1, 1.0, now - dt.timedelta(minutes=30)))
    monkeypatch.setenv("CLAUDE_CLI_USAGE_LOG", log)
    monkeypatch.setenv("CLAUDE_CLI_BUDGET",
                       _cfg(tmp_path, [{"hours": 5, "max_cost_usd": 50}]))

    assert claude_cli.call_structured("sys", "user", {"type": "object"}) == {"ok": True}
