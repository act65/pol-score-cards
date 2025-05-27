import datetime
import json
import pytz
import fire
import time

from pol_data_utils.utils import get_soup, format_raw

def get_full_url(relative_url):
    return f"https://www.rnz.co.nz{relative_url}"

def parse_rnz_date(date_str, article_url):
    """
    Parses the RNZ article date string.

    Args:
        date_str (str): The date string from the website.
        article_url (str): The URL of the article (for error reporting).

    Returns:
        datetime.datetime or None: The parsed datetime object in NZ timezone, or None if parsing fails.
    """
    if not date_str:
        return None

    nz_timezone = pytz.timezone('Pacific/Auckland')
    try:
        # Try parsing with the full date format
        date_format_full = "%I:%M %p on %d %B %Y"
        article_date_naive = datetime.datetime.strptime(date_str, date_format_full)
        return nz_timezone.localize(article_date_naive)
    except ValueError:
        try:
            # Try parsing with the "today" format
            date_format_today = "%I:%M %p today"
            article_date_naive_today = datetime.datetime.strptime(date_str, date_format_today)
            # Set the date to today's date in the NZ timezone
            today_nz = datetime.datetime.now(nz_timezone).date()
            return nz_timezone.localize(datetime.datetime.combine(today_nz, article_date_naive_today.time()))
        except ValueError as e:
            print(f"Could not parse date: {date_str} for URL: {article_url} - {e}")
            return None

def scrape_rnz_article(url):
    time.sleep(1)
    soup = get_soup(url)

    headline_element = soup.find('h1', class_='c-story-header__headline')
    headline = format_raw(headline_element.text) if headline_element else None

    date_element = soup.find('div', class_='c-dateblock')
    date_span = date_element.find('span') if date_element else None
    date_str = format_raw(date_span.text) if date_span else None
    article_date = parse_rnz_date(date_str, url)

    author_element = soup.find('span', class_='author-name')
    author = format_raw(author_element.text) if author_element else None

    content_element = soup.find('div', class_='article__body')
    content = format_raw(content_element.get_text(separator='\n')) if content_element else None

    return {
        'headline': headline,
        'date': article_date.isoformat() if article_date else None,
        'author': author,
        'content': content,
        'url': url,
    }

def scrape_rnz_article_page(url, N=100):
    counter = 0
    page_number = 0
    scraping = True
    while scraping:
        page_url = url + f'?page={page_number}'
        soup = get_soup(page_url)

        article_list = soup.find_all('a', class_='faux-link')

        for link_element in article_list:
            if link_element and 'href' in link_element.attrs:
                yield get_full_url(link_element['href'])
                counter += 1

                if counter >= N:
                    scraping = False
                    break

        if not article_list or counter >= N:
            scraping = False

        page_number += 1

def main(output_dir, N=100):
    base_url = "https://www.rnz.co.nz/news/political"

    with open(output_dir, "w", encoding="utf-8") as f:
        print(f"Scraping RNZ political news from {base_url}")
        for article_url in scrape_rnz_article_page(base_url, N):
            release_data = scrape_rnz_article(article_url)
            if release_data:
                print(release_data['headline'])
                json.dump(release_data, f, indent=4, default=str, ensure_ascii=False)
                f.write("\n")

    print(f"\nScraped data saved to {output_dir}")

if __name__ == "__main__":
    fire.Fire(main)