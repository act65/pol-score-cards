"""Package the v3.0 scores for hosting, and optionally push them to HuggingFace.

WHY THIS EXISTS. Four generated files were tracked in git and they dominate the
repository: across history `hansard_scores_v3.jsonl` accounts for ~1,088 MB and
`site/static/examples.jsonl` for ~601 MB, in a 624 MB `.git`. Worse,
`examples.jsonl` reached 88 MB, and GitHub refuses a push over 100 MB outright,
so the next extraction pass would have been unpushable. None of these files is
hand-written: every one is reproducible from the extraction outputs, which is
the definition of something that does not belong in version control.

Hosting decision: a public HuggingFace Dataset, matching `data/publish_corpus.py`
(which does the same job for the scraped corpus). Free, versioned, anonymous
read, no egress billing. A requester-pays bucket was considered and rejected:
requester-pays bills the DOWNLOADER, who must therefore be an authenticated
cloud principal, which breaks both CI-without-secrets and the public download
links on /data -- an anonymous visitor has no account to bill.

This script does NOT share code with `data/publish_corpus.py`. The subprojects
in this repo communicate through files on disk, never imports (see CLAUDE.md),
and the two artifacts have different schemas: that one publishes scraped
statements, this one publishes scores and the evidence behind them.

    python publish_scores.py package                      # manifest + card, no upload
    python publish_scores.py package --push --repo act65/nz-pol-scorecards

Packaging needs nothing. Pushing needs `pip install huggingface_hub` and auth
(`hf auth login`, or an HF_TOKEN environment variable).
"""

import datetime
import hashlib
import json
import os

import fire

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STAGE = os.path.join(HERE, "hf_release")

# published path -> source path, relative to the repo root.
#
# `site/` is what CI needs to build the website and what `site/fetch_data.py`
# pulls. `raw/` is the extraction output a researcher would actually want: the
# per-statement scores before they were folded into one row per politician.
FILES = {
    "site/politicians.jsonl":  "site/static/politicians.jsonl",
    "site/attributes.jsonl":   "site/static/attributes.jsonl",
    "site/scores.jsonl":       "site/static/scores.jsonl",
    "site/examples.jsonl":     "site/static/examples.jsonl",
    "raw/hansard_scores_v3.jsonl":        "attribute-extraction/hansard_scores_v3.jsonl",
    "raw/acuity_scores_v3.jsonl":         "attribute-extraction/acuity_scores_v3.jsonl",
    "raw/calibration_scores_v3.jsonl":    "attribute-extraction/calibration_scores_v3.jsonl",
    "raw/forthrightness_scores_v3.jsonl": "attribute-extraction/forthrightness_scores_v3.jsonl",
    "raw/resolved_v3.jsonl":              "attribute-extraction/resolved_v3.jsonl",
    # v2.0 output. Retired -- it used a different Civility scale and a retired
    # attribute, so it is NOT comparable with v3.0 (CLAUDE.md). Published
    # anyway, at 27 MB, because two scripts in `archive/` reproduce the v2.0
    # site from it and deleting it would make that history unreproducible.
    "legacy/hansard_scores_full.jsonl":   "attribute-extraction/hansard_scores_full.jsonl",
    "legacy/presser_scores.jsonl":        "attribute-extraction/presser_scores.jsonl",
    "legacy/release_scores.jsonl":        "attribute-extraction/release_scores.jsonl",
}

# Only these are needed to build the site. Keeping the list here rather than in
# the CI workflow means one place to change when a file is added.
BUILD_INPUTS = tuple(k for k in FILES if k.startswith("site/"))

MANIFEST = os.path.join(ROOT, "site", "data_manifest.json")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _lines(path):
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def _describe(repo):
    """Per-file size, line count and digest. The digest is the point: it is
    committed to the repo so a fetch can prove it got the bytes we published."""
    out = {}
    missing = []
    for pub, src in sorted(FILES.items()):
        p = os.path.join(ROOT, src)
        if not os.path.exists(p):
            missing.append(src)
            continue
        out[pub] = {
            "source": src,
            "bytes": os.path.getsize(p),
            "lines": _lines(p),
            "sha256": _sha256(p),
        }
    return out, missing


