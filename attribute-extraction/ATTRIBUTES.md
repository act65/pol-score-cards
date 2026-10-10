
## Decision 2026-10-02 — Veracity's queue is not full of junk, so narrowing the prompt is the wrong tool

The goal was to tighten Veracity so the resolver faces a manageable number of
claims: 25,747 extracted, 25,486 unresolved, which at the measured 58
verdicts/h is **444 hours**. The intended mechanism was a prompt gate on
structural anchors (a figure, a date, a named source, a comparison) — the
rewrite of the uncredited abstain rule recorded on 2026-09-27.

**Measured first, on the 276 veracity claims already resolved. The premise is
false: 97% of them came back usable** — 170 `true`, 82 `partly_true`, 15
`false`, and only **9 `uncheckable`**. There is no unresolvable chaff to filter
out, so there is nothing for a checkability gate to catch.

No structural gate beats that base rate:

| gate | claims kept | usable verdict | vs 97% base |
|---|---:|---:|---:|
| figure | 164 | 96% | −1.0 |
| source | 18 | 100% | +3.3 |
| compare | 54 | 94% | −2.3 |
| figure AND compare | 30 | 93% | −3.4 |
| figure AND (year OR source) | 36 | 100% | +3.3 |

The two gates that reach 100% do so on n=18 and n=36, for +3.3 points over a
97% base. Meanwhile the tight gate would discard **239 of 276 (87%)** claims
that *did* resolve usefully.

So a prompt gate cuts volume without improving verifiability. It is a sampling
decision wearing a quality filter's clothes — and an expensive one: it needs a
fresh 5,548-window extraction (~$1,640, 18–28 h) and yields a subset whose
composition nobody chose.

**Resolved instead by sampling what is already on disk.** `resolve.stratify()`
caps claims per politician and draws them at an even stride through the term.
The median MP has 160 veracity claims and 113 of 138 have at least 56, so:

| cap per MP | claims | resolver hours |
|---:|---:|---:|
| 10 | 1,349 | 23 |
| 20 | 2,658 | 46 |
| 30 | 3,924 | 68 |
| 56 | 6,992 | 121 |

against 444 h unstratified. The even stride matters as much as the cap: taking
each MP's *first* n claims would rebuild the time bias inside every MP, which
is the bias that got `resolve_veracity` pulled on 2026-09-08 (371 of 389
resolved claims from one month out of seven).

**What this does NOT settle.** The abstain rule now in `prompts/veracity.txt`
is untested against real output — the 25,747 claims on disk were all extracted
before it landed, so it affects only future extraction (the June-to-election
Hansard, once scraped). Narrowing Veracity may still be worth doing there on a
different argument: at 4.6 claims/window it consumes 31% of the whole
extraction's output budget. That is a cost-of-extraction case, not a
quality-of-claims case, and it should be argued on its own evidence.

## Decision 2026-10-10 — Charity (steel/strawmanning) rejected before the pilot; Calibration piloted instead

Two attributes were proposed to fill the gap left by Veracity being the only
externally-verified attribute (and at $1.24 per verdict against $0.15 per
text-scored example, 8x the cost of the other five).

### Charity — REJECTED, on the ownership ledger, without spending a call

The idea: does the member engage the strongest version of the opponent's
argument, or a caricature? It was rejected because **strawmanning is already
owned**, in two places:

* `prompts/rigor.txt` lists `strawman` as an explicit 0.0 criterion, alongside
  non-sequitur and false dichotomy.
* `prompts/acuity.txt` already instructs the model that a strawman is "HIGH
  Acuity and LOW Rigor", naming it as the most likely confusion between those
  two.

That leaves only the positive half — steelmanning — and Acuity claims most of
that too: engaging the strongest form of an argument IS close engagement, which
Acuity scores 1.0. A third prompt claiming the same behaviour is the
double-counting this ledger exists to prevent, and it is a DEFINITIONAL
conflict, so no amount of pilot data resolves it. Rejecting it on the ledger
cost nothing; a pilot would have cost ~$83 to discover the same thing.

If charity is ever revisited, the honest route is to take strawmanning OUT of
Rigor's 0.0 list first and re-pilot Rigor, not to add a third claimant.

### Calibration — PILOT, 2025-10

`prompts/calibration.txt`, registered in `attributes.py` as WITHHELD.

THE ONE QUESTION: *is the speaker as certain as this kind of claim allows?*

The gap it fills is real and none of the six catch it: a member can be truthful,
precise, logical, responsive, civil and on-topic while asserting flatly
something nobody could know. Nobody understands the long-run behaviour of an
economy, so "this will destroy New Zealand's economy" is **not a lie** — there
is no fact of the matter yet — which is exactly why Veracity cannot catch it.
Rigor needs an inference to judge, and this is often a bare assertion.
Specificity scores the overclaim *higher* when it is precise: "GDP will be 2.4%
higher by 2035" is high Specificity and low Calibration, and that is the
separating case the prompt is built around.

It also covers the category error of presenting a PREFERENCE as a FINDING ("it
is simply a fact that this is the wrong priority"). These are one attribute
rather than two because both are a mismatch between the certainty used and the
kind of claim made.

`claim_class` is REQUIRED (`value` | `settled_fact` | `contested_empirical` |
`forecast`, plus the confidence markers quoted), on the same principle as
Acuity's `responding_to`: a judgement a reader cannot audit is not evidence.

**Supporting evidence already in hand.** 158 of 657 resolved veracity claims
(24%) came back `partly_true`, defined in the resolver prompt as "the substance
holds but is materially overstated, or true only under a reading the speaker did
not signal". That vice currently scores 50 inside Veracity, where it is
indistinguishable from "half right".

**The two failure modes to watch for in the pilot**, both of which would be the
prompt's fault and not the model's:
1. It becomes a vagueness detector. "There may possibly be some effects" must
   score ~0.3, not 1.0 — the prompt says so explicitly, twice.
2. It penalises conviction. A firmly-held value clearly marked as the speaker's
   own is a 1.0. If the pilot shows `value` rows scoring low, the prompt is
   wrong, not the MPs.
