<<<<<<< Updated upstream
from bs4 import BeautifulSoup
=======
>>>>>>> Stashed changes
import datetime
import json
import pytz
<<<<<<< Updated upstream
import re
from .utils import format_text, make_request, save_to_json
=======
import fire
import time
import re

from pol_data_utils.utils import get_soup, format_raw
>>>>>>> Stashed changes

def get_full_url(base_url, relative_url):
    return f"{base_url}{relative_url}"

<<<<<<< Updated upstream
def scrape_national_media_release(url):
    try:
        response = make_request(url, delay_seconds=1)
        if not response:
            return None # make_request already prints an error

        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h1', class_='mb-2 text-5xl font-extrabold')
        headline = format_text(headline_element.text) if headline_element else None

        author_element = soup.find('p', class_='text-lg font-bold uppercase my-2 flex group-hover:underline')
        author = format_text(author_element.text) if author_element else None

        date_element = soup.find('p', class_='text-lg font-bold uppercase')
        # Apply format_text to date_str before parsing
        date_str_raw = date_element.text if date_element else None
        date_str_formatted = format_text(date_str_raw) if date_str_raw else None
        
        date_published = None
        if date_str_formatted:
            try:
                # The National Party website date format is like "20 February 2024"
                date_published = datetime.datetime.strptime(date_str_formatted, '%d %B %Y').replace(tzinfo=pytz.timezone('Pacific/Auckland'))
            except ValueError as e:
                print(f"Error parsing date '{date_str_formatted}' (raw: '{date_str_raw}') from URL {url}: {e}")

        content_element = soup.find('div', class_='space-y-3')
        content = format_text(content_element.text) if content_element else None

        return {
            'headline': headline,
            # The key in the original dict was 'date', not 'date_published'. Keep 'date'.
            'date': date_published.isoformat() if date_published else None,
            'author': author,
            'content': content,
            'url': url,
        }
    # requests.exceptions.RequestException is handled by make_request
    except Exception as e:
        print(f"Error processing URL {url}: {e}") # Catch other parsing errors
=======
def parse_national_date(date_str, article_url):
    """
    Parses the National Party media release date string.

    Args:
        date_str (str): The date string from the website.
        article_url (str): The URL of the article (for error reporting).

    Returns:
        datetime.datetime or None: The parsed datetime object in NZ timezone, or None if parsing fails.
    """
    if not date_str:
>>>>>>> Stashed changes
        return None
    try:
        return datetime.datetime.strptime(date_str, '%d %B %Y').replace(tzinfo=pytz.timezone('Pacific/Auckland'))
    except ValueError as e:
        print(f"Error parsing date '{date_str}' from URL {article_url}: {e}")
        return date_str

def scrape_national_release(url):
    soup = get_soup(url)

    headline_element = soup.find('h1', class_='mb-2 text-5xl font-extrabold')
    headline = format_raw(headline_element.text) if headline_element else None

    author_element = soup.find('p', class_='text-lg font-bold uppercase my-2 flex group-hover:underline')
    author = format_raw(author_element.text) if author_element else None

    date_element = soup.find('p', class_='text-lg font-bold uppercase')
    date_str = format_raw(date_element.text) if date_element else None
    article_date = parse_national_date(date_str, url)

    content_element = soup.find('div', class_='space-y-3')
    content = format_raw(content_element.text) if content_element else None

    return {
        'headline': headline,
        'date': article_date.isoformat() if article_date else None,
        'author': author,
        'content': content,
        'url': url,
    }

def scrape_national_release_page(base_url, page_path="press", N=100):
    counter = 0
    page_num = 1
    scraping = True

<<<<<<< Updated upstream
    while not stop_scraping and counter < 100:  # Limit to 100 for now, can adjust
        page_url = f"{base_url}/{page}?page={page_num}" # Corrected URL construction
        print(f"Fetching page: {page_url}")
        
        response = make_request(page_url, delay_seconds=1)
        if not response:
            print(f"Failed to fetch page {page_url}, stopping pagination for this section.")
            break # If page request fails, stop for this section

        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            article_links = soup.find_all('a', href=re.compile(r'/press/'))
