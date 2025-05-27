from bs4 import BeautifulSoup
import datetime
import pytz
import re
from .utils import format_text, make_request, save_to_json
# urllib.parse.urljoin is a robust way, but prompt asked for specific logic.
# from urllib.parse import urljoin 

# --- Configuration ---
BASE_DOMAIN = "https://www.labour.org.nz" # Used for get_full_labour_url
NEWS_URL = f"{BASE_DOMAIN}/news/"
TARGET_ARTICLE_COUNT = 50
OUTPUT_FILENAME = "labour_media_releases.json"
AUCKLAND_TZ = pytz.timezone('Pacific/Auckland')

# --- Helper Functions ---

def get_full_labour_url(relative_url: str) -> str:
    """
    Ensures a URL is absolute for the Labour Party website.
    If relative_url doesn't start with 'http', prepend BASE_DOMAIN.
    Ensures no double slashes between domain and path.
    """
    if relative_url.startswith('http://') or relative_url.startswith('https://'):
        return relative_url
    
    # Ensure no double slashes
    if relative_url.startswith('/'):
        return f"{BASE_DOMAIN}{relative_url}"
    else:
        return f"{BASE_DOMAIN}/{relative_url}"


def parse_labour_date(date_str: str | None) -> str | None:
    """
    Parses a date string from Labour's website into an ISO formatted string.
    Handles common formats and localizes to Pacific/Auckland.
    """
    if not date_str:
        return None

    date_str = date_str.strip() # Clean leading/trailing whitespace

    # Common formats found on websites (order might matter)
    date_formats_to_try = [
        "%d %B, %Y",    # "20 April, 2023"
        "%B %d, %Y",    # "April 20, 2023"
        "%Y-%m-%dT%H:%M:%S%z", # ISO format often in <time datetime="..."> e.g. 2023-08-15T00:00:00+12:00
        "%Y-%m-%dT%H:%M:%S", # ISO format without timezone e.g. 2023-08-15T00:00:00
        "%Y-%m-%d %H:%M:%S", # Common DB/log format
        "%d/%m/%Y",       # "20/04/2023"
        "%m/%d/%Y",       # "04/20/2023"
        "%Y-%m-%d",       # "2023-04-20"
        "%b %d, %Y",    # "Apr 20, 2023" (abbreviated month)
        "%d %b %Y",     # "20 Apr 2023" 
        "%A, %d %B %Y", # "Thursday, 20 April 2023"
    ]

    parsed_date = None
    
    # Attempt direct ISO parsing first if it includes timezone (most reliable)
    try:
        dt_obj = datetime.datetime.fromisoformat(date_str)
        # Check if it's timezone aware
        if dt_obj.tzinfo is not None and dt_obj.tzinfo.utcoffset(dt_obj) is not None:
            parsed_date = dt_obj
    except ValueError:
        pass # Not a direct ISO parseable string with timezone

    if not parsed_date:
        for fmt in date_formats_to_try:
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                parsed_date = dt
                break
            except ValueError:
                continue

    if parsed_date:
        if parsed_date.tzinfo is None or parsed_date.tzinfo.utcoffset(parsed_date) is None:
            # If timezone naive, localize to Auckland
            localized_date = AUCKLAND_TZ.localize(parsed_date)
        else:
            # If timezone aware, convert to Auckland
            localized_date = parsed_date.astimezone(AUCKLAND_TZ)
        return localized_date.isoformat()
    else:
        print(f"Warning: Could not parse date string: '{date_str}'")
        return None

# --- Scraper Functions ---

