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

The search client requests English results from the [Commission search API](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis). Grants use source types `1`, `2`, `8`; procurement uses type `0`. Both queries include forthcoming and open source statuses. Requests use multipart JSON payloads and bounded retries. Pages contain at most 100 rows; larger requested sizes can be silently capped by the API.

A collection is accepted only if:

1. An independent query without sorting establishes a nonzero source total.
2. Every page honours the requested page number and size, has the expected row count and reports no warnings.
3. Ordered pages have the same total as the independent query. Ordering uses `identifier`, `DATASOURCE` and `esDA_IngestDate`. The total is checked again without sorting after the last page.
4. Every document has a source reference, source provenance and English language marker, and can be normalized.
5. Every `(DATASOURCE, reference, language)` tuple occurs exactly once. Their count must equal `totalResults`.
6. Two consecutive complete scans agree on every document identity and its normalized content, including raw metadata. Confirmation includes all source versions, before selecting a preferred version.

The distinction between source documents and opportunities matters: the current `SEDIA` index and legacy `SEDIA_PRD_CENTRICITY` index can contain different versions of the same reference. Those are separate documents for coverage validation. Repeating the same document within or between pages rejects the entire scan, even if the raw row count matches the reported total.

Only after coverage and stability checks pass are versions resolved into `<kind>:<reference>` opportunities. Preference is determined by source ingestion time, title availability and content completeness, with canonical JSON as the final deterministic tie-break. Separate references with the same public identifier remain separate opportunities.

A category gets at most four scan attempts. A rejected scan breaks the consecutive confirmation sequence; partial scans are never combined. A complete but changed scan becomes a new confirmation candidate. Exhausted scan validation or request retries fail the collection. This protocol establishes agreement between observed API responses; it is not a server-side snapshot or proof that the upstream index contains every published call.

All requested categories are fetched successfully before the stored catalogue is changed. The merged catalogue is written to an adjacent temporary file, flushed, synchronized and atomically replaced. A failed collection leaves the previous catalogue intact.

The writer assumes a single process. The temporary filename is shared and there is no interprocess lock. GitHub workflow concurrency serializes hosted runs; concurrent local writers are unsupported. Persistence retains the latest representation of each source identity, not every historical version of its content.

## Record lifecycle

| Condition | Transition |
| --- | --- |
| Previously unseen identity | Set `first_seen`, `last_seen`, `last_changed`; mark listed |
| Listed identity with unchanged source content | Advance `last_seen` |
| Changed source content or reappearing identity | Advance `last_changed` and `last_seen`; mark listed |
| Identity absent from two consecutive complete, concordant category scans | Retain record, set `listed: false`, advance `last_changed` |

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
- Hosted jobs explicitly use `ubuntu-24.04` to avoid automatic operating-system changes through `ubuntu-latest`. The Pages actions use Node.js 24, including the upload action's artifact dependency. Runner upgrades should be validated before changing the pinned image label.
- The schedule is 21:00 `Europe/Rome`, including daylight-saving changes. [GitHub scheduled workflows can be delayed or dropped](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
- Pages receives only the generated distribution. Dataset history and evaluation fixtures remain repository assets.

A failed collection or quality check prevents a fresh deployment. The existing site remains available with its previous snapshot; the interface identifies a collection older than 36 hours. Logs report each scan, rejected validation and the verified document/opportunity totals. An entirely empty category is treated as suspicious and requires investigation rather than automatically unlisting its history. Missing an upstream opportunity or a source field cannot be detected by these pipeline checks alone. See the [collection validation record](collection-validation.md) for the pagination regression and real API checks.

## Capacity and extension boundaries

The catalogue and retrieval index are loaded in memory. Each search builds term statistics over the current active set. JSONL is suitable for the present catalogue size, but Git history, browser transfer size and per-query indexing cost grow with the dataset.

A persistence migration should preserve source identity and lifecycle semantics. A retrieval replacement should preserve the response contract and be compared against independent judgments in addition to the current regression fixtures. Changes to the vocabulary or formula must maintain Python/JavaScript parity or explicitly version the public matching contract.
