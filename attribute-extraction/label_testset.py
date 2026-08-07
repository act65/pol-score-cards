"""Round-trip the labelling pool through a spreadsheet.

Hand-editing 120 JSONL rows × 9 attributes is miserable and error-prone, so this
exports the pool to CSV (one column per attribute), you label it in whatever
spreadsheet you like, and it imports back with validation.

    cd attribute-extraction
    python label_testset.py export                    # -> testsets/pool_v3.csv
    #   ... fill in the score columns in a spreadsheet, save as CSV ...
    python label_testset.py import_csv --by alex      # -> updates pool_v3.jsonl
    python label_testset.py status                    # how far through you are

**Only five columns are worth your time.** An isolated statement can only
support a human gold label for the text-only attributes plus subject
attribution. The other four are scored elsewhere in v3.0 and a label here would
not evaluate them:

| label these | why |
|---|---|
| `subject` | The fix we most need to verify, and it has no testset at all. |
| `civility`, `rigor`, `specificity`, `focus` | Text-only — the statement *is* the evidence. |

| not these | why not |
|---|---|
| `forthrightness` | Needs a question/answer **pair**. Evasion cannot be seen in one statement, so a label here measures nothing. A separate Q/A pool is needed. |
| `strength`, `authenticity` | Computed from the legislative record, not from text. Human labels would evaluate the *extraction* step, which is a different task with a different format. |
| `veracity`, `divination` | Resolved by search against sources. Labelling them by eye reproduces the ungrounded guess we are removing. |

Run `python label_testset.py guide` for the rubrics, or read the file it writes
next to the CSV. **The Civility scale was re-anchored on 2026-08-07** — 1.0 is
the expected standard and 0.5 is a genuine failure, so hard criticism of a
*policy* now scores near 1.0. Labelling on the old scale would silently poison
the gold set.

**Leave a cell blank rather than guessing.** A blank is "can't tell" and is
skipped; a guessed 0.5 becomes gold that the model is measured against.
"""

from __future__ import annotations

import csv
import json
import os
import sys

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
TESTSETS = os.path.join(HERE, "testsets")
DEFAULT_POOL = os.path.join(TESTSETS, "pool_v3.jsonl")
DEFAULT_CSV = os.path.join(TESTSETS, "pool_v3.csv")

# What a human can usefully label from an isolated statement. Charisma was cut
# on 2026-08-07 and replaced by Focus; the other four v3.0 attributes are scored
# from records or by search, so a by-eye label would not evaluate them. See the
# module docstring and ATTRIBUTES.md.
ATTRIBUTES = ["civility", "rigor", "specificity", "focus"]

# Accepted on import so an older CSV still round-trips, but not exported and not
# requested. Keeping them readable avoids silently dropping existing work.
LEGACY_ATTRIBUTES = ["charisma", "veracity", "divination", "forthrightness",
                     "strength", "authenticity"]

SUBJECT_VALUES = {"speaker", "other", "unclear"}

# Shown for context but never edited; the importer keys on statement_id.
CONTEXT = ["statement_id", "split", "politician", "party", "side", "date", "statement"]

