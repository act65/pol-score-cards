"""A self-imposed ceiling on what the overnight run may spend.

WHY THIS EXISTS, AND WHAT IT HONESTLY CANNOT DO
-----------------------------------------------
The subscription's real cap is not readable from anywhere. `claude` reports
`total_cost_usd` per call — a notional API-equivalent price, not a balance —
and nothing exposes how much of the window is left. Worse, the cap is shared:
interactive daytime sessions draw on the same pool and are NOT in our usage
log, because they are not run by us.

So this module does not, and cannot, track headroom. It does one useful thing:

    it stops THIS pipeline once it has spent a configured amount in a rolling
    window, so the rest of the cap is still there during the day.

That is a self-imposed budget, not a quota reading. If the pipeline's budget is
$60 per five hours and the real cap is worth $200, then $140 is left for
daytime work — but only because we declined to spend it, not because anyone
told us it was there.

The cap is still enforced upstream too: when the real window is spent, the CLI
returns the zero-token envelope that `claude_cli._is_quota_error` detects. This
module fires FIRST, on our own accounting, which is the point.

HOW IT PLUGS IN
---------------
Opt-in by environment, so the module stays independent of the pipeline and
nothing changes for callers that do not set it:

    CLAUDE_CLI_BUDGET     path to the config JSON (this file's `quota_budget.json`)
    CLAUDE_CLI_USAGE_LOG  path to the usage log it meters (already set by the runner)

`claude_cli.call_structured*` calls `gate()` before spawning. Over budget raises
`BudgetExhausted`, which `claude_cli` re-raises as `QuotaExhausted`, so
`overnight_run.py` treats it exactly like a real quota block — clean stop,
EX_QUOTA, resume tomorrow — while the message says plainly the stop was ours.

ONE-CALL OVERSHOOT IS EXPECTED
------------------------------
`cost_usd` only exists after a call returns, so the gate compares spend *so
far* against the cap. The call that crosses the line is paid for. At ~$0.30 a
call that is noise; do not add a pre-estimate to chase it.

CLI
---
    python quota_budget.py status       # spend per window vs cap — spends nothing
    python quota_budget.py calibrate    # what the REAL ceiling looks like, from history
"""
import datetime as dt
import json
import os

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "quota_budget.json")
DEFAULT_LOG = os.path.join(HERE, "usage_v3.jsonl")

# Used only when no config file exists. Deliberately not a guess at the real
# cap: it is a ceiling on us, and `calibrate` is how it gets set from evidence.
FALLBACK = {"windows": [{"hours": 5, "max_cost_usd": 60.0}]}


class BudgetExhausted(Exception):
    """Our own budget is spent. `claude_cli` catches this and re-raises it as
    `QuotaExhausted`, so every existing handler works unchanged — the runner
    stops cleanly with EX_QUOTA and resumes tomorrow. Kept a separate type
    here so this module never imports the pipeline."""


def load_config(path: str = "") -> dict:
    path = path or os.environ.get("CLAUDE_CLI_BUDGET", "") or DEFAULT_CONFIG
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(FALLBACK)
    if not isinstance(cfg.get("windows"), list) or not cfg["windows"]:
        return dict(FALLBACK)
    return cfg


def _rows(log_path: str = ""):
    path = log_path or os.environ.get("CLAUDE_CLI_USAGE_LOG", "") or DEFAULT_LOG
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue          # a torn last line, mid-append
                ts = r.get("ts")
                if not ts:
                    continue
                try:
                    r["_t"] = dt.datetime.fromisoformat(ts)
                except ValueError:
                    continue
                yield r
    except OSError:
        return                        # no log yet is not an error: spend is 0


def spent(hours: float, now: dt.datetime = None, log_path: str = "") -> float:
    """Dollars this pipeline has logged in the last `hours`."""
    now = now or dt.datetime.now()
    cutoff = now - dt.timedelta(hours=hours)
    return sum(float(r.get("cost_usd") or 0.0)
               for r in _rows(log_path) if r["_t"] >= cutoff)


