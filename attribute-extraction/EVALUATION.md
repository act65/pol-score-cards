# Attribute Extraction — Evaluation

How we measure whether the LLM scoring is any good, and where the numbers come from.

## What is evaluated

The testsets in `testsets/` split into two tasks:

| Testset | Task | Gold field | Wired into `evaluate.py`? |
|---|---|---|---|
| `civility_testset.jsonl` | score a statement 0..1 | `civility_score` | ✅ |
| `veracity_testset.jsonl` | score a statement 0..1 | `veracity_score` | ✅ |
| `evasion.jsonl` | detect evasion (binary) | `contains_evasion` | ⬜ detection — not yet wired |
| `integrity.jsonl` | detect a factual claim (binary) | `contains_claim` | ⬜ detection — not yet wired |

`evaluate.py` currently covers the **scoring** testsets. Each row is a single,
pre-isolated statement with a human-assigned gold score; the harness calls
`extract.score_statement` with the matching prompt and compares.

## Metrics

For each attribute, over its testset (`n` rows):

- **MAE** — mean absolute error on the 0..1 scale. Interpretable directly: 0.10
  means predictions are off by 0.1 on average.
- **RMSE** — penalises large misses more than MAE.
- **Pearson r** — linear agreement between predicted and gold scores. This is
  the headline number: it tells you whether the model *ranks* statements the way
  the rubric does, even if it's systematically high or low.
- **Binary accuracy** — agreement after thresholding both at 0.5 ("acceptable"
  vs "not"). A coarse but intuitive pass/fail view.

The metric functions are pure Python and unit-tested offline in
`test_evaluate.py` (`pytest test_evaluate.py`) — no API key needed to trust the
arithmetic.

## Running it

```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python evaluate.py run all            # writes eval_report.json
python evaluate.py run civility       # single attribute
python evaluate.py run veracity --model claude-haiku-4-5   # cheaper model
```

`eval_report.json` contains per-attribute metrics plus per-statement
predicted/gold/error/explanation so you can eyeball the worst misses.

## Results

Live run, `claude-opus-4-8`, 2025-06-19 (`python evaluate.py run all`):

```
  civility       n=14  MAE=0.129  RMSE=0.175  r=0.882  binacc=0.857
  veracity       n=14  MAE=0.139  RMSE=0.199  r=0.734  binacc=0.786
```

**Reading it:** On these (small) held-out sets, the model ranks statements much
the way the human rubric does — civility correlation 0.88 is strong, veracity
0.73 is good. Average error is ~0.13 on the 0–1 scale, and binary "acceptable vs
not" agreement is 0.86 / 0.79.

**The instructive miss confirms the trust caveat.** The single largest veracity
error (0.5) was the claim *"My opponent voted against clean water initiatives 17
times"*: gold = 0.0 (false), model = 0.5. The model correctly reasoned it
*couldn't verify the voting record* and hedged to the middle — exactly the
behaviour the README's trust table predicts for veracity (LLM identifies the
claim; a fact-checking step must score it). Civility/specificity, which are
judgeable from the text alone, score higher and more reliably. Full
per-statement predictions and explanations are in `eval_report.json`.

### Model comparison — can a cheaper model do the scoring?

We score on a Claude Pro subscription via the `claude -p` CLI backend (no API
credits), so it's worth knowing whether a cheaper/faster model is good enough.
`evaluate.py compare` runs the testsets across several models:

```
python evaluate.py compare        # opus-4-8 vs sonnet-4-6 vs haiku-4-5 (~28 calls/model)
```

Prelim run, CLI backend, 2026-06-20 (best `r` first):

| Attribute | Model | n | MAE ↓ | RMSE ↓ | Pearson r ↑ | Binary acc ↑ |
|---|---|---:|---:|---:|---:|---:|
| **civility** | claude-opus-4-8   | 14 | **0.196** | **0.259** | **0.627** | **0.714** |
|              | claude-haiku-4-5  | 14 | 0.250 | 0.286 | 0.433 | 0.571 |
|              | claude-sonnet-4-6 | 14 | 0.275 | 0.315 | 0.186 | 0.643 |
| **veracity** | claude-opus-4-8   | 14 | **0.204** | **0.254** | **0.489** | **0.714** |
|              | claude-sonnet-4-6 | 14 | 0.250 | 0.296 | 0.191 | 0.357 |
|              | claude-haiku-4-5  | 14 | 0.289 | 0.316 | -0.033 | 0.429 |

**Conclusion: keep Opus for scoring — the cheaper models don't hold up.**
`claude-opus-4-8` is best on every metric for both attributes. Dropping to
Sonnet or Haiku roughly halves (or worse) the rank correlation — Sonnet's
civility `r` falls 0.63 → 0.19, and Haiku's veracity `r` collapses to ≈0 (no
better than random ranking). MAE also worsens by 5–9 points on the 0–1 scale.
On a tiny set these are directional, but the gap is large and consistent enough
that downgrading the scorer isn't worth the quality loss.

