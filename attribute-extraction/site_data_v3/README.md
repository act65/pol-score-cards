# site_data_v3 — the v3.0 site dataset

Seven attributes (Charisma absent, Focus in its place); Strength and
Authenticity deferred to v4. Built from the v3 extraction with:

    cd attribute-extraction
    python build_v2_dataset.py \
        --scores hansard_scores_v3.jsonl \
        --qa_scores forthrightness_scores_v3.jsonl \
        --resolved resolved_v3.jsonl \
        --out site_data_v3 \
        --corpus_label "Hansard 54th Parliament v3.0"

NOTE there is no `run` subcommand — the file ends in `fire.Fire(run)`, so a
leading `run` binds positionally to `--scores` and fails later with a confusing
`'<' not supported between instances of 'int' and 'str'`.

Preview it without touching the published data in `site/static/`:

    cd site && SCORECARD_DATA=../attribute-extraction/site_data_v3 python app.py

## What is committed here

`scores.jsonl`, `politicians.jsonl`, `attributes.jsonl` — small, and the useful
artefact to diff between builds.

`examples.jsonl` is NOT committed: 49 MB, and regenerable in ~2 minutes by the
command above from inputs that are already tracked. The site preview needs it,
so run the build once after checkout.

## Coverage as built (5,300 of 5,548 windows)

| attribute | MPs with a score | |
|---|---:|---|
| Focus | 132 | 100% |
| Rigor | 132 | 100% |
| Specificity | 132 | 100% |
| Civility | 131 | 99% |
| Forthrightness | 74 | 56% — needs Q/A pairs, so ministers mostly |
| Veracity | 70 | 53% — from 389 resolved claims only |
| Divination | 29 | 22% — from 389 resolved claims only |

Veracity and Divination are built with `use_prior=False`, so a score here comes
from a searched verdict, never from the model's guess.

## Two mislabels to fix before this is shown to anyone

1. `Forthrightness_tier` says `text`. It is `record` — scored over question/
   answer pairs, not speech windows.
2. `Veracity_tier` / `Divination_tier` say `unresolved` for every row, including
   rows that came from a resolved verdict. With `use_prior=False` the opposite
   is true: every score present IS resolved. The label errs on the cautious
   side, but it is still wrong.
