import requests
from bs4 import BeautifulSoup
import datetime
import pytz
import re
import time
import json

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

def get_full_url(base_url, relative_url):
    return f"{base_url}{relative_url}"

def scrape_beehive_media_release(url):
    try:
        time.sleep(1)  # Be nice to the server

        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h1', class_='article__title')
        headline = format_raw(headline_element.text) if headline_element else None

        date_element = soup.find('time', datetime=True)
        date_str = date_element['datetime'] if date_element else None

        author_element = soup.find('div', class_='field minister__title')
        author = format_raw(author_element.text) if author_element else None

        content_element = soup.find('div', class_='prose field field--name-body field--type-text-with-summary field--label-hidden field--item')
        content_paragraphs = content_element.find_all('p') if content_element else None
        content_text = "\n\n".join(format_raw(p.text) for p in content_paragraphs) if content_paragraphs else None

        return {
            'headline': headline,
            'date': date_str,
            'author': author,
            'content': content_text,
            'url': url,
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None

def scrape_beehive_media_release_page(base_url, last_year_date, all_releases):
    counter = 0
    page_num = 1
    stop_scraping = False

    while not stop_scraping and counter < 100:  # Limit to 100 for now, can adjust
        page_url = base_url + '/releases' + f'?page={page_num}'
        print(f"Fetching Beehive page: {page_url}")
        try:
            
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            article_list = soup.find_all('a', href=re.compile(r'/release/'), hreflang='en')

            if not article_list:
                print("No more articles found on this page.")
                break

            for link_element in article_list:
                relative_url = link_element['href']
                article_url = get_full_url(base_url, relative_url)
                # print(relative_url, article_url)
                # raise SystemExit

                if any(release['url'] == article_url for release in all_releases):
                    continue

                release_data = scrape_beehive_media_release(article_url)
                if release_data:
                    all_releases.append(release_data)
                    counter += 1
                    print(f"Beehive: {release_data['headline']}")

                if counter >= 100:
                    stop_scraping = True
                    break

            if stop_scraping:
                break

            page_num += 1
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Beehive media release page {page_url}: {e}")
            break
        except Exception as e:
            print(f"Error processing Beehive media release page {page_url}: {e}")
            break

if __name__ == "__main__":
    today = datetime.datetime.now(pytz.timezone('Pacific/Auckland'))
    one_year_ago = today - datetime.timedelta(days=365)

    # --- Beehive Scraper ---
    beehive_base_url = "https://www.beehive.govt.nz"
    all_beehive_releases = []

    print(f"\n--- Scraping Beehive media releases ---")
    scrape_beehive_media_release_page(beehive_base_url, one_year_ago, all_beehive_releases)
    print(f"\nFound {len(all_beehive_releases)} Beehive media releases in the last year.")
    with open("beehive_media_releases.json", "w", encoding="utf-8") as f:
        json.dump(all_beehive_releases, f, indent=4, default=str, ensure_ascii=False)
    print("\nScraped Beehive data saved to beehive_media_releases.json")