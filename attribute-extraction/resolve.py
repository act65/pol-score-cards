"""Resolve Veracity claims and Divination predictions against real sources.

Extraction emits a claim plus the `falsification_criterion` that would settle
it, and leaves `score` empty. This searches the web for that evidence and
assigns the score — which is what moves both attributes out of the "ungrounded
LLM plausibility" tier.

    cd attribute-extraction
    python resolve.py run --scores hansard_scores_v3.jsonl --limit 40
    python resolve.py compare --out GUESS_VS_SEARCH.md   # is searching worth it?

**The confirmation-bias controls, and why each exists:**

* The criterion was written at EXTRACTION time, before anything was looked up,
  so the resolver is checking against a standard it cannot tune to whatever it
  happens to find.
* The resolver **never sees `prior_score`**. Anchoring on a prior judgement is
  the exact failure being guarded against, so the guess is withheld from the
  prompt and only rejoined afterwards for the comparison.
* Verdicts must cite the URLs they relied on. A resolved score that cannot show
  its working is worse than no score.
* `uncheckable` and `not_yet_due` are first-class outcomes. **Failing to find
  evidence is not evidence of falsity**, and must never become a low score.

`compare` answers the question that decides whether any of this is worth the
quota: how far apart are the unaided guess and the searched verdict? If they
agree almost everywhere, searching buys little and the guess is good enough.
"""

from __future__ import annotations

import collections
import json
import math
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import fire
from pydantic import BaseModel, Field

import claude_cli

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "resolved_v3.jsonl")

# Verdicts that carry a score, and those that deliberately do not.
SCORED_VERDICTS = {"true", "false", "partly_true", "correct", "wrong",
                   "partly_correct"}
UNSCORED_VERDICTS = {"uncheckable", "not_yet_due"}

# Verdict -> score. Kept as a table rather than letting the model pick a number:
# the model's job is the judgement, and a fixed mapping stops verdict and score
# drifting apart between calls.
VERDICT_SCORE = {
    "true": 1.0, "correct": 1.0,
    "partly_true": 0.5, "partly_correct": 0.5,
    "false": 0.0, "wrong": 0.0,
}


class _Verdict(BaseModel):
    item_id: str = Field(description="Echo the id you were given.")
    verdict: str = Field(description="true | partly_true | false | correct | "
                                     "partly_correct | wrong | uncheckable | "
                                     "not_yet_due")
    reasoning: str = Field(description="What the evidence shows, briefly.")
    sources: List[str] = Field(default_factory=list,
                               description="URLs actually relied on.")


_SYSTEM = """You are a careful fact-checker for a New Zealand politics project.

For each item you are given a QUOTE from a politician and a CRITERION that was
written down BEFORE any research happened — it says what evidence would make the
claim true and what would make it false. Your job is to search for that evidence
and return a verdict against that criterion, not against a standard of your own.

RULES

1. SEARCH FIRST. Do not answer from memory. Use the web.
2. Build queries from the SUBJECT of the claim, never from its direction.
   Searching "X does not exist" and searching "X population status" return
   different internets, and the first one finds what it went looking for.
3. Judge against the CRITERION AS WRITTEN. If the criterion names a source, go
   to that source. Do not substitute an easier question.
4. LOOK FOR DISCONFIRMING EVIDENCE TOO. Before settling on a verdict, ask what
   you would expect to find if the opposite were true, and check for it.
5. CITE THE URLS you actually relied on. A verdict with no sources is not a
   verdict.
6. If the evidence is genuinely not findable, return `uncheckable`. If the
   claim is a prediction whose date has not passed, return `not_yet_due`.
   NEITHER IS A FAILING GRADE. Not finding evidence is not evidence of falsity,
   and saying so is a correct answer, not a cop-out.

VERDICTS
  For factual claims:  true | partly_true | false | uncheckable
  For predictions:     correct | partly_correct | wrong | not_yet_due | uncheckable

`partly_true` / `partly_correct` means the substance holds but is materially
overstated, or true only under a reading the speaker did not signal.
"""

_INSTRUCTION = ("\n\nReturn one verdict per item, echoing `item_id` exactly. "
                "Search before answering. Cite the URLs you used.")


