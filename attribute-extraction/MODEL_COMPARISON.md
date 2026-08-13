# Model comparison

Sampled 3 Hansard windows from 2024-11 (deliberately not the 2025-10 pilot month).

**`claude-opus-5` is treated as ground truth.** The question is not which model is best in the abstract — it is whether a cheaper one reproduces the reference closely enough to use across 1,127 windows. No human labels are involved, so this measures faithfulness and contract compliance, not accuracy.

## Contract compliance

| model | proposed | kept | quote-gate rejects | missing criterion | sec/window |
|---|---:|---:|---:|---:|---:|
| claude-opus-5 | 118 | 118 (100%) | 0.0% | 0.0% | 149 |
| claude-sonnet-5 | 109 | 109 (100%) | 0.0% | 0.0% | 372 |
| claude-opus-4-8 | 72 | 72 (100%) | 0.0% | 0.0% | 273 |

`quote-gate rejects` is the share of proposals thrown away for paraphrasing, splicing with an ellipsis, or cutting mid-sentence. **Lower is better** — it is pure instruction-following.

## Attribute independence

Max pairwise correlation among co-scored statements. Target: **< 0.65**.

| model | max pairwise r | worst pair | statements 2+ attrs |
|---|---:|---|---:|
| claude-opus-5 | — | too few co-scored | 29% |
| claude-sonnet-5 | — | too few co-scored | 26% |
| claude-opus-4-8 | — | too few co-scored | 21% |

*Small samples make these noisy — read them as a smoke test for a model that has collapsed the attributes, not as the final number. `attribute_overlap.py` on a full run is the real measurement.*

## Self-consistency

Mean absolute gap between two runs of the same model on identical input. **Lower is better**; this is a floor on agreement with any human.

| model | mean gap | statements compared |
|---|---:|---:|
| claude-opus-5 | 0.030 | 27 |
| claude-sonnet-5 | 0.039 | 9 |
| claude-opus-4-8 | 0.039 | 14 |

## Agreement with the reference (`claude-opus-5`)

**This is the decision.** Opus 5 is treated as ground truth; a cheaper model is a viable substitute if it scores the same statements the same way. Two models can each look fine on compliance and still disagree with each other about everything, which is what this catches.

| model | statement overlap | scored in common | Pearson r | mean gap | agree ±0.25 |
|---|---:|---:|---:|---:|---:|
| claude-sonnet-5 | 0.33 | 16 | 0.88 | 0.078 | 94% |
| claude-opus-4-8 | 0.50 | 20 | 0.93 | 0.070 | 100% |

`statement overlap` is Jaccard over which statements each model chose to extract at all. **It caps everything else** — a model that agrees perfectly on the 30% of statements it also surfaced is still producing a different dataset. Read this column first.

Rough bar for switching: overlap ≥ 0.6, `r` ≥ 0.85, mean gap ≤ 0.10, and a quote-gate reject rate no worse than the reference's.

## Errors (1)

- claude-sonnet-5 2024-11-07#2: claude --json-schema failed after 3 attempts: timeout after 300s

