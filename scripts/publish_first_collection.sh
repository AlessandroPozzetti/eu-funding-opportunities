#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

git add -A -- \
  .github/workflows/nightly-sync.yml \
  README.md \
  bandi_eu \
  data/README.md \
  data/opportunities.jsonl \
  scripts/publish_first_collection.sh \
  tests \
  web

if ! git diff --cached --quiet; then
  git commit -m "Collect EU opportunities and add matching portal"
fi

git push origin main
gh workflow run nightly-sync.yml

printf '\nPublished the first collection and requested a fresh GitHub Actions run.\n'
printf 'Open the run URL printed above, or use: gh run list --workflow nightly-sync.yml\n'
