"""Read the four dataset JSONL files, once, and index them for lookup.

Every accessor used to re-read and re-parse its file on each call, which meant
an evidence page rebuilt all 78,196 examples from disk to return the ~300 it
shows, and the front page re-read the scores file once per politician. Locally
that is 0.4s a request; on a 512MB host it is the whole memory budget.

The files are static between deploys, so they are loaded at import and kept in
dicts keyed the way the site asks for them. Nothing else about the interface
changed.
"""

import json
import os

# Resolve data files relative to THIS file, not the working directory, so the app
# runs from anywhere (gunicorn, Docker, etc.) — not only `cd site && python app.py`.
_HERE = os.path.dirname(os.path.abspath(__file__))

# Where the four dataset files live. Defaults to `static/`, the published data.
# Point it elsewhere to preview a build without overwriting what is live:
#
#     SCORECARD_DATA=../attribute-extraction/site_data_v3 python app.py
#
# Only the dataset moves — templates, CSS and portraits still come from
# `static/`, so a preview looks exactly like the real site.
_DATA_DIR = os.environ.get("SCORECARD_DATA", "static")


def load_jsonl(fname):
    data = []
    if not os.path.isabs(fname):
        fname = os.path.join(_DATA_DIR, os.path.basename(fname))
    path = fname if os.path.isabs(fname) else os.path.join(_HERE, fname)
    try:
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    except FileNotFoundError:
        print(f"Error: {path} not found.")
    return data


# --- Loaded once, at import -------------------------------------------------
_POLITICIANS = load_jsonl('static/politicians.jsonl')
_ATTRIBUTES = load_jsonl('static/attributes.jsonl')
_SCORES = load_jsonl('static/scores.jsonl')
_EXAMPLES = load_jsonl('static/examples.jsonl')

_BY_ID = {p['id']: p for p in _POLITICIANS}
_SCORE_BY_ID = {s['politician_id']: s for s in _SCORES}

# (politician_id, attribute) -> [example, ...], in the order they were written.
_EXAMPLES_BY_PAIR = {}
for _e in _EXAMPLES:
    _EXAMPLES_BY_PAIR.setdefault((_e.get('politician_id'), _e.get('attribute')), []).append(_e)


def get_all_politicians():
    return _POLITICIANS

def get_all_attributes():
    return _ATTRIBUTES

def get_all_scores():
    return _SCORES

def get_all_examples():
    return _EXAMPLES

def get_politician(politician_id):
    return _BY_ID.get(politician_id)

def get_attribute(attribute_name):
    return next((a for a in _ATTRIBUTES if a['name'] == attribute_name), None)

def get_attribute_description(attribute_name):
    return next((d for d in _ATTRIBUTES if d['id'] == attribute_name), None)

def get_scores(politician_id):
    return _SCORE_BY_ID.get(politician_id)

def get_examples(politician_id, attribute_name):
    """Every scored statement behind one (politician, attribute) score.

    Returned in stored order, which is highest-score first. Callers that show
    these to a reader must not present them in that order — the best quotes
    first is the opposite of the evidence for a low score. See `app.index`.
    """
    return _EXAMPLES_BY_PAIR.get((politician_id, attribute_name), [])


def example_counts(politician_id):
    """attribute -> how many statements sit behind that score."""
    return {attr: len(v) for (pid, attr), v in _EXAMPLES_BY_PAIR.items()
            if pid == politician_id}
