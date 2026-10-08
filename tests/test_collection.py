"""Coverage regressions: source versions are distinct; repeated pages are not."""

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bandi_eu.core import (
    IncompleteCollection, SOURCE_SORT, _collect_once, fetch_all, fetch_page,
    load, normalize, save, sync,
)
from test_core import hit


def source(identifier="A", source_name="SEDIA", reference=None):
    row = hit(identifier)
    row["metadata"].update({"DATASOURCE": [source_name], "language": ["en"], "type": ["1"]})
    if reference:
        row["reference"] = reference
    return row


def response(rows, total, number=1, size=1, **extra):
    return {"results": rows, "totalResults": total, "pageNumber": number,
            "pageSize": size, "warnings": [], **extra}


def scan(rows, size=1):
    """An unsorted count query, full ordered pages, then a fresh count query."""
    control = response(rows[:1], len(rows))
    pages = [response(rows[i:i + size], len(rows), i // size + 1, size)
             for i in range(0, len(rows), size)]
    return [copy.deepcopy(page) for page in [control, *pages, control]]


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch("bandi_eu.core.time.sleep").start()
        self.addCleanup(patch.stopall)

    def test_request_encodes_sort_and_control_preserves_original_query(self):
        data = json.dumps(response([source()], 1)).encode()
        with patch("bandi_eu.core.urlopen", side_effect=lambda *a, **k: io.BytesIO(data)) as request:
            fetch_page("grant", 1, 1)
            ordered = request.call_args.args[0]
            self.assertIn(json.dumps(SOURCE_SORT).encode(), ordered.data)
            self.assertIn(b'name="languages"', ordered.data)
            fetch_page("grant", 1, 1, ordered=False)
            control = request.call_args.args[0]
            self.assertNotIn(b'name="sort"', control.data)
            self.assertIn(b'"type": ["1", "2", "8"]', control.data)

    def test_requires_two_matching_complete_scans(self):
        rows = [source("A"), source("B"), source("C")]
        with patch("bandi_eu.core.fetch_page", side_effect=scan(rows, 2) * 2) as fetch:
            records = fetch_all("grant", page_size=2)
        self.assertEqual(len(records), 3)
        self.assertEqual(fetch.call_count, 8)
        self.assertEqual(fetch.call_args_list[0].kwargs, {"ordered": False})

    def test_rejects_page_overlap_even_when_raw_row_count_matches(self):
        row = source()
        # One missing record is hidden by repeating the same document on page two.
        with patch("bandi_eu.core.fetch_page", side_effect=scan([row, row])):
            with self.assertRaisesRegex(IncompleteCollection, "repeated source document"):
                _collect_once("grant", 1)

    def test_rejects_same_source_reference_with_changed_content_within_scan(self):
        row = source()
        changed = copy.deepcopy(row)
        changed["metadata"]["descriptionByte"] = ["Changed while paginating"]
        with patch("bandi_eu.core.fetch_page", side_effect=scan([row, changed])):
            with self.assertRaisesRegex(IncompleteCollection, "repeated source document"):
                _collect_once("grant", 1)

    def test_accepts_distinct_current_and_legacy_versions_then_selects_latest(self):
        legacy = source(source_name="SEDIA_PRD_CENTRICITY")
        legacy["metadata"]["esDA_IngestDate"] = ["2022-01-01T00:00:00Z"]
        current = source()
        current["metadata"]["esDA_IngestDate"] = ["2026-01-01T00:00:00Z"]
        current["metadata"]["descriptionByte"] = ["Current source text"]
        with patch("bandi_eu.core.fetch_page", side_effect=scan([legacy, current]) * 2):
            records = fetch_all("grant", 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records["grant:ref-A"]["description"], "Current source text")

    def test_preserves_distinct_references_with_same_public_identifier(self):
        rows = [source(reference="ref-1"), source(reference="ref-2")]
        with patch("bandi_eu.core.fetch_page", side_effect=scan(rows) * 2):
            records = fetch_all("grant", 1)
        self.assertEqual(set(records), {"grant:ref-1", "grant:ref-2"})

    def test_rejects_invalid_page_metadata_and_source_records(self):
        good = source()
        variants = [
            {"pageNumber": 2}, {"pageNumber": True}, {"pageSize": 100}, {"warnings": ["partial results"]},
            {"results": []}, {"totalResults": -1}, {"totalResults": True},
            {"results": [{**good, "reference": ""}]},
            {"results": [{**good, "metadata": {**good["metadata"], "DATASOURCE": []}}]},
            {"results": [{**good, "metadata": {**good["metadata"], "language": ["fr"]}}]},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                pages = scan([good])
                pages[1].update(variant)
                with patch("bandi_eu.core.fetch_page", side_effect=pages):
                    with self.assertRaises(IncompleteCollection):
                        _collect_once("grant", 1)

    def test_rejects_sort_that_silently_excludes_source_documents(self):
        row = source()
        pages = [response([row], 2), response([row], 1)]
        with patch("bandi_eu.core.fetch_page", side_effect=pages):
            with self.assertRaisesRegex(IncompleteCollection, "sorting excluded"):
                _collect_once("grant", 1)

    def test_rejects_total_change_at_end_of_scan(self):
        row = source()
        pages = scan([row]); pages[-1]["totalResults"] = 2
        with patch("bandi_eu.core.fetch_page", side_effect=pages):
            with self.assertRaisesRegex(IncompleteCollection, "at the end"):
                _collect_once("grant", 1)

    def test_rejects_zero_total(self):
        with patch("bandi_eu.core.fetch_page", return_value=response([], 0)):
            with self.assertRaisesRegex(IncompleteCollection, "no grant records"):
                _collect_once("grant", 1)

    def test_changed_membership_with_same_total_requires_new_confirmation(self):
        a, b, c = source("A"), source("B"), source("C")
        pages = scan([a, b]) + scan([a, c]) + scan([a, c])
        with patch("bandi_eu.core.fetch_page", side_effect=pages):
            records = fetch_all("grant", 1, max_attempts=3)
        self.assertEqual(set(records), {"grant:ref-A", "grant:ref-C"})

    def test_changed_content_requires_new_confirmation(self):
        before = source()
        after = copy.deepcopy(before); after["metadata"]["title"] = ["Updated call"]
        with patch("bandi_eu.core.fetch_page", side_effect=scan([before]) + scan([after]) * 2):
            records = fetch_all("grant", 1, max_attempts=3)
        self.assertEqual(records["grant:ref-A"]["title"], "Updated call")

    def test_rejected_pass_breaks_consecutive_confirmation(self):
        row = source()
        bad = scan([row, row])[:-1]  # Rejection happens before the final count request.
        with patch("bandi_eu.core.fetch_page", side_effect=scan([row]) + bad + scan([row])):
            with self.assertRaisesRegex(IncompleteCollection, "after 3 passes"):
                fetch_all("grant", 1, max_attempts=3)

    def test_retries_discard_partial_results_and_can_recover(self):
        row, missing = source(), source("MISSING")
        bad = scan([row, row])[:-1]
        with patch("bandi_eu.core.fetch_page", side_effect=bad + scan([row, missing]) * 2):
            records = fetch_all("grant", 1, max_attempts=3)
        self.assertEqual(len(records), 2)

    def test_failed_tender_verification_preserves_entire_catalogue_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "opportunities.jsonl"
            row = normalize(source(), "grant")
            save(path, {row["id"]: {**row, "listed": True, "first_seen": "before", "last_seen": "before"}})
            before = path.read_bytes()
            with patch("bandi_eu.core.fetch_all", side_effect=[{row["id"]: row}, IncompleteCollection("overlap")]):
                with self.assertRaises(IncompleteCollection):
                    sync(path)
            self.assertEqual(path.read_bytes(), before)

    def test_verified_sync_restores_omitted_records_and_marks_confirmed_absence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "opportunities.jsonl"
            present, absent = normalize(source("A"), "grant"), normalize(source("B"), "grant")
            rows = {r["id"]: {**r, "listed": r is absent, "first_seen": "first", "last_seen": "old", "last_changed": "old"}
                    for r in [present, absent]}
            save(path, rows)
            with patch("bandi_eu.core.fetch_all", return_value={present["id"]: present}):
                sync(path, include_tenders=False)
            result = load(path)
            self.assertTrue(result[present["id"]]["listed"])
            self.assertEqual(result[present["id"]]["first_seen"], "first")
            self.assertFalse(result[absent["id"]]["listed"])
            self.assertEqual(result[absent["id"]]["last_seen"], "old")


if __name__ == "__main__":
    unittest.main()
