"""Fetch the build inputs the site is rendered from.

The four `static/*.jsonl` files are generated, large (92 MB for `examples.jsonl`
alone) and regenerated wholesale on every extraction pass, so they are hosted on
HuggingFace rather than committed. See `attribute-extraction/publish_scores.py`
for the why and the upload side.

    python fetch_data.py                 # fetch what is missing or stale
    python fetch_data.py --force         # re-fetch everything
    python fetch_data.py --check         # verify only, download nothing

Verification is the reason this is a script and not a curl in the workflow.
`site/data_manifest.json` is committed and carries a sha256 per file, so a
truncated download, a half-written cache or a repo that moved on since this
commit all fail loudly here rather than producing a website built from the wrong
numbers. CI treats a hash mismatch as a build failure.

No credentials: the dataset is public, so this works anonymously in CI and for
anyone who clones the repo. `huggingface_hub` is used when available (it caches
and resumes); otherwise it falls back to a plain HTTPS GET of the same URL, so
the only hard dependency is the standard library.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "data_manifest.json")
STATIC = os.path.join(HERE, "static")

# Where a published path lands locally. The manifest publishes `site/x.jsonl`;
# the site reads `static/x.jsonl`.
def _local(published):
    return os.path.join(STATIC, os.path.basename(published))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _url(repo, published):
    return (f"https://huggingface.co/datasets/{repo}/resolve/main/"
            f"{published}?download=true")


def _download(repo, published, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        tmp = dest + ".part"
        with urllib.request.urlopen(_url(repo, published)) as r, \
                open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, dest)
        return
    got = hf_hub_download(repo_id=repo, repo_type="dataset",
                          filename=published)
    # Copy out of the HF cache: the cache path is a symlink into a blob store
    # and the site reads `static/` directly.
    with open(got, "rb") as fin, open(dest + ".part", "wb") as fout:
        for chunk in iter(lambda: fin.read(1 << 22), b""):
            fout.write(chunk)
    os.replace(dest + ".part", dest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if the local file already matches")
    ap.add_argument("--check", action="store_true",
                    help="verify local files against the manifest; fetch nothing")
    ap.add_argument("--repo", default=None,
                    help="override the dataset repo in the manifest")
    args = ap.parse_args(argv)

    if not os.path.exists(MANIFEST):
        print(f"no manifest at {MANIFEST}", file=sys.stderr)
        print("run: cd attribute-extraction && python publish_scores.py package",
              file=sys.stderr)
        return 2
    with open(MANIFEST) as f:
        manifest = json.load(f)
    repo = args.repo or manifest["repo"]
    wanted = manifest.get("build_inputs") or []
    if not wanted:
        print("manifest lists no build_inputs", file=sys.stderr)
        return 2

    failed = []
    for published in wanted:
        rec = manifest["files"][published]
        dest = _local(published)
        have = os.path.exists(dest)
        if have and not args.force:
            if _sha256(dest) == rec["sha256"]:
                print(f"  ok       {published}  ({rec['bytes'] / 1e6:.1f} MB)")
                continue
            if args.check:
                print(f"  MISMATCH {published}")
                failed.append(published)
                continue
            print(f"  stale    {published} — re-fetching")
        elif args.check:
            print(f"  MISSING  {published}")
            failed.append(published)
            continue
        print(f"  fetch    {published}  ({rec['bytes'] / 1e6:.1f} MB) "
              f"from {repo}")
        try:
            _download(repo, published, dest)
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAILED   {published}: {exc}", file=sys.stderr)
            failed.append(published)
            continue
        got = _sha256(dest)
        if got != rec["sha256"]:
            print(f"  BAD HASH {published}: got {got[:12]}, "
                  f"expected {rec['sha256'][:12]}", file=sys.stderr)
            failed.append(published)
        else:
            print(f"  ok       {published}")

    if failed:
        print(f"\n{len(failed)} file(s) unavailable or corrupt: "
              f"{', '.join(failed)}", file=sys.stderr)
        print("The site cannot be built from incomplete data, so this is a "
              "hard failure rather than a warning.", file=sys.stderr)
        return 1
    print(f"\n{len(wanted)} build input(s) present and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