# The labeller-facing rubrics. Deliberately terser than `prompts/` — a person
# labelling 64 rows needs the anchors, not the full prompt. **These must track
# ATTRIBUTES.md**; if the two disagree, ATTRIBUTES.md is right.
RUBRICS = {
    "subject": """Whose conduct does this statement let you judge?

  speaker  the statement is about the speaker's own conduct/record
  other    the speaker is describing SOMEONE ELSE's conduct
           (an opponent's broken promise, a previous government's failure)
  unclear  genuinely ambiguous

This is the single most important column. Scoring an MP down for pointing out
an opponent's failure is the defect v3.0 exists to fix, and it has no testset.
Not a score — use the words.""",

    "civility": """Is the attack on the argument, or on the person?

  1.0   Civil. Engages the substance, attacks no one.
        THIS IS THE STANDARD, NOT AN ACHIEVEMENT.
        Harsh criticism of a POLICY belongs here — near 1.0.
  0.75  Pointed, edging toward the person but not landing on them.
  0.5   A real failure: imputing bad faith, sneering, mockery.
  0.25  A clear personal attack.
  0.0   Contempt — sustained abuse, attacks on character or worth.

RE-ANCHORED 2026-08-07. The old scale put "harsh but legitimate criticism" at
0.5; it is now near 1.0. Do not label from the old rubric.

NOT civility: a false claim (veracity), a fallacy (rigor), an attack on a
PARTY rather than a person (focus).
Ineligible: ceremonial speech — tributes and condolences are trivially civil.""",

    "rigor": """Does the conclusion follow from the premises?

  1.0  Valid inference; the conclusion is supported by what was offered.
  0.5  A reasonable point leaning on an appeal, or with a gap in the logic.
  0.0  Non-sequitur, strawman, false dichotomy, slippery slope, circular
       reasoning, or a bare appeal to emotion/popularity/tradition/authority.

WE ARE NOT FACT-CHECKING. An argument can be perfectly rigorous and built on
FALSE premises — that scores HIGH on rigor and low on veracity. Whether the
assumptions are true is not this column's job.

Ad hominem counts against rigor ONLY when the conclusion rests on it.
  "the policy fails because the member is a fool"        -> low rigor
  "the member is a fool, and the policy fails because X" -> rude, not illogical
Ineligible: statements advancing no argument at all.""",

    "specificity": """Is there checkable content in the statement?

  1.0  Concrete: figures, mechanisms, timeframes, named policies.
  0.5  A direction with some detail, missing the how / how much / by when.
  0.0  Platitude or slogan committing to nothing.

Judge in context — credit detail the speaker actually supplied nearby.
NOT specificity: whether the content is true (veracity), whether it answers a
question (forthrightness).""",

    "focus": """Is this about the policy, or about the other team?

  1.0  Engages the substance: mechanism, cost, effect, who it hits.
  1.0  ALSO legitimate scrutiny — "the government promised 1,000 homes and
       built 200" names a specific policy and outcome. THIS IS THE JOB.
  0.5  A real policy point wrapped in party framing.
  0.0  Purely about the other party — their record in general, their
       hypocrisy, their internal divisions. No policy content.

New in v3.0, replacing Charisma. The gap it fills: attacking a PARTY rather
than a person passes civility cleanly but is pure tribalism.
The deciding test: does it name a specific policy, measure or outcome?
Ineligible: ceremony, procedure, debate with no policy at issue.""",
}


def _load(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _save(rows: list[dict], path: str) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def export(pool: str = DEFAULT_POOL, out: str = DEFAULT_CSV,
           split: str | None = None) -> None:
    """Write the pool to CSV for labelling. Existing labels are pre-filled.

    `--split dev` exports only the dev half, which is what you should label
    first: prompts are iterated against dev, and test is touched once at the
    end (V3_PLAN.md §3.4)."""
    rows = _load(pool)
    if split:
        rows = [r for r in rows if r.get("split") == split]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CONTEXT + ["subject"] + ATTRIBUTES)
        for r in rows:
            gold = r.get("gold") or {}
            w.writerow([r.get(k, "") for k in CONTEXT]
                       + [gold.get("subject", "")]
                       + [gold.get(a, "") for a in ATTRIBUTES])

    # The rubrics go next to the CSV, because labelling from memory is how the
    # re-anchored civility scale would quietly get encoded wrong.
    guide_path = os.path.splitext(out)[0] + "_GUIDE.md"
    with open(guide_path, "w") as f:
        f.write(_guide_text())

    print(f"exported {len(rows)} rows -> {out}")
    print(f"rubrics                -> {guide_path}")
    print(f"\nColumns to fill: subject, {', '.join(ATTRIBUTES)}")
    print("Leave a cell BLANK rather than guessing. Scores 0.0-1.0, higher is better.")
    print("`subject` is speaker | other | unclear, not a score.")
    print("\nNOTE: the civility scale was re-anchored on 2026-08-07 — hard criticism")
    print("of a POLICY now scores near 1.0, not 0.5. Read the guide first.")


def _guide_text() -> str:
    parts = ["# Labelling guide", "",
             "Rubrics for the columns in `pool_v3.csv`. These track "
             "`ATTRIBUTES.md`; if the two ever disagree, that file is right.",
             "",
             "**Leave a cell blank rather than guessing.** Blank means "
             "\"can't tell\" and is skipped. A guessed 0.5 becomes a gold label "
             "the model is then measured against.",
             ""]
    for name in ["subject"] + ATTRIBUTES:
        parts += [f"## {name}", "", "```", RUBRICS[name], "```", ""]
    parts += ["## Columns deliberately absent", "",
              "`forthrightness` needs a question/answer pair, not a statement. "
              "`strength` and `authenticity` are computed from the legislative "
              "record. `veracity` and `divination` are resolved by search "
              "against sources. Labelling any of them by eye here would not "
              "evaluate how they are actually scored.", ""]
    return "\n".join(parts)


