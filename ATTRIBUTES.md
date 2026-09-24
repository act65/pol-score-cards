# The nine attributes — definitions and boundaries

**Status: v3.0 draft specification.** This is the contract every prompt, testset
and rubric must implement. Where it disagrees with a prompt in
`attribute-extraction/prompts/`, this document is right and the prompt is a bug.

## Why this document exists

The nine attributes were written one at a time, and each one grew to cover
whatever seemed like bad conduct. The result is that they overlap badly.
Measured on the v2.0 output (`attribute-extraction/ATTRIBUTE_OVERLAP.md`):

| pair | Pearson r |
|---|---:|
| Charisma / Civility | **0.96** |
| Civility / Rigor | **0.85** |
| Charisma / Rigor | 0.83 |
| Veracity / Rigor | **0.83** |
| Forthrightness / Rigor | 0.73 |
| Divination / Rigor | 0.72 |

Two things stand out. **Rigor is the hub** — it correlates above 0.65 with six
of the other eight, because its prompt has become a general "is this a good
argument" score. And **Veracity/Rigor at 0.83** means we are scoring truth and
validity as one quantity, which is precisely the conflation this document
exists to end.

This matters because card rank is a geometric mean over all nine. An attribute
that duplicates another does not add a reading — it re-weights one. One ad
hominem currently costs an MP on Civility, Rigor *and* Charisma, so a single act
moves a third of the card.

## The organising rule

**One attribute owns one failure mode.** If two attributes would both penalise
the same move, exactly one of them is wrong, and this document says which.

Every prompt must therefore carry, explicitly:

1. **The one question** it asks — and nothing else.
2. **An eligibility gate** — the precondition for scoring at all.
3. **Disclaimers** — the neighbouring failures it must ignore, named.

### The eligibility gate

A statement is eligible for an attribute only if **the speaker had a real
opportunity to score anywhere from 0 to 100 on it.** If a statement could not
have been much worse or much better on this attribute, scoring it adds noise,
not signal.

Ineligible, for every attribute:

- procedural speech — "I move that the question be now put", "Point of order"
- the Speaker's rulings and the Clerk's readings
- interjections too short to carry a claim
- reading a document into the record

Ineligible, per attribute — the important cases:

- **Civility**: ceremonial speech. Tributes, condolences and valedictories are
  trivially civil and no MP could have scored low on them. They currently
  inflate the top of the civility scale for whoever gives more of them, which
  is a function of seniority, not conduct.
- **Rigor**: statements advancing no argument. A factual announcement with no
  inference has no reasoning to assess.
- **Veracity**: opinions, predictions, value statements. Also — and this is new
  — **any claim the scorer cannot actually check**. See below.
- **Forthrightness**: anything that is not a response to a clear question.
- **Specificity**: statements whose job is not to convey content (thanks,
  procedural courtesies).

**Emitting nothing is a correct and expected outcome.** The prompts currently
imply the opposite by asking the model to "find instances", and it obliges: 84%
of scored statements carry two or more attributes, and Specificity fires on 51%
of everything. An attribute that fires on half the corpus is not distinguishing
anything.

---

## The ownership ledger

The moves that more than one attribute currently penalises, and who keeps each.

| Move | Currently penalised by | **Owner** | Reasoning |
|---|---|---|---|
| Ad hominem, insult, contempt | Civility, Rigor, Charisma | **Civility** | Attacking a person is a conduct failure. It is *also* a Rigor failure **only when the conclusion rests on it** — "the policy fails because the member is a fool" is illogical; "the member is a fool, and the policy fails because [valid argument]" is merely rude. |
| Strawman, misrepresenting a position | Civility, Rigor | **Rigor** | The target is the argument, not the person. Refuting a claim nobody made is an inference failure. Remove from Civility. |
| Hyperbole, exaggeration | Civility, Veracity | **Veracity** | An overstated claim is an inaccurate claim. Remove from Civility. |
| Appeals to emotion, popularity, tradition, authority | Rigor | **Rigor** | Uncontested. |
| Vagueness, platitude | Specificity, Forthrightness | **Specificity** | Forthrightness asks whether the question was *addressed*, not how precisely. A blunt, vague "no" is fully forthright and highly unspecific. |
| Unevidenced assertion | Veracity, Rigor | **split** | If the *claim* is false → Veracity. If the *inference from it* does not follow → Rigor. This is the single most important split in the document. |
| Divisive us-vs-them framing | Charisma, Civility | **Focus** | Attacking a *party* rather than a *person* passes Civility but is pure tribalism. That gap is what Focus now occupies (Charisma is cut). |

