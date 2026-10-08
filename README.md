# EU Opportunity Finder

A small, testable project that collects grants and procurement notices from the European Commission's [Funding & Tenders Portal API](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) and matches open opportunities to a project description.

## Project structure

| Path | Purpose |
| --- | --- |
| `bandi_eu/core.py` | API client, normalization, collection, storage, and active-record filtering |
| `bandi_eu/matching.py` | Explainable relevance scoring and evidence extraction |
| `bandi_eu/matching_config.json` | Shared English-first vocabulary and limited Italian aliases |
| `bandi_eu/site.py` | Compact snapshot and static portal builder |
| `bandi_eu/web.py` | Local HTTP server and JSON endpoints |
| `web/` | Responsive portal interface |
| `data/opportunities.jsonl` | Collected records, one JSON object per line |
| `tests/` | Collector and portal tests |
| `evaluation/` | Frozen corpus, labelled pilot scenarios, original baseline, and comparison report |
| `scripts/evaluate_matcher.py` | Reproduce the ranking comparison and check quality gates |
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

Open **http://127.0.0.1:8000**. Describe the intended activity, subject and users in English, add comma-separated priority topics, and optionally choose grants or tenders. English is the main evaluation language. The portal shows only opportunities marked open with a future deadline.

Each result displays a **relevance index out of 100**, supporting text, and topics not found in the available description. It is an uncalibrated search index, not a probability of project compatibility, eligibility or funding. Compare it only within the same search. A generic query such as `digital` asks for more detail instead of returning misleading perfect matches. Confirm the scope and requirements on the official opportunity page.

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

The script runs the tests and matching quality checks, commits the portal changes, incorporates the latest dataset commit from `main`, pushes, enables GitHub Pages with GitHub Actions as its source, and starts a fresh collection and deployment. Once the run succeeds, the expected site URL is **https://alessandropozzetti.github.io/eu-funding-opportunities/**. GitHub Pages hosts the browser portal; the Python server remains useful for local development. Restart a running local server after updating Python code.

The workflow requests `contents: write` to commit the updated JSONL. If it cannot push, check *Settings → Actions → General → Workflow permissions* in the repository. The dataset grows with each run; if it becomes too large for Git, move persistence to a managed database.

## Matching limitations and next steps

- Matching uses field-aware term scoring, conservative plural normalization, a maintained concept vocabulary, and priority phrases. Specific call titles take precedence over the parent programme title. Keywords receive extra weight; at least half of the non-generic priority topics must occur in the available title, keywords or description. Sparse source text can therefore cause relevant opportunities to be missed.
- English descriptions and keywords are the primary supported input. A small set of Italian aliases is provided; it is not general translation or multilingual semantic understanding. Use uppercase `AI` or the full phrase `artificial intelligence` to distinguish the acronym from the Italian preposition.
- Phrase order matters for multiword priority keywords after normalization. Unsupported synonyms, negation, intended activity, and incidental mentions can still cause retrieval errors. Read the supporting excerpts and missing topics.
- The score does not verify organisation type, country, consortium rules, budget fit, or other eligibility conditions.
- [The evaluation report](evaluation/README.md) compares the old and new matchers on a frozen collection of 339 records, with 16 English scenarios and two supplementary Italian scenarios. Labels were assessed by the coding assistant from source text and are not independent expert judgments. These are regression checks, not an estimate of real-world accuracy.
- Run `python3 scripts/evaluate_matcher.py --check` to reproduce the quality checks. They also run before every nightly deployment. Python/browser parity tests verify matching results and explanations on every frozen scenario.
- The next validation step is independent review of real project/call pairs, including missed opportunities and eligibility. Semantic retrieval or calibrated compatibility estimates should be evaluated against those judgments before adoption.
