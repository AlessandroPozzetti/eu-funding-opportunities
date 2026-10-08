# Matching evaluation

Fixed-corpus regression evaluation for the Python and browser retrieval engines. Relevance judgments are development fixtures derived from source descriptions. The scenarios were used during implementation; they have not undergone independent expert annotation or held-out evaluation. Scores are not probability-calibrated.

## Evidence and reproducibility

- `fixtures/opportunities.json` freezes 339 open grants and tenders at `2026-10-08T18:16:06.319186+00:00`. The original dataset SHA-256 and source URLs are preserved. Fixture records are never used as the live portal dataset.
- `cases.json` contains 16 English scenarios: 13 with known topical targets, one battery-scope rejection case, one generic-query case, and one absent-topic case. Two Italian alias checks are reported separately.
- Each case records its query, priority topics, known targets, selected misleading alternatives, and the rationale. Targets are non-exhaustive and do not imply eligibility.
- `baseline.py` preserves the original matcher. Only an injected evaluation time and result IDs were added.
- `report.json` records both rankings, summary measures, the fixed evaluation time and the corpus/configuration hashes. Expiring live deadlines cannot change this comparison.

Run from the repository root:

```bash
python3 scripts/evaluate_matcher.py --check --output evaluation/report.json
python3 -m unittest discover -s tests -v
node tests/test_matcher.js
```

The workflow fails if a known target leaves the top five, a selected misleading alternative outranks a target, or a rejection case regresses. These gates detect regressions on this small collection; they cannot guarantee quality on new subjects.

## English pilot results

| Measure | Original | Version 2 |
| --- | ---: | ---: |
| Queries with a known target in the top five | 12 / 13 | 13 / 13 |
| Mean recall of the listed targets in the top five | 0.8846 | 1.0000 |
| Mean reciprocal rank of the first listed target | 0.8894 | 1.0000 |
| Target ranked above the selected misleading alternative | 13 / 15 | 15 / 15 |
| Generic/absent-topic rejection cases passed | 1 / 2 | 2 / 2 |

The target for the English cultural-heritage/XR project moves from rank 16 to rank 1. The two software-maintenance targets move from ranks 2 and 14 to ranks 1 and 2. The battery-recycling query no longer returns a fusion-power call or a recycled-paper supply contract through generic shared terminology.

Judgments are incomplete: most query/document pairs are unlabelled. The reported measures describe recovery of specified targets and selected pairwise orderings; they do not estimate corpus-wide precision or recall. Italian alias checks are reported separately and provide no evidence of general multilingual performance.

## How the index is calculated

1. Normalize accents and conservative English plurals. Resolve the maintained concept aliases. Preserve multiword priority phrases after normalization. This is dictionary-assisted lexical retrieval, not an embedding model or an LLM assessment.
2. For a cascade-funding record, use the specific call title as the primary title and the parent programme as weaker context. A match only in programme context cannot qualify a result.
3. Compute document frequency over **all open records before the grant/tender filter**. The same record keeps the same score when the type filter changes.
4. Apply an IDF weight `log(1 + (N - df + 0.5) / (df + 0.5))`, multiplied by 2.5 for priority terms and by 0.12 for generic terms.
5. Compute weighted term frequency with field factors: specific title 4, programme context 0.5, keywords 2, description 1. Repetitions are capped at three per field. Field length normalization uses `b=0.75` for descriptions and `b=0.3` elsewhere. Term strength is `tf / (1.2 + tf)`.
6. Require a supported specific topic and, when priorities are supplied, at least half of their normalized non-generic topics. Compute weighted query coverage `C` and weighted mean term strength `S`. The index is `100 × (0.55 C + 0.45 S) × (0.6 + 0.4 C)`, rounded to one decimal. Results below 15 are omitted.
7. Display an evidence label: strong requires `C >= 0.7`, at least two supported specific terms, and an index of at least 60; partial requires `C >= 0.4` and an index of at least 30; the remainder is limited. These thresholds are design choices, not learned probabilities. Show supporting fields, a source excerpt, and missing specific query topics separately from eligibility.

The length normalization and saturation follow the principles of [BM25](https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-non-binary-model-1.html); the displayed index and thresholds are application-specific heuristics. The need for query/document judgments and a fixed test collection follows standard [information-retrieval evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html).

## What remains unvalidated

An index of 80 does not mean an 80% chance that a project qualifies or receives funding. It is not comparable across searches or changing corpus snapshots. Synonyms outside the vocabulary, negation, incidental mentions, sparse descriptions and activities with similar vocabulary can still cause errors. Country, applicant type, consortium, budget and eligible activities are not assessed. The source may link to full requirements absent from the collected description.

Before claiming wider reliability, collect real project descriptions, have an independent funding reviewer judge pooled results from several retrieval approaches, record explicit eligibility separately, and reserve unseen projects for final evaluation. Inspect missed calls as well as returned calls. Only calibrate a compatibility probability after defining the event being predicted and obtaining enough independent labels. Keep evaluation snapshots and reviewer provenance versioned.
