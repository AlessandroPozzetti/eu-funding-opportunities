# Catalogue schema

`opportunities.jsonl` contains one JSON object per source identity, encoded as UTF-8 and ordered by `id`. It stores the latest normalized representation of each identity and retains records removed from subsequent successful collections.

## Identity and source fields

| Field | Type | Semantics |
| --- | --- | --- |
| `id` | string | `<kind>:<source_reference>`; falls back to the public identifier when no source reference is present |
| `kind` | string | `grant` or `tender` |
| `identifier` | string | Public topic/procurement identifier; not necessarily unique |
| `source_reference` | string | Upstream search reference |
| `api_type` | string | Upstream category code |
| `source` | string | Source system name |
| `url` | string | Source link; a grant-topic link may be constructed when absent |
| `source_updated_at` | string | Source ingestion timestamp, when supplied |
| `raw_metadata` | object | Original metadata retained for audit and reprocessing |

## Content

| Fields | Representation |
| --- | --- |
| `title`, `call_title`, `call_identifier` | Strings; the specific cascade call may differ from its parent topic |
| `description`, `conditions`, `destination` | HTML converted to whitespace-normalized plain text |
| `programme_code`, `programme_period` | Source programme identifiers |
| `keywords`, `tags`, `types_of_action` | Arrays of source strings |
| `budget`, `currency` | Source strings; no currency conversion or budget interpretation |
| `source_title_present` | Boolean; missing titles receive an explicit fallback display label |

Missing scalar source values generally become empty strings. Lists become empty arrays. Source text can remain multilingual despite the English search-language parameter.

## Time and lifecycle

`status_code` retains the source value. Known statuses are normalized to `forthcoming`, `open` or `closed` in `status`; unknown values are preserved. `opening_date`, `deadline` and `deadline_model` retain source representations. Parsed date-only deadlines use the end of the day in `Europe/Brussels`.

`first_seen`, `last_seen` and `last_changed` are UTC collection timestamps. `listed` indicates presence in the most recent verified collection of the record's category. Verification requires two consecutive complete scans with identical source documents and content. A failed collection changes neither listing flags nor timestamps. Confirmed absence does not delete a record. Previous content versions are not retained within the JSONL file.

A record is eligible for the public snapshot only if it is listed, has an open source status and a known, nonexpired deadline. This operational definition does not establish legal eligibility or guarantee that the source's status is current.

## Collection invariants

The API can return current and legacy index versions of the same reference. Coverage is checked using distinct `(DATASOURCE, reference, language)` document identities, before resolving versions into opportunity identities. Repeated documents within or across pages cause validation failure; they cannot stand in for missing rows. Consequently, the stored opportunity count can be lower than the upstream document total.

Distinct source references sharing a public identifier or URL are preserved; they can represent different rounds or dates. The newest source ingestion timestamp determines the preferred index version, with deterministic completeness tie-breaks. Source reference, provenance and language are mandatory for new collections; the normalizer's identifier fallback exists for compatibility with historical inputs.

The sorted query total must match an independent query without sorting, both before and after pagination. This prevents a sort on sparsely populated fields from silently dropping documents. Both categories must pass verification before the catalogue is replaced. See [collection architecture](../docs/architecture.md#ingestion-transaction) for retry and failure semantics.

`python3 -m bandi_eu audit` reports current counts and missing or inconsistent fields. Counts are evaluated at invocation time and should not be inferred from historical reports.

The selected Funding & Tenders Portal categories are the collection boundary. They do not constitute full TED coverage. Detailed call attachments are not downloaded or parsed by this pipeline.
