"""Fetch NZ bills and their stage history from the Parliament bills service.

`bills.parliament.nz` is a Blazor WebAssembly app, so the page HTML is empty —
but the JSON API behind it is public, unauthenticated, and answers plain POST
requests (no browser, no API key, no CAPTCHA). Two endpoints are used:

    POST /api/data/search          list bills, filterable by parliament
    GET  /api/data/Bill/{id}       one bill: stage dates, MP in charge, outcome

The CAPTCHA on `legislation.govt.nz` is not in the way: that site holds the
*text* of bills and Acts, which we do not need. Everything required to ask "did
this politician's policy actually become law" — who was in charge, which stages
it reached, on what dates, and whether it got Royal assent — is here.

    python bills.py fetch --parliament 54 --out ../corpus/bills.jsonl
    python bills.py fetch --parliament 54 --limit 5 --out /tmp/sample.jsonl

Output is one JSON object per bill (see `normalise_bill`).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import fire

API = "https://bills.parliament.nz/api"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROSTER = os.path.join(HERE, "..", "mps_roster.json")
DEFAULT_OUT = os.path.join(HERE, "..", "corpus", "bills.jsonl")

# These run as scripts from their own directory, so reach the shared
# name/roster module in data/ explicitly.
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
from names import RosterIndex  # noqa: E402

# The search endpoint validates every field, so the whole filter object has to
# be sent even though most of it is null. `documentPreset: 1` = bill search.
SEARCH_TEMPLATE = {
    "id": None, "documentPreset": 1, "keyword": None, "selectCommittee": None,
    "status": [], "documentTypes": [], "documentSubtypes": [],
    "beforeCommittee": None, "billStages": [], "billTab": "All", "billId": None,
    "includeBillStages": True, "subject": None, "person": None,
    "parliament": None, "dateFrom": None, "dateTo": None, "datePeriod": None,
    "restrictedFrom": None, "restrictedTo": None, "terminatedReason": None,
    "prettyTerminatedReason": None, "terminatedReasons": [],
    "column": 17, "direction": 1, "pageSize": 500, "page": 1,
}

# Bills that reached Royal assent became law; the rest stopped somewhere.
ENACTED_STAGE = "Royal Assent"

# `documentPreset` selects what the search endpoint returns. Beyond bills, two
# more document types carry a named member and so widen Strength beyond the
# ~53% of MPs who ever hold a bill (see data/VOTES.md):
#   3 — a bill lodged in the members' ballot, drawn or not: legislative intent
#       independent of ballot luck, and open to any MP without a portfolio.
#   9 — an Amendment Paper (formerly SOP) in a member's own name: drafting work
#       on someone else's bill.
PRESET_BILLS = 1
PRESET_PROPOSED = 3
PRESET_AMENDMENTS = 9


def _request(url: str, payload: dict | None = None, retries: int = 3) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url} failed after {retries} attempts: {last}")


def load_roster_index(path: str = DEFAULT_ROSTER) -> RosterIndex:
    """Roster lookup, shared with every other pipeline (see data/names.py)."""
    return RosterIndex(path)


def _resolve_member(display: str, sorted_name: str, index) -> str | None:
    """Match 'Hon Paul Goldsmith' or 'Goldsmith, Paul' against the roster."""
    for candidate in (display, sorted_name):
        pid = index.resolve(candidate) if (candidate and index) else None
        if pid:
            return pid
    return None


# `billTab`, `includeBillStages` and the column-17 sort are bill-search options;
# sending them with another preset makes the endpoint 500.
_NON_BILL_OVERRIDES = {"billTab": None, "includeBillStages": None, "column": 4}


def search(preset: int, parliament: int | None = 54) -> list[dict]:
    """Every result for a `documentPreset`, paged out."""
    payload = dict(SEARCH_TEMPLATE)
    if preset != PRESET_BILLS:
        payload.update(_NON_BILL_OVERRIDES)
    payload["documentPreset"] = preset
    payload["parliament"] = str(parliament) if parliament else None
    out, page = [], 1
    while True:
        payload["page"] = page
        data = _request(f"{API}/data/search", payload)
        results = data.get("results") or []
        out.extend(results)
        total = data.get("totalResults", len(out))
        if len(out) >= total or not results:
            break
        page += 1
    return out


def list_bills(parliament: int | None = 54) -> list[dict]:
    """All bills for a parliament (both finished and before the House)."""
    return search(PRESET_BILLS, parliament)


def fetch_bill(bill_id: str) -> dict:
    return _request(f"{API}/data/Bill/{bill_id}")


def normalise_bill(detail: dict, roster_index: dict) -> dict:
    """Flatten the API's bill object into our schema."""
    members = detail.get("Members") or []
    in_charge = members[0] if members else {}
    display = in_charge.get("PreferredFormOfAddress") or ""
    stages = [
        {
            "stage": s.get("StageName"),
            "date": s.get("StageDate"),
            "outcome": s.get("OutcomeName"),
            "type": s.get("TypeName"),
        }
        for s in (detail.get("Stages") or [])
    ]
    stages.sort(key=lambda s: s["date"] or "")
    committees = [c.get("Name")
                  for c in ((detail.get("SelectCommitteeInfo") or {}).get("Committees") or [])]
    current_stage = detail.get("BillCurrentStageName")
    status = detail.get("BillStatusName")
    # `status` lags — bills that have had Royal assent are often still "Active" —
    # so the stage is the reliable signal. A bill that is Terminated without
    # reaching Royal assent was defeated, withdrawn, discharged or lapsed.
    if current_stage == ENACTED_STAGE:
        outcome = "enacted"
    elif status == "Terminated":
        outcome = "terminated"
    else:
        outcome = "in_progress"
    return {
        "bill_id": detail.get("Id"),
        "title": detail.get("Title"),
        "bill_number": detail.get("BillNumber"),
        "parliament": detail.get("ParliamentNumber"),
        "bill_type": detail.get("BillTypeName"),          # Government / Member's / Local / Private
        "status": status,                                 # Active / Terminated
        "current_stage": current_stage,
        "outcome": outcome,                               # enacted / terminated / in_progress
        "enacted": current_stage == ENACTED_STAGE,
        "act": detail.get("Act") or None,
        "description": detail.get("Description"),
        "member_in_charge": display or None,
        "member_in_charge_id": _resolve_member(
            display, in_charge.get("SortedName", ""), roster_index),
        "select_committees": committees,
        "dates": {
            "introduced": detail.get("IntroducedDate"),
            "first_reading": detail.get("FirstReadingDate"),
            "select_committee": detail.get("SelectCommitteeDate"),
            "second_reading": detail.get("SecondReadingDate"),
            "committee_of_whole_house": detail.get("CommitteeOfWholeHouseDate"),
            "third_reading": detail.get("ThirdReadingDate"),
        },
        "stages": stages,
        "legislation_url": detail.get("BillLegislationUrl"),
        "url": f"https://bills.parliament.nz/v/6/{detail.get('Id')}",
    }


