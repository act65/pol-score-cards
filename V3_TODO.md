# v3.0 — the backlog

Companion to `V3_PLAN.md` (why) and `ATTRIBUTES.md` (what each attribute means).
This file is the ordered work list.

**Owner tags:** 🧑 = you, 🤖 = me, 🧑🤖 = needs a decision from you, then me.

---

## What changed on 2026-08-07

Three measurements were added, all deterministic and re-runnable. They turn
"the attributes feel correlated" into numbers we can hold a rewrite to.

| Tool | Output | Headline |
|---|---|---|
| `attribute_overlap.py` | `ATTRIBUTE_OVERLAP.md` | Rigor correlates >0.65 with six of eight attributes. Veracity/Rigor **0.83**. |
| `check_quotes.py` | `QUOTE_AUDIT.md` | 85% of quotes verbatim; **6% not in the source**, 9% ellipsis-spliced, 25% cut mid-sentence. |
| `ATTRIBUTES.md` | — | One failure mode per attribute, with an ownership ledger for the moves that currently double-count. |

**The three findings that should drive everything below.**

1. **Rigor is the hub of the redundancy.** Its prompt has become a general
   "is this a good argument" score. r=0.85 with Civility, 0.83 with Veracity,
   0.83 with Charisma, 0.73 with Forthrightness, 0.72 with Divination.
2. **Veracity is not measuring truth.** Its prompt says to score how
   well-evidenced a claim *looks* and to "prefer ~0.5" when it cannot verify —
   which is a reasoning judgement, not a fact check. It fires on 41% of the
   corpus and duplicates Rigor.
3. **6% of quotes are not in the transcript.** Sampled, ±1.7pp. Every score
   links to a quote, so this is the auditability promise failing.

---

## Phase A — repair the instrument *(no LLM quota)* — **DONE 2026-08-07**

- [x] 🧑🤖 ~~Resolve Charisma~~ → **cut, replaced by Focus.**
- [x] 🤖 **All nine prompts rewritten to `ATTRIBUTES.md`.** Each carries THE ONE
      QUESTION, an eligibility gate, named disclaimers for the neighbouring
      attributes, and worked boundary examples. The critical one is in
      `rigor.txt`: *"Unemployment is at 40 percent, so the labour market is in
      crisis" → 0.85 rigor.* Valid inference, false premise.
- [x] 🤖 **Double-counted moves reassigned:** strawman Civility→Rigor; hyperbole
      Civility→Veracity; ad hominem stays Civility and counts against Rigor only
      where the conclusion rests on it.
- [x] 🤖 **Veracity and Divination no longer score at all.** They emit a claim
      plus a `falsification_criterion` (plus `resolve_by` for Divination) and the
      resolver assigns the score later. `score` is `None` — a pending row, never
      a zero.
- [x] 🤖 **Eligibility gates in the prompts and the preamble**, with "returning
      nothing is a correct and expected outcome" stated explicitly. Gate
      statistics are collected during the run and printed at the end.
- [x] 🤖 **Quote-fidelity gate is live in `extract.py`.** Non-verbatim,
      ellipsis-spliced and mid-sentence quotes are dropped before they reach
      disk. 18 tests in `tests/test_extract_gates.py`.
- [x] 🤖 **Removed** the "resolve pronouns/ambiguity" licence from
      `divination.txt`, and deleted the superseded `charisma.txt`, `true.txt`,
      `promises.txt` and `fewshot_examples.md`.
- [x] 🤖 **`attributes.py` is the single source of truth** for the attribute
      set, its tiers and its card-facing definitions. `build_v2_dataset.py` and
      the icon map now read from it; `tests/test_registry_consistency.py` fails
      if a copy drifts.
- [ ] 🤖 **Delete `attribute-extraction/roster.py`** — still outstanding. It is a
      seventh near-copy of the name logic and lacks the "Surname, Given" and
      "on behalf of" handling `data/names.py` has, so scores may be splitting
      across spelling variants. Check the blast radius on published cards first.
- [ ] 🤖 Re-run both audits on v3.0 output; hold to the targets in
      `ATTRIBUTES.md`. `overnight_run.py` does this automatically at the end of
      a stage.

## Phase B — evaluation *(the main deliverable; mostly no quota)*

### B1. Ground truth

- [ ] 🧑 **Label the 120-item pool.** Still the blocking manual step.
      ```bash
      cd attribute-extraction
      python label_testset.py export --split dev     # -> testsets/pool_v3.csv (64 rows)
      python label_testset.py import_csv --by <name>
      python label_testset.py status
      ```
      Leave a cell blank rather than guessing — blank means "not judged", a
      guessed 0.5 becomes gold. `subject` takes `speaker|other|unclear`.
