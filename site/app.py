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

# --- Grade ------------------------------------------------------------------
# A card's overall strength is the GEOMETRIC mean of its attribute scores (so a
# single weak attribute drags the whole card down — you can't be strong by being
# lopsided). That number sets the card's border colour, on a continuous ramp
# over a fixed window.
#
# This replaced a five-tier rarity ranking (legendary/epic/rare/uncommon/common
# in exponential buckets). Two things were wrong with it. It put 117 of 132
# cards in one tier, so the border said nothing about 89% of the House. And
# "rarity" means scarcity in a card game but quality here, so calling the Prime
# Minister's card *common* read as a verdict the data had not delivered.
#
# The window is ABSOLUTE and wider than the observed spread on purpose. Every
# card in this Parliament lands between 43 and 74, and a ramp stretched to fit
# that would imply the top of it is good. The pass mark is 100. The bar in the
# legend shows the same window, so a reader can see how little of it is used.
GRADE_WINDOW = (40, 80)
# A single-hue INK ramp, pale to near-black — not bronze/silver/gold.
#
# Two reasons. The card is monochrome ink on white with the party chip as its
# only colour, and a medal ramp added a second colour system competing with it.
# And a gold border for the best card implies the best card is good: it is 74
# against a pass mark of 100. Ink carries no such claim, and it is the encoding
# the card already uses one level down — `.sc-val` runs faint grey for a low
# stat to bold black for a high one. This is the same idea at card scale.
_GRADE_STOPS = [(0.0, (169, 162, 150)),   # faint
                (1.0, (20, 17, 13))]      # bold black


def _grade_colour(score):
    """Interpolate the ink ramp at `score`."""
    lo, hi = GRADE_WINDOW
    t = min(1.0, max(0.0, (float(score) - lo) / (hi - lo)))
    for (t0, c0), (t1, c1) in zip(_GRADE_STOPS, _GRADE_STOPS[1:]):
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return "#%02x%02x%02x" % tuple(
                round(a + (b - a) * k) for a, b in zip(c0, c1))
    return "#%02x%02x%02x" % _GRADE_STOPS[-1][1]


# Ticks for the colour bar in the legend.
GRADE_TICKS = list(range(GRADE_WINDOW[0], GRADE_WINDOW[1] + 1, 10))


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


def _assign_grades(items):
    """Score each card and give it its border colour."""
    for it in items:
        it["geo"] = _geo_mean(it.get("scores"))
        it["overall"] = round(it["geo"])
        it["grade"] = _grade_colour(it["overall"])


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
    _assign_grades(shown)
    for rank, d in enumerate(sorted(shown, key=lambda d: d["geo"], reverse=True), 1):
        d["rank"] = rank
    return shown, len(politician_data)


