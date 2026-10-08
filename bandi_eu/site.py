"""Build a static, public version of the opportunity portal."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from shutil import copyfile

from .core import live, load
from .matching import CONFIG


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PUBLIC_FIELDS = (
    "id", "kind", "identifier", "title", "call_title", "description",
    "keywords", "tags", "deadline", "url", "programme_code", "status", "listed",
)


def public_snapshot(records: dict[str, dict]) -> dict:
    """Return the shared public data contract for static and local clients."""
    active = [row for row in records.values() if live(row)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_collected": max((row.get("last_seen", "") for row in records.values()), default=""),
        "stored": len(records),
        "matching_config": CONFIG,
        "records": [{key: row.get(key) for key in PUBLIC_FIELDS} for row in active],
    }


def build_site(data_path: Path, output_dir: Path) -> dict[str, object]:
    snapshot = public_snapshot(load(data_path))
    output_dir.mkdir(parents=True, exist_ok=True)

    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    marker = 'data-mode="local"'
    if marker not in html:
        raise RuntimeError("The portal HTML is missing its local-mode marker")
    (output_dir / "index.html").write_text(
        html.replace(marker, 'data-mode="static"'), encoding="utf-8"
    )
    for name in ("styles.css", "matcher.js", "app.js", "favicon.svg"):
        copyfile(WEB_DIR / name, output_dir / name)
    (output_dir / "opportunities.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return {"active_exported": len(snapshot["records"]), "stored": snapshot["stored"], "output_dir": str(output_dir)}
