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
- `app.py` serves politician cards and per-attribute detail/example pages.
- Two interchangeable data-access backends: `data_access_jsonl.py` (active, reads `static/*.jsonl`) and `data_access_sqlite.py` (stubbed/incomplete). `app.py` imports the jsonl one.
- Display data lives in `static/`: `politicians.jsonl`, `attributes.jsonl`, `scores.jsonl`, `examples.jsonl`.

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
cd attribute-extraction
pip install -r requirements.txt && export ANTHROPIC_API_KEY=...
python extract.py extract_file ../data/data/<articles>.json specificity out.jsonl
python extract_all.py "../data/data/*.json" all ./out      # batch
python evaluate.py run all                                  # eval (writes eval_report.json)
python -m pytest test_evaluate.py                           # offline metric tests (no key)

# Dataset stats (run from data/, no key needed)
cd data && python dataset_stats.py --out=DATASET_STATS.md

# Scraping (run from data/)
cd data && python scrapers/greens.py <output_dir> <N>
```

CLI tools (`extract.py`, `extract_all.py`, `evaluate.py`, `dataset_stats.py`, `scripts/scrape.py`) use [python-fire](https://github.com/google/python-fire) or simple argv, so args map to function parameters. Note `extract.py`/`evaluate.py` expose subcommands (`extract_file`, `run`) — name the subcommand first.

## Notes
- No CI, linter config, or top-level pinned dependencies (each tool has its own needs). Dependencies by area: extraction — `anthropic`, `pydantic`, `fire` (`attribute-extraction/requirements.txt`); scrapers — `requests`, `beautifulsoup4`, `fire`; apps — `flask`; tests — `pytest`.
- Generated analysis docs: `attribute-extraction/EVALUATION.md` (eval methodology/results), `data/DATASET_STATS.md` (per-source dataset stats, regenerate with `dataset_stats.py`), `game/GAME_REVIEW.md` (rules/balance review).
- `TODOs` (root) is the live backlog across all four subprojects.
- The two Flask apps both default to port 5000 — run only one at a time, or change the port.
