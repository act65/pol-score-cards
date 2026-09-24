# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NZ Politician Scorecards — a data-driven platform that scores New Zealand politicians on nine D&D-style attributes (Forthrightness, Strength, Veracity, Authenticity, Divination, Charisma, Civility, Rigor, Specificity). See `README.md` for the attribute definitions and `design-decisions.md` for the rationale (e.g. all attributes are oriented so "higher = better").

## Architecture

The repo is **four loosely-coupled subprojects** that communicate via JSON/JSONL files on disk, not via imports. There is no top-level package, no shared dependency file (root `requirements.txt` is empty), and each piece is run independently from inside its own directory.

The intended data pipeline flows left-to-right, but stages are run manually and partially stubbed:

```
data/  ──scrape──▶  raw articles (JSON)  ──▶  attribute-extraction/  ──LLM──▶  scores/examples (JSONL)  ──▶  site/  (Flask display)
                                                                                                            game/  (Flask card game, currently fed by fake data)
```

### `data/` — scrapers
- `scrapers/` holds one module per source (`greens.py`, `national.py`, `rnz.py`, `hansard.py`, `parliament.py`, `labour.py`). Each is a standalone script run as `python scrapers/X.py <output_dir> <N>`.
- `scrapers/utils.py` and `pol_data_utils/utils.py` are two near-duplicate sets of scraping helpers (`get_soup`/`make_request`, text normalization). Be aware both exist.
- `scripts/scrape.py` is a (currently stubbed — `subprocess.Popen` commented out) orchestrator that runs the scrapers listed in its `scrapers` array.
- **Votes, bills & promises** (the evidence base for Strength/Authenticity — all deterministic, no LLM): `parse_divisions.py` recovers 984 party votes from the already-scraped Hansard corpus; `scrapers/bills.py` pulls bills, ballot bills and Amendment Papers from the public `bills.parliament.nz` JSON API; `strength_ledger.py` joins those three into one row per MP; `scrapers/manifestos.py` captures coalition agreements and party platforms (live + Wayback). See **`data/VOTES.md`** — it documents the party-vote caveat (NZ votes are cast per-party, so the signal is mostly party-level), why the Strength ledger writes no score, and the Hansard short-paragraph defect that corrupted early vote data.
- `pol_data_utils` is installable via `data/setup.py`, but the scrapers mostly use `scrapers/utils.py` directly.
- `data/README.md` tracks which sources are implemented (checkboxes).

### `attribute-extraction/` — LLM scoring
- `extract.py` (python-fire CLI) takes raw scraped articles and an attribute, sends each through Claude with the matching prompt, and writes JSONL results. **Uses the Anthropic SDK (`anthropic`, default model `claude-opus-4-8`) with structured outputs** — `messages.parse` against a Pydantic schema, so parsing is reliable. Importable functions: `extract_examples` (find+score statements in an article) and `score_statement` (score one isolated statement; used by the eval harness).
- `prompts/<attribute>.txt` — one prompt per attribute; the `attribute` arg must match a filename here. All nine prompts share one format: attribute definition + 0..1 scoring rubric (higher = better). The per-prompt output JSON is *not* specified there — the structured-output schema (`politician`, `statement`, `score`, `explanation`) handles format uniformly.
- `evaluate.py` — held-out eval harness; scores testset statements with Claude and reports MAE/RMSE/Pearson/binary-accuracy vs gold. Pure metric functions are unit-tested offline in `test_evaluate.py`. See `EVALUATION.md`.
- `testsets/*.jsonl` — evaluation sets. Scoring testsets (`civility_testset`, `veracity_testset`) are wired into `evaluate.py`; detection testsets (`evasion`, `integrity`) are a separate binary task, not yet wired.
- `extract_all.py` is a batch runner over (article file × attribute) pairs.
- The scoring metric convention is `S = 100 * positive / (positive + negative)`. `attribute-extraction/README.md` documents how trustworthy LLM scoring is per attribute (some need human verification).

