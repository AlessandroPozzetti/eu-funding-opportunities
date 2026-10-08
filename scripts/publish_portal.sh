#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

python3 -m unittest discover -s tests -v
node tests/test_matcher.js
python3 scripts/evaluate_matcher.py --check

git add -A -- \
  .github \
  .gitignore \
  README.md \
  CONTRIBUTING.md \
  docs \
  data/README.md \
  bandi_eu \
  evaluation \
  tests \
  web \
  scripts

if ! git diff --cached --quiet; then
  git commit -m "Update opportunity portal"
fi

git pull --rebase origin main
git push origin main

repository="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
if gh api "repos/$repository/pages" >/dev/null 2>&1; then
  gh api --method PUT "repos/$repository/pages" -f build_type=workflow >/dev/null
else
  gh api --method POST "repos/$repository/pages" -f build_type=workflow >/dev/null
fi

gh workflow run nightly-sync.yml --ref main
printf '\nThe public portal deployment was requested.\n'
gh api "repos/$repository/pages" --jq '.html_url'
