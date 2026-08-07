# v3.0 — evidence-grounded extraction

**Goal:** re-extract the whole corpus with a pipeline where Strength and
Authenticity are *derived from the legislative record* rather than guessed from
text, every scored statement records **whose conduct it describes**, and the
result is measured against held-out data rather than asserted.

v2.0 was "all current MPs, Hansard only, nine LLM-scored attributes". v3.0 keeps
Hansard as the single conduct corpus and changes four things: some attributes
stop being LLM guesses and are computed against an external record, every scored
statement records whose conduct it describes, **the attributes are redefined so
they stop measuring each other**, and evaluation becomes a first-class
deliverable rather than a 14-row afterthought.

**Read alongside:**

| Document | Answers |
|---|---|
| `ATTRIBUTES.md` | What each attribute means, what it explicitly does *not* cover, and the eligibility gate for scoring at all. |
| `V3_TODO.md` | The ordered backlog, who owns each item, and the open questions. |
| `attribute-extraction/ATTRIBUTE_OVERLAP.md` | How much the nine currently overlap. Generated. |
| `attribute-extraction/QUOTE_AUDIT.md` | Whether the quotes behind the scores are real. Generated. |
| `data/VOTES.md` | The votes/bills evidence base and its caveats. |

Prerequisites already built (see `data/VOTES.md`): `divisions.jsonl` (4,122 party
votes), `bills.jsonl` / `proposed_bills.jsonl` / `amendment_papers.jsonl`,
`strength_ledger.jsonl` (135 MPs), `manifestos.jsonl`, `oral_questions.jsonl`
(11,082), `written_questions.jsonl` (180,939), `propositions.jsonl` (212).

---

## 1. Sources — one scoring corpus, several evidence tables

**Decided: Hansard is the only conduct-scoring corpus.** Everything else enters
as *evidence a score is checked against*, never as text we score conduct from.

That distinction dissolves the source-mix confound rather than managing it.
Scoring civility across Hansard and press releases would compare venues as much
as people; using a vote record to check whether a Hansard statement matched the
speaker's actions is a different operation entirely, and carries no venue bias.

### Evidence tiers

Which attributes can be judged from the words alone, and which need an external
record. This has always been implicit in `README.md`'s trust table — v3.0 makes
it structural, and puts it on the card.

| Tier | Attributes | Scored from | Evidence source |
|---|---|---|---|
| **Text-only** | Civility, Rigor, Specificity, **Focus** | the statement itself | none needed — the words *are* the evidence |
| **Grounded — record** | Strength | legislative record | `strength_ledger.jsonl`, `bills.jsonl` |
| | Authenticity | stated position vs action | `divisions.jsonl`, `manifestos.jsonl`, party releases |
| | Forthrightness | question/answer pairs | Hansard oral questions; written PQs |
| **Grounded — search** | Veracity, Divination | resolved against sources | the resolver (`ATTRIBUTES.md`) |

**Charisma is cut** — r=0.96 with Civility. **Focus** takes its slot.

**Veracity and Divination move into the grounded tier via one shared resolver.**
Both ask the same shape of question — *is there evidence in the world that
settles this?* — so one search-backed component serves both: Veracity asks "is
it true", Divination asks "did it happen". The defence against confirmation bias
is that extraction states the **falsification criterion before any search
runs**, so the resolver cannot tune the target to what it finds. Until it ships
they remain ungrounded and the card must say so.

### Forthrightness needs *pairs*, not statements

Worth calling out because it is a structural change, not a prompt change.
Evasion is a **relation between a question and an answer** — you cannot detect
it in an isolated sentence, which is what the current pipeline scores. The good
news is that oral question time is *in Hansard*, with an explicit Q/A structure
we can extract as pairs. Written parliamentary questions are a separate feed
with the same shape and an even cleaner signal (asked / answered / refused), and
are the one auxiliary source still to be scraped.

### Auxiliary sources and what each is for

| Source | Records | Role in v3.0 |
|---|---:|---|
| `hansard_v2.json` | 2,618 | **the conduct corpus** + oral Q/A pairs |
| `divisions.jsonl` | 3,890 | Authenticity: did the vote match the words |
| `strength_ledger.jsonl` | 135 | Strength: delivery, initiative, engagement |
| `manifestos.jsonl` | 14 | Authenticity: campaign + coalition promises |
| party releases | 2,976 | Authenticity: public positions between elections |
| written PQs | *to scrape* | Forthrightness: asked vs answered |
| coalition quarterly action plans | *to scrape* | promise resolution |
| newsroom / spinoff | 3,704 | later: Veracity verification corpus |
| `rnz.json` | 982 | excluded — only covers 2026-03 onward |