### `site/` — public Flask website
- `app.py` serves politician cards, per-attribute detail/example pages, a `/party` page (one aggregated scorecard per party) and a `/data` dataset-overview page (size, per-party, per-politician, per-source stats + download placeholders).
- **`/party`** aggregates over the same featured MPs the grid shows. Each attribute is the plain mean of the party's MPs on it; the party's **overall** is the geometric mean of the six numbers printed on its own card (not the average of members' overalls), so the card can be checked against itself. The colour block is a dot plot — one dot per MP at that MP's own overall — which is what the per-party ridgeline on `/data` used to show. A party needs `MIN_PARTY_MPS` (3) featured MPs or it is named under the table instead of ranked: a one-MP "party" is one MP's card with a party name on it. Unverified and thin-coverage marks propagate to the aggregate — averaging a `prior_score` over a caucus does not resolve it.
- The **overall score** (the geometric mean the cards are ranked by) is shown as a badge in each card's banner, ringed in the rarity colour. It used to be encoded only in the border colour and was nowhere readable.
- Two interchangeable data-access backends: `data_access_jsonl.py` (active, reads `static/*.jsonl`) and `data_access_sqlite.py` (stubbed/incomplete). `app.py` imports the jsonl one.
- Display data lives in `static/`: `politicians.jsonl`, `attributes.jsonl`, `scores.jsonl`, `examples.jsonl`. The `/data` page reads a precomputed `static/dataset_stats.json` (regenerate with `python gen_data_stats.py`).
- MP portraits: `data/scrape_portraits.py` fetches Commons-licensed Wikipedia infobox photos into `static/img/portraits/orig/<id>.jpg`, then `data/stylize_portraits.py` face-frames (whole face centred, no chin clipped), cuts the background with rembg (U²-Net) to clean white, and renders a **pure-greyscale** stylization to `static/img/portraits/<id>.jpg` (the served image; originals kept so you can re-stylize without re-scraping; masks cached in `masks/`). `app.py` resolves portraits by convention (no `image` field needed in the dataset); cards fall back to an initials monogram.
  - Current default style **`lineart`** — an ML pencil-style line drawing (Informative Drawings, via `controlnet_aux` LineartDetector) that preserves likeness far better than tonal filters. Other styles: `lineart_coarse` (fewer/bolder ML lines), and the classical `posterize|vector|posterline|sketch|woodcut|wireframe|pencil|notan|ink`. Switch with `--style <name>`. `lineart` runs the model per-image (~2 min for 133 on CPU); the classical styles are ~15s.
  - The stylize pipeline runs in an **isolated venv** `data/.venv-portraits` (gitignored) — rembg/torch/controlnet_aux need numpy≥2 etc. which conflict with the repo's other tools, so they're kept out of the global env. Recreate with `python -m venv data/.venv-portraits && data/.venv-portraits/bin/pip install -r data/requirements-portraits.txt`, then run `data/.venv-portraits/bin/python stylize_portraits.py --style <style>`. Model weights (rembg u2net, lineart) download to `~/.u2net` / the HF cache on first run.
- Card design is the shared 5:7 minimal trading card in `shared/card.css` (rarity = outer border colour, pure-greyscale sketch portrait, no party tint); edit there and run `python shared/sync.py` to copy into `site/` and `game/`.

### `game/` — Flask card game
- A 1-player (human vs AI) browser card game. `game_logic.py` is the pure, dependency-light engine; `app.py` is the Flask layer exposing `/api/start_game` and `/api/submit_round_actions`, with the UI in `templates/index.html` + `static/script.js`.
- `game_logic.py` is the core to read: dataclasses `GameConfig`, `Attributes`, `PoliticianCard`, `PlayerState`, `GameState`, and the `GameEngine`. Each attribute maps to a combat mechanic (e.g. Strength → HP & base damage, Rigor → attack multiplier, Veracity → defense multiplier, Divination → turn order). The full mapping is in `game/rules.md`.
- `politicians.jsonl` is the card deck; `generate_fake_data.py` produces fake cards for it. The game does not yet consume real scores from `site/`.

## Common commands

Each app uses **relative paths** and must be run from its own directory.

```bash
# Public site (reads site/static/*.jsonl)
cd site && python app.py            # http://127.0.0.1:5000/

# Card game
cd game && python app.py            # http://127.0.0.1:5000/

# Game tests (the only test suite in the repo)
cd game && pytest test_logic.py
cd game && pytest test_logic.py::test_name        # single test
cd game && python generate_fake_data.py           # regenerate the card deck

# LLM attribute extraction (run from attribute-extraction/ — prompts/testsets read relatively)
#
# BACKENDS — these are not interchangeable, and one of them costs money:
#   --backend claude_cli  runs `claude -p` against the user's SUBSCRIPTION. No
#                         API credits. This is the default for every real run.
#                         Throughput is the constraint: keep --workers at 1-2,
#                         because past ~2 concurrent CLI sessions the calls
#                         queue behind each other and a batch appears to hang.
#   --backend anthropic   uses the paid Anthropic API. Real dollars — the
#                         full-term dry run estimates ~$295. Do not use it
#                         without the user explicitly asking.
cd attribute-extraction
pip install -r requirements.txt && export ANTHROPIC_API_KEY=...
python extract.py extract_file ../data/data/<articles>.json specificity out.jsonl
python extract_all.py "../data/data/*.json" all ./out      # batch
python evaluate.py run all                                  # eval (writes eval_report.json)
python -m pytest test_evaluate.py                           # offline metric tests (no key)

# Label the evaluation pool (see attribute-extraction/label_testset.py)
# Only 5 columns are asked for: subject, civility, rigor, specificity, focus.
# The other four are scored from records or by search, so a by-eye label there
# would not evaluate how they actually work.
cd attribute-extraction && python label_testset.py guide                # rubrics
cd attribute-extraction && python label_testset.py export --split dev   # -> testsets/pool_v3.csv + _GUIDE.md
cd attribute-extraction && python label_testset.py import_csv --by <name>
cd attribute-extraction && python label_testset.py status

# Instrument audits — deterministic, no key; gate every prompt change on these
cd attribute-extraction && python attribute_overlap.py run --out ATTRIBUTE_OVERLAP.md
cd attribute-extraction && python check_quotes.py run --n 2000 --out QUOTE_AUDIT.md

# v3.0 extraction (spends quota). ALWAYS --dry_run first; ALWAYS pilot before full.
cd attribute-extraction
python extract_hansard.py --dry_run --since 2025-10-01 --until 2025-10   #  51 windows
python extract_hansard.py --dry_run                                      # 1127 windows (full term)
python overnight_run.py run --hours 10 --stage pilot      # 2025-10 only — start here
python overnight_run.py run --hours 10 --stage windows    # full term
python overnight_run.py run --hours 6  --stage questions  # Forthrightness over Q/A pairs
python overnight_run.py status                            # progress, spends nothing

# The scheduler runs under systemd so a crash or reboot cannot silently lose a
# night (two were lost that way on 2026-09-04). Unit kept in the repo at
# attribute-extraction/nz-scorecards-nightly.service.
systemctl --user status nz-scorecards-nightly             # is tonight armed?
systemctl --user disable --now nz-scorecards-nightly      # stop scheduling

# A ceiling we put on OURSELVES so the night cannot take the whole rolling
# window — the real cap is readable from nowhere and is shared with daytime
# interactive sessions. Edit the dollars in quota_budget.json.
python quota_budget.py status        # spend per window vs cap; spends nothing
python quota_budget.py calibrate     # the real ceiling, measured from history

# Forthrightness is scored over question/answer PAIRS, not speech windows
python extract_questions.py run --dry_run --source oral      #   924 calls
python extract_questions.py run --dry_run --source written   # 7,097 calls — opt-in only

# Both v3.0 experiments, overnight, sequential, resumable (subscription only)
nohup python run_experiments.py run --hours 14 > experiments.log 2>&1 &
python run_experiments.py status          # progress; spends nothing

# Model bake-off — Opus 5 is the reference; can a cheaper model reproduce it?
python compare_models.py run --windows 3 --repeats 2 --workers 2 --backend claude_cli
python compare_models.py report --out MODEL_COMPARISON.md

# Resolver — searches for evidence to score veracity/divination (needs the CLI,
# which has WebSearch; the API backend has no browser). Also answers "is
# searching worth it?" by comparing against the model's unaided prior_score.
python resolve.py run --scores hansard_scores_v3.jsonl --limit 40
python resolve.py compare --out GUESS_VS_SEARCH.md

# Dataset stats / coverage (run from data/, no key needed)
cd data && python dataset_stats.py --out=DATASET_STATS.md       # per-source summary
cd data && python corpus_report.py --out=CORPUS_REPORT.md       # per-politician coverage (uses mps_roster.json)

# Votes, bills, promises (all deterministic, no LLM/API key — see data/VOTES.md)
cd data && python parse_divisions.py run              # Hansard corpus -> corpus/divisions.jsonl
cd data && python parse_divisions.py stats            # summary only, writes nothing
cd data/scrapers && python bills.py fetch             # -> ../corpus/bills.jsonl (~10 min)
cd data/scrapers && python bills.py fetch_proposed    # -> ../corpus/proposed_bills.jsonl (ballot bills)
cd data/scrapers && python bills.py fetch_amendments  # -> ../corpus/amendment_papers.jsonl
cd data && python strength_ledger.py run              # joins the 3 -> corpus/strength_ledger.jsonl
cd data && python parse_questions.py run              # oral Q/A pairs -> corpus/oral_questions.jsonl
cd data && python build_propositions.py run           # -> corpus/propositions.jsonl (Authenticity join key)
cd data/scrapers && python written_questions.py fetch # -> ../corpus/written_questions.jsonl (Forthrightness)
cd data/scrapers && python manifestos.py fetch        # -> ../corpus/manifestos.jsonl (promise side)
# Re-scrape Hansard with the fixed short-paragraph parser (~3-5 h, resumable):
cd data/scrapers && python rescrape_hansard_days.py run --out ../corpus/hansard_v2.json
# Tests: one command from the repo root covers every suite (see pytest.ini)
pytest                                 # data/tests + attribute-extraction/tests + site/tests + game
cd data && pytest tests                # or per subproject
cd attribute-extraction && pytest tests

# Scraping — unified driver (run from data/scrapers/); --since for the term window
cd data/scrapers && python sources.py scrape --source tpm --since 2023-10-06 --out ../data/tpm.json
# sources: greens national act top tpm labour nzfirst rnz newsroom spinoff parliament
#          (browser-path, need Playwright: labour nzfirst rnz parliament; Hansard via hansard.py)

# Full term backfill + publish (run on a VM with Playwright — see data/CLOUD_SCRAPING.md)
cd data && python scripts/backfill.py --out corpus              # all in-scope sources, 2023-10-06 → 2026-11-07
cd data && python publish_corpus.py --corpus corpus --repo you/nz-pol-statements --push   # → HuggingFace Dataset
```

CLI tools (`extract.py`, `extract_all.py`, `evaluate.py`, `dataset_stats.py`, `scripts/scrape.py`) use [python-fire](https://github.com/google/python-fire) or simple argv, so args map to function parameters. Note `extract.py`/`evaluate.py` expose subcommands (`extract_file`, `run`) — name the subcommand first.

## Notes
- **Repo layout**: tests live in `data/tests/`, `attribute-extraction/tests/` and `site/tests/`, each with a `conftest.py` that puts the sibling modules on the path (site's also sets `SCORECARD_DATA` to an absolute path, since `app.py` reads its dataset at import time) (the pipelines are run as scripts from their own directories, so they import each other by bare name). `pytest.ini` at the root runs everything.
- **`data/leadership.json` is hand-written**, not derived — a dated, sourced snapshot of who held a senior role (party leaders and deputies, the presiding officers, and every ministerial warrant on the 7 April 2026 list). It is a display facet only: `build_v2_dataset.py` joins it into `politicians.jsonl` as `leadership` (`leader`/`minister`), `role` and `portfolio`, and the site's "Role" filter reads those. An MP missing from it is a backbencher, not an error. It is a **snapshot**: roles that changed earlier in the term are recorded in `_changes_in_term` but NOT in `roles`, so a 2023 Labour minister counts as a backbencher. Update `_as_at` and the entries together; `data/tests/test_leadership.py` checks every id against the roster and that no minister sits outside the coalition.
- **`data/names.py` is the single implementation** of politician-name cleaning and roster lookup — honorifics, "Surname, Given" order, "on behalf of" delegation, accent/case folding, and a unique-only fuzzy match for Hansard's misspellings. Six modules used to carry near-copies and the differences between them were bugs. Import `RosterIndex`, `clean`, `norm` from it rather than writing another.
- No CI, linter config, or top-level pinned dependencies (each tool has its own needs). Dependencies by area: extraction — `anthropic`, `pydantic`, `fire` (`attribute-extraction/requirements.txt`); scrapers — `requests`, `beautifulsoup4`, `fire`; apps — `flask`; tests — `pytest`.
- Generated analysis docs: `attribute-extraction/EVALUATION.md` (eval methodology/results, including the open subject-attribution defect in Strength/Authenticity), `attribute-extraction/ATTRIBUTE_OVERLAP.md` + `QUOTE_AUDIT.md` (instrument audits, regenerate with `attribute_overlap.py` / `check_quotes.py`), `data/VOTES.md` (votes/bills evidence base and its caveats), `data/DATASET_STATS.md` (per-source dataset stats, regenerate with `dataset_stats.py`), `game/GAME_REVIEW.md` (rules/balance review).
- **v3.0 planning**: `ATTRIBUTES.md` is the **attribute contract** — one failure mode per attribute, the ownership ledger for moves that currently double-count, eligibility gates, and the decisions log. Where a prompt in `attribute-extraction/prompts/` disagrees with it, the prompt is a bug. `V3_PLAN.md` is the why, `V3_TODO.md` the ordered backlog.
- **`attribute-extraction/attributes.py` is the single source of truth** for the attribute set, its three tiers and its card-facing definitions. The extractor, `build_v2_dataset.py` and the icon map all read it — never re-list attributes by globbing `prompts/*.txt` (that is how Charisma survived in the site copy after it was cut). `tests/test_registry_consistency.py` fails if a copy drifts.
- **v3.0 attribute changes, implemented 2026-08-07:** **Charisma cut** (r=0.96 with Civility), replaced by **Focus** (is the statement about the policy, or the other team?). **Civility re-anchored** — 1.0 is the expected standard, 0.5 a genuine failure, so hard criticism of a *policy* now scores near 1.0; **every v2.0 civility score is therefore incomparable with v3.0**. **Veracity and Divination no longer score at extraction** — they emit a claim plus a `falsification_criterion`, `score=None`, and `prior_score` (the model's unaided guess). `resolve.py` searches for evidence and assigns the real score. A `None` score is a pending row, never a zero.
- **`prior_score` vs `score`** — the guess lives in a separate field on purpose. It exists so `resolve.py compare` can measure whether searching beats guessing, and keeping it out of `score` makes it structurally impossible for a guess to be published as a resolved answer. The resolver is never shown it.
- **`uncheckable` / `not_yet_due` produce no score, ever.** Absence of evidence is not evidence of falsity; mapping them to 0.0 would mark every hard-to-check claim as a lie.
- **Subject attribution applies to some attributes only.** Civility/Rigor/Specificity/Focus measure how the *speaker* is behaving, so an insult aimed at someone else is still the speaker's own — `attributes.normalise_subject()` forces `speaker` for those. Only Strength/Authenticity (and narrowly Veracity/Divination, when relaying) can be `other`.
- **Three tiers** (`attributes.py`): `text` (Civility, Rigor, Specificity, Focus — scored in speech windows), `record` (Forthrightness over Q/A pairs; Strength and Authenticity joined to `corpus/` records), `search` (Veracity, Divination). **Only the `text` tier is scored by the window extractor** — `extract_hansard.py` covers the 4 text + 2 search attributes, `extract_questions.py` covers Forthrightness.
- **The published set is six** (`attributes.PUBLISHED`): Veracity, Divination, Focus, Civility, Rigor, Specificity. **Forthrightness is WITHHELD** as of 2026-09-25 — still extracted, not on a card. Only the executive answers oral questions, so of the 31 MPs with a usable sample all 31 are government, and it reads as a government bonus on a 133-card grid. That is structural and survives fixing the Q/A pairing bug (see V3_TODO.md Phase D0). Divination took its place: 95% coverage with `--use_prior`, a bench gap of −1, and the lowest mean correlation of the seven. Veracity and Divination are both shown from `prior_score` and both carry the unverified `?` mark until the resolver runs.
- **`extract.py` enforces a hard quote gate**: any example whose statement is not verbatim in the source window, is ellipsis-spliced, or does not begin and end on a sentence boundary is dropped before it reaches disk. Run-level rejection stats print at the end of every run.
- v3.0 output goes to **new files** (`hansard_scores_v3.jsonl`, `forthrightness_scores_v3.jsonl`) — never append to the v2.0 scores, which used a different Civility scale and a retired attribute. `overnight_run.py` deliberately **does not publish**; the site is refreshed only after the evaluation pass.
- `voted.nz` is **not** a usable vote source: personal (conscience) votes only, no party votes, no API. Party votes come from Hansard (already scraped) — see `data/VOTES.md`.
- `TODOs` (root) is the live backlog across all four subprojects.
- The two Flask apps both default to port 5000 — run only one at a time, or change the port.