def fetch(parliament: int | str = "53,54", out: str = DEFAULT_OUT,
          limit: int | None = None, delay: float = 0.3,
          roster: str = DEFAULT_ROSTER) -> None:
    """List every bill in one or more parliaments and fetch its detail record.

    Defaults to 53 *and* 54: the API files a bill under the parliament that
    introduced it, so bills carried over from the 53rd are still being voted on
    in the 54th and would otherwise be missing from the join."""
    roster_index = load_roster_index(roster)
    parliaments = [int(p) for p in str(parliament).split(",") if p.strip()]
    summaries, seen = [], set()
    for parl in parliaments:
        found = list_bills(parl)
        fresh = [b for b in found if b["id"] not in seen]
        seen.update(b["id"] for b in fresh)
        summaries.extend(fresh)
        print(f"parliament {parl}: {len(found)} bills ({len(fresh)} new)", file=sys.stderr)
    if limit:
        summaries = summaries[:limit]
    print(f"{len(summaries)} bills total; fetching detail...", file=sys.stderr)

    rows, failures = [], []
    for i, summary in enumerate(summaries, 1):
        try:
            rows.append(normalise_bill(fetch_bill(summary["id"]), roster_index))
        except Exception as exc:                     # noqa: BLE001 - report and continue
            failures.append((summary.get("title"), str(exc)))
        if i % 25 == 0 or i == len(summaries):
            print(f"  {i}/{len(summaries)}", file=sys.stderr)
        time.sleep(delay)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} bills -> {out}")
    if failures:
        print(f"{len(failures)} failed:", file=sys.stderr)
        for title, err in failures[:10]:
            print(f"  {title}: {err}", file=sys.stderr)
    _summarise(rows)


def normalise_proposed(row: dict, roster_index: dict) -> dict:
    """A bill lodged in the members' ballot. `publicationDate` is the ballot it
    was entered for; whether it was ever drawn is a separate (luck) question, so
    this records intent only."""
    member = row.get("memberName") or ""
    return {
        "proposed_id": row.get("id"),
        "title": (row.get("title") or "").strip(),
        "parliament": row.get("parliamentNumber"),
        "member": member or None,
        "member_id": _resolve_member(member, member, roster_index),
        "party": row.get("partyName"),
        "ballot_date": row.get("publicationDate"),
        "url": f"https://bills.parliament.nz/v/ProposedMembersBill/{row.get('id')}",
    }


