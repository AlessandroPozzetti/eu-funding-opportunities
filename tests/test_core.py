import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bandi_eu.core import fetch_all, live, multipart, normalize, rank, sync


def hit(identifier="EU-2026-01", title="Clean energy storage", deadline=None):
    deadline = deadline or (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    return {"reference": "ref-1", "metadata": {
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

    def test_pagination_rejects_missing_rows(self):
        first = {"totalResults": 2, "results": [hit()]}
        second = {"totalResults": 2, "results": []}
        with patch("bandi_eu.core.fetch_page", side_effect=[first, second]):
            with self.assertRaises(RuntimeError):
                fetch_all("grant", page_size=1)

    def test_sync_is_atomic_on_api_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            path.write_text('{"id":"grant:old","kind":"grant","listed":true}\n')
            before = path.read_bytes()
            with patch("bandi_eu.core.fetch_all", side_effect=RuntimeError("API down")):
                with self.assertRaises(RuntimeError):
                    sync(path)
            self.assertEqual(path.read_bytes(), before)

    def test_sync_keeps_history_and_records_source_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            source = normalize(hit(), "grant")
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: source}):
                first_run = sync(path)
            self.assertEqual(first_run["new"], 1)
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: source}):
                second_run = sync(path)
            self.assertEqual(second_run["changed"], 0)
            modified = {**source, "title": "Updated clean energy storage"}
            with patch("bandi_eu.core.fetch_all", return_value={source["id"]: modified}):
                third_run = sync(path)
            self.assertEqual(third_run["changed"], 1)
            stored = json.loads(path.read_text().splitlines()[0])
            self.assertEqual(stored["title"], "Updated clean energy storage")
            self.assertTrue(stored["listed"])

    def test_rank_uses_only_open_opportunities(self):
        record = normalize(hit(), "grant")
        record["listed"] = True
        closed = {**record, "id": "grant:closed", "identifier": "closed", "status": "closed"}
        results = rank({record["id"]: record, closed["id"]: closed}, "battery recycling", ["energy"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["identifier"], "EU-2026-01")
        self.assertGreater(results[0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