def _rows_from(path: str):
    """Yield {window_id, date, examples_by_attribute} from either input shape.

    Extraction writes JSONL; `compare_models.py` writes a single JSON object
    whose `results` carry the same per-window examples. Reading both means the
    guess-vs-search test can reuse claims the bake-off already extracted instead
    of paying to extract them again.
    """
    with open(path) as f:
        head = f.read(1)
        f.seek(0)
        if head == "{" and path.endswith(".json"):
            data = json.load(f)
            ref = data.get("reference")
            for r in data.get("results", []):
                # One model only, or the same claim appears once per model.
                if "error" in r or (ref and r.get("model") != ref):
                    continue
                if r.get("repeat", 0) != 0:
                    continue
                yield {"window_id": f"{r['window_id']}@{r['model']}",
                       "date": r["window_id"][:10],
                       "examples_by_attribute": r.get("examples", {})}
            return
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_pending(scores: str, attributes: tuple = ("veracity", "divination"),
                 limit: int = 0) -> list[dict]:
    """Unresolved search-tier rows from an extraction or comparison file."""
    out = []
    for row in _rows_from(scores):
        date = row.get("date") or (row.get("window_id") or "")[:10]
        for attr, examples in (row.get("examples_by_attribute") or {}).items():
            if attr not in attributes:
                continue
            for i, ex in enumerate(examples or []):
                if ex.get("score") is not None:
                    continue                      # already resolved
                if not ex.get("falsification_criterion"):
                    continue                      # nothing to check against
                out.append({
                    "item_id": f"{row.get('window_id')}|{attr}|{i}",
                    "attribute": attr, "date": date,
                    "politician": ex.get("politician"),
                    "statement": ex.get("statement"),
                    "criterion": ex["falsification_criterion"],
                    "resolve_by": ex.get("resolve_by"),
                    # Withheld from the prompt; rejoined only for `compare`.
                    "prior_score": ex.get("prior_score"),
                })
    return out[:limit] if limit else out


def _render(batch: list[dict]) -> str:
    parts = []
    for it in batch:
        kind = "PREDICTION" if it["attribute"] == "divination" else "FACTUAL CLAIM"
        block = [f"--- item {it['item_id']} ({kind}) ---",
                 f"Speaker: {it.get('politician') or 'unknown'}",
                 f"Said on: {it.get('date') or 'unknown'}",
                 f"Quote: {it['statement']}",
                 f"Criterion (written before any research): {it['criterion']}"]
        if it.get("resolve_by"):
            block.append(f"Resolve by: {it['resolve_by']}")
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def _saved(path: str) -> set:
    ids = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    try:
                        ids.add(json.loads(line)["item_id"])
                    except Exception:
                        pass
    return ids


def run(scores: str = "hansard_scores_v3.jsonl", out: str = DEFAULT_OUT,
        per_call: int = 3, workers: int = 3, limit: int = 0,
        model: str = "claude-opus-4-8", timeout: int = 600,
        dry_run: bool = False, attrs: str = "veracity,divination") -> None:
    """Resolve pending veracity/divination items against searched sources.

    `--attrs divination` runs one attribute at a time. Divination is the one to
    resolve first: it is the smaller set by an order of magnitude (110 pending
    against 1,109), and it is the attribute least able to survive on a guess —
    "did it come true" has an answer in the world, and a model's unaided hunch
    about it carries no information the reader could check.
    """
    chosen = tuple(a.strip() for a in attrs.split(",") if a.strip())
    scores = scores if os.path.isabs(scores) else os.path.join(HERE, scores)
    out = out if os.path.isabs(out) else os.path.join(HERE, out)

    items = load_pending(scores, attributes=chosen, limit=limit)
    done = _saved(out)
    todo = [it for it in items if it["item_id"] not in done]
    batches = [todo[i:i + per_call] for i in range(0, len(todo), per_call)]

    if dry_run:
        print(f"=== resolver DRY RUN ({model}) ===")
        print(f"pending: {len(items):,}   done: {len(done):,}   "
              f"to do: {len(todo):,}   calls: {len(batches):,}")
        by_attr = collections.Counter(it["attribute"] for it in todo)
        print(f"by attribute: {dict(by_attr)}")
        return

    print(f"{len(todo)} items in {len(batches)} calls ({workers} workers)")
    lock = threading.Lock()
    written = 0

    def work(batch):
        # Web search requires the CLI's tools; the API path has no browser.
        return claude_cli.call_structured_searching(
            _SYSTEM, _render(batch), {"type": "object", "properties": {
                "verdicts": {"type": "array", "items": _Verdict.model_json_schema()}},
                "required": ["verdicts"]},
            model=model, instruction=_INSTRUCTION, timeout=timeout)

    with open(out, "a") as fh, ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, b): b for b in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            by_id = {it["item_id"]: it for it in batch}
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"error: {e}", flush=True)
                continue
            with lock:
                for v in (result or {}).get("verdicts", []) or []:
                    it = by_id.get(v.get("item_id"))
                    if not it:
                        continue
                    verdict = str(v.get("verdict", "")).strip().lower()
                    fh.write(json.dumps({
                        **{k: it[k] for k in ("item_id", "attribute", "date",
                                              "politician", "statement",
                                              "criterion", "prior_score")},
                        "verdict": verdict,
                        # uncheckable / not_yet_due stay unscored on purpose.
                        "resolved_score": VERDICT_SCORE.get(verdict),
                        "reasoning": v.get("reasoning", ""),
                        "sources": v.get("sources", []),
                    }, ensure_ascii=False) + "\n")
                    written += 1
                fh.flush()
                print(f"[{written}/{len(todo)}] resolved", flush=True)

    print(f"done: wrote {written} verdicts -> {out}")
    compare(out)


