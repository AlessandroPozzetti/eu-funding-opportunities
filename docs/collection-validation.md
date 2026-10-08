# Collection validation — 8 October 2026

## Failure reproduced

Two published/local catalogue snapshots disagreed on active membership while the affected source records had identical content and deadlines. The previous collector compared the number of received rows with `totalResults`, then resolved repeated references into one opportunity. This allowed overlapping pages to conceal omitted documents and incorrectly change `listed` flags.

The API also returns legitimate current/legacy versions of the same reference. Rejecting every repeated reference would therefore reject valid collections. Coverage must use `(DATASOURCE, reference, language)` document identities; opportunity version resolution follows coverage validation.

## API observations

The [official API documentation](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) describes multipart queries, language filtering and grants/tenders categories. The following behavior was checked against actual responses:

- A request for 10,000 rows was capped to 100. The collector now bounds page size and checks the returned pagination metadata.
- Sorting on `REFERENCE` excluded documents lacking that metadata field. The collector now compares every sorted-page total with a separate query without sorting, before and after the scan.
- Ordering by `identifier`, `DATASOURCE` and `esDA_IngestDate` preserved the unsorted totals in both category scans.
- Current and legacy indexes contained 119 additional versions of existing references: one grant version and 118 tender versions. They were distinct source documents, not overlapping pages.

## Verification result

Two independent API reads per category were captured and replayed through the production validation and synchronization functions against an isolated copy of the catalogue. All document identities and normalized contents, including raw metadata, matched across the two reads. Each pass checked the unsorted total before and after pagination.

| Category | Source documents per pass | Ordered pages per pass | Resolved opportunities | Active at verification |
| --- | ---: | ---: | ---: | ---: |
| Grants | 1,187 | 12 | 1,186 | 195 |
| Tenders | 1,447 | 15 | 1,329 | 149 |
| Total | 2,634 | 27 | 2,515 | 344 |

The synchronized catalogue retained 2,516 historical opportunity identities. One remained unlisted. Relative to the previous public snapshot of 319 active opportunities, the verified collection recovered 25 omitted grants. These counters describe this validation run, not a permanent catalogue size.

## Regression coverage

`tests/test_collection.py` exercises repeated documents, changed versions within a scan, legitimate current/legacy versions, distinct references sharing an identifier, incomplete pages, mismatched pagination metadata, warnings, missing provenance, unexpected languages, zero totals, sorting-induced exclusions and changing totals.

It also checks changes in membership at a constant total, content changes between complete scans, bounded recovery after a rejected scan, the requirement for consecutive confirmation, and byte-for-byte catalogue preservation when tender verification fails after grants have been fetched. Confirmed absences are retained as history; previously omitted records can reappear without losing `first_seen`.

## Limits

Two concordant scans provide evidence of a complete, stable API result during collection. The API does not expose a transactional snapshot in this workflow. A persistently incomplete upstream index can still agree with itself. The collector intentionally fails when it cannot establish coverage or agreement; it does not merge partial scans or silently publish them. Existing source-content, eligibility and deadline-interpretation limitations still apply.
