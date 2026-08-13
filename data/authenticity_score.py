"""Score Authenticity by joining stated positions to the vote record.

    cd data
    python authenticity_score.py run --positions ../attribute-extraction/positions_v3.jsonl
    python authenticity_score.py explain --name "Chris Bishop"

**The LLM does not score Authenticity.** It extracts a position — who, which
proposition, for or against — and this module decides whether the vote matched.
Judging consistency from a single passage means guessing at a record the model
cannot see, and in v2.0 it produced the subject-attribution bug: an MP attacking
an *opponent's* hypocrisy had the low score filed against themselves, which hit
opposition MPs 4.1 times as often as government ones.

**Individual record beats party record.** NZ votes are cast per party, so a
party vote says what the party did, not what the member believed. Where a member
is recorded individually — conscience votes, named dissents; 88 of 212
propositions carry these — that record is used instead, and the row says which
was used via `basis`. A contradiction found only at party level is a weaker
claim and the card must not present it as a personal one.

**Scored as a rate, with the denominator shown.** Contradictions per position
stated. A raw count would make a prolific speaker look worse for speaking more.

**What is not scorable is not a contradiction.** A `mixed` party vote, an absent
member, a proposition with no recorded division, or a position the extractor
marked low confidence are all dropped from both numerator and denominator. They
are recorded in `unscorable` so the loss is visible rather than silent.
"""

from __future__ import annotations

import json
import os
from collections import Counter

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
PROPOSITIONS = os.path.join(HERE, "corpus", "propositions.jsonl")
DIVISIONS = os.path.join(HERE, "corpus", "divisions.jsonl")
ROSTER = os.path.join(HERE, "mps_roster.json")
OUT = os.path.join(HERE, "corpus", "authenticity_scores.jsonl")

# Stances that can be compared. Anything else (a `mixed` party vote, an
# abstention) carries no direction and cannot contradict anything.
COMPARABLE = {"support", "oppose"}

# Below this, the extractor was not sure it read a position at all. Scoring a
# contradiction off an uncertain reading manufactures hypocrisy.
MIN_CONFIDENCE = 0.5


def _read(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _positions_from(path: str, roster_path: str = ROSTER) -> list[dict]:
    """Read extracted positions from either shape the pipeline produces.

    * flat rows — one position per line, already carrying `politician_id`
    * window records — `extract_hansard.py --attrs positions` output, keyed by
      `examples_by_attribute`, with the speaker named in prose

    Names are resolved through `data/names.py`, the single implementation. An
    unresolvable name is dropped rather than guessed: attributing a broken
    promise to the wrong MP is worse than attributing it to nobody.
    """
    import names

    roster = names.RosterIndex(roster_path)
    party_of = {}
    if os.path.exists(roster_path):
        with open(roster_path, encoding="utf-8") as f:
            party_of = {mp["id"]: mp.get("party") for mp in json.load(f)}

    rows, dropped = [], Counter()
    for raw in _read(path):
        if "examples_by_attribute" not in raw:
            rows.append(raw)
            continue
        for ex in (raw["examples_by_attribute"].get("authenticity") or []):
            # Only the speaker's own stated position belongs on their card. An
            # MP describing an opponent's position is not stating their own.
            if ex.get("subject") not in (None, "speaker"):
                dropped["subject_other"] += 1
                continue
            pid = roster.resolve(names.clean(ex.get("politician") or ""))
            if not pid:
                dropped["unresolved_name"] += 1
                continue
            rows.append({
                "politician_id": pid,
                "politician": ex.get("politician"),
                "party": party_of.get(pid),
                "proposition": ex.get("proposition"),
                "stance": ex.get("stance"),
                "quote": ex.get("statement"),
                "date": raw.get("date"),
            })
    if dropped:
        print("positions dropped: " +
              ", ".join(f"{k}={v}" for k, v in sorted(dropped.items())))
    return rows


# --- matching a spoken bill name to the proposition vocabulary ----------------
#
# The extractor is asked to name the bill the speaker took a position on, not to
# pick an ID out of a 212-item list — pasting the vocabulary into every window
# prompt would cost more than the extraction and invites the model to force a
# match. Matching is done here instead, deterministically.
#
# The rule is `names.py`'s: **a fuzzy match is accepted only when it is unique.**
# Two plausible bills means we do not know which was meant, and guessing invents
# a position the speaker never took.

_STOP = {"the", "a", "an", "of", "and", "no", "bill", "amendment", "act"}


def _tokens(text: str) -> set:
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in (text or ""))
    return {t for t in cleaned.lower().split() if t and t not in _STOP}


