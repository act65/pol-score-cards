import fire
import json
import os
from openai import OpenAI

def load_prompt(name):
    with open(f"prompts/{name}.txt", "r") as f:
        return f.read()

def build_query(prompt, article):
    """
    Each article is a dictionary with the following keys:
    - headline: str
    - date: datetime
    - content: str
    - url: str
    - author: str
    """
    query = prompt + "\n\n***Article to analyze***\n\n"
    query += f"Source: {article['url']}\n\n"
    query += f"Headline: {article['headline']}\n\n"
    query += f"Date: {article['date']}\n\n"
    query += f"Author: {article['author']}\n\n"
    query += f"Content: {article['content']}\n\n"

    return query
    
def main(fname, attribute, api_key, save_to):
    """
    fname: str
        Path to the JSON file containing the articles.
    attribute: str
        Name of the attribute to analyze. It should match the name of a file in the prompts directory.
    save_to: str
        Path to save the results to.
    """
    client = OpenAI(
        api_key=api_key,
    )

    with open(fname, "r") as f:
        articles = json.load(f)

    prompt = load_prompt(attribute)

    responses = []
    bad_responses = []

    for i, article in enumerate(articles):
        print(f"\rAnalyzing article {i}: {article['headline']}...", end=" ", flush=True)
        query = build_query(prompt, article)

        completion = client.chat.completions.create(
            # model="gpt-4o-mini",
            model="gpt-4o",
            messages=[
                {"role": "system", "content": query},
            ],
        )

        # response should be formatted as a list of json objects
        try:
            examples = [json.loads(eg) for eg in completion.choices[0].message.content.split("\n") if eg]
        except Exception as e:
            print(f"Error processing response for article {article['headline']}: {e}")
            bad_responses.append({
                "source": article['url'],
                "response": completion.choices[0].message.content
            })
            continue

        responses.append({
            "examples": examples,
            "source": article['url']
        })

    with open(save_to, "w") as f:
        json.dump(responses, f, indent=4)

    
    if bad_responses:
        with open("bad_responses.json", "w") as f:
            json.dump(bad_responses, f, indent=4)


if __name__ == "__main__":
    fire.Fire(main)