"""Score Forthrightness over question/answer PAIRS.

Evasion is a relation between a question and an answer. It cannot be seen in an
isolated statement, which is what the window extractor scores — so in v2.0
Forthrightness was being judged from lone sentences and ended up correlating
with Rigor at 0.73. This runs it over the structured pairs instead:

    corpus/oral_questions.jsonl     11,082 Hansard Q/A pairs
    corpus/written_questions.jsonl  180,939 written PQs and replies

    cd attribute-extraction
    python extract_questions.py run --dry_run
    python extract_questions.py run --backend claude_cli --out forthrightness.jsonl
    python extract_questions.py run --source written --limit 2000

**Written questions must be de-duplicated before scoring.** 180,939 written
questions reduce to 56,482 distinct templates — one Verrall template was filed
1,763 times across 31 ministers. Scoring raw questions would weight a card by
how often the opposition used find-and-replace, so the default is to score one
representative per template and reuse the score. Pass `--dedupe False` to
override, but there is no good reason to.

Resumable: pairs already in the output file are skipped.
"""

from __future__ import annotations

import collections
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import fire
from pydantic import BaseModel, Field

import claude_cli
import extract

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "data", "corpus")
SOURCES = {
    "oral": os.path.join(CORPUS, "oral_questions.jsonl"),
    "written": os.path.join(CORPUS, "written_questions.jsonl"),
}

# Written questions are filed in bulk from a template with the portfolio or a
# number swapped in. Normalising those out is what makes a template key.
_NUMS = re.compile(r"\d[\d,.]*")
_WS = re.compile(r"\s+")


def template_key(text: str) -> str:
    """Collapse a written question to its reusable skeleton.

    Digits become a placeholder because the bulk-filed variants differ only by
    year, dollar amount or item number; whitespace and case are folded. Two
    questions with the same key are the same question asked of different people.
    """
    return _WS.sub(" ", _NUMS.sub("#", (text or "").lower())).strip()


class _Pair(BaseModel):
    question_id: str = Field(description="Echo the id given with the pair.")
    score: float = Field(description="Forthrightness in [0, 1]; higher is better.")
    explanation: str = Field(description="What was asked, and whether it was answered.")


class _PairResult(BaseModel):
    scores: List[_Pair]


_INSTRUCTION = (
    "\n\nScore EVERY pair you are given, and echo its `question_id` exactly. Judge "
    "only whether the response addressed the question that was asked. Do not let "
    "the answer's detail, truthfulness, politeness or reasoning move the score — "
    "those are other attributes. A blunt refusal that answers the question scores "
    "HIGH. If a pair is not a real question (a point of order, a procedural motion), "
    "omit it rather than scoring it."
)


def load_pairs(source: str, since: str = "", dedupe: bool = True) -> list[dict]:
    """Read a source into uniform {id, asker, responder, question, answer} rows."""
    path = SOURCES[source]
    rows = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if source == "oral":
                rows.append({"id": r["question_id"], "date": r.get("date", ""),
                             "asker": r.get("asker"), "responder": r.get("responder"),
                             "responder_id": r.get("responder_id"),
                             "question": r.get("question", ""),
                             "answer": r.get("answer", "")})
            else:
                if not r.get("answered"):
                    continue          # pending: no answer to judge, not a dodge
                if r.get("attachment_only"):
                    continue          # the reply is a file; nothing to score
                rows.append({"id": str(r["question_id"]),
                             "date": r.get("released_date") or "",
                             "asker": r.get("asker"), "responder": r.get("minister"),
                             "responder_id": r.get("minister_id"),
                             "question": r.get("question", ""),
                             "answer": r.get("reply") or ""})
    if since:
        rows = [r for r in rows if r["date"] >= since]
    rows = [r for r in rows if r["question"].strip() and r["answer"].strip()]

    if dedupe and source == "written":
        # One representative per (template, responder): the same question put to
        # a different minister is a genuinely different test of that minister,
        # but the same question filed 40 times at one minister is not.
        seen, kept = set(), []
        for r in rows:
            key = (template_key(r["question"]), r.get("responder_id") or r.get("responder"))
            if key in seen:
                continue
            seen.add(key)
            kept.append(r)
        print(f"{source}: {len(rows):,} answered -> {len(kept):,} distinct "
              f"(template, minister) pairs")
        rows = kept
    return rows


