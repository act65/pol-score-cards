"""Pair up oral questions and their answers from the Hansard corpus.

Forthrightness is a **relation between a question and an answer** — whether the
answer addressed what was asked. It cannot be seen in an isolated sentence,
which is what the rest of the pipeline scores, so this builds the pairs first
and leaves only the judgement to the model.

Hansard's question time has a fixed shape:

    Question No. 1—Prime Minister
    1. Rt Hon CHRIS HIPKINS (Leader of the Opposition) to the Prime Minister: Does he stand by …?
    Rt Hon CHRISTOPHER LUXON (Prime Minister): Yes.
    Rt Hon Chris Hipkins : Does he stand by his statement …?          <- supplementary
    Rt Hon CHRISTOPHER LUXON : Well, absolutely, and that's why …     <- answer
    Hon Ginny Andersen : Answer the question.                         <- interjection, dropped
    SPEAKER : I just would express a hope that …                      <- chair, dropped

so a block gives one primary question plus a run of supplementaries, all between
the same two people. Everyone else in the block is interjecting.

    cd data
    python parse_questions.py run      # -> corpus/oral_questions.jsonl
    python parse_questions.py stats    # summary, writes nothing

Deterministic: no LLM, no network.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter

import fire

from names import RosterIndex, clean as clean_name, norm as _norm

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROSTER = os.path.join(HERE, "mps_roster.json")
DEFAULT_OUT = os.path.join(HERE, "corpus", "oral_questions.jsonl")
_CORPUS_V2 = os.path.join(HERE, "corpus", "hansard_v2.json")
_CORPUS_V1 = os.path.join(HERE, "corpus", "hansard.json")
DEFAULT_CORPUS = _CORPUS_V2 if os.path.exists(_CORPUS_V2) else _CORPUS_V1

# "Question No. 3—Health" (to 2025) or bare "Question No. 1" (2026 onward).
_BLOCK = re.compile(r"^Question No\.\s*(\d+)\s*(?:[—–-]\s*(.*))?$")
# The primary question, in either house style:
#   "1. Rt Hon CHRIS HIPKINS (Leader of the Opposition) to the Prime Minister: …"
#   "DAN BIDOIS (National—Northcote) (14:44) to the Minister of Finance : …"
# The leading number is optional and there may be several parenthetical groups
# (party/electorate, then a timestamp).
_PRIMARY = re.compile(
    r"^(?:\d+\.\s*)?(?P<asker>[^:()]+?)\s*(?:\([^)]*\)\s*)*"
    r"\bto the\s+(?P<addressee>[^:]+?)\s*:\s*(?P<question>.+)$")
# Chair and clerk turns are procedure, never a question or an answer.
_CHAIR = re.compile(r"^(SPEAKER|ASSISTANT SPEAKER|CHAIRPERSON|Mr Speaker|"
                    r"Madam Speaker|Deputy Speaker|CLERK|Hon Member)\b", re.I)
# The asker also raises points of order and seeks leave mid-block. Those are
# procedure, not supplementary questions — counting them pairs the Minister's
# real answer with the wrong text and inflates the question count.
_PROCEDURAL_TURN = re.compile(
    r"^\s*(point of order|speaking to the point of order|I seek leave|"
    r"I raise a point of order|supplementary question\s*[.?]?\s*$)", re.I)


def split_turn(line: str) -> tuple[str, str] | None:
    """Split "Hon NAME (Minister for X: Y) (14:44) : text" into (speaker, text).

    Splitting on the first colon breaks on titles that contain one, leaving an
    unbalanced parenthesis in the name. Only a colon at paren depth zero ends
    the speaker."""
    depth = 0
    for i, ch in enumerate(line):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            speaker, text = line[:i].strip(), line[i + 1:].strip()
            if 2 <= len(speaker) <= 90:
                return speaker, text
            return None
    return None


def _same_person(a: str, b: str) -> bool:
    na, nb = _norm(clean_name(a)), _norm(clean_name(b))
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Fall back to surname, which is stable across "Chris"/"Christopher" forms.
    return na.split()[-1] == nb.split()[-1]


def load_roster_index(path: str = DEFAULT_ROSTER) -> RosterIndex:
    """Roster lookup, shared with every other pipeline (see data/names.py)."""
    return RosterIndex(path)


def _resolve(name: str, index) -> str | None:
    return index.resolve(name) if index else None


def parse_block(lines: list[str], index) -> list[dict]:
    """One `Question No. N` block -> its primary and supplementary Q/A pairs."""
    header = _BLOCK.match(lines[0].strip())
    number = int(header.group(1)) if header else None
    portfolio = (header.group(2) or "").strip() or None if header else None

    primary = None
    start = 1
    for i, line in enumerate(lines[1:], start=1):
        m = _PRIMARY.match(line.strip())
        if m:
            primary, start = m, i + 1
            break
    if not primary:
        return []

    asker = clean_name(primary.group("asker"))
    turns = []
    for line in lines[start:]:
        turn = split_turn(line.strip())
        if not turn:
            continue
        speaker, text = turn
        if _CHAIR.match(speaker) or not text:
            continue
        turns.append((speaker, text))
    if not turns:
        return []

    # Whoever speaks first after the primary question is the Minister answering;
    # everyone who is neither them nor the asker is interjecting.
    responder = clean_name(turns[0][0])

    pairs = []
    pending_q = primary.group("question").strip()
    supp = 0
    for speaker, text in turns:
        if _same_person(speaker, responder):
            if pending_q is None:
                continue                       # a follow-on answer, not a new pair
            pairs.append({
                "asker": asker, "responder": responder,
                "question": pending_q, "answer": text,
                "is_primary": len(pairs) == 0,
                "supplementary_index": None if not pairs else supp,
            })
            pending_q = None
        elif _same_person(speaker, asker):
            if _PROCEDURAL_TURN.match(text):
                continue                       # a point of order, not a question
            supp += 1
            pending_q = text                   # a supplementary awaiting its answer
        # anyone else in the block is interjecting — ignore

    for p in pairs:
        p["number"] = number
        p["portfolio"] = portfolio
        p["addressee"] = primary.group("addressee").strip()
        p["asker_id"] = _resolve(p["asker"], index)
        p["responder_id"] = _resolve(p["responder"], index)
    return pairs


def parse_corpus(corpus_path: str = DEFAULT_CORPUS,
                 roster_path: str = DEFAULT_ROSTER) -> list[dict]:
    index = load_roster_index(roster_path)
    with open(corpus_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    out = []
    # A question number is not unique within a day — a day is split across
    # several corpus records, and deferred questions reuse numbers — so ids are
    # sequenced per date rather than per question number.
    seq: dict[str, int] = {}
    for rec in records:
        date = rec.get("date") or ""
        lines = rec.get("content", "").split("\n")
        starts = [i for i, l in enumerate(lines) if _BLOCK.match(l.strip())]
        for n, i in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(lines)
            block = parse_block(lines[i:end], index)
            if not block:
                continue
            b = seq[date] = seq.get(date, 0) + 1
            for k, pair in enumerate(block):
                pair["date"] = date
                pair["source_url"] = rec.get("url")
                pair["question_id"] = f"{date}-b{b:02d}-{k}"
                out.append(pair)
    return out


def run(out: str = DEFAULT_OUT, corpus: str = DEFAULT_CORPUS,
        roster: str = DEFAULT_ROSTER) -> None:
    pairs = parse_corpus(corpus, roster)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {len(pairs)} question/answer pairs -> {out}")
    _summarise(pairs)


def stats(corpus: str = DEFAULT_CORPUS, roster: str = DEFAULT_ROSTER) -> None:
    _summarise(parse_corpus(corpus, roster))


def _summarise(pairs: list[dict]) -> None:
    if not pairs:
        print("no pairs found")
        return
    dates = sorted({p["date"] for p in pairs if p["date"]})
    print(f"\npairs: {len(pairs)}   question-time days: {len(dates)}   "
          f"range: {dates[0]} .. {dates[-1]}")
    print(f"primary: {sum(p['is_primary'] for p in pairs)}   "
          f"supplementary: {sum(not p['is_primary'] for p in pairs)}")
    ar = sum(bool(p["asker_id"]) for p in pairs)
    rr = sum(bool(p["responder_id"]) for p in pairs)
    print(f"asker resolved: {ar}/{len(pairs)}   responder resolved: {rr}/{len(pairs)}")

    print("\nmost questioned (responder):")
    for name, c in Counter(p["responder"] for p in pairs).most_common(8):
        print(f"  {c:5}  {name}")
    print("\nmost persistent (asker):")
    for name, c in Counter(p["asker"] for p in pairs).most_common(8):
        print(f"  {c:5}  {name}")
    print("\ntop portfolios:")
    for name, c in Counter(p["portfolio"] for p in pairs).most_common(8):
        print(f"  {c:5}  {name}")

    unresolved = Counter(p["responder"] for p in pairs if not p["responder_id"])
    if unresolved:
        print("\nunresolved responders:")
        for name, c in unresolved.most_common(8):
            print(f"  {c:5}  {name}")


if __name__ == "__main__":
    fire.Fire({"run": run, "stats": stats})
