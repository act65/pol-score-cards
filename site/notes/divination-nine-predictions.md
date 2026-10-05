---
title: A real signal, smaller than its own error bars
date: 2026-09-26
summary: MPs' checkable predictions come true 72% of the time. Some MPs are genuinely better at it than others. With nine predictions each we cannot tell you which — and resolving every last prediction did not change that, so the attribute came off the card.
tags: attributes, statistics, withheld
---

Divination asks whether a prediction came true. Not whether it was reasonable when made —
that is a judgement about the argument, and it belongs to Rigor. Just: the MP said a thing
would happen, did it happen.

This is the hardest attribute to score and the most satisfying when it works, because the
answer exists in the world rather than in anybody's opinion. The extractor pulls out a
prediction, writes down what would settle it and by when, and refuses to score it. A
separate resolver then goes and searches, and records the verdict **with the sources it
decided on**, which you can click.

It produced a genuinely interesting number and it still should not be on a card. Both of
those are worth explaining.

## What the verdicts say

Of 878 resolved claims so far, 413 are divination predictions with a settled outcome:

| verdict | share |
|---|---:|
| came true | 46% |
| partly | 13% |
| did not come true | 16% |
| too early to tell | 22% |
| no source settles it | 2% |

Scored on the 0 / 50 / 100 scale the card uses, **MPs' checkable predictions come true about
69% of the time.** That is the single most quotable thing this project has produced, and it
is a fact about Parliament rather than about anyone in it.

## The individual records look convincing

| MP | score | record |
|---|---:|---|
| Julie Anne Genter | 92 | 11 right, 0 partly, 1 wrong |
| David Seymour | 86 | 6 right, 0 partly, 1 wrong |
| Dan Bidois | 42 | 2 right, 1 partly, 3 wrong |
| Louise Upston | 27 | 2 right, 2 partly, 7 wrong |

Eleven-from-twelve against two-right-seven-wrong is not a subtle difference, and the
temptation is to rank all 130 MPs like this and be done.

## Why we can't

A single verdict is 0, 50 or 100. That makes the standard deviation of *one observation*
**41 points** — enormous, because there is no such thing as a partly-partly-true. With nine
observations per MP, the error on an individual average is roughly 14 points before we say
anything about anybody.

So the question is not "do the MPs differ" but "do they differ by more than 14 points". You
can answer it by taking the observed spread of per-MP averages and subtracting the part that
sampling luck alone would produce:

| | observed spread of MP means | sampling noise alone | **real differences** |
|---|---:|---:|---:|
| MPs with ≥6 predictions (24) | 15.3 pts | 14.0 pts | **6.2 pts** |
| MPs with ≥8 predictions (16) | 14.0 pts | 12.8 pts | **5.5 pts** |

The real differences are about **6 points wide**. The error on the card meant to show them is
**14**. The signal is not zero — Genter really is better at this than Upston — it is just two
to three times smaller than our ability to measure it per MP. Most of the visible spread in
that table above is luck.

This also rules out the comfortable explanation that our variance estimate was thrown off by
MPs with only one or two predictions. Restricting to MPs with eight or more still leaves only
5.5 points of real signal.

### How much would be enough

At 41 points per observation:

| to get the per-MP error down to… | predictions needed each |
|---|---:|
| 5.5 pts — equal to the real differences | **56** |
| 2.8 pts — half of them | **223** |

We have a median of **9**. The entire remaining queue is 1,881 predictions across ~130 MPs,
so even at 100% resolution we land near **14 each** — four times short. **Resolving more does
not fix this.** The constraint is how many checkable predictions one MP makes in one
parliamentary term, and that is roughly a dozen.

## The shrinkage was telling us this all along

The cards use empirical-Bayes shrinkage: an estimate is pulled toward the population mean in
proportion to how little its own evidence supports it. The pull is reported as `shrink`,
where 1.0 means "trust this MP's own data" and 0 means "we learned nothing, here is the
House average".

