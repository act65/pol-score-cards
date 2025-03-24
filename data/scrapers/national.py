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

def scrape_national_media_release(url):
    try:
        time.sleep(1)  # Be nice to the server

        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h1', class_='mb-2 text-5xl font-extrabold')
        headline = format_raw(headline_element.text) if headline_element else None

        author_element = soup.find('p', class_='text-lg font-bold uppercase my-2 flex group-hover:underline')
        author = format_raw(author_element.text) if author_element else None

        date_element = soup.find('p', class_='text-lg font-bold uppercase')
        date_str = format_raw(date_element.text) if date_element else None
        date_published = None
        if date_str:
            try:
                date_published = datetime.datetime.strptime(date_str, '%d %B %Y').replace(tzinfo=pytz.timezone('Pacific/Auckland'))
            except ValueError as e:
                print(f"Error parsing date '{date_str}' from URL {url}: {e}")

        content_element = soup.find('div', class_='space-y-3')
        content = format_raw(content_element.text) if content_element else None

        return {
            'headline': headline,
            'date': date_published.isoformat() if date_published else None,
            'author': author,
            'content': content,
            'url': url,
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None

def scrape_national_media_release_page(base_url, page, last_year_date, all_releases):
    counter = 0
    page_num = 1
    stop_scraping = False

    while not stop_scraping and counter < 100:  # Limit to 100 for now, can adjust
        page_url = base_url + f"/{page}" + f'?page={page_num}'
        print(f"Fetching page: {page_url}")
        try:
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')


            # article_links = soup.find_all('a', href=re.compile(r'/news/\d{8}-'))
            article_links = soup.find_all('a', href=re.compile(r'/press/'))

            if not article_links:
                print("No more articles found on this page.")
                break

            for link_element in article_links:
                relative_url = link_element['href']
                article_url = get_full_url(base_url, relative_url)

                # Basic check to avoid duplicates if the same link appears multiple times
                if any(release['url'] == article_url for release in all_releases):
                    continue

                release_data = scrape_national_media_release(article_url)
                if release_data:
                    if release_data['date_published']:
                        release_date = datetime.datetime.fromisoformat(release_data['date_published'])
                        if release_date >= last_year_date:
                            all_releases.append(release_data)
                            counter += 1
                            print(release_data['headline'])  # Print headline as progress
                        else:
                            print(f"Skipping older article: {release_data['headline']} published on {release_date.strftime('%Y-%m-%d')}")
                            stop_scraping = True # Stop if we hit articles older than the target date
                            break
                    else:
                        print(f"Could not determine publish date for {article_url}")
                if counter >= 100:
                    stop_scraping = True
                    break

            if stop_scraping:
                break

            page_num += 1
            time.sleep(1) # Be nice

        except requests.exceptions.RequestException as e:
            print(f"Error fetching media release page {page_url}: {e}")
            break
        except Exception as e:
            print(f"Error processing media release page {page_url}: {e}")
            break

if __name__ == "__main__":
    national_base_url = "https://www.national.org.nz"
    page = "news"
    page = "press"
    today = datetime.datetime.now(pytz.timezone('Pacific/Auckland'))
    one_year_ago = today - datetime.timedelta(days=365)
    all_national_releases = []

    print(f"Scraping National Party media releases from {national_base_url} for the last year (since {one_year_ago.strftime('%Y-%m-%d')})...")
    scrape_national_media_release_page(national_base_url, page, one_year_ago, all_national_releases)

    print(f"\nFound {len(all_national_releases)} National Party media releases in the last year.")

    # Save the data to a JSON file
    output_filename = f"national_media_releases_{page}.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_national_releases, f, indent=4, default=str, ensure_ascii=False)

    print(f"\nScraped data saved to {output_filename}")