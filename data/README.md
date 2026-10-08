# First collection report

Collected on 8 October 2026 from the European Commission Funding & Tenders Portal search API. The dataset is [`opportunities.jsonl`](opportunities.jsonl); each line is one normalized opportunity with its original source metadata.

| Measure | Count |
| --- | ---: |
| Grant source rows | 1,187 |
| Distinct grant source references | 1,085 |
| Tender source rows | 1,448 |
| Distinct tender source references | 1,229 |
| Total distinct source references | 2,314 |
| Open with a future deadline at collection time | 243 (151 grants, 92 tenders) |

The API returned multiple English rows for some source references. The collector validates the **source row count** against `totalResults`, then keeps the latest ingested version for each source reference. Different grant references sometimes share the same public identifier and URL but have different opening or deadline dates, so they remain separate records. This explains why the number of stored records is lower than the reported API total.

## Source data checks

The API's status and deadline fields sometimes disagree. At collection time, 784 records were marked open but had a past deadline. Another 634 records had no deadline, one tender had no source title, and two records had no description. The matcher shows only records marked open with a future deadline. An absent source title is preserved as an explicit `Untitled ...` label and counted by `audit`.

These counts are a snapshot, not a live status guarantee. Check the official opportunity page and documents before acting. The funding and tender categories reflect this portal's search API; this project does not claim to cover every notice published on [TED](https://ted.europa.eu/).
