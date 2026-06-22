"""Drop articles that mention none of the tracked MPs.

The scrapers pull whole feeds (e.g. all of Newsroom 'politics'), but many pieces
name no sitting MP — noise for scoring and wasted LLM cost. This keeps only
articles where at least one roster MP appears (full-name match in headline/body,
or as the author), writing a parallel corpus dir. Run before extraction.

    python filter_corpus.py                         # corpus -> corpus_relevant
    python filter_corpus.py --in=corpus --out=corpus_relevant --min_mentions=1

Uses the same matching as corpus_report.py / analyse_corpus.py.
"""

import json
import os
import sys

import corpus_report as cr

HERE = os.path.dirname(os.path.abspath(__file__))


def _mentions(article, roster):
    text = cr._fold((article.get("headline", "") or "") + "\n" + (article.get("content", "") or ""))
    author = cr._fold(article.get("author", ""))
    return sum(1 for r in roster if any(n in text or n in author for n in r["_full"]))


def main():
    src_dir = os.path.join(HERE, "corpus")
    out_dir = os.path.join(HERE, "corpus_relevant")
    min_mentions = 1
    for a in sys.argv[1:]:
        if a.startswith("--in="):
            src_dir = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out_dir = a.split("=", 1)[1]
        elif a.startswith("--min_mentions="):
            min_mentions = int(a.split("=", 1)[1])

    import glob
    roster = cr.load_roster(os.path.join(HERE, "mps_roster.json"))
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src_dir, "*.json")) +
                   glob.glob(os.path.join(src_dir, "*.jsonl")))
    kept_total = seen_total = 0
    print(f"{'source':<16}{'kept':>8}{'dropped':>9}")
    for path in files:
        if os.path.basename(path) in ("manifest.json",):
            continue
        arts = cr._load_articles(path)
        if not arts:
            continue
        kept = [a for a in arts if _mentions(a, roster) >= min_mentions]
        seen_total += len(arts)
        kept_total += len(kept)
        print(f"{os.path.splitext(os.path.basename(path))[0]:<16}{len(kept):>8}{len(arts) - len(kept):>9}")
        with open(os.path.join(out_dir, os.path.basename(path).replace(".jsonl", ".json")),
                  "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
    print(f"{'TOTAL':<16}{kept_total:>8}{seen_total - kept_total:>9}")
    print(f"\nkept {kept_total:,}/{seen_total:,} articles -> {out_dir}/")


if __name__ == "__main__":
    main()
