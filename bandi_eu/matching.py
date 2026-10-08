"""Explainable, field-aware retrieval. Scores are uncalibrated relevance indices."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import re
import unicodedata


CONFIG = json.loads(Path(__file__).with_name("matching_config.json").read_text())


def plain(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(value or "")) if not unicodedata.combining(c))


def raw_words(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", plain(value), re.UNICODE)


def stem(word: str) -> str:
    # Conservative English plural handling, not a general language stemmer.
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


STOP = set(CONFIG["stopwords"].split())
GENERIC = {stem(word) for word in CONFIG["generic_terms"]}
ALIASES: dict[str, list[tuple[list[str], str, str]]] = {}
for label, aliases in CONFIG["concepts"].items():
    for alias in aliases:
        parts = raw_words(alias.lower())
        ALIASES.setdefault(parts[0], []).append((parts, label, alias))
for entries in ALIASES.values():
    entries.sort(key=lambda item: -len(item[0]))


def analyze(value: str) -> list[str]:
    original = raw_words(value)
    words = [word.lower() for word in original]
    terms = []
    i = 0
    while i < len(words):
        found = False
        for parts, label, alias in ALIASES.get(words[i], []):
            # Uppercase short acronyms avoid interpreting Italian "ai" as AI.
            if len(parts) == 1 and alias.isupper() and len(alias) <= 3 and original[i] != alias:
                continue
            if words[i:i + len(parts)] == parts:
                terms.append(label)
                i += len(parts)
                found = True
                break
        if found:
            continue
        word = words[i]
        if len(word) > 2 and not word.isdigit() and word not in STOP:
            terms.append(stem(word))
        i += 1
    return terms


def display_title(row: dict) -> tuple[str, str]:
    title, call = row.get("title") or "", row.get("call_title") or ""
    if "COMPETITIVE_CALL" in (row.get("id") or "") and call:
        return call, title
    return title, call if call != title else ""


def fields(row: dict) -> dict[str, str]:
    title, context = display_title(row)
    return {"title": title, "programme": context,
            "keywords": " ".join((row.get("keywords") or []) + (row.get("tags") or [])),
            "description": row.get("description") or ""}


def query_analyzer(keywords: list[str]):
    """Preserve multiword priority phrases after concept/stopword normalization."""
    phrases = sorted({tuple(analyze(keyword)) for keyword in keywords if len(analyze(keyword)) > 1},
                     key=lambda phrase: (-len(phrase), phrase))

    def normalize(value: str) -> list[str]:
        terms = analyze(value)
        output, i = [], 0
        while i < len(terms):
            phrase = next((p for p in phrases if tuple(terms[i:i + len(p)]) == p), None)
            if phrase:
                output.append(" ".join(phrase))
                i += len(phrase)
            else:
                output.append(terms[i])
                i += 1
        return output

    return normalize


def evidence_excerpt(text: str, matched: set[str], normalize=analyze) -> str:
    if not text:
        return ""
    # Score bounded passages, so a keyword buried in a long notice is visible.
    passages = []
    for sentence in re.split(r"(?<=[.!?;])\s+|[\n•]", text):
        words = sentence.split()
        for offset in range(0, len(words), 32):
            passages.append(" ".join(words[offset:offset + 48]))
    best = max(passages or [text], key=lambda passage: len(set(normalize(passage)) & matched))
    return best if len(best) <= 340 else best[:337] + "…"


def assess(candidates: list[dict], description: str, keywords: list[str], limit: int = 20,
           kind: str | None = None) -> dict:
    """Rank already-open records; corpus statistics always include both types."""
    normalize = query_analyzer(keywords)
    terms = set(normalize(description))
    keyword_terms = set(term for keyword in keywords for term in normalize(keyword))
    terms |= keyword_terms
    if not terms:
        raise ValueError("Add a specific topic, activity or service to your description")
    generic = GENERIC | {term for term in terms if all(part in GENERIC for part in term.split())}
    specific = terms - generic
    focus = keyword_terms - generic or specific
    notices = []
    if not specific:
        notices.append("Your search is too broad. Add a specific topic, activity or service; words such as digital or energy are not enough.")
    elif len(specific) == 1:
        notices.append("This is a broad topic search. Add the intended activity and target users to narrow the results.")
    query = {"topics": sorted(specific), "priority_topics": sorted(keyword_terms - generic),
             "broad_terms": sorted(terms & generic)}
    result = {"version": CONFIG["version"], "query": query, "notices": notices,
              "results": [], "count": 0, "total": 0,
              "score_note": "Relevance index, not a probability. Compare results within this search. Eligibility has not been assessed."}
    if not specific or not candidates:
        return result

    documents, frequency = [], Counter()
    for row in candidates:
        texts = fields(row)
        counts = {key: Counter(normalize(value)) for key, value in texts.items()}
        frequency.update(set().union(*(set(value) for value in counts.values())))
        documents.append((row, texts, counts))
    averages = {key: max(1, sum(sum(doc[2][key].values()) for doc in documents) / len(documents))
                for key in ("title", "programme", "keywords", "description")}
    weights = {term: math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
               * (2.5 if term in keyword_terms else 1) * (0.12 if term in generic else 1)
               for term in terms}
    denominator = sum(weights.values())
    field_weights = {"title": 4.0, "programme": 0.5, "keywords": 2.0, "description": 1.0}
    scored = []
    for row, texts, counts in documents:
        if kind and row.get("kind") != kind:
            continue
        # Programme-wide terminology alone must not qualify a specific call.
        actual = set(counts["title"]) | set(counts["keywords"]) | set(counts["description"])
        supported_focus = focus & actual
        if not supported_focus:
            continue
        if keyword_terms - generic and len(supported_focus) < math.ceil(len(focus) / 2):
            continue
        matched = terms & actual
        coverage = sum(weights[t] for t in matched) / denominator
        strength = 0.0
        for term in matched:
            tf = 0.0
            for field, factor in field_weights.items():
                b = 0.75 if field == "description" else 0.3
                length = sum(counts[field].values())
                tf += factor * min(3, counts[field][term]) / (1 - b + b * length / averages[field])
            strength += weights[term] * tf / (1.2 + tf)
        strength /= denominator
        score = math.floor(1000 * (0.55 * coverage + 0.45 * strength) * (0.6 + 0.4 * coverage) + 0.5) / 10
        if score < 15:
            continue
        level = "Strong text evidence" if coverage >= 0.7 and len(matched - generic) >= 2 and score >= 60 else (
            "Partial text evidence" if coverage >= 0.4 and score >= 30 else "Limited text evidence")
        missing = sorted(specific - actual, key=lambda t: (-weights[t], t))
        evidence = [{"topic": term, "fields": [key for key in ("title", "keywords", "description") if term in counts[key]]}
                    for term in sorted(matched - generic, key=lambda t: (-weights[t], t))]
        title, context = display_title(row)
        scored.append({
            "id": row.get("id", row.get("identifier", "")), "score": score, "match_level": level,
            "matched_terms": sorted(matched), "missing_topics": missing,
            "evidence": evidence, "eligibility": "Not assessed",
            "kind": row["kind"], "identifier": row["identifier"], "title": title,
            "programme_title": context,
            "description": evidence_excerpt(texts["description"], matched - generic, normalize),
            "deadline": row["deadline"], "url": row.get("url", ""),
            "programme_code": row.get("programme_code", ""),
        })
    scored.sort(key=lambda row: (-row["score"], row["deadline"], row["id"]))
    result.update(results=scored[:limit], count=len(scored[:limit]), total=len(scored))
    if not scored:
        notices.append("No sufficient text evidence was found. Try fewer priority keywords or a different description; there may be no suitable open call in this collection.")
    elif not any(row["match_level"] == "Strong text evidence" for row in scored):
        notices.append("No strong text match was found. The results below cover only part of your description; review the missing topics and official scope.")
    return result
