# Allow PEP 604 (`X | None`) annotations on Python 3.9 by deferring evaluation.
from __future__ import annotations

import requests
import time
import json
import re
import datetime
from requests.exceptions import RequestException
import os # For test cleanup

def format_text(text: str) -> str:
    """Cleans text by stripping whitespace, normalizing newlines and spaces."""
    if not text:
        return ""
    text = text.strip()
    # Replace combinations of newlines and spaces (and multiple newlines) with a single newline
    text = re.sub(r'\s*\n\s*', '\n', text)
    # Replace multiple spaces with a single space
    text = re.sub(r' +', ' ', text)
    # Replace multiple newlines (that might have been created or were already there) with a single newline
    text = re.sub(r'\n+', '\n', text)
    return text

def make_request(url: str, delay_seconds: int = 1) -> requests.Response | None:
    """
    Makes a GET request to a URL with a delay and a generic User-Agent.

    Args:
        url: The URL to request.
        delay_seconds: Time to wait before making the request.

    Returns:
        A requests.Response object if successful, None otherwise.
    """
    try:
        # print(f"Waiting {delay_seconds}s before requesting {url}...") # Verbose, remove for production
        time.sleep(delay_seconds)
        # A real browser UA + Accept headers. The old self-identifying bot UA
        # tripped some sites' WAF (Cloudflare "browser integrity check"); a
        # normal browser fingerprint is far less likely to be 403'd. (NB: a few
        # sites also block datacenter IPs outright — that needs a residential
        # connection, not just better headers.)
        headers = {
            'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
            'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
                       'image/avif,image/webp,*/*;q=0.8'),
            'Accept-Language': 'en-NZ,en;q=0.9',
        }
        # print(f"Requesting {url}...") # Verbose, remove for production
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        # print(f"Request to {url} successful.") # Verbose, remove for production
        return response
    except RequestException as e:
        print(f"Error making request to {url}: {e}")
        return None

def save_to_json(data: list[dict], filename: str) -> None:
    """
    Saves a list of dictionaries to a JSON file.

    Args:
        data: The list of dictionaries to save.
        filename: The name of the file to save to.
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, default=str)
        print(f"Data successfully saved to {filename}")
    except IOError as e:
        print(f"Error saving data to {filename}: {e}")
    except TypeError as e:
        print(f"Error serializing data to JSON for {filename}: {e}")

# --- date-window filtering -------------------------------------------------
# For the proof-of-concept we want only the last N months of articles. Each
# scraper iterates newest-first, so it can call `is_recent(date, months)` and
# stop as soon as it sees an article older than the cutoff.

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_date_loose(value):
    """Best-effort parse to a `datetime.date`. Accepts a date/datetime, an ISO
    string ('2025-03-20', '2025-03-20T12:50:00+13:00'), or any string that
    contains a YYYY-MM-DD. Returns None if no date can be found."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    m = _DATE_RE.search(str(value))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def cutoff_date(months: int, ref: datetime.date = None) -> datetime.date:
    """The date `months` months before `ref` (default: today). Approximates a
    month as 30 days, which is plenty precise for a 6-month window."""
    ref = ref or datetime.date.today()
    return ref - datetime.timedelta(days=30 * months)


def is_recent(value, months: int = 6, ref: datetime.date = None) -> bool:
    """True if `value`'s date is on or after the cutoff `months` before `ref`.
    Unparseable dates return True (keep rather than silently drop — let the
    caller decide), so callers should not rely on this to stop early when a
    source has missing dates."""
    d = parse_date_loose(value)
    if d is None:
        return True
    return d >= cutoff_date(months, ref)


if __name__ == '__main__':
    # Test format_text
    test_text_1 = "  Hello \n  World!  \n\n  This is a test.  "
    expected_text_1 = "Hello\nWorld!\nThis is a test."
    formatted_text_1 = format_text(test_text_1)
    assert formatted_text_1 == expected_text_1, f"format_text test 1 failed: expected '{expected_text_1}', got '{formatted_text_1}'"

    test_text_2 = "No   extra spaces."
    expected_text_2 = "No extra spaces."
    formatted_text_2 = format_text(test_text_2)
    assert formatted_text_2 == expected_text_2, f"format_text test 2 failed: expected '{expected_text_2}', got '{formatted_text_2}'"

    test_text_3 = "\n\nMultiple\n\n\nNewlines\n"
    expected_text_3 = "\nMultiple\nNewlines"
    formatted_text_3 = format_text(test_text_3)
    assert formatted_text_3 == expected_text_3, f"format_text test 3 failed: expected '{expected_text_3}', got '{formatted_text_3}'"
    
    assert format_text("") == "", "format_text failed for empty string"
    assert format_text("  ") == "", "format_text failed for spaces string"
    print("format_text tests passed.")

    # Test save_to_json
    test_data = [{"name": "Test", "value": 1, "nested": {"foo": "bar"}, "date_obj": datetime.datetime(2023, 1, 1)}, {"name": "Test2", "value": 2}]
    test_filename = "test_output.json"
    # Need datetime for the test case above.
    import datetime

    print(f"\nTesting save_to_json with {test_filename}...")
    save_to_json(test_data, test_filename)
    try:
        with open(test_filename, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        # Convert date_obj back to string for comparison as json.dump(default=str) would do
        test_data[0]['date_obj'] = str(test_data[0]['date_obj'])
        assert loaded_data == test_data, "save_to_json test failed: content mismatch"
        print(f"save_to_json test passed, {test_filename} verified.")
    except Exception as e:
        print(f"Error during save_to_json test verification: {e}")
    finally:
        if os.path.exists(test_filename):
            os.remove(test_filename)
            print(f"Cleaned up {test_filename}.")
    
    print("\nutils.py self-tests completed (make_request example call would require internet).")
    # Example of make_request call (would print error if no internet or DNS issue)
    # print("\nExample make_request call:")
    # test_response = make_request("http://example.com", 0)
    # if test_response:
    #     print(f"example.com response status: {test_response.status_code}")