def _card(repo, files, generated):
    total = sum(f["bytes"] for f in files.values())
    rows = "\n".join(
        f"| `{k}` | {v['lines']:,} | {v['bytes'] / 1e6:.1f} MB |"
        for k, v in sorted(files.items()))
    return f"""---
license: cc-by-4.0
language: [en]
tags: [politics, new-zealand, parliament, hansard, llm-scoring]
pretty_name: NZ Politician Scorecards — v3.0 scores
---

# NZ Politician Scorecards — v3.0 scores

Attribute scores for every member of the 54th New Zealand Parliament, derived
from Hansard by LLM scoring, plus the verbatim quote behind every score.

Generated {generated}. {len(files)} files, {total / 1e6:.0f} MB total.

This repository hosts the **outputs** of
[pol-score-cards](https://github.com/act65/pol-score-cards). They live here
rather than in git because they are regenerated wholesale on every extraction
pass and had grown to dominate the repository.

## Files

| file | rows | size |
|---|---:|---:|
{rows}

`site/` is the display dataset: one row per politician per attribute, plus the
examples behind each score. It is what the website is built from.

`raw/` is the extraction output: one row per window, each carrying the
statements found in it and the score given to each. Use this if you want the
per-statement data rather than per-politician aggregates.

## The six published attributes

Focus, Civility, Rigor, Specificity, Acuity and Calibration — all scored from
the text of the speech itself.

Three further attributes are extracted but **withheld**, and the data for two of
them is in `raw/`: **Veracity** and **Divination** (resolved against searched
sources; `resolved_v3.jsonl` holds the verdicts) and **Forthrightness** (scored
over question/answer pairs). They are withheld because each failed a
measurement gate, not because the data is bad — the reasons are recorded in
`ATTRIBUTES.md` in the repository.

## Please read this before using it

These are **automated estimates, not verified fact**, produced by an imperfect
model over an incomplete sample. A politician with little coverage is scored on
little evidence. Scores are empirical-Bayes shrunk toward the population mean,
so a thin sample is deliberately pulled toward the middle. Nothing here is an
accusation of wrongdoing.

Every score carries the quote it came from, and every quote is verbatim from
Hansard — a 2,000-statement audit found 100% verbatim, 0% spliced. Follow the
quote and judge for yourself.

## Licence

CC-BY-4.0. Hansard itself is Crown copyright, reproduced under the Parliamentary
licence for the reporting of proceedings.
"""


def package(repo: str = "act65/nz-pol-scorecards", push: bool = False,
            stage: str = STAGE):
    """Stage the files, write the manifest and card, optionally upload."""
    files, missing = _describe(repo)
    if missing:
        print("MISSING (not packaged):")
        for m in missing:
            print(f"  {m}")
        if any(k.startswith("site/") for k in BUILD_INPUTS
               if FILES[k] in missing):
            raise SystemExit("a build input is missing; refusing to publish a "
                             "manifest the site cannot be built from")
    generated = datetime.datetime.now().strftime("%Y-%m-%d")
    manifest = {
        "dataset": "nz-pol-scorecards-v3",
        "repo": repo,
        "generated": generated,
        "build_inputs": [k for k in BUILD_INPUTS if k in files],
        "files": files,
    }
    os.makedirs(stage, exist_ok=True)
    for pub, src in FILES.items():
        p = os.path.join(ROOT, src)
        if not os.path.exists(p):
            continue
        dest = os.path.join(stage, pub)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(p):
            continue                      # same size: assume already staged
        with open(p, "rb") as fin, open(dest, "wb") as fout:
            for chunk in iter(lambda: fin.read(1 << 22), b""):
                fout.write(chunk)
    with open(os.path.join(stage, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    with open(os.path.join(stage, "README.md"), "w") as f:
        f.write(_card(repo, files, generated))
    # The manifest is ALSO committed to the repo, small, so that fetch_data.py
    # can verify what it downloaded against what we published.
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    total = sum(v["bytes"] for v in files.values())
    print(f"staged {len(files)} files, {total / 1e6:.0f} MB -> {stage}")
    print(f"manifest -> {MANIFEST}  (commit this)")
    for k, v in sorted(files.items()):
        print(f"  {k:40s} {v['lines']:>9,} rows  {v['bytes'] / 1e6:>6.1f} MB")
    if not push:
        print(f"\npackaged only. To upload:\n"
              f"  pip install huggingface_hub\n"
              f"  hf auth login\n"
              f"  python publish_scores.py package --push --repo {repo}")
        return
    _upload(stage, repo)


def _upload(stage, repo):
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("pip install huggingface_hub")
    api = HfApi()
    api.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=stage, repo_id=repo, repo_type="dataset")
    print(f"pushed -> https://huggingface.co/datasets/{repo}")


def verify(stage: str = STAGE):
    """Re-hash the working files and compare against the committed manifest."""
    if not os.path.exists(MANIFEST):
        raise SystemExit(f"no manifest at {MANIFEST}; run `package` first")
    with open(MANIFEST) as f:
        manifest = json.load(f)
    bad = []
    for pub, rec in sorted(manifest["files"].items()):
        p = os.path.join(ROOT, rec["source"])
        if not os.path.exists(p):
            bad.append((pub, "missing locally"))
            continue
        got = _sha256(p)
        if got != rec["sha256"]:
            bad.append((pub, f"sha256 {got[:12]} != {rec['sha256'][:12]}"))
    for pub, why in bad:
        print(f"  CHANGED  {pub}: {why}")
    if bad:
        raise SystemExit(f"{len(bad)} file(s) differ from the manifest — "
                         f"re-run `package` and re-upload")
    print(f"all {len(manifest['files'])} files match the manifest")


if __name__ == "__main__":
    fire.Fire({"package": package, "verify": verify})
