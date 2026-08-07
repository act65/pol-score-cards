"""Parse party-vote divisions out of the scraped Hansard corpus.

Hansard prints every party vote in a fixed three-part shape:

    A party vote was called for on the question, That <question> .
    New Zealand National 48; ACT New Zealand 11; New Zealand First 8.      <- Ayes
    New Zealand Labour 34; Green Party ... 15; Te Pāti Māori 4; Ferris.    <- Noes
    Motion agreed to.                                                      <- optional

so the whole vote record can be recovered from text we already scraped — no new
network calls, no LLM. Output is one JSON object per division:

    python parse_divisions.py --out corpus/divisions.jsonl
    python parse_divisions.py --stats            # summary, writes nothing

Point `--corpus` at a Hansard scrape taken after the `parse_hansard_day` fix
(`corpus/hansard_v2.json`) and Hansard's own `Ayes 83` / `Noes 34` labels are
present: the sides are then **read**, the declared total is kept alongside the
parsed one, and records are flagged `ayes_labelled`. The original corpus lost
those labels, so for it the parser falls back to Hansard's invariant
Ayes-then-Noes ordering and flags `ayes_order_inferred`. Both paths are
supported; see data/VOTES.md for what the re-scrape recovered.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter

import fire

from names import RosterIndex, norm as _norm

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROSTER = os.path.join(HERE, "mps_roster.json")
DEFAULT_OUT = os.path.join(HERE, "corpus", "divisions.jsonl")

# Prefer the re-scraped corpus: the original lost the Ayes/Noes labels and
# truncated long sitting days at 8 sections, which cost about three quarters of
# all divisions. Fall back to the old one so this still runs before a re-scrape.
_CORPUS_V2 = os.path.join(HERE, "corpus", "hansard_v2.json")
_CORPUS_V1 = os.path.join(HERE, "corpus", "hansard.json")
DEFAULT_CORPUS = _CORPUS_V2 if os.path.exists(_CORPUS_V2) else _CORPUS_V1

MARKER = "A party vote was called for on the question,"
_MARKER_RE = re.compile(re.escape(MARKER) + r"\s*(.*)$")

# First sitting of the 54th Parliament. Earlier divisions in the corpus belong
# to the 53rd, whose membership the current roster does not cover.
TERM_54_START = "2023-10-06"

# Hansard's full party names -> the ids used in site/static/politicians.jsonl.
# "Te Paati Māori" is a real alternate spelling in the record, not a typo of ours.
PARTY_MAP = {
    "New Zealand National": "National",
    "New Zealand Labour": "Labour",
    "ACT New Zealand": "ACT",
    "Green Party of Aotearoa New Zealand": "Green",
    "Green Party of Aotearoa": "Green",
    "New Zealand First": "NZ First",
    "Te Pāti Māori": "Te Pāti Māori",
    "Te Paati Māori": "Te Pāti Māori",
}

# Lines that sit where a vote list sits but are prose, not votes.
_NOT_A_VOTE_LINE = re.compile(
    r"^(The result corrected|The bill was divided|The committee divided|"
    r"A party vote was called)", re.I)

# A vote list is "<Party> <n>" segments and/or bare surnames, separated by
# ";" (usual) or "," (occasional). Nothing else, and never a speaker turn.
_SEGMENT = re.compile(r"^(?P<party>.*?)\s+(?P<count>\d+)$")


def _clean(line: str) -> str:
    """Hansard sprinkles non-breaking spaces inside party names
    ('New\\xa0Zealand\\xa0First 8'). Collapse all whitespace to plain spaces so
    the party lookup can succeed."""
    return re.sub(r"\s+", " ", (line or "").replace("\xa0", " ")).strip()


def _split_segments(line: str) -> list[str]:
    """Split a vote list into segments. Semicolons are the normal separator;
    a handful of lines use commas instead, so fall back to those."""
    parts = [p.strip() for p in _clean(line).rstrip(". ").split(";")]
    out = []
    for p in parts:
        # "New Zealand Labour 34, ACT New Zealand 11" — comma-separated variant.
        if "," in p and re.search(r"\d\s*,", p):
            out.extend(q.strip() for q in p.split(","))
        else:
            out.append(p)
    return [p for p in out if p]


def is_vote_line(line: str) -> bool:
    """True if `line` is a party-vote tally list rather than prose."""
    line = _clean(line)
    if not line or len(line) > 400 or ":" in line:
        return False
    if _NOT_A_VOTE_LINE.match(line):
        return False
    segments = _split_segments(line)
    if not segments:
        return False
    # Every segment must be "<known party> <n>" or a short bare surname, and at
    # least one must be a party count (a line of bare words is prose).
    saw_party = False
    for seg in segments:
        m = _SEGMENT.match(seg)
        if m:
            if m.group("party").strip() not in PARTY_MAP:
                return False
            saw_party = True
        elif not re.fullmatch(r"[A-ZŌĀĒĪŪ][\w’'‑-]{1,24}", seg):
            return False
    return saw_party


def parse_vote_line(line: str, roster_index: dict | None = None) -> dict:
    """'New Zealand National 48; ACT New Zealand 11; Ferris.' ->
    {parties: {National: 48, ACT: 11}, members: [...], total: 60}

    Bare surnames are MPs voting apart from any party (independents and
    defectors); each counts as one vote. They are resolved to politician ids
    when `roster_index` is given, and kept as raw surnames otherwise."""
    parties: dict[str, int] = {}
    members: list[str] = []
    unresolved: list[str] = []
    for seg in _split_segments(line):
        m = _SEGMENT.match(seg)
        if m:
            party = PARTY_MAP.get(m.group("party").strip())
            if party:
                parties[party] = parties.get(party, 0) + int(m.group("count"))
        else:
            pid = roster_index.resolve(seg) if roster_index else None
            if pid:
                members.append(pid)
            else:
                unresolved.append(seg)
    return {
        "parties": parties,
        "members": members,
        "unresolved_members": unresolved,
        "total": sum(parties.values()) + len(members) + len(unresolved),
    }


# Hansard prints "Ayes 83" / "Noes 34" as their own line above each tally. Our
# first Hansard scrape dropped them (see VOTES.md); corpora scraped after that
# fix have them, and then nothing has to be inferred.
_LABEL = re.compile(r"^(Ayes|Noes|Abstentions?|Abstained)\s+(\d+)$", re.I)
_SIDE_OF_LABEL = {"ayes": "ayes", "noes": "noes",
                  "abstention": "abstentions", "abstentions": "abstentions",
                  "abstained": "abstentions"}
_POSITIONAL_SIDES = ("ayes", "noes", "abstentions")


def _bare_total(line: str) -> int:
    """Votes in a tally line, without resolving anyone."""
    return parse_vote_line(line)["total"]


def scan_vote_block(lines: list[str]) -> tuple[list[dict], bool, int]:
    """Read the tally lines that follow a division marker.

    Returns (sides, labelled, consumed). Each side is
    {"side": "ayes"|"noes"|"abstentions", "declared": int|None, "line": str}.
    `labelled` is True when Hansard's own Ayes/Noes labels were present, in which
    case the side assignment is read rather than inferred from position.
    `consumed` is how many input lines the block occupied, so the caller can look
    for the verdict line straight after it."""
    sides: list[dict] = []
    pending: str | None = None
    declared: int | None = None
    consumed = 0
    buf = ""
    for offset, raw in enumerate(lines):
        line = _clean(raw)
        label = _LABEL.match(line)
        if label:
            if pending or buf:                # a label with no complete tally
                break
            pending = _SIDE_OF_LABEL[label.group(1).lower()]
            declared = int(label.group(2))
            continue
        if not is_vote_line(line):
            break
        # A long tally can wrap across two paragraphs; Hansard ends the real one
        # with a full stop, so keep accumulating until we see it. Without this a
        # continuation is read as the *other* side and a party's votes vanish.
        buf = f"{buf} {line}".strip() if buf else line
        consumed = offset + 1
        # Normally the full stop ends the tally. When Hansard omits it, the
        # declared total tells us when we have everything — without this the
        # next side gets swallowed into this one.
        complete = buf.endswith(".")
        if not complete and declared is not None:
            complete = _bare_total(buf) >= declared
        if not complete:
            continue
        if pending:
            sides.append({"side": pending, "declared": declared, "line": buf})
            pending, declared = None, None
        else:
            if len(sides) >= len(_POSITIONAL_SIDES):
                break
            sides.append({"side": _POSITIONAL_SIDES[len(sides)],
                          "declared": None, "line": buf})
        buf = ""
    return sides, any(s["declared"] is not None for s in sides), consumed


# --- classification -------------------------------------------------------

_TYPE_RULES = [
    ("third_reading",  re.compile(r"read a third time", re.I)),
    ("second_reading", re.compile(r"read a second time", re.I)),
    ("first_reading",  re.compile(r"read a first time", re.I)),
    ("closure",        re.compile(r"debate on this question now close|question be now put", re.I)),
    ("urgency",        re.compile(r"urgency be accorded|extended sitting", re.I)),
    ("committee_report", re.compile(r"be reported to the House", re.I)),
    ("amendment",      re.compile(r"\bamendments?\b.*be agreed to", re.I)),
    ("committee",      re.compile(r"\b(clause|Part|Schedule)s?\b.*be agreed to", re.I)),
    ("motion",         re.compile(r"That the motion be agreed to", re.I)),
]

# Votes that express a position on policy, vs pure floor management. Only the
# substantive ones are meaningful evidence for Authenticity.
SUBSTANTIVE_TYPES = {"first_reading", "second_reading", "third_reading",
                     "committee", "amendment", "motion"}


def classify(question: str) -> str:
    for name, pattern in _TYPE_RULES:
        if pattern.search(question):
            return name
    return "other"


_BILL_IN_QUESTION = re.compile(
    r"That (?:the )?(?P<bill>[A-ZŌĀĒĪŪ][^,]*?\bBill\b(?:\s*\(No \d+\))?)\s+be\b", re.I)
# A standalone heading line naming a bill: no speaker colon, no trailing stop.
_BILL_HEADING = re.compile(r"^(?P<bill>[A-ZŌĀĒĪŪ][^:.]{5,110}?\bBill\b(?:\s*\(No \d+\))?)"
                           r"(?:,\s*(?:in committee|third reading|second reading|"
                           r"first reading|introduction))?$", re.I)
# "report of the Health Committee on the Pae Ora ... Bill" — the division is
# about the bill, not the committee's report on it.
_REPORT_PREFIX = re.compile(r"^.*?\bCommittee on the\s+", re.I)
# Bills split in committee get a joint reading: "the Gangs Bill and the
# Sentencing Amendment Bill be now read a third time" is one vote on two bills.
# Only split where the left side already ends in "Bill", so ordinary conjunctions
# inside a title ("Education and Training Amendment Bill") stay intact.
_JOINT = re.compile(r"(?<=\bBill)\s+and\s+(?:the\s+)?(?=[A-ZŌĀĒĪŪ])")


def _split_titles(text: str) -> list[str]:
    """Split a joint bill reference into individual titles, keeping only parts
    that are themselves bill titles."""
    text = _REPORT_PREFIX.sub("", text).strip()
    parts = [p.strip() for p in _JOINT.split(text)]
    titles = [p for p in parts if re.search(r"\bBill\b", p)]
    return titles or ([text] if re.search(r"\bBill\b", text) else [])


def bills_from_question(question: str) -> list[str]:
    m = _BILL_IN_QUESTION.search(question)
    return _split_titles(m.group("bill")) if m else []


def bills_from_heading(line: str) -> list[str]:
    line = _clean(line)
    if not line or len(line) > 140 or ":" in line or line.lower().startswith("that "):
        return []
    m = _BILL_HEADING.match(line)
    return _split_titles(m.group("bill")) if m else []


_VERDICT_PASS = re.compile(r"\b(agreed to|read a (first|second|third) time|carried)\.$", re.I)
_VERDICT_FAIL = re.compile(r"\b(not agreed to|negatived|lost)\.$", re.I)


def read_verdict_line(line: str) -> tuple[str | None, str | None]:
    """A bare declarative verdict line -> ('agreed'|'not_agreed', line)."""
    line = (line or "").strip()
    if not line or len(line) > 90 or ":" in line:
        return None, None
    if re.search(r"party vote|question is|called for", line, re.I):
        return None, None
    if _VERDICT_FAIL.search(line):
        return "not_agreed", line
    if _VERDICT_PASS.search(line):
        return "agreed", line
    return None, None


# --- roster ---------------------------------------------------------------

def load_roster_index(path: str = DEFAULT_ROSTER) -> RosterIndex:
    """Roster lookup, shared with every other pipeline (see data/names.py)."""
    return RosterIndex(path)


# --- main parse -----------------------------------------------------------

_PART_RE = re.compile(r"part\s+(\d+)", re.I)


def _record_sort_key(rec: dict) -> tuple:
    m = _PART_RE.search(rec.get("headline") or "")
    return (rec.get("date") or "", int(m.group(1)) if m else 0)


def _read_corpus(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_corpus(corpus_path: str = DEFAULT_CORPUS,
                 roster_path: str = DEFAULT_ROSTER,
                 fallback_corpus: str | None = None) -> list[dict]:
    """Parse every party vote in the Hansard corpus into division records.

    `fallback_corpus` supplies whole sitting days that the primary corpus is
    missing — a handful of day pages fail to render however many times they are
    retried, and the older scrape still has them. Days are never mixed: a day
    comes wholly from one corpus or the other, and records sourced from the
    fallback keep their `ayes_order_inferred` flag, so the weaker provenance
    stays visible."""
    roster_index = load_roster_index(roster_path) if os.path.exists(roster_path) else None

    records = _read_corpus(corpus_path)
    if fallback_corpus and os.path.exists(fallback_corpus):
        have = {r.get("date") for r in records}
        extra = [r for r in _read_corpus(fallback_corpus) if r.get("date") not in have]
        if extra:
            print(f"[parse_divisions] {len({r['date'] for r in extra})} day(s) taken "
                  f"from fallback {os.path.basename(fallback_corpus)}")
            records += extra
    records.sort(key=_record_sort_key)

    divisions: list[dict] = []
    current_bills: list[str] = []
    current_date: str | None = None
    seq = 0

    for rec in records:
        date = rec.get("date") or ""
        if date != current_date:
            # Bill context does not carry across sitting days.
            current_date, current_bills, seq = date, [], 0

        lines = rec.get("content", "").split("\n")
        for i, line in enumerate(lines):
            heading = bills_from_heading(line)
            if heading:
                current_bills = heading

            m = _MARKER_RE.search(line)
            if not m:
                continue

            question = m.group(1).strip().rstrip(".").strip()
            flags: list[str] = []

            sides, labelled, consumed = scan_vote_block(lines[i + 1:i + 8])
            if not sides:
                flags.append("no_vote_lines")

            named = bills_from_question(question)
            if named:
                current_bills = named
                bill_source = "question"
            else:
                bill_source = "carried_forward" if current_bills else None

            tallies: dict[str, dict | None] = {"ayes": None, "noes": None,
                                               "abstentions": None}
            for side in sides:
                parsed = parse_vote_line(side["line"], roster_index)
                if side["declared"] is not None:
                    parsed["declared_total"] = side["declared"]
                    if side["declared"] != parsed["total"]:
                        flags.append("tally_mismatch")
                tallies[side["side"]] = parsed
            ayes, noes = tallies["ayes"], tallies["noes"]
            abstentions = tallies["abstentions"]

            if sides:
                # With Hansard's labels the sides are read, not guessed; without
                # them we fall back to Hansard's invariant Ayes-then-Noes order.
                flags.append("ayes_labelled" if labelled else "ayes_order_inferred")
            if ayes and not noes:
                flags.append("unopposed")

            verdict, verdict_line = read_verdict_line(
                lines[i + 1 + consumed] if i + 1 + consumed < len(lines) else "")
            from_totals = (("agreed" if ayes["total"] > (noes["total"] if noes else 0)
                            else "not_agreed") if ayes else None)
            if verdict is None:
                verdict = from_totals
                if verdict:
                    flags.append("result_from_totals")
            elif from_totals and from_totals != verdict:
                # The tally is the primary evidence; a nearby declarative line can
                # be a summary covering several votes rather than this one's verdict.
                flags.append("verdict_conflicts_with_totals")
                verdict = from_totals

            if any(p["unresolved_members"] for p in (ayes, noes, abstentions) if p):
                flags.append("unresolved_members")

            seq += 1
            dtype = classify(question)
            divisions.append({
                "division_id": f"{date}-{seq:03d}",
                "date": date,
                "parliament": 54 if date >= TERM_54_START else 53,
                "question": question,
                "type": dtype,
                "substantive": dtype in SUBSTANTIVE_TYPES,
                # Usually one bill; a joint reading of bills split in committee
                # is a single vote covering two.
                "bills": list(current_bills),
                "bill_source": bill_source,
                "ayes": ayes,
                "noes": noes,
                "abstentions": abstentions,
                "result": verdict,
                "verdict_line": verdict_line,
                "flags": flags,
                "hansard_headline": rec.get("headline"),
                "source_url": rec.get("url"),
            })
    return divisions


def run(out: str = DEFAULT_OUT, corpus: str = DEFAULT_CORPUS,
        roster: str = DEFAULT_ROSTER,
        fallback_corpus: str | None = _CORPUS_V1) -> None:
    """Parse the corpus and write divisions.jsonl."""
    if fallback_corpus == corpus:
        fallback_corpus = None
    divisions = parse_corpus(corpus, roster, fallback_corpus)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for d in divisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"wrote {len(divisions)} divisions -> {out}")
    _summarise(divisions)


def stats(corpus: str = DEFAULT_CORPUS, roster: str = DEFAULT_ROSTER,
          fallback_corpus: str | None = _CORPUS_V1) -> None:
    """Parse and print a summary without writing anything."""
    if fallback_corpus == corpus:
        fallback_corpus = None
    _summarise(parse_corpus(corpus, roster, fallback_corpus))


def _summarise(divisions: list[dict]) -> None:
    n = len(divisions)
    print(f"\ndivisions: {n}")
    if not n:
        return
    dates = sorted({d["date"] for d in divisions if d["date"]})
    print(f"sitting days: {len(dates)}   range: {dates[0]} .. {dates[-1]}")
    print(f"substantive: {sum(d['substantive'] for d in divisions)}"
          f"   procedural: {sum(not d['substantive'] for d in divisions)}")
    print(f"bill identified: {sum(bool(d['bills']) for d in divisions)}"
          f"  (from question: {sum(d['bill_source'] == 'question' for d in divisions)},"
          f" carried forward: {sum(d['bill_source'] == 'carried_forward' for d in divisions)})")
    print(f"distinct bills: {len({b for d in divisions for b in d['bills']})}")

    print("\nby type:")
    for t, c in Counter(d["type"] for d in divisions).most_common():
        print(f"  {c:5}  {t}")
    print("\nresult:")
    for r, c in Counter(d["result"] for d in divisions).most_common():
        print(f"  {c:5}  {r}")
    print("\nflags:")
    for fl, c in Counter(f for d in divisions for f in d["flags"]).most_common():
        print(f"  {c:5}  {fl}")

    party_votes: Counter = Counter()
    for d in divisions:
        for side in ("ayes", "noes"):
            if d[side]:
                for p in d[side]["parties"]:
                    party_votes[p] += 1
    print("\nparty appearances:")
    for p, c in party_votes.most_common():
        print(f"  {c:5}  {p}")
    ind = Counter(m for d in divisions for side in ("ayes", "noes", "abstentions")
                  if d[side] for m in d[side]["members"])
    if ind:
        print("\nindividually-recorded members:")
        for m, c in ind.most_common(10):
            print(f"  {c:5}  {m}")
    unres = Counter(m for d in divisions for side in ("ayes", "noes", "abstentions")
                    if d[side] for m in d[side]["unresolved_members"])
    if unres:
        print("\nUNRESOLVED surnames (not in roster):")
        for m, c in unres.most_common(10):
            print(f"  {c:5}  {m}")


if __name__ == "__main__":
    fire.Fire({"run": run, "stats": stats})
