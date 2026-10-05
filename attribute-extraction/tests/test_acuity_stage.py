"""The acuity stage's two silent failure modes, and the supervisor contract.

Acuity is the one attribute the completed six-attribute pass never scored, so
it is run alone over the same 5,548 windows. Two ways that goes wrong without
anybody noticing:

 1. WRONG OUTPUT FILE. `extract_hansard` resumes by reading `window_id`s out of
    `--out`. `hansard_scores_v3.jsonl` already holds all 5,548 of them, so an
    acuity run pointed there would decide every window was done, extract
    nothing, and exit reporting success. Over an unattended weekend that is
    three days of nothing, with a plausible-looking log.

 2. NO TARGET. `run()` only measures completion against a target for window
    stages. Without one, `done() < target` is vacuously true and the stage can
    never reach the `EX_DONE` branch — so tonight.py keeps handing it turns
    after the last window is scored (the 2026-09-24 hot loop, from the other
    direction).

The third test covers `burst`, which is now supervised by systemd rather than
by a person: it has to distinguish "finished" from "stopped early".
"""

import datetime as dt
import inspect

import overnight_run
import tonight


def test_acuity_writes_to_its_own_file():
    """Not SCORES — see failure mode 1. The whole run depends on this."""
    assert overnight_run.ACUITY != overnight_run.SCORES
    cmd = _acuity_cmd()
    assert "--out" in cmd
    assert cmd[cmd.index("--out") + 1] == overnight_run.ACUITY


def test_acuity_extracts_acuity_alone_over_the_full_term():
    """One attribute, matching the pilot: yield falls 26-58% when bundled."""
    cmd = _acuity_cmd()
    assert cmd[cmd.index("--attrs") + 1] == "acuity"
    assert cmd[cmd.index("--since") + 1] == overnight_run.SINCE
    # Window size and the resume index are coupled; the pilot ran at 3,000.
    assert cmd[cmd.index("--window_tokens") + 1] == overnight_run.WINDOW_TOKENS


def _acuity_cmd():
    """The argv `_pass` would run, captured instead of executed."""
    captured = {}

    class _Stop(Exception):
        pass

    def _fake_run(cmd, **_kw):
        captured["cmd"] = cmd
        raise _Stop()

    real = overnight_run.subprocess.run
    overnight_run.subprocess.run = _fake_run
    try:
        overnight_run._pass("acuity", 60, overnight_run.MODEL,
                            overnight_run.BACKEND)
    except _Stop:
        pass
    finally:
        overnight_run.subprocess.run = real
    return captured["cmd"]


def test_acuity_gets_a_target_so_it_can_report_done(monkeypatch):
    """Failure mode 2: a window stage with target 0 can never exit EX_DONE."""
    monkeypatch.setattr(overnight_run, "_count", lambda _p: 5548)
    monkeypatch.setattr(overnight_run, "_plan_size", lambda *a, **k: 5548)
    monkeypatch.setattr(overnight_run, "_audit", lambda _s: None)
    spent = []
    monkeypatch.setattr(overnight_run, "_pass",
                        lambda *a, **k: spent.append(a[0]) or 0)
    try:
        overnight_run.run(hours=0.01, stage="acuity")
    except SystemExit as exc:
        assert exc.code == overnight_run.EX_DONE
    else:
        raise AssertionError("a finished acuity stage must exit EX_DONE")
    assert spent == [], "a stage at its target must not spend a pass"


def test_acuity_is_an_accepted_stage(monkeypatch):
    """`--stage acuity` must not be rejected by the whitelist."""
    monkeypatch.setattr(overnight_run, "_count", lambda _p: 0)
    monkeypatch.setattr(overnight_run, "_plan_size", lambda *a, **k: 5548)
    monkeypatch.setattr(overnight_run, "_audit", lambda _s: None)
    monkeypatch.setattr(overnight_run, "_pass", lambda *a, **k: 0)
    try:
        overnight_run.run(hours=0.001, stage="acuity")
    except SystemExit as exc:
        assert exc.code != 1 and "must be" not in str(exc.code or "")


