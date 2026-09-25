from flask import Flask, render_template
import collections
import math
import random
import json
import os
import urllib.parse

import data_access_jsonl
# from game.routes import game_bp # Added import

app = Flask(__name__)


# --- Showing what a claim was checked against -------------------------------
# Veracity and Divination are the two search-tier attributes: the extractor
# emits a claim and a falsification criterion, and `resolve.py` then searches
# for evidence and records a verdict WITH THE SOURCE URLS it decided on.
# Those URLs are the entire difference between a checked score and the model's
# unaided guess, and they were being collected, stored and published in
# examples.jsonl without ever being rendered.
#
# The verdict vocabulary is split by attribute on purpose (resolve.py
# SCORED_VERDICTS): Veracity asks "was this statement true", Divination asks
# "did this prediction come true", so `wrong` and `false` are different claims
# and are worded differently here.
_VERDICT_LABEL = {
    # Veracity — a statement of fact, checked.
    "true": "checked — true",
    "partly_true": "checked — partly true",
    "false": "checked — false",
    # Divination — a prediction, checked once its horizon passed.
    "correct": "checked — it came true",
    "partly_correct": "checked — partly came true",
    "wrong": "checked — it did not come true",
    # Searched, but no score. These carry sources too: the reader deserves to
    # see where we looked. The score beside them is still the guess.
    "uncheckable": "searched — no source settles it",
    "not_yet_due": "searched — too early to tell",
}


@app.template_filter("verdict_label")
def _verdict_label(verdict):
    """A verdict word as a reader-facing phrase."""
    if not verdict:
        return ""
    return _VERDICT_LABEL.get(verdict, verdict.replace("_", " "))


@app.template_filter("hostname")
def _hostname(url):
    """The bare host of a source URL — "stats.govt.nz", not 180 characters of it.

    A resolver source is often a long query URL, and a dozen of those stacked up
    is unreadable. The host is what tells a reader whether to trust it; the full
    URL is still one click away in the href.
    """
    try:
        host = urllib.parse.urlparse(url).netloc
    except ValueError:
        return url
    return host[4:] if host.startswith("www.") else (host or url)

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

# The card's border is a fixed neutral. It carried the overall score on a
# colour ramp for a while, and before that a five-tier rarity; both encoded one
# number that the card already prints, at the cost of the only other colour on
# a deliberately monochrome design. The six stats are the information.
#
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


def _score_cards(items):
    for it in items:
        it["geo"] = _geo_mean(it.get("scores"))
        it["overall"] = round(it["geo"])


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
    _score_cards(shown)
    for rank, d in enumerate(sorted(shown, key=lambda d: d["geo"], reverse=True), 1):
        d["rank"] = rank
    return shown, len(politician_data)


