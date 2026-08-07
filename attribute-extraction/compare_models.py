"""Can a cheaper model do the extraction? Measure it before committing.

**The question is agreement with a reference, not abstract quality.** Opus 5 is
treated as ground truth; every other model is scored on how closely it
reproduces it. If a cheap model correlates highly with the expensive one AND
quotes properly, there is no reason to pay for the expensive one across 1,127
windows.

That framing matters. Two models can both look "good" on contract compliance and
still disagree with each other about every score — which would make the choice
between them consequential in a way a symmetric comparison would hide.

**It needs no human labels.** Gold labels are still being written, but agreement
with a reference is measurable now, and so is everything below:

* **Quote fidelity** — does the model actually quote verbatim, in whole
  sentences, without splicing? An instruction-following measure with a
  ground truth (the transcript) that requires no judgement.
* **Selectivity** — does it respect the eligibility gates, or does it score
  every statement on every attribute? v2.0 put 84% of statements under two or
  more attributes; the target is under 60%.
* **Attribute independence** — do the nine come out as separate readings, or
  collapse into one "was this good" judgement? Target: max pairwise r < 0.65.
* **Criterion discipline** — for veracity and divination, does it supply a real
  falsification criterion, or does it ignore the instruction and guess a score?
* **Self-consistency** — run the same window twice; how far apart are the
  scores? A model that disagrees with itself cannot agree with a human.
* **Cost** — wall-clock and token throughput per window.

None of this tells you which model is most *accurate* — the reference is another
model, not a human. It tells you whether the cheap one is a faithful substitute,
which is the actual decision. Add accuracy with `--gold` once
`testsets/pool_v3.jsonl` is labelled.

    cd attribute-extraction
    python compare_models.py run --windows 6 --repeats 2
    python compare_models.py run --reference claude-opus-5 \
        --models claude-sonnet-5,claude-opus-4-8 --backend claude_cli
    python compare_models.py report --out MODEL_COMPARISON.md

Spends quota — one call per (window x model x repeat). Keep `--windows` small.
"""

from __future__ import annotations

import collections
import itertools
import json
import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fire

import attribute_overlap
import attributes
import check_quotes
import extract
import hansard_prep

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "data", "corpus", "hansard_v2.json")
DEFAULT_OUT = os.path.join(HERE, "model_comparison.json")

# Opus 5 is the reference: the most capable option, treated as ground truth.
# Everything else is judged on how faithfully it reproduces it — Sonnet 5 above
# all, since that is the one worth switching to if it holds up.
REFERENCE_MODEL = "claude-opus-5"
DEFAULT_MODELS = ("claude-sonnet-5", "claude-opus-4-8")

# Sample from a month that is NOT the pilot month, so the comparison cannot be
# graded on the same text the pilot will be. 2025-10 is the pilot (V3_PLAN §4).
SAMPLE_MONTH = "2024-11"


def _windows(corpus: str, month: str, n: int, window_tokens: int = 6000):
    """A few real Hansard windows, deterministically chosen."""
    by_day = collections.defaultdict(list)
    with open(corpus) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if (r.get("date") or "").startswith(month):
                by_day[r["date"]].append(r)

    out = []
    for date in sorted(by_day):
        blocks = hansard_prep.prep_day(by_day[date])
        cur, tok = [], 0
        for b in blocks:
            piece = f"{b['speaker']}: {b['text']}"
            tok += len(piece) // 4
            cur.append(piece)
            if tok >= window_tokens:
                out.append({"window_id": f"{date}#{len(out)}", "date": date,
                            "content": "\n\n".join(cur)})
                cur, tok = [], 0
                break            # one window per day keeps speakers diverse
        if len(out) >= n:
            break
    return out[:n]