---

## The nine

### Tier

| Tier | Attributes | Meaning |
|---|---|---|
| **Text-only** | Civility, Rigor, Specificity, Focus | The words are the evidence. Judgeable from the statement plus its context. |
| **Grounded — record** | Forthrightness, Strength, Authenticity | Computed against a record we hold. The LLM extracts; arithmetic scores. |
| **Grounded — search** | Veracity, Divination | Resolved against sources found at check time. New in v3.0; see *The resolver*. |

**Charisma is cut** (decided 2026-08-07). At r=0.96 with Civility it was not a
second reading of conduct, and it was the third penalty on a single ad hominem.
**Focus** replaces it, occupying the genuine gap Civility leaves: attacking a
*party* rather than a *person*.

**Veracity and Divination move out of the ungrounded tier** (decided
2026-08-07). Both are resolved by one search-backed component rather than
guessed from text. Until it ships they remain ungrounded and the card must say
so.

---

### 1. Forthrightness — *grounded*

**The question:** Did the answer address the question that was asked?

**Unit:** a question/answer pair, never an isolated statement. Evasion is a
*relation*; it cannot be seen in one sentence.

**Eligible when:** there is a clear question and an attributable response.
Source: Hansard oral question time (`corpus/oral_questions.jsonl`) and written
PQs (`corpus/written_questions.jsonl`).

**Owns:** pivoting, answering a different question, non-answers, refusals.

**Explicitly not:**
- *how detailed* the answer is → Specificity
- whether the answer is *true* → Veracity
- whether the answer is *polite* → Civility
- whether the reasoning is *valid* → Rigor

A rude, vague, false answer that squarely addresses the question **scores high
on Forthrightness.** This is counter-intuitive and must be stated in the prompt
with an example, or the model will fold the other four in — it currently does,
at r=0.73 with Rigor.

**Scored as a rate:** evasions per question faced. Never a raw count, or
whoever is asked most looks worst.

**Known defect:** this is close to a minister-only measure — only 104 of 135
MPs have a score. Written PQs widen it, but the asymmetry is structural: only
ministers are obliged to answer. Cards must not compare a minister's
Forthrightness with a backbencher's as though it were the same test.

---

### 2. Strength — *grounded*

**The question:** Did this member's stated commitments become law?

**Unit:** the member, over the term. Computed from `corpus/strength_ledger.jsonl`
— bills in charge, ballot bills, amendment papers, resolved manifesto and
coalition-agreement promises.

**The LLM does not score Strength in v3.0.** Its prompt becomes an *extraction*
prompt: pull out delivery claims and promises into `promises.jsonl`. Arithmetic
does the rest.

**Owns:** delivery, follow-through, abandoned commitments.

**Explicitly not:** how ambitious the goal is, how popular it is, or how
confidently it was announced.

**Delivery-scope gate:** an MP with no lever cannot deliver. `n=0` is
`not_applicable`, **never zero** — otherwise this becomes a measure of being in
government. Already implemented as `insufficient_evidence` in the ledger.

**Encouraging:** Strength is the one attribute that is already independent —
r=0.01 with Civility and −0.01 with Rigor. Grounding works.

---

### 3. Veracity — *grounded by search*

**The question:** Are the factual premises accurate?

**Unit:** one checkable factual claim.