- [x] 🧑🤖 ~~Decide the labelling corpus~~ → **the 54th.** Publishing the corpus
      does not disqualify it; hold back the labels, not the statements.
- [ ] 🤖 **Re-anchored Civility means the pool needs re-labelling guidance**, not
      re-drawing. The statements are fine; the rubric handed to the labeller
      must be the new one (1.0 = expected standard, 0.5 = genuine failure).
      ⚠️ Do this **before** you start labelling, or the gold labels encode the
      old scale.
- [ ] 🧑 **Double-label ~50 items** (second annotator) for inter-annotator
      agreement. Without it an r of 0.88 is uninterpretable: we cannot tell
      model error from rubric ambiguity.
- [ ] 🤖 **Subject-attribution testset.** The fix we most need to verify has no
      testset at all. Sampler already emits the fields.
- [ ] 🤖 Grow toward n ≥ 100 **per attribute** (currently 120 total, unlabelled).

### B2. The 53rd Parliament *(2020-11-25 → 2023-08-31)*

Your suggestion, and it is stronger than it first looks — it is the only way to
ground Divination, and it doubles as a bias check.

- [ ] 🤖 **Scrape it.** Mechanically straightforward: `hansard.py`'s
      `_enumerate_day_urls` walks weekdays and non-sitting days render nothing,
      so it is the existing Playwright path over a wider date range. ~730
      weekdays, ~250 sitting. Budget **12–18h wall clock**; resumable. Best run
      overnight or on the scraping VM (`data/CLOUD_SCRAPING.md`).
- [ ] 🤖 **Resolve predictions against outcomes** → the first real Divination
      ground truth. Predictions made 2020–2023 have known answers now.
- [ ] 🤖 **Resolve 2020 Labour manifesto promises** → Strength ground truth with
      a completed term behind it.
- [ ] 🤖 **Run the instrument on a Labour-majority Parliament as a bias check.**
      If the rubric is politically neutral, a Labour government should score
      about where a National-led coalition does. If it does not, we have found a
      bias in the instrument, not a fact about either party. This is the single
      most valuable check available and it needs no human labels.
- [ ] ⚠️ **Roster.** The 53rd has a different membership. `mps_roster.json` is
      built for the 54th, so this needs a second roster before any name
      resolution will work.

### B3. Free labels *(no annotation needed)*

- [ ] 🤖 **Authenticity — hold out the vote.** Extract a stance from what a party
      said, check it against how it voted. Thousands of labels from
      `divisions.jsonl`. **Always report against the ~97% party-line baseline** —
      an accuracy number without it is meaningless.
- [ ] 🤖 **Named dissenters** (Ferris 1,448, Kapa-Kingi 1,346, Tana 163
      divisions) are a ready-made positive set for position-vs-vote divergence,
      with matched controls from the same debates.
- [ ] 🤖 Coalition-agreement items with published quarterly status → promise
      resolution ground truth.

### B4. Wiring

- [ ] 🤖 Wire `evasion.jsonl` / `integrity.jsonl` into `evaluate.py` — built,
      never connected.
- [ ] 🤖 **Correlation and quote audits as pipeline gates**, not manual runs.
      Add to `tests/`, fail on regression.
- [ ] 🤖 **Golden-window regression test** — a fixed Hansard window with
      committed expected output, so a prompt edit shows its blast radius.
- [ ] 🤖 Re-run the Opus-vs-Haiku comparison on the grown testsets. The existing
      result was n=14 through the weaker CLI harness.

### B5. Bias checks — mandatory

- [ ] 🤖 Party means before/after the `subject` filter, government vs opposition.
- [ ] 🤖 Per-source means per attribute.
- [ ] 🤖 `insufficient_evidence` distribution by party — if it tracks opposition
      status, the "no evidence" rule is doing hidden harm.
- [ ] 🤖 Directional check on vote-derived Authenticity (opposition MPs vote
      against government bills by role, not by hypocrisy).
- [ ] 🤖 **Speaking-volume confound.** Score correlates −0.25 with how much an MP
      talks. Establish how much is the shrinkage estimator and how much is real.

## Phase C — pilot *(spends quota)*

- [ ] 🤖 **Pre-register the decision rule** before touching a prompt. Draft:
      *"test-set Pearson r improves ≥0.05 on ≥5 of 9 attributes, no attribute
      regresses >0.03, and max pairwise correlation falls below 0.65."*