=======
    while scraping:
        page_url = base_url + f"/{page_path}" + f'?page={page_num}'
        print(f"Fetching National Party page: {page_url}")
        soup = get_soup(page_url)

        article_links = soup.find_all('a', href=re.compile(rf'/{page_path}/'))

        if not article_links:
            print("No more articles found on this page.")
            scraping = False
            break
>>>>>>> Stashed changes

        for link_element in article_links:
            relative_url = link_element['href']
            yield get_full_url(base_url, relative_url)
            counter += 1

<<<<<<< Updated upstream
            for link_element in article_links:
                relative_url = link_element['href']
                # Ensure get_full_url is used correctly; National's base URL might not need to be passed if relative_url is full path
                # Assuming get_full_url prepends base_url only if needed.
                # Original get_full_url: return f"{base_url}{relative_url}" - this might lead to double base_url if relative_url is like /press/..
                # Let's assume relative_url starts with / and base_url does not end with /
                article_url = get_full_url(base_url.rstrip('/'), relative_url)


                # Basic check to avoid duplicates if the same link appears multiple times
                if any(release['url'] == article_url for release in all_releases):
                    continue

                release_data = scrape_national_media_release(article_url)
                if release_data:
                    # Ensure the key used here matches what scrape_national_media_release returns ('date')
                    if release_data.get('date'): 
                        try:
                            release_date = datetime.datetime.fromisoformat(release_data['date'])
                            if release_date >= last_year_date:
                                all_releases.append(release_data)
                                counter += 1
                                print(release_data['headline'])  # Print headline as progress
                            else:
                                print(f"Skipping older article: {release_data['headline']} published on {release_date.strftime('%Y-%m-%d')}")
                                stop_scraping = True # Stop if we hit articles older than the target date
                                break
                        except ValueError: # Handles if date is None or not valid ISO format
                             print(f"Could not parse date for {article_url} from '{release_data.get('date')}'")
                    else:
                        print(f"Could not determine publish date for {article_url}, data: {release_data}")
                if counter >= 100: # overall limit
                    stop_scraping = True
                    break

            if stop_scraping:
                break

            page_num += 1
            # time.sleep(1) is removed as make_request handles delay
        # requests.exceptions.RequestException is handled by make_request
        except Exception as e:
            print(f"Error processing media release page {page_url}: {e}")
            break # Stop for this section if processing fails
=======
            if counter >= N:
                scraping = False
                break

        if counter >= N:
            scraping = False

        page_num += 1
        time.sleep(1)
>>>>>>> Stashed changes

def main(output_dir, N=100):
    base_url = "https://www.national.org.nz"

    with open(output_dir, "w", encoding="utf-8") as f:
        page_path = "press"
        print(f"Scraping National Party media releases from {base_url}/{page_path}")
        for article_url in scrape_national_release_page(base_url, page_path, N):
            release_data = scrape_national_release(article_url)
            if release_data:
                print(release_data['headline'])
                json.dump(release_data, f, indent=4, default=str, ensure_ascii=False)
                f.write("\n")

        page_path = "news"
        print(f"Scraping National Party media releases from {base_url}/{page_path}")
        for article_url in scrape_national_release_page(base_url, page_path, N):
            release_data = scrape_national_release(article_url)
            if release_data:
                print(release_data['headline'])
                json.dump(release_data, f, indent=4, default=str, ensure_ascii=False)
                f.write("\n")

<<<<<<< Updated upstream
    output_filename = f"national_media_releases_{page}.json"
    save_to_json(all_national_releases, output_filename)
    # The print statement "Data successfully saved to..." is now part of save_to_json
=======
    print(f"\nScraped data saved to {output_dir}")

if __name__ == "__main__":
    fire.Fire(main)
>>>>>>> Stashed changes
