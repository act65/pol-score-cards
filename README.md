# NZ Politician Scorecards

## Overview

This project aims to create a data-driven platform for assessing the performance and accountability of New Zealand politicians. Inspired by fantasy and D\&D game mechanics, each politician will have a card displaying metrics / attributes related to their political behaviour.

The goal is to (help) make politicians more accountable for their actions by providing the public with data-backed insights into their conduct.

## Key parts

* A website to display the cards
    *  Individual cards for each NZ politician displaying their scores across various attributes.
    * Each attibute will allow users to view examples (quotes, citations) that contributed to a politician's score. Ability to explore our database.
* Build a database of examples
    * Need scrapers to collect data from news sources, Hansard, more... to build the database. Already a few implemented in `data/scrapers`
    * Need a database to host the data.
* LLM Powered Data Extraction: Utilizing Large Language Models to automatically extract data for each score from the identified sources.
    * Filter the raw scraped data (using LLMs) for comments related to our attributes
    * Use LLMs to classify. More details on how in `attribute-extraction/README.md` 
    * Evaluation of accuracy using test sets
* A card game based on the cards.
    * See `game/rules.md` for more info.
    * Game is currently playable as a 1-player game using `python app.py`.

## Attributes

Each attribute asks **one question** and is required to ignore the others. Where
two would penalise the same thing, exactly one owns it — see `ATTRIBUTES.md` for
the full contract, the ownership ledger, and the eligibility gates.

| Attribute | The one question | How it is scored |
|---|---|---|
| **Forthrightness** | Did the answer address the question that was asked? | Over question/answer **pairs** from Hansard oral questions and written PQs. A blunt, vague, even false answer that squarely addresses the question scores high. |
| **Strength** | What did this politician commit to? | Joined to the legislative record — bills in charge, ballot bills, amendment papers, resolved promises. No lever means *not applicable*, never zero. |
| **Veracity** | Are the factual premises accurate? | Extracted with a falsification criterion, then resolved against sources. Not "does this look well-evidenced" — that is Rigor. |
| **Authenticity** | What position did this politician state? | Joined to the division record: did the vote match the words? Party-level, so an MP may personally disagree with a vote they were counted in. |
| **Divination** | Did the prediction come true? | Extracted with a criterion and a resolve-by date, then resolved against what happened. Not "was it plausible at the time". |
| **Focus** | Is this about the policy, or about the other team? | Naming a specific policy, measure or outcome separates accountability from tribalism. Scrutiny of a named government failure scores **high** — that is the job. |
| **Civility** | Is the attack on the argument, or on the person? | 1.0 is the expected standard. Fierce criticism of a *policy* is civil; turning on the person is not. |
| **Rigor** | Does the conclusion follow from the premises? | Validity, not truth. An argument can be perfectly rigorous and built on false premises — high Rigor, low Veracity. |
| **Specificity** | Is there checkable content in the statement? | Figures, mechanisms, timeframes, named policies. A precise but false claim still scores high here. |

All are oriented so **higher is better** (see `design-decisions.md`).

**Six of these are published on the cards** (`attributes.PUBLISHED`): Veracity,
Divination, Focus, Civility, Rigor, Specificity. The other three are measured
but not shown, for three different reasons:

> **Charisma was cut on 2026-08-07.** It correlated with Civility at r=0.96 —
> one insult counted twice, then compounded by the geometric mean used for card
> rank. **Focus** replaced it, covering the gap Civility leaves: attacking a
> *party* rather than a *person* passes Civility cleanly but is pure tribalism.
> Measurements in `attribute-extraction/ATTRIBUTE_OVERLAP.md`.

> **Strength and Authenticity are DEFERRED to v4.** Both need the voting, bill
> and promise records joined properly, and both currently file a low score under
> the *speaker* even when the statement describes someone else's broken promise —
> which penalises MPs for scrutinising opponents. See `data/VOTES.md`.

> **Forthrightness is WITHHELD since 2026-09-25.** It is scored over Q/A pairs,
> and in the House only ministers answer questions: of the 31 MPs with enough
> evidence to score, all 31 sat on the government benches. It cannot be compared
> across a Parliament, so it is not published — but it keeps being extracted,
> because it is a good measure *of the executive*. See the decisions log in
> `ATTRIBUTES.md`.

For the full rubrics see `attribute-extraction/prompts/`; for why each attribute
is drawn where it is, `ATTRIBUTES.md`.

## Status (June 2026)

A working MVP. The site runs on **real data**: ~85 NZ politicians scored from
scraped party press releases, RNZ political reporting, Beehive releases, and
Hansard, with every score linked to the statements behind it. Accuracy is
measured against held-out test sets and **varies by attribute** — some scores are
reliable, some are LLM estimates of plausibility (see `attribute-extraction/EVALUATION.md`
and the site's About page). It is a research/accountability prototype, not a
finished product.

## Quickstart — see the demo (no API key, no scraping)

The site and game ship with committed data, so you can run them immediately:

```bash
git clone <repository_url> && cd pol-score-cards

# The public site (the main demo) — reads committed site/static/*.jsonl
pip install -r site/requirements.txt
cd site && python app.py          # -> http://127.0.0.1:5000/

# The card game (run from a fresh shell; both default to port 5000)
pip install -r game/requirements.txt
cd game && python app.py          # -> http://127.0.0.1:5000/
```

That's it for the demo — neither needs an API key or any scraping.

## Regenerating the data (advanced)

Only needed if you want to scrape fresh statements or re-score. Two stages:

```bash
# 1. Scrape (free, just HTTP). From data/ — see data/LIVE_FETCH.md for all sources.
cd data && pip install -r requirements.txt
python scrapers/... / python sources.py scrape --source greens --months 3 --out data/greens.json

# 2. Extract attribute scores with an LLM (from attribute-extraction/).
cd attribute-extraction && pip install -r requirements.txt
python build_site_data.py build --articles "../data/data/<file>.json" --merge
```

**Which LLM backend?** Extraction defaults to `--backend claude_cli`, which uses
your local `claude` CLI login (a Claude subscription, no API credits). To use the
Anthropic API instead, copy `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, and
pass `--backend anthropic`. See `attribute-extraction/README.md` for details, and
`data/HANSARD_HOWTO.md` for the browser-based scrapers.

## Tests

```bash
cd game && pytest                              # game engine
cd attribute-extraction && pytest test_evaluate.py   # scoring metrics (no key needed)
cd data/scrapers && pytest                     # scraper parsing
```
