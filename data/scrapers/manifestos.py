"""Party manifestos, policy platforms and coalition agreements.

The vote record is party-level (see data/VOTES.md), so the promise side should be
too — and manifestos and coalition agreements are exactly that: dated, itemised,
party-attributed public commitments. This is the missing half of Authenticity:
what a party told the public, to set against how it then voted and what it
delivered.

Two kinds of document, both in a small curated registry rather than crawled,
because there are about a dozen of them and their URLs move:

  coalition_agreement — the National/ACT and National/NZ First agreements. The
      most binding promise set we have: numbered, dated, with published
      quarterly progress. Direct PDFs.
  policy_platform     — each party's policy pages.

Each document is captured twice where possible:

  live    — what the party says now (the 2026 election platform)
  archive — the closest Wayback snapshot to `--archive_date` (default just
            before the 2023 election), i.e. what they promised to win this term

    cd data/scrapers
    python manifestos.py fetch --out ../corpus/manifestos.jsonl
    python manifestos.py fetch --archive_date 20231010 --live=False   # archive only
    python manifestos.py registry                                     # list documents

**The archive capture records the snapshot date it actually got, not the one
asked for.** The Wayback availability API returns the *closest* snapshot, which
can be years off; a document silently labelled 2023 when it is really 2025 would
poison every promise derived from it. Anything outside `--archive_tolerance_days`
is written with `stale_snapshot: true`.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import fire

try:
    from bs4 import BeautifulSoup
except ImportError:                                  # pragma: no cover
    BeautifulSoup = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "corpus", "manifestos.jsonl")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
AVAILABILITY = "https://archive.org/wayback/available"

# The 2023 general election was 14 October; a snapshot just before it is the
# platform the party actually campaigned on.
DEFAULT_ARCHIVE_DATE = "20231010"

REGISTRY = [
    # --- coalition agreements: the binding, dated commitments of this term ---
    {"doc_id": "coalition-national-act-2023", "party": "National/ACT",
     "kind": "coalition_agreement", "format": "pdf", "date": "2023-11-24",
     "title": "Coalition Agreement: New Zealand National Party & ACT New Zealand",
     "url": "https://assets.nationbuilder.com/actnz/mailings/6945/attachments/"
            "original/National_ACT_Agreement.pdf",
     "archive": False},
    {"doc_id": "coalition-national-nzfirst-2023", "party": "National/NZ First",
     "kind": "coalition_agreement", "format": "pdf", "date": "2023-11-24",
     "title": "Coalition Agreement: New Zealand National Party & New Zealand First",
     "url": "https://assets.nationbuilder.com/nzfirst/pages/4462/attachments/"
            "original/1700784896/National___NZF_Coalition_Agreement_signed_-_24_Nov_2023.pdf",
     "archive": False},

    # --- party policy platforms: live now, and as at the 2023 election -------
    {"doc_id": "policy-national", "party": "National", "kind": "policy_platform",
     "format": "html", "title": "National Party plan",
     "url": "https://www.national.org.nz/plan", "archive": True},
    {"doc_id": "policy-labour", "party": "Labour", "kind": "policy_platform",
     "format": "html", "title": "Labour Party policy",
     "url": "https://www.labour.org.nz/policy", "archive": True},
    {"doc_id": "policy-green", "party": "Green", "kind": "policy_platform",
     "format": "html", "title": "Green Party policy",
     "url": "https://www.greens.org.nz/policy", "archive": True},
    {"doc_id": "policy-act", "party": "ACT", "kind": "policy_platform",
     "format": "html", "title": "ACT policy",
     "url": "https://www.act.org.nz/policies", "archive": True},
    {"doc_id": "policy-nzfirst", "party": "NZ First", "kind": "policy_platform",
     "format": "html", "title": "New Zealand First policy",
     "url": "https://www.nzfirst.nz/policy", "archive": True},
    {"doc_id": "policy-tpm", "party": "Te Pāti Māori", "kind": "policy_platform",
     "format": "html", "title": "Te Pāti Māori policy",
     "url": "https://www.maoriparty.org.nz/policy", "archive": True},
]


def _get(url: str, timeout: int = 60, retries: int = 3) -> bytes | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:                            # noqa: BLE001 — caller reports
            if attempt == retries - 1:
                return None
            time.sleep(2 ** attempt)
    return None


def extract_pdf(data: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return _tidy("\n".join(pages))


# Chrome that carries no policy content and would otherwise dominate a page.
_DROP_TAGS = ("script", "style", "nav", "header", "footer", "form", "noscript", "svg")


def extract_html(data: bytes) -> str:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required: pip install beautifulsoup4")
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(list(_DROP_TAGS)):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    return _tidy(root.get_text("\n", strip=True))


def _tidy(text: str) -> str:
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract(data: bytes, fmt: str) -> str:
    return extract_pdf(data) if fmt == "pdf" else extract_html(data)


# A party's /policy page is usually an index — the commitments live one click
# down, under /policy/housing, /policies/tax and so on. Fetching only the index
# yields a few hundred characters of link text, which is useless as a promise
# set, so follow the sub-pages once.
_POLICY_PATH = re.compile(r"/(polic|plan|manifesto|our-priorities)", re.I)


def _sub_links(data: bytes, page_url: str, limit: int) -> list[str]:
    """Same-site policy sub-pages linked from an index page.

    Works for Wayback captures too: the archive rewrites hrefs to
    /web/<timestamp>/<original>, so the crawl stays inside the same snapshot."""
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(data, "html.parser")
    base = urllib.parse.urlparse(page_url)
    seen, out = {page_url.rstrip("/")}, []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(page_url, a["href"]).split("#")[0].rstrip("/")
        parsed = urllib.parse.urlparse(href)
        if parsed.netloc != base.netloc or href in seen:
            continue
        # For an archived page the original URL sits after /web/<ts>/.
        path = re.sub(r"^/web/\d+(?:id_)?/https?://[^/]+", "", parsed.path)
        if not _POLICY_PATH.search(path) or path.count("/") > 4:
            continue
        seen.add(href)
        out.append(href)
        if len(out) >= limit:
            break
    return out


def fetch_page_tree(url: str, fmt: str, max_pages: int, delay: float) -> tuple[str, int]:
    """Fetch a page and, for HTML indexes, its policy sub-pages. Returns
    (combined text, pages fetched)."""
    data = _get(url)
    if not data:
        return "", 0
    text = extract(data, fmt)
    if fmt != "html" or max_pages <= 1:
        return text, 1
    parts, fetched = [text], 1
    for link in _sub_links(data, url, max_pages - 1):
        time.sleep(delay)
        sub = _get(link)
        if not sub:
            continue
        sub_text = extract_html(sub)
        if len(sub_text) > 200:                      # skip near-empty shells
            parts.append(f"\n\n## {link}\n{sub_text}")
            fetched += 1
    return "\n".join(parts), fetched


def closest_snapshot(url: str, timestamp: str) -> dict | None:
    """Wayback's closest snapshot to `timestamp` — note *closest*, which may be
    nowhere near it. The caller must check the returned date."""
    api = f"{AVAILABILITY}?{urllib.parse.urlencode({'url': url, 'timestamp': timestamp})}"
    raw = _get(api, timeout=40)
    if not raw:
        return None
    try:
        snap = (json.loads(raw).get("archived_snapshots") or {}).get("closest")
    except json.JSONDecodeError:
        return None
    return snap if snap and snap.get("available") else None


def _days_apart(ts_a: str, ts_b: str) -> int:
    fmt = "%Y%m%d"
    a = datetime.datetime.strptime(ts_a[:8], fmt)
    b = datetime.datetime.strptime(ts_b[:8], fmt)
    return abs((a - b).days)


def _record(doc: dict, capture: str, url: str, text: str, **extra) -> dict:
    return {
        "doc_id": f"{doc['doc_id']}--{capture}",
        "party": doc["party"],
        "kind": doc["kind"],
        "title": doc["title"],
        "capture": capture,                # live | archive
        "source_url": doc["url"],
        "fetched_url": url,
        "date": doc.get("date"),
        "chars": len(text),
        "text": text,
        **extra,
    }


def fetch(out: str = DEFAULT_OUT, archive_date: str = DEFAULT_ARCHIVE_DATE,
          live: bool = True, archive: bool = True,
          archive_tolerance_days: int = 120, delay: float = 1.0,
          max_pages: int = 30, thin_chars: int = 3000,
          only: str | None = None) -> None:
    """Fetch every registry document, live and/or from the Wayback Machine."""
    docs = [d for d in REGISTRY if not only or only in d["doc_id"]]
    rows, problems = [], []

    for doc in docs:
        if live:
            try:
                text, pages = fetch_page_tree(doc["url"], doc["format"], max_pages, delay)
            except Exception as exc:                 # noqa: BLE001
                text, pages = "", 0
                problems.append(f"{doc['doc_id']} live: {exc}")
            if text:
                rows.append(_record(doc, "live", doc["url"], text, pages=pages,
                                    captured_at=datetime.date.today().isoformat()))
            elif pages == 0:
                problems.append(f"{doc['doc_id']} live: fetch failed")
            time.sleep(delay)

        if archive and doc.get("archive", True):
            snap = closest_snapshot(doc["url"], archive_date)
            if not snap:
                problems.append(f"{doc['doc_id']} archive: no snapshot")
            else:
                ts = snap["timestamp"]
                drift = _days_apart(ts, archive_date)
                stale = drift > archive_tolerance_days
                try:
                    text, pages = fetch_page_tree(snap["url"], doc["format"],
                                                  max_pages, delay)
                except Exception as exc:             # noqa: BLE001
                    text, pages = "", 0
                    problems.append(f"{doc['doc_id']} archive: {exc}")
                if not text:
                    problems.append(f"{doc['doc_id']} archive: fetch failed ({ts[:8]})")
                else:
                    rows.append(_record(
                        doc, "archive", snap["url"], text, pages=pages,
                        snapshot_timestamp=ts,
                        snapshot_date=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                        requested_date=archive_date,
                        snapshot_drift_days=drift,
                        stale_snapshot=stale))
                    if stale:
                        problems.append(
                            f"{doc['doc_id']} archive: closest snapshot is "
                            f"{ts[:8]}, {drift} days from {archive_date} "
                            f"— flagged stale_snapshot")
            time.sleep(delay)

    for row in rows:
        if row["kind"] == "policy_platform" and row["chars"] < thin_chars:
            problems.append(
                f"{row['doc_id']}: only {row['chars']} chars from {row.get('pages')} "
                f"page(s) — likely a JS-rendered index; needs a browser fetch or a "
                f"direct manifesto URL in the registry")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} documents -> {out}")
    _summarise(rows)
    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)


def _summarise(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"\n{'party':18} {'kind':20} {'capture':8} {'date':12} {'pages':>5} {'chars':>8}")
    for r in sorted(rows, key=lambda r: (r["kind"], r["party"], r["capture"])):
        when = r.get("snapshot_date") or r.get("captured_at") or r.get("date") or "-"
        flag = "  STALE" if r.get("stale_snapshot") else ""
        print(f"{r['party'][:17]:18} {r['kind']:20} {r['capture']:8} "
              f"{when:12} {r.get('pages', 1):5} {r['chars']:8}{flag}")
    total = sum(r["chars"] for r in rows)
    stale = sum(bool(r.get("stale_snapshot")) for r in rows)
    print(f"\ntotal {total:,} chars across {len(rows)} documents"
          + (f"   ({stale} with a stale snapshot — check before using as 2023 promises)"
             if stale else ""))


def registry() -> None:
    """List the curated documents."""
    for d in REGISTRY:
        print(f"{d['doc_id']:34} {d['party']:18} {d['kind']:20} {d['format']:5} {d['url']}")


if __name__ == "__main__":
    fire.Fire({"fetch": fetch, "registry": registry})
