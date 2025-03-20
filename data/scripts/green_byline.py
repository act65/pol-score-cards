import re
import datetime
import pytz
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

    return {
        "author": " and ".join(text[1:-1]),
        "date": article_date
    }
    

all_data = []
with open("data/greens_media_releases.json", "r") as file:
    data = json.load(file)
    for item in data:
        byline = item["byline"]
        byline = byline.replace("  ", " ")
        print(byline)
        parsed = parse_greens_byline(byline)

        # add the other fields
        parsed["headline"] = item["headline"]
        parsed["content"] = item["content"]
        parsed["url"] = item["url"]
        # print(parsed)
        all_data.append(parsed)

with open("data/greens_media_releases_fixed.json", "w") as file2:
    json.dump(all_data, file2, indent=4, default=str)