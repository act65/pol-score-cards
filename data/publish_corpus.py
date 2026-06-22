"""Package the scraped corpus and publish it to HuggingFace Datasets.

Hosting decision: a public HuggingFace Dataset — free, versioned, discoverable,
no egress billing — so others can reuse the raw statements. This script writes a
`manifest.json` (per-source counts, date coverage, sha256) and a `README.md`
dataset card into the corpus dir, then optionally pushes the whole dir.

    python publish_corpus.py --corpus corpus                         # package only
    python publish_corpus.py --corpus corpus --repo you/nz-pol-statements --push

Pushing needs `pip install huggingface_hub` and auth (HF_TOKEN env var or
`huggingface-cli login`). Packaging (manifest + card) needs neither — run it any
time to inspect what would be published.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re

DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SCHEMA_FIELDS = ["headline", "date", "author", "content", "url"]


def _date_key(value):
    m = DATE_RE.search(str(value or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _load(path):
    with open(path) as f:
        text = f.read().strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(corpus_dir, term_start, term_end):
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.json")) +
                   glob.glob(os.path.join(corpus_dir, "*.jsonl")))
    files = [f for f in files if os.path.basename(f) != "manifest.json"]
    sources, total = [], 0
    for path in files:
        arts = _load(path)
        dates = sorted(d for d in (_date_key(a.get("date")) for a in arts) if d)
        total += len(arts)
        sources.append({
            "file": os.path.basename(path),
            "articles": len(arts),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "n_with_date": len(dates),
            "bytes": os.path.getsize(path),
            "sha256": _sha256(path),
        })
    return {
        "name": "NZ politician public-statement corpus",
        "term_window": {"start": term_start, "end": term_end},
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "total_articles": total,
        "schema": {f: "string" for f in SCHEMA_FIELDS},
        "sources": sources,
    }


def dataset_card(manifest):
    m = manifest
    rows = "\n".join(
        f"| {s['file']} | {s['articles']:,} | "
        f"{(s['date_min'] or '—')} → {(s['date_max'] or '—')} |"
        for s in m["sources"])
    return f"""---
license: cc-by-4.0
language: [en, mi]
task_categories: [text-classification, text-scoring]
pretty_name: NZ Politician Public-Statement Corpus
tags: [politics, new-zealand, accountability]
---

# {m['name']}

Public statements by New Zealand politicians — party press releases, news
reporting, Beehive releases, and Hansard — scraped for the NZ Politician
Scorecards project. Window: **{m['term_window']['start']} → {m['term_window']['end']}**
(the 54th Parliament term). **{m['total_articles']:,} articles.**

This is the *raw* corpus (the inputs to scoring), not the scores. Each record:

```json
{{ {", ".join(f'"{f}": "..."' for f in SCHEMA_FIELDS)} }}
```

## Sources

| File | Articles | Date range |
|---|---|---|
{rows}

## Provenance & caveats

- Scraped from public web pages; see the project repo for the per-source scrapers.
- Coverage is uneven across politicians and sources — a press release is curated,
  Hansard is adversarial, news is newsworthy. **Do not** read raw article counts
  as importance. See `manifest.json` for exact per-source counts and hashes.
- Generated: {m['generated_utc']}.

## Licence

Released CC-BY-4.0. Underlying statements remain the property of their authors /
publishers; this corpus is provided for research and accountability use.
"""


def push(corpus_dir, repo):
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=corpus_dir, repo_id=repo, repo_type="dataset")
    print(f"pushed {corpus_dir} -> https://huggingface.co/datasets/{repo}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--since", default="2023-10-06")
    ap.add_argument("--until", default="2026-11-07")
    ap.add_argument("--repo", help="HuggingFace dataset id, e.g. you/nz-pol-statements")
    ap.add_argument("--push", action="store_true", help="upload to HuggingFace (needs --repo + auth)")
    args = ap.parse_args()

    manifest = build_manifest(args.corpus, args.since, args.until)
    with open(os.path.join(args.corpus, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.corpus, "README.md"), "w", encoding="utf-8") as f:
        f.write(dataset_card(manifest))
    print(f"{manifest['total_articles']:,} articles across {len(manifest['sources'])} source file(s)")
    print(f"wrote {args.corpus}/manifest.json and {args.corpus}/README.md")

    if args.push:
        if not args.repo:
            raise SystemExit("--push needs --repo you/dataset-name")
        push(args.corpus, args.repo)
    elif args.repo:
        print(f"(dry run — re-run with --push to upload to {args.repo})")


if __name__ == "__main__":
    main()
