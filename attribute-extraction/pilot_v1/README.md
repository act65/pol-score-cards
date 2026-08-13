# Pilot run 1 — before the Focus/Rigor separation

220 of 260 windows of 2025-10, Opus 5, 3k-token windows. Stopped at its 6am
deadline, not by failure.

**Kept as the before/after baseline.** The prompts changed after this run, so
these scores are not comparable with the current `hansard_scores_v3.jsonl` and
must never be merged with it.

What it established:

| metric | v2.0 | target | this run |
|---|---:|---:|---:|
| quotes not found | 6% | 0% | **0%** |
| quotes mid-sentence | 25% | <5% | **0%** |
| statements with 2+ attributes | 84% | <60% | **24%** |
| Specificity firing rate | 51% | <30% | 41% |
| max pairwise r | 0.96 | <0.65 | **0.87** (focus/rigor) |

The quote gate and the attribute separation both worked. The one miss was
Focus/Rigor at 0.87 — driven by a cluster (21% of their 96 co-scored
statements) where both fired low on content-free attacks on the other party:
off-policy by Focus's reckoning, and labelled a fallacy by Rigor's.

The fix tightened **Rigor's** eligibility gate rather than narrowing Focus,
because the cases where they disagreed were Focus working correctly (high
focus + low rigor = engaging the policy, reasoning badly) and narrowing Focus
would have deleted the signal it exists to capture.

Re-run `attribute_overlap.py` against both files to see whether it worked.
