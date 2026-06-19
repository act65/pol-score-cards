"""Curate an MVP slice of the existing scraped data for the extraction pipeline.

We already have hundreds of real articles on disk (greens/national/rnz dumps +
100 Beehive releases). Running the extractor over all of them is expensive, so
this picks a spread that covers ~15+ politicians: a few articles per unique
author from the party/Beehive releases (author == the politician), plus a handful
of RNZ articles (multi-politician content). Writes mvp_*.json into data/data/ for
`build_site_data.py` to consume.

    python select_mvp.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# (source file, output name, max per author, cap). RNZ uses per_author=None
# (author is a journalist) -> just take the first `cap`.
SOURCES = [
    (os.path.join(DATA, "greens_media_releases.json"),       "mvp_greens.json",   2, 8),
    (os.path.join(DATA, "live_greens_2026-06.json"),         None,                2, 8),
    (os.path.join(DATA, "national_media_releases_press.json"), "mvp_national.json", 2, 8),
    (os.path.join(DATA, "live_national_2026-06.json"),       None,                2, 8),
    (os.path.join(HERE, "beehive_media_releases.json"),      "mvp_beehive.json",  1, 14),
    (os.path.join(DATA, "rnz_political_articles.json"),      "mvp_rnz.json",      None, 5),
    (os.path.join(DATA, "live_rnz_2026-06.json"),            None,                None, 5),
]


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def select(articles, per_author, cap):
    if per_author is None:
        return articles[:cap]
    counts, chosen = {}, []
    for a in articles:
        author = (a.get("author") or "").strip().lower()
        if not (a.get("content") or "").strip():
            continue
        if counts.get(author, 0) >= per_author:
            continue
        counts[author] = counts.get(author, 0) + 1
        chosen.append(a)
        if len(chosen) >= cap:
            break
    return chosen


def main():
    # outputs keyed by output filename; live_* feed into the matching mvp_* bucket
    buckets = {"mvp_greens.json": [], "mvp_national.json": [], "mvp_beehive.json": [], "mvp_rnz.json": []}
    # map a None-output (live) source to its bucket by name
    live_target = {"live_greens_2026-06.json": "mvp_greens.json",
                   "live_national_2026-06.json": "mvp_national.json",
                   "live_rnz_2026-06.json": "mvp_rnz.json"}

    for path, out_name, per_author, cap in SOURCES:
        arts = _load(path)
        picked = select(arts, per_author, cap)
        target = out_name or live_target[os.path.basename(path)]
        buckets[target].extend(picked)

    total = 0
    for name, arts in buckets.items():
        # de-dup by url within a bucket
        seen, deduped = set(), []
        for a in arts:
            u = a.get("url")
            if u in seen:
                continue
            seen.add(u)
            deduped.append(a)
        with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
            json.dump(deduped, f, ensure_ascii=False, indent=2)
        print(f"{name}: {len(deduped)} articles")
        total += len(deduped)
    print(f"total MVP articles: {total}")


if __name__ == "__main__":
    main()
