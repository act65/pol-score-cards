"""Gate report for the Calibration pilot (2025-10, 260 windows, attribute alone).

Four gates from ATTRIBUTES.md, plus the two prompt-specific failure modes that
would be OUR fault rather than the model's:

  1. a vagueness detector  — "there may possibly be some effects" must sit ~0.3
  2. a conviction penalty  — a `value` clearly marked as the speaker's own is 1.0

Run:  python pilot_calibration/analyse.py
"""
import collections
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PILOT = os.path.join(HERE, "calibration_pilot.jsonl")
FULL = os.path.join(ROOT, "hansard_scores_v3.jsonl")
ACUITY = os.path.join(ROOT, "acuity_scores_v3.jsonl")
POLS = os.path.join(ROOT, "site_data_v3", "politicians.jsonl")
GOVT = {"National", "ACT", "ACT New Zealand", "New Zealand First", "NZ First"}


def _rows(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _examples(path, attr):
    for r in _rows(path):
        for e in (r.get("examples_by_attribute") or {}).get(attr, []):
            yield r.get("window_id"), e


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def main():
    if not os.path.exists(PILOT):
        raise SystemExit(f"no pilot output at {PILOT}")
    pols = {p["name"]: p for p in _rows(POLS)}
    wins = {w for w, _ in _examples(PILOT, "calibration")}
    ex = [e for _, e in _examples(PILOT, "calibration")]
    n_windows = len(_rows(PILOT))
    print(f"=== CALIBRATION PILOT — 2025-10 ===")
    print(f"{n_windows} windows, {len(ex)} examples "
          f"= {len(ex) / max(1, n_windows):.2f}/window   (acuity pilot: 1.75)")

    scored = [e for e in ex if e.get("score") is not None]
    sc = [e["score"] for e in scored]
    if not sc:
        raise SystemExit("no scored examples")
    print(f"\nscores: mean {statistics.mean(sc) * 100:.0f}, "
          f"median {statistics.median(sc) * 100:.0f}, "
          f"sd {statistics.stdev(sc) * 100:.0f}")
    print("  dist:", {round(k, 1): v for k, v in
                      sorted(collections.Counter(round(s, 1) for s in sc).items())})

    # --- prompt compliance: claim_class ---
    have = sum(1 for e in ex if (e.get("claim_class") or "").strip())
    print(f"\nclaim_class present: {have}/{len(ex)}  "
          f"({have / len(ex) * 100:.0f}%)   REQUIRED by the prompt")
    cls = collections.Counter()
    for e in ex:
        c = (e.get("claim_class") or "").split(";")[0].strip().lower()
        cls[c or "(missing)"] += 1
    print("  classes:", dict(cls.most_common()))

    print("\n  mean score BY CLASS — the prompt's own logic, tested:")
    by = collections.defaultdict(list)
    for e in scored:
        c = (e.get("claim_class") or "").split(";")[0].strip().lower()
        by[c or "(missing)"].append(e["score"] * 100)
    for c, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"    {c:22s} n={len(v):4d}  mean {statistics.mean(v):5.1f}")
    print("    EXPECTED: value and settled_fact high (they are markable),")
    print("              forecast lowest (hardest to be certain about).")
    print("    IF `value` IS LOW the prompt penalises conviction — our bug.")

    # --- gates ---
    per = collections.defaultdict(list)
    for e in scored:
        per[e.get("politician", "?")].append(e["score"] * 100)
    MIN = 4
    elig = {m: v for m, v in per.items() if len(v) >= MIN}
    print(f"\n=== GATES (MPs with >={MIN} examples: {len(elig)}) ===")
    bench = collections.Counter()
    for m in elig:
        p = pols.get(m, {}).get("party")
        bench["govt" if p in GOVT else "opp" if p else "off-roster"] += 1
    print(f"1) BENCH COVERAGE  {dict(bench)}        gate: both benches")

    means = {m: statistics.mean(v) for m, v in elig.items()}
    vals = sorted(means.values())
    print(f"2) SPREAD          {vals[-1] - vals[0]:.0f} pts "
          f"(min {vals[0]:.0f}, max {vals[-1]:.0f})      gate >20")

    ov = statistics.variance(list(means.values()))
    nv = statistics.mean([statistics.variance(v) / len(v)
                          for v in elig.values() if len(v) > 1])
    bv = max(0.0, ov - nv)
    print(f"3) SHRINK          {bv / (bv + nv):.2f}                      gate >0.5")
    print(f"   true between-MP sd {math.sqrt(bv):.1f} vs sampling noise "
          f"{math.sqrt(nv):.1f}")

    print(f"4) CORRELATION (statement-level text join)      gate |r|<0.65")
    mine = {e["statement"].strip(): e["score"] for e in scored}
    worst = 0.0
    others = collections.defaultdict(dict)
    for path in (FULL, ACUITY):
        if not os.path.exists(path):
            continue
        for r in _rows(path):
            for a, exs in (r.get("examples_by_attribute") or {}).items():
                for e in exs:
                    if e.get("score") is not None:
                        others[a][e["statement"].strip()] = e["score"]
    for a in sorted(others):
        shared = set(mine) & set(others[a])
        if len(shared) < 30:
            print(f"   calibration~{a:12s} only {len(shared)} shared")
            continue
        r = _pearson([mine[s] for s in shared], [others[a][s] for s in shared])
        worst = max(worst, abs(r))
        print(f"   calibration~{a:12s} r={r:+.2f}  n={len(shared)}")
    print(f"   max |r| = {worst:.2f}")

    g = [means[m] for m in elig if pols.get(m, {}).get("party") in GOVT]
    o = [means[m] for m in elig if m in pols and pols[m]["party"] not in GOVT]
    if g and o:
        print(f"\nBENCH MEANS  govt {statistics.mean(g):.0f} (n={len(g)})  "
              f"opp {statistics.mean(o):.0f} (n={len(o)})  "
              f"gap {statistics.mean(g) - statistics.mean(o):+.0f}")
        print("  (both benches overclaim; a large gap means the prompt is "
              "reading role, not posture)")

    print("\n=== FAILURE MODE 1: is it just a vagueness detector? ===")
    print("  lowest-scoring examples — these should be OVERCLAIMS, not mush:")
    for e in sorted(scored, key=lambda x: x["score"])[:6]:
        print(f"    [{e['score']:.1f}] {(e.get('claim_class') or '?')[:34]:34s} "
              f"{e['statement'][:88]}")
    print("\n  highest-scoring — should include FIRM claims, not only hedged ones:")
    for e in sorted(scored, key=lambda x: -x["score"])[:6]:
        print(f"    [{e['score']:.1f}] {(e.get('claim_class') or '?')[:34]:34s} "
              f"{e['statement'][:88]}")


if __name__ == "__main__":
    main()