@app.route('/')
def index():
    shown, total = _featured()
    parties = sorted({d["politician"].get("party") for d in shown if d["politician"].get("party")})
    return render_template('index.html', politicians_data=shown,
                           all_attributes=attribute_descriptions,
                           grade_ticks=GRADE_TICKS, grade_window=GRADE_WINDOW,
                           grade_ramp=[_grade_colour(v) for v in
                                       range(GRADE_WINDOW[0], GRADE_WINDOW[1] + 1, 4)],
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
#     internally consistent: you can recompute it from what you can see. It is
#     no longer printed on the card (it says little — every party lands between
#     48 and 61) but it still ranks them, and the table below the cards has it.
#
# The block shows each attribute's DISTANCE FROM THE HOUSE MEAN instead. With
# the overall scores that tightly bunched, "National 59" carries almost no
# information, while "National -9 Focus, +4 Specificity" is the thing you came
# to the page for. Bars share one scale across every card, so a long bar means
# the same distance on each.
# A one-MP "party" is that MP's own card with a party name on it — and because
# the list is ranked, it would sit above real caucuses on a sample of one.
# (Darleen Tana, sitting as an Independent, topped the page before this.) Below
# the threshold a grouping is named under the table instead of being aggregated.
MIN_PARTY_MPS = 3


def _house_means(shown=None):
    """The all-MP mean per attribute — the baseline every deviation bar is read
    against, on a party card and on a politician's page alike."""
    if shown is None:
        shown, _total = _featured()
    means = {}
    for attr in ATTR_NAMES:
        vals = [d["scores"][attr] for d in shown
                if isinstance(d["scores"].get(attr), (int, float))]
        if vals:
            means[attr] = sum(vals) / len(vals)
    return means


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

    # Deviation bars. The widest bar on the page is the largest |delta| any
    # party has on any attribute, so every bar on every card is to one scale.
    house = _house_means(shown)
    # `or 1`: with a single party on the page every deviation is zero by
    # construction (the party IS the House), and that divided by itself is a 500.
    widest = max((abs(c["scores"][a] - house[a])
                  for c in cards for a in c["scores"] if a in house), default=1) or 1
    for c in cards:
        c["dev"] = [{"attr": a,
                     "delta": round(c["scores"][a] - house[a]),
                     "width": round(abs(c["scores"][a] - house[a]) / widest * 50, 2)}
                    for a in c["scores"] if a in house]
        c["dev_by_attr"] = {d["attr"]: d for d in c["dev"]}
    return cards, too_small, {a: round(v) for a, v in house.items()}


@app.route('/party')
def party():
    shown, _total = _featured()
    cards, too_small, house = _party_cards(shown)
    counted = sum(c["n"] for c in cards)
    return render_template('party.html', party_cards=cards,
                           all_attributes=attribute_descriptions,
                           too_small=too_small,
                           min_party_mps=MIN_PARTY_MPS, house=house,
                           mp_count=counted, min_attributes=MIN_ATTRIBUTES)

# --- Evidence ordering ------------------------------------------------------
# Examples are STORED highest-score first. Rendering them in that order means a
# card scoring 34 opens with a wall of 95s, so the page that exists to show you
# the evidence shows you the opposite of it. The default is a shuffle instead —
# seeded on (politician, attribute) so the page is stable, shareable and the
# same for everyone, rather than reshuffling under a reader on reload. Sorting
# high-to-low and low-to-high is a control on the page.
def _shuffled(examples, *seed_parts):
    out = list(examples)
    random.Random("|".join(str(p) for p in seed_parts)).shuffle(out)
    return out


@app.route('/politician/<politician_id>')
def politician_page(politician_id):
    politician = data_access_jsonl.get_politician(politician_id)
    if politician is None:
        return "Politician not found", 404
    if not politician.get("image"):
        politician["image"] = _portrait_for(politician_id)

    scores = data_access_jsonl.get_scores(politician_id) or {}
    geo = _geo_mean(scores)
    counts = data_access_jsonl.example_counts(politician_id)

    # A handful of statements per attribute, shuffled, so the page is a fair
    # sample of how this MP argues rather than a highlight reel.
    sections = []
    for attr in attribute_descriptions:
        name = attr["name"]
        if not isinstance(scores.get(name), (int, float)):
            continue
        picked = _shuffled(data_access_jsonl.get_examples(politician_id, name),
                           politician_id, name)[:3]
        sections.append({
            "attribute": attr,
            "score": scores[name],
            "n": counts.get(name, 0),
            "unverified": scores.get(f"{name}_tier") == "unresolved",
            "ci": scores.get(f"{name}_ci"),
            "examples": picked,
        })

    shown, _total = _featured()
    rank = next((d["rank"] for d in shown
                 if d["politician"]["id"] == politician_id), None)

    # The profile figure: each attribute against the House mean, the same idiom
    # the party cards use, so one visual language covers both pages. The
    # ARITHMETIC mean is drawn beside the geometric one because the gap between
    # them is the "one weak attribute drags the card down" effect made visible —
    # a lopsided card has a wide gap, an even one has almost none.
    house = _house_means(shown)
    vals = [sec["score"] for sec in sections]
    widest = max((abs(sec["score"] - house[sec["attribute"]["name"]])
                  for sec in sections
                  if sec["attribute"]["name"] in house), default=1) or 1
    for sec in sections:
        name = sec["attribute"]["name"]
        if name in house:
            sec["delta"] = round(sec["score"] - house[name])
            sec["bar"] = round(abs(sec["delta"]) / widest * 50, 2)
    profile = {
        "geo": round(geo),
        "arith": round(sum(vals) / len(vals)) if vals else 0,
        "low": min(vals) if vals else 0,
        "high": max(vals) if vals else 0,
        "house_geo": round(_geo_mean({a: v for a, v in house.items()})),
    }
    return render_template('politician.html', politician=politician,
                           sections=sections, scores=scores, house=house,
                           overall=round(geo), grade=_grade_colour(round(geo)),
                           rank=rank, ranked_of=len(shown), profile=profile,
                           all_attributes=attribute_descriptions)


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

    if not politician:
        return "Politician not found", 404
    examples = _shuffled(data_access_jsonl.get_examples(politician_id, attribute),
                         politician_id, attribute)
    return render_template('attribute_detail.html', politician=politician,
                           attribute_info=attribute_info, examples=examples,
                           score=score, meta=meta,
                           all_attributes=attribute_descriptions,
                           scores=scores,
                           strip=_attribute_strip(attribute, politician_id))


# --- Where one score sits among the rest ------------------------------------
# A number is not readable on its own: 34 for Civility means nothing until you
# know the House runs 20 to 84 and sits around 64. So the evidence page opens
# with a strip of every MP's score on that attribute, this MP marked. Same dot
# idiom as the party cards, one axis, no axes furniture.
_STRIP_PAD = 3


def _attribute_strip(attribute, politician_id):
    shown, _total = _featured()
    pairs = [(d["politician"]["id"], d["scores"][attribute]) for d in shown
             if isinstance(d["scores"].get(attribute), (int, float))]
    if len(pairs) < 5:
        return None
    vals = [v for _pid, v in pairs]
    lo, hi = min(vals) - _STRIP_PAD, max(vals) + _STRIP_PAD
    span = max(hi - lo, 1)
    stack = collections.Counter()
    dots = []
    for pid, v in sorted(pairs, key=lambda t: t[1]):
        dots.append({"x": round((v - lo) / span * 100, 2),
                     "row": stack[v],
                     "me": pid == politician_id,
                     "score": v})
        stack[v] += 1
    mine = next((d for d in dots if d["me"]), None)
    ranked = sorted(vals, reverse=True)
    return {
        "dots": dots,
        "lo": lo, "hi": hi, "n": len(pairs),
        "rows": (max(stack.values()) if stack else 1),
        "median": sorted(vals)[len(vals) // 2],
        "median_x": round((sorted(vals)[len(vals) // 2] - lo) / span * 100, 2),
        "mine": mine,
        "rank": (ranked.index(mine["score"]) + 1) if mine else None,
    }


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


# Downloadable files: the served dataset (already in static/) and the raw corpus
# it is scored from (data/corpus/, not otherwise web-exposed).
#
# Only what the scores are built from is offered. Press conferences and party
# releases are scraped and held, but nothing on this site is scored from them,
# and publishing them here invited exactly the confusion the labels were trying
# to talk readers out of.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CORPUS = os.path.join(os.path.dirname(_HERE), "data", "corpus")
_DOWNLOADS = {
    "examples": os.path.join(_HERE, "static", "examples.jsonl"),
    "scores": os.path.join(_HERE, "static", "scores.jsonl"),
    "hansard": os.path.join(_CORPUS, "hansard.json"),
}


@app.route('/download/<key>')
def download(key):
    from flask import send_file, abort
    path = _DOWNLOADS.get(key)
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route('/about')
def about():
    return render_template('about.html', attributes=attribute_descriptions,
                           min_attributes=MIN_ATTRIBUTES)


@app.route('/rules')
def rules():
    return render_template('rules.html', attributes=attribute_descriptions)

# app.register_blueprint(game_bp) # Registered blueprint

if __name__ == '__main__':
    app.run(debug=True)