### The bias this introduces, and the fix

Using party releases as the "what they said publicly" side creates a subtle
trap: **more speech means more chances to be caught contradicting yourself.** A
prolific party would score lower on Authenticity purely for publishing more.

Authenticity must therefore be a **rate, not a count** — contradictions per
position extracted — with the denominator stored and displayed. The same applies
to Forthrightness: evasions per question answered, not evasions.

## 1b. The attributes are not nine independent readings

**Added 2026-08-07, after measuring it.** The single biggest defect in the
instrument is not any one prompt — it is that the nine attributes overlap so
heavily that a card is not nine readings of conduct. Full detail in
`ATTRIBUTES.md`; the summary:

| pair | Pearson r |
|---|---:|
| Charisma / Civility | **0.96** |
| Civility / Rigor | **0.85** |
| Charisma / Rigor | 0.83 |
| Veracity / Rigor | **0.83** |
| Forthrightness / Rigor | 0.73 |

**Rigor is the hub** — above 0.65 with six of the other eight — because its
prompt grew into a general "is this a good argument" score. Card rank is a
geometric mean over all nine, so one ad hominem currently costs an MP on
Civility, Rigor *and* Charisma: a single act moves a third of the card.

### The three prompt-design principles for v3.0

**(a) One attribute owns one failure mode.** Where two prompts penalise the same
move, exactly one is wrong. The ownership ledger in `ATTRIBUTES.md` settles each
case; the load-bearing ones are strawman (Civility→**Rigor**), hyperbole
(Civility→**Veracity**), and ad hominem (stays **Civility**; counts against Rigor
only where the conclusion rests on it).

**(b) Rigor is validity, not truth.** *Do the conclusions follow from the
assumptions?* We are not fact-checking — the accuracy of the assumptions is
Veracity's job. An argument can be perfectly rigorous and built on false
premises: high Rigor, low Veracity. This must appear in the prompt as a worked
example, because it is the largest single source of the current overlap.

The corollary is that **Veracity must abstain rather than guess.** Its prompt
currently asks how well-evidenced a claim *looks* and says to "prefer ~0.5" when
it cannot verify — which is a reasoning judgement wearing a fact-check label. In
v3.0 an unverifiable claim produces no example at all.

**(c) Score only where there was a real opportunity to score 0–100.** If a
statement could not have been much better or much worse on an attribute, scoring
it adds noise. Every prompt gets an explicit eligibility gate, and the model is
told that **returning nothing is an expected outcome** — the current phrasing
("find instances of…") pushes the other way, and it obliges: 84% of statements
carry two or more attributes and Specificity fires on 51% of the corpus.

Two eligibility cases matter most: **ceremonial speech is ineligible for
Civility** (tributes are trivially civil and inflate the top of the scale for
whoever is senior enough to give them), and **statements advancing no argument
are ineligible for Rigor**.

### Quotes must be real

Sampling 800 scored statements against their source day
(`QUOTE_AUDIT.md`): 85% verbatim, **6% not present in the transcript at all**,
9% ellipsis-spliced from non-contiguous fragments, and 25% cut mid-sentence.

The site's promise is that any number can be clicked back to its evidence, so
this is a correctness bug, not a polish item. v3.0 makes it a hard gate in
`extract.py`: verbatim only, no splicing, whole sentences. The
`divination.txt` licence to "resolve pronouns/ambiguity for clarity" is removed.

## 2. The new extraction contract

Today one call emits `{politician, statement, score, explanation}` per attribute.
v3.0 splits the output into four tables, because they are different kinds of
claim with different provenance and different units.

### (a) `examples.jsonl` — statement-level scores

The four text-only attributes: Civility, Rigor, Specificity and **Focus**.
Veracity and Divination no longer land here — extraction emits *candidates* with
a falsification criterion and the resolver scores them (§1b, `ATTRIBUTES.md`).

Scored as now, plus one required new field:

```
subject: "speaker" | "other" | "unclear"      (+ subject_name when "other")
```

