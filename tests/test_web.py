import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from bandi_eu.core import normalize, save
from bandi_eu.web import create_handler, summary
from test_core import hit


class PortalTests(unittest.TestCase):
    def test_status_and_match_over_http(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "opportunities.jsonl"
            grant = normalize(hit(), "grant")
            grant["listed"] = True
            grant["last_seen"] = "2026-10-08T17:00:00+00:00"
            tender = normalize(hit("EU-TENDER-01", "Software services"), "tender")
            tender["listed"] = True
            tender["last_seen"] = grant["last_seen"]
            save(path, {grant["id"]: grant, tender["id"]: tender})
            self.assertEqual(summary({grant["id"]: grant, tender["id"]: tender})["active"], 2)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(path))
            except PermissionError:
                self.skipTest("Local sockets are disabled in this sandbox")
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/api/status") as response:
                    status = json.load(response)
                self.assertEqual(status["active_grants"], 1)
                self.assertEqual(status["active_tenders"], 1)
                request = Request(
                    base + "/api/match",
                    data=json.dumps({"description": "battery recycling", "keywords": ["energy"], "kind": "grant"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    matches = json.load(response)
                self.assertEqual(matches["count"], 1)
                self.assertEqual(matches["results"][0]["kind"], "grant")
                with urlopen(base + "/") as response:
                    self.assertIn(b"EU Opportunity Finder", response.read())
                with urlopen(base + "/matcher.js") as response:
                    self.assertIn(b"rankOpportunities", response.read())
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
