"""Explore a scraped corpus: counts + charts for articles, sources, politicians.

Builds on corpus_report.py (roster + loaders) and writes PNG charts plus a
SUMMARY.md into an output dir. Answers: how much from each source, how coverage
is spread over the term, who gets covered, and how many sources mention each MP.

    python analyse_corpus.py                       # ./corpus -> ./analysis
    python analyse_corpus.py --corpus corpus --out analysis

Needs matplotlib (`pip install matplotlib`). Politician matching is the same
full-name/author match corpus_report uses (note: news bodies still include
comment-section text, which can inflate counts — see corpus_report).
"""

import os
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

import corpus_report as cr  # roster + _load_articles + _fold + _date_key

HERE = os.path.dirname(os.path.abspath(__file__))

# Coarse source types, for the per-politician source-mix (a score built mostly
# off a politician's own party releases is more flattering than one off
# adversarial Hansard or newsworthy reporting).
SOURCE_TYPE = {
    "national": "party", "greens": "party", "act": "party", "top": "party",
    "tpm": "party", "labour": "party", "nzfirst": "party",
    "rnz": "news", "newsroom": "news", "spinoff": "news",
    "hansard": "hansard", "parliament": "official",
}


def _args():
    corpus = os.path.join(HERE, "corpus")
    out = os.path.join(HERE, "analysis")
    for a in sys.argv[1:]:
        if a.startswith("--corpus="):
            corpus = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
    return corpus, out


def load_corpus(corpus_dir):
    """-> {source: [articles]} for every non-empty json/jsonl in the dir."""
    import glob
    by_source = {}
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.json")) +
                   glob.glob(os.path.join(corpus_dir, "*.jsonl")))
    for path in files:
        if os.path.basename(path) == "manifest.json":
            continue
        src = os.path.splitext(os.path.basename(path))[0]
        arts = cr._load_articles(path)
        if arts:
            by_source[src] = arts
    return by_source


