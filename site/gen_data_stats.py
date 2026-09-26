"""Precompute the dataset-overview stats the /data page shows.

Reads the site's static JSONL (politicians, scores, examples) plus the manifest,
and (if present) the raw Hansard corpus, and writes a small static/dataset_stats.json
the Flask /data route loads instantly — so the page never has to scan the 26MB
examples file at request time. Re-run after rebuilding the dataset:

    cd site && python gen_data_stats.py
"""

import collections
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
_CORPUS_DIR = os.path.join(os.path.dirname(HERE), "data", "corpus")
CORPUS = os.path.join(_CORPUS_DIR, "hansard.json")
PRESSERS = os.path.join(_CORPUS_DIR, "pressers.json")
PARTY_FILES = {"national": "National", "labour": "Labour", "greens": "Green",
               "act": "ACT", "nzfirst": "NZ First", "tpm": "Te Pāti Māori"}

# Party brand colours, adjusted for legibility on a white chart surface (ACT's
# yellow and NZ First's black are darkened/lightened so fills read).
PARTY_COLORS = {"National": "#00529F", "Labour": "#D82A20", "Green": "#098137",
                "ACT": "#C8960A", "NZ First": "#333333", "Te Pāti Māori": "#B5121B",
                "Independent": "#777777"}

# Per-source descriptions + a link to the primary source site.
SOURCE_META = {
    "Hansard": {
        "label": "Hansard — parliamentary debates",
        "url": "https://www.parliament.nz/en/pb/hansard-debates/rhr/",
        "desc": "The official verbatim record of debate in the House. Adversarial, "
                "on-the-record, and covering every MP — the backbone of the dataset.",
    },
    "Pressers": {
        "label": "Post-Cabinet press conferences",
        "url": "https://www.beehive.govt.nz/",
        "desc": "The Prime Minister and senior ministers' weekly stand-up, taking live "
                "questions from the press gallery. Unscripted and public, but government-side only.",
    },
    "Party releases": {
        "label": "Party press releases",
        "url": None,
        "desc": "Each party's own curated public messaging, published on their websites — "
                "the most polished and on-message of the three voices.",
    },
}
PARTY_URLS = {"National": "https://www.national.org.nz/news",
              "Labour": "https://www.labour.org.nz/news",
              "Green": "https://www.greens.org.nz/news",
              "ACT": "https://www.act.org.nz/news",
              "NZ First": "https://www.nzfirst.nz/news",
              "Te Pāti Māori": "https://www.maoriparty.org.nz/panui"}


def _geo_mean(row, attr_names):
    """Overall score for one MP: geometric mean of their attribute scores (a single
    weak attribute drags it down — same measure the card grid ranks rarity by)."""
    vals = [max(float(v), 1.0) for k, v in row.items()
            if k in attr_names and isinstance(v, (int, float))]
    if not vals:
        return None
    return math.exp(sum(math.log(x) for x in vals) / len(vals))


