# Contributing

## Working environment

Use Python 3.10+ and Node.js. Runtime code has no third-party Python or JavaScript dependencies. The local application and static distribution must remain usable from a checkout.

## Change boundaries

- Keep source normalization and persistence in `core.py`; retrieval must not invoke the upstream API.
- Preserve source-reference identities and all-or-nothing collection behavior.
- Treat `PUBLIC_FIELDS` and the HTTP response shapes as contracts. Document intentional changes in `docs/api.md`.
- Update Python and JavaScript retrieval together. Vocabulary changes belong in `matching_config.json`.
- Keep website source text in English. Render user and upstream content as text, and maintain keyboard interaction, visible focus and reduced-motion support.
- Bundle new frontend assets locally. Preserve third-party asset licenses.

## Required checks

```bash
python3 -m unittest discover -s tests -v
node tests/test_matcher.js
python3 scripts/evaluate_matcher.py --check
python3 -m bandi_eu build-site --output public_site
```

Collector tests use synthetic API responses; verification must not depend on a live collection. The local HTTP integration test skips only when the execution environment prohibits sockets.

For interface changes, inspect both wide and narrow layouts and exercise catalogue filtering, example searches, evidence expansion, empty/error states and pagination. The local and static modes must expose the same user-facing behavior.

## Retrieval changes

Record a concrete failure case before changing scoring behavior. Include source IDs, the query, expected ordering or rejection, and a rationale. Keep the existing frozen corpus stable so results remain comparable; introduce a separately versioned fixture when evaluating a new snapshot.

Regenerate `evaluation/report.json` when the retrieval engine or configuration changes. Report known-target recovery and selected pairwise comparisons separately from independent accuracy estimates. Development fixtures must not be described as held-out judgments or as probability calibration.
