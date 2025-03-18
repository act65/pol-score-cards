from flask import Flask, render_template
import random

app = Flask(__name__)

# Sample list of politicians (replace with actual data later)
politicians = [
    {"name": "Jacinda Ardern", "party": "Labour", "id": "ardern"},
    {"name": "Christopher Luxon", "party": "National", "id": "luxon"},
    {"name": "David Seymour", "party": "ACT", "id": "seymour"},
    {"name": "Winston Peters", "party": "NZ First", "id": "peters"},
    {"name": "Chloe Swarbrick", "party": "Green", "id": "swarbrick"},
]

attribute_descriptions = {
    "evasiveness": {
        "name": "Evasiveness",
        "description": "Measures how often the politician directly answers the question asked, rather than dodging or changing the subject."
    },
    "strength": {
        "name": "Strength (Policy Implementation)",
        "description": "Indicates the politician's ability to translate their public rhetoric and promises into concrete policies and see them through to implementation."
    },
    "integrity": {
        "name": "Integrity",
        "description": "Assesses how often the politician has been observed to spout demonstrably false information or mislead the public with inaccurate claims."
    },
    "alignment": {
        "name": "Public Rhetoric vs. Parliamentary Debate Alignment",
        "description": "Evaluates the consistency between the politician's public statements and their actions, such as voting and speeches, within the parliamentary setting."
    },
    "prophecy": {
        "name": "Prediction Accuracy",
        "description": "Tracks how often the politician's predictions about future events (economic, social, etc.) have proven to be accurate."
    },
    "influence": {
        "name": "Influence",
        "description": "Measures the politician's ability to persuade colleagues, build consensus, and effectively get legislation passed or achieve their political goals."
    },
}


def generate_random_scores():
    return {
        "evasiveness": random.randint(0, 100),
        "strength": random.randint(0, 100),
        "integrity": random.randint(0, 100),
        "alignment": random.randint(0, 100),
        "prophecy": random.randint(0, 100),
        "influence": random.randint(0, 100),
    }

@app.route('/')
def index():
    politician_data = []
    for politician in politicians:
        scores = generate_random_scores()
        politician_data.append({"politician": politician, "scores": scores})
    return render_template('index.html', politicians_data=politician_data)

@app.route('/politician/<politician_id>')
def politician_detail(politician_id):
    politician = next((p for p in politicians if p['id'] == politician_id), None)
    if politician:
        scores = generate_random_scores() # Generate random scores for the detail page too
        return render_template('politician_detail.html', politician=politician, scores=scores)
    else:
        return "Politician not found", 404

@app.route('/politician/<politician_id>/<attribute>')
def attribute_detail(politician_id, attribute):
    politician = next((p for p in politicians if p['id'] == politician_id), None)
    attribute_info = attribute_descriptions[attribute]
    scores = generate_random_scores()
    score = scores[attribute]

    if politician:
        # In a real application, you would fetch the relevant examples
        # for this politician and attribute from your data source.
        examples = [
            {"text": f"Example 1 of {attribute} for {politician['name']}.", "source": "Stuff"},
            {"text": f"Example 2 of {attribute} for {politician['name']}.", "source": "Newshub"},
            {"text": f"Example 3 of {attribute} for {politician['name']}.", "source": "RNZ"},
        ]
        return render_template('attribute_detail.html', politician=politician, attribute_info=attribute_info, examples=examples, score=score)
    else:
        return "Politician not found", 404


@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)