"""Import and search EU opportunities using only the Python standard library."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import time
from datetime import datetime, time as dt_time, timezone
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo


API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
SOURCE_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis"
STATUS = {"31094501": "forthcoming", "31094502": "open", "31094503": "closed"}
ROME = ZoneInfo("Europe/Rome")
STOPWORDS = set("a an and are as at be by for from in is it of on or the to with this that we our you your una uno un di da del della delle dei gli il la le lo i e o per con su nel nella che si sono questo questi tra come ai agli alle all allo al the".split())


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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
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
    if not identifier or not title:
        raise ValueError("Opportunity is missing an identifier or title")
    raw_url = first(metadata, "url") or hit.get("url") or ""
    if not raw_url and kind == "grant":
        from urllib.parse import quote

        raw_url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/" + quote(identifier, safe="")
    status_code = first(metadata, "status")
    record = {
        "id": f"{kind}:{identifier}",
        "kind": kind,
        "api_type": first(metadata, "type"),
        "identifier": identifier,
        "title": clean_text(title),
        "call_identifier": first(metadata, "callIdentifier"),
        "call_title": clean_text(first(metadata, "callTitle")),
        "programme_code": first(metadata, "frameworkProgramme"),
        "programme_period": first(metadata, "programmePeriod"),
        "status": STATUS.get(status_code, status_code),
        "status_code": status_code,
        "opening_date": first(metadata, "startDate"),
        "deadline": first(metadata, "deadlineDate"),
        "deadline_model": first(metadata, "deadlineModel"),
        "description": clean_text(first(metadata, "descriptionByte", "description")),
        "conditions": clean_text(first(metadata, "topicConditions")),
        "destination": clean_text(first(metadata, "destinationDescription")),
        "keywords": values(metadata, "keywords"),
        "tags": values(metadata, "tags"),
        "types_of_action": values(metadata, "typesOfAction"),
        "budget": first(metadata, "budget", "budgetOverview"),
        "currency": first(metadata, "currency"),
        "url": raw_url,
        "source_reference": str(hit.get("reference") or ""),
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


def fetch_page(kind: str, page: int, page_size: int = 100, retries: int = 3) -> dict:
    clauses = [
        {"terms": {"type": ["1", "2", "8"] if kind == "grant" else ["0"]}},
        {"terms": {"status": ["31094501", "31094502"]}},
    ]
    body, content_type = multipart({"query": {"bool": {"must": clauses}}, "languages": ["en"]})
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
            if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not isinstance(data.get("totalResults"), int):
                raise ValueError("Unexpected API response: missing results or total")
            return data
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"EU API unavailable, page {page} ({kind}): {exc}") from exc
            time.sleep(2 ** attempt)
    raise AssertionError("Retry limit reached")


def fetch_all(kind: str, page_size: int = 100) -> dict[str, dict]:
    found: dict[str, dict] = {}
    page = 1
    expected: int | None = None
    while True:
        data = fetch_page(kind, page, page_size)
        results = data["results"]
        total = data["totalResults"]
        if expected is None:
            expected = total
            if expected == 0:
                raise RuntimeError(f"The API returned no {kind} records; collection stopped")
        if total != expected:
            raise RuntimeError(f"API total changed during pagination ({expected} → {total})")
        if not results and len(found) < total:
            raise RuntimeError(f"Incomplete pagination: {len(found)} of {total} records")
        for hit in results:
            record = normalize(hit, kind)
            found[record["id"]] = record
        print(f"{kind}: page {page}, {len(found)}/{total}", flush=True)
        if page * page_size >= total:
            break
        page += 1
    if len(found) != expected:
        raise RuntimeError(f"Incomplete or duplicated pagination: {len(found)} unique records of {expected}")
    return found


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


def sync(path: Path, include_tenders: bool = False) -> dict[str, int]:
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
    return {"new": new, "changed": changed, "removed_from_current_list": removed, "total_stored": len(records)}


def tokens(value: str) -> Counter:
    return Counter(word for word in re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE) if len(word) > 2 and word not in STOPWORDS)


def rank(records: dict[str, dict], description: str, keywords: list[str], limit: int = 10) -> list[dict]:
    query = tokens(description + " " + " ".join(keywords))
    if not query:
        raise ValueError("Provide a description or at least one keyword")
    now = datetime.now(timezone.utc)
    candidates = [row for row in records.values() if live(row, now)]
    if not candidates:
        return []
    documents = []
    frequency = Counter()
    for row in candidates:
        weighted = Counter()
        for term, count in tokens(row["title"] + " " + row.get("call_title", "")).items():
            weighted[term] += 3 * count
        weighted.update(tokens(row.get("description", "")))
        for term, count in tokens(" ".join(row.get("keywords", []) + row.get("tags", []))).items():
            weighted[term] += 2 * count
        documents.append((row, weighted))
        frequency.update(weighted.keys())
    scored = []
    for row, document in documents:
        matches = []
        numerator = denominator = 0.0
        for word, count in query.items():
            weight = math.log(1 + (len(documents) + 1) / (frequency[word] + 1))
            denominator += weight * count
            if word in document:
                numerator += weight * min(count, document[word])
                matches.append(word)
        if not matches:
            continue
        score = round(100 * numerator / denominator, 1)
        scored.append({"score": score, "matched_terms": sorted(matches), "identifier": row["identifier"], "title": row["title"], "deadline": row["deadline"], "url": row["url"], "programme_code": row["programme_code"]})
    return sorted(scored, key=lambda item: (-item["score"], item["deadline"]))[:limit]
