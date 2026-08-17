# The 3,000-token pilot (archived 2026-08-17)

260 windows over 2025-10, the instrument every v3.0 audit number describes.
Kept because it is the **baseline for the window-size change**, not because the
data is wanted: the full term is being re-extracted at 14,000 tokens.

## Why the switch

Content is constant — the same 13.9M tokens of Hansard however it is sliced.
What changes is how many calls it takes, and every call resends the 7,469-token
system prompt:

| window | calls | content | prompt overhead | total input |
|---:|---:|---:|---:|---:|
| 3,000 | 5,548 | 13.9M | 41.4M | **55.3M** |
| 14,000 | 1,127 | 13.9M | 8.4M | **22.3M** |

At 3k, three-quarters of everything sent is the same rubric over and over. The
subscription cap is the binding constraint on this project, so 60% less input
for identical coverage is the one lever that attacks it directly. Wall clock
barely moves (116h vs 94h) — the saving is tokens, not time.

## What to compare against

These are the numbers the 14k run has to hold:

| measure | 3k pilot |
|---|---|
| max pairwise r | 0.73 (focus/civility, 12%/19% share) |
| focus / rigor | 0.54 |
| rigor / specificity | 0.71 (on 30 co-scored — thin) |
| quotes verbatim | 100% of 800 sampled |
| statements with 2+ attributes | 18% |
| specificity firing | 37% |

Regenerate the equivalents with `attribute_overlap.py` and `check_quotes.py`
against the 14k output and put them side by side. A bigger window means the
model sees a whole debate rather than a slice, which may change what it selects
and how it judges — that is the thing being tested, and it is unmeasured until
those two reports are run.

## Do not merge these rows into a 14k file

`window_id` is `<date>#<index>` and the index is a position within that day's
packing, so 2025-10-07#3 is a different passage at each size. `_saved_ids` now
refuses to resume across sizes, but this file predates the `window_tokens`
marker and would only produce a warning.
