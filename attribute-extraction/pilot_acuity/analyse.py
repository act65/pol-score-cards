"""Does Acuity pass the gates? Run after the pilot.

    python pilot_acuity/analyse.py

The gates are in ATTRIBUTES.md: coverage on BOTH benches, shrink > 0.5,
spread > 20 points, max pairwise |r| < 0.65 against the published six. A
one-month pilot cannot settle the per-MP signal-to-noise question — 260 windows
is ~5% of the term, so per-MP n is a handful — so that is extrapolated and
flagged rather than asserted.
"""
import collections
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "data")))

import bias_adjust                                              # noqa: E402
import build_v2_dataset as b                                    # noqa: E402

PILOT = os.path.join(HERE, "acuity_pilot.jsonl")
FULL = os.path.abspath(os.path.join(HERE, "..", "hansard_scores_v3.jsonl"))
POLS = os.path.abspath(os.path.join(HERE, "..", "site_data_v3", "politicians.jsonl"))
GOV = {"National", "ACT", "NZ First"}


def _rows(path, attr):
    """[(window_id, politician, statement, score, extras)] for one attribute."""
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        wid = rec.get("window_id", "")
        for a, exs in (rec.get("examples_by_attribute") or {}).items():
            if a != attr:
                continue
            for e in exs:
                sc = e.get("score")
                if isinstance(sc, (int, float)):
                    out.append((wid, e.get("politician", ""),
                                (e.get("statement") or "").strip(), sc, e))
    return out


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else None


