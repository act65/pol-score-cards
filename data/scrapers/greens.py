import requests
from bs4 import BeautifulSoup
import datetime
import pytz
import re
import time
import json

def parse_greens_byline(text):
    """
    Parses the Green Party media release byline to extract author and date.

    Args:
        byline (str): The byline string.

    Returns:
        dict: A dictionary containing 'author' and 'date' (as a datetime object),
              or None for either if parsing fails.
    """
    text = text.split("\n")
    author = " and ".join(text[1:-1])
    nz_timezone = pytz.timezone('Pacific/Auckland')
    date = datetime.datetime.strptime(text[-1], "%B %d, %Y %I:%M %p")
    article_date = nz_timezone.localize(date)
    today_nz = datetime.datetime.now(nz_timezone).date()
    article_date = nz_timezone.localize(datetime.datetime.combine(today_nz, date.time()))

    return " and ".join(text[1:-1]), article_date
    

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

def get_full_url(relative_url):
    return f"https://www.greens.org.nz{relative_url}"

def scrape_media_release(url):
    try:
        time.sleep(1)  # Be nice to the server and wait 1 second between requests

        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h2', class_='headline')
        headline = format_raw(headline_element.text) if headline_element else None

        byline_element = soup.find('div', class_='byline')
        byline = format_raw(byline_element.text) if byline_element else None

        content_element = soup.find('div', class_='content')
        content = format_raw(content_element.text) if content_element else None

        author, article_date = parse_greens_byline(byline)

        return {
            'headline': headline,
            'author': author,
            'date': article_date.isoformat(),
            'content': content,
            'url': url,
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None

def scrape_media_release_page(url, last_year_date, all_releases):
    counter = 0
    for i in range(10):
        page_url = url + f'?page={i}'
        try:
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            article_list = soup.find_all('h3', class_='page-excerpt--heading')
            stop_scraping = False

            for article_heading in article_list:
                link_element = article_heading.find('a')
                if link_element and 'href' in link_element.attrs:
                    article_url = get_full_url(link_element['href'])
                    release_data = scrape_media_release(article_url)
                    print(release_data)
                    # raise SystemExit

                    all_releases.append(release_data)
                    counter += 1

                    if counter > 100:
                        stop_scraping = True
                        break


        except requests.exceptions.RequestException as e:
            print(f"Error fetching media release page {page_url}: {e}")
        except Exception as e:
            print(f"Error processing media release page {page_url}: {e}")

if __name__ == "__main__":
    base_url = "https://www.greens.org.nz/media"
    today = datetime.datetime.now(pytz.timezone('Pacific/Auckland'))
    one_year_ago = today - datetime.timedelta(days=365)
    all_media_releases = []

    print(f"Scraping media releases from {base_url} for the last year (since {one_year_ago.strftime('%Y-%m-%d')})...")
    scrape_media_release_page(base_url, one_year_ago, all_media_releases)

    print(f"\nFound {len(all_media_releases)} media releases in the last year.")

    # Or save the data to a file (e.g., JSON or CSV)
    with open("greens_media_releases.json", "w", encoding="utf-8") as f:
        json.dump(all_media_releases, f, indent=4, default=str)

    print("\nScraped data saved to greens_media_releases.json")