"""Held-out evaluation of LLM attribute scoring against the testsets/.

For each scoring testset (rows with a ``<attribute>_score`` gold value), we ask
Claude to score the same statement and compare predicted vs gold. Metrics are
pure-Python (no numpy/scipy) so this runs anywhere:

- MAE / RMSE      — average error magnitude on the 0..1 scale
- Pearson r       — linear agreement between predicted and gold scores
- binary accuracy — agreement after thresholding at 0.5 (good vs bad)

The metric functions are independent of any API call, so they're unit-testable
offline (see test_evaluate.py).

    export ANTHROPIC_API_KEY=...
    python evaluate.py run civility
    python evaluate.py run all
"""

import json
import math
import os
from typing import List, Optional

import fire

import extract

TESTSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testsets")

# Maps an attribute to its scoring testset file. Only attributes whose testset
# carries a numeric gold score belong here; detection testsets (evasion,
# integrity) are a separate binary task handled elsewhere.
SCORING_TESTSETS = {
    "civility": "civility_testset.jsonl",
    "veracity": "veracity_testset.jsonl",
}


def _load_jsonl(path: str) -> List[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _gold_score(row: dict) -> Optional[float]:
    """Pull the gold score from a testset row (the key ending in `_score`)."""
    for key, value in row.items():
        if key.endswith("_score") and isinstance(value, (int, float)):
            return float(value)
    return None


# --- pure metric functions (offline-testable) -----------------------------


def mae(pred: List[float], gold: List[float]) -> float:
    return sum(abs(p - g) for p, g in zip(pred, gold)) / len(pred)


def rmse(pred: List[float], gold: List[float]) -> float:
    return math.sqrt(sum((p - g) ** 2 for p, g in zip(pred, gold)) / len(pred))


def pearson(pred: List[float], gold: List[float]) -> Optional[float]:
    n = len(pred)
    if n < 2:
        return None
    mp, mg = sum(pred) / n, sum(gold) / n
    cov = sum((p - mp) * (g - mg) for p, g in zip(pred, gold))
    vp = sum((p - mp) ** 2 for p in pred)
    vg = sum((g - mg) ** 2 for g in gold)
    if vp == 0 or vg == 0:
        return None
    return cov / math.sqrt(vp * vg)


def binary_accuracy(pred: List[float], gold: List[float], threshold: float = 0.5) -> float:
    correct = sum((p >= threshold) == (g >= threshold) for p, g in zip(pred, gold))
    return correct / len(pred)


def metrics(pred: List[float], gold: List[float]) -> dict:
    return {
        "n": len(pred),
        "mae": mae(pred, gold),
        "rmse": rmse(pred, gold),
        "pearson_r": pearson(pred, gold),
        "binary_accuracy": binary_accuracy(pred, gold),
    }


# --- evaluation driver ------------------------------------------------------


def evaluate_attribute(
    attribute: str,
    model: str = extract.DEFAULT_MODEL,
    client: Optional["object"] = None,
    backend: str = "claude_cli",
) -> dict:
    if attribute not in SCORING_TESTSETS:
        raise ValueError(
            f"No scoring testset for '{attribute}'. Available: {sorted(SCORING_TESTSETS)}"
        )
    # The CLI backend authenticates via the Claude subscription (no API credits)
    # and ignores `client`; only build the API client for the 'anthropic' backend.
    if backend == "anthropic":
        client = client or extract._client()
    prompt = extract.load_prompt(attribute)
    rows = _load_jsonl(os.path.join(TESTSET_DIR, SCORING_TESTSETS[attribute]))

    preds, golds, details = [], [], []
    for i, row in enumerate(rows):
        gold = _gold_score(row)
        statement = row.get("statement") or row.get("text", "")
        if gold is None or not statement:
            continue
        print(f"\r[{attribute}/{model}] scoring {i + 1}/{len(rows)}", end=" ", flush=True)
        try:
            result = extract.score_statement(
                client, prompt, statement, model=model, politician=row.get("politician"),
                backend=backend,
            )
        except Exception as e:   # one statement failing shouldn't abort the run
            print(f"\n  ! skipped row {i + 1} ({type(e).__name__}: {str(e)[:80]})")
            continue
        preds.append(result.score)
        golds.append(gold)
        details.append(
            {
                "statement": statement,
                "gold": gold,
                "pred": result.score,
                "error": abs(result.score - gold),
                "explanation": result.explanation,
            }
        )
    print()
    return {"attribute": attribute, "model": model, "metrics": metrics(preds, golds), "details": details}


def _fmt(m: dict) -> str:
    r = f"{m['pearson_r']:.3f}" if m["pearson_r"] is not None else "n/a"
    return (f"n={m['n']:<3d} MAE={m['mae']:.3f} RMSE={m['rmse']:.3f} "
            f"r={r} binacc={m['binary_accuracy']:.3f}")


def run(attribute: str = "all", model: str = extract.DEFAULT_MODEL,
        save_to: str = "eval_report.json", backend: str = "claude_cli"):
    """Evaluate one attribute, or `all` scoring testsets, and write a report.

    backend: 'claude_cli' (subscription, no API credits — default) or 'anthropic'."""
    attrs = sorted(SCORING_TESTSETS) if attribute == "all" else [attribute]
    client = extract._client() if backend == "anthropic" else None

    report = {}
    for attr in attrs:
        result = evaluate_attribute(attr, model=model, client=client, backend=backend)
        report[attr] = result
        print(f"  {attr:14s} {_fmt(result['metrics'])}")

    with open(save_to, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {save_to}")
    return report


def compare(models: str = "claude-opus-4-8,claude-sonnet-4-6,claude-haiku-4-5",
            attribute: str = "all", backend: str = "claude_cli",
            save_to: str = "eval_compare.json"):
    """Score the testsets with several models and print a side-by-side table, so
    you can see whether a cheaper model is good enough for attribute scoring.

        python evaluate.py compare                       # opus vs sonnet vs haiku
        python evaluate.py compare --models claude-haiku-4-5 --attribute civility

    Cost: ~28 calls per model (14 civility + 14 veracity) on the subscription."""
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    attrs = sorted(SCORING_TESTSETS) if attribute == "all" else [attribute]
    client = extract._client() if backend == "anthropic" else None

    report = {}
    for model in model_list:
        report[model] = {}
        for attr in attrs:
            result = evaluate_attribute(attr, model=model, client=client, backend=backend)
            report[model][attr] = result["metrics"]

    # comparison table: one block per attribute, models as rows (best r first)
    print("\n=== model comparison (higher r / binacc, lower MAE = better) ===")
    for attr in attrs:
        print(f"\n[{attr}]")
        rows = sorted(report.items(),
                      key=lambda kv: kv[1][attr]["pearson_r"] or -1, reverse=True)
        for model, by_attr in rows:
            print(f"  {model:22s} {_fmt(by_attr[attr])}")

    with open(save_to, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {save_to}")
    return report


if __name__ == "__main__":
    fire.Fire({"run": run, "evaluate_attribute": evaluate_attribute, "compare": compare})
