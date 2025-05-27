import requests
import time
import json
import re
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
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; MyScraperBot/1.0; +http://mywebsite.com/botinfo)'
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
