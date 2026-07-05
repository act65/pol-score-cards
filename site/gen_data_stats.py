"""Precompute the dataset-overview stats the /data page shows.

Reads the site's static JSONL (politicians, scores, examples) plus the manifest,
and (if present) the raw Hansard corpus, and writes a small static/dataset_stats.json
the Flask /data route loads instantly — so the page never has to scan the 26MB
examples file at request time. Re-run after rebuilding the dataset:

    cd site && python gen_data_stats.py
"""

import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
CORPUS = os.path.join(os.path.dirname(HERE), "data", "corpus", "hansard.json")


def _jsonl(name):
    path = os.path.join(STATIC, name)
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _corpus_stats():
    """Raw Hansard corpus size, if the corpus file is on disk (data subproject)."""
    if not os.path.exists(CORPUS):
        return None
    parts, dates, chars = 0, set(), 0
    for line in open(CORPUS, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        parts += 1
        if rec.get("date"):
            dates.add(rec["date"])
        chars += len(rec.get("content", ""))
    return {
        "transcript_parts": parts,
        "sitting_days": len(dates),
        "approx_words": round(chars / 6),          # ~6 chars/word incl. spaces
        "bytes": os.path.getsize(CORPUS),
    }


def main():
    politicians = _jsonl("politicians.jsonl")
    attributes = _jsonl("attributes.jsonl")
    scores = {s["politician_id"]: s for s in _jsonl("scores.jsonl")}
    manifest = {}
    mpath = os.path.join(STATIC, "manifest.json")
    if os.path.exists(mpath):
        manifest = json.load(open(mpath))

    attr_names = {a["name"] for a in attributes}

    # statements per politician (stream examples so we never hold 26MB in memory)
    stmt_by_mp = collections.Counter()
    total_statements = 0
    epath = os.path.join(STATIC, "examples.jsonl")
    if os.path.exists(epath):
        for line in open(epath, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            stmt_by_mp[e.get("politician_id")] += 1
            total_statements += 1

    def n_attrs(mid):
        s = scores.get(mid, {})
        return len([k for k in s if k in attr_names])

    per_pol = []
    for p in politicians:
        mid = p["id"]
        per_pol.append({
            "id": mid, "name": p["name"], "party": p.get("party") or "Independent",
            "statements": stmt_by_mp.get(mid, 0), "n_attrs": n_attrs(mid),
        })
    per_pol.sort(key=lambda r: r["statements"], reverse=True)

    party = collections.defaultdict(lambda: {"mps": 0, "statements": 0})
    for r in per_pol:
        party[r["party"]]["mps"] += 1
        party[r["party"]]["statements"] += r["statements"]
    per_party = sorted(
        ({"party": k, **v} for k, v in party.items()),
        key=lambda r: r["statements"], reverse=True)

    stats = {
        "totals": {
            "politicians": len(politicians),
            "attributes": len(attributes),
            "statements": total_statements,
            "windows_scored": manifest.get("windows_scored"),
            "date_range": manifest.get("date_range"),
        },
        "per_source": [{"source": "Hansard (54th Parliament debates)",
                        "statements": total_statements, "share": 100.0}],
        "per_party": per_party,
        "per_politician": per_pol,
        "corpus": _corpus_stats(),
        "downloads": [
            {"label": "Raw Hansard corpus (JSONL)", "note": "speaker transcripts, 54th term", "url": None},
            {"label": "Extracted attribute scores (JSONL)", "note": "scores + evidence statements", "url": None},
        ],
    }
    out = os.path.join(STATIC, "dataset_stats.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"wrote {out}")
    print(f"  {stats['totals']['politicians']} MPs, {total_statements:,} statements, "
          f"{len(per_party)} parties; corpus={'yes' if stats['corpus'] else 'absent'}")


if __name__ == "__main__":
    main()