**Eligible when:** the statement asserts a fact about the world that could in
principle be checked. Not opinions, not predictions (→ Divination), not value
statements.

**Owns:** false claims, misleading framing, hyperbole, exaggeration, true-but-
deceptive statements.

**Explicitly not:**
- whether the *conclusion follows* from the claim → Rigor
- whether the claim is *precise* → Specificity
- whether it is *rudely* expressed → Civility

**The change that matters — abstain rather than guess.** The prompt currently
says: score "how well-evidenced a claim *looks*", and "prefer ~0.5 for a
specific claim you cannot verify". That instruction is the bug. It makes
Veracity a judgement about *how the reasoning reads*, which is Rigor's job —
hence r=0.83 — and it manufactures a pile of uninformative 0.5s. Veracity
currently fires on 41% of the corpus and means almost nothing.

In v3.0 the extraction step no longer scores at all. It emits a **candidate**:

```
{claim, falsification_criterion, quote, subject}
```

If it cannot state a criterion — what evidence would show this true, and what
would show it false — the claim is not checkable and **nothing is emitted**. A
small honest Veracity set beats a large plausible one. Expect coverage to fall
sharply from 41%; that is the point, and it is what makes the resolver
affordable.

**The score comes from the resolver** (below), which searches for the evidence
and returns a verdict with its sources. That is what moves Veracity out of the
ungrounded tier.

**Handle spoken language carefully.** Hansard is lightly-edited speech, full of
inversions and self-corrections. A word-order slip is not a false claim. The
project has already had to withdraw one published example for exactly this.
When the literal reading is false but the intended reading is obviously true,
**skip it**.

---

### 4. Authenticity — *grounded, party-level*

**The question:** Does the stated position match the recorded vote?

**Unit:** a stated position, joined to `corpus/divisions.jsonl` through the
proposition vocabulary (`corpus/propositions.jsonl`).

**The LLM does not score Authenticity in v3.0.** It extracts a position —
`{subject, proposition_id, stance, quote, confidence}` — into `positions.jsonl`.
The join decides the score.

**Owns:** words-versus-deeds mismatch.

**Explicitly not:** self-contradiction within a single speech (that is a Rigor
matter unless it is a position reversal), and never an opponent's hypocrisy.

**The caveat is load-bearing.** NZ votes are cast per party, so this measures
*the party's* consistency with *this member's* words. An MP may personally
disagree with a vote they were counted in. The card must say so. Where a member
is recorded individually — conscience votes, named dissents — prefer that.

**Scored as a rate:** contradictions per position extracted, denominator shown.
Otherwise a prolific speaker looks worse for speaking more.

**Mandatory bias check:** opposition MPs vote against government bills because
that is their job. Confirm the vote-derived score has not simply inverted the
old directional bias.

---

### 5. Divination — *grounded by search*

**The question:** Did it come true?

Not "is it plausible" — that was the v2.0 question and it is why every MP scores
43–54, an eleven-point spread for a whole Parliament against a ±4 per-card
interval. It was measuring nothing while occupying one of nine terms in the
geometric mean.

**Unit:** one falsifiable prediction about a future event, as distinct from a
promise about the speaker's own action (→ Strength).

**Eligible when:** the prediction is specific enough that a criterion can be
stated *and* its horizon has passed. Extraction emits:

```
{prediction, falsification_criterion, resolve_by, quote, subject}
```

A prediction with no stateable criterion is not a prediction we can score —
emit nothing. A prediction whose `resolve_by` is in the future is retained but
**not scored yet**; it is a pending row, not a zero.

**Owns:** forecasting accuracy.

**Explicitly not:** whether the forecast was *reasonable at the time*. That is a
Rigor judgement about the inference, and conflating the two is why Divination
correlates 0.72 with Rigor today.

**The score comes from the resolver** (below).

---

### 6. Focus — *text-only; replaces Charisma*

**The question:** Is this about the policy, or about the other team?

