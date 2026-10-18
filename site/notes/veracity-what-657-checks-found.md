---
title: What 657 fact-checks found, and why Veracity still left the card
date: 2026-10-18
summary: Two thirds of the checkable claims MPs made were true, a quarter were true but materially overstated, and one in twelve was false. It is a finding about Parliament, not a score for any individual MP — and that is exactly the problem.
tags: attributes, veracity, withheld, resolver
---

Veracity asked the question a reader most wants answered: **are the factual
premises accurate?** It is not on the card any more. This is what it found
first, and then why it went.

## What the checks found

The resolver takes a claim, writes down what evidence would settle it *before*
looking, searches for that evidence, and returns a verdict. 657 claims were put
through it.

| verdict | n | share |
|---|---|---|
| **true** | 424 | 64.5% |
| **partly_true** — the substance holds but is materially overstated | 158 | 24.0% |
| **false** | 55 | 8.4% |
| uncheckable — no source settles it | 20 | 3.0% |

Of the 637 that could be checked at all: **two thirds true, a quarter
overstated, one in twelve false.**

The middle row is the interesting one, and it is the one a true/false frame
destroys. A representative case:

> "In the last year, wage growth has outpaced the cost of living in the first
> year of our new Government—compare that to the 13 quarters in a row under
> Labour, where wages grew slower than inflation."

The first half is confirmed on every standard Stats NZ measure. The second half
is overstated. Nothing here is fabricated; the claim is built out of true
material and then pushed past what the material supports. **A quarter of
everything we checked was like this** — which is why the attribute that replaced
Veracity on the card asks about *overstatement* rather than truth.

Outright falsity does occur:

> "Well, in answer to the first part of the question, there is no hiring freeze."

Health NZ had ordered an immediate hiring freeze on all non-frontline roles, and
there was no evidence it had been lifted.

## Why it is not a score

657 claims across 124 MPs is a **median of four claims each**. Eleven MPs have
ten or more. You cannot rank 133 people on four observations apiece, and the
remaining queue is 25,747 claims — at $3.72 a verdict, about $4,400 and roughly
86 hours of searching to finish, which is twice what scoring the whole of
Calibration cost end to end.

So for its entire time on the card, Veracity showed something else: the model's
own unaided guess, recorded as `prior_score` and marked unverified. On 133 of
133 cards. **2.6% of claims had actually been checked.**

## The honest counter-argument

The guess was not noise. Ordered by what the search later found:

| later verdict | mean guess |
|---|---|
| true | 79.6 |
| partly_true | 60.4 |
| false | 31.8 |

The model's prior ranked the three outcomes correctly, in the right order, with
real separation. That is a genuine point in favour of the guess, and it is
recorded here because it is evidence against the decision we took.

It is not enough, for two reasons. Ordering three *verdict classes* on average
is a much weaker claim than ranking 133 *people* — the per-MP samples are four
claims deep, so the aggregate is dominated by which four claims each MP happened
to make. And the fourth row of that table is the tell: `uncheckable` claims drew
a mean guess of **66.0**. The model was comfortably confident about statements
for which no source exists at all. A guess that cannot tell "true" from
"unknowable" is not a measurement, however well it orders the rest.

## What happens to it

Withheld, not retired — the same disposition as [Divination](divination-nine-predictions).
The prompts, the falsification criteria, the 657 verdicts and the resolver all
stay. Every claim extracted still carries the criterion that would settle it, so
the queue keeps its value and the work resumes when there is a budget for it.

The card slot went to **Calibration**, which asks whether a member was as certain
as their claim allowed. It covers the adjacent ground — the 24% that are
overstated rather than false — from 43,285 statements scored directly, at a sixth
of the cost of finishing this.

What the cards no longer claim is anything about an individual MP's
truthfulness. That is a real narrowing and it should be read as one.
