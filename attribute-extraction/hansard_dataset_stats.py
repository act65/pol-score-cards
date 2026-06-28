"""Statistics over the extracted Hansard scores (task 2a).

Reads the extraction JSONL (window_id, date, examples_by_attribute) produced by
extract_hansard.py and reports:
  * totals — windows, scored (attribute, statement) pairs, distinct statements;
  * per-attribute — count, mean score, score histogram;
  * per-politician — statements scored, words spoken (from the prepped corpus),
    per-attribute mean scores, resolved to canonical roster ids;
  * roster coverage — how many of the 123 current MPs have any scores, who has
    none, and any high-volume speakers that DON'T resolve to the roster (mid-term
    replacement MPs to add — a "cover all politicians" gap).

Tolerant of a partially-written file (safe to run while extraction is in flight).

    python hansard_dataset_stats.py --scores hansard_scores_3mo.jsonl
    python hansard_dataset_stats.py --scores hansard_scores_3mo.jsonl --out STATS_3MO.md
"""

import collections
import json
import os

import fire

import hansard_prep
from roster import Roster, is_probably_mp_name


def _read_scores(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # last line may be mid-write
    return rows


def _hist(scores, bins=10):
    h = [0] * bins
    for s in scores:
        i = min(bins - 1, max(0, int(s * bins)))
        h[i] += 1
    return h


def _words_spoken(corpus, since, R):
    """Words spoken per roster MP, from the prepped (speaker-attributed) corpus."""
    by_day = collections.defaultdict(list)
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("date", "") >= since:
                by_day[r["date"]].append(r)
    words = collections.Counter()
    for parts in by_day.values():
        for b in hansard_prep.prep_day(parts):
            mid = R.match(b["speaker"])
            if mid:
                words[mid] += len(b["text"].split())
    return words


def run(scores="hansard_scores_3mo.jsonl",
        corpus="../data/corpus/hansard.json",
        since="2026-03-01",
        out=None):
    R = Roster()
    rows = _read_scores(scores)

    per_attr_scores = collections.defaultdict(list)
    mp_attr_scores = collections.defaultdict(lambda: collections.defaultdict(list))
    mp_stmt = collections.Counter()
    unresolved = collections.Counter()
    total_pairs = 0
    distinct_statements = set()

    for rec in rows:
        for attr, exs in rec.get("examples_by_attribute", {}).items():
            for e in exs:
                total_pairs += 1
                sc = e.get("score")
                if not isinstance(sc, (int, float)):
                    continue
                per_attr_scores[attr].append(sc)
                name = e.get("politician", "")
                distinct_statements.add((name, e.get("statement", "")[:80]))
                mid = R.match(name)
                if mid:
                    mp_attr_scores[mid][attr].append(sc)
                    mp_stmt[mid] += 1
                elif is_probably_mp_name(name):
                    unresolved[name] += 1

    words = _words_spoken(corpus, since, R)

    L = []
    p = L.append
    p("# Extracted Hansard dataset — statistics\n")
    p(f"Source scores: `{scores}`  (since {since})\n")
    p(f"- windows processed: **{len(rows):,}**")
    p(f"- scored (attribute, statement) pairs: **{total_pairs:,}**")
    p(f"- distinct statements: **{len(distinct_statements):,}**")
    p(f"- roster MPs with ≥1 score: **{len(mp_stmt)}/{len(R.mps)}**\n")

    p("## Per attribute\n")
    p("| attribute | n | mean | histogram 0.0→1.0 |")
    p("|---|---:|---:|---|")
    for attr in sorted(per_attr_scores):
        s = per_attr_scores[attr]
        mean = sum(s) / len(s)
        bars = " ".join(f"{c}" for c in _hist(s))
        p(f"| {attr} | {len(s)} | {mean:.2f} | {bars} |")
    p("")

    p("## Top politicians by statements scored\n")
    p("| MP | party | statements | words spoken | mean civility | mean veracity |")
    p("|---|---|---:|---:|---:|---:|")
    for mid, n in mp_stmt.most_common(25):
        def m(a):
            v = mp_attr_scores[mid].get(a, [])
            return f"{sum(v)/len(v):.2f}" if v else "–"
        p(f"| {R.name(mid)} | {R.party(mid)} | {n} | {words.get(mid, 0):,} | "
          f"{m('civility')} | {m('veracity')} |")
    p("")

    no_scores = [m["id"] for m in R.mps if m["id"] not in mp_stmt]
    p(f"## Roster coverage gaps\n")
    p(f"MPs with NO scores yet ({len(no_scores)}/{len(R.mps)}): "
      f"{', '.join(R.name(i) for i in no_scores[:40])}"
      f"{' …' if len(no_scores) > 40 else ''}\n")
    if unresolved:
        p("### Unresolved speakers (likely roster gaps — add to mps_roster.json)\n")
        p("Names with scored statements that don't map to the 123-MP roster — "
          "mostly mid-term replacement MPs or departed members:\n")
        for name, c in unresolved.most_common(25):
            p(f"- {name}: {c} statements")
        p("")

    text = "\n".join(L)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {out}  ({len(rows)} windows, {total_pairs} pairs)")
    else:
        print(text)


if __name__ == "__main__":
    fire.Fire(run)
