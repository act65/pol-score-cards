from flask import Flask, render_template
import random
import json

import data_access_jsonl
# from game.routes import game_bp # Added import

app = Flask(__name__)

politicians = data_access_jsonl.get_all_politicians()
attribute_descriptions = data_access_jsonl.get_all_attributes()

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
    score = data_access_jsonl.get_scores(politician_id)[attribute]

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