def main():
    pilot = _rows(PILOT, "acuity")
    if not pilot:
        print("no pilot rows yet")
        return
    windows = {w for w, *_ in pilot}
    R = b.Roster()
    pol = {r["id"]: r for r in map(json.loads, open(POLS, encoding="utf-8"))}

    print("=" * 66)
    print("ACUITY PILOT — 2025-10")
    print("=" * 66)
    scores = [s for *_x, s, _e in pilot]
    print(f"windows with >=1 example: {len(windows)}")
    print(f"examples: {len(pilot)}   mean {st.mean(scores) * 100:.0f}   "
          f"median {st.median(scores) * 100:.0f}")
    hist = collections.Counter(round(s * 10) / 10 for s in scores)
    print("score distribution: " + "  ".join(
        f"{k:.1f}:{hist[k]}" for k in sorted(hist)))
    if len(hist) <= 2:
        print("  !! degenerate — the prompt is not discriminating")

    # The audit field: can a reader see what was responded to?
    have = sum(1 for *_x, _s, e in pilot if (e.get("responding_to") or "").strip())
    print(f"\nresponding_to present: {have}/{len(pilot)} ({100 * have / len(pilot):.0f}%)")
    nothing = [e for *_x, s, e in pilot
               if (e.get("responding_to") or "").lower().startswith("nothing")]
    print(f"  of which 'nothing: ...': {len(nothing)}")
    if nothing:
        ns = [s for *_x, s, e in pilot
              if (e.get("responding_to") or "").lower().startswith("nothing")]
        over = [x for x in ns if x > 0.3]
        print(f"  their mean score: {st.mean(ns) * 100:.0f}, max {max(ns) * 100:.0f}")
        print(f"  outside the 0.0-0.3 band the prompt allows: {len(over)} "
              f"({'PASS' if not over else 'FAIL'})")

    # --- coverage, both benches -------------------------------------------
    per = collections.defaultdict(list)
    for _w, name, _t, s, _e in pilot:
        mid = R.match(name)
        if mid:
            per[mid].append(s)
    g = [m for m in per if pol.get(m, {}).get("party") in GOV]
    o = [m for m in per if m not in g and pol.get(m, {}).get("party")]
    print(f"\nCOVERAGE: {len(per)} MPs — government {len(g)}, opposition {len(o)}")
    ns = sorted(len(v) for v in per.values())
    print(f"  examples per MP: median {st.median(ns)}, max {max(ns)}")
    if g and o:
        gm = st.mean([st.mean(per[m]) for m in g]) * 100
        om = st.mean([st.mean(per[m]) for m in o]) * 100
        print(f"  raw bench means: government {gm:.0f}  opposition {om:.0f}  "
              f"gap {gm - om:+.1f}")

    # Extrapolate the full term: the pilot is 260 of 5,548 windows.
    rate = len(pilot) / max(1, len(windows))
    print(f"\n  examples per window: {rate:.1f}  ->  at 5,548 windows that is "
          f"~{rate * 5548:,.0f} examples, ~{rate * 5548 / 132:.0f} per MP")

    # --- overlap with the published six, on CO-SCORED statements ----------
    print("\nOVERLAP (Pearson r on the same statement, both attributes scoring it)")
    acu = {(w, t): s for w, _n, t, s, _e in pilot}
    print(f"{'vs':14s} {'co-scored':>9s} {'r':>7s}")
    worst = 0.0
    for other in ("focus", "civility", "rigor", "specificity"):
        rows = _rows(FULL, other)
        pairs = [(acu[(w, t)], s) for w, _n, t, s, _e in rows
                 if (w, t) in acu]
        if len(pairs) < 30:
            print(f"{other:14s} {len(pairs):9d} {'--':>7s}  (under 30)")
            continue
        r = _pearson([a for a, _ in pairs], [c for _, c in pairs])
        worst = max(worst, abs(r or 0))
        flag = "  <-- REDUNDANT" if abs(r or 0) >= 0.65 else ""
        print(f"{other:14s} {len(pairs):9d} {r:7.2f}{flag}")

    # --- is this just Forthrightness again? -------------------------------
    # The trap we are trying to escape. Forthrightness scores a minister's ANSWER
    # in question time; if Acuity mostly scores the same act, it inherits the
    # same executive-only coverage and there was no point. Joined on the
    # statement text, since the two runs carry no common row id.
    QA = os.path.abspath(os.path.join(HERE, "..", "forthrightness_scores_v3.jsonl"))
    fo = {}
    if os.path.exists(QA):
        for line in open(QA, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = (r.get("statement") or "").strip()
            if t and isinstance(r.get("score"), (int, float)):
                fo[t] = r["score"]
    shared = [(acu[k], fo[k[1]]) for k in acu if k[1] in fo]
    print(f"\nVS FORTHRIGHTNESS (same statement scored by both)")
    print(f"  acuity examples also scored as an ANSWER in question time: "
          f"{len(shared)}/{len(pilot)} ({100 * len(shared) / len(pilot):.0f}%)")
    if len(shared) >= 30:
        r = _pearson([a for a, _ in shared], [f for _, f in shared])
        print(f"  r = {r:.2f}" + ("  <-- measuring the same act" if abs(r) >= 0.65 else ""))
    elif shared:
        print(f"  too few to correlate; the share is the number that matters here")
    # Bench balance among the question-time overlap vs the rest.
    qa_mps = {R.match(n) for _w, n, t, _s, _e in pilot if t in fo}
    qa_mps.discard(None)
    qg = sum(1 for m in qa_mps if pol.get(m, {}).get("party") in GOV)
    print(f"  MPs in that overlap: {len(qa_mps)} — government {qg}, "
          f"opposition {len(qa_mps) - qg}")

    # --- shrinkage and spread, on the pilot's own pool --------------------
    pool = {(m, "acuity"): v for m, v in per.items()}
    adj = bias_adjust.adjust_scores(pool)
    vals = [round(a.adj_mean * 100) for a in adj.values()]
    sh = st.mean(a.shrink for a in adj.values())
    print(f"\nSHRINK/SPREAD (pilot n only — the term would be ~20x this)")
    print(f"  mean shrink: {sh:.2f}   spread {min(vals)}-{max(vals)} "
          f"= {max(vals) - min(vals)} pts")
    raws = [st.mean(v) * 100 for v in per.values() if len(v) >= 2]
    if len(raws) > 5:
        within = st.mean([bias_adjust._var(v) for v in per.values()
                          if len(v) >= 2]) * 10000
        obs = st.pstdev(raws)
        noise = math.sqrt(st.mean([within / len(v) for v in per.values()
                                   if len(v) >= 2]))
        print(f"  observed sd of MP means {obs:.1f}  sampling noise {noise:.1f}  "
              f"true between-MP sd {math.sqrt(max(0.0, obs ** 2 - noise ** 2)):.1f}")

    print("\n" + "=" * 66)
    print("GATES")
    print(f"  both benches covered      {'PASS' if g and o else 'FAIL'}")
    print(f"  max |r| < 0.65            {'PASS' if worst < 0.65 else 'FAIL'}  ({worst:.2f})")
    print(f"  spread > 20 pts           {'PASS' if max(vals) - min(vals) > 20 else 'see note'}"
          f"  ({max(vals) - min(vals)})")
    print(f"  shrink > 0.5              {'PASS' if sh > 0.5 else 'see note'}  ({sh:.2f})")
    print("  NOTE spread and shrink are n-limited in a 1-month pilot; judge them")
    print("       on the extrapolated per-MP n, not on these two numbers.")


if __name__ == "__main__":
    main()