def _ridgeline_svg(dist, xmin, xmax):
    """A ridgeline: one density curve per party (KDE of its MPs' overall scores),
    in the party's colour, each row directly labelled so identity isn't colour-alone.
    Shared density scale so curve heights are comparable across parties."""
    W, LGUT, RGUT, row_h, peak, top = 760, 132, 22, 52, 40, 16
    plot_w = W - LGUT - RGUT
    height = top + len(dist) * row_h + 44
    grid = [xmin + i * (xmax - xmin) / 80 for i in range(81)]

    def X(v):
        return LGUT + (v - xmin) / (xmax - xmin) * plot_w

    def kde(vals, bw=6.0):
        k = 1.0 / (len(vals) * bw * math.sqrt(2 * math.pi))
        return [k * sum(math.exp(-0.5 * ((x - v) / bw) ** 2) for v in vals) for x in grid]

    dens = [kde(d["values"]) for d in dist]
    gmax = max((max(dd) for dd in dens), default=1.0) or 1.0

    s = [f'<svg viewBox="0 0 {W} {height}" width="100%" role="img" '
         f'aria-label="Distribution of overall scores by party" '
         f'font-family="Inter, Segoe UI, system-ui, sans-serif">']
    for i, (d, dd) in enumerate(zip(dist, dens)):
        base = top + i * row_h + row_h - 12
        pts = " L ".join(f"{X(x):.1f},{base - (y / gmax) * peak:.1f}" for x, y in zip(grid, dd))
        path = f"M {X(xmin):.1f},{base:.1f} L {pts} L {X(xmax):.1f},{base:.1f} Z"
        c, mx = d["color"], X(d["mean"])
        s.append(f'<g><title>{d["party"]}: {d["n"]} MPs · mean {d["mean"]:.0f} '
                 f'· range {d["lo"]:.0f}–{d["hi"]:.0f}</title>')
        s.append(f'<path d="{path}" fill="{c}" fill-opacity="0.5" stroke="{c}" stroke-width="1.5"/>')
        s.append(f'<line x1="{mx:.1f}" y1="{base - peak - 1:.1f}" x2="{mx:.1f}" y2="{base:.1f}" '
                 f'stroke="{c}" stroke-width="1.5" stroke-dasharray="2 2"/>')
        s.append(f'<text x="{LGUT - 12}" y="{base - 5:.0f}" text-anchor="end" font-size="13" '
                 f'font-weight="600" fill="#1e293b">{d["party"]}</text>')
        s.append(f'<text x="{LGUT - 12}" y="{base + 9:.0f}" text-anchor="end" font-size="10" '
                 f'fill="#94a3b8">n={d["n"]} · μ{d["mean"]:.0f}</text></g>')
    ay = top + len(dist) * row_h + 6
    s.append(f'<line x1="{LGUT}" y1="{ay}" x2="{W - RGUT}" y2="{ay}" stroke="#cbd5e1"/>')
    tick = 10 * math.ceil(xmin / 10)
    while tick <= xmax:
        tx = X(tick)
        s.append(f'<line x1="{tx:.1f}" y1="{ay}" x2="{tx:.1f}" y2="{ay + 4}" stroke="#cbd5e1"/>'
                 f'<text x="{tx:.1f}" y="{ay + 16}" text-anchor="middle" font-size="10" '
                 f'fill="#94a3b8">{int(tick)}</text>')
        tick += 10
    s.append(f'<text x="{LGUT}" y="{ay + 31}" font-size="10.5" fill="#64748b">← lower overall score</text>'
             f'<text x="{W - RGUT}" y="{ay + 31}" text-anchor="end" font-size="10.5" '
             f'fill="#64748b">higher →</text></svg>')
    return "".join(s)


def _jsonl(name):
    path = os.path.join(STATIC, name)
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


# --- Instrument checks ------------------------------------------------------
# The three audits that can be run without a human labeller, each of which
# writes a JSON sidecar next to its markdown report:
#
#   check_quotes.py      is every scored statement really in the transcript?
#   attribute_overlap.py are these six attributes measuring six things, or one?
#   resolve.py compare   does searching for evidence beat the model's guess?
#
# Read from disk rather than recomputed here: they need the raw corpus and the
# resolver output, neither of which the site ships. A missing file means that
# audit has not been re-run, and the section is simply omitted rather than
# shown stale.
_EXTRACTION = os.path.join(os.path.dirname(HERE), "attribute-extraction")
_AUDITS = {
    "quotes": "QUOTE_AUDIT_v3.json",
    "overlap": "ATTRIBUTE_OVERLAP_v3.json",
    "resolver": "GUESS_VS_SEARCH.json",
}


def _instrument_checks() -> dict:
    out = {}
    for key, name in _AUDITS.items():
        path = os.path.join(_EXTRACTION, name)
        try:
            with open(path) as f:
                out[key] = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    if "quotes" in out:
        t = out["quotes"]["totals"]
        n = t["n"] or 1
        out["quotes"]["pct"] = {k: round(100 * t[k] / n, 1)
                                for k in ("verbatim", "spliced", "missing", "truncated")}
    if "overlap" in out:
        pairs = [p for p in out["overlap"]["pairs"] if p.get("r") is not None]
        pairs.sort(key=lambda p: -abs(p["r"]))
        out["overlap"]["top_pairs"] = pairs[:6]
        out["overlap"]["redundant"] = [p for p in pairs if abs(p["r"]) >= 0.85]
    return out


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


