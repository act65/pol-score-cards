"""Fetch written parliamentary questions and their ministerial replies.

Written questions are the cleanest Forthrightness signal available: an MP asks a
specific question in writing, and a Minister either answers it or does not. Both
texts are published, dated and attributed, so unlike a Hansard exchange there is
no diarisation or interjection to untangle — just a question and what came back.

`questions.parliament.nz` is a Blazor WebAssembly app, so the page HTML is empty,
but its JSON API is public and answers plain POST requests (no browser, no key,
no CAPTCHA). Note it is a *different* API shape from `bills.parliament.nz`:

    GET  /api/data/searchFilters   parliaments, and memberId -> name per parliament
    POST /api/data/search          the questions themselves, full reply included

The reply text comes back in the listing, so there is no per-question detail
call — the whole 54th Parliament is a few dozen requests.

    cd data/scrapers
    python written_questions.py fetch                  # -> ../corpus/written_questions.jsonl
    python written_questions.py fetch --parliament 53 --limit 500

**Server-side filtering does not work on this endpoint** — sending
`parliament`, `dateFrom` or `questionNumberYear` returns the unfiltered count of
~181,000 regardless. Results are ordered newest-first, so we page through and
stop once we leave the requested parliament, which is both correct and cheap.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import fire

API = "https://questions.parliament.nz/api"
SITE = "https://questions.parliament.nz"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROSTER = os.path.join(HERE, "..", "mps_roster.json")
DEFAULT_OUT = os.path.join(HERE, "..", "corpus", "written_questions.jsonl")

# These run as scripts from their own directory, so reach the shared
# name/roster module in data/ explicitly.
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from names import RosterIndex, clean as tidy_name  # noqa: E402

# statusId 1 = awaiting reply, 2 = answered. An unanswered question carries a
# placeholder reply ("Reply due: 10 Aug 2026") rather than an empty field, so
# treating replyText as an answer without checking would score a pending
# question as a non-answer.
STATUS_PENDING, STATUS_ANSWERED = 1, 2
_PENDING_PREFIX = "reply due"

SEARCH_TEMPLATE = {
    "searchTab": 0, "keyword": None, "status": None, "questionNumber": None,
    "questionNumberYear": None, "members": [], "ministers": [], "portfolios": [],
    "parliament": None, "dateFrom": None, "dateTo": None, "datePeriod": None,
    "restrictedFrom": None, "restrictedTo": None,
    "column": 1, "direction": 1, "pageSize": 1000, "page": 1,
}


def _request(url: str, payload: dict | None = None, retries: int = 4) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url} failed after {retries} attempts: {last}")


def load_roster_index(path: str = DEFAULT_ROSTER) -> RosterIndex:
    """Roster lookup, shared with every other pipeline (see data/names.py)."""
    return RosterIndex(path)


def _resolve(name: str, index) -> str | None:
    return index.resolve(name) if (name and index) else None


def member_names(parliament: int) -> dict:
    """{memberId -> display name} for a parliament. The search results identify
    the asker only by GUID, so this is how a question gets a person."""
    filters = _request(f"{API}/data/searchFilters")
    members = (filters.get("Members") or {}).get(str(parliament)) or []
    return {m["MemberId"]: m["DisplayName"] for m in members}


def normalise(row: dict, names: dict, index: dict) -> dict:
    reply = (row.get("replyText") or "").strip()
    pending = (row.get("statusId") == STATUS_PENDING
               or reply.lower().startswith(_PENDING_PREFIX))
    asker = tidy_name(names.get(row.get("memberId"), ""))
    minister = tidy_name(row.get("ministerName") or "")
    doc_id = row.get("writtenQuestionsDocumentId")
    return {
        "question_id": doc_id,
        "number": row.get("questionNumber"),
        "year": row.get("questionYear"),
        "parliament": row.get("parliamentNumber"),
        "asker": asker or None,
        "asker_id": _resolve(asker, index),
        "minister": minister or None,
        "minister_id": _resolve(minister, index),
        "portfolio": row.get("ministerialDisplayName"),
        "question": (row.get("questionText") or "").strip(),
        "reply": None if pending else reply,
        "answered": not pending,
        # A reply that is only an attachment has no text to judge; flag it so it
        # is not scored as a non-answer.
        "attachment_only": bool(row.get("attachmentName")) and not pending and not reply,
        "attachment_name": row.get("attachmentName"),
        "released_date": (row.get("questionReleasedDate") or "")[:10] or None,
        "url": f"{SITE}/written-questions/question/{doc_id}" if doc_id else None,
    }


def _months(since: str, until: str):
    """Inclusive month windows as (dateFrom, dateTo) ISO pairs."""
    y, m = int(since[:4]), int(since[5:7])
    end_y, end_m = int(until[:4]), int(until[5:7])
    while (y, m) <= (end_y, end_m):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y:04d}-{m:02d}-01T00:00:00Z", f"{ny:04d}-{nm:02d}-01T00:00:00Z"
        y, m = ny, nm


def _existing(path: str) -> set:
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path) as f:
        for line in f:
            if line.strip():
                out.add(json.loads(line).get("question_id"))
    return out


def fetch(parliament: int = 54, out: str = DEFAULT_OUT, page_size: int = 1000,
          delay: float = 0.4, since: str = "2023-10", until: str | None = None,
          roster: str = DEFAULT_ROSTER) -> None:
    """Fetch written questions **one month at a time**, appending as we go.

    Two hard-won constraints shape this:

    * **Deep pagination 500s.** Paging the unfiltered result set dies at about
      page 102 (~101k rows), so the whole parliament cannot be walked in one
      sequence. `dateFrom` *and* `dateTo` together do filter (either alone is
      ignored), so a month at a time keeps every sequence a few pages deep.
    * **Write as you go.** An earlier version buffered everything and wrote at
      the end; the 500 at page 102 threw away 100,989 rows. Each month is
      flushed on completion and re-runs skip what is already on disk.
    """
    index = load_roster_index(roster)
    names = member_names(parliament)
    until = until or time.strftime("%Y-%m")
    seen = _existing(out)
    print(f"{len(names)} members in parliament {parliament}; "
          f"{len(seen)} question(s) already on disk", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    total = len(seen)
    with open(out, "a") as sink:
        for date_from, date_to in _months(since, until):
            month, page, wrote = date_from[:7], 1, 0
            while True:
                payload = dict(SEARCH_TEMPLATE, page=page, pageSize=page_size,
                               dateFrom=date_from, dateTo=date_to)
                data = _request(f"{API}/data/search", payload)
                batch = data.get("value") or []
                if not batch:
                    break
                for r in batch:
                    if r.get("parliamentNumber") != parliament:
                        continue
                    key = r.get("writtenQuestionsDocumentId") or r.get("id")
                    if key in seen:
                        continue
                    seen.add(key)
                    sink.write(json.dumps(normalise(r, names, index),
                                          ensure_ascii=False) + "\n")
                    wrote += 1
                if len(batch) < page_size:
                    break
                page += 1
                time.sleep(delay)
            sink.flush()
            total += wrote
            print(f"  {month}: +{wrote}  (total {total})", file=sys.stderr)
            time.sleep(delay)

    with open(out) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    print(f"wrote {len(rows)} written questions -> {out}")
    _summarise(rows)


def _summarise(rows: list[dict]) -> None:
    from collections import Counter
    if not rows:
        return
    answered = sum(r["answered"] for r in rows)
    print(f"\nquestions: {len(rows)}   answered: {answered}   "
          f"awaiting reply: {len(rows) - answered}")
    print(f"attachment-only replies: {sum(r['attachment_only'] for r in rows)}")
    dates = sorted(r["released_date"] for r in rows if r["released_date"])
    if dates:
        print(f"released: {dates[0]} .. {dates[-1]}")
    ar = sum(bool(r["asker_id"]) for r in rows)
    mr = sum(bool(r["minister_id"]) for r in rows)
    print(f"asker resolved: {ar}/{len(rows)}   minister resolved: {mr}/{len(rows)}")

    print("\nmost prolific askers:")
    for name, c in Counter(r["asker"] for r in rows if r["asker"]).most_common(8):
        print(f"  {c:6}  {name}")
    print("\nmost questioned ministers:")
    for name, c in Counter(r["minister"] for r in rows if r["minister"]).most_common(8):
        print(f"  {c:6}  {name}")

    lens = [len(r["reply"]) for r in rows if r["reply"]]
    if lens:
        lens.sort()
        print(f"\nreply length: median {lens[len(lens)//2]} chars, "
              f"max {lens[-1]}, under 80 chars: {sum(l < 80 for l in lens)}")

    unresolved = Counter(r["asker"] for r in rows if r["asker"] and not r["asker_id"])
    if unresolved:
        print("\nunresolved askers (not in current roster):")
        for name, c in unresolved.most_common(8):
            print(f"  {c:6}  {name}")


if __name__ == "__main__":
    fire.Fire({"fetch": fetch, "member_names": member_names})