def _batches(rows: list[dict], per_call: int, max_chars: int):
    """Group pairs into calls, bounded by both count and total size."""
    cur, size = [], 0
    for r in rows:
        n = len(r["question"]) + len(r["answer"])
        if cur and (len(cur) >= per_call or size + n > max_chars):
            yield cur
            cur, size = [], 0
        cur.append(r)
        size += n
    if cur:
        yield cur


def _render(batch: list[dict]) -> str:
    out = []
    for r in batch:
        out.append(f"--- pair {r['id']} ---\n"
                   f"Q ({r.get('asker') or 'unknown'}): {r['question'].strip()}\n"
                   f"A ({r.get('responder') or 'unknown'}): {r['answer'].strip()}")
    return "\n\n".join(out)


def _saved_ids(path: str) -> set:
    ids = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    try:
                        ids.add(json.loads(line)["question_id"])
                    except Exception:
                        pass
    return ids


def run(out: str = "forthrightness_scores.jsonl", source: str = "oral",
        since: str = "", per_call: int = 12, max_chars: int = 24000,
        workers: int = 4, model: str = extract.DEFAULT_MODEL,
        backend: str = extract.DEFAULT_BACKEND, dedupe: bool = True,
        limit: int = 0, dry_run: bool = False) -> None:
    """Score Forthrightness over question/answer pairs."""
    if source not in SOURCES:
        raise SystemExit(f"--source must be one of {sorted(SOURCES)}")

    system = extract.load_prompt("forthrightness") + _INSTRUCTION
    rows = load_pairs(source, since=since, dedupe=dedupe)
    done = _saved_ids(out)
    todo = [r for r in rows if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    batches = list(_batches(todo, per_call, max_chars))

    if dry_run:
        chars = sum(len(_render(b)) for b in batches)
        print(f"=== forthrightness DRY RUN ({source}, {model}) ===")
        print(f"pairs: {len(rows):,}   already done: {len(done):,}   "
              f"to do: {len(todo):,}")
        print(f"calls: {len(batches):,}   content ≈{chars // 4:,} tok   "
              f"system ≈{len(system) // 4:,} tok (cached)")
        return

    print(f"{len(todo):,} pairs in {len(batches):,} calls ({workers} workers)")
    client = extract._client() if backend == "anthropic" else None
    by_id = {r["id"]: r for r in todo}
    lock = threading.Lock()
    stats = collections.Counter()

    def work(batch):
        text = _render(batch)
        if backend == "claude_cli":
            result = claude_cli.call_structured(
                system, text, _PairResult.model_json_schema(),
                model=model, instruction="")
            return [(s.get("question_id"), s.get("score"), s.get("explanation", ""))
                    for s in (result or {}).get("scores", []) or []]
        resp = client.messages.parse(
            model=model, max_tokens=8192,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": text}],
            output_format=_PairResult)
        return [(s.question_id, s.score, s.explanation)
                for s in resp.parsed_output.scores]

    written = 0
    with open(out, "a") as fh, ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, b): b for b in batches}
        for fut in as_completed(futures):
            try:
                results = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"error on a batch: {e}", flush=True)
                continue
            with lock:
                for qid, score, why in results:
                    row = by_id.get(str(qid))
                    if row is None or score is None:
                        stats["unmatched_or_unscored"] += 1
                        continue
                    fh.write(json.dumps({
                        "question_id": row["id"], "date": row["date"],
                        "source": source,
                        "politician": row.get("responder"),
                        "politician_id": row.get("responder_id"),
                        "asker": row.get("asker"),
                        "attribute": "forthrightness",
                        "score": max(0.0, min(1.0, float(score))),
                        "explanation": why,
                        "question": row["question"], "statement": row["answer"],
                    }, ensure_ascii=False) + "\n")
                    written += 1
                fh.flush()
                print(f"[{written}/{len(todo)}] scored", flush=True)

    print(f"done: wrote {written:,} scores -> {out}")
    if stats:
        print(f"skipped: {dict(stats)}")


if __name__ == "__main__":
    fire.Fire({"run": run})
