"""Local web portal for browsing and matching collected EU opportunities."""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from .core import assess, live, load
from .site import public_snapshot


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/matcher.js": ("matcher.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


def summary(records: dict[str, dict]) -> dict:
    active = [row for row in records.values() if live(row)]
    seen = [row.get("last_seen", "") for row in records.values() if row.get("last_seen")]
    return {
        "stored": len(records),
        "active": len(active),
        "active_grants": sum(row.get("kind") == "grant" for row in active),
        "active_tenders": sum(row.get("kind") == "tender" for row in active),
        "last_collected": max(seen) if seen else None,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def create_handler(data_path: Path):
    class PortalHandler(BaseHTTPRequestHandler):
        def send_json(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/status":
                self.send_json(summary(load(data_path)))
                return
            if path == "/api/opportunities":
                self.send_json(public_snapshot(load(data_path)))
                return
            if path not in STATIC_FILES:
                self.send_error(404, "Not found")
                return
            name, content_type = STATIC_FILES[path]
            body = (WEB_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/match":
                self.send_error(404, "Not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 12_000:
                    raise ValueError("Request body must be at most 12 KB")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                description = payload.get("description", "")
                keywords = payload.get("keywords", [])
                kind = payload.get("kind") or None
                if not isinstance(description, str) or len(description) > 4000:
                    raise ValueError("Description must be at most 4,000 characters")
                if not isinstance(keywords, list) or len(keywords) > 25 or any(not isinstance(word, str) or len(word) > 80 for word in keywords):
                    raise ValueError("Provide up to 25 short keywords")
                if kind not in {None, "grant", "tender"}:
                    raise ValueError("Unknown opportunity type")
                assessment = assess(load(data_path), description, keywords, limit=20, kind=kind)
                self.send_json({**assessment, "as_of": datetime.now(timezone.utc).isoformat()})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, status=400)

    return PortalHandler


def serve(data_path: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(data_path))
    print(f"EU opportunities portal: http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
