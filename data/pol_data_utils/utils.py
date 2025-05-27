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