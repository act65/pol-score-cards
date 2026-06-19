# Project status & deliverables

A working map of the project, organised around the **four deliverables**, with an
honest status for each. Updated 2026-06-19.

1. **Tools** — the scrapers, the attribute-extraction prompts, and the extraction scripts.
2. **Raw datasets** — the scraped articles and the LLM-extracted attributes, **presented with extraction accuracies** (a technical contribution to the social sciences).
3. **Site** — displays the extracted attribute data as cards, and **links each score back to the statements/claims/promises that produced it** (click a card's stat → explore the evidence).
4. **Game** — the politician card battler.

---

## 1. Tools — ✅ working

- **Attribute extraction** (`attribute-extraction/`): two backends — **`anthropic`**
  (SDK structured outputs, uses API credits) and **`claude_cli`** (routes through
  the local `claude -p` CLI → uses your Claude **subscription, no API credits**;
  `claude_cli.py`). Pick with `--backend`. `extract.py`, `extract_all.py`, and the
  concurrent `build_site_data.py` pipeline.
- **Prompts**: all **9** standardised to one format (definition + 0–1 rubric,
  higher = better), including the new `authenticity` prompt; fixed two empty + one
  unfinished; verified disjoint from the testsets. `prompts/<attribute>.txt`.
- **Eval harness** `evaluate.py` (+ offline-tested metrics) → accuracies (see #2).
- **Scrapers** (`data/scrapers/`): date-window filter (`is_recent`, tested) + a
  fixed Py3.9 import bug. Live fetching of party sites + RNZ works (see #2);
  the standalone BeautifulSoup scrapers still need debugging, and Hansard needs a
  headless browser / its SPA API — full status in `data/LIVE_FETCH.md`.

## 2. Raw datasets + extraction accuracies — ◐ growing

- **Articles:** 323 across Beehive, Greens, National, RNZ — stats in
  `data/DATASET_STATS.md` (regenerate with `data/dataset_stats.py`). Includes
  fresh **live** June-2026 samples (`data/data/live_{greens,national,rnz}_2026-06.json`)
  fetched directly from the sources.
- **Extraction accuracies** (the social-science framing): held-out eval on
  `claude-opus-4-8` — **civility r=0.88** (MAE 0.13), **veracity r=0.73** (MAE
  0.14); methodology, the instructive misses, and trust caveats in
  `attribute-extraction/EVALUATION.md`; raw output in `eval_report.json`.
- **End-to-end pipeline** (`attribute-extraction/build_site_data.py`, concurrent,
  all **9** attributes incl. the new Authenticity prompt): sampled the existing
  scraped data (`data/select_mvp.py`, ~42 articles across Greens/National/Beehive/
  RNZ) → **26 politicians across all 5 parties, 649 enriched examples, avg
  6.7/9 attributes** each (cleaned via `clean_site_ids.py`).
- **Examples are enriched:** each carries the **per-statement score**, the
  **analysis** (why it scored that way), and **context** (headline/author/date/
  source) — the score on a card is the mean of the displayed evidence.
- **Run for FREE on the Claude subscription** via the `claude_cli` backend — no
  API credits consumed (after the earlier API run exhausted the balance).
- **The one gap is Precision/Forthrightness (~0)** — it scores *whether a
  question was answered*, which only exists in Q&A (interviews/**Hansard**), not
  press releases. Exactly what the Hansard scraper unlocks.
- ⬜ **Remaining:** Hansard (→ Precision; `data/HANSARD_HOWTO.md`); months-deep
  backfill via listing pagination; wire detection testsets.

## 3. Site — ✅ cards + evidence links + shared design

- Scorecards rendered as **trading cards** (shared design — see below): party-
  coloured banner, small **circular corner portrait** (real CC-licensed photos
  for all 7 demo politicians, credited in `site/static/img/CREDITS.md`), and a
  **stylized icon per attribute** (no text labels) with a value coloured by tier.
- An **attribute legend/key** explains the icons.
- **Now showing REAL extracted data:** the site renders **26 data-driven
  politicians** across all 5 parties (Luxon, Seymour, Peters, Swarbrick, Bishop,
  Stanford, Reti, Hoggard, McKee, Menéndez March, Hipkins, …). Each card stat links
  to `/attribute/<id>/<attr>`, an **enriched evidence page**: every statement shows
  its own score, the **analysis** of why it scored that way, the **context**
  (headline/author/date/source), and a link to the source — and the card score is
  the mean of those displayed statements. The old hand-written sample is preserved
  as `*.sample.jsonl`. Verified by running the app.
- ⬜ **Remaining:** responsive grid polish; portraits for the data-driven
  politicians (currently initials avatars; Swarbrick has a photo).

## 4. Game — ✅ playable, bugs fixed, shared card design

- Fixed the play-test bugs: 0-HP cards always leave the field (incl. attacker
  killed by reflected damage; + end-of-round sweep), and **base attacks** let you
  hit the opponent's HP directly when they have no cards, so the game can be won.
- **Clearer resolution:** structured per-round events replayed step-by-step in a
  Resolution panel with card highlights (replaced brittle log-parsing). Base-target
  UI added.
- **Real cards:** a **0–100 → game-stat normaliser** (`game/normalise.py`) scales
  real scores into a sane band (strength/rigor/veracity → 1–10; percentages pass
  through), so real politicians are now playable (max_hp ~400–800, no one-shots).
  Run with `GAME_DECK=real python app.py` to battle the actual extracted cards;
  `python normalise.py build` regenerates the deck from the site data.
- **24 unit tests pass** (18 engine + 6 normaliser); verified end-to-end through
  the running Flask server.
- ⬜ **Remaining:** draw/discard; balance tuning.

---

## Shared card design (deliverables 3 + 4)

One canonical trading-card design is reused by both the site and the game:
`shared/card.css` + `shared/attribute_icons.json` are the source of truth, synced
into both apps by `python shared/sync.py`. Same `.sc-card` markup, same attribute
icons + legend; the game scales it down and layers interaction states on top.

## MVP status — everything together ✅ (demo path works)

scraped (live: party sites + RNZ) → parsed (Claude, 8 attributes) → evaluated
(civility r=0.88 / veracity r=0.73) → **scores + evidence into the site**, and the
same real scores → **normalised into the game deck**. The one MVP source still
missing live is **Hansard** (scraper built, blocked by an anti-bot wall here).

## Paused / not started

- **Hansard live fetch** — `data/scrapers/hansard.py` is code-complete + parser-
  tested, but `hansard.parliament.nz` is behind a Radware anti-bot wall + SPA;
  running `fetch_via_playwright` needs a browser-capable environment
  (`data/LIVE_FETCH.md`). No Hansard data was fabricated.
- **Months-deep backfill** — needs listing pagination (current live data ~1 week).
- **Deployment** — paused per request ("get things working locally first").

## How to verify

No API key needed (37 tests):
```bash
cd attribute-extraction && python -m pytest test_evaluate.py        # eval metrics (6)
cd game && python -m pytest test_logic.py test_normalise.py         # engine + normaliser (24)
cd data/scrapers && python -m pytest test_window.py test_hansard.py # window + hansard parser (7)
cd data && python dataset_stats.py                                  # dataset stats
python shared/sync.py                                               # sync shared card assets
cd game && python normalise.py build                                # rebuild real game deck
```
With `ANTHROPIC_API_KEY` (e.g. in a gitignored `.env`):
```bash
cd attribute-extraction && python evaluate.py run all               # live eval -> eval_report.json
cd attribute-extraction && python build_site_data.py build          # live -> site scores + evidence
```
Run the apps (one at a time — both default to port 5000):
```bash
cd site && python app.py                  # real scorecards + evidence pages
cd game && GAME_DECK=real python app.py    # battle the real extracted cards
```
Run the apps (one at a time — both default to port 5000):
```bash
cd site && python app.py     # scorecards + evidence pages
cd game && python app.py     # card battler
```
