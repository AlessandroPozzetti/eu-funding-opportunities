"use strict";

function words(value, stopwords) {
  const found = String(value || "").toLocaleLowerCase("en").match(/[\p{L}\p{N}]+/gu) || [];
  return new Set(found.filter((word) => word.length > 2 && !stopwords.has(word)));
}

function parseSourceDate(value) {
  if (!value) return NaN;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return Date.parse(`${value}T23:59:59Z`);
  return Date.parse(value.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
}

function isOpenOpportunity(record, now = Date.now()) {
  if (record.status !== "open" || record.listed === false || !record.deadline) return false;
  const deadline = parseSourceDate(record.deadline);
  return Number.isFinite(deadline) && deadline >= now;
}

function rankOpportunities(records, description, keywords, kind, stopwords, limit = 20) {
  const ignored = new Set(stopwords);
  const query = words(`${description} ${keywords.join(" ")}`, ignored);
  if (!query.size) throw new Error("Provide a description or at least one keyword");

  const now = Date.now();
  const candidates = records.filter((row) => isOpenOpportunity(row, now) && (!kind || row.kind === kind));
  const documents = candidates.map((row) => ({
    row,
    title: words(`${row.title} ${row.call_title || ""}`, ignored),
    keywords: words([...(row.keywords || []), ...(row.tags || [])].join(" "), ignored),
    description: words(row.description, ignored),
  }));
  const frequency = new Map();
  for (const document of documents) {
    const terms = new Set([...document.title, ...document.keywords, ...document.description]);
    for (const term of terms) frequency.set(term, (frequency.get(term) || 0) + 1);
  }

  const scored = [];
  for (const document of documents) {
    let numerator = 0;
    let denominator = 0;
    const matched = [];
    for (const term of query) {
      const weight = Math.log(1 + (documents.length + 1) / ((frequency.get(term) || 0) + 1));
      denominator += weight;
      const strength = Math.min(1,
        (document.title.has(term) ? 0.85 : 0) +
        (document.keywords.has(term) ? 0.55 : 0) +
        (document.description.has(term) ? 0.3 : 0));
      if (strength) {
        numerator += weight * strength;
        matched.push(term);
      }
    }
    if (!matched.length) continue;
    const row = document.row;
    scored.push({
      score: Math.round(1000 * numerator / denominator) / 10,
      matched_terms: matched.sort(),
      kind: row.kind,
      identifier: row.identifier,
      title: row.title,
      description: (row.description || "").slice(0, 360),
      deadline: row.deadline,
      url: row.url,
      programme_code: row.programme_code,
    });
  }
  scored.sort((a, b) => b.score - a.score || a.deadline.localeCompare(b.deadline));
  return scored.slice(0, limit);
}

const OpportunityMatcher = { isOpenOpportunity, parseSourceDate, rankOpportunities };
if (typeof window !== "undefined") window.OpportunityMatcher = OpportunityMatcher;
if (typeof module !== "undefined") module.exports = OpportunityMatcher;