def resolve_proposition(text: str, propositions: dict) -> str | None:
    """Best proposition for a spoken bill name, or None when it is not unique.

    Tries exact normalised equality, then containment, then token overlap —
    accepting each only when exactly one proposition qualifies.
    """
    want = _tokens(text)
    if not want:
        return None

    labels = {pid: _tokens(p.get("label", "")) for pid, p in propositions.items()}

    exact = [pid for pid, toks in labels.items() if toks == want]
    if len(exact) == 1:
        return exact[0]

    contained = [pid for pid, toks in labels.items()
                 if toks and (toks <= want or want <= toks)]
    if len(contained) == 1:
        return contained[0]

    scored = sorted(
        ((len(want & toks) / len(want | toks), pid)
         for pid, toks in labels.items() if toks),
        reverse=True)
    if not scored or scored[0][0] < 0.6:
        return None
    # Unique winner only: a tie means two bills fit and we cannot tell them
    # apart, which is a reason to drop the position, not to pick one.
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def judge(position: dict, proposition: dict) -> dict:
    """Compare one stated position against the recorded vote.

    Returns `{verdict, basis, voted, stated, reason}`. Verdicts:
      * `consistent`   — the vote matched the words
      * `contradiction`— the vote was the opposite
      * `unscorable`   — no comparable vote, or the position was too uncertain
    """
    stated = (position.get("stance") or "").lower()
    out = {"verdict": "unscorable", "basis": None, "voted": None,
           "stated": stated, "reason": None}

    if stated not in COMPARABLE:
        out["reason"] = f"stated stance {stated!r} has no direction"
        return out
    if position.get("confidence") is not None and \
            float(position["confidence"]) < MIN_CONFIDENCE:
        out["reason"] = "position extracted with low confidence"
        return out
    if proposition is None:
        out["reason"] = "proposition not in the vocabulary"
        return out

    # Individual record first — it is the only one that speaks to this member.
    pid = position.get("politician_id")
    member = (proposition.get("member_positions") or {}).get(pid)
    party = (proposition.get("party_positions") or {}).get(position.get("party"))
    record, basis = (member, "member") if member else (party, "party")

    if not record:
        out["reason"] = "no recorded vote for this member or their party"
        return out

    voted = (record.get("stance") or "").lower()
    out.update(basis=basis, voted=voted)
    if voted not in COMPARABLE:
        out["reason"] = f"recorded vote is {voted!r}"
        return out

    out["verdict"] = "consistent" if voted == stated else "contradiction"
    return out


def _score_member(judged: list[dict]) -> dict:
    """Aggregate one member's judged positions into a rate."""
    counts = Counter(j["verdict"] for j in judged)
    scored = counts["consistent"] + counts["contradiction"]
    # Party-level evidence only is a weaker claim; the card must say so.
    bases = Counter(j["basis"] for j in judged
                    if j["verdict"] in ("consistent", "contradiction"))
    return {
        "score": round(counts["consistent"] / scored, 4) if scored else None,
        "positions_stated": len(judged),
        "positions_scored": scored,
        "contradictions": counts["contradiction"],
        "unscorable": counts["unscorable"],
        "basis": ("member" if bases["member"] and not bases["party"]
                  else "party" if bases["party"] and not bases["member"]
                  else "mixed" if scored else None),
        "member_level_n": bases["member"],
        "party_level_n": bases["party"],
        "insufficient_evidence": scored == 0,
    }


def score(positions: str, propositions: str = PROPOSITIONS) -> list[dict]:
    """Join extracted positions to the vote record, one row per member."""
    props = {p["proposition_id"]: p for p in _read(propositions)}

    by_member: dict[str, list] = {}
    for pos in _positions_from(positions):
        pid = pos.get("politician_id")
        if not pid:
            continue
        # The extractor may give an ID directly, or name the bill in words.
        prop_id = pos.get("proposition_id")
        if not prop_id and pos.get("proposition"):
            prop_id = resolve_proposition(pos["proposition"], props)
            pos = {**pos, "proposition_id": prop_id}
        by_member.setdefault(pid, []).append(
            (pos, judge(pos, props.get(prop_id))))

    rows = []
    for pid, pairs in sorted(by_member.items()):
        judged = [j for _, j in pairs]
        agg = _score_member(judged)
        first = pairs[0][0]
        rows.append({
            "politician_id": pid,
            "name": first.get("politician") or pid,
            "party": first.get("party"),
            "attribute": "authenticity",
            **agg,
            "examples": [
                {"proposition_id": p.get("proposition_id"),
                 "quote": p.get("quote"), "stated": j["stated"],
                 "voted": j["voted"], "basis": j["basis"]}
                for p, j in pairs if j["verdict"] == "contradiction"
            ],
        })
    return rows


def run(positions: str, propositions: str = PROPOSITIONS, out: str = OUT) -> None:
    """Score Authenticity and write corpus/authenticity_scores.jsonl."""
    rows = score(positions, propositions)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    have = [r for r in rows if r["score"] is not None]
    stated = sum(r["positions_stated"] for r in rows)
    scored = sum(r["positions_scored"] for r in rows)
    print(f"{len(rows)} members, {len(have)} scored")
    print(f"{stated:,} positions stated, {scored:,} joined to a vote "
          f"({100*scored/stated if stated else 0:.0f}%), "
          f"{stated - scored:,} unscorable")
    if have:
        print(f"mean {sum(r['score'] for r in have)/len(have):.3f}")
        m = sum(r["member_level_n"] for r in rows)
        p = sum(r["party_level_n"] for r in rows)
        print(f"evidence basis: {m:,} individual records, {p:,} party votes "
              f"({100*p/(m+p) if m+p else 0:.0f}% party-level — the caveat "
              f"the card must carry)")

        # Mandatory bias check (ATTRIBUTES.md): opposition MPs vote against
        # government bills because that is their job, not because they are
        # inconsistent. If this gap is large, the join has re-created the old
        # directional bias in a new place.
        gov = {"National", "ACT", "NZ First"}
        g = [r["score"] for r in have if r.get("party") in gov]
        o = [r["score"] for r in have if r.get("party") not in gov]
        if g and o:
            print(f"\nbias check — government {sum(g)/len(g):.3f} (n={len(g)})  "
                  f"opposition {sum(o)/len(o):.3f} (n={len(o)})  "
                  f"gap {abs(sum(g)/len(g) - sum(o)/len(o)):.3f}")
    print(f"\nwrote {out}")


def explain(name: str, positions: str, propositions: str = PROPOSITIONS) -> None:
    """Show one member's positions and how each was judged."""
    for r in score(positions, propositions):
        if (r["name"] or "").lower() == name.lower():
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return
    raise SystemExit(f"no member named {name!r}")


if __name__ == "__main__":
    fire.Fire({"run": run, "score": score, "explain": explain, "judge": judge})
