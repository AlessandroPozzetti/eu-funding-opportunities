import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bandi_eu.core import normalize, save
from bandi_eu.site import build_site
from test_core import hit


class StaticSiteTests(unittest.TestCase):
    def test_exports_only_open_future_records_without_raw_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            future = normalize(hit("OPEN", "Building renovation"), "grant")
            future["last_seen"] = "2026-10-08T17:00:00+00:00"
            expired = normalize(hit("EXPIRED", "Old call"), "tender")
            expired["deadline"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            expired["last_seen"] = future["last_seen"]
            data = root / "opportunities.jsonl"
            save(data, {future["id"]: future, expired["id"]: expired})

            report = build_site(data, root / "public")
            snapshot = json.loads((root / "public" / "opportunities.json").read_text())
            self.assertEqual(report["active_exported"], 1)
            self.assertEqual(snapshot["stored"], 2)
            self.assertEqual(snapshot["records"][0]["identifier"], "OPEN")
            self.assertNotIn("raw_metadata", snapshot["records"][0])
            self.assertIn('data-mode="static"', (root / "public" / "index.html").read_text())
            self.assertTrue((root / "public" / "matcher.js").exists())
            self.assertTrue((root / "public" / "favicon.svg").exists())


if __name__ == "__main__":
    unittest.main()
