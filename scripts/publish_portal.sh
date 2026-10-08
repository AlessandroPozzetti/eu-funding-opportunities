#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

git add -A -- \
  .github/workflows/nightly-sync.yml \
  .gitignore \
  README.md \
  bandi_eu \
  tests \
  web \
  scripts/publish_portal.sh

if ! git diff --cached --quiet; then
  git commit -m "Publish EU opportunity portal with nightly updates"
fi

git pull --rebase origin main
git push origin main

repository="AlessandroPozzetti/eu-funding-opportunities"
if gh api "repos/$repository/pages" >/dev/null 2>&1; then
  gh api --method PUT "repos/$repository/pages" -f build_type=workflow >/dev/null
else
  gh api --method POST "repos/$repository/pages" -f build_type=workflow >/dev/null
fi

gh workflow run nightly-sync.yml --ref main
printf '\nThe public portal deployment was requested.\n'
printf 'Expected URL: https://alessandropozzetti.github.io/eu-funding-opportunities/\n'
