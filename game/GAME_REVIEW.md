# Game review — works? fun? balanced?

Review of `game_logic.py` + `rules.md` as they stand. The engine runs and the
12 unit tests pass (`pytest test_logic.py`). Below: what works, two correctness
gaps worth fixing before a demo, and balance/fun notes.

## Mechanics as implemented

| Attribute | Mechanic in code |
|---|---|
| Strength | `max_hp = 100 * strength`; also the common multiplier in attack and defense |
| Rigor | `attack_damage_base = strength * rigor` |
| Veracity | `defense_base = strength * veracity`; damage = `max(0, atk − def)` |
| Divination | attack resolution order (higher acts first) |
| Charisma | field slots: `2 + floor(sum(charisma on field) / 100)` |
| Specificity | miss chance `(100 − specificity)/100`; 100 = always hits |
| Authenticity | retarget chance `(100 − authenticity)/100` to a random other enemy card |
| Forthrightness | reflects `calculated_attack * forthrightness/100` back to the attacker |
| Civility | pierce: `floor(civility/10)` direct damage to the opposing player per attack |

This matches `rules.md`. (Fixed during this review: the forthrightness test
asserted an old "block" behaviour and the source carried a misleading "block"
comment + a "relected" typo — both now corrected to the reflect mechanic.)

## Correctness gaps

1. ~~**There may be no way to win.**~~ **FIXED.** Base attacks are implemented:
   an `AttackAction` whose target is a player id (or a card-target that's gone
   while the opposing field is empty) now hits that player's HP directly for
   `attack_damage_base`. The AI also base-attacks when the human has no cards, the
   frontend exposes an "attack base" target (click the opponent's info panel), and
   `_check_game_over` ends the game when HP reaches 0. Covered by
   `test_base_attack_*` in `test_logic.py`.

   Also FIXED: an attacker killed by reflected (forthrightness) damage is now
   removed from the field, and an end-of-round sweep guarantees no defeated card
   lingers (`test_attacker_removed_when_killed_by_reflect`,
   `test_end_of_round_sweep_removes_defeated`).

2. **Attribute scale mismatch — still open; blocks feeding in real card data.** The site's
   real attribute scores are on **0–100**, but Strength/Rigor/Veracity are used as
   small *multipliers*: with `strength=80, rigor=70` a card has `max_hp = 8000` and
   `attack = 5600`, dwarfing `STARTING_HEALTH_POINTS = 1000`. The unit tests
   sidestep this by using `strength=1–3` while leaving the percentage attributes at
   0–100 — i.e. the test cards aren't on the same scale the real data will be.
   Before real politician cards can be used, normalise: either scale
   Strength/Rigor/Veracity into a small band (e.g. 1–10) when building cards, or
   change the formulas to treat all attributes as 0–100 and divide.

## Balance / fun notes

- **Stalemate-friendly defense.** Damage is `max(0, strength·rigor − strength·veracity)`
  = `strength·(rigor − veracity)` when positive. A card whose target has higher
  veracity than the attacker's rigor deals **zero** damage — and still takes
  reflected damage from Forthrightness. Attacking can be strictly bad, which
  pushes toward passivity. Consider a minimum chip damage, or making defense
  reduce rather than hard-cancel.
- **Forthrightness reflects off pre-defense damage.** Reflection uses
  `calculated_attack`, not the damage actually dealt, so a fully-defended hit (0
  damage to target) still reflects. Arguably should reflect off damage dealt.
- **Card economy is thin.** `INITIAL_HAND_SIZE = 3`, `CARDS_DRAWN_PER_ROUND = 0`,
  `BASE_FIELD_SLOTS = 2`: you play from a fixed hand of 3 and never draw. The TODO
  list already wants a real draw/discard loop — worth doing for replayability.
- **Randomness is well sourced.** Specificity (miss) and Authenticity (retarget)
  give thematic variance; Divination ordering rewards a stat that's otherwise
  passive. Good hooks for "fun".

## Suggested next steps (smallest first)

1. Add a win path (option 1a is simplest and thematic: undefended player takes hits).
2. Add a card-builder that normalises real 0–100 scores into game stats, so the
   site's politician cards can be dropped into the game.
3. Tune `STARTING_HEALTH_POINTS` and the Civility divisor against the normalised
   scale so matches last a satisfying number of rounds.
4. Implement draw/discard (already on the TODO list) for deck variety.
