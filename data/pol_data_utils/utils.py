"""LEGACY scraping helpers — `get_soup` and `format_raw`.

Imported by three scrapers only: `rnz.py`, `national.py`, `parliament.py`.
New code uses `data/scrapers/utils.py` (`make_request`, `format_text`, plus the
date helpers), which is the current implementation.

These two are NOT drop-in equivalents of those two. `format_raw` and
`format_text` normalise whitespace differently, so swapping one for the other
changes the bytes that land in the corpus — which means a re-scrape and a
re-extraction, not a refactor. Consolidating is a deliberate job; until then,
do not add a fourth copy.
"""
import time
import requests
from bs4 import BeautifulSoup
import re

def get_soup(url):
    try:
        time.sleep(1)  # Be nice to the server and wait 1 second between requests

        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, 'html.parser')

        return soup
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None
    
def format_raw(text):
    text = text.strip()
    """Removes excessive sequences of newlines and spaces from text."""
    # Replace combinations of newlines and spaces with a single newline
    text = re.sub(r'(\n\s+){2,}', '\n', text)
    # Replace multiple spaces with a single space
    text = re.sub(r' {3,}', ' ', text)
    # Replace multiple newlines with a single newline
    text = re.sub(r'\n{2,}', '\n', text)
    return text