**Why it exists.** Cutting Charisma left a real gap. Civility asks whether the
attack is on the *person* — so "Labour are hopeless, they failed in 2017 and
they'll fail again" passes Civility cleanly. No individual is insulted. But it
is pure tribalism with no policy content, and nothing in the nine caught it.
Focus does.

**Unit:** a statement made where a policy question is genuinely at issue.

**Eligible when:** there is a policy at issue to engage with. Ceremony,
procedure, and general debate with no measure before the House are ineligible.

**Scoring:**

- **1.0** — engages the substance: the mechanism, the cost, who it affects, what
  the evidence says.
- **1.0** — *also* legitimate scrutiny: "the government promised 1,000 homes and
  built 200" names a specific policy and outcome. **This is the job**, and it
  must score high.
- **~0.5** — a real policy point wrapped in party framing.
- **0.0** — entirely about the other party: their record in general, their
  hypocrisy, their internal divisions. No policy content at all.

**Owns:** tribalism, party-versus-party framing displacing the policy question.

**Explicitly not:**
- attacks on a **person** → Civility
- whether the argument is **valid** → Rigor
- whether the claim is **true** → Veracity

**The line that decides it: does the statement name a specific policy, measure
or outcome?** Naming one is what separates accountability from tribalism.

**Two risks to watch, both measurable.**

1. **Directional bias.** Opposition MPs criticise the government by role. If
   Focus penalises that, we have re-created the subject-attribution defect in a
   new place. The "scrutiny scores 1.0" rule above is the guard; the bias check
   in `V3_TODO.md` §B5 is how we confirm it held.
2. **Overlap with Specificity.** "Names a specific policy" is close to what
   Specificity measures. If `attribute_overlap.py` shows Focus/Specificity above
   0.65 after the pilot, the definition needs narrowing to *what the statement is
   about* rather than *how precise it is*.

Neither risk is a reason not to build it, but shipping it without checking both
would be.

---

### 7. Civility

**The question:** Is the attack on the argument, or on the person?

**Unit:** a statement in adversarial context.

**Eligible when:** something is genuinely contested. **Ceremonial speech is
ineligible** — tributes and condolences are trivially civil and currently
inflate the top of the scale.

**Owns:** ad hominem, insult, contempt, mockery of a person, imputing bad faith.

**Explicitly not:**
- **strawmanning** → Rigor *(moved: currently in both)*
- **hyperbole and sensationalism** → Veracity *(moved: currently in both)*
- whether the argument is *valid* → Rigor
- whether the claim is *true* → Veracity

A logically fallacious, factually wrong statement that attacks no one **scores
high on Civility.** The rubric must say this explicitly.

**Re-anchored (decided 2026-08-07).** The old scale put 0.5 at "harsh but
legitimate criticism" — *acceptable* conduct sitting at the midpoint, which made
the published "class average of 54 against a pass mark of 100" framing
indefensible. The new anchoring makes 1.0 the expected standard and 0.5 a
genuine failure:

| score | meaning |
|---:|---|
| **1.0** | Civil. Engages the substance, attacks no one. **This is the standard, not an achievement** — it is what every statement should be. |
| ~0.75 | Pointed and robust, edging toward the person but not landing on them. |
| **0.5** | A real failure. Imputing bad faith, sneering, mockery — short of a direct insult but no longer civil. |
| ~0.25 | A clear personal attack. |
| **0.0** | Contempt. Sustained abuse, attacks on a person's character, competence or worth. |

The consequence is deliberate: **"harsh but legitimate criticism of a policy"
now scores near 1.0, not 0.5.** Criticising a policy hard is civil. Only turning
on the person costs anything.

⚠️ **This makes every v2.0 civility score incomparable with v3.0.** Full
re-extraction is required — which was already committed for independent reasons
(§3.4 of `V3_PLAN.md`), so it costs no extra run. But no v2.0 civility number
may be quoted alongside a v3.0 one, including in the blog post.

