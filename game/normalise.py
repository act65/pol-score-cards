"""Normalise real 0-100 attribute scores into game-ready card stats.

Real attribute scores (site/static/scores.jsonl) are on a 0-100 scale. The game
engine uses strength / rigor / veracity as *multipliers*:

    max_hp              = 100 * strength
    attack_damage_base  = strength * rigor
    defense_base        = strength * veracity

so feeding 0-100 straight in produces ~10,000-HP, one-shot cards (see
GAME_REVIEW.md §2). This module scales those three multiplier attributes into a
1-10 band; the remaining attributes are already used by the engine as 0-100
percentages (miss/retarget chances, civility pierce, charisma slots, divination
ordering) and pass through unchanged.

Also bridges the site's attribute naming to the game's: the site calls the
"answers directly" attribute `Precision`; the game calls it `forthrightness`.

CLI — regenerate the real-politician deck the game can load:

    python normalise.py build            # writes game/politicians_real.jsonl
    python normalise.py build --out X     # custom path
"""

import json
import os

import fire

from game_logic import Attributes, PoliticianCard

MULTIPLIER_ATTRS = ("strength", "rigor", "veracity")
GAME_FIELDS = (
    "strength", "divination", "charisma", "rigor", "specificity",
    "civility", "authenticity", "veracity", "forthrightness",
)
# site score id (lowercased) -> game Attributes field
ALIASES = {"precision": "forthrightness"}

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_STATIC = os.path.join(HERE, "..", "site", "static")


def scale_multiplier(score: float) -> int:
    """Map a 0-100 score to a 1-10 multiplier band (so max_hp 100-1000,
    base attack 1-100 — sane against STARTING_HEALTH_POINTS = 1000)."""
    return max(1, min(10, round(score / 10)))


def normalise_scores(scores: dict, default: float = 50) -> dict:
    """Turn a {attribute_name: 0-100} dict into the 9 game Attributes fields.

    Case-insensitive; resolves the Precision->forthrightness alias; scales the
    multiplier attributes; clamps the percentage attributes to 0-100; fills any
    missing attribute with `default`."""
    norm = {}
    for key, value in scores.items():
        if not isinstance(value, (int, float)):
            continue
        k = key.lower()
        norm[ALIASES.get(k, k)] = value

    out = {}
    for field in GAME_FIELDS:
        value = norm.get(field, default)
        if field in MULTIPLIER_ATTRS:
            out[field] = scale_multiplier(value)
        else:
            out[field] = int(max(0, min(100, round(value))))
    return out


def card_dict_from_politician(politician: dict, scores: dict) -> dict:
    """A game-deck record ({id,name,party,attributes}) from real data."""
    return {
        "id": politician["id"],
        "name": politician["name"],
        "party": politician["party"],
        "attributes": normalise_scores(scores),
    }


def card_from_politician(politician: dict, scores: dict) -> PoliticianCard:
    return PoliticianCard(
        id=politician["id"], name=politician["name"], party=politician["party"],
        attributes=Attributes(**normalise_scores(scores)),
    )


def _load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build(out: str = None, politicians: str = None, scores: str = None):
    """Write a real-politician game deck (JSONL, game-deck format) from the
    site's politicians + scores."""
    politicians = politicians or os.path.join(SITE_STATIC, "politicians.jsonl")
    scores = scores or os.path.join(SITE_STATIC, "scores.jsonl")
    out = out or os.path.join(HERE, "politicians_real.jsonl")

    pols = _load_jsonl(politicians)
    scores_by_id = {r["politician_id"]: r for r in _load_jsonl(scores)}

    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for p in pols:
            s = scores_by_id.get(p["id"])
            if not s:
                continue
            f.write(json.dumps(card_dict_from_politician(p, s), ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} real-politician cards -> {os.path.relpath(out, HERE)}")


if __name__ == "__main__":
    fire.Fire({"build": build})