def check(now: dt.datetime = None, config_path: str = "",
          log_path: str = "") -> list:
    """One row per configured window: (hours, spent, cap, over?)."""
    cfg = load_config(config_path)
    now = now or dt.datetime.now()
    out = []
    for w in cfg["windows"]:
        hours = float(w.get("hours", 5))
        cap = float(w.get("max_cost_usd", 0) or 0)
        s = spent(hours, now, log_path)
        out.append((hours, s, cap, cap > 0 and s >= cap))
    return out


def gate(now: dt.datetime = None, config_path: str = "",
         log_path: str = "") -> None:
    """Raise BudgetExhausted if any window is spent. Silent when under, and a
    no-op when CLAUDE_CLI_BUDGET is unset and no config file exists."""
    if not (os.environ.get("CLAUDE_CLI_BUDGET") or os.path.exists(DEFAULT_CONFIG)):
        return
    for hours, s, cap, over in check(now, config_path, log_path):
        if over:
            raise BudgetExhausted(
                f"self-imposed budget spent: ${s:.2f} in the last {hours:g}h "
                f"against a ${cap:.2f} cap. This is OUR limit, not the "
                f"subscription's — the rest of the window is being kept for "
                f"daytime use. Raise it in quota_budget.json.")


# ---------------------------------------------------------------- CLI

def status(config_path: str = "", log_path: str = "") -> None:
    """Spend per window against its cap. Spends nothing."""
    cfg = load_config(config_path)
    rows = check(None, config_path, log_path)
    print(f"{'window':>9}{'spent':>10}{'cap':>10}{'left':>10}   state")
    for hours, s, cap, over in rows:
        left = cap - s
        state = "OVER — pipeline stops" if over else "ok"
        print(f"{hours:>8g}h{s:>10.2f}{cap:>10.2f}{left:>10.2f}   {state}")
    if cfg.get("note"):
        print(f"\n{cfg['note']}")


def calibrate(hours: float = 5, log_path: str = "") -> None:
    """What the REAL ceiling looks like, measured from history.

    Slides a window over the usage log and reports the most this pipeline ever
    got through in one. That maximum is a LOWER BOUND on the true cap: on
    nights that ended in quota blocks it is the cap itself, on nights that ran
    out of work it is just the work available. Set the budget below it.
    """
    rows = sorted(_rows(log_path), key=lambda r: r["_t"])
    if not rows:
        print("no usage logged yet — run a night first")
        return
    best = (0.0, None)
    j = 0
    run = 0.0
    for i, r in enumerate(rows):
        run += float(r.get("cost_usd") or 0.0)
        while rows[j]["_t"] < r["_t"] - dt.timedelta(hours=hours):
            run -= float(rows[j].get("cost_usd") or 0.0)
            j += 1
        if run > best[0]:
            best = (run, r["_t"])
    daily = {}
    for r in rows:
        d = (r["_t"] - dt.timedelta(hours=12)).date().isoformat()
        daily[d] = daily.get(d, 0.0) + float(r.get("cost_usd") or 0.0)
    print(f"logged {len(rows):,} calls, {rows[0]['_t']:%Y-%m-%d} -> "
          f"{rows[-1]['_t']:%Y-%m-%d}")
    print(f"\nbusiest {hours:g}h window: ${best[0]:.2f}  (ending {best[1]:%Y-%m-%d %H:%M})")
    print("\nper night (a night is credited to the morning it ends):")
    for d in sorted(daily)[-14:]:
        print(f"  {d}  ${daily[d]:8.2f}")
    print("\nThe busiest window is a LOWER bound on the real cap — on nights\n"
          "that ended in quota blocks it IS the cap; on nights that simply ran\n"
          "out of work it is less. Set max_cost_usd below it, by whatever you\n"
          "want left for the day.")


if __name__ == "__main__":
    fire.Fire({"status": status, "calibrate": calibrate,
               "check": check, "spent": spent})
