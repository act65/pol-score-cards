#!/usr/bin/env bash
# Drop the generated data files from every commit in git history.
#
# WHY. These paths account for roughly 2 GB of blobs across ~95 revisions, in a
# 624 MB .git. Nothing in any of those revisions is source: every file is
# reproduced by an extraction run or by build_v2_dataset.py, and the current
# copies are hosted on HuggingFace (see DEPLOY.md). Untracking them in 6cb95c4
# stopped the growth; only a history rewrite reclaims what is already there.
#
# THIS IS DESTRUCTIVE AND IRREVERSIBLE.
#   * Every commit after the first touched path gets a NEW SHA. The history is
#     not edited, it is replaced.
#   * It requires `git push --force` to origin/main.
#   * Anyone else holding a clone must re-clone. Their branches will not merge:
#     the commits they are based on no longer exist.
#   * Open pull requests against the old SHAs break.
#   * Links to a commit SHA -- in issues, in notes, in this repo's own docs --
#     stop resolving.
#
# Check that list against reality before running. On a solo repo with no open
# PRs it is a cheap trade; with collaborators it is a coordinated job.
#
# RUN IT ONLY AFTER:
#   1. publish_scores.py has pushed the dataset to HuggingFace, and
#   2. a CI run has gone green fetching from there -- proving the data is
#      reachable without these blobs, and
#   3. the mirror backup in step 1 below exists.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP="${BACKUP:-$HOME/pol-score-cards-prepurge-$(date +%Y%m%d-%H%M%S).git}"

PATHS=(
  site/static/examples.jsonl
  site/static/scores.jsonl
  site/static/politicians.jsonl
  site/static/attributes.jsonl
  attribute-extraction/hansard_scores_v3.jsonl
  attribute-extraction/acuity_scores_v3.jsonl
  attribute-extraction/calibration_scores_v3.jsonl
  attribute-extraction/forthrightness_scores_v3.jsonl
  attribute-extraction/resolved_v3.jsonl
  attribute-extraction/hansard_scores_full.jsonl
  attribute-extraction/presser_scores.jsonl
  attribute-extraction/release_scores.jsonl
  attribute-extraction/site_data_full/examples.jsonl
  attribute-extraction/site_data_v3/examples.jsonl
  attribute-extraction/site_data_v3_prior/examples.jsonl
  attribute-extraction/site_data_v2/examples.jsonl
)

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo is not installed. It is the supported tool for this;"
  echo "git filter-branch is deprecated and mishandles tags and merges."
  echo
  echo "  pip install git-filter-repo"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit or stash first -- rewriting history"
  echo "with uncommitted changes is a good way to lose them."
  exit 1
fi

echo "=== Step 1: mirror backup ==="
# Reuse an existing one rather than writing a second 624 MB copy. Pass
# BACKUP=... to force a specific path, or delete the old one to take a fresh
# snapshot.
EXISTING="$(ls -1d "$HOME"/pol-score-cards-prepurge-*.git 2>/dev/null | tail -1 || true)"
if [ -n "$EXISTING" ] && [ -z "${BACKUP_FORCE:-}" ]; then
  echo "  reusing existing backup: $EXISTING"
  echo "  (set BACKUP_FORCE=1 to take a fresh one)"
  BACKUP="$EXISTING"
else
  echo "  -> $BACKUP"
  git clone --mirror . "$BACKUP"
fi
echo "  To undo everything, including a force-push:"
echo "    git -C $BACKUP push --mirror git@github.com:act65/pol-score-cards.git"
echo

echo "=== Step 2: size before ==="
du -sh .git
echo

echo "=== Step 3: rewrite ==="
# --invert-paths keeps everything EXCEPT these paths. --force because the repo
# has an origin, and filter-repo refuses to rewrite a non-fresh clone without it.
ARGS=()
for p in "${PATHS[@]}"; do ARGS+=(--path "$p"); done
git filter-repo --force --invert-paths "${ARGS[@]}"
echo

echo "=== Step 4: repack ==="
# filter-repo expires reflogs and drops the original refs itself; this gc is
# what actually returns the disk.
git reflog expire --expire=now --all
git gc --prune=now --aggressive
echo

echo "=== Step 5: size after ==="
du -sh .git
echo
echo "filter-repo removes 'origin' deliberately, so a stale remote cannot be"
echo "pushed to by reflex. Restore it and push only after checking:"
echo
echo "  git remote add origin git@github.com:act65/pol-score-cards.git"
echo "  git log --oneline -5                       # is the history sane?"
echo "  cd site && python fetch_data.py --check    # data still reachable?"
echo "  pytest -q                                  # suite still green?"
echo "  git push --force origin main"
echo
echo "The other branches (v3, feature/dynamic-scorecard-display) were rewritten"
echo "too, and each needs its own --force push if you still want it."