def scrape_labour_article(article_url: str) -> dict | None:
    """
    Scrapes a single Labour Party article page.
    """
    print(f"Scraping article: {article_url}")
    response = make_request(article_url, delay_seconds=0.5) 
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    headline = None
    headline_el = soup.find('h1') or soup.find(class_='entry-title')
    if headline_el:
        headline = format_text(headline_el.text)

    author_str = "Labour Party" # Default author
    author_el = soup.find(class_='author-name') or soup.find(rel='author') or soup.find(class_='byline')
    if author_el:
        author_text_cleaned = format_text(author_el.text)
        if author_text_cleaned: # Ensure it's not empty after formatting
             # Remove "By " prefix if it exists, case-insensitive
            author_str = re.sub(r'^(By\s+)', '', author_text_cleaned, flags=re.IGNORECASE).strip()
            if not author_str: # If it was only "By "
                author_str = "Labour Party"


    date_str = None
    date_iso = None
    time_el = soup.find('time', attrs={'datetime': True})
    if time_el and time_el.get('datetime'):
        date_str = time_el['datetime']
    else:
        date_el = soup.find(class_='date') or soup.find(class_='published') or soup.find('span', class_='entry-date')
        if date_el:
            date_str = format_text(date_el.text) # format_text here as it's visible text
            
    if date_str:
        date_iso = parse_labour_date(date_str)


    content = ""
    # Requirement: soup.select('div.entry-content p') or soup.select('div.article-body p')
    # The previous implementation was more robust, let's stick to the requirement for now and expand if needed.
    content_elements = soup.select('div.entry-content p, div.article-body p')
    
    # If the specific selectors don't yield results, try a broader approach (as in previous code)
    if not content_elements:
        content_elements = soup.select('div.entry-content, div.content, div.article-content, section.article-content, div.ArticleBody')
        # If these broader selectors return a single div, we take its paragraphs or its full text.
        if len(content_elements) == 1:
            # Try to find <p> tags within this broader div
            paragraphs_in_div = content_elements[0].find_all('p')
            if paragraphs_in_div:
                content_elements = paragraphs_in_div
            # else: we will use the get_text() of the single div as a whole paragraph below

    if content_elements:
        content_parts = [format_text(p.get_text(separator=' ', strip=True)) for p in content_elements]
        content = "\n".join(filter(None, content_parts))
    
    if not headline and not content:
        print(f"Warning: No headline or content found for {article_url}. Skipping.")
        return None

    return {
        'headline': headline or "N/A",
        'author': author_str,
        'date': date_iso,
        'content': content,
        'url': article_url,
    }

def scrape_labour_news_page(main_news_url: str, all_releases: list, target_article_count: int = TARGET_ARTICLE_COUNT):
    """
    Scrapes the Labour Party news page for article links and processes them.
    Currently scrapes only the first page.
    """
    print(f"Scraping news list page: {main_news_url}")
    response = make_request(main_news_url, delay_seconds=1)
    if not response:
        print(f"Error: Could not fetch main news page {main_news_url}. Aborting.")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Requirement: soup.select('article h2 a[href]'), then soup.select('div.news-item a[href]')
    link_elements = soup.select('article h2 a[href]')
    if not link_elements:
        link_elements = soup.select('div.news-item a[href]')
    # Adding other robust selectors from before as fallbacks if the primary ones fail
    if not link_elements:
        link_elements = soup.select('div.card-details a.card-title[href]')
    if not link_elements:
        link_elements = soup.select('a.news_box[href]')


    processed_urls = {release['url'] for release in all_releases}
    articles_found_on_page = 0

    for link_el in link_elements:
        relative_url = link_el['href']
        article_url = get_full_labour_url(relative_url)

        if article_url in processed_urls:
            continue
        
        if len(all_releases) >= target_article_count:
            print(f"Reached target article count ({target_article_count}). Stopping.")
            break
            
        article_data = scrape_labour_article(article_url)
        if article_data:
            all_releases.append(article_data)
            processed_urls.add(article_url)
            articles_found_on_page +=1
        
    print(f"Found and processed {articles_found_on_page} new articles from {main_news_url}.")


# --- Main Execution ---

if __name__ == "__main__":
    print(f"Starting Labour Party scraper. Target: {TARGET_ARTICLE_COUNT} articles.")
    all_labour_releases = []
    
    # base_url in the prompt is NEWS_URL here
    scrape_labour_news_page(NEWS_URL, all_labour_releases, target_article_count=TARGET_ARTICLE_COUNT)
    
    save_to_json(all_labour_releases, OUTPUT_FILENAME)
    
    print(f"\nScraping complete. Found {len(all_labour_releases)} articles.")
    print(f"Data saved to {OUTPUT_FILENAME}")