def test_the_nightly_plan_is_runnable():
    """A durable invariant, not tonight's contents.

    This test used to assert `"acuity" in NIGHTLY_PLAN` and that
    resolve_divination led it. Both were true for two days and then false: the
    stages finished on 2026-10-04 and the plan moved to resolve_veracity, so the
    test failed for the one reason a test should never fail -- the work
    succeeded. What actually needs guarding is that whatever the plan holds can
    be run, which is the failure that would otherwise surface at 3am.
    """
    assert tonight.NIGHTLY_PLAN, "an empty plan is a night that does nothing"
    assert set(tonight.NIGHTLY_PLAN) <= tonight.KNOWN_STAGES
    for stage in tonight.NIGHTLY_PLAN:
        assert f'"{stage}"' in inspect.getsource(overnight_run.run), \
            f"{stage} is scheduled but overnight_run.run rejects it"


def _burst(monkeypatch, hours_ahead, finished):
    """Run `burst` with the night stubbed; return the exit code systemd sees."""
    stop = dt.datetime.now() + dt.timedelta(hours=hours_ahead)
    monkeypatch.setattr(tonight, "_one_night",
                        lambda *a, **k: set(finished))
    monkeypatch.setattr(tonight.subprocess, "run", lambda *a, **k: None)
    try:
        tonight.burst(until=stop.isoformat(timespec="minutes"),
                      stages="resolve_divination,acuity")
    except SystemExit as exc:
        return exc.code
    return 0


def test_burst_reports_failure_when_it_ends_early_with_work_left(monkeypatch):
    """So systemd restarts it. Exiting 0 here silently ends a multi-day run."""
    code = _burst(monkeypatch, hours_ahead=48, finished=[])
    assert code == tonight.EX_FAIL


def test_burst_ending_at_its_deadline_is_not_a_failure(monkeypatch):
    """The budget doing its job. Restarting into a passed deadline hot-loops."""
    code = _burst(monkeypatch, hours_ahead=0.05, finished=[])
    assert code == 0


def test_burst_exits_clean_when_every_stage_is_done(monkeypatch):
    code = _burst(monkeypatch, hours_ahead=48,
                  finished=["resolve_divination", "acuity"])
    assert code == 0


def test_plan_accepts_the_tuple_python_fire_actually_passes():
    """The bug that killed the first unattended launch, one second in.

    `--stages resolve_divination,acuity` reaches `burst` as a TUPLE, not a
    string, so the old `stages.split(",")` raised AttributeError. Every earlier
    unit passed a SINGLE stage, which fire hands over as a string — so this was
    reachable only by the two-stage plan the unattended run needs.
    """
    want = ("resolve_divination", "acuity")
    assert tonight._plan(("resolve_divination", "acuity")) == want
    assert tonight._plan("resolve_divination,acuity") == want
    assert tonight._plan("acuity") == ("acuity",)


def test_plan_falls_back_to_the_nightly_rotation():
    assert tonight._plan("") == tonight.NIGHTLY_PLAN
    assert tonight._plan(()) == tonight.NIGHTLY_PLAN


def test_plan_rejects_an_unknown_stage():
    """A typo in a unit file must fail in the first second, not at 3am."""
    try:
        tonight._plan("acuity,resolve_divinaton")
    except SystemExit as exc:
        assert "resolve_divinaton" in str(exc)
    else:
        raise AssertionError("an unknown stage must be rejected")


def test_known_stages_matches_the_runners_whitelist():
    """Two whitelists that disagree let tonight.py schedule what run() refuses."""
    import inspect
    src = inspect.getsource(overnight_run.run)
    for stage in tonight.KNOWN_STAGES:
        assert f'"{stage}"' in src, f"{stage} is not accepted by overnight_run.run"
