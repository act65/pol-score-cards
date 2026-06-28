"""Hansard coverage report — does corpus/hansard.json have everything of interest?

No network, no LLM. Reads the scraped Hansard JSONL and reports:
  * record/day/word/token totals and per-year, per-month sitting-day counts;
  * a 53rd- vs 54th-Parliament split (current MPs sit in the 54th, from the
    2023-10-14 election; the House first met 2023-12-05);
  * content-integrity checks (parts per day, words per day, tiny records);
  * SUSPECTED SILENT GAPS — NZ Parliament sits Tue/Wed/Thu, so inside a week
    that already has a sitting day, a missing Tue/Wed/Thu is likely a render
    failure to re-scrape (vs a whole missing week = genuine recess).

    python hansard_coverage.py                       # report to stdout
    python hansard_coverage.py --out HANSARD_COVERAGE.md
    python hansard_coverage.py --corpus corpus/hansard.json
"""

import argparse
import collections
import datetime
import json
import os
import statistics

# 54th Parliament: election 2023-10-14; House first met 2023-12-05; the term we
# care about for *current* MPs. Anything earlier is the 53rd Parliament.
ELECTION_54 = datetime.date(2023, 10, 14)
TERM_END = datetime.date(2026, 11, 7)
SITTING_WEEKDAYS = {1, 2, 3}  # Tue, Wed, Thu (Mon=0 .. Sun=6)


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def _d(s):
    return datetime.date.fromisoformat(s)


def suspected_gaps(days):
    """Weekdays (Tue/Wed/Thu) with no transcript that fall inside a week which
    *does* have sitting days — i.e. likely silent scrape failures, not recess."""
    by_week = collections.defaultdict(set)
    for d in days:
        iso = d.isocalendar()
        by_week[(iso[0], iso[1])].add(d)
    gaps = []
    for (_y, _w), ds in by_week.items():
        present = {d.weekday() for d in ds}
        monday = min(ds) - datetime.timedelta(days=min(ds).weekday())
        for wd in sorted(SITTING_WEEKDAYS - present):
            cand = monday + datetime.timedelta(days=wd)
            # only flag gaps bracketed by sitting days within the same week
            if any(d.weekday() < wd for d in ds) and any(d.weekday() > wd for d in ds):
                gaps.append(cand)
    return sorted(gaps)


def report(path):
    recs = load(path)
    days = sorted({_d(r["date"]) for r in recs if r.get("date")})
    L = []
    p = L.append

    p("# Hansard coverage report\n")
    p(f"Source: `{path}`\n")
    total_words = sum(len(r.get("content", "").split()) for r in recs)
    p(f"- **Records (parts):** {len(recs):,}")
    p(f"- **Distinct sitting days:** {len(days):,}")
    p(f"- **Date range:** {days[0]} → {days[-1]}")
    p(f"- **Total words:** {total_words:,}  (~{int(total_words * 1.33):,} tokens @1.33)\n")

    # 53rd vs 54th
    pre = [d for d in days if d < ELECTION_54]
    cur = [d for d in days if d >= ELECTION_54]
    p("## Parliament split\n")
    p(f"- 53rd Parliament (pre-{ELECTION_54}, NOT current MPs): **{len(pre)} days** "
      f"({pre[0]} → {pre[-1]})" if pre else "- 53rd Parliament: none")
    p(f"- 54th Parliament (current MPs): **{len(cur)} days** ({cur[0]} → {cur[-1]})\n")
    in_term = [d for d in cur if d <= TERM_END]
    p(f"  → in-scope for v2.0 (54th term, ≤ {TERM_END}): **{len(in_term)} days**\n")

    # per-year / per-month
    p("## Sitting days per year\n")
    by_year = collections.Counter(d.year for d in days)
    for y in sorted(by_year):
        p(f"- {y}: {by_year[y]}")
    p("")
    p("## Sitting days per month (54th Parliament only)\n")
    by_month = collections.Counter(f"{d:%Y-%m}" for d in cur)
    for m in sorted(by_month):
        bar = "█" * by_month[m]
        p(f"- {m}: {by_month[m]:>2}  {bar}")
    p("")

    # content integrity
    parts = collections.Counter(r["date"] for r in recs)
    wc = [len(r.get("content", "").split()) for r in recs]
    words_per_day = collections.Counter()
    for r in recs:
        words_per_day[r["date"]] += len(r.get("content", "").split())
    tiny = [r for r in recs if len(r.get("content", "").split()) < 50]
    thin_days = sorted(d for d, w in words_per_day.items() if w < 2000)
    p("## Content integrity\n")
    p(f"- Parts per record-day: min {min(parts.values())}, "
      f"median {int(statistics.median(list(parts.values())))}, max {max(parts.values())}")
    p(f"- Words per part: min {min(wc)}, median {int(statistics.median(wc))}, max {max(wc)}")
    p(f"- Records under 50 words: {len(tiny)}")
    p(f"- Days with <2000 words total (suspiciously thin, may be partial): {len(thin_days)}")
    for d in thin_days[:20]:
        p(f"    - {d}: {words_per_day[d]:,} words / {parts[d]} parts")
    p("")

    # suspected silent gaps
    gaps = suspected_gaps([d for d in cur if d <= TERM_END])
    p("## Suspected silent gaps (re-scrape candidates)\n")
    p("Tue/Wed/Thu with no transcript, *bracketed* by sitting days in the same "
      "week — likely render failures rather than recess.\n")
    if gaps:
        for g in gaps:
            p(f"- {g:%Y-%m-%d} ({g:%A})")
    else:
        p("- None — every mid-week weekday inside a sitting week has a transcript. ✅")
    p("")
    return "\n".join(L), {"days": days, "in_term": in_term, "gaps": gaps,
                          "thin_days": thin_days, "recs": len(recs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hansard.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    text, _ = report(args.corpus)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
