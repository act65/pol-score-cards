# Licence and terms of use — the data

Three different things live in this repository and they are not under the same
terms.

| | what | terms |
|---|---|---|
| **The code** | everything in `data/`, `attribute-extraction/`, `site/`, `game/` | **GPL-3.0** — see `LICENSE` |
| **The source material** | the Hansard transcripts the scores are derived from | **no copyright** — see below |
| **The derived dataset** | the scores, the selected statements, the model's explanations, the per-MP aggregates | **CC BY 4.0** |

## The source material is not copyrighted

Section 27(1) of the **Copyright Act 1994** lists material in which no copyright
exists, and **debates in the New Zealand Parliament** are on that list. Hansard
is the verbatim record of those debates. So the transcripts underlying every
score here are free to reproduce, without permission and without attribution.

That is a fact about the source, not about this dataset.

## The derived dataset — CC BY 4.0

The part that is ours is the derivation: which statements were selected, what
each was scored, the written explanation attached to it, and the aggregates
built from them. That is released under
[**Creative Commons Attribution 4.0 International**](https://creativecommons.org/licenses/by/4.0/).

You may share and adapt it, including commercially. You must give appropriate
credit and indicate if changes were made. Suggested attribution:

> NZ Politician Scorecards, https://github.com/act65/pol-score-cards — CC BY 4.0

## What you are agreeing to understand

CC BY carries no warranty, and this dataset needs three warnings that a licence
alone does not give. They are not extra legal conditions — they are the
conditions under which the data means anything.

**1. These are automated estimates, not findings.** Every score is produced by a
large language model reading a transcript. The model is wrong some of the time,
in ways that are not evenly distributed. At the time of writing the accuracy of
the instrument **has not been measured against human labels** — that evaluation
is unfinished. Anyone republishing a number from here should say that.

**2. They are about named real people.** A low score is a claim about how an
identifiable politician conducts themselves in public office. It is derived only
from what they said on the parliamentary record, in their public role, and
nothing here touches private life. Presenting a score as an established fact
about a person — rather than as an automated estimate with its evidence
attached — misrepresents it, and the evidence is included precisely so that it
does not have to be taken on trust.

**3. The scales are versioned and not comparable across versions.** Civility was
re-anchored in v3.0, an attribute was cut and another added. A v2.0 number and a
v3.0 number are different measurements. Say which you used.

## What is not here

`prior_score` — the model's unaided guess before any evidence was searched — is
kept in a separate field from `score` on purpose, so that a guess can never be
published as a resolved answer. Verdicts of `uncheckable` or `not_yet_due`
produce **no score at all**, because absence of evidence is not evidence of
falsity. If you are aggregating this data, preserve that distinction; mapping
either to zero marks every hard-to-check claim as a lie.

## Portraits

MP portraits are Commons-licensed Wikipedia images, stylized. They are **not**
covered by the CC BY 4.0 grant above — each carries its own licence and
attribution, recorded in `site/static/img/portraits/CREDITS.md`.

## Corrections

If a quote is misattributed or a score is indefensible on its own evidence,
please open an issue. Getting it wrong about a named person is the failure mode
this project cares most about.
