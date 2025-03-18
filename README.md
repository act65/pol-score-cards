# NZ Politician Scorecards

## Overview

This project aims to create a data-driven platform for assessing the performance and accountability of New Zealand politicians. Inspired by fantasy and D\&D game mechanics, each politician will have a "scorecard" displaying metrics related to their political behaviour, such as evasiveness, strength (policy implementation), integrity, alignment, and more.

The goal is to (help) make politicians more accountable for their actions by providing the public with data-backed insights into their conduct. This project seeks to address concerns about politicians misleading the public and not being transparent about their priorities and actions.

## Key Features (Planned)

* Politician Scorecards: Individual cards for each NZ politician displaying their scores across various attributes.
* Data-Driven Scores: Scores are intended to be derived from analysis of news sources, Hansard (parliamentary records), and potentially other relevant data.
* LLM Powered Data Extraction: Utilizing Large Language Models to automatically extract data for each score from the identified sources.
* Evidence Display: Each scorecard will allow users to view examples (quotes, citations) that contributed to a politician's score.

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
