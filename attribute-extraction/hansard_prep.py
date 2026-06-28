"""Hansard-specific preparation for attribute extraction.

The scraped Hansard parts are arbitrary ~5k-word char-chunks of a day's debate.
Two problems for extraction:

  1. ATTRIBUTION. A chunk boundary often falls mid-speech, so a chunk can open
     with un-attributed prose (the "Hon NAME:" tag was in the previous chunk).
     If the LLM has to guess the speaker it will mis-attribute scores — a
     correctness risk for a public scorecard.
  2. TOKENS. A large share of the transcript is procedural (the Speaker, the
     Clerk, division bells, "the question is that…") and carries no scoreable
     MP conduct. Sending it costs money for no signal.

`segment_turns` re-derives speaker turns from the chunked text using the NZ
Hansard tag formats, tags each turn with its speaker and whether the speaker is
procedural (Speaker/Clerk/etc.) vs a named member. `prep_day` then drops
procedural turns and regroups member speech into attributed blocks ready for the
combined extractor — every block already carries a known speaker, so the model
scores rather than guesses who spoke.

This module is pure text processing (no network, no LLM); `measure()` reports the
token reduction and attribution coverage so we can decide the extraction config
before paying for the full run.
"""

import re

# NZ Hansard speaker-tag formats, in priority order. A "turn" starts at one of
# these and runs to the next.
#   Rt Hon CHRISTOPHER LUXON (Prime Minister):   member (minister/PM)
#   Hon NICOLA WILLIS:                            member (minister)
#   CATHERINE WEDD (National):                    member (backbench, ALLCAPS)
#   SPEAKER (14:00):  CLERK:  DEPUTY SPEAKER:     procedural
_HON = r"(?:Rt Hon|Hon)(?: Dr| Sir| Dame)? [A-Z][\w’'-]+(?: [A-Z][\w’'-]+){0,3}"
_ALLCAPS = r"[A-Z][A-Z’'-]+(?: [A-Z][A-Z’'-]+){0,3}"
_TAG_RE = re.compile(
    r"(?:^|\n)\s*("
    rf"{_HON}|{_ALLCAPS}"
    r")\s*(\([^)\n]{0,60}\))?\s*:",
)

# Speakers that are the Chair / officials, not a member being scored.
_PROCEDURAL = {
    "SPEAKER", "DEPUTY SPEAKER", "ASSISTANT SPEAKER", "CLERK", "DEPUTY CLERK",
    "TEMPORARY SPEAKER", "CHAIRPERSON", "THE CHAIRPERSON", "MADAM SPEAKER",
    "MR SPEAKER", "SERGEANT-AT-ARMS",
}
# Lines that are pure procedure even inside a member turn — cheap to drop.
_PROC_LINE_RE = re.compile(
    r"^\s*(?:A division was called|The question was put|Motion agreed|"
    r"The House divided|Ayes \d|Noes \d|Bells? rung|Sitting suspended|"
    r"The question is that|Party Votes|A personal vote)",
    re.I,
)


def _norm_speaker(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    return s


def _is_procedural(speaker: str) -> bool:
    up = speaker.upper().strip()
    return up in _PROCEDURAL


def segment_turns(text: str) -> list:
    """Split a Hansard text block into [{speaker, procedural, text}] turns.

    A leading block before the first recognised tag (e.g. a chunk that opened
    mid-speech) is returned with speaker=None so callers can decide what to do.
    """
    turns = []
    last = 0
    last_speaker = None
    for m in _TAG_RE.finditer(text):
        if m.start() > last:
            body = text[last:m.start()].strip()
            if body:
                turns.append({"speaker": last_speaker, "procedural":
                              _is_procedural(last_speaker) if last_speaker else None,
                              "text": body})
        last_speaker = _norm_speaker(m.group(1))
        last = m.end()
    tail = text[last:].strip()
    if tail:
        turns.append({"speaker": last_speaker,
                      "procedural": _is_procedural(last_speaker) if last_speaker else None,
                      "text": tail})
    return turns


def _strip_proc_lines(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not _PROC_LINE_RE.match(l))


def prep_day(parts: list) -> list:
    """Given a day's scraped parts (in order), return attributed member blocks:
    [{speaker, date, text}], procedural turns dropped, member turns by the same
    speaker merged. Ready to feed the combined extractor with a known speaker."""
    date = parts[0].get("date") if parts else None
    blocks, cur_spk, buf = [], None, []

    def flush():
        if cur_spk and buf:
            blocks.append({"speaker": cur_spk, "date": date,
                           "text": _strip_proc_lines("\n".join(buf)).strip()})

    for p in parts:
        for t in segment_turns(p.get("content", "")):
            if t["speaker"] is None:
                # A leading un-tagged block. Parts are arbitrary char-chunks, so
                # this is usually a speech continuing across the part boundary —
                # attribute it to the carried speaker. At the very start of a day
                # (no carried speaker) it's page chrome / prayers; drop it.
                if cur_spk:
                    buf.append(t["text"])
                continue
            if t["procedural"]:
                flush()
                cur_spk, buf = None, []  # reset so the next opener isn't mis-carried
                continue
            if t["speaker"] != cur_spk:
                flush()
                cur_spk, buf = t["speaker"], []
            buf.append(t["text"])
    flush()
    return [b for b in blocks if len(b["text"]) > 80]


def _toks(s: str) -> int:
    # cheap, consistent estimate; ~4 chars/token for English prose
    return max(1, len(s) // 4)


def measure(corpus_path="../data/corpus/hansard.json", since="2023-10-14"):
    """Report token reduction + attribution coverage from speaker-prep."""
    import collections
    import json
    by_day = collections.defaultdict(list)
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("date", "") >= since:
                by_day[r["date"]].append(r)

    raw_tok = proc_tok = mp_tok = 0
    unattr_tok = 0
    speaker_words = collections.Counter()
    for day, parts in by_day.items():
        for p in parts:
            raw_tok += _toks(p.get("content", ""))
            for t in segment_turns(p.get("content", "")):
                tk = _toks(t["text"])
                if not t["speaker"]:
                    unattr_tok += tk
                elif t["procedural"]:
                    proc_tok += tk
                else:
                    mp_tok += tk
                    speaker_words[t["speaker"]] += len(t["text"].split())

    print(f"Hansard prep measurement (54th term, since {since})")
    print(f"  days: {len(by_day)}   parts: {sum(len(v) for v in by_day.values())}")
    print(f"  raw content tokens (est):     {raw_tok:>12,}")
    print(f"  procedural (Speaker/Clerk):   {proc_tok:>12,}  ({proc_tok/raw_tok:5.1%})")
    print(f"  un-attributed (chunk openers):{unattr_tok:>12,}  ({unattr_tok/raw_tok:5.1%})")
    print(f"  MEMBER speech (kept):         {mp_tok:>12,}  ({mp_tok/raw_tok:5.1%})")
    print(f"  distinct member speakers:     {len(speaker_words):>12,}")
    print("  top speakers by words:")
    for s, w in speaker_words.most_common(12):
        print(f"     {w:>9,}  {s}")
    return {"raw": raw_tok, "proc": proc_tok, "unattr": unattr_tok, "mp": mp_tok,
            "speakers": speaker_words}


if __name__ == "__main__":
    measure()