Only `subject: "speaker"` rows count toward a card. This is the real fix for the
open defect in `attribute-extraction/EVALUATION.md`, and it applies to **every**
attribute — not just the two where we happened to notice it.

### (b) `positions.jsonl` — Authenticity

The LLM no longer scores Authenticity. It extracts a position:

```
{subject, proposition_id | null, stance: support|oppose|mixed, date, quote, confidence}
```

Authenticity is then computed by joining to `divisions.jsonl`: did the party vote
match the stated stance? Requires the **proposition vocabulary** (below).

### (c) `promises.jsonl` — Strength / the claims ledger

```
{subject, promise, deadline | null, measurable: bool, date, quote}
```

Strength comes from `strength_ledger.jsonl` (bills in charge, ballot bills,
amendment papers) plus resolved promises. `prompts/strength.txt` stops being a
scoring prompt and becomes an extraction prompt. `prompts/promises.txt` already
exists — start there.

### (d) `qa_pairs.jsonl` — Forthrightness

```
{question_id, asker, responder, question, answer, date, answered: bool,
 evasion_type | null, quote}
```

Extracted from Hansard oral question time as **pairs**, because evasion is a
relation between a question and an answer and cannot be seen in either alone.
Written PQs feed the same table once scraped. Score is a rate — evasions per
question faced — never a raw count.

### Supporting work

- **Proposition vocabulary** — seed from the 253 bills and motion texts in
  `divisions.jsonl`; both sides normalise to the same ids so the join is a
  lookup, not fuzzy text matching. Embeddings capture topic, not stance, so they
  are a retriever at most, never the scorer.
- **Prompt fixes** (cheap, needed regardless): delete `strength.txt`'s "year
  after year they promised" few-shot — it teaches the bug; change
  `authenticity.txt`'s "signal about that opponent" note to "skip it"; add
  "only score when the subject is the speaker, their own party, or their own
  government" to all prompts.
- **Delivery-scope gate** — Strength is `not applicable`, not zero, for MPs with
  no lever. `insufficient_evidence` is already implemented in the ledger.

---

## 3. Evaluation — the main deliverable

The current state is two testsets of **n=14** with known prompt leakage. That
cannot validate anything. This section should carry the bulk of the effort.

### 3.1 Testsets

- [x] **The existing testsets are entirely synthetic** — "Senator Armstrong",
      "Governor Miller", "Mayor Garcia". No New Zealander, no Hansard. The
      headline `civility r=0.88` was measured on invented American-register
      statements and is not evidence about this task. Documented in
      `EVALUATION.md`; every published accuracy figure is now marked unvalidated.
- [x] `build_testsets.py` samples REAL statements from the corpus (228,688
      labellable passages), stratified by government/opposition and month,
      emitted **unlabelled**. First pool of 120 drawn: 66 speakers, 28 months,
      64 government / 56 opposition.
- [x] **Deterministic dev/test split** by content hash — cannot drift as rows
      are added, cannot be re-rolled to flatter a prompt.
- [x] **Prompt-leakage check enforced** in `test_testsets.py`, not merely
      documented. Currently clean.
- [ ] **Label the 120-item pool by hand** (the blocking manual step), then
      extend toward n ≥ 100 *per attribute*.
- [ ] **Subject-attribution testset** — statements labelled speaker/other/unclear.
      This is the fix we most need to verify, and it has no testset at all. The
      sampler already emits the fields; only the labels are missing.
- [ ] **Double-label a calibration subset** (~50 items, two annotators) and
      report inter-annotator agreement. Without it we cannot tell whether a
      model/human gap is model error or rubric ambiguity — and an `r` of 0.88
      means little if two humans only agree at 0.7.
- [ ] Wire the existing binary detection sets (`evasion.jsonl`,
      `integrity.jsonl`) into `evaluate.py` — built but never connected.

### 3.1b Instrument checks — run on every prompt change

Accuracy against gold labels is not the only thing that can be wrong. Two
deterministic audits now run without any labels at all, and a prompt rewrite is
held to both:

```bash
cd attribute-extraction
python attribute_overlap.py run --out ATTRIBUTE_OVERLAP.md
python check_quotes.py run --n 2000 --out QUOTE_AUDIT.md
```

- [ ] **Attribute correlation** — pairwise Pearson r on co-scored statements,
      plus selection overlap (Jaccard) and firing rate. These are different
      failures: two attributes picking the same statement is fine, grading it
      identically is not.
