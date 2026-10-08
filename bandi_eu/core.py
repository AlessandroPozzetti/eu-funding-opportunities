"""Import and search EU opportunities using only the Python standard library."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, time as dt_time, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo


API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
STATUS = {"31094501": "forthcoming", "31094502": "open", "31094503": "closed"}
SOURCE_SORT = [
    {"field": "identifier", "order": "ASC"},
    {"field": "DATASOURCE", "order": "ASC"},
    {"field": "esDA_IngestDate", "order": "ASC"},
]
MAX_SCAN_ATTEMPTS = 4


class IncompleteCollection(RuntimeError):
    """A response cannot establish a complete, consistent source snapshot."""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append(" ")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    parser = _Text()
    parser.feed(str(value))
    return " ".join(html.unescape("".join(parser.parts)).split())


def first(metadata: dict, *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is not None and str(value).strip():
            return str(value)
    return ""


def values(metadata: dict, key: str) -> list[str]:
    value = metadata.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if item is not None and str(item).strip()]


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            # Date-only deadlines remain valid through the end of the Brussels day.
            if len(value) == 10:
                parsed = datetime.combine(parsed.date(), dt_time.max)
            parsed = parsed.replace(tzinfo=ZoneInfo("Europe/Brussels"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def live(record: dict, now: datetime | None = None) -> bool:
    if record.get("status") != "open" or not record.get("listed", True):
        return False
    deadline = parse_date(record.get("deadline", ""))
    if deadline is None:
        return False  # An unknown deadline must be checked on the portal.
    return deadline >= (now or datetime.now(timezone.utc))


def normalize(hit: dict, kind: str) -> dict:
    metadata = hit.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Invalid API metadata")
    identifier = first(metadata, "identifier", "topicAbbreviation")
    title = first(metadata, "title")
    if not identifier:
        raise ValueError("Opportunity is missing an identifier")
    reference = str(hit.get("reference") or "").strip()
    raw_url = first(metadata, "url") or hit.get("url") or ""
    if not raw_url and kind == "grant":
        from urllib.parse import quote

        raw_url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/" + quote(identifier, safe="")
    status_code = first(metadata, "status")
    record = {
        "id": f"{kind}:{reference or identifier}",
        "kind": kind,
        "api_type": first(metadata, "type"),
        "identifier": identifier,
        "title": clean_text(title) if title else f"Untitled {kind} ({identifier})",
        "source_title_present": bool(title),
        "call_identifier": first(metadata, "callIdentifier"),
        "call_title": clean_text(first(metadata, "callTitle")),
        "programme_code": first(metadata, "frameworkProgramme"),
        "programme_period": first(metadata, "programmePeriod"),
        "status": STATUS.get(status_code, status_code),
        "status_code": status_code,
        "opening_date": first(metadata, "startDate"),
        "deadline": first(metadata, "deadlineDate"),
        "deadline_model": first(metadata, "deadlineModel"),
        "description": clean_text(first(metadata, "descriptionByte", "description") or hit.get("summary")),
        "conditions": clean_text(first(metadata, "topicConditions")),
        "destination": clean_text(first(metadata, "destinationDescription")),
        "keywords": values(metadata, "keywords"),
        "tags": values(metadata, "tags"),
        "types_of_action": values(metadata, "typesOfAction"),
        "budget": first(metadata, "budget", "budgetOverview"),
        "currency": first(metadata, "currency"),
        "url": raw_url,
        "source_reference": reference,
        "source_updated_at": first(metadata, "esDA_IngestDate"),
        "source": "EU Funding & Tenders Portal",
        "raw_metadata": metadata,
    }
    return record


def multipart(payload: dict) -> tuple[bytes, str]:
    boundary = "bandi-eu-" + uuid4().hex
    parts = []
    for name, value in payload.items():
        parts.extend([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\nContent-Type: application/json\r\n\r\n".encode(),
            json.dumps(value, ensure_ascii=False).encode(),
            b"\r\n",
        ])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def fetch_page(kind: str, page: int, page_size: int = 100, retries: int = 3, *, ordered: bool = True) -> dict:
    if kind not in {"grant", "tender"} or page < 1 or not 1 <= page_size <= 100:
        raise ValueError("Use grant/tender, a positive page number and a page size of 1–100")
    clauses = [
        {"terms": {"type": ["1", "2", "8"] if kind == "grant" else ["0"]}},
        {"terms": {"status": ["31094501", "31094502"]}},
    ]
    payload = {"query": {"bool": {"must": clauses}}, "languages": ["en"]}
    if ordered:
        payload["sort"] = SOURCE_SORT
    body, content_type = multipart(payload)
    query = urlencode({"apiKey": "SEDIA", "text": "***", "pageSize": page_size, "pageNumber": page})
    request = Request(
        f"{API_URL}?{query}",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "bandi-eu/0.1 (+public EU API)",
            "Origin": "https://ec.europa.eu",
            "Referer": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
        },
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=45) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get("results"), list) or type(data.get("totalResults")) is not int:
                raise ValueError("Unexpected API response: missing results or total")
            return data
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"EU API unavailable, page {page} ({kind}): {exc}") from exc
            time.sleep(2 ** attempt)
    raise AssertionError("Retry limit reached")


def _checked_page(kind: str, page: int, page_size: int, *, ordered: bool = True) -> tuple[list, int]:
    data = fetch_page(kind, page, page_size, ordered=ordered)
    if not isinstance(data, dict):
        raise IncompleteCollection("Invalid API response")
    results, total = data.get("results"), data.get("totalResults")
    if not isinstance(results, list) or type(total) is not int or total < 0:
        raise IncompleteCollection("Invalid API results or total")
    if (type(data.get("pageNumber")) is not int or type(data.get("pageSize")) is not int
            or data["pageNumber"] != page or data["pageSize"] != page_size):
        raise IncompleteCollection(f"API did not honour page {page} / page size {page_size}")
    if data.get("warnings"):
        raise IncompleteCollection(f"API returned warnings on {kind} page {page}")
    if len(results) != min(page_size, max(0, total - (page - 1) * page_size)):
        raise IncompleteCollection(f"{kind} page {page}: row count does not match the source total")
    return results, total


def _collect_once(kind: str, page_size: int) -> dict[tuple[str, str, str], dict]:
    """Read one complete pass; overlapping pages are failures, never deduplication."""
    # Sorting on a sparsely populated metadata field can silently exclude records.
    # Measure coverage independently, with the original unsorted query.
    _, expected = _checked_page(kind, 1, 1, ordered=False)
    if expected == 0:
        raise IncompleteCollection(f"The API returned no {kind} records; collection stopped")
    found: dict[tuple[str, str, str], dict] = {}
    page = 1
    while True:
        results, total = _checked_page(kind, page, page_size)
        if total != expected:
            raise IncompleteCollection(f"API total changed or sorting excluded records ({expected} → {total})")
        for hit in results:
            if not isinstance(hit, dict) or not isinstance(hit.get("reference"), str) or not hit["reference"].strip():
                raise IncompleteCollection(f"{kind} page {page}: missing source reference")
            try:
                record = normalize(hit, kind)
            except (ValueError, TypeError) as exc:
                raise IncompleteCollection(f"{kind} page {page}: invalid source record") from exc
            source = first(record["raw_metadata"], "DATASOURCE", "datasource")
            language = first(record["raw_metadata"], "language") or hit.get("language", "")
            if not source or language != "en":
                raise IncompleteCollection(f"{kind} page {page}: missing source provenance or unexpected language")
            # The current and legacy indexes may contain the same reference.
            # Count those distinct source documents, but never the same document twice.
            document_key = (source, record["source_reference"], language)
            if document_key in found:
                raise IncompleteCollection(f"{kind} page {page}: repeated source document {document_key}")
            found[document_key] = record
        print(f"{kind}: page {page}, {len(found)}/{total} distinct source documents", flush=True)
        if len(found) == expected:
            break
        page += 1
    _, final_total = _checked_page(kind, 1, 1, ordered=False)
    if final_total != expected:
        raise IncompleteCollection(f"API total changed at the end of the scan ({expected} → {final_total})")
    return found


def fetch_all(kind: str, page_size: int = 100, max_attempts: int = MAX_SCAN_ATTEMPTS) -> dict[str, dict]:
    """Require two consecutive complete scans with identical identities and content.

    A total counts documents identified by source, reference and language.
    Rejected scans are discarded in full; partial results are never unioned.
    """
    if kind not in {"grant", "tender"} or not 1 <= page_size <= 100 or max_attempts < 2:
        raise ValueError("A valid kind, page size of 1–100 and at least two scan attempts are required")
    previous = None
    reason = "No complete scan"
    for attempt in range(1, max_attempts + 1):
        print(f"{kind}: verification pass {attempt}/{max_attempts}", flush=True)
        try:
            current = _collect_once(kind, page_size)
        except IncompleteCollection as exc:
            previous = None
            reason = str(exc)
            print(f"{kind}: rejected pass: {reason}", flush=True)
        else:
            if previous == current:
                records = {}
                for record in current.values():
                    old = records.get(record["id"])
                    if old is None or _record_quality(record) > _record_quality(old):
                        records[record["id"]] = record
                print(f"{kind}: verified {len(current)} distinct source documents, {len(records)} opportunities in two consecutive complete passes", flush=True)
                return records
            reason = "Source identities or content changed between complete scans" if previous is not None else "A second matching complete scan is required"
            previous = current
        if attempt < max_attempts:
            time.sleep(1)
    raise IncompleteCollection(f"Could not verify {kind} collection after {max_attempts} passes: {reason}. Previous catalogue preserved.")


def _record_quality(record: dict) -> tuple:
    """Resolve current/legacy index versions only after coverage is verified."""
    return (
        parse_date(record["source_updated_at"]) or datetime.min.replace(tzinfo=timezone.utc),
        record["source_title_present"],
        len(record["description"]),
        len(record["conditions"]),
        bool(record["url"]),
        json.dumps(record, ensure_ascii=False, sort_keys=True),
    )


def load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["id"]] = record
    return records


def save(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            for key in sorted(records):
                file.write(json.dumps(records[key], ensure_ascii=False, sort_keys=True) + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sync(path: Path, include_tenders: bool = True) -> dict[str, int]:
    kinds = ["grant", "tender"] if include_tenders else ["grant"]
    snapshots = {kind: fetch_all(kind) for kind in kinds}
    records = load(path)
    timestamp = datetime.now(timezone.utc).isoformat()
    new = changed = removed = 0
    for kind, snapshot in snapshots.items():
        for key, incoming in snapshot.items():
            old = records.get(key)
            if old is None:
                new += 1
                incoming["first_seen"] = timestamp
                incoming["last_changed"] = timestamp
            else:
                incoming["first_seen"] = old["first_seen"]
                # Collection time and local listing status are not source changes.
                old_content = {k: v for k, v in old.items() if k not in {"first_seen", "last_seen", "last_changed", "listed"}}
                new_content = {k: v for k, v in incoming.items() if k not in {"first_seen", "last_seen", "last_changed", "listed"}}
                if old_content != new_content or not old.get("listed", True):
                    changed += 1
                    incoming["last_changed"] = timestamp
                else:
                    incoming["last_changed"] = old["last_changed"]
            incoming["last_seen"] = timestamp
            incoming["listed"] = True
            records[key] = incoming
        for key, old in records.items():
            if old["kind"] == kind and key not in snapshot and old.get("listed", True):
                old["listed"] = False
                old["last_changed"] = timestamp
                removed += 1
    save(path, records)
    return {"new": new, "changed": changed, "removed_from_current_list": removed, "total_stored": len(records), "grants_fetched": len(snapshots["grant"]), "tenders_fetched": len(snapshots.get("tender", {}))}


def audit(records: dict[str, dict]) -> dict:
    listed = [row for row in records.values() if row.get("listed", True)]
    active = [row for row in listed if live(row)]
    now = datetime.now(timezone.utc)
    return {
        "stored": len(records),
        "listed": len(listed),
        "listed_grants": sum(row.get("kind") == "grant" for row in listed),
        "listed_tenders": sum(row.get("kind") == "tender" for row in listed),
        "open_with_future_deadline": len(active),
        "open_grants": sum(row.get("kind") == "grant" for row in active),
        "open_tenders": sum(row.get("kind") == "tender" for row in active),
        "open_with_past_deadline": sum(
            row.get("status") == "open" and (deadline := parse_date(row.get("deadline", ""))) is not None and deadline < now
            for row in listed
        ),
        "missing_deadline": sum(not row.get("deadline") for row in listed),
        "missing_source_title": sum(not row.get("source_title_present", True) for row in listed),
        "missing_source_url": sum(not row.get("url") for row in listed),
        "missing_description": sum(not row.get("description") for row in listed),
        "last_collected": max((row.get("last_seen", "") for row in listed), default=""),
    }


def assess(records: dict[str, dict], description: str, keywords: list[str], limit: int = 20,
           kind: str | None = None, now: datetime | None = None) -> dict:
    from .matching import assess as assess_open_records
    now = now or datetime.now(timezone.utc)
    candidates = [row for row in records.values() if live(row, now)]
    return assess_open_records(candidates, description, keywords, limit, kind)


def rank(records: dict[str, dict], description: str, keywords: list[str], limit: int = 10,
         kind: str | None = None) -> list[dict]:
    return assess(records, description, keywords, limit, kind)["results"]
