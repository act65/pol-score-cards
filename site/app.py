from flask import Flask, render_template
import math
import random
import json
import os

import data_access_jsonl
# from game.routes import game_bp # Added import

app = Flask(__name__)

politicians = data_access_jsonl.get_all_politicians()
attribute_descriptions = data_access_jsonl.get_all_attributes()

# The canonical attribute names (= score keys). The v2 dataset also carries
# per-attribute bias metadata under suffixed keys ("Civility_n", "_conf", "_ci"),
# so anywhere we treat the scores dict as "attribute -> value" we must restrict to
# these names, or the metadata would be miscounted as extra attributes/scores.
ATTR_NAMES = {a["name"] for a in attribute_descriptions}


def _load_attribute_icons():
    """Resolve attribute id/name -> stylized symbol from the shared icon map
    (synced from shared/attribute_icons.json). Keyed loosely so it matches the
    site's attribute ids (e.g. 'Precision') and the canonical ids alike."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "attribute_icons.json")
    table = {}
    try:
        with open(path) as f:
            raw = json.load(f)
        for cid, meta in raw.items():
            if cid.startswith("_"):
                continue
            entry = {"symbol": meta["symbol"], "svg": meta.get("svg", ""),
                     "blurb": meta.get("blurb", "")}
            for key in (cid, meta["name"], meta.get("site_id", "")):
                if key:
                    table[key.lower()] = entry
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return table


_ICONS = _load_attribute_icons()
for _a in attribute_descriptions:
    _entry = _ICONS.get(str(_a.get("id", "")).lower()) or _ICONS.get(str(_a.get("name", "")).lower()) or {}
    _a["symbol"] = _entry.get("symbol", "•")
    _a["svg"] = _entry.get("svg", "")
    _a["blurb"] = _entry.get("blurb", "")

# --- Rarity -----------------------------------------------------------------
# A card's overall strength is the GEOMETRIC mean of its attribute scores (so a
# single weak attribute drags the whole card down — you can't be "rare" by being
# lopsided). Cards are then ranked across the whole roster and dropped into
# exponentially-sized buckets: the very best card is legendary, the next 2 epic,
# next 4 rare, next 8 uncommon, and everyone else common. Rarest = smallest bucket.
RARITY_TIERS = [
    ("legendary", "#b8860b"),   # dark goldenrod
    ("epic",      "#6b21a8"),   # purple
    ("rare",      "#1e5fa0"),   # blue
    ("uncommon",  "#2f7d4f"),   # green
    ("common",    "#4b5563"),   # slate
]
_RARITY_SIZES = [1, 2, 4, 8]    # exp buckets for the top tiers; common gets the rest


def _geo_mean(scores):
    vals = []
    for k, v in (scores or {}).items():
        if k not in ATTR_NAMES:          # skip politician_id + bias-metadata keys
            continue
        try:
            vals.append(max(float(v), 1.0))   # clamp at 1 so a 0 doesn't zero the product
        except (TypeError, ValueError):
            continue
    if not vals:
        return 0.0
    return math.exp(sum(math.log(x) for x in vals) / len(vals))


def _assign_rarity(items):
    """Rank items by geometric-mean score and tag each with a rarity tier/colour."""
    for it in items:
        it["geo"] = _geo_mean(it.get("scores"))
    ranked = sorted(items, key=lambda it: it["geo"], reverse=True)
    # exponentially-sized buckets from the top; the last tier absorbs the remainder
    counts, remaining = [], len(ranked)
    for size in _RARITY_SIZES:
        take = min(size, remaining)
        counts.append(take)
        remaining -= take
    counts.append(remaining)   # common
    idx = 0
    for tier, count in enumerate(counts):
        name, colour = RARITY_TIERS[tier]
        for _ in range(count):
            ranked[idx]["rarity"] = colour
            ranked[idx]["rarity_name"] = name
            idx += 1


# Only feature politicians with enough scored attributes — a card with 2 of 9
# attributes looks broken. Thinly-covered politicians (e.g. a single Hansard
# mention) are still in the data and reachable by URL, just not on the grid.
MIN_ATTRIBUTES = 6


def _n_attrs(score):
    return len([k for k in (score or {}) if k in ATTR_NAMES])


@app.route('/')
def index():
    politician_data = []
    for politician in politicians:
        score = data_access_jsonl.get_scores(politician['id'])
        politician_data.append({"politician": politician, "scores": score,
                                "n_attrs": _n_attrs(score)})
    shown = [d for d in politician_data if d["n_attrs"] >= MIN_ATTRIBUTES]
    shown.sort(key=lambda d: d["n_attrs"], reverse=True)   # richest cards first
    _assign_rarity(shown)                                  # rarity ranked among the featured set
    parties = sorted({d["politician"].get("party") for d in shown if d["politician"].get("party")})
    return render_template('index.html', politicians_data=shown,
                           all_attributes=attribute_descriptions, rarity_tiers=RARITY_TIERS,
                           parties=parties, shown_count=len(shown),
                           total_count=len(politician_data), min_attributes=MIN_ATTRIBUTES)

@app.route('/attribute/<politician_id>/<attribute>')
def attribute_detail(politician_id, attribute):
    politician = data_access_jsonl.get_politician(politician_id)
    attribute_info = data_access_jsonl.get_attribute_description(attribute)
    scores = data_access_jsonl.get_scores(politician_id) or {}
    score = scores.get(attribute, "N/A")
    # bias-aware metadata (see bias_adjust.py): n statements, confidence tier, ±95% CI
    meta = {"n": scores.get(f"{attribute}_n"),
            "conf": scores.get(f"{attribute}_conf"),
            "ci": scores.get(f"{attribute}_ci")}

    if politician:
        examples = data_access_jsonl.get_examples(politician_id, attribute)
        return render_template('attribute_detail.html', politician=politician,
                               attribute_info=attribute_info, examples=examples,
                               score=score, meta=meta)
    else:
        return "Politician not found", 404


@app.route('/about')
def about():
    return render_template('about.html', attributes=attribute_descriptions)


@app.route('/rules')
def rules():
    return render_template('rules.html', attributes=attribute_descriptions)

# app.register_blueprint(game_bp) # Registered blueprint

if __name__ == '__main__':
    app.run(debug=True)