| attribute | statements per MP | shrink | spread across the House |
|---|---:|---:|---:|
| Focus | 82 | 0.89 | 61 pts |
| Specificity | 108 | 0.88 | 35 pts |
| Rigor | 74 | 0.87 | 34 pts |
| Civility | 45 | 0.84 | 51 pts |
| Veracity | 165 | 0.80 | 17 pts |
| **Divination** | **9** | **0.09** | **9 pts** |

Every Divination card was **91% population mean and 9% that MP**. The nine-point spread
across 129 MPs was not a measurement of anything; it was the House average with a rounding
error on top.

Note Veracity in that table, though: only 17 points of spread, so MPs barely differ there
either. It survives because n is 165 — the *differences* are small but the *estimate* is
solid. That is the real distinction. The failure mode is never a small signal on its own;
it is a small signal relative to how much evidence you have.

## Two things we changed because of this

**A prediction that cannot be settled yet gets no score.** 22% of resolved predictions come
back "too early to tell". Those used to fall through to the model's unaided guess and be
published as a number. They are now shown as evidence with no score at all. Fixing them to
50 instead would have been worse than it sounds: the prompt *instructs* the model to write
0.5 when the date has not passed, so 42 of the first 68 already were 50 — and a middling
score drags every long-horizon prediction toward the middle while one about next week keeps
its 100. That punishes exactly the boldness the attribute is supposed to reward.

**Confidence now accounts for shrinkage**, which is [its own story](/notes/a-narrow-interval-is-not-confidence).

## Where it stands

Not "Divination measures nothing" — that was the problem with an earlier design, which scored
plausibility-when-made, correlated 0.72 with Rigor and put every MP in an eleven-point band.
This version measures something real.

It is that **this instrument can measure the House but not the MP.** The 69% is solid. The
ranking is not. So the verdicts stay published as evidence on each MP's page, with their
sources; the number comes off the card.

## Epilogue, 5 October 2026: we resolved all of them

This post was written on 878 verdicts and ended on a prediction of its own — that the
ranking would not survive. On 4 October the resolver finished the **entire queue**: 1,884
verdicts against 1,881 extracted claims. So this is no longer an argument from a sample.

**The aggregate got better.** 72.1% of checkable predictions came true, across 1,171 scorable
claims. It has barely moved as the sample grew — 69%, then 71.3%, then 72.1% — which is what
a real population number looks like. That figure is the most interesting thing this attribute
produced and it is worth knowing: when a New Zealand politician makes a prediction specific
enough to check, it comes true about seven times in ten.

**The ranking got worse.** Not noisier — *worse*, because precision improved and the signal
still did not appear:

| verdicts | shrink | true between-MP sd | sampling noise |
|---:|---:|---:|---:|
| 878 | 0.09 | 5.5–6.2 | 12.8–14.0 |
| **1,884** | **0.03** | **2.6** | **13.5** |

At five or more scorable predictions per MP — 82 MPs, a median of nine each — the posterior is
**97% population mean and 3% that MP**. Restricting to the 40 best-covered MPs only reaches
shrink 0.38, and noise still exceeds signal, now while publishing 40 cards out of 133.

A third of the problem is structural and will not improve: **38% of resolved predictions carry
no score at all** — 667 "too early to tell" and 42 unfindable. A prediction about 2030 is not
a failed prediction, so it gets no number, which is right and also means a long-horizon
predictor accumulates evidence very slowly.

So the post's last line has been carried out. The verdicts stay on each MP's page as evidence,
with the sources they were decided on. The number is off the card.

**What took its place.** [Acuity](/rubric/Acuity) — does this speech engage with what was
actually just said. On the same full-term corpus it has a true between-MP sd of **13.9 against
sampling noise of 3.4**: signal four times noise, where Divination's noise was five times its
signal. That contrast is the whole lesson of this post, and it took measuring both to see it.
