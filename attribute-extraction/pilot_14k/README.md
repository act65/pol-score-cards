# The 14,000-token window test (2026-08-18)

One night at `window_tokens=14000`, run against the same month the 3k pilot
covered so the two are comparable. **Result: reverted to 3,000.** These files are
kept as the evidence, not as data — nothing here is in the active dataset.

`hansard_scores_14k.jsonl` — 37 of 51 windows (quota went at ~02:30), covering
2025-10-07/08/09/14/15/16 complete plus 2025-10-21 partial. 1,219 examples.

Compared against `pilot_3k/hansard_scores_3k.jsonl` on the six complete days:

| measure | 3k | 14k |
|---|---:|---:|
| examples on those 6 days | 2,381 | 1,045 (44%) |
| examples per sitting day | 397 | 174 |
| examples per 1,000 window tokens | 4.7 | 2.35 |
| content input, full term (`--dry_run`) | 13,904,410 | 13,908,271 |
| statements with 2+ attributes | 26% | 19% |
| quotes verbatim | 100% | 100% |

Per-day recall ratio was 0.42-0.52 on every day individually, so the halving is
not one bad day.

## Coverage within the window

Every window rebuilt and every quote located inside it, binned by relative
position:

| fifth | 3k | 14k |
|---|---:|---:|
| 1 | 20.0% | 27.1% |
| 2 | 21.0% | 21.9% |
| 3 | 18.8% | 17.4% |
| 4 | 19.6% | 15.9% |
| 5 | 20.7% | 17.7% |

chi2(4) = 5.7 at 3k (uniform, p=0.22) against 49.5 at 14k (p<1e-9). The model
covers a 3k window evenly and a 14k one from the front.

## Per attribute

| attribute | recall at 14k | mean 3k -> 14k |
|---|---:|---|
| focus | 30% | 0.74 -> 0.60 |
| specificity | 43% | 0.67 -> 0.73 |
| rigor | 46% | 0.49 -> 0.50 |
| civility | 47% | 0.60 -> 0.48 |
| veracity | 49% | (no score at extraction) |
| divination | 58% | (no score at extraction) |

Focus — the attribute a whole-debate window was most supposed to help — fired
least and moved most.

## Stability

Across 57 MP-attribute cells with >=4 scores in both runs, the two window sizes
agree at r = 0.77, mean |difference| 0.10, with 10 cells moving more than 0.15
(Luxon's Focus 0.49 -> 0.26). A score that depends on how the transcript was
chunked is not measuring the MP.

## What 14k genuinely won

Multi-attribute double-counting 26% -> 19%, and 8.4M rather than 41.4M tokens of
repeated system prompt over the full term. Both real; neither is worth 56% of
the evidence, and both sizes are far inside the <60% overlap target already.

Not a prompt defect: the preamble says "find EACH statement that bears on any
attribute", with no cap and no notability filter.
