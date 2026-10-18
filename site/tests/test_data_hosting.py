"""The dataset is hosted, not committed — so the contract has to be tested.

`site/static/*.jsonl` are build artifacts: regenerated wholesale by every
extraction pass, 92 MB for `examples.jsonl` alone, and they had grown to
dominate the repository (~1,088 MB of `hansard_scores_v3.jsonl` across history
in a 624 MB `.git`, with `examples.jsonl` approaching GitHub's 100 MB hard push
limit). They now live on HuggingFace.

That moves a failure mode: the site can now be built from data that is missing,
stale, or truncated. `site/data_manifest.json` is committed and carries a
sha256 per file so `fetch_data.py` can refuse, and these tests check the
pieces line up — a manifest that names a file CI never fetches, or a fetch that
writes where `app.py` does not read, would both produce a green build and a
wrong website.
"""
import json
import os
import subprocess

import pytest

import fetch_data

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SITE, ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pages.yml")


@pytest.fixture(scope="module")
def manifest():
    with open(fetch_data.MANIFEST) as f:
        return json.load(f)


def test_the_manifest_names_a_repo_and_some_build_inputs(manifest):
    assert manifest["repo"]
    assert manifest["build_inputs"], "nothing to fetch means an empty site"


def test_every_build_input_has_a_digest(manifest):
    """Without a hash there is nothing to verify, which is the whole point."""
    for published in manifest["build_inputs"]:
        rec = manifest["files"][published]
        assert len(rec["sha256"]) == 64, published
        assert rec["bytes"] > 0, published
        assert rec["lines"] > 0, published


def test_the_four_files_the_site_reads_are_all_fetched(manifest):
    """app.py loads these at import. If one is not a build input, CI builds a
    site with an empty section and nothing fails."""
    needed = {"politicians.jsonl", "attributes.jsonl",
              "scores.jsonl", "examples.jsonl"}
    fetched = {os.path.basename(p) for p in manifest["build_inputs"]}
    assert needed <= fetched, f"not fetched: {needed - fetched}"


def test_fetch_writes_where_the_site_reads(manifest):
    """The manifest publishes `site/x.jsonl`; the app reads `static/x.jsonl`."""
    for published in manifest["build_inputs"]:
        dest = fetch_data._local(published)
        assert os.path.dirname(dest) == os.path.join(SITE, "static"), dest
        assert os.path.basename(dest) == os.path.basename(published)


def test_the_hosted_data_is_not_tracked_in_git():
    """Re-committing these is the regression this whole change exists to stop."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split("\n")
    tracked = set(out)
    for bad in ("site/static/examples.jsonl",
                "attribute-extraction/hansard_scores_v3.jsonl",
                "attribute-extraction/calibration_scores_v3.jsonl"):
        assert bad not in tracked, f"{bad} is tracked again"


def test_no_tracked_file_is_anywhere_near_the_push_limit():
    """GitHub warns at 50 MB and refuses at 100 MB. Catch the next one early."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    big = []
    for rel in out.split("\0"):
        if not rel:
            continue
        p = os.path.join(ROOT, rel)
        if os.path.exists(p) and os.path.getsize(p) > 20 * 1024 * 1024:
            big.append((rel, os.path.getsize(p) / 1e6))
    assert not big, f"tracked files over 20 MB: {big}"


def test_the_manifest_is_small_enough_to_commit():
    assert os.path.getsize(fetch_data.MANIFEST) < 64 * 1024


def _build_steps():
    """The build job's steps, in order, as (name_or_uses, run) pairs.

    Parsed rather than string-matched: the workflow's own header comment
    mentions freeze.py, so a naive str.index found that instead of the step
    and the ordering assertion was meaningless."""
    yaml = pytest.importorskip("yaml")
    with open(WORKFLOW) as f:
        wf = yaml.safe_load(f)
    return [(st.get("name") or st.get("uses") or "", st.get("run") or "")
            for st in wf["jobs"]["build"]["steps"]]


def test_ci_fetches_before_it_freezes():
    """Order matters: freezing first would build from whatever is on the
    runner, which is nothing."""
    steps = _build_steps()
    fetch = [i for i, (_n, run) in enumerate(steps) if "fetch_data.py" in run]
    freeze = [i for i, (_n, run) in enumerate(steps) if "freeze.py" in run]
    assert fetch, "CI never fetches the dataset"
    assert freeze, "CI never freezes the site"
    assert min(fetch) < min(freeze), "CI freezes before fetching"


def test_ci_restores_the_cache_before_fetching():
    """A cache step after the fetch would download 92 MB every run and then
    helpfully save it for nobody."""
    steps = _build_steps()
    cache = [i for i, (n, _r) in enumerate(steps) if "cache" in n.lower()]
    fetch = [i for i, (_n, run) in enumerate(steps) if "fetch_data.py" in run]
    assert cache and fetch
    assert min(cache) < min(fetch)


def test_ci_caches_on_the_manifest_not_on_a_fixed_key():
    """A fixed cache key would serve stale data forever after a republish."""
    with open(WORKFLOW) as f:
        body = f.read()
    assert "hashFiles('site/data_manifest.json')" in body


def test_the_working_copy_matches_the_manifest(manifest):
    """Catches regenerating data and forgetting to re-publish it. Skips on a
    fresh clone, where the files are simply not there yet."""
    present = [p for p in manifest["build_inputs"]
               if os.path.exists(fetch_data._local(p))]
    if not present:
        pytest.skip("no local dataset; run `python fetch_data.py`")
    stale = [p for p in present
             if fetch_data._sha256(fetch_data._local(p))
             != manifest["files"][p]["sha256"]]
    assert not stale, (
        f"{stale} differ from the manifest — re-run "
        f"`cd attribute-extraction && python publish_scores.py package` "
        f"and re-upload")
