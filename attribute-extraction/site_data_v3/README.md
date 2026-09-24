# site_data_v3 — the v3.0 site dataset

**Six published attributes:** Forthrightness, Veracity, Focus, Civility, Rigor,
Specificity. Charisma is RETIRED, Strength and Authenticity DEFERRED to v4, and
Divination is WITHHELD — still extracted and measured, but not shown on a card
until the resolver has scored it (see `attributes.WITHHELD`).

Built with:

    cd attribute-extraction
    python build_v2_dataset.py \
        --scores hansard_scores_v3.jsonl \
        --qa_scores forthrightness_scores_v3.jsonl \
        --resolved resolved_v3.jsonl \
        --use_prior True \
        --out site_data_v3 \
        --corpus_label "Hansard 54th Parliament v3.0"

NOTE there is no `run` subcommand — the file ends in `fire.Fire(run)`, so a
leading `run` binds positionally to `--scores` and fails 300 lines later with a
confusing `'<' not supported between instances of 'int' and 'str'`.

Preview it without touching the published v2.0 data in `site/static/`:

    cd site && SCORECARD_DATA=../attribute-extraction/site_data_v3 python app.py

## `--use_prior True` is doing real work here

Without it, every one of the 70 MPs with a Veracity score had the SAME score
(79), because 276 resolved veracity claims over 132 MPs is a median evidence n
of 3 and `bias_adjust` shrank them all onto the prior. The column carried no
information. With the guesses in: 100% coverage, 17 distinct values.

The cost is that 132 of the 133 Veracity scores are the model's unaided
`prior_score`, not a checked source. On 312 resolved claims that guess has
MAE 0.22 against the evidence and is confidently wrong 6% of the time, so the
card marks every one of them with a superscript `?`, a dimmed value and an
UNVERIFIED tooltip. Do not publish this publicly without either resolving them
or keeping that marking.

## Coverage as built (5,300 of 5,548 windows)

| attribute | MPs | | distinct scores |
|---|---:|---|---:|
| Veracity | 133 | 100% | 17 |
| Focus | 132 | 99% | 45 |
| Rigor | 132 | 99% | 29 |
| Specificity | 132 | 99% | 33 |
| Civility | 131 | 98% | 37 |
| Forthrightness | 74 | 56% | 35 |

132 of 133 MPs reach the grid. Forthrightness needs question/answer pairs where
the MP is the *responder*, so it covers ministers and spokespeople rather than
the whole House — a coverage gap, not redundancy: its card-level correlations
are the most independent of the six (-0.50 with Focus, -0.42 with Specificity,
0.02 with Civility).

## What is committed here

`scores.jsonl`, `politicians.jsonl`, `attributes.jsonl` — small, and the useful
artefact to diff between builds. `examples.jsonl` is NOT committed: 48 MB, and
regenerable in ~2 minutes by the command above from inputs already tracked. The
site preview needs it, so run the build once after checkout.

## `politicians.jsonl` now carries a role

`build_v2_dataset.py` joins `data/leadership.json` (hand-written, dated, sourced
— see its `_note`) so each row can carry `leadership` (`leader` / `minister`),
`role` and `portfolio`. 37 of the 133 MPs have one; the site's "Role" filter and
nothing else reads them. The two entries that do NOT appear are the Speaker and
the Deputy Speaker, who chair rather than debate and so never reach the minimum
scored attributes — the expected gap, not a join failure.

## A defect this build made visible

The `/party` page shows Forthrightness at 62 for government caucuses and 19 for
opposition ones. That is not a finding — it is a Q/A pairing bug. 43 of the 74
scored MPs rest on ≤10 pairs and average 24, against 67 for the 31 with real
volume, and in those thin rows the "answer" is the MP's own next supplementary
question. See the Phase D0 entry in `V3_TODO.md`. Treat every thin
Forthrightness score in this build as unusable.

## One mislabel left to fix

`Forthrightness_tier` says `text`. It is `record` — scored over question/answer
pairs, not speech windows. Nothing reads it yet except the unverified marker,
which keys off `unresolved`, so this is cosmetic for now.
