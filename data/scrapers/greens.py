from bs4 import BeautifulSoup
import datetime
import pytz
import re
from .utils import format_text, make_request, save_to_json

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
def get_full_url(relative_url):
    return f"https://www.greens.org.nz{relative_url}"

def scrape_media_release(url):
    try:
        response = make_request(url, delay_seconds=1)
        if not response:
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h2', class_='headline')
        headline = format_text(headline_element.text) if headline_element else None

        byline_element = soup.find('div', class_='byline')
        byline_text = byline_element.text if byline_element else "" # Ensure byline_text is a string
        
        # The byline from the website might have multiple lines and needs specific parsing by parse_greens_byline
        # format_text might be too aggressive here if parse_greens_byline expects a certain structure.
        # Let's keep byline formatting within parse_greens_byline or format specific parts if needed.
        # For now, let's pass the raw byline text to parse_greens_byline after basic strip.
        
        author, article_date = parse_greens_byline(byline_text.strip())


        content_element = soup.find('div', class_='content')
        content = format_text(content_element.text) if content_element else None

        return {
            'headline': headline,
            'author': author,
            'date': article_date.isoformat(),
            'content': content,
            'url': url,
        }
    # Removed requests.exceptions.RequestException as make_request handles it
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None

def scrape_media_release_page(url, N):
    counter = 0
    for i in range(10): # Limited to 10 pages for this example
        page_url = url + f'?page={i}'
        try:
            # Using make_request for the page listing as well
            response = make_request(page_url, delay_seconds=1)
            if not response:
                continue # Skip to next page if request fails

            soup = BeautifulSoup(response.content, 'html.parser')

        article_list = soup.find_all('h3', class_='page-excerpt--heading')

        for article_heading in article_list:
            link_element = article_heading.find('a')
            if link_element and 'href' in link_element.attrs:
                yield get_full_url(link_element['href'])
                counter += 1

                    if counter > 100: # Limiting to 100 articles for this example
                        stop_scraping = True
                        break
            if stop_scraping:
                break

        # Removed requests.exceptions.RequestException as make_request handles it
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

    save_to_json(all_media_releases, "greens_media_releases.json")

    # The message "Scraped data saved to..." is now part of save_to_json