- [ ] **Quote fidelity** — verbatim / spliced / not-found / mid-sentence.
- [ ] Both wired into `tests/` as regression gates, so a prompt edit that
      re-merges two attributes fails rather than ships.

Pre-registered targets are in `ATTRIBUTES.md` — headline: max pairwise r below
0.65, Veracity/Rigor below 0.55, multi-attribute statements below 60%, quotes
not-found at zero.

**A prompt rewrite that improves accuracy but leaves the correlations where they
are has not fixed the instrument.**

### 3.1c The 53rd Parliament (2020-11-25 → 2023-08-31)

A completed Parliament buys three things the current corpus cannot:

- **The only possible grounding for Divination.** Predictions made 2020–2023
  have known outcomes now. There is no other route.
- **Strength ground truth** — the 2020 manifesto ran a full term, so promise
  resolution is observable rather than in-progress.
- **A political-bias check that needs no human labels.** If the rubric is
  neutral, a Labour-majority Parliament should score about where a National-led
  coalition does. A large gap is evidence of bias *in the instrument*, not a
  finding about either party. This is the strongest free check available.

Mechanically it is the existing Playwright path over a wider date range —
`hansard.py`'s `_enumerate_day_urls` walks weekdays and non-sitting days render
nothing. ~730 weekdays, ~250 sitting, **12–18h wall clock**, resumable.

⚠️ It needs a **second roster**: `mps_roster.json` is built for the 54th, so no
name resolution will work on the 53rd until that exists.

**Not a replacement for labelling the 54th.** We score the 54th, so the
text-only attributes must be evaluated on it — a different Parliament, Speaker
and standing-orders era is a real distribution shift. The 53rd is for
outcome-resolved ground truth and the bias check.

### 3.2 Free labels: self-supervised evaluation

The strongest evaluation available, and it needs no annotation.

- [ ] **Authenticity — hold out the vote.** Extract a party's stance from what
      it said, then check it against how it actually voted. Thousands of labels
      from `divisions.jsonl` for free.
      **Always report against the party-line baseline (~97%).** An accuracy
      number without that beside it is meaningless.
- [ ] **Strength — coalition agreement items** with published quarterly status
      are labelled ground truth for promise resolution.
- [ ] **Named dissenters** (Ferris 1,448, Kapa-Kingi 1,346, Tana 163 divisions)
      are a ready-made positive set for position-vs-vote divergence, with matched
      controls from the same debates.

### 3.3 Bias checks — mandatory, not optional

Re-run the analysis that found the subject-attribution defect, on the new output:

- [ ] Party means before/after the `subject` filter, government vs opposition.
- [ ] Per-source means per attribute (the confound in §1).
- [ ] Distribution of `insufficient_evidence` by party — if it correlates with
      opposition status, the "no evidence" rule is doing hidden harm.
- [ ] A directional-bias check on the vote-derived Authenticity: opposition MPs
      vote against most government bills because that is their job. Confirm we
      have not swapped one directional bias for its mirror image.

### 3.4 Prompt redesign — and the protocol that keeps it honest

We intend to rewrite the prompts for all nine attributes and re-extract if the
evals improve. That is the right instinct, and it is also the single easiest way
to produce numbers that are silently wrong.

**Iterating prompts against the testset and then reporting testset scores is
model selection on the test set.** After a dozen prompt variants the reported
`r` measures how well we fitted 100 examples, not how well the pipeline works.

Protocol, fixed before any prompt is touched:

- [ ] **Three-way split per attribute**: `dev` (iterate freely), `test` (touched
      once, at the end), and the free self-supervised labels (§3.2) as a third,
      independent signal. Store the split in the repo so it cannot drift.
- [ ] **Pre-register the decision rule.** Write down, before running, what
      counts as an improvement worth a full re-extraction — e.g. "test-set
      Pearson `r` improves by ≥0.05 on ≥5 of 9 attributes with no attribute
      regressing by more than 0.03". Otherwise the threshold moves to fit the
      result.
- [ ] **The pilot window must not overlap the testsets.** Draw testset items
      from months outside the pilot month, or the pilot evaluates itself.
- [ ] Record cost per variant alongside accuracy. A prompt that gains 0.02 `r`
      for 40% more tokens is not obviously a win on a quota-limited budget.