def _presser_corpus_stats():
    """Raw post-Cabinet presser corpus size (JSON array of transcripts)."""
    if not os.path.exists(PRESSERS):
        return None
    try:
        recs = json.load(open(PRESSERS, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    chars = sum(len(r.get("content", "")) for r in recs)
    return {
        "conferences": len(recs),
        "approx_words": round(chars / 6),
        "bytes": os.path.getsize(PRESSERS),
    }


def _release_corpus_stats():
    """Raw party press-release corpus: article count, per-party, size."""
    per_party, total, chars, size = {}, 0, 0, 0
    for key, party in PARTY_FILES.items():
        path = os.path.join(_CORPUS_DIR, f"{key}.json")
        if not os.path.exists(path):
            continue
        try:
            recs = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        per_party[party] = len(recs)
        total += len(recs)
        chars += sum(len(r.get("content", "")) for r in recs)
        size += os.path.getsize(path)
    if not total:
        return None
    return {
        "articles": total,
        "parties": len(per_party),
        "per_party": dict(sorted(per_party.items(), key=lambda kv: -kv[1])),
        "approx_words": round(chars / 6),
        "bytes": size,
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

    # statements per politician + per source (stream examples so we never hold 26MB)
    stmt_by_mp = collections.Counter()
    by_source = collections.Counter()
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
            by_source[e.get("source", "Hansard")] += 1
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

    # Per-party distribution of overall scores (geometric mean of each MP's
    # attributes), for the ridgeline. Only MPs with >=6 attributes scored, and
    # only parties with >=3 such MPs, so a density curve is meaningful.
    geo_by_party = collections.defaultdict(list)
    for p in politicians:
        if n_attrs(p["id"]) >= 6:
            g = _geo_mean(scores.get(p["id"], {}), attr_names)
            if g is not None:
                geo_by_party[p.get("party") or "Independent"].append(g)
    dist, party_mean = [], {}
    for pp in per_party:                                 # keep the by-statements order
        vals = geo_by_party.get(pp["party"], [])
        if len(vals) >= 3:
            vs = sorted(vals)
            mean = sum(vals) / len(vals)
            party_mean[pp["party"]] = round(mean)
            dist.append({"party": pp["party"], "color": PARTY_COLORS.get(pp["party"], "#777"),
                         "values": vals, "n": len(vals), "mean": mean,
                         "lo": vs[0], "hi": vs[-1]})
    allv = [v for d in dist for v in d["values"]]
    party_dist_svg = ""
    if allv:
        xmin, xmax = math.floor(min(allv) - 3), math.ceil(max(allv) + 3)
        party_dist_svg = _ridgeline_svg(dist, xmin, xmax)

    for pp in per_party:                                 # unify Share (%) + add mean score
        pp["share"] = round(100.0 * pp["statements"] / max(1, total_statements), 1)
        pp["mean_score"] = party_mean.get(pp["party"])

    stats = {
        "totals": {
            "politicians": len(politicians),
            "attributes": len(attributes),
            "statements": total_statements,
            "windows_scored": manifest.get("windows_scored"),
            "date_range": manifest.get("date_range"),
        },
        "per_source": [
            {"source": SOURCE_META.get(s, {}).get("label", s),
             "desc": SOURCE_META.get(s, {}).get("desc", ""),
             "url": SOURCE_META.get(s, {}).get("url"),
             "statements": c,
             "share": round(100.0 * c / max(1, total_statements), 1)}
            for s, c in by_source.most_common()],
        "party_urls": {p: PARTY_URLS.get(p) for p in party_mean},
        "per_party": per_party,
        "per_politician": per_pol,
        "instrument": _instrument_checks(),
        "corpus": _corpus_stats(),
        "presser_corpus": _presser_corpus_stats(),
        "release_corpus": _release_corpus_stats(),
        # `key` indexes app._DOWNLOADS; the template builds the href with
        # url_for so it survives being served under a path prefix (a GitHub
        # project page lives at /<repo>/, where a literal "/download/..." 404s).
        "downloads": [
            {"label": "Attribute scores + evidence (JSONL)", "key": "examples",
             "note": f"{total_statements:,} scored, sourced statements"},
            {"label": "Per-MP scores (JSONL)", "key": "scores",
             "note": "bias-adjusted score per attribute"},
            # The raw Hansard corpus is deliberately NOT here. It is 44 MB and
            # gitignored, so it is absent from every deploy and the button was a
            # 404 on the live site. It belongs on a dataset host (publish_corpus.py)
            # and gets linked back once it is there.
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