- [ ] 🤖 **Pilot on 2025-10** — 62 distinct speakers, 146 divisions, 9 sitting
      days, median month by size. **51 windows** (measured, not estimated).
      Excluded from the testset pool already, so it cannot grade itself.
      ```bash
      cd attribute-extraction && python overnight_run.py run --hours 4 --stage pilot
      ```
      Ends by writing `ATTRIBUTE_OVERLAP_v3.md` and `QUOTE_AUDIT_v3.md`. Read
      both before going further.
- [ ] 🤖 Optional second pilot on **2024-11** (Treaty Principles first reading) —
      high-heat debate is where civility and subject-attribution are hardest.
- [ ] 🤖 Evaluate on `dev` only. Iterate. Record cost per variant alongside
      accuracy.
- [ ] 🤖 **Touch `test` once**, at the end. Apply the pre-registered rule.

## Phase D0 — before publishing *(the site currently describes v2.0)*

The live site is honest about the v2.0 data it is serving. It stops being honest
the moment v3.0 scores are published, so these must ship together:

- [ ] 🤖 `site/templates/about.html` — the "nine attributes" section still lists
      **Charisma**, still describes Veracity/Divination as ungrounded
      plausibility, and still carries the Strength/Authenticity
      subject-attribution defect as a live warning. All three change with v3.0.
- [ ] 🤖 The blog post
      (`../act65.github.io/_posts/inbetween-posts/2026-08-01-scorecards.md`)
      quotes v2.0 civility numbers against a pass mark of 100. **The re-anchored
      scale makes every one of them incomparable** — "civility averages 54",
      "one in ten at 20 or below", the 79 ceiling, the top/bottom cards.
- [ ] 🤖 Card display: evidence tier per attribute; "unverified" until the
      resolver runs; denominators for rate-based scores.
- [ ] 🤖 Fix the missing-attribute free pass before changing the attribute count
      — cards rank on the geometric mean of whatever subset was scored, so
      8-attribute cards median 45th against 71st for 9-attribute ones.
