# `game/` — the card-battle prototype

A 1-player (human vs AI) browser game played with the politician cards.
`game_logic.py` is the pure engine; `app.py` is a thin Flask layer over it
(`/api/start_game`, `/api/submit_round_actions`) with the UI in
`templates/index.html` + `static/script.js`.

```bash
cd game && python app.py          # http://127.0.0.1:5000/  (same port as site/ — run one)
cd game && pytest                 # 24 tests
cd game && python generate_fake_data.py    # regenerate the card deck
```

## Status: prototype, and behind the scorecard

**This engine implements the retired v2.0 attribute set.** It is built on
`strength`, `charisma` and `authenticity`: Charisma was cut in v3.0 (it
correlated with Civility at r=0.96) and replaced by Focus, and Strength and
Authenticity are deferred to v4 — see `attributes.py`, which is the source of
truth for what is published.

So there are currently **two different games** in the repo, on purpose:

| | attributes | status |
|---|---|---|
| `site/templates/rules.html` (`/rules`) | the published six | **canonical** — the paper rules, kept current |
| `game/` (this directory, `rules.md`) | the v2.0 nine | frozen prototype, not deployed |

The published rules are the ones to trust. Porting the engine to the six is
v4 work and is not scheduled; the playable game is treated as a separate
project from the scorecard site.

`politicians.jsonl` is fake data from `generate_fake_data.py` — the game does
not consume real scores from `site/`, which is the other half of the same port.

See `rules.md` for the v2.0 mechanics this code implements, `GAME_REVIEW.md`
for a balance review, and `../ATTRIBUTES.md` for the attribute contract.
