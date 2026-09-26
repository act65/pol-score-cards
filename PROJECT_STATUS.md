# Project status

Honest status of the four deliverables. **Updated 2026-09-26.**

This file is deliberately short. `CLAUDE.md` is how to work in the repo,
`V3_TODO.md` is the ordered backlog, `ATTRIBUTES.md` is the attribute contract.
This is just: what works, what does not, and what is not yet true.

---

## 1. Tools — ✅ working

Scrapers (`data/scrapers/sources.py`, one date-windowed driver over 10 sources),
extraction (`attribute-extraction/extract_hansard.py`, Opus via the subscription
CLI with a hard verbatim-quote gate), bias adjustment (`bias_adjust.py`,
empirical-Bayes shrinkage), and the bundler (`build_v2_dataset.py`).

**455 tests pass in ~40s** (`pytest` from the root covers all four subprojects).

Two deterministic instrument audits gate any prompt change:
`attribute_overlap.py` and `check_quotes.py`.

## 2. Dataset — ◐ complete for the term as scraped, not yet to the election

- **82,569 scored statements**, **133 MPs**, **183 sitting days**, 5,548 windows.
- Coverage runs to **2026-05-28**. June → the November election is **not yet
  scraped**, let alone scored. This is the single biggest gap.
- **Quote audit: 100% verbatim**, 0% spliced, 0% not-found, on an 800-statement
  sample across all six attributes. The extractor drops any quote that is not
  verbatim in its source window before it reaches disk.
- **Six attributes published**: Veracity, Divination, Focus, Civility, Rigor,
  Specificity. Forthrightness is **withheld** (only the executive answers oral
  questions, so it reads as a government bonus); Strength and Authenticity are
  deferred to v4; Charisma is retired (r=0.96 with Civility).

## 3. Accuracy — ✗ **not established**

This is the honest gap, and it gates every claim the project makes.

- The **120-statement evaluation pool has 0 labels**. Until it is labelled there
  is no measured accuracy for the v3.0 instrument. The v2.0 figures that used to
  sit here (civility r=0.88, veracity r=0.73) were a **different instrument** —
  Civility was re-anchored, so they do not carry over.
- **262 of 790 published scores are still `unresolved`** — Veracity and
  Divination shown from the model's unaided `prior_score`, marked with a `?` on
  the card. The resolver has settled 878 claims so far and is still running.

Nothing on the site or in `DATA_LICENCE.md` claims otherwise, and that should
stay true until the labelling is done.

## 4. Site — ✅ live, published as static files

133 cards, a page per MP, a page per (MP × attribute) with every statement
behind the score, a page per party, a rubric page per attribute, and a dataset
page. **933 pages**, built by `site/freeze.py` in ~4s and deployed to GitHub
Pages by CI — see `DEPLOY.md`. Every score links to its quote and its sitting
day; that is the feature the project stands on.

## 5. Game — ◐ prototype, deliberately behind

A playable local Flask prototype, running on the **retired v2.0 attributes** and
a fake deck. The canonical rules are the site's `/rules`. Treated as a separate
project; see `game/README.md`.

---

## What would change the status

1. **Label the 120-statement pool** (`label_testset.py`) — unblocks every
   accuracy claim. Needs a human, not an agent.
2. **Scrape and score June → election** — closes the coverage gap.
3. **Finish the resolver over Veracity/Divination** — clears the 262 `?` marks.
4. **Fix the Q/A pairing bug**, then reconsider Forthrightness as an explicitly
   executive-only measure (`V3_TODO.md` Phase D0).
