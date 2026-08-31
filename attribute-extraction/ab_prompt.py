"""Does moving the rubric into --system-prompt change WHAT we extract?

    python ab_prompt.py run --n 12          # spends quota — scheduled window only
    python ab_prompt.py report

Re-scores windows that are ALREADY in hansard_scores_v3.jsonl, twice: once the
way the corpus was built (rubric prepended to the user message), once with the
rubric passed as --system-prompt. Nothing is written to the dataset; both arms
go to ab_prompt_A.jsonl / ab_prompt_B.jsonl.

## Why

usage_v3.jsonl over 294 window calls (2026-08-19..24) shows where the
subscription actually goes, and it is not where I argued from cap timings:

    output           3,131,511 tok   65.1% of weighted cost
    cache_creation   7,794,798 tok   32.4%
    cache_read       5,929,542 tok    2.5%
    fresh input            588 tok    0.0%

cache_read is pinned at exactly 20,611 per call and fresh input at 2 tokens, so
the prefix IS being cached — my "not cached" reading of the cap timings was
wrong. But 20,611 is the CLI's OWN default system prompt, which extraction does
not use, and cache_creation runs at 26,512 per call: we pay to write a cache
entry nothing reads back, because the unique window text sits inside the same
cached span as the rubric.

--system-prompt should fix both at once: it replaces the CLI default (removing
20.6k of unused instruction) and makes the rubric a stable prefix that can
actually be reused.

## What has to hold

Cheaper is worthless if it extracts differently. The arms are compared on the
things the instrument is made of — how many statements, which statements, and
what scores — not on cost alone. The threshold is deliberately strict: this
would be the third instrument change in a fortnight, and a dataset half-built
under each is worth less than either.
"""

from __future__ import annotations

import collections
import json
import os
import statistics
import sys

import fire

import attributes
import claude_cli
import extract
import extract_hansard
import hansard_prep

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = "../data/corpus/hansard_v2.json"
SCORES = "hansard_scores_v3.jsonl"
A_OUT = "ab_prompt_A.jsonl"          # as the corpus was built
B_OUT = "ab_prompt_B.jsonl"          # rubric via --system-prompt


