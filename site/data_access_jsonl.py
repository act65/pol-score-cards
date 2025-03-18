import json

def load_jsonl(fname):
    data = []
    try:
        with open(fname, 'r') as f:
            for line in f:
                data.append(json.loads(line))
    except FileNotFoundError:
        print(f"Error: {fname} not found.")
    return data

def get_all_politicians():
    return load_jsonl('static/politicians.jsonl')

def get_all_attributes():
    return load_jsonl('static/attributes.jsonl')

def get_all_scores():
    return load_jsonl('static/scores.jsonl')

def get_all_examples():
    return load_jsonl('static/examples.jsonl')

def get_politician(politician_id):
    politicians = get_all_politicians()
    return next((p for p in politicians if p['id'] == politician_id), None)

def get_attribute(attribute_name):
    attributes = get_all_attributes()
    return next((a for a in attributes if a['name'] == attribute_name), None)
    # next((attr[attribute] for attr in attribute_descriptions if attribute in attr), None)

def get_attribute_description(attribute_name):
    descriptions = get_all_attributes()
    return next((d for d in descriptions if d['id'] == attribute_name), None)

def get_scores(politician_id):
    scores = get_all_scores()
    politician_scores = next((s for s in scores if s['politician_id'] == politician_id), None)
    if politician_scores:
        return politician_scores
    return None

def get_examples(politician_id, attribute_name):
    """
    Returns: list[dict]
    Example return value:
    [
        {"text": "Example 1 of attribute for politician.", "source": "Stuff"},
        {"text": "Example 2 of attribute for politician.", "source": "Newshub"},
        {"text": "Example 3 of attribute for politician.", "source": "RNZ"},
    ]
    """
    examples = get_all_examples()
    politician_examples = [e for e in examples if ((e['politician_id'] == politician_id) and (e['attribute'] == attribute_name))]
    return politician_examples