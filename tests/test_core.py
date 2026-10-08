import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bandi_eu.core import audit, live, multipart, normalize, parse_date, rank, sync


def hit(identifier="EU-2026-01", title="Clean energy storage", deadline=None):
    deadline = deadline or (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    return {"reference": f"ref-{identifier}", "metadata": {
        "identifier": [identifier], "title": [title], "status": ["31094502"],
        "deadlineDate": [deadline], "descriptionByte": ["<p>Battery <b>recycling</b> research</p>"],
        "keywords": ["battery", "energy"], "frameworkProgramme": ["43108390"],
    }}


class CoreTests(unittest.TestCase):
    def test_multipart_json_parts(self):
        body, content_type = multipart({"query": {"bool": {"must": []}}, "languages": ["en"]})
        self.assertIn(b'Content-Type: application/json', body)
        self.assertIn(b'name="query"', body)
        self.assertIn(b'name="languages"', body)
        self.assertIn(b'"bool"', body)
        self.assertIn(b"--" + content_type.split("boundary=")[1].encode() + b"--", body)

    def test_normalize_and_live_deadline(self):
        record = normalize(hit(), "grant")
        self.assertEqual(record["description"], "Battery recycling research")
        self.assertTrue(live({**record, "listed": True}))
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(live({**record, "deadline": past, "listed": True}))
        self.assertFalse(live({**record, "listed": False}))

    def test_parse_date_accepts_eu_api_timezone(self):
        self.assertEqual(parse_date("2026-11-25T00:00:00.000+0000"), datetime(2026, 11, 25, tzinfo=timezone.utc))

    def test_normalize_preserves_untitled_source_record(self):
        source = hit("TENDER-01", "")
        source["metadata"]["title"] = []
        record = normalize(source, "tender")
        self.assertEqual(record["title"], "Untitled tender (TENDER-01)")
        self.assertFalse(record["source_title_present"])
        self.assertEqual(audit({record["id"]: record})["missing_source_title"], 1)

    def test_sync_is_atomic_on_api_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            path.write_text('{"id":"grant:old","kind":"grant","listed":true}\n')
            before = path.read_bytes()
            with patch("bandi_eu.core.fetch_all", side_effect=RuntimeError("API down")):
                with self.assertRaises(RuntimeError):
                    sync(path, include_tenders=False)
            self.assertEqual(path.read_bytes(), before)

    def test_sync_keeps_history_and_records_source_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            source = normalize(hit(), "grant")
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: source}):
                first_run = sync(path, include_tenders=False)
            self.assertEqual(first_run["new"], 1)
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: source}):
                second_run = sync(path, include_tenders=False)
            self.assertEqual(second_run["changed"], 0)
            modified = {**source, "title": "Updated clean energy storage"}
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: modified}):
                third_run = sync(path, include_tenders=False)
            self.assertEqual(third_run["changed"], 1)
            stored = json.loads(path.read_text().splitlines()[0])
            self.assertEqual(stored["title"], "Updated clean energy storage")
            self.assertTrue(stored["listed"])

    def test_sync_collects_grants_and_tenders_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            grant = normalize(hit(), "grant")
            tender = normalize(hit("EU-TENDER-01", "Software services"), "tender")
            with patch("bandi_eu.core.fetch_all", side_effect=[{grant["id"]: grant}, {tender["id"]: tender}]) as fetch:
                result = sync(path)
            self.assertEqual(fetch.call_args_list[0].args, ("grant",))
            self.assertEqual(fetch.call_args_list[1].args, ("tender",))
            self.assertEqual(result["grants_fetched"], 1)
            self.assertEqual(result["tenders_fetched"], 1)
            self.assertEqual(result["total_stored"], 2)

    def test_audit_distinguishes_expired_portal_status(self):
        grant = normalize(hit(), "grant")
        grant["listed"] = True
        expired = {**grant, "id": "grant:expired", "deadline": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
        report = audit({grant["id"]: grant, expired["id"]: expired})
        self.assertEqual(report["open_with_future_deadline"], 1)
        self.assertEqual(report["open_with_past_deadline"], 1)

    def test_rank_uses_only_open_opportunities(self):
        record = normalize(hit(), "grant")
        record["listed"] = True
        closed = {**record, "id": "grant:closed", "identifier": "closed", "status": "closed"}
        results = rank({record["id"]: record, closed["id"]: closed}, "battery recycling", ["energy"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["identifier"], "EU-2026-01")
        self.assertGreater(results[0]["score"], 0)

    def test_rank_prefers_title_match(self):
        title_match = normalize(hit("EU-TITLE", "Battery recycling"), "grant")
        description_match = normalize(hit("EU-DESC", "Other research"), "grant")
        title_match["listed"] = True
        description_match["listed"] = True
        result = rank({title_match["id"]: title_match, description_match["id"]: description_match}, "battery recycling", [])
        self.assertEqual(result[0]["identifier"], "EU-TITLE")


if __name__ == "__main__":
    unittest.main()
