"""Frozen v1 matcher for reproducible comparisons; only time injection and result IDs were added."""

import math
import re
from collections import Counter
from datetime import datetime, timezone
from bandi_eu.core import live

STOPWORDS = ['a', 'agli', 'ai', 'al', 'all', 'alle', 'allo', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'che', 'come', 'con', 'da', 'dei', 'del', 'della', 'delle', 'di', 'e', 'for', 'from', 'gli', 'i', 'il', 'in', 'is', 'it', 'la', 'le', 'lo', 'nel', 'nella', 'o', 'of', 'on', 'or', 'our', 'per', 'questi', 'questo', 'si', 'sono', 'su', 'that', 'the', 'this', 'to', 'tra', 'un', 'una', 'uno', 'we', 'with', 'you', 'your']

def tokens(value: str) -> Counter:
    return Counter(word for word in re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE) if len(word) > 2 and word not in STOPWORDS)


def rank(records: dict[str, dict], description: str, keywords: list[str], limit: int = 10, kind: str | None = None, as_of=None) -> list[dict]:
    query = tokens(description + " " + " ".join(keywords))
    if not query:
        raise ValueError("Provide a description or at least one keyword")
    now = as_of or datetime.now(timezone.utc)
    candidates = [row for row in records.values() if live(row, now) and (kind is None or row.get("kind") == kind)]
    if not candidates:
        return []
    documents = []
    frequency = Counter()
    for row in candidates:
        title_terms = tokens(row["title"] + " " + row.get("call_title", ""))
        keyword_terms = tokens(" ".join(row.get("keywords", []) + row.get("tags", [])))
        description_terms = tokens(row.get("description", ""))
        documents.append((row, title_terms, keyword_terms, description_terms))
        frequency.update(set(title_terms) | set(keyword_terms) | set(description_terms))
    scored = []
    for row, title_terms, keyword_terms, description_terms in documents:
        matches = []
        numerator = denominator = 0.0
        for word in query:
            weight = math.log(1 + (len(documents) + 1) / (frequency[word] + 1))
            denominator += weight
            strength = min(1.0, (0.85 if word in title_terms else 0) + (0.55 if word in keyword_terms else 0) + (0.3 if word in description_terms else 0))
            if strength:
                numerator += weight * strength
                matches.append(word)
        if not matches:
            continue
        score = round(100 * numerator / denominator, 1)
        scored.append({
            "id": row["id"],
            "score": score,
            "matched_terms": sorted(matches),
            "kind": row["kind"],
            "identifier": row["identifier"],
            "title": row["title"],
            "description": row.get("description", "")[:360],
            "deadline": row["deadline"],
            "url": row["url"],
            "programme_code": row["programme_code"],
        })
    return sorted(scored, key=lambda item: (-item["score"], item["deadline"]))[:limit]
