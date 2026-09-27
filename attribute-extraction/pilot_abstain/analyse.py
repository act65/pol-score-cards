"""Did the abstain rule and the Focus narrowing do what they were meant to?

    python pilot_abstain/analyse.py

Compares the NEW prompts against the CURRENT instrument on the SAME 260 windows
(2025-10), which is the only comparison that isolates the prompt change from the
corpus. Civility is unchanged, so the Focus/Civility correlation is computed by
joining new Focus scores onto the existing Civility scores.
"""
import collections
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

NEW = os.path.join(HERE, "abstain_pilot.jsonl")
OLD = os.path.abspath(os.path.join(HERE, "..", "hansard_scores_v3.jsonl"))


def load(path, only_windows=None):
    """{attribute: {statement: score_or_None}} plus the set of windows seen."""
    by = collections.defaultdict(dict)
    wins = set()
    if not os.path.exists(path):
        return by, wins
    for line in open(path, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        wid = rec.get("window_id", "")
        if only_windows is not None and wid not in only_windows:
            continue
        wins.add(wid)
        for a, exs in (rec.get("examples_by_attribute") or {}).items():
            for e in exs:
                t = (e.get("statement") or "").strip()
                if t:
                    by[a][t] = e.get("score")
    return by, wins


def pearson(xs, ys):
    if len(xs) < 30:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (dx * dy)
            if dx and dy else None)


def main():
    new, wins = load(NEW)
    if not wins:
        print("no pilot rows yet")
        return
    old, _ = load(OLD, only_windows=wins)

    # Denominator: distinct statements the run extracted at all. The two runs
    # requested different attribute sets, so each is measured against its own
    # extraction — which is the right comparison for a firing RATE.
    new_stmts = {t for d in new.values() for t in d}
    old_stmts = {t for d in old.values() for t in d}
    print("=" * 68)
    print(f"ABSTAIN + FOCUS PILOT — 2025-10, {len(wins)} windows")
    print("=" * 68)
    print(f"distinct statements extracted: new {len(new_stmts):,} | "
          f"current {len(old_stmts):,}")

    print(f"\n{'attribute':13s} {'current n':>10s} {'new n':>7s} "
          f"{'current rate':>13s} {'new rate':>9s}")
    for a in ("veracity", "focus"):
        on, nn = len(old.get(a, {})), len(new.get(a, {}))
        orate = 100 * on / len(old_stmts) if old_stmts else 0
        nrate = 100 * nn / len(new_stmts) if new_stmts else 0
        print(f"  {a:11s} {on:10,d} {nn:7,d} {orate:12.0f}% {nrate:8.0f}%")

    # Veracity's gate: target < 15% of statements.
    vn = len(new.get("veracity", {}))
    vrate = 100 * vn / len(new_stmts) if new_stmts else 0
    print(f"\nVERACITY FIRING: {vrate:.0f}%  (target < 15%)  "
          f"{'PASS' if vrate < 15 else 'MISS'}")
    if vn:
        print(f"  extrapolated resolver queue over the full term: "
              f"~{vrate / 100 * 61666:,.0f} claims "
              f"= {vrate / 100 * 61666 / 73 / 7:.0f} nights at 73/hour")

    # Focus x Civility. Civility's prompt is unchanged, so its scores stand.
    civ = old.get("civility", {})
    for label, foc in (("current Focus", old.get("focus", {})),
                       ("NEW Focus", new.get("focus", {}))):
        pairs = [(foc[t], civ[t]) for t in foc
                 if t in civ and isinstance(foc[t], (int, float))
                 and isinstance(civ[t], (int, float))]
        r = pearson([a for a, _ in pairs], [c for _, c in pairs])
        shown = f"{r:+.3f}" if r is not None else "--"
        flag = ""
        if r is not None:
            flag = "  MISS" if abs(r) >= 0.65 else "  PASS"
        print(f"\nFOCUS x CIVILITY ({label}): r = {shown}   "
              f"co-scored {len(pairs)}{flag}")

    # What the abstain rule dropped — the check that it dropped the right thing.
    dropped = [t for t in old.get("veracity", {}) if t not in new.get("veracity", {})]
    kept = [t for t in new.get("veracity", {}) if t in old.get("veracity", {})]
    added = [t for t in new.get("veracity", {}) if t not in old.get("veracity", {})]
    print(f"\nVERACITY set change: dropped {len(dropped)}, kept {len(kept)}, "
          f"newly picked up {len(added)}")
    for t in dropped[:6]:
        print(f"  DROPPED: {t[:110]}")
    for t in kept[:3]:
        print(f"  KEPT   : {t[:110]}")

    # Focus: did it abstain on abuse rather than scoring it 0.0?
    fo_old, fo_new = old.get("focus", {}), new.get("focus", {})
    gone = [t for t in fo_old if t not in fo_new]
    zeros_old = [t for t in fo_old
                 if isinstance(fo_old[t], (int, float)) and fo_old[t] <= 0.1]
    gone_zeros = [t for t in zeros_old if t not in fo_new]
    print(f"\nFOCUS set change: {len(fo_old)} -> {len(fo_new)}; "
          f"dropped {len(gone)}")
    if zeros_old:
        print(f"  of {len(zeros_old)} statements the current prompt scored <=0.1, "
              f"{len(gone_zeros)} are now omitted "
              f"({100 * len(gone_zeros) / len(zeros_old):.0f}%)")
    for t in gone_zeros[:5]:
        print(f"  NOW OMITTED: {t[:110]}")


if __name__ == "__main__":
    main()
