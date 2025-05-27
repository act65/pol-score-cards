import datetime
import json
import pytz
import fire
import time
import re

from pol_data_utils.utils import get_soup, format_raw

def get_full_url(base_url, relative_url):
    return f"{base_url}{relative_url}"

def scrape_beehive_release(url):
    time.sleep(1)  # Be nice to the server
    soup = get_soup(url)

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

def scrape_beehive_release_page(base_url, N=100):
    counter = 0
    page_num = 1
    scraping = True

    while scraping:
        page_url = base_url + '/releases' + f'?page={page_num}'
        print(f"Fetching Beehive page: {page_url}")
        soup = get_soup(page_url)

        article_list = soup.find_all('a', href=re.compile(r'/release/'), hreflang='en')

        if not article_list:
            print("No more articles found on this page.")
            scraping = False
            break

        for link_element in article_list:
            relative_url = link_element['href']
            article_url = get_full_url(base_url, relative_url)
            yield article_url
            counter += 1

            if counter >= N:
                scraping = False
                break

        if counter >= N:
            scraping = False

        page_num += 1
        time.sleep(1)

def main(output_dir, N=100):
    base_url = "https://www.beehive.govt.nz"

    with open(output_dir, "w", encoding="utf-8") as f:
        print(f"Scraping Beehive media releases from {base_url}")
        for article_url in scrape_beehive_release_page(base_url, N):
            release_data = scrape_beehive_release(article_url)
            if release_data:
                print(release_data['headline'])
                json.dump(release_data, f, indent=4, default=str, ensure_ascii=False)
                f.write("\n")

    print(f"\nScraped data saved to {output_dir}")

if __name__ == "__main__":
    fire.Fire(main)