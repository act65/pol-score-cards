"""Sample real statements from the corpus to build labelling pools for evaluation.

**Why this exists.** Every testset in `testsets/` is *synthetic* — invented
statements attributed to "Senator Armstrong", "Governor Miller",
"Councilperson Davis". None of it is New Zealand, and none of it is Hansard. The
headline civility `r`=0.88 in `EVALUATION.md` was measured on made-up American
statements, so it says nothing about performance on the register we actually
score: adversarial NZ parliamentary speech. Fixing the sample size without
fixing the distribution would not help.

This draws candidate statements from the real corpus, stratified so the pool is
not accidentally all ministers or all one month, and emits them **unlabelled**
for a human to score. It never invents a gold label.

    cd attribute-extraction
    python build_testsets.py sample --n 120 --out testsets/pool_v3.jsonl
    python build_testsets.py check_leakage          # prompts vs testsets
    python build_testsets.py split_stats testsets/pool_v3.jsonl

**The dev/test split is deterministic**, derived from a hash of the statement
id, so it never drifts as rows are added and cannot be re-rolled to flatter a
prompt. Iterate prompts on `dev`; touch `test` once, at the end (see
`V3_PLAN.md` §3.4).

Deterministic: no LLM, no network.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "prompts")
TESTSETS = os.path.join(HERE, "testsets")
CORPUS = os.path.join(HERE, "..", "data", "corpus")
ROSTER = os.path.join(HERE, "..", "data", "mps_roster.json")

# The roster and its name-matching rules live with the data pipelines; import
# them rather than keeping a sixth near-copy (see data/names.py).
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "data")))
from names import RosterIndex, clean as clean_speaker, norm as _norm  # noqa: E402

# Fraction of the pool reserved for the untouchable held-out set.
TEST_FRACTION = 0.4

# A labelling item should be a self-contained thought: long enough to judge,
# short enough that a human is scoring one thing.
MIN_CHARS, MAX_CHARS = 120, 600

sys.path.insert(0, HERE)


def statement_id(speaker: str, text: str) -> str:
    """Stable id from content, so the same statement always lands in the same
    split no matter when it was sampled."""
    h = hashlib.sha256(f"{speaker}|{text}".encode()).hexdigest()
    return h[:16]


def assign_split(sid: str, test_fraction: float = TEST_FRACTION) -> str:
    """dev/test by hash — reproducible, and not re-rollable."""
    bucket = int(hashlib.sha256(f"split:{sid}".encode()).hexdigest()[:8], 16) % 1000
    return "test" if bucket < test_fraction * 1000 else "dev"


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"])")


def passages(text: str) -> list[str]:
    """Split a speech turn into self-contained passages of a labellable size."""
    out, buf = [], ""
    for sentence in _SENT.split(text or ""):
        sentence = sentence.strip()
        if not sentence:
            continue
        buf = f"{buf} {sentence}".strip() if buf else sentence
        if len(buf) >= MIN_CHARS:
            if len(buf) <= MAX_CHARS:
                out.append(buf)
            buf = ""
    return out


def _roster() -> RosterIndex:
    """Roster lookup, shared with the data pipelines (see data/names.py)."""
    return RosterIndex(ROSTER)


GOVT_PARTIES = {"National", "ACT", "NZ First"}


def sample(n: int = 120, out: str = os.path.join(TESTSETS, "pool_v3.jsonl"),
           corpus: str | None = None, seed: int = 20260801,
           exclude_months: str = "2025-10", test_fraction: float = TEST_FRACTION) -> None:
    """Draw `n` real statements, stratified by party and month.

    `exclude_months` keeps the pilot window out of the evaluation pool — a pilot
    that is graded on statements it was run over is grading itself."""
    import hansard_prep

    corpus = corpus or os.path.join(CORPUS, "hansard_v2.json")
    excluded = {m.strip() for m in exclude_months.split(",") if m.strip()}
    by_name = _roster()
    # resolve() gives an id; the sample rows also need the party and display name.
    with open(ROSTER) as f:
        by_id = {m["id"]: m for m in json.load(f)}

    with open(corpus) as f:
        records = [json.loads(line) for line in f if line.strip()]
    by_day: dict[str, list] = defaultdict(list)
    for r in records:
        if r.get("date"):
            by_day[r["date"]].append(r)

    candidates = []
    for date, parts in by_day.items():
        if date[:7] in excluded or date < "2023-10-06":
            continue
        for block in hansard_prep.prep_day(parts):
            mp = by_id.get(by_name.resolve(block["speaker"]) or "")
            if not mp:
                continue                       # unmatched speaker: not scoreable
            for text in passages(block["text"]):
                candidates.append({
                    "statement_id": statement_id(mp["id"], text),
                    "politician_id": mp["id"],
                    "politician": mp["name"],
                    "party": mp["party"],
                    "side": "government" if mp["party"] in GOVT_PARTIES else "opposition",
                    "date": date,
                    "month": date[:7],
                    "statement": text,
                    "source": "hansard",
                })
    if not candidates:
        raise SystemExit("no candidate statements found — check the corpus path")

    # Stratify by (side, month) so the pool is not all ministers or all one
    # sitting block, then de-duplicate by statement id.
    rng = random.Random(seed)
    strata: dict[tuple, list] = defaultdict(list)
    for c in candidates:
        strata[(c["side"], c["month"])].append(c)
    keys = sorted(strata)
    for k in keys:
        rng.shuffle(strata[k])

    picked, seen, i = [], set(), 0
    while len(picked) < n and any(strata[k] for k in keys):
        k = keys[i % len(keys)]
        i += 1
        if not strata[k]:
            continue
        c = strata[k].pop()
        if c["statement_id"] in seen:
            continue
        seen.add(c["statement_id"])
        c["split"] = assign_split(c["statement_id"], test_fraction)
        # Gold fields are left blank on purpose — a human fills these in.
        c["gold"] = {}
        c["labelled_by"] = None
        picked.append(c)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for c in picked:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(picked)} UNLABELLED statements -> {out}")
    print(f"drawn from {len(candidates):,} candidates across {len(keys)} strata")
    _summarise(picked)
    print("\nNext: label the `gold` field by hand. Iterate prompts on split=dev;")
    print("touch split=test once, at the end (V3_PLAN.md §3.4).")


def split_stats(path: str) -> None:
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    _summarise(rows)


def _summarise(rows: list[dict]) -> None:
    print(f"\nsplit:  " + "  ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["split"] for r in rows).items())))
    print("side:   " + "  ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["side"] for r in rows).items())))
    print("party:  " + "  ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["party"] for r in rows).items())))
    months = Counter(r["month"] for r in rows)
    print(f"months: {len(months)} distinct, "
          f"{min(months.values())}-{max(months.values())} per month")
    print(f"speakers: {len({r['politician_id'] for r in rows})} distinct")
    labelled = sum(1 for r in rows if r.get("gold"))
    print(f"labelled: {labelled}/{len(rows)}")


# --- leakage -----------------------------------------------------------------

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()


def _shingles(text: str, k: int = 8) -> set:
    words = _normalise(text).split()
    return {" ".join(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def check_leakage(k: int = 8, quiet: bool = False) -> list:
    """Fail if any testset statement also appears in a prompt's few-shot block.

    Few-shot examples that overlap the testsets inflate every metric we report.
    `EVALUATION.md` already lists this as a known risk; this makes it enforced
    rather than remembered."""
    prompt_text = {}
    for path in sorted(glob.glob(os.path.join(PROMPTS, "*.txt"))):
        with open(path) as f:
            prompt_text[os.path.basename(path)] = _shingles(f.read(), k)

    hits = []
    for path in sorted(glob.glob(os.path.join(TESTSETS, "*.jsonl"))):
        with open(path) as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                text = row.get("statement") or row.get("text") or ""
                shingles = _shingles(text, k)
                if not shingles:
                    continue
                for prompt, pshingles in prompt_text.items():
                    overlap = shingles & pshingles
                    if overlap:
                        hits.append({
                            "testset": os.path.basename(path), "line": lineno,
                            "prompt": prompt, "shared": sorted(overlap)[:2],
                        })
    if not quiet:
        if hits:
            print(f"LEAKAGE: {len(hits)} testset row(s) overlap a prompt")
            for h in hits[:20]:
                print(f"  {h['testset']}:{h['line']} <-> {h['prompt']}")
                print(f"      shared: {h['shared'][0][:80]}…")
        else:
            print(f"no leakage: no {k}-word overlap between any testset and any prompt")
    return hits


if __name__ == "__main__":
    fire.Fire({"sample": sample, "check_leakage": check_leakage,
               "split_stats": split_stats})