- [ ] 🤖 **Forthrightness is scoring opposition MPs on their own questions.**
      Found 2026-09-24 when the new `/party` page showed a 62-vs-19 government /
      opposition split that no definition of the attribute predicts. 43 of the
      74 scored MPs rest on ≤10 Q/A pairs and average **24**; the 31 with real
      volume average **67**, and the thin ones are almost entirely opposition
      MPs. Reading the rows, the "answer" attributed to them is their own next
      supplementary question — `asked_by` and `politician_id` are the same
      person — and the extractor says so in its own explanations ("the
      attributed 'answer' is not an answer at all — it is a further question").
      So the pairing in `parse_questions.py` / `extract_questions.py` drops the
      minister's reply and pairs question with question. **Nothing downstream
      can fix this**: the fix is in the pairing, then a re-score of the affected
      pairs. Until then a Forthrightness party mean is an artefact, and 36 of
      the 74 MP-level scores are measuring the wrong person's words. `min_n` in
      `build_v2_dataset.py` is the stopgap, not the repair.

## Phase D — re-extract and rebuild

- [ ] 🤖 Full extraction, resumable. ~1,200–1,300 windows.
      **Note this is justified even if the prompts do not improve** — the v2.0
      output was extracted from a corpus missing 37% of Hansard.
- [ ] 🤖 Split output into four tables: `examples` / `positions` / `promises` /
      `qa_pairs`.
- [ ] 🤖 Proposition vocabulary from the 253 bills and motion texts. No LLM.
- [ ] 🤖 Join, shrink with `bias_adjust.py`, rebuild the site dataset.
- [ ] 🤖 **Card changes:** evidence tier per attribute; the party-level
      Authenticity caveat; denominators shown for rate-based scores; fix the
      missing-attribute free pass (cards with 8 attributes median 45th, with 9
      median 71st).
- [ ] 🤖 **Resolve a designed sample of Veracity/Divination claims.**
      Nightly resolution was pulled on 2026-09-08: it drained ~58 claims a
      night against ~425 created, so the backlog grew ~7x faster than it
      cleared (~25,000 claims over the full term, ~430 nights) for 22% of each
      night's budget. It also sampled by extraction order — 371 of 389
      resolved claims came from one month of seven.
      Do it once the claim pool is COMPLETE, so the sample can be stratified
      (per MP, and across sitting months) and is therefore unbiased. Open
      questions: sample size per MP for a usable CI; whether `not_yet_due` /
      `uncheckable` (20% of returns, no score by design) should be drawn
      against the quota or replaced; whether Divination needs its own rate
      given how few claims it yields. `resolve.py` is unchanged and the 389
      resolved rows are kept.

---

## Cleanup and organisation

Both top-level directories have accumulated one-off scripts. Nothing here
changes behaviour; it is about being able to find things.

- [ ] 🤖 **Consolidate the five extraction runners.** `extract_hansard.py`,
      `extract_pressers.py`, `extract_releases.py`, `extract_all.py` and
      `overnight_run.py` are variations on one loop. One runner, `--source`.
- [x] 🤖 **Archive superseded build scripts** — DONE 2026-09-26. Moved to
      `attribute-extraction/archive/` with a README saying what superseded each:
      `build_site_data.py`, `clean_site_ids.py`, `resume_extraction.py`,
      `benchmark_diarization.py`, plus three more found by the same scan —
      `publish_v2_dataset.py`, `start_at.py` (pre-systemd scheduler) and
      `usage_report.py` (read the old usage-log format).
- [ ] 🤖 **Generated reports into `reports/`** — `STATS_3-month.md`,
      `STATS_full-term.md`, `eval_report.json`, `eval_compare.json`,
      `bench_diar.json`, `ATTRIBUTE_OVERLAP.md`, `QUOTE_AUDIT.md`.
      Keep them: they are the only backing for numbers quoted in the docs.
- [ ] 🤖 **Group the remaining modules** into `pipeline/`, `eval/`, `publish/`.
      ⚠️ Trade-off: these run as scripts from their own directory and import
      each other by bare name, so a move needs either `__init__.py` plus
      relative imports, or the `conftest.py` path shim already used in `tests/`.
      The clean answer is a `pyproject.toml` and a real package — a bigger
      change than the rest of this list, so it should be its own decision.
- [x] 🤖 **`site_data_full/` (40M) and `site_data_v2/`** — DONE 2026-09-26.
      `git rm --cached` + gitignored. As noted, `.git` is unchanged (still 453M,
      most of it 28 revisions of a 62M `hansard_scores_v3.jsonl` — see the new
      item below).
- [x] 🤖 **`HANSARD_EXTRACTION_PLAN.md`** — DONE 2026-09-26. Moved to
      `attribute-extraction/archive/` rather than folded into `V3_PLAN.md`:
      merging a finished migration's detail into the live plan makes the live
      plan harder to read, and the file is worth keeping intact as a record.
- [ ] 🤖 **Stop committing `hansard_scores_v3.jsonl` (62M).** 28 revisions of it
      are most of the 453M `.git`, and it is a build input, not source. Either
      gitignore it and publish releases to a dataset host (`publish_corpus.py`
      already has the shape), or git-lfs it. Not committing the 29th is free;
      rewriting history to purge the existing blobs is a separate, disruptive
      decision.
- [ ] 🤖 **Retired v2.0 score files are still tracked** — `hansard_scores_full.jsonl`
      (27M), `release_scores.jsonl` (9.3M), `presser_scores.jsonl` (2.2M),
      `hansard_scores_3mo.jsonl` (2.9M). Not simply deletable: they are the
      **defaults** of `build_v2_dataset.py --scores` and `attribute_overlap.py`
      DEFAULT_SCORES, so the defaults have to move to v3 first.
- [ ] 🧑 **`data/.venv-portraits` is 1.4G.** Gitignored and recreatable, but a
      ~2GB re-download. Your call; I have not touched it.

---

## Decisions taken 2026-08-07

All four open questions are settled. Full rationale in `ATTRIBUTES.md`.

| # | Decision | Consequence |
|---|---|---|
| 1 | **Charisma is cut. Focus replaces it** — is the statement about the policy, or about the other team? | New prompt, new rubric. Two correlations to watch: Focus/Specificity and Focus/Civility. |
| 2 | **53rd Parliament deferred** until after the pilot. | Label the 54th pool now; nothing blocks on a 12–18h scrape. |
| 3 | **Civility re-anchored** — 1.0 is the expected standard, 0.5 a genuine failure. | Forces re-extraction (already committed). **v2.0 civility scores become incomparable** — including in the blog post. |
| 4 | **Veracity and Divination grounded by one search-backed resolver**, both from the start. | Largest new build in v3.0. Abstain rule must run first or the cost balloons. |

**One premise corrected.** The 53rd was proposed because publishing the 54th's
Hansard would rule it out for evaluation. It does not: Hansard is already public
and already in every frontier model's training data, so our scrape adds no
contamination. What leaks is **gold labels, not statements** — so publish the
corpus and hold back the labelled test split. The 53rd is still worth having,
but for the political-bias check and long-horizon outcomes, not for this.

---

## Phase A2 — Focus, the replacement attribute — **mostly done**

- [x] 🤖 `prompts/focus.txt` written to the spec in `ATTRIBUTES.md` §6.
- [x] 🤖 **Scrutiny rule encoded as a worked example.** "The government promised
      1,000 homes and built 200" → **1.0**, with a `DO NOT PENALISE OPPOSITION`
      block, because getting this wrong re-creates the subject-attribution bias
      in a new place. Enforced by `tests/test_registry_consistency.py`.
- [x] 🤖 Charisma removed from the prompts, the registry, the icon map and the
      site's game rules. Kept in `attributes.RETIRED` so v2.0 data still reads.
- [x] 🤖 **Site game rules updated.** Focus drives a new **Concentration**
      mechanic — press the same target on consecutive turns for escalating
      damage, capped at Focus ÷ 2, reset on switching. Ties to the fantasy sense
      of focus and to what the attribute measures: staying on the policy
      compounds, lashing out at whoever is nearest builds nothing. Also fixed a
      latent bug — the riposte rule was keyed to a non-existent attribute called
      "Precision" and so never rendered; it is Forthrightness.
- [ ] 🤖 **Measure both risks on the pilot before shipping.** Focus/Specificity
      and Focus/Civility must land below 0.65, and the government-vs-opposition
      gap must not exceed the other text-only attributes. If either fails,
      narrow Focus to *what the statement is about* rather than *how precise it
      is*.
- [ ] 🤖 v4: port Concentration into `game_logic.py`. Deliberately deferred —
      `game/rules.md` carries a note.

## Phase A4 — two experiments *(small, run 2026-08-07)*

### Can a cheaper model do it? — `compare_models.py`

**Opus 5 is treated as ground truth**; Sonnet 5 and Opus 4.8 are scored on how
faithfully they reproduce it. If a cheap model correlates highly *and* quotes
properly, there is no reason to pay for the expensive one over 1,127 windows.

Read the **statement-overlap** column first: it caps everything else. A model
that agrees perfectly on the 30% of statements it also chose to surface is still
producing a different dataset.

Rough bar for switching: overlap ≥ 0.6, `r` ≥ 0.85, mean gap ≤ 0.10, quote-gate
rejects no worse than the reference.

### Is searching worth it? — `resolve.py`

Extraction now records `prior_score`, the model's **unaided guess** for veracity
and divination, written *after* the falsification criterion and never published.
The resolver then searches for evidence — and **never sees the guess**, so the
two are independent. `resolve.py compare` reports how far apart they land.

- A high `r` with a small gap → the guess already tracks the evidence and search
  is an expensive confirmation.
- A low `r`, or a few large flips → the guess is confidently wrong somewhere,
  which is exactly what the site cannot afford, and justifies the cost.
- The share returning `uncheckable` / `not_yet_due` is the share where searching
  bought nothing at all.

```bash
python compare_models.py run --windows 4 --repeats 2 --backend claude_cli
python resolve.py run --scores model_comparison.json --limit 24
python resolve.py compare --out GUESS_VS_SEARCH.md
```

## Phase A3 — the resolver *(spends quota; build after Phase A)*

One component, two callers. Spec in `ATTRIBUTES.md` §The resolver.

- [ ] 🤖 **Extraction emits a falsification criterion**, before any search:
      Veracity `{claim, falsification_criterion, quote, subject}`; Divination
      adds `resolve_by`. No criterion statable → emit nothing.
- [ ] 🤖 **Resolver**: neutral query from the *subject* of the claim, not its
      direction. Never sees the original LLM score. Stores every source URL.
- [ ] 🤖 `uncheckable` / `not_yet_due` are first-class verdicts, **never a low
      score**. Absence of evidence is not evidence of falsity.
- [ ] 🤖 **Bias probe as a test**: negate a held-out sample of claims and re-run.
      A resolver that confirms both a claim and its negation is measuring
      agreeableness. This must fail the build, not sit in a doc.
- [ ] 🤖 **Run the abstain rule first.** It shrinks the input from 18,725
      veracity examples and 3,151 predictions to whatever is genuinely
      checkable. Searching first and filtering after is the expensive ordering.
- [ ] 🤖 Resumable and incremental — this is the largest quota line in v3.0.
- [ ] 🤖 Surface sources on the card. A resolved score that cannot show its
      working is worse than no score.