def normalise_amendment(row: dict, roster_index: dict) -> dict:
    """An Amendment Paper. `title` is "<AP number> - <bill>", and `shortTitle`
    is the bill on its own — which is what joins to bills.jsonl, and so to
    "distinct bills engaged"."""
    member = row.get("memberName") or ""
    return {
        "amendment_id": row.get("id"),
        "sop": row.get("sop"),                    # Amendment Paper number
        "bill_title": (row.get("shortTitle") or "").strip() or None,
        "title": (row.get("title") or "").strip(),
        "parliament": row.get("parliamentNumber"),
        "member": member or None,
        "member_id": _resolve_member(member, member, roster_index),
        "published": row.get("publicationDate"),
        "url": f"https://bills.parliament.nz/v/AmendmentToBill/{row.get('id')}",
    }


def _fetch_listing(preset: int, normalise, parliament, out, roster, label) -> None:
    """Shared driver: these two document types are fully described by the search
    listing, so unlike bills they need no per-item detail call."""
    roster_index = load_roster_index(roster)
    parliaments = [int(p) for p in str(parliament).split(",") if p.strip()]
    rows, seen = [], set()
    for parl in parliaments:
        found = search(preset, parl)
        fresh = [r for r in found if r.get("id") not in seen]
        seen.update(r.get("id") for r in fresh)
        rows.extend(normalise(r, roster_index) for r in fresh)
        print(f"parliament {parl}: {len(found)} {label} ({len(fresh)} new)", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    linked = sum(bool(r["member_id"]) for r in rows)
    print(f"wrote {len(rows)} {label} -> {out}")
    print(f"members linked to roster: {linked}/{len(rows)}")
    from collections import Counter
    unlinked = Counter(r["member"] for r in rows if r["member"] and not r["member_id"])
    if unlinked:
        print("unlinked (not in current roster):", file=sys.stderr)
        for m, c in unlinked.most_common(10):
            print(f"  {c:5}  {m}", file=sys.stderr)


def fetch_proposed(parliament: int | str = 54, out: str | None = None,
                   roster: str = DEFAULT_ROSTER) -> None:
    """Members' ballot bills -> proposed_bills.jsonl."""
    out = out or os.path.join(HERE, "..", "corpus", "proposed_bills.jsonl")
    _fetch_listing(PRESET_PROPOSED, normalise_proposed, parliament, out, roster,
                   "proposed members' bills")


def fetch_amendments(parliament: int | str = 54, out: str | None = None,
                     roster: str = DEFAULT_ROSTER) -> None:
    """Amendment Papers -> amendment_papers.jsonl."""
    out = out or os.path.join(HERE, "..", "corpus", "amendment_papers.jsonl")
    _fetch_listing(PRESET_AMENDMENTS, normalise_amendment, parliament, out, roster,
                   "amendment papers")


def _summarise(rows: list[dict]) -> None:
    from collections import Counter
    if not rows:
        return
    print(f"\nbills: {len(rows)}")
    print("\nby outcome:")
    for o, c in Counter(r["outcome"] for r in rows).most_common():
        print(f"  {c:5}  {o}")
    print("\nby type:")
    for t, c in Counter(r["bill_type"] for r in rows).most_common():
        of_type = [r for r in rows if r["bill_type"] == t]
        enacted = sum(r["enacted"] for r in of_type)
        killed = sum(r["outcome"] == "terminated" for r in of_type)
        print(f"  {c:5}  {t:14} enacted {enacted:4}  terminated {killed:4}"
              f"  in progress {len(of_type) - enacted - killed:4}")
    print("\nby current stage:")
    for s, c in Counter(r["current_stage"] for r in rows).most_common():
        print(f"  {c:5}  {s}")
    linked = sum(bool(r["member_in_charge_id"]) for r in rows)
    named = sum(bool(r["member_in_charge"]) for r in rows)
    print(f"\nMP in charge named: {named}/{len(rows)}   linked to roster: {linked}/{len(rows)}")
    unlinked = Counter(r["member_in_charge"] for r in rows
                       if r["member_in_charge"] and not r["member_in_charge_id"])
    if unlinked:
        print("unlinked MPs in charge (not in current roster):")
        for m, c in unlinked.most_common(10):
            print(f"  {c:5}  {m}")


if __name__ == "__main__":
    fire.Fire({"fetch": fetch, "list": list_bills,
               "fetch_proposed": fetch_proposed,
               "fetch_amendments": fetch_amendments})