---

### 8. Rigor

**The question:** Does the conclusion follow from the premises?

This is the user's formulation and it is the right one: **we are not fact-
checking. We are asking whether the reasoning is valid given its assumptions.
The accuracy of the assumptions is Veracity's job.**

**Unit:** one argument — at minimum a premise and a conclusion.

**Eligible when:** the statement actually advances an argument. A bare
announcement, a factual report or an expression of feeling has no inference to
assess and must be skipped. This gate alone should cut Rigor's 32% firing rate
substantially.

**Owns:** non-sequitur, strawman, false dichotomy, slippery slope, circular
reasoning, appeals to emotion/popularity/tradition/authority/anecdote, and
ad hominem **only where the conclusion depends on it**.

**Explicitly not:**
- whether the premises are **true** → Veracity. *An argument can be perfectly
  rigorous and built on false premises; it scores high on Rigor and low on
  Veracity. This must appear in the prompt as a worked example, because it is
  the single largest source of the current overlap.*
- whether the speaker is **rude** → Civility
- whether the statement is **specific** → Specificity
- whether the answer is **responsive** → Forthrightness

**Rigor is the hub of the redundancy problem.** It correlates above 0.65 with
six of eight. The eligibility gate and the disclaimers above are the fix, and
`attribute_overlap.py` is how we check they worked.

---

### 9. Specificity

**The question:** Is there checkable content in the statement?

**Unit:** a statement that is trying to convey substance.

**Owns:** platitudes, slogans, commitments with no mechanism or measure.

**Explicitly not:**
- whether the content is **true** → Veracity
- whether it **answers the question** → Forthrightness
- whether it is **well-argued** → Rigor

**Structural bias, to be stated on the card.** Specificity rewards "figures,
mechanisms, timeframes, named policies" — which is what a minister announcing a
programme produces and what an opposition MP asking why it has not happened does
not. It fires on 51% of the corpus and averages 0.62, the highest of the nine.
Either normalise within speaking role, or say plainly that this attribute
partly measures being in government.

---

## The resolver — one component, two attributes

**Decided 2026-08-07.** Veracity and Divination ask the same shape of question:
*is there evidence in the world that settles this?* One search-backed component
serves both, and it is what moves them out of the ungrounded tier.

| | input | question | verdict |
|---|---|---|---|
| Veracity | a factual claim | is it true? | `true` / `false` / `uncheckable` |
| Divination | a prediction + `resolve_by` | did it happen? | `correct` / `wrong` / `not_yet_due` / `unresolvable` |

### Pre-register the criterion before searching

The extraction step must state **what evidence would show this true, and what
would show it false**, before any search happens. The resolver then searches
against a criterion it cannot tune to whatever it happens to find.

This is the main defence against confirmation bias, and it is the same
discipline we apply to the prompt decision rule: fix the standard first, then
collect the result. A resolver that both chooses the target and judges the
throw is not evidence.

### Record the guess too — is searching even worth it?

After writing the criterion, extraction also records `prior_score`: the model's
**unaided guess**, from knowledge alone. It is never published. It exists to
answer a question that decides whether the resolver earns its cost:

> Does searching for evidence actually beat guessing?

The two are independent by construction — the guess is written before any
lookup, and **the resolver is never shown it**. `resolve.py compare` reports the
correlation and the gap:

- High `r`, small gap → the guess already tracks the evidence, and searching is
  an expensive way to confirm what the model knew.
- Low `r`, or a handful of large flips → the guess is confidently wrong
  somewhere. That is the failure the site cannot afford, and it justifies the
  cost.
- The `uncheckable` / `not_yet_due` share is where searching bought nothing.

Keeping the guess in a **separate field** from `score` is deliberate: it makes
it structurally impossible for a guess to be published as a resolved answer, no
matter what the model returns.

### The rest of the controls

- **Neutral queries.** Build the search from the *subject* of the claim, not its
  direction. Searching "Māui dolphin does not exist" and searching "Māui dolphin
  population status" return different internets.
