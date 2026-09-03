# Prompt-placement A/B

10 windows scored under both arms.

A = rubric prepended to the user message (how the corpus was built)
B = rubric passed as --system-prompt

## Cost per call

| | A | B | change |
|---|---:|---:|---:|
| output tok | 9,307 | 7,316 | -21% |
| cache read | 14,434 | 20,261 | +40% |
| cache write | 27,461 | 18,741 | -32% |
| fresh in | 2 | 2 | +0% |
| seconds | 116 | 91 | -22% |

Weighted at public list rates, B costs **76%** of A per call — about **1.32x** the throughput for the same cap.

## Is it the same instrument?

examples: A 132, B 124 (94% of A)

| attribute | A | B | statement overlap | r on shared | mean A | mean B |
|---|---:|---:|---:|---:|---:|---:|
| civility | 16 | 15 | 0.41 | 0.95 | 0.56 | 0.52 |
| divination | 7 | 6 | 0.62 | — | — | — |
| focus | 23 | 23 | 0.12 | — | 0.69 | 0.62 |
| rigor | 26 | 23 | 0.26 | 0.95 | 0.41 | 0.43 |
| specificity | 27 | 23 | 0.35 | 0.98 | 0.68 | 0.61 |
| veracity | 33 | 34 | 0.63 | — | — | — |

`statement overlap` is Jaccard on the exact quotes chosen. Two runs of the SAME prompt do not score 1.00 either — the model is sampled, not deterministic — so read B against that floor, not against perfection.

## Verdict

mean statement overlap 0.40, mean score r 0.96, yield ratio 0.94
same-prompt floor (corpus vs arm A) 0.38 — the most agreement any change could show

**Same instrument within sampling noise.** Adopting B is a cost change, not a measurement change — the 970 windows already scored stay comparable.
