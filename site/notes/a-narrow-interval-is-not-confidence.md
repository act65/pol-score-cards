---
title: A narrow interval is not confidence
date: 2026-09-26
summary: Seventy cards were labelled "high confidence" precisely because we had learned almost nothing about the MPs on them. The interval was correct; the word next to it was not.
tags: statistics, bugs
---

Every score on this site carries an interval and a one-word confidence tier. Until this week
the tier read off the interval and the sample size:

```python
if ci95 <= 0.05 and n >= 8:
    return "high"
```

That looks unobjectionable. It produced **70 of 129 Divination cards labelled "high
confidence"** on an attribute whose entire spread across Parliament was nine points — and it
was the narrowness of the intervals that did it.

## How a tight interval can mean the opposite

The cards use empirical-Bayes shrinkage. Each MP's score is a blend of their own average and
the population mean, weighted by how much their evidence supports them:

```
shrink   = between_var / (between_var + se²)
post_var = 1 / (1/between_var + 1/se²)
```

The second line rearranges to something worth staring at:

```
post_var = between_var × (1 − shrink)
```

As an MP's evidence gets noisier, `se²` grows, `shrink` falls toward zero, and the posterior
variance converges on `between_var` — **the spread of the whole House**. If MPs are tightly
bunched on an attribute, that is a small number, so the interval comes out *narrow*.

The interval was never wrong. A posterior that has collapsed onto the prior really is narrow,
and the honest sentence to attach to it is *"we are confident this MP is somewhere near
average, because we learned nothing that would move them off it."*

What we printed instead was **high confidence**, which every reader correctly understands as
*we measured this person well.* Same number, opposite meaning.

## Why it survived so long

Because it only bites when shrinkage is severe, and on five of the six attributes it is not:

| attribute | mean shrink | was h/m/l | now h/m/l |
|---|---:|---|---|
| **Divination** | **0.09** | 3 / 114 / 13 | **1 / 2 / 126** |
| Veracity | 0.80 | 122 / 10 / 1 | 122 / 9 / 2 |
| Civility | 0.84 | 44 / 72 / 16 | 44 / 72 / 16 |
| Rigor | 0.87 | 100 / 31 / 1 | 100 / 31 / 1 |
| Specificity | 0.88 | 66 / 59 / 7 | 66 / 59 / 7 |
| Focus | 0.89 | 37 / 78 / 17 | 37 / 78 / 17 |

At a shrink of 0.85 the posterior is dominated by the MP's own data and the interval means
what it appears to mean. The two readings only diverge at the bottom of that column, and until
Divination arrived nothing lived there.

## The fix

Confidence now also reads `shrink` — the share of the estimate that is this MP rather than
the prior. Below a half it cannot be "high"; below a quarter it is "low" whatever the interval
says.

Thresholds on the share of the estimate rather than on the interval, because the share is the
thing a reader is being misled about.

## The test was the interesting part

The first regression test built a population by sampling: 130 MPs, nine coin-flip-ish
observations each, check that the defect is caught. It passed, and it was worthless.

Whether the defect appears at all depends on whether `between_var` bottoms out at its floor,
and with sampling that depends on the seed. Three seeds gave 0, 0, and 130 affected cards. The
test was a coin flip about a coin flip.

It now builds the pathological case deterministically: every MP gets the *same multiset* of
scores, so the spread of per-MP means is exactly zero, `between_var` is guaranteed to floor,
and the interval collapses to ±0.2 points on an attribute where nobody has been measured at
all. That is the situation the label has to get right, and now it is pinned rather than
stumbled upon.

## What to take from it

The general shape: **a summary statistic that is correct can still be a lie once you put a
word next to it.** The interval was right. `high` was a translation, and the translation was
wrong for a whole class of inputs nobody had looked at yet, because those inputs only occur
when the underlying measurement is failing — exactly when you most need the label to be
honest.

Which is the argument for [publishing the failures](/notes) as well as the scores.