- **The resolver never sees the original LLM score.** Anchoring on a prior
  judgement is the failure mode we are trying to avoid.
- **Cite sources, always.** Every verdict stores the URLs it relied on. The
  site's promise is that a number can be clicked back to its evidence; a
  resolved score that cannot show its working is worse than no score.
- **`uncheckable` is a valid, expected outcome** and must not be recorded as a
  low score. Failing to find evidence is not evidence of falsity.
- **Bias probe.** On a held-out sample, negate the claim and re-run. A resolver
  that confirms both a claim and its negation is measuring agreeableness, not
  truth. This should be a test, not an intention.

### Sequencing, because it decides the cost

Run the **abstain rule first**. Extraction drops every claim for which no
falsification criterion can be stated, so the resolver's input is far smaller
than v2.0's 18,725 veracity examples and 3,151 predictions. Ordering it the
other way round means paying to search for claims we were going to discard.

Only predictions whose `resolve_by` has passed are resolvable. A 2027 forecast
is a pending row, not a failure — and never a zero.

## Subject attribution applies to some attributes, not all

Every extracted row carries `subject: speaker | other | unclear` — whose conduct
the statement lets you judge. Only `speaker` rows count toward a card, which
fixes the worst v2.0 defect: an MP describing an opponent's broken promise had
the low score filed against themselves.

**But the field is meaningless for most attributes, and applying it everywhere
destroys data.** The first v3.0 smoke test made the error: an insult by Winston
Peters was filed `subject="other"` because the insult was aimed at someone else.
It would have been dropped from his card — deleting the very incivility we were
measuring.

The rule is whether a statement can **report someone else's record**:

| Attribute | `subject="other"` possible? | Why |
|---|---|---|
| Civility, Rigor, Specificity, Focus | **No — always `speaker`** | These measure how the speaker is conducting themselves *right now*. An insult aimed at someone else is still the speaker's own incivility; a muddled argument is the speaker's own muddle. |
| Strength, Authenticity | **Yes** | A statement can describe an opponent's broken promise or another party's flip-flop. This is where the v2.0 bug lived. |
| Veracity, Divination | **Yes, narrowly** | Only when the speaker is *relaying* a claim or forecast someone else made, rather than asserting it. |

Enforced by `attributes.normalise_subject()`, which overrides the model rather
than trusting it, and stated in the extraction preamble so the model is not
fighting the code.

## Quote fidelity — a requirement on every attribute

Measured on 800 sampled statements (`attribute-extraction/QUOTE_AUDIT.md`):

| | share |
|---|---:|
| verbatim | 85% |
| ellipsis-spliced from non-contiguous fragments | 9% |
| not found in the source at all | 6% |
| verbatim but cut mid-sentence | 25% |

Every score links to a quote, so the quote must be real. Three rules:

