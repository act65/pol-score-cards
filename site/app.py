from flask import Flask, render_template
import collections
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
#
# Derived from the dataset, not hard-coded. It was a literal 6, which meant 6
# of 9 on v2.0 but 6 of 7 on v3.0 — and since v3.0's Divination reaches only
# some MPs, that silently cut the grid from 126 cards to 54. Two thirds keeps
# the v2.0 behaviour exactly (6 of 9) and follows the attribute set when it
# changes.
MIN_ATTRIBUTES = max(3, round(len(ATTR_NAMES) * 2 / 3))


def _n_attrs(score):
    return len([k for k in (score or {}) if k in ATTR_NAMES])


_PORTRAIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "portraits")


def _portrait_for(pid):
    """Convention over config: if scrape_portraits.py fetched a photo for this MP,
    use it; otherwise the card falls back to an initials avatar. Decouples portrait
    availability from the dataset build (which doesn't carry an image field)."""
    rel = f"img/portraits/{pid}.jpg"
    return rel if os.path.exists(os.path.join(_PORTRAIT_DIR, f"{pid}.jpg")) else None


def _featured():
    """(featured cards, total politicians) — the grid's set, built once and shared
    by / and /party so a party's aggregate is the mean of the cards you can
    actually click through to."""
    politician_data = []
    for politician in politicians:
        if not politician.get("image"):
            politician["image"] = _portrait_for(politician["id"])
        score = data_access_jsonl.get_scores(politician['id'])
        politician_data.append({"politician": politician, "scores": score,
                                "n_attrs": _n_attrs(score)})
    shown = [d for d in politician_data if d["n_attrs"] >= MIN_ATTRIBUTES]
    shown.sort(key=lambda d: d["n_attrs"], reverse=True)   # richest cards first
    _assign_rarity(shown)                                  # rarity ranked among the featured set
    # The geometric mean is now shown as a number, not just implied by the border
    # colour, so give it a rank too — "62" means little without "12th of 132".
    for rank, d in enumerate(sorted(shown, key=lambda d: d["geo"], reverse=True), 1):
        d["overall"] = round(d["geo"])
        d["rank"] = rank
    return shown, len(politician_data)


@app.route('/')
def index():
    shown, total = _featured()
    parties = sorted({d["politician"].get("party") for d in shown if d["politician"].get("party")})
    return render_template('index.html', politicians_data=shown,
                           all_attributes=attribute_descriptions, rarity_tiers=RARITY_TIERS,
                           parties=parties, shown_count=len(shown),
                           total_count=total, min_attributes=MIN_ATTRIBUTES)


# --- Party cards ------------------------------------------------------------
# An aggregate per party over its featured MPs. Two deliberate choices:
#
#   * each attribute is the plain MEAN of the party's MPs on that attribute,
#     over whoever has it — so Forthrightness, which only reaches MPs who answer
#     questions, is a mean over fewer people than Civility. `n` is shown per
#     attribute for that reason.
#   * the party's OVERALL is the geometric mean of the six numbers printed on
#     its own card, not the average of its members' overalls. The card is then
#     internally consistent: you can recompute it from what you can see. The two
#     differ slightly (the geometric mean is not linear), which is why the ticks
#     on the block are the members' own overalls — the spread is the honest part.
_SPREAD_PAD = 2          # axis padding either side of the observed range

# A one-MP "party" is that MP's own card with a party name on it — and because
# the list is ranked, it would sit above real caucuses on a sample of one.
# (Darleen Tana, sitting as an Independent, topped the page before this.) Below
# the threshold a grouping is named under the table instead of being aggregated.
MIN_PARTY_MPS = 3