@app.route('/')
def index():
    shown, total = _featured()
    parties = sorted({d["politician"].get("party") for d in shown if d["politician"].get("party")})
    return render_template('index.html', politicians_data=shown,
                           all_attributes=attribute_descriptions,
                           house=_house_means(shown),
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
        c["radar"] = _radar([(a["name"], c["scores"].get(a["name"]))
                             for a in attribute_descriptions], size=150, pad=22)
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


# --- Radar ------------------------------------------------------------------
# Six attributes is exactly the count where a radar earns its keep: the shape
# is readable at a glance, and what it shows — which attributes are lopsided —
# is the thing a row of six numbers hides. Computed here as plain geometry and
# rendered as inline SVG, so there is no chart library and nothing to load.
#
# The scale is ABSOLUTE, 0 at the centre and 100 at the rim, because the rim is
# the standard. Every card in this Parliament draws a small polygon, and that
# is the honest picture.
def _radar(values, size=160, pad=18, icon_px=12, icon_class="rd-icon"):
    """values: [(label, score_or_None), ...] in card order -> SVG geometry.

    Each axis also carries `icon`: the attribute's glyph, already positioned as
    a nested <svg>. Built here rather than in the template because Jinja's
    `replace` on a Markup value escapes what it inserts, so the attributes were
    silently dropped and every glyph rendered at full size.
    """
    n = len(values)
    if n < 3:
        return None
    c = size / 2.0
    r = c - pad

    def point(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (round(c + r * frac * math.cos(ang), 2),
                round(c + r * frac * math.sin(ang), 2))

    axes = []
    poly = []
    for i, (label, score) in enumerate(values):
        ex, ey = point(i, 1.0)
        # Labels sit a little beyond the rim, nudged off-centre so the top and
        # bottom ones do not collide with the polygon.
        lx, ly = point(i, 1.18)
        frac = (max(0.0, min(100.0, float(score))) / 100.0) if score is not None else 0.0
        px, py = point(i, frac)
        raw = (_ICONS.get(str(label).lower()) or {}).get("svg", "")
        icon = ""
        if raw.startswith("<svg "):
            icon = (f"<svg class='{icon_class}' x='{lx - icon_px / 2:.2f}' "
                    f"y='{ly - icon_px / 2:.2f}' width='{icon_px}' "
                    f"height='{icon_px}' " + raw[len("<svg "):])
        axes.append({"x": ex, "y": ey, "lx": lx, "ly": ly,
                     "label": label, "score": score, "icon": icon,
                     "dx": round(c + (ex - c) * (((score or 0)) / 100.0), 2),
                     "dy": round(c + (ey - c) * (((score or 0)) / 100.0), 2)})
        poly.append(f"{px},{py}")
    rings = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        rings.append({"points": " ".join(f"{x},{y}" for x, y in
                                         (point(i, frac) for i in range(n))),
                      "frac": frac})
    return {"size": size, "cx": c, "cy": c, "r": r,
            "axes": axes, "rings": rings,
            "polygon": " ".join(poly)}


# --- Rubrics ----------------------------------------------------------------
# One page per attribute: the question it asks, what it skips, the scale, and
# invented examples showing where the boundaries are.
#
# rubrics.json is a READING of attribute-extraction/prompts/<id>.txt, not the
# instrument itself. The prompt is what the model is actually given; this is the
# same rubric written for a person. tests/test_rubrics.py checks the two have
# not drifted apart on the one line that matters — the question each attribute
# asks — and that every published attribute has a page.
_RUBRICS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "rubrics.json")
_PROMPTS_URL = ("https://github.com/act65/pol-score-cards/blob/main/"
                "attribute-extraction/prompts")


def _rubrics():
    try:
        with open(_RUBRICS_PATH, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items()
                    if not k.startswith("_")}
    except (OSError, json.JSONDecodeError):
        return {}


RUBRICS = _rubrics()


@app.route('/rubric/<attribute>')
def rubric(attribute):
    info = data_access_jsonl.get_attribute_description(attribute)
    rub = RUBRICS.get(attribute)
    if info is None or rub is None:
        return "Attribute not found", 404
    return render_template('rubric.html', attribute=info, rubric=rub,
                           all_attributes=attribute_descriptions,
                           prompt_url=f"{_PROMPTS_URL}/{attribute.lower()}.txt")


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
    radar = _radar([(a["name"], scores.get(a["name"]))
                    for a in attribute_descriptions],
                   size=210, pad=30, icon_px=15, icon_class="rd-icon dark")
    return render_template('politician.html', politician=politician, radar=radar,
                           sections=sections, scores=scores, house=house,
                           overall=round(geo),
                           rank=rank, ranked_of=len(shown),
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
    # How much of this page is actually checked. The headline score for a
    # search-tier attribute is still the model's guess until the resolver has
    # worked the whole queue, but individual statements below get settled one at
    # a time -- so "unverified" is a claim about the number at the top, and the
    # banner has to say how far the checking has got rather than implying none
    # of it has happened.
    checked = sum(1 for e in examples
                  if e.get("resolved") and e.get("evidence_urls"))
    return render_template('attribute_detail.html', politician=politician,
                           attribute_info=attribute_info, examples=examples,
                           score=score, meta=meta, checked=checked,
                           all_attributes=attribute_descriptions,
                           scores=scores,
                           spread=_score_spread(politician_id, attribute,
                                                score if isinstance(score, (int, float)) else None))


# --- The spread behind one score --------------------------------------------
# A card score is one number standing for hundreds of statements, and the number
# alone hides whether those statements agree. 34 could be every statement at 34,
# or half at 5 and half at 70 — a very different claim about an MP. So the
# evidence page opens with the distribution of the scores it is made of, with
# the headline number marked on the same axis.
#
# A histogram rather than a dot per statement: these run to 859 statements for
# one (MP, attribute), which no dot plot survives.
_HIST_BINS = 20          # 20 bins of 5 points each, over 0-100


def _score_spread(politician_id, attribute, headline):
    examples = data_access_jsonl.get_examples(politician_id, attribute)
    vals = [e["score"] for e in examples
            if isinstance(e.get("score"), (int, float))]
    if len(vals) < 8:
        return None
    width = 100 / _HIST_BINS
    counts = [0] * _HIST_BINS
    for v in vals:
        counts[min(_HIST_BINS - 1, int(v / width))] += 1
    tallest = max(counts) or 1
    mean = sum(vals) / len(vals)
    return {
        "n": len(vals),
        "bins": [{"left": round(i * width, 2), "width": round(width, 2),
                  "height": round(100 * c / tallest, 1), "count": c,
                  "lo": round(i * width), "hi": round((i + 1) * width)}
                 for i, c in enumerate(counts)],
        "headline": headline,
        "mean": round(mean),
        "median": sorted(vals)[len(vals) // 2],
        "worst": min(vals),
        "best": max(vals),
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