1. **Verbatim only.** No paraphrase, no cleanup, no resolving pronouns.
   `divination.txt` currently invites the opposite ("you may resolve
   pronouns/ambiguity for clarity") — remove that.
2. **No splicing.** If two fragments are needed, emit two examples.
3. **Whole sentences.** Start and end on a sentence boundary. A quarter of
   current quotes do not, and that is how a word-order slip becomes a
   "false claim".

Enforced by `check_quotes.py` as a pipeline gate, not a manual review.

---

## How we will know this worked

Re-run after the prompt rewrite:

```bash
cd attribute-extraction
python attribute_overlap.py run --out ATTRIBUTE_OVERLAP.md
python check_quotes.py run --n 2000 --out QUOTE_AUDIT.md
```

Targets, pre-registered before any prompt is touched:

| metric | v2.0 | target |
|---|---:|---:|
| max pairwise r | 0.96 | **< 0.65** |
| Civility / Rigor r | 0.85 | **< 0.65** |
| Veracity / Rigor r | 0.83 | **< 0.55** |
| Focus / Specificity r | *new* | **< 0.65** |
| Focus / Civility r | *new* | **< 0.65** |
| statements scored by 2+ attributes | 84% | **< 60%** |
| Specificity firing rate | 51% | **< 30%** |
| Veracity firing rate | 41% | **< 15%** (abstain rule) |
| quotes not found in source | 6% | **0%** (hard gate) |
| quotes cut mid-sentence | 25% | **< 5%** |

The two Focus rows are the ones to watch: it is a new attribute defined partly
by "names a specific policy", which is uncomfortably close to Specificity. If it
lands above 0.65 on either, it needs narrowing before it ships.

A prompt rewrite that improves accuracy but leaves the correlations where they
are has not fixed the instrument.

---

## Decisions log

| Date | Decision |
|---|---|
| 2026-08-07 | **Charisma cut**; **Focus** added in its place (policy vs the players). |
| 2026-09-24 | **Divination WITHHELD** — still extracted and measured, not shown on cards until the resolver has scored it. 113 of 1,618 claims resolved, so 95% of a card would be the model's guess (MAE 0.22, confidently wrong 6% of the time), and all 29 covered MPs shared one score. ~1.5 nights of resolver time brings it back. Cards show **six**: Forthrightness, Veracity, Focus, Civility, Rigor, Specificity. |
| 2026-08-07 | **Civility re-anchored** — 1.0 is the expected standard, 0.5 a genuine failure. Forces re-extraction; v2.0 civility scores become incomparable. |
| 2026-08-07 | **Veracity and Divination grounded by search**, via one shared resolver with pre-registered falsification criteria. |
| 2026-08-07 | **53rd Parliament deferred** until after the pilot — for the political-bias check and long-horizon outcomes, not for text-only evaluation. |
| 2026-08-07 | Hansard is already public, so **publishing the 54th corpus does not disqualify it for evaluation**. Hold back gold labels, not statements. |

---

## Decision 2026-08-15 — Strength and Authenticity deferred to v4

Seven attributes remain: Forthrightness, Veracity, Divination, Focus, Civility,
Rigor, Specificity.

**Strength — the ledger cannot answer the question the attribute asks.** Built,
measured, and cut on what the measurement showed. 53% of scored MPs (64 of 121)
have no resolved bill at all, so their score came entirely from ballot bills and
amendment papers: an activity count, not a delivery rate. Among ministers
`delivery_rate` took 4 distinct values across 29 people, so it barely separated
them either. The manifesto and coalition-promise side — the half that would make
this a genuine delivery measure — was never built. Publishing it would label a
rank-within-cohort activity count as "did commitments become law".

**Authenticity — the unit does not match the card.** NZ votes are cast per
party, and only 88 of 212 propositions carry an individual member record. For
most MPs it would measure *the party's* consistency with *this member's* words
and print the result on the member's card. Every other attribute measures the
person. v4 should rebuild it on conscience votes and named dissents, where the
unit is right.

**Focus was considered and kept.** The concern was its correlation, but it is
not distinctive: mean r with its neighbours is 0.62, against 0.61 for Rigor and
0.65 for Specificity. It is not a hub. It fills a gap nothing else covers —
"Labour are hopeless, they were hopeless in 2017" insults no one, so Civility
passes it cleanly — and it costs nothing extra, being extracted in the same
call.

**Veracity and Divination stay, resolved by search rather than guessed.** They
currently render from `prior_score`, which is a placeholder, not the answer.
The resolver is the accepted path; Divination is resolved first, being the
smaller set (110 pending against 1,109) and the one least able to stand on a
guess.

**What survives for v4:** `data/strength_score.py`, `data/authenticity_score.py`
and their 25 tests, `corpus/strength_ledger.jsonl`, the 212-item proposition
vocabulary, and the `extract_hansard.py --attrs positions` path. Their prompts
stay in `prompts/`. Nothing is deleted; the attributes are out of the active set
in `attributes.py` via `DEFERRED`.
