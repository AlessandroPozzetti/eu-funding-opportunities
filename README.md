# EU Opportunity Finder

A small, testable project that collects grants and procurement notices from the European Commission's [Funding & Tenders Portal API](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) and matches open opportunities to a project description.

## Project structure

| Path | Purpose |
| --- | --- |
| `bandi_eu/core.py` | API client, normalization, collection, storage, and lexical matching |
| `bandi_eu/site.py` | Compact snapshot and static portal builder |
| `bandi_eu/web.py` | Local HTTP server and JSON endpoints |
| `web/` | Responsive portal interface |
| `data/opportunities.jsonl` | Collected records, one JSON object per line |
| `tests/` | Collector and portal tests |
| `.github/workflows/nightly-sync.yml` | Nightly and manual GitHub Actions collection |
| `scripts/publish_first_collection.sh` | One-time publisher for the first collection and portal |
| `scripts/publish_portal.sh` | Publish the browser portal and enable GitHub Pages |

## First collection

Python 3.10 or newer is required. There are no third-party packages or private API keys.

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m bandi_eu sync
python3 -m bandi_eu audit
```

`sync` collects **both grants and tenders** by default. It requests every page for active and forthcoming opportunities. It validates the reported total before replacing the dataset, so an incomplete API response does not overwrite the previous collection. It prints separate grant and tender counts at the end.

`audit` reports how many collected records are currently open, how many belong to each type, and how many are missing a deadline, source title, description, or source URL. Review this summary after each collection and spot-check several official links. See [data/README.md](data/README.md) for the first collection report and source data caveats.

The collector stores the official identifier, source reference, type, title, programme, opening and deadline dates, description, conditions, keywords, budget, source URL, and original metadata. Records removed from the current API result remain in the history with `listed: false`.

The funding query uses API categories `type=1,2,8` from the Commission's examples; the tender query uses `type=0`. The first collection should be reviewed against the portal to confirm category coverage. Procurement notices from this portal do **not** cover every notice in [TED](https://ted.europa.eu/).

## Explore the portal locally

After the first collection, start the portal:

```bash
python3 -m bandi_eu serve
```

Open **http://127.0.0.1:8000**. Enter a short project description, comma-separated keywords, and optionally choose grants or tenders. The portal shows only opportunities marked open with a future deadline. Its 0–100 score measures English text overlap and shows the matching terms; it is **not** an award probability or an eligibility decision. Confirm all deadlines and requirements on the official opportunity page.

The command-line matcher remains available:

```bash
python3 -m bandi_eu match "We develop sustainable batteries for the power grid" --keywords battery recycling energy
```

## Collection workflow

To publish the first collection from a Terminal authenticated with GitHub CLI, run `bash scripts/publish_first_collection.sh`. It stages the project files, creates a commit, pushes `main`, and requests a fresh workflow run. It is safe to run again if the commit already exists; it still requests a fresh run.

The GitHub Actions workflow runs every day at **21:00 Europe/Rome** and also supports manual runs from the Actions tab. The timezone setting follows daylight saving time. GitHub [documents that scheduled runs can be delayed or dropped](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows); a dedicated scheduler is needed for a guaranteed start at an exact minute.

## Public portal

The same nightly workflow builds a compact snapshot of open grants and tenders, then deploys it to GitHub Pages. The public portal runs its text matching in each visitor's browser; project descriptions and keywords are not sent to this repository's server. It checks deadlines again in the browser, so an opportunity disappears from search after its deadline even before the next collection.

The repository owner can publish this version from the repository root in a Terminal authenticated with GitHub CLI:

```bash
bash scripts/publish_portal.sh
```

The script commits the portal changes, incorporates the latest dataset commit from `main`, pushes, enables GitHub Pages with GitHub Actions as its source, and starts a fresh collection and deployment. Once the run succeeds, the expected site URL is **https://alessandropozzetti.github.io/eu-funding-opportunities/**. GitHub Pages hosts the browser portal; the Python server remains useful for local development.

The workflow requests `contents: write` to commit the updated JSONL. If it cannot push, check *Settings → Actions → General → Workflow permissions* in the repository. The dataset grows with each run; if it becomes too large for Git, move persistence to a managed database.

## Matching limitations and next steps

- English descriptions and keywords currently work best because the imported records are requested in English.
- The score does not verify organisation type, country, consortium rules, budget fit, or other eligibility conditions.
- A later version can add multilingual semantic matching, explainable eligibility filters, user profiles, and a hosted portal backed by a database.
