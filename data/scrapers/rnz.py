import requests
from bs4 import BeautifulSoup
import datetime
import pytz
import re
import time

def get_full_url(relative_url):
    return f"https://www.rnz.co.nz{relative_url}"

def scrape_rnz_article(article_url):
    try:
        time.sleep(1)
        response = requests.get(article_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        headline_element = soup.find('h1', class_='c-story-header__headline')
        headline = headline_element.text.strip() if headline_element else None

        date_element = soup.find('div', class_='c-dateblock')
        date_str = date_element.find('span').text.strip() if date_element and date_element.find('span') else None
        article_date = None
        if date_str:
            nz_timezone = pytz.timezone('Pacific/Auckland')
            try:
                # Try parsing with the full date format
                date_format_full = "%I:%M %p on %d %B %Y"
                article_date_naive = datetime.datetime.strptime(date_str, date_format_full)
                article_date = nz_timezone.localize(article_date_naive)
            except ValueError:
                try:
                    # Try parsing with the "today" format
                    date_format_today = "%I:%M %p today"
                    article_date_naive_today = datetime.datetime.strptime(date_str, date_format_today)
                    # Set the date to today's date in the NZ timezone
                    today_nz = datetime.datetime.now(nz_timezone).date()
                    article_date = nz_timezone.localize(datetime.datetime.combine(today_nz, article_date_naive_today.time()))
                except ValueError as e:
                    print(f"Could not parse date: {date_str} for URL: {article_url} - {e}")

        author_element = soup.find('span', class_='author-name')
        author = author_element.text.strip() if author_element else None

        content_element = soup.find('div', class_='article__body')
        content = content_element.get_text(separator='\n').strip() if content_element else None

        return {
            'headline': headline,
            'date': article_date,
            'author': author,
            'content': content,
            'url': article_url
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {article_url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {article_url}: {e}")
        return None

def get_rnz_article_links(page_number):
    base_url = "https://www.rnz.co.nz/news/political"
    params = {'page': str(page_number)}
    try:
        response = requests.get(base_url, params=params)
        # print(response.url)
        # print(response.content)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        links = []
        link_elements = soup.find_all('a', class_='faux-link')
        for link_element in link_elements:
            if link_element and 'href' in link_element.attrs:
                links.append(get_full_url(link_element['href']))
        return links
    except requests.exceptions.RequestException as e:
        print(f"Error fetching RNZ political news page {page_number}: {e}")
        return
    except Exception as e:
        print(f"Error processing RNZ political news page {page_number}: {e}")
        return

if __name__ == "__main__":
    today_nz = datetime.datetime.now(pytz.timezone('Pacific/Auckland'))
    one_year_ago = today_nz - datetime.timedelta(days=365)
    all_rnz_articles = []
    page_number = 0
    counter = 0
    scrape = True

    print(f"Scraping RNZ political news since {one_year_ago.strftime('%Y-%m-%d')}...")

    while scrape:
        article_links = get_rnz_article_links(page_number)
        if not article_links:
            print(f"No more article links found on page {page_number}. Stopping.")
            break

        print(f"Found {len(article_links)} articles on page {page_number}.")
        for link in article_links:
            article_data = scrape_rnz_article(link)
            print(f"Scraped article: {article_data['headline']}")
            all_rnz_articles.append(article_data)
            counter += 1

            if counter >= 100:
                scrape = False
                break


        page_number += 1

    print(f"\nSuccessfully scraped {len(all_rnz_articles)} RNZ political news articles from the last year.")

    import json
    with open("rnz_political_articles.json", "w", encoding="utf-8") as f:
        json.dump(all_rnz_articles, f, indent=4, default=str)

    print("\nScraped RNZ political articles data saved to rnz_political_articles.json")