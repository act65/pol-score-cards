import requests
from bs4 import BeautifulSoup
import datetime
import pytz
import re
import time
import json

class BaseScraper:
    def __init__(self, base_url, timezone='Pacific/Auckland', delay=1, max_articles=100):
        self.base_url = base_url
        self.timezone = pytz.timezone(timezone)
        self.delay = delay
        self.max_articles = max_articles
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    def format_text(self, text):
        """Clean up text by removing excessive whitespace and newlines"""
        text = re.sub(r'(\n\s*){2,}', '\n', text.strip())
        text = re.sub(r' {2,}', ' ', text)
        return text

    def fetch(self, url):
        """Generic URL fetcher with rate limiting"""
        try:
            time.sleep(self.delay)
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None

    def parse_date(self, date_str, formats):
        """Try parsing date with multiple formats"""
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                return self.timezone.localize(dt)
            except ValueError:
                continue
        return None

    def save_json(self, filename, data):
        """Save results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, default=str)
        print(f"Saved {len(data)} articles to {filename}")

    def run(self):
        data = []
        for url in self.get_page_links():
            if len(data) >= self.max_articles:
                break
            article_data = self.parse_page(url)
            if article_data:
                data.append(article_data)

        self.save_json('greens.json', data)
    
    def parse_page(self, url):
        """Parse a single article"""
        raise NotImplementedError("Subclasses must implement parse_page()")
    
    def get_page_links(self):
        """Get links to individual articles"""
        raise NotImplementedError("Subclasses must implement get_page_links()")
    

class GreensScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            base_url="https://www.greens.org.nz/media",
            max_articles=100
        )

    def parse_page(self, url):
        soup = self.fetch(url)
        if not soup:
            return None

        headline_element = soup.find('h2', class_='headline')
        headline = format_raw(headline_element.text) if headline_element else None

        byline_element = soup.find('div', class_='byline')
        byline_text = format_raw(byline_element.text) if byline_element else None
        byline_data = parse_greens_byline(byline_text)

        content_element = soup.find('div', class_='content')
        content = format_raw(content_element.text) if content_element else None

        author = byline_data['author'] if byline_data else None
        date = byline_data['date'] if byline_data else None

        return {
            'headline': headline,
            'author': author,
            'date': date,
            'content': content,
            'url': url,
            'source': 'Greens'
        }
    
    def get_page_links(self, url):
        scraping = True
        i = 1
        counter = 0
        while scraping:
            page_url = url + f'?page={i}'
            soup = self.fetch(page_url)
            if not soup:
                continue

            article_list = soup.find_all('h3', class_='page-excerpt--heading')

            for article_heading in article_list:
                link_element = article_heading.find('a')
                if link_element and 'href' in link_element.attrs:
                    article_url = self._get_full_url(link_element['href'])
                    yield article_url
                    counter += 1

                    if counter >= 100:
                        scraping = False
                        break

            i += 1