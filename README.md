# NZ Politician Scorecards

## Overview

This project aims to create a data-driven platform for assessing the performance and accountability of New Zealand politicians. Inspired by fantasy and D\&D game mechanics, each politician will have a card displaying metrics / attributes related to their political behaviour.

The goal is to (help) make politicians more accountable for their actions by providing the public with data-backed insights into their conduct.

## Key parts

* A website to display the cards
    *  Individual cards for each NZ politician displaying their scores across various attributes.
    * Each attibute will allow users to view examples (quotes, citations) that contributed to a politician's score. Ability to explore our database.
* Build a database of examples
    * Need scrapers to collect data from news sources, Hansard, more... to build the database. Already a few implemented in `data/scrapers`
    * Need a database to host the data.
* LLM Powered Data Extraction: Utilizing Large Language Models to automatically extract data for each score from the identified sources.
    * Filter the raw scraped data (using LLMs) for comments related to our attributes
    * Use LLMs to classify. More details on how in `attribute-extraction/README.md` 
    * Evaluation of accuracy using test sets
* A card game based on the cards.
    * See `game/rules.md` for more info.
    * Game is currently playable as a 1-player game using `python app.py`.

## Attributes

| Metric         | Description                                                                                                                                                           |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Forthrightness** | Measures how often the politician directly answers the question asked, rather than dodging or changing the subject.                                                     |
| **Strength**     | Indicates the politician's ability to translate their public rhetoric and promises into concrete policies and see them through to implementation.                       |
| **Veracity**     | Assesses how often the politician has been observed to spout demonstrably false information or mislead the public with inaccurate claims.                                |
| **Authenticity** | Evaluates the consistency between the politician's public statements and their actions, such as voting and speeches, within the parliamentary setting.                   |
| **Divination**   | Tracks how often the politician's predictions about future events (economic, social, etc.) have proven to be accurate.                                                 |
| **Charisma**     | Measures the politician's ability to persuade colleagues, build consensus, and work across party lines.                                                                 |
| **Civility**     | Measures the politician's commitment to constructive dialogue over personal attacks, insults, or unproductive rhetoric. A high Civility score reflects respect for opponents and focus on policy over character assassination. |
| **Rigor**        | Tracks how rigorously the politician avoids logical fallacies (e.g., strawman arguments, slippery slopes) and relies on evidence-based reasoning. A high Rigorousness score indicates disciplined, fallacy-free rhetoric. |
| **Specificity**  | Measure the 'meaningfulness' of the politician's statements. A low Specificity score indicates vague platitudes and / or ambiguous statements.                             |

For more indepth defitions, see `llm-data-extraction/prompts`.

## Setup and Installation (Initial Steps)

1.  Clone the repository:
    ```bash
    git clone <repository_url>
    cd nz-politician-scorecards
    ```
2.  Install dependencies (if any are added later):
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the Flask app:
    ```bash
    python app.py
    ```
4.  Open your web browser and navigate to `http://127.0.0.1:5000/` to view the initial setup.
