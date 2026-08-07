# Labelling guide

Rubrics for the columns in `pool_v3.csv`. These track `ATTRIBUTES.md`; if the two ever disagree, that file is right.

**Leave a cell blank rather than guessing.** Blank means "can't tell" and is skipped. A guessed 0.5 becomes a gold label the model is then measured against.

## subject

```
Whose conduct does this statement let you judge?

  speaker  the statement is about the speaker's own conduct/record
  other    the speaker is describing SOMEONE ELSE's conduct
           (an opponent's broken promise, a previous government's failure)
  unclear  genuinely ambiguous

This is the single most important column. Scoring an MP down for pointing out
an opponent's failure is the defect v3.0 exists to fix, and it has no testset.
Not a score — use the words.
```

## civility

```
Is the attack on the argument, or on the person?

  1.0   Civil. Engages the substance, attacks no one.
        THIS IS THE STANDARD, NOT AN ACHIEVEMENT.
        Harsh criticism of a POLICY belongs here — near 1.0.
  0.75  Pointed, edging toward the person but not landing on them.
  0.5   A real failure: imputing bad faith, sneering, mockery.
  0.25  A clear personal attack.
  0.0   Contempt — sustained abuse, attacks on character or worth.

RE-ANCHORED 2026-08-07. The old scale put "harsh but legitimate criticism" at
0.5; it is now near 1.0. Do not label from the old rubric.

NOT civility: a false claim (veracity), a fallacy (rigor), an attack on a
PARTY rather than a person (focus).
Ineligible: ceremonial speech — tributes and condolences are trivially civil.
```

## rigor

```
Does the conclusion follow from the premises?

  1.0  Valid inference; the conclusion is supported by what was offered.
  0.5  A reasonable point leaning on an appeal, or with a gap in the logic.
  0.0  Non-sequitur, strawman, false dichotomy, slippery slope, circular
       reasoning, or a bare appeal to emotion/popularity/tradition/authority.

WE ARE NOT FACT-CHECKING. An argument can be perfectly rigorous and built on
FALSE premises — that scores HIGH on rigor and low on veracity. Whether the
assumptions are true is not this column's job.

Ad hominem counts against rigor ONLY when the conclusion rests on it.
  "the policy fails because the member is a fool"        -> low rigor
  "the member is a fool, and the policy fails because X" -> rude, not illogical
Ineligible: statements advancing no argument at all.
```

## specificity

```
Is there checkable content in the statement?

  1.0  Concrete: figures, mechanisms, timeframes, named policies.
  0.5  A direction with some detail, missing the how / how much / by when.
  0.0  Platitude or slogan committing to nothing.

Judge in context — credit detail the speaker actually supplied nearby.
NOT specificity: whether the content is true (veracity), whether it answers a
question (forthrightness).
```

## focus

```
Is this about the policy, or about the other team?

  1.0  Engages the substance: mechanism, cost, effect, who it hits.
  1.0  ALSO legitimate scrutiny — "the government promised 1,000 homes and
       built 200" names a specific policy and outcome. THIS IS THE JOB.
  0.5  A real policy point wrapped in party framing.
  0.0  Purely about the other party — their record in general, their
       hypocrisy, their internal divisions. No policy content.

New in v3.0, replacing Charisma. The gap it fills: attacking a PARTY rather
than a person passes civility cleanly but is pure tribalism.
The deciding test: does it name a specific policy, measure or outcome?
Ineligible: ceremony, procedure, debate with no policy at issue.
```

## Columns deliberately absent

`forthrightness` needs a question/answer pair, not a statement. `strength` and `authenticity` are computed from the legislative record. `veracity` and `divination` are resolved by search against sources. Labelling any of them by eye here would not evaluate how they are actually scored.