**Two independent reasons to re-extract — do not conflate them.** Better prompts
are one. The other is that the current 94k examples were extracted from a corpus
missing **37% of Hansard**, concentrated at the end of every long sitting day
(`data/VOTES.md`). That second reason holds *even if the new prompts show no
improvement at all*, and it is the stronger of the two.

### 3.5 Pipeline tests

- [ ] Offline tests for the new schema: `subject` required, positions/promises
      round-trip, ledger join correctness.
- [ ] A **golden-window regression test**: a fixed Hansard window with a
      committed expected output, so prompt edits show their blast radius.
- [ ] Model comparison re-run on the grown testsets — the existing Opus-vs-Haiku
      result was measured at n=14 through the weaker CLI harness.

---

## 4. The pilot, cost and sequencing

### Pick the pilot month deliberately

One month of Hansard is ~39 windows against the ~1,235 for the full term, so the
pilot is cheap. But months are not interchangeable, and the obvious choice is a
trap:

| Month | Divisions | Sitting days | Distinct speakers | Chars |
|---|---:|---:|---:|---:|
| 2026-05 | **791** | 9 | **42** | 4.6M |
| 2025-11 | 519 | 7 | 61 | 4.4M |
| **2025-10** | 146 | 9 | **62** | 2.9M |
| 2024-11 | 162 | 9 | 60 | 2.9M |
| 2024-03 | 108 | 8 | 61 | 3.1M |

2026-05 looks richest on divisions and is the worst choice: 791 of them come
from one committee-stage filibuster, and only 42 members spoke all month.

**Recommend 2025-10** — highest speaker diversity (62), a healthy 146 divisions,
9 sitting days, and almost exactly the median month by size (2.9M vs 2.9M), so
throughput measured on it extrapolates honestly.

If we can afford two, add **2024-11** as a contentious stress case (Treaty
Principles Bill first reading) to check the pipeline does not degrade on
high-heat debate — that is precisely where civility and subject-attribution are
hardest.

### Cost

`hansard_v2.json` is 74.9M chars, **1.66× the old corpus** (45.0M). The last full
run produced 744 windows, so budget roughly **1,200–1,300 windows** for the full
term, ~39 for a one-month pilot. Extraction runs on the user's usage-limited
subscription, so latency and rate limits — not dollars — are the constraint.

### Order

1. Prompt fixes + `subject` field + the four-table schema. Cheap, testable
   without a re-run.
2. Proposition vocabulary from the 253 bills and motion texts. No LLM.
3. Hansard oral-question **Q/A pair extraction** (structural, no LLM to segment).
4. Testsets: grow, three-way split, leakage check in CI, annotator agreement.
5. **Pilot on 2025-10.** Evaluate on `dev`, iterate prompts, run the bias checks.
6. Touch `test` **once**; apply the pre-registered rule to decide on full
   re-extraction.
7. Full extraction, resumable as v2.0 was.
8. Promise/position ledgers from manifestos, coalition agreements and party
   releases — separate path, no conduct scoring.
9. Join, aggregate with `bias_adjust.py` shrinkage, rebuild the site dataset.

## 5. Decisions

**Settled:**

1. ~~Source mix~~ → **Hansard only** for conduct scoring; everything else is an
   evidence table (§1).
2. ~~Re-extract all nine attributes or only the changed ones?~~ → **all nine**,
   because the 37%-missing-Hansard sampling bias applies to every attribute
   regardless of prompt quality (§3.4).
3. Pilot before committing to the full run → **yes, 2025-10** (§4).

**Also settled (2026-08-01):**

4. **Party-level Authenticity does appear on the individual MP card.** It
   measures how what this politician says aligns with how their party votes,
   which is genuinely informative. It must carry the caveat that an MP may
   personally disagree with a party vote they were counted in, so it is **not a
   true measure of that individual's authenticity**. Where an MP is recorded
   individually — conscience votes and named dissents — prefer that evidence.
5. **Veracity and Divination stay text-only LLM judgements for v3.0**, with an
   explicit note on the card and in the docs that they are ungrounded and need
   an evidence source (fact-check corpus; prediction→outcome resolution).
6. **Written parliamentary questions are in scope** — `scrapers/written_questions.py`
   built, feeding Forthrightness alongside Hansard oral Q/A.

**Also settled (2026-08-07)** — rationale in `ATTRIBUTES.md`:

