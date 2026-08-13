"""Round-trip the labelling pool through a browser page.

    cd attribute-extraction
    python label_testset.py add_context               # attach each window ONCE
    python label_testset.py export_html --split dev   # -> testsets/pool_v3.html
    #   ... open it, label, click "Download labels" ...
    python label_testset.py import_json --path pool_v3_labels.jsonl --by alex
    python label_testset.py status                    # how far through you are

**Why this is not a spreadsheet any more.** The first design exported one
sentence per row and asked for a score. But the extractor judges a statement
inside a ~3,000-token window, and stripped of that window many statements are
simply not judgeable — "That's the start of the period and the thinking at the
time" says nothing on its own. The labeller was being given a harder task than
the model, on less evidence, and a disagreement could not be attributed: model
error, or a human denied the context? `add_context` rebuilds the exact windows
from the same corpus and the same packing, so both now answer the same question.

A 3,000-token window does not fit in a spreadsheet cell, hence the page. It
shows one item at a time with the statement highlighted in its debate, keeps the
rubric on screen, and saves to the browser's local storage as you go.

**Three kinds of answer, and the last two matter as much as the score:**

| answer | meaning |
|---|---|
| a score | the attribute applies and this is its value |
| `n/a` | the attribute does not apply here — so if the model scored it, that is a **false positive**, which a score-only testset cannot detect |
| `can't tell` | not judgeable even with the window. If a human says this often, the question is unanswerable and the model's confidence is the defect |

The old CSV path (`export` / `import_csv`) still works and still round-trips.

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

import collections
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


# How much of the original window to show the labeller. The extractor saw a
# ~3,000-token window; showing the same text is the whole point, so this is a
# safety cap for pathological days rather than a trim.
MAX_CONTEXT_CHARS = 14000


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def add_context(pool: str = DEFAULT_POOL,
                corpus: str = "../data/corpus/hansard_v2.json",
                window_tokens: int = 3000) -> None:
    """Attach to each pool item the window the MODEL was shown.

    **This is the fix for the original labelling design.** The pool held a lone
    sentence, so a labeller was asked to judge "That's the start of the period
    and the thinking at the time" with no idea what period, what thinking, or
    what was being debated. The model, meanwhile, saw ~3,000 tokens around it.

    Two people doing different tasks cannot be compared. Any disagreement was
    uninterpretable: model error, or a human denied the evidence? Rebuilding the
    same windows — from the same corpus, the same prep, the same packing — means
    the labeller and the model finally answer the same question.
    """
    import hansard_prep
    import extract_hansard

    rows = _load(pool)
    dates = sorted({r["date"] for r in rows})
    by_day = extract_hansard._load_by_day(corpus, dates[0], dates[-1])

    found = 0
    cache: dict[str, list] = {}
    for r in rows:
        if r["date"] not in cache:
            parts = by_day.get(r["date"]) or []
            cache[r["date"]] = (extract_hansard._windows(
                hansard_prep.prep_day(parts), window_tokens) if parts else [])
        target = _norm(r["statement"])
        for i, w in enumerate(cache[r["date"]]):
            if target in _norm(w):
                r["window"] = w[:MAX_CONTEXT_CHARS]
                r["window_id"] = f"{r['date']}#{i}"
                found += 1
                break
        else:
            # No window means no context, and no context means the item is not
            # labellable. Better to know that than to ship it blind.
            r["window"] = None
            r["window_id"] = None

    _save(rows, pool)
    print(f"{found}/{len(rows)} items matched to their window "
          f"({100 * found / len(rows):.0f}%)")
    if found < len(rows):
        print(f"{len(rows) - found} could not be located and will be flagged "
              f"as unlabellable in the export.")


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


# --- HTML labelling page ------------------------------------------------------
#
# CSV was the wrong medium once context came back: a spreadsheet cell cannot
# hold 3,000 tokens of debate, and the labeller ends up scrolling a wall of
# quoted text with the statement lost inside it. The page below shows one item
# at a time, highlights the target statement inside its window, and keeps the
# rubric for the attribute being judged on screen.
#
# Two answers matter as much as the scores:
#   n/a        — this attribute does not apply here. Measures the model's
#                FALSE POSITIVES, which a score-only testset cannot see.
#   can't tell — not judgeable even with the window. If a human says this
#                often, the instrument is asking an unanswerable question and
#                the model's confident answer is the problem.

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Label pool_v3</title><style>
:root{--bg:#fbfbfa;--fg:#1a1a1a;--mut:#666;--line:#e0ddd8;--hl:#ffe9a8;--acc:#2f5d8a}
*{box-sizing:border-box}
body{margin:0;font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
background:var(--bg);color:var(--fg)}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:9}
header b{font-size:14px}
.bar{flex:1;height:6px;background:var(--line);border-radius:3px;min-width:120px}
.bar>i{display:block;height:100%;background:var(--acc);border-radius:3px;width:0}
main{max-width:1180px;margin:0 auto;padding:20px;display:grid;
grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:22px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:16px}
.meta{color:var(--mut);font-size:13px;margin-bottom:10px}
.win{white-space:pre-wrap;max-height:60vh;overflow:auto;font-size:14px;
background:#fcfbf9;border:1px solid var(--line);border-radius:6px;padding:12px}
mark{background:var(--hl);padding:1px 0;font-weight:600}
h3{margin:18px 0 4px;font-size:14px;text-transform:uppercase;letter-spacing:.04em}
.rub{white-space:pre-wrap;font-size:12.5px;color:#444;background:#faf9f7;
border-left:3px solid var(--line);padding:8px 10px;margin:6px 0 10px}
.opts{display:flex;flex-wrap:wrap;gap:6px}
button.o{border:1px solid var(--line);background:#fff;border-radius:6px;padding:6px 11px;
cursor:pointer;font:inherit;font-size:13px}
button.o:hover{border-color:var(--acc)}
button.o.on{background:var(--acc);border-color:var(--acc);color:#fff}
button.o.na.on{background:#8a8a8a;border-color:#8a8a8a}
button.o.ct.on{background:#a8562f;border-color:#a8562f}
nav{display:flex;gap:8px;margin-top:18px;align-items:center}
nav button{padding:8px 16px;border-radius:6px;border:1px solid var(--line);
background:#fff;cursor:pointer;font:inherit}
nav button.pri{background:var(--acc);color:#fff;border-color:var(--acc)}
textarea{width:100%;min-height:52px;border:1px solid var(--line);border-radius:6px;
padding:8px;font:inherit;font-size:13px;resize:vertical}
.warn{background:#fff4f4;border:1px solid #e8c4c4;padding:10px;border-radius:6px;
color:#8a2f2f;font-size:13px}
</style></head><body>
<header>
  <b id="pos"></b><div class="bar"><i id="prog"></i></div>
  <span id="cnt" style="font-size:13px;color:var(--mut)"></span>
  <button onclick="dl()" style="padding:6px 14px;border-radius:6px;
    border:1px solid var(--line);background:#fff;cursor:pointer;font:inherit">
    Download labels</button>
</header>
<main>
  <div class="card">
    <div class="meta" id="meta"></div>
    <div class="win" id="win"></div>
  </div>
  <div class="card" id="form"></div>
</main>
<script>
const ITEMS=__ITEMS__, RUBRICS=__RUBRICS__, ATTRS=__ATTRS__;
const KEY="pool_v3_labels";
let L=JSON.parse(localStorage.getItem(KEY)||"{}"), i=0;
const SCORES=[["0.0","0"],["0.25",".25"],["0.5",".5"],["0.75",".75"],["1.0","1"]];
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

function set(id,f,v){ (L[id]=L[id]||{})[f]=v; localStorage.setItem(KEY,JSON.stringify(L)); render(); }

function opts(id,f,vals,cls){
  const cur=(L[id]||{})[f];
  return `<div class="opts">`+vals.map(([v,lab])=>
    `<button class="o ${cls||''} ${cur===v?'on':''}" onclick="set('${id}','${f}',${cur===v?'null':`'${v}'`})">${lab}</button>`
  ).join("")+`</div>`;
}

function render(){
  const it=ITEMS[i], id=it.statement_id, done=Object.keys(L).filter(k=>Object.values(L[k]||{}).some(v=>v)).length;
  document.getElementById("pos").textContent=`${i+1} / ${ITEMS.length}`;
  document.getElementById("prog").style.width=(100*done/ITEMS.length)+"%";
  document.getElementById("cnt").textContent=`${done} labelled`;
  document.getElementById("meta").innerHTML=
    `<b>${esc(it.politician)}</b> · ${esc(it.party||"")} · ${esc(it.side||"")} · ${it.date}`
    +(it.window_id?` · window ${it.window_id}`:"");
  const w=document.getElementById("win");
  if(!it.window){ w.innerHTML=`<div class="warn">No window could be recovered for this
    statement, so there is not enough context to label it. Skip it.</div>
    <p style="margin-top:10px">${esc(it.statement)}</p>`; }
  else { const n=s=>s.replace(/\s+/g," ");
    const wi=n(it.window), st=n(it.statement), at=wi.indexOf(st);
    w.innerHTML = at<0 ? esc(it.window)
      : esc(wi.slice(0,at))+"<mark>"+esc(st)+"</mark>"+esc(wi.slice(at+st.length)); }

  let h=`<h3>subject</h3><div class="rub">${esc(RUBRICS.subject)}</div>`
    + opts(id,"subject",[["speaker","speaker"],["other","other"],["unclear","unclear"]]);
  for(const a of ATTRS){
    h+=`<h3>${a}</h3><div class="rub">${esc(RUBRICS[a])}</div>`
      + opts(id,a,SCORES)
      + `<div class="opts" style="margin-top:6px">`
      + `<button class="o na ${(L[id]||{})[a]==="n/a"?"on":""}" onclick="set('${id}','${a}',${(L[id]||{})[a]==="n/a"?"null":"'n/a'"})">n/a — doesn't apply</button>`
      + `<button class="o ct ${(L[id]||{})[a]==="?"?"on":""}" onclick="set('${id}','${a}',${(L[id]||{})[a]==="?"?"null":"'?'"})">can't tell</button>`
      + `</div>`;
  }
  h+=`<h3>note</h3><textarea onchange="set('${id}','note',this.value)"
      placeholder="optional — especially useful when you disagree with yourself">${
      esc(((L[id]||{}).note)||"")}</textarea>`;
  h+=`<nav><button onclick="go(-1)">&larr; prev</button>
      <button class="pri" onclick="go(1)">next &rarr;</button>
      <span style="color:var(--mut);font-size:13px">progress saves automatically</span></nav>`;
  document.getElementById("form").innerHTML=h;
}
function go(d){ i=Math.max(0,Math.min(ITEMS.length-1,i+d)); window.scrollTo(0,0); render(); }
document.addEventListener("keydown",e=>{ if(e.target.tagName==="TEXTAREA")return;
  if(e.key==="ArrowRight")go(1); if(e.key==="ArrowLeft")go(-1); });
function dl(){
  const out=ITEMS.filter(t=>L[t.statement_id]).map(t=>({statement_id:t.statement_id,...L[t.statement_id]}));
  const b=new Blob([out.map(o=>JSON.stringify(o)).join("\n")],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(b);
  a.download="pool_v3_labels.jsonl"; a.click();
}
render();
</script></body></html>"""