> **Backend caveat.** This comparison ran through the **CLI** backend (loose
> "return a JSON array" prompting), whereas the headline run above used the
> **Anthropic API** with structured outputs (`messages.parse`). That's why
> Opus's absolute numbers here (civility `r`=0.63) are lower than the API run
> (`r`=0.88): the structured-output harness is stronger. The cross-model
> *ranking* is what's robust — all three models ran through the identical CLI
> harness, so the comparison is apples-to-apples even if the absolute scores
> are pessimistic. For the best absolute quality, score with the API backend.

### ⚠ The testsets are synthetic — the headline numbers do not measure this task

**Found 2026-08-01.** Every row in `testsets/` is an *invented* statement
attributed to a fictional politician: "Senator Armstrong", "Governor Miller",
"Councilperson Davis", "Mayor Garcia", "Minister Brown". There is no New
Zealander in any testset, and not one line of Hansard.

| Testset | n | Speakers |
|---|---:|---|
| `civility_testset.jsonl` | 14 | Senator / Governor / Councilperson / Mayor (fictional) |
| `veracity_testset.jsonl` | 14 | Senator / Governor / Commissioner (fictional) |
| `evasion.jsonl` | 10 | Minister Brown / Mr Green / Ms Black (fictional) |
| `integrity.jsonl` | 15 | unattributed |

So `civility r=0.88` was measured on made-up American-register statements. The
production task is adversarial New Zealand parliamentary speech — a different
register, different conventions, and far more combative than the polite council
-meeting tone of the synthetic set. **The number is not evidence about the
system we actually run**, and growing these sets would have compounded the
problem rather than fixed it.

Replacement is under way (`build_testsets.py`): candidates are sampled from the
real corpus — 228,688 labellable passages — stratified by government/opposition
and month, and emitted **unlabelled** for human scoring. A 120-item pool is
drawn and split deterministically into dev/test by content hash, so the split
cannot drift or be re-rolled to flatter a prompt.

```
cd attribute-extraction
python build_testsets.py sample --n 120        # -> testsets/pool_v3.jsonl (unlabelled)
python build_testsets.py check_leakage         # enforced in test_testsets.py
```

Until that pool is labelled, **treat every accuracy figure in this document as
unvalidated.**

### Methodology caveats (important for interpreting results)

- **Tiny testsets (n≈14).** These numbers are directional, not statistically
  robust. Treat a high `r` as "promising", not "validated". Grow the testsets
  before drawing strong conclusions.
- **Trust varies by attribute.** Per `README.md`, civility/specificity/
  forthrightness are plausibly LLM-scorable end-to-end; veracity/strength/
  divination need external verification, so a good `r` on the veracity testset
  reflects the model judging *plausibility*, not ground-truth fact-checking.
- **Prompt/testset leakage.** Several prompts embed few-shot examples. Keep
  those examples disjoint from the testsets, or the scores are inflated. This is
  tracked as a known cleanup task (see the prompt-improvement work).

---

## Known defect: subject attribution in Strength & Authenticity

**Status: open, affects the live dataset.** Found 2026-08-01 while pulling
example quotes for a write-up.

### The problem

Strength and Authenticity are usually *discussed* rather than *demonstrated*.
An MP stands up and describes an opponent's broken promise or hypocrisy — the
model correctly identifies that this is a low-delivery / low-consistency signal
**about the opponent**, says so in its explanation, and emits a low score. The
pipeline then files that score under the **speaker**, because `politician_id` is
the person who said the sentence.

Net effect: **an MP is penalised for pointing out someone else's failure.**

Verbatim from the live data (`site/static/examples.jsonl`) — all three of these
land on the *speaker's* card:

| Statement (excerpt) | Filed under | Score | Model's own explanation |
|---|---|---|---|
| "They promised 500 extra police, but … they've failed to deliver" | Ginny Andersen (Lab) | Strength 15 | "*Describes an opponent's undelivered promise*" |
| "only build 446 houses of the 2050 he promised" | Kieran McAnulty (Lab) | Strength 15 | "*a low-strength signal for the responsible minister, not the speaker*" |
| "Christopher Luxon promised to fix the economy … Instead, he has made both worse." | Barbara Edmonds (Lab) | Authenticity 30 | "*a low-authenticity charge about the opponent, not Edmonds*" |

### Size of the problem

Counting examples whose `explanation` names another actor as the subject
(regex over `explanation`: `opponent|not the speaker|those responsible|
responsible minister|prior government|previous government|about that
(Minister|Government)|about the Government|about them|directed at`):

| Attribute | All examples | Flagged | Of the low ones (score ≤ 30) |
|---|---:|---:|---:|
| Authenticity | 3,004 | 150 (5.0%) | **28 of 75 (37%)** |
| Strength | 4,845 | 57 (1.2%) | **20 of 276 (7%)** |

The regex is a **lower bound** — it only catches cases where the model
volunteered the subject. Flagged examples average **45.1** vs **65.7** for
unflagged Authenticity, so each one drags its card down ~20 points.

### It is a *directional* bias, not noise

Opposition MPs spend most of their airtime describing government failures —
which is their constitutional job — so they absorb most of the mis-attribution:

| Attribute | Govt MPs flagged | Opposition MPs flagged |
|---|---:|---:|
| Authenticity | 48 / 1,962 (2.4%) | 102 / 1,042 (**9.8%**) |
| Strength | 25 / 4,159 (0.6%) | 32 / 686 (**4.7%**) |

Dropping the flagged examples moves party means in the expected direction —
Labour's Authenticity 65.3 → 68.3, Green 69.7 → 72.1, while National barely
moves (61.0 → 61.2). **The pipeline currently penalises scrutiny.**

### Root cause

Both prompts *anticipate* the case and still let it through.

`prompts/authenticity.txt` ends with:

> "Attacking an opponent's hypocrisy is itself a (low-authenticity) signal about
> that opponent, not the speaker."

— which tells the model to score it, without ever saying *whose* card it belongs
to. Nothing downstream can act on the distinction, because the extraction schema
(`politician`, `statement`, `score`, `explanation`) has **no field for the
subject of the judgement**; `politician` means "who said it".

`prompts/strength.txt` is worse — it teaches the behaviour by example:

> "Year after year they promised to fix the hospital and year after year nothing
> was built." → 0.1 (describes repeated non-delivery — low strength for those
> responsible)

That few-shot example is the bug, written down.

### Fix options

1. **Cheapest, no re-run — post-hoc filter.** Exclude flagged examples from the
   card means at build time (`build_site_data.py` / `bias_adjust.py`). Regex is a
   crude classifier; a single cheap Haiku pass over the ~8k Strength/Authenticity
   explanations ("is the subject of this judgement the speaker?") would be
   better and costs very little. **Do this first** — it repairs the live site.
2. **Correct fix — add `subject` to the schema.** Extend the structured output
   to `subject: "speaker" | "other" | "unclear"` (plus optionally the named
   other party), and have the builder keep only `speaker`. Cost: one schema
   change + a re-run of these two attributes.
3. **Fix the prompts** (needed either way, and cheap):
   - `strength.txt` — delete the "year after year they promised" few-shot, or
     flip it to score **0.5 / skip** with the reason "subject is a third party".
   - `authenticity.txt` — change the note from "*is a signal about that
     opponent*" to "**skip it — do not emit a score for statements judging
     someone other than the speaker**".
   - Add to both: "Only score a statement when the person being judged is the
     speaker, their own party, or their own government."
4. **Bonus, if (2) is done.** A statement judging an opponent is not waste — it
   is a *claim about that opponent* that could feed their card once verified.
   That is the claims ledger in `PITCH.md`, and `subject` is the field it needs.

### Until it is fixed

Strength and Authenticity should be **read with a heavy discount**, and are not
suitable as illustrative examples. The other seven attributes are unaffected:
Civility, Rigor, Specificity, Forthrightness, Charisma, Veracity and Divination
all score the statement *as spoken*, so speaker and subject coincide.

---

## Grounding Strength & Authenticity in the record (v3.0)

The deeper problem behind the defect above: **neither attribute is a property of
a statement.** Both are *relations* between what someone said and an external
record — how they voted, what they delivered. The current pipeline asks a model
to score a relation while showing it only one side of it, which is why it
returns plausibility rather than fact, and why the schema has nowhere to put
*whose* record is at issue.

The fix is an intermediate **ledger**: extract `(subject, proposition, stance or
promise, date, evidence)` from statements, normalise the vote/bill record to the
same propositions, join, and make the card score an *aggregate over the ledger*
rather than a mean of per-statement LLM scores. `subject` then has a home, and
rows with `subject: other` become the claims ledger in `PITCH.md`.

**Step 1 is done — the substrate exists, and it cost no LLM quota.**
See `data/VOTES.md`:

- `data/corpus/divisions.jsonl` — **984 party votes** parsed straight out of the
  Hansard corpus we had already scraped (154 sitting days, 2023-07-18 →
  2026-05-28): tallies, named dissenters, result, and bill context.
- `data/corpus/bills.jsonl` — every bill of the 53rd and 54th Parliaments from
  the public `bills.parliament.nz` JSON API: stage history, MP in charge,
  and whether it was enacted, terminated or is still in progress.

`voted.nz` turned out not to be usable — it tracks personal (conscience) votes
only, no party votes, and has no API.

Three constraints that must shape the scoring design, all documented with
numbers in `data/VOTES.md`:

1. **The signal is mostly party-level.** NZ party discipline is near-absolute,
   so a party vote assigns one position to all 48 National MPs. Real per-MP
   variance exists only in individually-named dissenters and conscience votes.
2. **Always report against the party-line baseline** (~97%). An accuracy figure
   without it says nothing.
3. **Strength needs a delivery-scope gate.** Only ministers and members in
   charge of a bill can deliver one; scoring an opposition backbencher low for
   not delivering repeats the subject-attribution error in a new form. And
   `pending` must be kept distinct from `abandoned` — a promise made in 2026
   cannot resolve before the election.

Remaining steps are tracked in `TODOs` under "EVIDENCE-BASED STRENGTH &
AUTHENTICITY (v3.0)".
