# site_data_v3 — the v3.0 site dataset

**Six published attributes:** Veracity, Divination, Focus, Civility, Rigor,
Specificity. Charisma is RETIRED, Strength and Authenticity DEFERRED to v4, and
**Forthrightness is WITHHELD** — still extracted and measured, but not shown on
a card (see `attributes.WITHHELD`, and the section below).

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

## Coverage as built (5,300 of 5,548 windows)

| attribute | MPs | | distinct | unverified |
|---|---:|---|---:|---:|
| Veracity | 133 | 100% | 17 | 133 |
| Divination | 127 | 95% | 16 | 127 |
| Focus | 132 | 99% | 45 | 0 |
| Rigor | 132 | 99% | 29 | 0 |
| Specificity | 132 | 99% | 33 | 0 |
| Civility | 131 | 98% | 37 | 0 |

132 of 133 MPs reach the grid. No attribute's government/opposition gap exceeds
16 points, and four of the six are within 6.

## Why Forthrightness is withheld and Divination is not

Swapped on 2026-09-25, after the `/party` page made both errors visible.

**Forthrightness had a 44-point government/opposition gap.** Two causes, and
only the second decides it. The first is a pairing bug: 43 of the 74 scored MPs
rest on ≤10 Q/A pairs and average 24, against 67 for the 31 with real volume,
and in those thin rows the "answer" attributed to the MP is the MP's own next
supplementary question — `asked_by` is the same person. The second is
structural: **only the executive answers oral questions.** Of the 31 MPs with a
usable sample, 31 are government — National 22, ACT 5, NZ First 4, and not one
opposition MP. Fixing the pairing cannot change that, so on a 133-card grid the
attribute is a proxy for which benches you sit on. It stays extracted because it
is a good measure *of ministers*; see `V3_TODO.md` Phase D0.

**Divination was withheld the day before on a bad number.** "29 MPs, all sharing
one score" was the *resolved-only* count. With `--use_prior` it reaches 127 of
133 MPs at a median of 10 predictions each, its bench gap is −1, and its mean
|r| against the other five is 0.17 — the most independent attribute of the
seven, where Forthrightness's apparent independence (−0.50 with Focus) was
mostly the bench artefact above.

## `politicians.jsonl` now carries a role

`build_v2_dataset.py` joins `data/leadership.json` (hand-written, dated, sourced
— see its `_note`) so each row can carry `leadership` (`leader` / `minister`),
`role` and `portfolio`. 37 of the 133 MPs have one; the site's "Role" filter and
nothing else reads them. The two entries that do NOT appear are the Speaker and
the Deputy Speaker, who chair rather than debate and so never reach the minimum
scored attributes — the expected gap, not a join failure.

## Two of the six are the model's own estimates

`--use_prior True` is what gives Veracity and Divination any coverage at all:
without it, Veracity had one distinct value (79) across 70 MPs and Divination
one (62) across 29, because the resolved evidence is a median n of 3 and 1 and
`bias_adjust` shrank it all onto the prior.

The cost is that 133 Veracity and 127 Divination scores are `prior_score`, not a
checked source. On 312 resolved claims that guess has MAE 0.22 against the
evidence and is confidently wrong 6% of the time, so the card marks every one
with a superscript `?`, a dimmed value and an UNVERIFIED tooltip — and the
`/party` aggregate carries the same mark, because averaging a guess over a
caucus does not check it. Do not publish without either resolving them or
keeping that marking.
