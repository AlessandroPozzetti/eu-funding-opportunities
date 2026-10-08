# Local HTTP API and public snapshot

The local server binds to `127.0.0.1:8000` by default. These HTTP endpoints belong to the local application; GitHub Pages serves `opportunities.json` and static assets instead.

Responses use JSON with UTF-8 encoding and `Cache-Control: no-store`. Unknown paths return HTTP 404. The service has no authentication layer and is intended for loopback use.

## `GET /api/status`

Returns catalogue counters and collection time.

| Field | Type | Meaning |
| --- | --- | --- |
| `stored` | integer | All retained identities |
| `active` | integer | Listed, open records with a nonexpired known deadline |
| `active_grants` / `active_tenders` | integer | Active records by type |
| `last_collected` | string or null | Most recent `last_seen` timestamp |
| `as_of` | string | UTC response time |

## `GET /api/opportunities`

Returns the same projection as the static site's `opportunities.json`.

| Field | Type | Meaning |
| --- | --- | --- |
| `generated_at` | string | UTC serialization time |
| `last_collected` | string | Latest stored `last_seen`; empty for an empty catalogue |
| `stored` | integer | All retained identities, including inactive records |
| `matching_config` | object | Versioned normalization and vocabulary configuration |
| `records` | array | Public fields for active opportunities |

Public record fields are `id`, `kind`, `identifier`, `title`, `call_title`, `description`, `keywords`, `tags`, `deadline`, `url`, `programme_code`, `status`, and `listed`. Raw metadata and detailed conditions are excluded. See [the storage schema](../data/README.md) for their source semantics.

## `POST /api/match`

```json
{
  "description": "We develop software applications and provide ongoing maintenance.",
  "keywords": ["software", "maintenance"],
  "kind": "tender"
}
```

| Input | Constraint |
| --- | --- |
| Request body | 1–12,000 bytes |
| `description` | String, at most 4,000 characters; defaults to empty |
| `keywords` | At most 25 strings, each at most 80 characters; defaults to empty |
| `kind` | `grant`, `tender`, null or empty; omitted means both types |

At least one usable normalized search term is required. Invalid input returns HTTP 400 with `{"error": "..."}`. A valid but overly generic query returns HTTP 200 with an empty result set and a notice requesting a more specific description.

The response contains:

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | string | Matching contract version |
| `query` | object | Normalized topics, priority topics and broad terms |
| `notices` | string array | Query-quality and insufficient-evidence messages |
| `score_note` | string | Interpretation of the relevance index |
| `results` | array | Up to 20 results, ordered by score, deadline and stable ID |
| `count` | integer | Number of returned results |
| `total` | integer | Number of candidates passing the retrieval threshold |
| `as_of` | string | UTC response time; local API only |

Each result includes identity, type, specific call title, programme context, deadline, source URL and programme code. Retrieval fields are:

- `score`: uncalibrated relevance index on a 0–100 scale.
- `match_level`: strong, partial or limited text evidence, according to documented thresholds.
- `matched_terms`: supported normalized terms, including broad terms.
- `evidence`: specific topics and the fields supporting each one.
- `missing_topics`: specific query terms absent from the available text.
- `description`: a bounded excerpt selected from the source description.
- `eligibility`: `Not assessed`.

The client may sort the returned subset by deadline. This does not fetch additional ranked candidates beyond the server's top-20 limit.

## Static assets

The local server uses an explicit asset allowlist. HTML, CSS, JavaScript and the SVG favicon are served from `web/`; arbitrary filesystem paths are not exposed. User and source text is inserted into the interface through text nodes rather than HTML interpolation.