def run(models: str | tuple = DEFAULT_MODELS, windows: int = 6, repeats: int = 2,
        backend: str = extract.DEFAULT_BACKEND, corpus: str = CORPUS,
        month: str = SAMPLE_MONTH, out: str = DEFAULT_OUT,
        reference: str = REFERENCE_MODEL, workers: int = 6,
        window_tokens: int = 3500) -> None:
    """Run each model over the same windows and record everything measurable."""
    if isinstance(models, str):
        models = tuple(m.strip() for m in models.split(",") if m.strip())
    if reference not in models:
        models = (reference,) + tuple(models)
    attrs = sorted(attributes.EXTRACTED_IN_WINDOWS)
    system = extract.build_combined_system(attrs)
    valid = set(attrs)

    sample = _windows(corpus, month, windows, window_tokens)
    if not sample:
        raise SystemExit(f"no windows found for {month} in {corpus}")
    print(f"{len(sample)} windows from {month}; {len(models)} models x {repeats} "
          f"repeats = {len(sample) * len(models) * repeats} calls\n")

    client = extract._client() if backend == "anthropic" else None
    tasks = [(m, rep, w) for m, rep in itertools.product(models, range(repeats))
             for w in sample]

    def work(task):
        model, rep, w = task
        gate = collections.Counter()
        t0 = time.time()
        try:
            by_attr = extract.extract_all_attributes(
                client, system, w, valid, model=model, backend=backend, stats=gate)
        except Exception as e:  # noqa: BLE001
            return {"model": model, "repeat": rep, "window_id": w["window_id"],
                    "error": str(e)}
        return {"model": model, "repeat": rep, "window_id": w["window_id"],
                "seconds": round(time.time() - t0, 1), "gate": dict(gate),
                "examples": {a: [e.model_dump() for e in exs]
                             for a, exs in by_attr.items()}}

    # Each CLI call is its own subprocess, so threads parallelise well. Keep
    # `workers` low on the subscription backend: past ~3 concurrent CLI sessions
    # the calls start queueing behind each other and a batch can appear hung.
    #
    # Results are appended to a JSONL sidecar AS THEY COMPLETE, and already-done
    # (model, repeat, window) triples are skipped on restart. Buffering until the
    # end and writing once is how an earlier scraper threw away 100,989 rows.
    partial = os.path.splitext(out)[0] + ".partial.jsonl"
    done_keys = set()
    if os.path.exists(partial):
        with open(partial) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done_keys.add((r["model"], r["repeat"], r["window_id"]))
        print(f"resuming: {len(done_keys)} calls already in {partial}")
    tasks = [t for t in tasks if (t[0], t[1], t[2]["window_id"]) not in done_keys]

    done = len(done_keys)
    total = done + len(tasks)
    lock = threading.Lock()
    with open(partial, "a") as fh, \
            ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(work, t): t for t in tasks}
        for fut in as_completed(futures):
            r = fut.result()
            with lock:
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                done += 1
                if "error" in r:
                    print(f"  [{done}/{total}] {r['model']} {r['window_id']}: "
                          f"ERROR {r['error'][:100]}", flush=True)
                else:
                    n = sum(len(v) for v in r["examples"].values())
                    print(f"  [{done}/{total}] {r['model']} rep{r['repeat']} "
                          f"{r['window_id']}: {n} kept ({r['seconds']:.0f}s)",
                          flush=True)

    with open(partial) as f:
        results = [json.loads(l) for l in f if l.strip()]
    with open(out, "w") as f:
        json.dump({"models": list(models), "reference": reference, "month": month,
                   "windows": [w["window_id"] for w in sample],
                   "results": results}, f, indent=1)
    print(f"\nwrote {out} ({len(results)} calls)")
    report(out)


# --- analysis ----------------------------------------------------------------

def _by_model(results):
    out = collections.defaultdict(list)
    for r in results:
        if "error" not in r:
            out[r["model"]].append(r)
    return out


def _quote_rates(rows):
    """Re-derive the gate outcome from the raw counters."""
    g = collections.Counter()
    for r in rows:
        g.update(r["gate"])
    considered = g.get("considered", 0)
    kept = sum(v for k, v in g.items() if k.startswith("kept:"))
    quote_bad = sum(v for k, v in g.items() if k.startswith("quote:"))
    missing = sum(v for k, v in g.items() if ":missing_" in k)
    return considered, kept, quote_bad, missing