def guide() -> None:
    """Print the labelling rubrics."""
    print(_guide_text())


def import_csv(path: str = DEFAULT_CSV, pool: str = DEFAULT_POOL,
               by: str | None = None) -> None:
    """Read labels back in, validate, and merge into the pool by statement_id."""
    if not by:
        raise SystemExit("--by <your name> is required, so we can measure "
                         "inter-annotator agreement later")
    with open(path, newline="") as f:
        incoming = list(csv.DictReader(f))

    rows = _load(pool)
    by_id = {r["statement_id"]: r for r in rows}
    problems, labelled, cells = [], 0, 0

    for lineno, rec in enumerate(incoming, 2):
        sid = (rec.get("statement_id") or "").strip()
        target = by_id.get(sid)
        if not target:
            problems.append(f"line {lineno}: unknown statement_id {sid!r}")
            continue
        gold = dict(target.get("gold") or {})

        subject = (rec.get("subject") or "").strip().lower()
        if subject:
            if subject not in SUBJECT_VALUES:
                problems.append(f"line {lineno}: subject {subject!r} not one of "
                                f"{sorted(SUBJECT_VALUES)}")
            else:
                gold["subject"] = subject
                cells += 1

        for attr in ATTRIBUTES + LEGACY_ATTRIBUTES:
            if attr not in rec:
                continue                  # column absent entirely: leave as-is
            raw = (rec.get(attr) or "").strip()
            if not raw:
                gold.pop(attr, None)      # blank means "not judged"
                continue
            try:
                score = float(raw)
            except ValueError:
                problems.append(f"line {lineno}: {attr}={raw!r} is not a number")
                continue
            if not 0.0 <= score <= 1.0:
                problems.append(f"line {lineno}: {attr}={score} outside 0.0-1.0")
                continue
            gold[attr] = score
            cells += 1

        # Assign unconditionally. Guarding on `if gold` would mean that blanking
        # every cell in a row left the old labels in place, so a label could
        # never be retracted — you would have to edit the JSONL by hand.
        target["gold"] = gold
        target["labelled_by"] = by if gold else None
        if gold:
            labelled += 1

    if problems:
        print(f"{len(problems)} problem(s) — NOTHING WRITTEN:", file=sys.stderr)
        for p in problems[:25]:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)

    _save(rows, pool)
    print(f"merged labels for {labelled} statement(s), {cells} cells -> {pool}")
    status(pool)


def status(pool: str = DEFAULT_POOL) -> None:
    """How much of the pool is labelled, by split and attribute."""
    from collections import Counter
    rows = _load(pool)
    done = [r for r in rows if r.get("gold")]
    print(f"\n{len(done)}/{len(rows)} statements have at least one label")

    by_split = Counter(r["split"] for r in done)
    for s in ("dev", "test"):
        total = sum(1 for r in rows if r["split"] == s)
        print(f"  {s:5} {by_split.get(s, 0):4}/{total}")

    print("\nlabels per attribute:")
    counts = Counter(a for r in done for a in (r.get("gold") or {}))
    for a in ["subject"] + ATTRIBUTES:
        n = counts.get(a, 0)
        flag = "  <- needs >=100 for a usable testset" if 0 < n < 100 else ""
        print(f"  {a:16} {n:4}{flag}")
    stale = {a: counts[a] for a in LEGACY_ATTRIBUTES if counts.get(a)}
    if stale:
        print("\nlabels on attributes no longer scored from text "
              "(kept, but not evaluated):")
        for a, n in stale.items():
            print(f"  {a:16} {n:4}")

    annotators = Counter(r.get("labelled_by") for r in done if r.get("labelled_by"))
    if annotators:
        print("\nannotators:", dict(annotators))
        doubled = sum(1 for r in done if isinstance(r.get("labelled_by"), list))
        if len(annotators) > 1:
            print(f"double-labelled: {doubled} (needed for inter-annotator agreement)")


if __name__ == "__main__":
    fire.Fire({"export": export, "import_csv": import_csv, "status": status,
               "guide": guide})
