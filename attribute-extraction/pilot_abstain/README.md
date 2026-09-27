# Veracity abstain rule + Focus narrowing — pilot, 2025-10

Two pilots, because the first was confounded. Both on the same 260 windows the
Acuity pilot used, so the corpus is held constant.

| run | attrs requested | windows | dir |
|---|---|---|---|
| A | `veracity,focus` | 260 | `pilot_abstain/` |
| B | `scores` (all 7) | **45 of 260 — killed** | `pilot_full/` |

## Result 1: the Focus narrowing works

| | Focus × Civility r |
|---|---:|
| current prompt | 0.731 |
| **narrowed prompt** | **0.487** |

Target is < 0.65. The mechanism is directly visible and does not depend on the
yield question below: **67% of the statements the current prompt scores at or
below 0.1 are now omitted entirely**, and they are unambiguously personal abuse —
"He's out of touch and he's refusing to take responsibility", "the spin of
Christopher Luxon", "the cosplaying Prime Ministers". Focus abstains; Civility
owns them. **Keep this change.**

## Result 2: firing rate cannot be measured this way

Run A showed Focus firing +117%, which is impossible from a change that only
*narrows* eligibility. The cause:

- **50% of run A's Focus statements were never extracted by the 6-attribute
  baseline at all.**
- Distinct statements per window: **11.2** with 6 attributes, **7.3** with 2.

Per-attribute yield depends on HOW MANY ATTRIBUTES are in the system prompt. The
model has a roughly fixed example budget per window and divides it.

Run B held the attribute set at the production 7 and confirmed it from the other
direction — on 45 windows, prompts that were **not touched** moved as much as the
ones that were:

| attribute | change vs baseline | prompt |
|---|---:|---|
| veracity | −25% | **changed** |
| focus | +52% | **changed** |
| civility | −52% | unchanged |
| rigor | −44% | unchanged |
| specificity | −26% | unchanged |
| divination | −58% | unchanged |

Total yield fell 15.7 → 13.1 per window *while adding a seventh attribute*.

**So the abstain rule's −25% cannot be credited to the abstain rule.** It is
indistinguishable from crowding at this sample size.

## Result 3: two earlier claims were wrong

1. **"Bundling attributes is nearly free."** The token and throughput arithmetic
   was right — content input is identical and only the cached system prompt grows
   — but per-attribute *yield* falls 26–58%. Bundling costs evidence density.
2. **Acuity's coverage was extrapolated from a 1-attribute pilot.**

   | | per window | per MP over the term |
   |---|---:|---:|
   | alone | 1.75 | 74 |
   | bundled with 6 others | **0.77** | **32** |

   Still 3.5× Divination's nine and the gates still pass, but not the 103
   originally reported, and shrink/spread will be lower than the pilot suggested.

## Result 4: Veracity is still unresolvable

| | claims over the term | resolver nights at 73/h |
|---|---:|---:|
| baseline | 26,708 | **52** |
| with the abstain rule | 20,128 | **39** |
| target | ~9,200 | 18 |

39 nights is past the election. The rule is not sufficient, whatever the cause.

**Suspected flaw in the rule as written:** the "uncontested" test asks the model
whether anyone would dispute the claim, which invites it to judge the truth
*before* writing the falsification criterion — the exact ordering the prompt
exists to prevent. A rewrite should key on structural properties instead: does the
claim carry a figure, a date, a named source, a comparison.

## Why run B was killed at 45/260

24 windows/hour against the resolver's 23:00 start, which would have put four
concurrent `claude -p` workers against a documented ceiling of about two. The
divination queue (1,282 claims, ~17.6 h) is worth more than a firmer estimate of
a number we already know is insufficient.

## Next, and cheaper than another run

Measure **composition** rather than yield: of the veracity claims extracted, what
share carry a figure, date or named source? That is robust to crowding and
computable on data already on disk.
