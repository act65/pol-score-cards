import requests
from bs4 import BeautifulSoup
import datetime
import pytz
import re
import time

def get_full_url(relative_url):
    return f"https://www.parliament.nz{relative_url}"


headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0'
}

def scrape_hansard_report(report_url):
    try:
        time.sleep(1)
        response = requests.get(report_url, verify=False, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        date_element = soup.find('span', class_='publish-date')
        date_str = date_element.find('strong').next_sibling.strip() if date_element and date_element.find('strong') else None

        content_element = soup.find('div', class_='body-text body-text--pub body-text--hansard is-draft')
        content_with_html = str(content_element) if content_element else None
        content_text = content_element.get_text(separator='\n').strip() if content_element else None

        return {
            'date': date_str,
            'content_html': content_with_html,
            'content_text': content_text,
            'url': report_url
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {report_url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {report_url}: {e}")
        return None

def get_hansard_report_links(page_number, start_date):
    base_url = "https://www.parliament.nz/en/pb/hansard-debates/rhr/"
    params = {
        'Criteria.page': 'HansardReports',
        'Criteria.DefaultParliamentNumber': '54',
        'Criteria.ParliamenStartDate': start_date.strftime('%Y-%m-%d'),
        'Criteria.PageNumber': str(page_number)
    }
    try:
        response = requests.get(base_url, params=params, verify=False, headers=headers)
        print(response.url)
        print(response.content)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        links = []
        report_link_elements = soup.find_all('a', class_='theme__link')
        print(report_link_elements)
        for link_element in report_link_elements:
            print(link_element)
            if 'href' in link_element.attrs:
                links.append(get_full_url(link_element['href']))
        return links
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Hansard reports page {page_number}: {e}")
        return
    except Exception as e:
        print(f"Error processing Hansard reports page {page_number}: {e}")
        return

if __name__ == "__main__":
    today_nz = datetime.datetime.now(pytz.timezone('Pacific/Auckland'))
    one_year_ago = today_nz - datetime.timedelta(days=365)
    all_hansard_reports = []
    page_number = 1

    print(f"Scraping Hansard reports since {one_year_ago.strftime('%Y-%m-%d')}...")

    while True:
        report_links = get_hansard_report_links(page_number, one_year_ago)
        if not report_links:
            print(f"No more report links found on page {page_number}. Stopping.")
            break

        print(f"Found {len(report_links)} reports on page {page_number}.")
        for link in report_links:
            report_data = scrape_hansard_report(link)
            all_hansard_reports.append(report_data)



        page_number += 1
        # Add a delay if needed to be respectful to the website


    print(f"\nSuccessfully scraped {len(all_hansard_reports)} Hansard reports from the last year.")

    # You can now process the all_hansard_reports list, for example, save to a JSON file:
    import json
    with open("hansard_reports.json", "w", encoding="utf-8") as f:
        json.dump(all_hansard_reports, f, indent=4, default=str)

    print("\nScraped Hansard data saved to hansard_reports.json")