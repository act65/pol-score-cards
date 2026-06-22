"""Build mps_roster.json from Wikipedia's list of 54th-Parliament members.

The roster is the set of *sitting* MPs we track — it drives coverage analysis and
the relevance filter (drop articles that mention none of them). We scrape the
per-party member tables on the Wikipedia "54th New Zealand Parliament" page and
merge with any curated entries already in mps_roster.json, so hand-picked ids
(e.g. 'luxon', matched to card portraits) and macron alias variants survive.

    python build_roster.py                 # writes mps_roster.json
    python build_roster.py --dry-run       # print summary only

Re-run when membership changes (by-elections, list replacements).
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROSTER = os.path.join(HERE, "mps_roster.json")
URL = "https://en.wikipedia.org/wiki/54th_New_Zealand_Parliament"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0"

# Party-table headers vary ("ACT New Zealand (11)", "Green Party of Aotearoa
# New Zealand (15)"), so match a keyword anywhere in the header (minus the count).
PARTY_KEYWORDS = [
    ("national", "National"), ("labour", "Labour"), ("green", "Green"),
    ("first", "NZ First"), ("māori", "Te Pāti Māori"), ("maori", "Te Pāti Māori"),
    ("pāti", "Te Pāti Māori"), ("act", "ACT"),
]
_HEADER_RE = re.compile(r"^(.*?)\s*\(\d+\)\s*$")


def _party_from_header(text):
    m = _HEADER_RE.match(text)
    if not m:
        return None
    h = m.group(1).lower()
    if "independent" in h:
        return None
    for kw, party in PARTY_KEYWORDS:
        if kw in h:
            return party
    return None


def _fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _slug(name):
    return "-".join(_fold(name).split())


def scrape_members():
    from bs4 import BeautifulSoup
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    soup = BeautifulSoup(html, "html.parser")
    members = []  # (name, party)
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if not rows:
            continue
        party = _party_from_header(rows[0].get_text(" ", strip=True))
        if not party:
            continue
        # Column header row (Rank, Photo, Name, Electorate, Term, Portfolios...).
        hdr = next((r for r in rows
                    if "Name" in [c.get_text(strip=True) for c in r.find_all(["th", "td"])]), None)
        if not hdr:
            continue
        hcells = hdr.find_all(["th", "td"])
        name_h = [c.get_text(strip=True) for c in hcells].index("Name")
        for row in rows:
            if row is hdr:
                continue
            cells = row.find_all(["td", "th"])
            # Data rows carry a leading spacer cell, so they're offset vs the header.
            # Name = header index + that offset; Electorate, then Term follow.
            offset = len(cells) - len(hcells)
            ni, ti = name_h + offset, name_h + offset + 2
            if offset < 0 or ti >= len(cells):
                continue
            # A sitting MP's term is open-ended ("2023–"); a departed MP's is a
            # closed range ("2017–2024"). This keeps Speakers + by-election winners
            # (no rank number) and drops resigned/deceased members.
            term = cells[ti].get_text(" ", strip=True)
            if not re.search(r"[–\-]\s*$", term):
                continue
            cell = cells[ni]
            a = cell.find("a")  # prefer the linked (canonical) spelling
            name = re.sub(r"\[.*?\]", "", a.get_text(strip=True) if a else cell.get_text(" ", strip=True)).strip()
            if name and any(ch.isalpha() for ch in name):
                members.append((name, party))
    return members


def load_existing():
    if not os.path.exists(ROSTER):
        return []
    with open(ROSTER, encoding="utf-8") as f:
        return json.load(f)


def build(members, existing):
    # folded full-name -> existing entry, to preserve curated ids/aliases.
    by_name = {}
    for e in existing:
        for alias in e.get("aliases", []):
            if " " in alias:
                by_name[alias] = e

    roster, seen = [], set()
    for name, party in members:
        key = _fold(name)
        if key in seen:
            continue
        seen.add(key)
        surname = key.split()[-1]
        prev = by_name.get(key)
        if prev:
            aliases = sorted(set(prev.get("aliases", [])) | {key, surname})
            roster.append({"id": prev["id"], "name": name, "party": party, "aliases": aliases})
        else:
            roster.append({"id": _slug(name), "name": name, "party": party,
                           "aliases": sorted({key, surname})})
    return sorted(roster, key=lambda r: r["id"])


def main():
    dry = "--dry-run" in sys.argv
    existing = load_existing()
    members = scrape_members()
    roster = build(members, existing)

    from collections import Counter
    by_party = Counter(r["party"] for r in roster)
    old_names = {a for e in existing for a in e.get("aliases", []) if " " in a}
    new_names = {a for r in roster for a in r["aliases"] if " " in a}
    print(f"scraped {len(members)} member rows -> {len(roster)} unique MPs")
    for p, n in by_party.most_common():
        print(f"  {p:<16}{n}")
    added = len(new_names - old_names)
    dropped = sorted({e["name"] for e in existing} - {r["name"] for r in roster})
    print(f"new full-names added: {added}")
    if dropped:
        print(f"in old roster but not sitting now ({len(dropped)}): {', '.join(dropped)}")

    if dry:
        print("\n[dry run] not written")
        return
    with open(ROSTER, "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {ROSTER}")


if __name__ == "__main__":
    main()