def export_html(pool: str = DEFAULT_POOL, out: str = "testsets/pool_v3.html",
                split: str | None = None) -> None:
    """Write a self-contained labelling page — the statement in its window.

    Open the file in a browser, label, then click **Download labels** and run
    `import_json`. Progress is kept in the browser's local storage, so closing
    the tab does not lose work.
    """
    rows = _load(pool)
    if split:
        rows = [r for r in rows if r.get("split") == split]
    missing = [r for r in rows if not r.get("window")]
    if missing and len(missing) == len(rows):
        raise SystemExit("no windows attached — run `add_context` first")

    keep = ("statement_id", "politician", "party", "side", "date",
            "statement", "window", "window_id")
    items = [{k: r.get(k) for k in keep} for r in rows]
    html = (_PAGE
            .replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
            .replace("__RUBRICS__", json.dumps(RUBRICS, ensure_ascii=False))
            .replace("__ATTRS__", json.dumps(ATTRIBUTES)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"exported {len(rows)} items -> {out}")
    if missing:
        print(f"  {len(missing)} have no window and are flagged unlabellable")
    print(f"\n  open {os.path.abspath(out)}")
    print("  label, click 'Download labels', then:")
    print(f"  python label_testset.py import_json --path pool_v3_labels.jsonl --by <name>")


def import_json(path: str, pool: str = DEFAULT_POOL, by: str | None = None) -> None:
    """Merge labels downloaded from the HTML page into the pool.

    `n/a` and `?` are stored as-is rather than as numbers. They are answers, not
    missing data: `n/a` says the attribute should not have fired here (a false
    positive if the model scored it) and `?` says the item is not judgeable even
    with its window. Coercing either to a number would erase the finding.
    """
    if not by:
        raise SystemExit("--by <your name> is required, so we can measure "
                         "inter-annotator agreement later")
    incoming = _load(path)
    rows = _load(pool)
    by_id = {r["statement_id"]: r for r in rows}

    merged, unknown, counts = 0, 0, collections.Counter()
    for rec in incoming:
        row = by_id.get(rec.get("statement_id"))
        if not row:
            unknown += 1
            continue
        gold = dict(row.get("gold") or {})
        for field, value in rec.items():
            if field == "statement_id" or value in (None, ""):
                continue
            if field == "note":
                gold["note"] = value
            elif field == "subject":
                if value not in SUBJECT_VALUES:
                    raise SystemExit(f"bad subject {value!r} for {rec['statement_id']}")
                gold["subject"] = value
            elif field in ATTRIBUTES + LEGACY_ATTRIBUTES:
                gold[field] = value if value in ("n/a", "?") else float(value)
                counts[value if value in ("n/a", "?") else "scored"] += 1
        row["gold"] = gold
        row["labelled_by"] = by
        merged += 1

    _save(rows, pool)
    print(f"merged {merged} items from {path}" + (f", {unknown} unknown ids" if unknown else ""))
    print(f"  scored {counts['scored']}, n/a {counts['n/a']}, can't tell {counts['?']}")
    if counts["?"]:
        print("  'can't tell' is a finding: those items are not judgeable even "
              "with the window, so the model should not be confident there either.")


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
    fire.Fire({"export": export, "export_html": export_html,
               "import_csv": import_csv, "import_json": import_json,
               "add_context": add_context, "status": status, "guide": guide})
