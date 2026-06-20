# NZ Politician Scorecards — project overview

*A data-driven, evidence-linked way to hold New Zealand politicians accountable
for how they conduct themselves — not what they believe.*

**Live demo: <https://nz-politician-scorecards.onrender.com/>**
*(free hosting — the first visit after a quiet period may take ~30s to wake up.)*

## The problem

Politicians make promises, predictions, and claims with little systematic
accountability. Fact-checks are one-off and quickly forgotten; there is no
running, public record of *how* a politician conducts themselves over time —
whether they answer the question, argue in good faith, keep their promises, or
mislead.

## What we've built (working prototype)

A platform that scores NZ politicians on **nine conduct attributes** (e.g.
Civility, Veracity, Rigour, Specificity, Forthrightness) and — crucially —
**links every score to the exact statements behind it**, so anyone can click
through and judge the evidence themselves.

- **~85 politicians** scored from **real, scraped public statements**: party
  press releases, RNZ political reporting, Beehive releases, and **Hansard** (the
  verbatim parliamentary record).
- **~1,350 individual scored statements**, each kept with its quote, context, and
  the reasoning for the score.
- Scores are produced by a large language model (Claude) against a fixed,
  politically-neutral rubric, and measured against **held-out, human-labelled
  test sets** (e.g. civility rank-correlation ≈0.88 on the current set).
- A public website (filter/sort by party, attribute, rarity) and an
  accompanying card game.

## We are honest about the limits

This is a prototype. Accuracy varies by attribute: conduct attributes judgeable
from text (civility, specificity) score reliably; attributes that need external
verification (veracity, kept-promises) currently reflect *plausibility*, not
fact-checked truth. Scores are **automated estimates, not verdicts**, and the
evidence is always one click away. We treat this transparency as essential.

## Where it needs to go (the principled, scaled version)

To be genuinely useful — ideally **ready for the November 2026 election** — three
things need investment:

1. **Scale**: more politicians, more sources (all major outlets), and a deeper
   time window — years of statements, not months.
2. **Principled methodology**: measure and correct sampling/selection bias;
   normalise for source mix; surface sample sizes and confidence.
3. **Real accountability for promises & predictions**: a verified, longitudinal
   **claims ledger** — track every promise/prediction and whether it actually
   came true, with human review and evidence, rather than an LLM guess.

## What we're looking for

- **Funding**, primarily to cover LLM inference at scale (the main running cost).
- **Collaboration** — especially with a newsroom/data desk or researchers — on
  methodology and editorial standards.

## Try it

**Live: <https://nz-politician-scorecards.onrender.com/>** — click any score to see
the statements behind it. The site also runs locally in two commands on committed
data (no API key needed); source, methodology, and evaluation are all open.

*Contact: [your name / email here]*