def _party_cards(shown):
    groups = collections.defaultdict(list)
    for d in shown:
        party = d["politician"].get("party")
        if party:
            groups[party].append(d)
    too_small = sorted(((p, len(m)) for p, m in groups.items()
                        if len(m) < MIN_PARTY_MPS), key=lambda t: -t[1])
    groups = {p: m for p, m in groups.items() if len(m) >= MIN_PARTY_MPS}

    cards = []
    for party, members in groups.items():
        means, counts, unver = {}, {}, {}
        for attr in ATTR_NAMES:
            vals = [d["scores"][attr] for d in members
                    if isinstance(d["scores"].get(attr), (int, float))]
            if not vals:
                continue
            means[attr] = round(sum(vals) / len(vals))
            counts[attr] = len(vals)
            # An aggregate of unverified guesses is still an unverified guess.
            # Veracity is almost entirely prior_score in this build, and the
            # party mean must not launder that — it carries the same mark the
            # MP cards do (see the prior_score note in CLAUDE.md).
            guesses = sum(1 for d in members
                          if isinstance(d["scores"].get(attr), (int, float))
                          and d["scores"].get(f"{attr}_tier") == "unresolved")
            unver[attr] = guesses > len(vals) / 2
        overall = round(_geo_mean(means))
        cards.append({"party": party, "n": len(members), "scores": means,
                      "counts": counts, "unver": unver, "overall": overall,
                      "members": sorted(round(d["geo"]) for d in members)})
    cards.sort(key=lambda c: c["overall"], reverse=True)
    for rank, c in enumerate(cards, 1):
        c["rank"] = rank

    # One shared axis for every block, so the ticks are comparable across cards.
    every = [v for c in cards for v in c["members"]] or [0, 100]
    lo, hi = min(every) - _SPREAD_PAD, max(every) + _SPREAD_PAD
    span = max(hi - lo, 1)
    for c in cards:
        # A dot plot: MPs on the same integer score stack upward rather than
        # overprinting, so a 47-MP caucus reads as a shape and not one blob.
        stack = collections.Counter()
        dots = []
        for v in c["members"]:
            dots.append({"x": round((v - lo) / span * 100, 2),
                         "bottom": 17 + 7 * stack[v]})
            stack[v] += 1
        c["dots"] = dots
        c["mean_at"] = round((c["overall"] - lo) / span * 100, 2)
        # The aggregate line is drawn just clear of the tallest stack rather
        # than the full block height, where it read as a divider splitting the
        # card in two.
        c["mean_h"] = 17 + 7 * (max(stack.values()) if stack else 1) + 8
    return cards, lo, hi, too_small


@app.route('/party')
def party():
    shown, _total = _featured()
    cards, lo, hi, too_small = _party_cards(shown)
    counted = sum(c["n"] for c in cards)
    return render_template('party.html', party_cards=cards,
                           all_attributes=attribute_descriptions,
                           spread_lo=lo, spread_hi=hi, too_small=too_small,
                           min_party_mps=MIN_PARTY_MPS,
                           mp_count=counted, min_attributes=MIN_ATTRIBUTES)

@app.route('/attribute/<politician_id>/<attribute>')
def attribute_detail(politician_id, attribute):
    politician = data_access_jsonl.get_politician(politician_id)
    attribute_info = data_access_jsonl.get_attribute_description(attribute)
    # An attribute that is not in the dataset must 404, not render an empty page.
    # A reachable URL for a dropped attribute is how Charisma stayed visible on
    # the site after it was cut; Strength and Authenticity left the same way on
    # 2026-08-15 and must not linger as blank pages showing "N/A".
    if attribute_info is None:
        return "Attribute not found", 404
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


def _load_dataset_stats():
    """The precomputed /data overview (gen_data_stats.py). Loaded fresh per request
    so a rebuild is reflected without restarting the app; it's a small file."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "dataset_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@app.route('/data')
def data():
    return render_template('data.html', stats=_load_dataset_stats(),
                           attributes=attribute_descriptions)


# Downloadable files: the served dataset (already in static/) and the raw corpora
# (data/corpus/, not otherwise web-exposed). Party releases are zipped on the fly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORPUS = os.path.join(os.path.dirname(_HERE), "data", "corpus")
_DOWNLOADS = {
    "examples": os.path.join(_HERE, "static", "examples.jsonl"),
    "scores": os.path.join(_HERE, "static", "scores.jsonl"),
    "hansard": os.path.join(_CORPUS, "hansard.json"),
    "pressers": os.path.join(_CORPUS, "pressers.json"),
}
_RELEASE_FILES = ["national", "labour", "act", "greens", "nzfirst", "tpm"]


@app.route('/download/<key>')
def download(key):
    from flask import send_file, abort
    if key == "releases":
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name in _RELEASE_FILES:
                p = os.path.join(_CORPUS, f"{name}.json")
                if os.path.exists(p):
                    z.write(p, f"party_releases/{name}.json")
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name="nz_party_press_releases.zip")
    path = _DOWNLOADS.get(key)
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route('/about')
def about():
    return render_template('about.html', attributes=attribute_descriptions)


@app.route('/rules')
def rules():
    return render_template('rules.html', attributes=attribute_descriptions)

# app.register_blueprint(game_bp) # Registered blueprint

if __name__ == '__main__':
    app.run(debug=True)