7. **Charisma is cut; Focus replaces it.** At r=0.96 with Civility it was one
   insult counted twice. Focus asks *is this about the policy, or the other
   team?* — occupying the real gap Civility leaves, since attacking a **party**
   rather than a **person** passes Civility cleanly. Legitimate scrutiny of a
   named policy failure scores **high**, so opposition work is not penalised.
8. **Evaluate on the 54th; defer the 53rd until after the pilot.** The premise
   that publishing the corpus would disqualify it does not hold — Hansard is
   already public and already in every frontier model's training data. Hold back
   **gold labels**, not statements. The 53rd is still wanted, for the
   political-bias check and long-horizon outcomes (§3.1c).
9. **Civility is re-anchored**: 1.0 is the expected standard, 0.5 a genuine
   failure. Hard criticism of a *policy* now scores near 1.0. Forces
   re-extraction — already committed — and makes **every v2.0 civility number
   incomparable**, including those quoted in the blog post.
10. **Veracity and Divination are grounded by search**, via one shared resolver
    with pre-registered falsification criteria. They leave the ungrounded tier.
    This is the largest new build in v3.0; the abstain rule must run first or
    the cost balloons.

**Implemented 2026-08-07 — the pipeline is ready to run:**

- All nine prompts rewritten to `ATTRIBUTES.md`: one question each, eligibility
  gates, named disclaimers, worked boundary examples. `charisma.txt` deleted;
  `focus.txt` added; `true.txt` and `promises.txt` removed as superseded.
- `attributes.py` — the single source of truth for the attribute set, its three
  tiers and its card-facing definitions. Read by the extractor, the dataset
  builder and the icon map.
- `extract.py` — a hard quote gate (verbatim, no splices, whole sentences),
  optional scores so the search tier can emit pending rows, required-field
  checks, and run-level rejection statistics.
- `extract_questions.py` — Forthrightness over question/answer pairs, with
  written PQs de-duplicated to distinct (template, minister) pairs.
- `compare_models.py` — label-free model bake-off on contract compliance.
- `overnight_run.py` — three staged, resumable, time-bounded runs that finish by
  running the instrument audits, and deliberately do not publish.
- Site game rules: Focus drives a new **Concentration** mechanic.

Measured plan size: **51 windows** for the 2025-10 pilot, **1,127** for the full
term (183 sitting days), **924 calls** for oral Q/A. Written PQs are 7,097 calls
and are opt-in only.

**Built 2026-08-01:** the `subject` field and prompt fixes;
`corpus/oral_questions.jsonl` (11,082 Q/A pairs); `corpus/propositions.jsonl`
(212 propositions); `corpus/written_questions.jsonl` (180,939);
`build_testsets.py` with a deterministic dev/test split and an enforced
prompt-leakage check; `data/names.py` consolidating six copies of the name
logic; `attribute_overlap.py` and `check_quotes.py` with their generated
reports; `ATTRIBUTES.md` and `V3_TODO.md`. All deterministic — **no extraction
quota spent.** Remaining before the 2025-10 pilot: **hand-labelling the
120-item testset pool**, and answering Q7/Q8 above.

## 6. Known carry-overs

- Roster reconciliation (`TODOs`): `mps_roster.json` misses mid-term churn.
  Departed MPs still appear — which is why roughly half of the 14 "no Strength
  evidence" MPs (Rurawhe, Parker, Robertson, Davis, Ghahraman, Kemp) are people
  no longer in the House, not backbenchers with nothing to show.
- `attribute-extraction/roster.py` is a **seventh near-copy** of the name logic,
  missed when six were consolidated into `data/names.py`. It lacks the
  "Surname, Given" and "on behalf of" handling, and `build_v2_dataset.py` and
  `hansard_dataset_stats.py` both import it — so published scores may be split
  across spelling variants that `names.py` would have merged. Check the blast
  radius before deleting.
- 8 Hansard days never render; currently filled from the old corpus via
  `--fallback_corpus` and flagged `ayes_order_inferred`.
- **Cards get a free pass for missing attributes.** Rank is the geometric mean
  of whatever subset was scored, so an MP missing their weakest attribute ranks
  higher: 8-attribute cards median 45th, 9-attribute cards median 71st. Must be
  fixed at the same time as any decision to drop Divination from the mean.
- Thin manifesto captures: NZ First is JS-rendered (650 chars); Green's nearest
  2023 snapshot is July 2025 (`stale_snapshot`).