def _statement_attr_map(rows):
    """{statement_key -> {attribute: score}} across a model's output."""
    per = collections.defaultdict(dict)
    for r in rows:
        for attr, exs in r["examples"].items():
            for e in exs:
                if e.get("score") is None:
                    continue
                per[attribute_overlap._key(e["politician"], e["statement"])][attr] = e["score"]
    return per


def _self_consistency(rows):
    """Mean absolute score gap for the same (statement, attribute) across repeats.

    A model that cannot reproduce its own score on identical input puts a floor
    under how well it can ever agree with a human.
    """
    by_rep = collections.defaultdict(dict)
    for r in rows:
        for attr, exs in r["examples"].items():
            for e in exs:
                if e.get("score") is None:
                    continue
                k = (attribute_overlap._key(e["politician"], e["statement"]), attr)
                by_rep[r["repeat"]][k] = e["score"]
    reps = sorted(by_rep)
    if len(reps) < 2:
        return None, 0
    gaps = []
    a, b = by_rep[reps[0]], by_rep[reps[1]]
    for k in set(a) & set(b):
        gaps.append(abs(a[k] - b[k]))
    return (statistics.mean(gaps) if gaps else None), len(gaps)


def _recall_overlap(rows_a, rows_b):
    """Fraction of A's statements that B also surfaced — extraction stability."""
    sa = {attribute_overlap._key(e["politician"], e["statement"])
          for r in rows_a for exs in r["examples"].values() for e in exs}
    sb = {attribute_overlap._key(e["politician"], e["statement"])
          for r in rows_b for exs in r["examples"].values() for e in exs}
    return (len(sa & sb) / len(sa | sb)) if (sa or sb) else 0.0


