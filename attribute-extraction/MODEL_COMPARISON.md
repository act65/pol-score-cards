# Model comparison

Sampled 3 Hansard windows from 2024-11 (deliberately not the 2025-10 pilot month).

**`claude-opus-5` is treated as ground truth.** The question is not which model is best in the abstract — it is whether a cheaper one reproduces the reference closely enough to use across 1,127 windows. No human labels are involved, so this measures faithfulness and contract compliance, not accuracy.

## Contract compliance

| model | proposed | kept | quote-gate rejects | missing criterion | sec/window |
|---|---:|---:|---:|---:|---:|
| claude-opus-5 | 54 | 54 (100%) | 0.0% | 0.0% | 148 |

`quote-gate rejects` is the share of proposals thrown away for paraphrasing, splicing with an ellipsis, or cutting mid-sentence. **Lower is better** — it is pure instruction-following.

## Attribute independence

Max pairwise correlation among co-scored statements. Target: **< 0.65**.

| model | max pairwise r | worst pair | statements 2+ attrs |
|---|---:|---|---:|
| claude-opus-5 | — | too few co-scored | 14% |

*Small samples make these noisy — read them as a smoke test for a model that has collapsed the attributes, not as the final number. `attribute_overlap.py` on a full run is the real measurement.*

## Self-consistency

Mean absolute gap between two runs of the same model on identical input. **Lower is better**; this is a floor on agreement with any human.

| model | mean gap | statements compared |
|---|---:|---:|
| claude-opus-5 | — (need repeats ≥ 2) | 0 |