# --- is searching worth it? --------------------------------------------------

def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def compare(path: str = DEFAULT_OUT, out: str | None = None) -> None:
    """How far apart are the unaided guess and the searched verdict?

    This is the decision, not a curiosity. Searching costs a web round-trip per
    claim across thousands of claims; if the guess tracks the verdict closely it
    is not worth it.
    """
    path = path if os.path.isabs(path) else os.path.join(HERE, path)
    with open(path) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if not rows:
        raise SystemExit(f"no verdicts in {path}")

    paired = [r for r in rows
              if r.get("resolved_score") is not None and r.get("prior_score") is not None]
    L = ["# Guess vs search", "",
         "Does searching for evidence beat the model's unaided guess? The guess "
         "(`prior_score`) was written at extraction time, before any lookup, and "
         "was withheld from the resolver — so these are independent.", "",
         f"{len(rows)} verdicts; {len(paired)} have both a guess and a resolved "
         f"score.", ""]

    verdicts = collections.Counter(r["verdict"] for r in rows)
    L += ["## Verdicts", "", "| verdict | n | share |", "|---|---:|---:|"]
    for v, n in verdicts.most_common():
        L.append(f"| {v} | {n} | {100 * n / len(rows):.0f}% |")
    unscored = sum(n for v, n in verdicts.items() if v in UNSCORED_VERDICTS)
    L += ["", f"**{100 * unscored / len(rows):.0f}% returned no score** "
              "(`uncheckable` / `not_yet_due`). That is a real answer, not a "
              "failure — but it is also the share of claims where searching "
              "bought nothing.", ""]

    if paired:
        gaps = [abs(r["prior_score"] - r["resolved_score"]) for r in paired]
        r = _pearson([x["prior_score"] for x in paired],
                     [x["resolved_score"] for x in paired])
        agree = sum(1 for g in gaps if g <= 0.25)
        flips = [x for x in paired
                 if abs(x["prior_score"] - x["resolved_score"]) >= 0.5]
        L += ["## Agreement", "",
              "| metric | value |", "|---|---:|",
              f"| Pearson r (guess vs searched) | {r:.2f} |" if r is not None
              else "| Pearson r | too few |",
              f"| mean absolute gap | {statistics.mean(gaps):.3f} |",
              f"| median absolute gap | {statistics.median(gaps):.3f} |",
              f"| agree within 0.25 | {100 * agree / len(paired):.0f}% |",
              f"| disagree by >= 0.5 | {len(flips)} of {len(paired)} |", "",
              "**How to read this.** A high `r` with a small gap means the guess "
              "already tracks the evidence, and the search is an expensive way to "
              "confirm what the model knew. A low `r`, or a handful of large "
              "flips, means the guess is confidently wrong somewhere — which is "
              "exactly the failure mode the site cannot afford, and justifies the "
              "cost.", ""]
        if flips:
            L += ["### Where the guess was confidently wrong", ""]
            for x in flips[:10]:
                L.append(f"- **{x['attribute']}** / {x.get('politician')} — "
                         f"guessed {x['prior_score']:.2f}, resolved "
                         f"{x['resolved_score']:.2f} (`{x['verdict']}`)")
                L.append(f"  > {(x['statement'] or '')[:180]}")
                if x.get("sources"):
                    L.append(f"  source: {x['sources'][0]}")
            L.append("")

    cited = sum(1 for r in rows if r.get("sources"))
    L += ["## Sourcing", "",
          f"{cited}/{len(rows)} verdicts cite at least one URL "
          f"({100 * cited / len(rows):.0f}%). A resolved score with no source "
          "cannot be audited by a reader and should not be published.", ""]

    text = "\n".join(L)
    print(text)
    if out:
        p = out if os.path.isabs(out) else os.path.join(HERE, out)
        with open(p, "w") as f:
            f.write(text + "\n")
        print(f"\nwrote {p}")


if __name__ == "__main__":
    fire.Fire({"run": run, "compare": compare, "load_pending": load_pending})