def _pick(n, seed_skip=0):
    """n windows already scored, spread across the corpus rather than clustered."""
    rows = [json.loads(l) for l in open(os.path.join(HERE, SCORES)) if l.strip()]
    rows.sort(key=lambda r: r["window_id"])
    step = max(1, len(rows) // n)
    return [r["window_id"] for r in rows[seed_skip::step]][:n]


def _window_text(wid, window_tokens=3000):
    date = wid.split("#")[0]
    by_day = extract_hansard._load_by_day(os.path.join(HERE, CORPUS), date, date)
    if date not in by_day:
        return None
    wins = extract_hansard._windows(hansard_prep.prep_day(by_day[date]), window_tokens)
    idx = int(wid.split("#")[1])
    return wins[idx] if idx < len(wins) else None


def run(n: int = 12, model: str = "claude-opus-5", window_tokens: int = 3000,
        timeout: int = 900) -> None:
    """Score n already-scored windows under both prompt arrangements."""
    wids = _pick(n)
    print(f"A/B over {len(wids)} windows already in {SCORES}\n"
          f"  arm A: rubric prepended to the user message (how the corpus was built)\n"
          f"  arm B: rubric via --system-prompt\n", flush=True)

    prompts = os.path.join(HERE, "prompts")
    attrs = list(attributes.EXTRACTED_IN_WINDOWS)
    system = extract.build_combined_system(attrs, prompts)

    for arm, out, flag in (("A", A_OUT, "0"), ("B", B_OUT, "1")):
        done = set()
        path = os.path.join(HERE, out)
        if os.path.exists(path):
            done = {json.loads(l)["window_id"] for l in open(path) if l.strip()}
        os.environ["CLAUDE_CLI_SYSTEM_FLAG"] = flag
        os.environ["CLAUDE_CLI_USAGE_LOG"] = os.path.join(HERE, f"ab_usage_{arm}.jsonl")
        fails = 0
        with open(path, "a", encoding="utf-8") as fh:
            for i, wid in enumerate(wids, 1):
                if wid in done:
                    continue
                text = _window_text(wid, window_tokens)
                if not text:
                    print(f"  [{arm} {i}/{len(wids)}] {wid}: not rebuildable, skipped")
                    continue
                try:
                    got = extract.extract_all_attributes(
                        None, system, {"date": wid.split("#")[0], "content": text},
                        set(attrs), model=model, backend="claude_cli",
                        timeout=timeout)
                except claude_cli.QuotaExhausted:
                    # Exit EX_QUOTA (75), not 0. Returning quietly told the
                    # runner "finished, wrote nothing", which is indistinguishable
                    # from success and defeats its quota accounting.
                    print(f"  [{arm} {i}/{len(wids)}] {wid}: quota exhausted "
                          f"— stopping; rerun to resume", flush=True)
                    raise SystemExit(75)
                except TypeError:
                    # A signature mismatch is a BUG, not a transient failure, and
                    # swallowing it cost two whole nights on 2026-08-25/26: every
                    # call raised, the broad `except` logged and continued, the
                    # stage never reported EX_DONE, and it blocked `windows` in
                    # the rotation for 8 hours. Crash instead.
                    raise
                except Exception as exc:            # noqa: BLE001
                    print(f"  [{arm} {i}/{len(wids)}] {wid}: FAILED {exc}", flush=True)
                    fails += 1
                    if fails >= 3 and not (_load(A_OUT) or _load(B_OUT)):
                        raise SystemExit(
                            f"\n{fails} consecutive failures and nothing written "
                            f"— aborting rather than burning the night retrying.")
                    continue
                fails = 0
                total = sum(len(v) for v in got.values())
                # Example is a pydantic model, not a dict — mirror how
                # extract_hansard writes the real corpus (model_dump). Getting
                # this wrong cost four nights: my test asserted `.statement`,
                # which a model object satisfies, so it never touched the write.
                fh.write(json.dumps(
                    {"window_id": wid, "arm": arm,
                     "examples_by_attribute": {a: [e.model_dump() for e in exs]
                                               for a, exs in got.items()}},
                    ensure_ascii=False) + "\n")
                fh.flush()
                print(f"  [{arm} {i}/{len(wids)}] {wid}: {total} examples", flush=True)
    # Tell the scheduler the stage is finished so it drops out of the rotation
    # and hands the rest of the night back to `windows` (see overnight_run).
    if len(_load(A_OUT)) >= len(wids) and len(_load(B_OUT)) >= len(wids):
        print("\nboth arms complete — now: python ab_prompt.py report")
        raise SystemExit(64)
    print("\npartial — rerun to resume; then: python ab_prompt.py report")


def _load(path):
    p = os.path.join(HERE, path)
    if not os.path.exists(p):
        return {}
    out = {}
    for line in open(p, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            out[r["window_id"]] = r["examples_by_attribute"]
    return out


def _usage(arm):
    p = os.path.join(HERE, f"ab_usage_{arm}.jsonl")
    if not os.path.exists(p):
        return None
    rows = [json.loads(l) for l in open(p) if l.strip()]
    if not rows:
        return None
    n = len(rows)
    g = lambda k: sum(r.get(k) or 0 for r in rows) / n   # noqa: E731
    return {"calls": n, "output": g("output"), "cache_read": g("cache_read"),
            "cache_creation": g("cache_creation"), "input": g("input"),
            "secs": g("duration_ms") / 1000}


def report(out: str = "") -> None:
    """Compare the two arms. Spends nothing."""
    A, B = _load(A_OUT), _load(B_OUT)
    shared = sorted(set(A) & set(B))
    lines = []
    def say(s=""):
        print(s)
        lines.append(s)

    if not shared:
        say("no windows scored under both arms yet — run `ab_prompt.py run` first")
        return

    say(f"# Prompt-placement A/B\n")
    say(f"{len(shared)} windows scored under both arms.\n")
    say("A = rubric prepended to the user message (how the corpus was built)")
    say("B = rubric passed as --system-prompt\n")

    # --- cost ---------------------------------------------------------------
    ua, ub = _usage("A"), _usage("B")
    if ua and ub:
        say("## Cost per call\n")
        say(f"| | A | B | change |")
        say(f"|---|---:|---:|---:|")
        for key, label in (("output", "output tok"), ("cache_read", "cache read"),
                           ("cache_creation", "cache write"), ("input", "fresh in"),
                           ("secs", "seconds")):
            d = (100 * (ub[key] - ua[key]) / ua[key]) if ua[key] else 0
            say(f"| {label} | {ua[key]:,.0f} | {ub[key]:,.0f} | {d:+.0f}% |")
        wa = (ua["output"] * 75 + ua["cache_creation"] * 15 + ua["cache_read"] * 1.5
              + ua["input"] * 15) / 1e6
        wb = (ub["output"] * 75 + ub["cache_creation"] * 15 + ub["cache_read"] * 1.5
              + ub["input"] * 15) / 1e6
        say(f"\nWeighted at public list rates, B costs **{100 * wb / wa:.0f}%** of A "
            f"per call — about **{wa / wb:.2f}x** the throughput for the same cap.\n")

    # --- did it extract the same things? ------------------------------------
    say("## Is it the same instrument?\n")
    na = sum(len(v) for w in shared for v in A[w].values())
    nb = sum(len(v) for w in shared for v in B[w].values())
    say(f"examples: A {na}, B {nb} ({100 * nb / na:.0f}% of A)\n")

    say("| attribute | A | B | statement overlap | r on shared | mean A | mean B |")
    say("|---|---:|---:|---:|---:|---:|---:|")
    overlaps, corrs = [], []
    for attr in sorted({a for w in shared for a in set(A[w]) | set(B[w])}):
        sa = {e["statement"]: e.get("score") for w in shared for e in A[w].get(attr, [])}
        sb = {e["statement"]: e.get("score") for w in shared for e in B[w].get(attr, [])}
        if not sa and not sb:
            continue
        both = set(sa) & set(sb)
        jac = len(both) / len(set(sa) | set(sb)) if (sa or sb) else 0
        overlaps.append(jac)
        pairs = [(sa[s], sb[s]) for s in both
                 if sa[s] is not None and sb[s] is not None]
        r = ""
        if len(pairs) >= 8:
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
            if den:
                rv = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
                corrs.append(rv)
                r = f"{rv:.2f}"
        ma = [v for v in sa.values() if v is not None]
        mb = [v for v in sb.values() if v is not None]
        say(f"| {attr} | {len(sa)} | {len(sb)} | {jac:.2f} | {r or '—'} | "
            f"{statistics.mean(ma):.2f} | {statistics.mean(mb):.2f} |"
            if ma and mb else
            f"| {attr} | {len(sa)} | {len(sb)} | {jac:.2f} | {r or '—'} | — | — |")

    say("\n`statement overlap` is Jaccard on the exact quotes chosen. Two runs of "
        "the SAME prompt do not score 1.00 either — the model is sampled, not "
        "deterministic — so read B against that floor, not against perfection.\n")

    # --- verdict ------------------------------------------------------------
    mean_ov = statistics.mean(overlaps) if overlaps else 0
    mean_r = statistics.mean(corrs) if corrs else float("nan")
    yield_ok = 0.85 <= (nb / na if na else 0) <= 1.15
    say("## Verdict\n")
    say(f"mean statement overlap {mean_ov:.2f}, mean score r {mean_r:.2f}, "
        f"yield ratio {nb / na if na else 0:.2f}\n")
    if yield_ok and mean_ov >= 0.5 and (mean_r >= 0.8 or corrs == []):
        n_done = sum(1 for _ in open(os.path.join(HERE, SCORES), encoding="utf-8"))
        say(f"**Same instrument within sampling noise.** Adopting B is a cost "
            f"change, not a measurement change — the {n_done:,} windows already "
            f"scored stay comparable.")
    else:
        say("**Not established as the same instrument.** Adopting B would make "
            "the corpus a blend, as the Charisma and 14k episodes both did. "
            "Either keep A, or re-extract from scratch under B.")

    if out:
        with open(os.path.join(HERE, out), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nwrote {out}")


if __name__ == "__main__":
    fire.Fire({"run": run, "report": report})