def report(path: str = DEFAULT_OUT, out: str | None = None) -> None:
    """Summarise a comparison run."""
    with open(path) as f:
        data = json.load(f)
    grouped = _by_model(data["results"])

    # A run killed part-way through still has results worth reading, so the
    # header is built from whatever the file actually carries.
    windows = data.get("windows") or sorted(
        {r["window_id"] for r in data.get("results", [])})
    L = ["# Model comparison", "",
         f"Sampled {len(windows)} Hansard windows from "
         f"{data.get('month', 'an unrecorded month')} "
         f"(deliberately not the 2025-10 pilot month).",
         "",
         f"**`{data.get('reference')}` is treated as ground truth.** The question "
         "is not which model is best in the abstract — it is whether a cheaper "
         "one reproduces the reference closely enough to use across 1,127 "
         "windows. No human labels are involved, so this measures faithfulness "
         "and contract compliance, not accuracy.", ""]

    L += ["## Contract compliance", "",
          "| model | proposed | kept | quote-gate rejects | missing criterion | "
          "sec/window |", "|---|---:|---:|---:|---:|---:|"]
    for model, rows in grouped.items():
        considered, kept, bad, missing = _quote_rates(rows)
        secs = statistics.mean(r["seconds"] for r in rows) if rows else 0
        L.append(f"| {model} | {considered:,} | {kept:,} "
                 f"({100 * kept / considered:.0f}%) | "
                 f"{100 * bad / considered:.1f}% | "
                 f"{100 * missing / considered:.1f}% | {secs:.0f} |")
    L += ["", "`quote-gate rejects` is the share of proposals thrown away for "
              "paraphrasing, splicing with an ellipsis, or cutting mid-sentence. "
              "**Lower is better** — it is pure instruction-following.", ""]

    L += ["## Attribute independence", "",
          "Max pairwise correlation among co-scored statements. "
          "Target: **< 0.65**.", "",
          "| model | max pairwise r | worst pair | statements 2+ attrs |",
          "|---|---:|---|---:|"]
    for model, rows in grouped.items():
        per = _statement_attr_map(rows)
        by_attr = collections.defaultdict(dict)
        for k, scores in per.items():
            for a, s in scores.items():
                by_attr[a][k] = s
        pairs = [p for p in attribute_overlap.pairwise(by_attr, min_n=8)
                 if p["r"] is not None]
        multi = sum(1 for v in per.values() if len(v) > 1)
        if pairs:
            worst = max(pairs, key=lambda p: p["r"])
            L.append(f"| {model} | {worst['r']:.2f} | {worst['a']}/{worst['b']} | "
                     f"{100 * multi / len(per):.0f}% |")
        else:
            L.append(f"| {model} | — | too few co-scored | "
                     f"{100 * multi / max(1, len(per)):.0f}% |")
    L += ["", "*Small samples make these noisy — read them as a smoke test for a "
              "model that has collapsed the attributes, not as the final number. "
              "`attribute_overlap.py` on a full run is the real measurement.*", ""]

    L += ["## Self-consistency", "",
          "Mean absolute gap between two runs of the same model on identical "
          "input. **Lower is better**; this is a floor on agreement with any "
          "human.", "",
          "| model | mean gap | statements compared |", "|---|---:|---:|"]
    for model, rows in grouped.items():
        gap, n = _self_consistency(rows)
        L.append(f"| {model} | {gap:.3f} | {n} |" if gap is not None
                 else f"| {model} | — (need repeats ≥ 2) | {n} |")
    L.append("")

    ref = data.get("reference")
    if ref in grouped and len(grouped) > 1:
        L += [f"## Agreement with the reference (`{ref}`)", "",
              "**This is the decision.** Opus 5 is treated as ground truth; a "
              "cheaper model is a viable substitute if it scores the same "
              "statements the same way. Two models can each look fine on "
              "compliance and still disagree with each other about everything, "
              "which is what this catches.", "",
              "| model | statement overlap | scored in common | Pearson r | mean gap | agree ±0.25 |",
              "|---|---:|---:|---:|---:|---:|"]
        ref_scores = _statement_attr_map(grouped[ref])
        for model, rows in grouped.items():
            if model == ref:
                continue
            mine = _statement_attr_map(rows)
            xs, ys = [], []
            for key in set(ref_scores) & set(mine):
                for attr in set(ref_scores[key]) & set(mine[key]):
                    xs.append(ref_scores[key][attr])
                    ys.append(mine[key][attr])
            r = attribute_overlap.pearson(xs, ys)
            overlap = _recall_overlap(grouped[ref], rows)
            if xs:
                gaps = [abs(a - b) for a, b in zip(xs, ys)]
                agree = 100 * sum(1 for g in gaps if g <= 0.25) / len(gaps)
                L.append(f"| {model} | {overlap:.2f} | {len(xs)} | "
                         f"{f'{r:.2f}' if r is not None else '—'} | "
                         f"{statistics.mean(gaps):.3f} | {agree:.0f}% |")
            else:
                L.append(f"| {model} | {overlap:.2f} | 0 | — | — | — |")
        L += ["", "`statement overlap` is Jaccard over which statements each "
                  "model chose to extract at all. **It caps everything else** — "
                  "a model that agrees perfectly on the 30% of statements it "
                  "also surfaced is still producing a different dataset. Read "
                  "this column first.", "",
              "Rough bar for switching: overlap ≥ 0.6, `r` ≥ 0.85, mean gap "
              "≤ 0.10, and a quote-gate reject rate no worse than the "
              "reference's.", ""]

    errors = [r for r in data["results"] if "error" in r]
    if errors:
        L += [f"## Errors ({len(errors)})", ""]
        for e in errors[:10]:
            L.append(f"- {e['model']} {e['window_id']}: {e['error'][:160]}")
        L.append("")

    text = "\n".join(L)
    print(text)
    if out:
        p = out if os.path.isabs(out) else os.path.join(HERE, out)
        with open(p, "w") as f:
            f.write(text + "\n")
        print(f"\nwrote {p}")


if __name__ == "__main__":
    fire.Fire({"run": run, "report": report})
