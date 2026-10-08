# Architecture

## Components and execution modes

`core.py` owns upstream access, normalization, persistence and the active-record predicate. `matching.py` consumes active records without network access. `site.py` projects the persisted catalogue into the public contract used by both delivery modes.

| Concern | Static deployment | Local application |
| --- | --- | --- |
| Delivery | GitHub Pages | `ThreadingHTTPServer`, loopback by default |
| Catalogue | `opportunities.json` | `GET /api/opportunities` |
| Retrieval | `web/matcher.js` in the browser | `POST /api/match`, implemented in Python |
| Project text | Remains in browser memory | Sent to the local process; not persisted |
| Assets | Generated distribution | Allowlisted files from `web/` |

The two retrieval implementations share the vocabulary configuration. Full result objects, including explanations and notices, are compared on the frozen evaluation scenarios. The static build does not require Node.js; Node is used for verification.

## Ingestion transaction

The search client requests English results from the Commission search API. Grants use source types `1`, `2`, `8`; procurement uses type `0`. Both queries include forthcoming and open source statuses. Requests use multipart JSON payloads and bounded retries.

A collection is accepted only if:

1. Each query has a nonzero source total.
2. `totalResults` remains constant across its pages.
3. The sum of received source rows equals the reported total.
4. Every row can be normalized into an identified record.

Duplicate source rows count toward pagination completeness. They are then resolved by source identity, preferring the most recently ingested version, followed by source-title availability, English-language metadata and content completeness. Public identifiers are not deduplication keys: separate source references can share the same public identifier.

All requested categories are fetched successfully before the stored catalogue is changed. The merged catalogue is written to an adjacent temporary file, flushed, synchronized and atomically replaced. A failed collection leaves the previous catalogue intact.

The writer assumes a single process. The temporary filename is shared and there is no interprocess lock. GitHub workflow concurrency serializes hosted runs; concurrent local writers are unsupported. Persistence retains the latest representation of each source identity, not every historical version of its content.

## Record lifecycle

| Condition | Transition |
| --- | --- |
| Previously unseen identity | Set `first_seen`, `last_seen`, `last_changed`; mark listed |
| Listed identity with unchanged source content | Advance `last_seen` |
| Changed source content or reappearing identity | Advance `last_changed` and `last_seen`; mark listed |
| Identity absent from a successful category snapshot | Retain record, set `listed: false`, advance `last_changed` |

Local timestamps and listing flags are excluded when comparing source content. Source metadata and the original upstream timestamp remain available for audit.

An opportunity is active when `status == "open"`, it is listed, and it has a parseable deadline at or after the evaluation time. Date-only deadlines expire at the end of the corresponding day in `Europe/Brussels`. The public client rechecks deadlines before searches and catalogue views.

## Public projection

`public_snapshot()` is the shared serializer for the local catalogue endpoint and static build. It excludes raw metadata, detailed conditions, budget fields and lifecycle history. Exported fields are explicitly allowlisted in `PUBLIC_FIELDS`; adding a field requires a contract review.

The snapshot contains collection/build timestamps, stored-record count, matching configuration and active records. The builder copies the interface and favicon into `public_site/`. Typography uses system fonts without external requests. Project descriptions, query history and result selections are not part of the generated distribution.

The interface initially lists active opportunities by deadline. Search results expose the source excerpt, supported topics, absent query topics and a relevance index. Multiword priorities are retained after normalization. For cascade funding, the specific call title is displayed instead of the parent programme title.

## Retrieval contract

Corpus statistics include all active records before the opportunity-type filter. A type filter therefore does not alter a record's score. The engine caps term repetition, normalizes field length, suppresses generic-only queries and requires evidence for priority topics. The full formula and evidence thresholds are specified in [the evaluation protocol](../evaluation/README.md).

Scores are query-dependent heuristics. They are neither calibrated probabilities nor eligibility decisions. Eligibility would require additional structured applicant and call constraints; those constraints are outside the current retrieval contract.

## Automation

- `ci.yml` validates pull requests and code changes without invoking the upstream API.
- `nightly-sync.yml` validates, collects, versions the catalogue, builds the public projection and deploys it through the Pages artifact mechanism.
- The schedule is 21:00 `Europe/Rome`, including daylight-saving changes. [GitHub scheduled workflows can be delayed or dropped](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
- Pages receives only the generated distribution. Dataset history and evaluation fixtures remain repository assets.

A failed collection or quality check prevents a fresh deployment. The existing site remains available with its previous snapshot; the interface identifies a collection older than 36 hours. Missing an upstream opportunity or a source field cannot be detected by these pipeline checks alone.

## Capacity and extension boundaries

The catalogue and retrieval index are loaded in memory. Each search builds term statistics over the current active set. JSONL is suitable for the present catalogue size, but Git history, browser transfer size and per-query indexing cost grow with the dataset.

A persistence migration should preserve source identity and lifecycle semantics. A retrieval replacement should preserve the response contract and be compared against independent judgments in addition to the current regression fixtures. Changes to the vocabulary or formula must maintain Python/JavaScript parity or explicitly version the public matching contract.
