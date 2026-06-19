from flask import Flask, render_template
import random
import json
import os

import data_access_jsonl
# from game.routes import game_bp # Added import

app = Flask(__name__)

politicians = data_access_jsonl.get_all_politicians()
attribute_descriptions = data_access_jsonl.get_all_attributes()


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
            entry = {"symbol": meta["symbol"], "blurb": meta.get("blurb", "")}
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
    _a["blurb"] = _entry.get("blurb", "")

@app.route('/')
def index():
    politician_data = []
    for politician in politicians:
        score = data_access_jsonl.get_scores(politician['id'])
        politician_data.append({"politician": politician, "scores": score})
    return render_template('index.html', politicians_data=politician_data, all_attributes=attribute_descriptions)

@app.route('/attribute/<politician_id>/<attribute>')
def attribute_detail(politician_id, attribute):
    politician = data_access_jsonl.get_politician(politician_id)
    attribute_info = data_access_jsonl.get_attribute_description(attribute)
    scores = data_access_jsonl.get_scores(politician_id) or {}
    score = scores.get(attribute, "N/A")

    if politician:
        examples = data_access_jsonl.get_examples(politician_id, attribute)
        return render_template('attribute_detail.html', politician=politician, attribute_info=attribute_info, examples=examples, score=score)
    else:
        return "Politician not found", 404


@app.route('/about')
def about():
    return render_template('about.html')

# app.register_blueprint(game_bp) # Registered blueprint

if __name__ == '__main__':
    app.run(debug=True)