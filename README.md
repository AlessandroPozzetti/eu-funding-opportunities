# EU Funding Opportunities

This starter project collects opportunities from the European Commission's [Funding & Tenders Portal API](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) every evening and compares currently open opportunities with a short project description.

## Data collected

The first version imports funding opportunities marked *Open* or *Forthcoming* by the public SEDIA API. It reads every result page and stores the official identifier, title, programme, dates, description, conditions, keywords, budget, source URL, and original metadata. Records are stored in `data/opportunities.jsonl`, one JSON object per line. Opportunities that disappear from the current list remain in the history with `listed: false`.

Matching only suggests opportunities marked *Open* with a future deadline. If a deadline is missing or cannot be parsed, the record remains in the dataset but is not suggested automatically. The portal's status can be out of date, so the deadline is checked separately.

Add `--include-tenders` to collect procurement notices from the same portal. This does **not** cover all European public procurement notices published by [TED](https://ted.europa.eu/). The funding query uses API categories `type=1,2,8` from the Commission's examples; the tender query uses `type=0`. The first full run must confirm the coverage of these categories.

## Run locally

Requires Python 3.11 or newer. No third-party packages or private API keys are needed.

```bash
python3 -m unittest discover -s tests -v
python3 -m bandi_eu sync
python3 -m bandi_eu match "We develop sustainable batteries for the power grid" --keywords battery recycling energy
```

To include procurement notices:

```bash
python3 -m bandi_eu sync --include-tenders
```

Matching returns a **lexical relevance score from 0 to 100**, matching words, a deadline, and a source link. The score measures text overlap. It is not an estimate of award probability and does not check eligibility, geography, or applicant type. English keywords work best because the imported records are in English.

## Publish the repository

Sign in to the GitHub CLI with `gh auth login -h github.com`, then run these commands from this project directory:

```bash
git init -b main
git add .
git commit -m "Start EU funding collection"
gh repo create eu-funding-opportunities --private --source=. --remote=origin --push
```

The repository is private by default in this example. If the scheduled workflow cannot commit updates, check *Settings → Actions → General → Workflow permissions* and allow the `GITHUB_TOKEN` to write repository contents. The workflow requests `contents: write` only for the data update.

## Nightly update

The workflow in `.github/workflows/nightly-sync.yml` is provisionally scheduled for **21:00 Europe/Rome**, including daylight saving time changes. It can also be started manually from the *Actions* tab. After a complete collection, it commits the JSONL file. If the API fails or pagination is incomplete, the existing file remains intact and the workflow fails.

[GitHub notes that scheduled runs may be delayed or dropped](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). A dedicated scheduler with monitoring is required if execution at an exact minute must be guaranteed. GitHub can also disable schedules in a public repository after 60 days without activity.

## Next steps for the portal

1. Expose the records to a web application with filters for programme, deadline, and opportunity type.
2. Ask users for a project description, keywords, and essential eligibility details such as organisation type, country, size, and partners.
3. Improve multilingual matching with semantic search, explainable results, and a separate check of official eligibility requirements.
4. As the dataset and user base grow, move persistence from Git to a managed database and monitor each update.

The official call documents and conditions remain the authoritative source before submitting an application.