def analyse(by_source, roster):
    """Compute every series the charts/summary need, in one pass per article."""
    per_source = {s: len(a) for s, a in by_source.items()}
    month_source = defaultdict(Counter)          # 'YYYY-MM' -> {source: n}
    pol_articles = Counter()                      # politician id -> # articles
    pol_sources = defaultdict(set)                # politician id -> {sources}
    pol_by_source = defaultdict(set)              # source -> {politician ids}
    pol_srctype = defaultdict(Counter)            # politician id -> {src type: n}
    party_articles = Counter()                    # party -> # articles mentioning it
    tokens = Counter()                            # source -> ~tokens (chars/4)
    zero_mp = Counter()                           # source -> # articles mentioning no MP
    name = {r["id"]: r["name"] for r in roster}
    party = {r["id"]: r["party"] for r in roster}

    for src, arts in by_source.items():
        stype = SOURCE_TYPE.get(src, "other")
        for a in arts:
            mk = cr._date_key(a.get("date"))
            if mk:
                month_source[mk[:7]][src] += 1
            body = (a.get("headline", "") or "") + "\n" + (a.get("content", "") or "")
            tokens[src] += len(body) // 4
            text = cr._fold(body)
            author = cr._fold(a.get("author", ""))
            hit_parties = set()
            any_hit = False
            for r in roster:
                if any(n in text or n in author for n in r["_full"]):
                    any_hit = True
                    pol_articles[r["id"]] += 1
                    pol_sources[r["id"]].add(src)
                    pol_by_source[src].add(r["id"])
                    pol_srctype[r["id"]][stype] += 1
                    if party[r["id"]]:
                        hit_parties.add(party[r["id"]])
            for p in hit_parties:
                party_articles[p] += 1
            if not any_hit:
                zero_mp[src] += 1
    return {
        "per_source": per_source, "month_source": month_source,
        "pol_articles": pol_articles, "pol_sources": pol_sources,
        "pol_by_source": pol_by_source, "pol_srctype": pol_srctype,
        "party_articles": party_articles, "tokens": tokens, "zero_mp": zero_mp,
        "name": name, "party": party,
    }


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def chart_articles_per_source(d, path):
    items = sorted(d["per_source"].items(), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(items) + 1))
    ax.barh([s for s, _ in items], [n for _, n in items], color="#3b6ea5")
    for i, (_, n) in enumerate(items):
        ax.text(n, i, f" {n:,}", va="center", fontsize=9)
    ax.set_title("Articles per source")
    ax.set_xlabel("articles")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def chart_timeline(d, path):
    months = sorted(d["month_source"])
    sources = sorted({s for m in d["month_source"].values() for s in m})
    fig, ax = plt.subplots(figsize=(12, 5))
    bottom = [0] * len(months)
    for src in sources:
        vals = [d["month_source"][m].get(src, 0) for m in months]
        ax.bar(months, vals, bottom=bottom, label=src)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_title("Articles per month, stacked by source")
    ax.set_ylabel("articles")
    step = max(1, len(months) // 24)
    ax.set_xticks(range(0, len(months), step))
    ax.set_xticklabels([months[i] for i in range(0, len(months), step)], rotation=90, fontsize=7)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def chart_top_politicians(d, path, top=25):
    items = d["pol_articles"].most_common(top)[::-1]
    fig, ax = plt.subplots(figsize=(9, 0.34 * len(items) + 1))
    ax.barh([d["name"].get(pid, pid) for pid, _ in items], [n for _, n in items], color="#7a611f")
    for i, (_, n) in enumerate(items):
        ax.text(n, i, f" {n:,}", va="center", fontsize=8)
    ax.set_title(f"Top {top} politicians by articles mentioning them")
    ax.set_xlabel("articles")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def chart_politicians_per_source(d, path):
    items = sorted(((s, len(p)) for s, p in d["pol_by_source"].items()), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(items) + 1))
    ax.barh([s for s, _ in items], [n for _, n in items], color="#2f9e52")
    for i, (_, n) in enumerate(items):
        ax.text(n, i, f" {n}", va="center", fontsize=9)
    ax.set_title("Distinct politicians mentioned, per source")
    ax.set_xlabel("politicians")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def chart_articles_per_party(d, path):
    items = sorted(d["party_articles"].items(), key=lambda x: x[1])
    if not items:
        return
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(items) + 1))
    ax.barh([s for s, _ in items], [n for _, n in items], color="#8a3b3b")
    for i, (_, n) in enumerate(items):
        ax.text(n, i, f" {n:,}", va="center", fontsize=9)
    ax.set_title("Articles mentioning each party")
    ax.set_xlabel("articles")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def chart_coverage(d, roster, path):
    counts = [d["pol_articles"].get(r["id"], 0) for r in roster]
    buckets = {"0": 0, "1–9": 0, "10–49": 0, "50+": 0}
    for n in counts:
        buckets["0" if n == 0 else "1–9" if n < 10 else "10–49" if n < 50 else "50+"] += 1
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = {"0": "#b03030", "1–9": "#cf8a2e", "10–49": "#3b6ea5", "50+": "#2f9e52"}
    ax.bar(list(buckets), list(buckets.values()), color=[colors[k] for k in buckets])
    for i, (k, v) in enumerate(buckets.items()):
        ax.text(i, v, str(v), ha="center", va="bottom")
    ax.set_title(f"Coverage across the {len(roster)}-MP roster")
    ax.set_ylabel("politicians")
    ax.set_xlabel("articles mentioning them")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_summary(d, roster, out_dir, total):
    covered = {pid for pid, n in d["pol_articles"].items() if n}
    n_sources_hist = Counter(len(s) for s in d["pol_sources"].values())
    L = ["# Corpus analysis", "",
         f"**{total:,} articles** across **{len(d['per_source'])}** sources; roster "
         f"of **{len(roster)}** politicians, **{len(covered)}** mentioned at least once.",
         "", "Charts: `articles_per_source.png`, `timeline.png`, "
         "`top_politicians.png`, `politicians_per_source.png`.", "",
         "## Articles per source", "", "| Source | Articles | Politicians |", "|---|--:|--:|"]
    for s, n in sorted(d["per_source"].items(), key=lambda x: -x[1]):
        L.append(f"| {s} | {n:,} | {len(d['pol_by_source'].get(s, ()))} |")
    L += ["", "## Most-covered politicians", "", "| Politician | Articles | Sources |", "|---|--:|--:|"]
    for pid, n in d["pol_articles"].most_common(20):
        L.append(f"| {d['name'].get(pid, pid)} | {n:,} | {len(d['pol_sources'][pid])} |")
    L += ["", "## Source breadth per politician",
          "(how many distinct sources mention each — single-source MPs are the fragile ones)", ""]
    for k in sorted(n_sources_hist):
        L.append(f"- mentioned in **{k}** source(s): {n_sources_hist[k]} politicians")

    L += ["", "## Source-mix for the most-covered MPs",
          "(share of each MP's articles from their own party's press releases vs "
          "independent news/Hansard — a high party-release share flatters them)", "",
          "| Politician | Articles | % party | % news | % Hansard |", "|---|--:|--:|--:|--:|"]
    for pid, n in d["pol_articles"].most_common(15):
        st, tot = d["pol_srctype"][pid], (n or 1)
        L.append(f"| {d['name'].get(pid, pid)} | {n:,} | {100 * st.get('party', 0) // tot}% "
                 f"| {100 * st.get('news', 0) // tot}% | {100 * st.get('hansard', 0) // tot}% |")

    # Relevance: how many scraped articles mention NO tracked MP (filter candidates).
    noise = sum(d["zero_mp"].values())
    L += ["", "## Relevance (articles mentioning no tracked MP)",
          f"**{noise:,} of {total:,}** ({100*noise/total:.0f}%) mention none of the "
          f"{len(roster)} MPs — drop these before extraction (`filter_corpus.py`).", "",
          "| Source | Articles | No-MP | ~Tokens |", "|---|--:|--:|--:|"]
    for s, n in sorted(d["per_source"].items(), key=lambda x: -x[1]):
        L.append(f"| {s} | {n:,} | {d['zero_mp'].get(s, 0):,} | {d['tokens'].get(s, 0):,} |")
    L.append(f"| **total** | **{total:,}** | **{noise:,}** | **{sum(d['tokens'].values()):,}** |")

    L += ["", "## Articles per party", "", "| Party | Articles |", "|---|--:|"]
    for p, n in sorted(d["party_articles"].items(), key=lambda x: -x[1]):
        L.append(f"| {p} | {n:,} |")

    gaps = sorted(r["name"] for r in roster if not d["pol_articles"].get(r["id"]))
    L += ["", f"## Coverage gaps — {len(gaps)} of {len(roster)} MPs with zero articles", ""]
    L.append(", ".join(gaps) if gaps else "_Every rostered MP has at least one article._")
    L.append("")
    with open(os.path.join(out_dir, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    corpus_dir, out_dir = _args()
    os.makedirs(out_dir, exist_ok=True)
    roster = cr.load_roster(os.path.join(HERE, "mps_roster.json"))
    by_source = load_corpus(corpus_dir)
    if not by_source:
        raise SystemExit(f"no non-empty corpus files in {corpus_dir}")
    total = sum(len(a) for a in by_source.values())
    print(f"analysing {total:,} articles from {len(by_source)} sources...")
    d = analyse(by_source, roster)

    chart_articles_per_source(d, os.path.join(out_dir, "articles_per_source.png"))
    chart_timeline(d, os.path.join(out_dir, "timeline.png"))
    chart_top_politicians(d, os.path.join(out_dir, "top_politicians.png"))
    chart_politicians_per_source(d, os.path.join(out_dir, "politicians_per_source.png"))
    chart_articles_per_party(d, os.path.join(out_dir, "articles_per_party.png"))
    chart_coverage(d, roster, os.path.join(out_dir, "coverage.png"))
    write_summary(d, roster, out_dir, total)
    print(f"wrote charts + SUMMARY.md to {out_dir}/")


if __name__ == "__main__":
    main()
