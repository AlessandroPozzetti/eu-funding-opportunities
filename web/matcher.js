"use strict";

function plain(value) {
  return String(value || "").normalize("NFKD").replace(/\p{M}/gu, "");
}
function rawWords(value) { return plain(value).match(/[\p{L}\p{N}]+/gu) || []; }
function stem(word) {
  if (word.length > 4 && word.endsWith("ies")) return `${word.slice(0, -3)}y`;
  if (word.length > 4 && word.endsWith("s") && !/(ss|us|is)$/.test(word)) return word.slice(0, -1);
  return word;
}

function createAnalyzer(config) {
  const stop = new Set(config.stopwords.split(" "));
  const aliases = new Map();
  for (const [label, values] of Object.entries(config.concepts)) {
    for (const alias of values) {
      const parts = rawWords(alias.toLowerCase());
      if (!aliases.has(parts[0])) aliases.set(parts[0], []);
      aliases.get(parts[0]).push({ parts, label, alias });
    }
  }
  for (const entries of aliases.values()) entries.sort((a, b) => b.parts.length - a.parts.length);
  return function analyze(value) {
    const original = rawWords(value);
    const words = original.map((word) => word.toLowerCase());
    const terms = [];
    let i = 0;
    while (i < words.length) {
      let found = false;
      for (const { parts, label, alias } of aliases.get(words[i]) || []) {
        if (parts.length === 1 && alias === alias.toUpperCase() && alias.length <= 3 && original[i] !== alias) continue;
        if (parts.every((part, n) => words[i + n] === part)) {
          terms.push(label);
          i += parts.length;
          found = true;
          break;
        }
      }
      if (found) continue;
      const word = words[i];
      if (word.length > 2 && !/^\p{N}+$/u.test(word) && !stop.has(word)) terms.push(stem(word));
      i += 1;
    }
    return terms;
  };
}

function parseSourceDate(value) {
  if (!value) return NaN;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    // Europe/Brussels is UTC+1 in winter and UTC+2 in summer. Inspect midday
    // on this date, after either daylight-saving transition, for its offset.
    const midday = Date.parse(`${value}T12:00:00Z`);
    if (!Number.isFinite(midday) || new Date(midday).toISOString().slice(0, 10) !== value) return NaN;
    const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Brussels", hour: "2-digit", hourCycle: "h23" }).format(midday));
    return Date.parse(`${value}T23:59:59.999Z`) - (hour - 12) * 3600000;
  }
  return Date.parse(value.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
}
function isOpenOpportunity(record, now = Date.now()) {
  if (record.status !== "open" || record.listed === false || !record.deadline) return false;
  const deadline = parseSourceDate(record.deadline);
  return Number.isFinite(deadline) && deadline >= now;
}
function displayTitle(row) {
  const title = row.title || "";
  const call = row.call_title || "";
  return (row.id || "").includes("COMPETITIVE_CALL") && call
    ? [call, title] : [title, call !== title ? call : ""];
}
function fields(row) {
  const [title, programme] = displayTitle(row);
  return { title, programme, keywords: [...(row.keywords || []), ...(row.tags || [])].join(" "), description: row.description || "" };
}
function excerpt(text, matched, analyze) {
  if (!text) return "";
  const passages = [];
  for (const sentence of text.split(/(?<=[.!?;])\s+|[\n•]/)) {
    const words = sentence.trim().split(/\s+/).filter(Boolean);
    for (let offset = 0; offset < words.length; offset += 32) passages.push(words.slice(offset, offset + 48).join(" "));
  }
  let best = text, bestCount = -1;
  for (const passage of passages.length ? passages : [text]) {
    const count = [...new Set(analyze(passage))].filter((term) => matched.has(term)).length;
    if (count > bestCount) { best = passage; bestCount = count; }
  }
  return best.length <= 340 ? best : `${best.slice(0, 337)}…`;
}
function compare(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

function queryAnalyzer(config, keywords) {
  const base = createAnalyzer(config);
  const unique = new Map();
  for (const keyword of keywords) {
    const phrase = base(keyword);
    if (phrase.length > 1) unique.set(JSON.stringify(phrase), phrase);
  }
  const phrases = [...unique.values()].sort((a, b) => b.length - a.length || compare(a.join("\u0000"), b.join("\u0000")));
  return function analyze(value) {
    const terms = base(value), output = [];
    let i = 0;
    while (i < terms.length) {
      const phrase = phrases.find((p) => p.every((part, n) => terms[i + n] === part));
      if (phrase) { output.push(phrase.join(" ")); i += phrase.length; }
      else { output.push(terms[i]); i += 1; }
    }
    return output;
  };
}

function assessOpportunities(records, description, keywords, kind, config, limit = 20, now = Date.now()) {
  if (!config || config.version !== "2.0") throw new Error("The search data has changed. Reload this page and try again.");
  const analyze = queryAnalyzer(config, keywords);
  const generic = new Set(config.generic_terms.map(stem));
  const keywordTerms = new Set(keywords.flatMap(analyze));
  const terms = new Set([...analyze(description), ...keywordTerms]);
  if (!terms.size) throw new Error("Add a specific topic, activity or service to your description");
  for (const term of terms) if (term.split(" ").every((part) => generic.has(part))) generic.add(term);
  const specific = new Set([...terms].filter((term) => !generic.has(term)));
  const priority = [...keywordTerms].filter((term) => !generic.has(term));
  const focus = new Set(priority.length ? priority : specific);
  const notices = [];
  if (!specific.size) notices.push("Your search is too broad. Add a specific topic, activity or service; words such as digital or energy are not enough.");
  else if (specific.size === 1) notices.push("This is a broad topic search. Add the intended activity and target users to narrow the results.");
  const result = {
    version: config.version,
    query: { topics: [...specific].sort(), priority_topics: priority.sort(), broad_terms: [...terms].filter((term) => generic.has(term)).sort() },
    notices, results: [], count: 0, total: 0,
    score_note: "Relevance index, not a probability. Compare results within this search. Eligibility has not been assessed.",
  };
  const candidates = records.filter((row) => isOpenOpportunity(row, now));
  if (!specific.size || !candidates.length) return result;
  const frequency = new Map();
  const documents = candidates.map((row) => {
    const texts = fields(row), counts = {}, lengths = {};
    const all = new Set();
    for (const [key, value] of Object.entries(texts)) {
      counts[key] = new Map();
      const analyzed = analyze(value);
      lengths[key] = analyzed.length;
      for (const term of analyzed) { counts[key].set(term, (counts[key].get(term) || 0) + 1); all.add(term); }
    }
    for (const term of all) frequency.set(term, (frequency.get(term) || 0) + 1);
    return { row, texts, counts, lengths };
  });
  const factors = { title: 4, programme: 0.5, keywords: 2, description: 1 };
  const averages = {};
  for (const key of Object.keys(factors)) averages[key] = Math.max(1, documents.reduce((sum, doc) => sum + doc.lengths[key], 0) / documents.length);
  const weights = new Map();
  for (const term of terms) {
    const df = frequency.get(term) || 0;
    weights.set(term, Math.log(1 + (documents.length - df + 0.5) / (df + 0.5)) * (keywordTerms.has(term) ? 2.5 : 1) * (generic.has(term) ? 0.12 : 1));
  }
  const denominator = [...weights.values()].reduce((a, b) => a + b, 0);
  const scored = [];
  const byWeight = (a, b) => weights.get(b) - weights.get(a) || compare(a, b);
  for (const { row, texts, counts, lengths } of documents) {
    if (kind && row.kind !== kind) continue;
    const actual = new Set([...counts.title.keys(), ...counts.keywords.keys(), ...counts.description.keys()]);
    const supportedFocus = [...focus].filter((term) => actual.has(term));
    if (!supportedFocus.length) continue;
    if (priority.length && supportedFocus.length < Math.ceil(focus.size / 2)) continue;
    const matched = [...terms].filter((term) => actual.has(term));
    const coverage = matched.reduce((sum, term) => sum + weights.get(term), 0) / denominator;
    let strength = 0;
    for (const term of matched) {
      let tf = 0;
      for (const [field, factor] of Object.entries(factors)) {
        const b = field === "description" ? 0.75 : 0.3;
        tf += factor * Math.min(3, counts[field].get(term) || 0) / (1 - b + b * lengths[field] / averages[field]);
      }
      strength += weights.get(term) * tf / (1.2 + tf);
    }
    strength /= denominator;
    const score = Math.round(1000 * (0.55 * coverage + 0.45 * strength) * (0.6 + 0.4 * coverage)) / 10;
    if (score < 15) continue;
    const topical = matched.filter((term) => !generic.has(term));
    const level = coverage >= 0.7 && topical.length >= 2 && score >= 60 ? "Strong text evidence" : coverage >= 0.4 && score >= 30 ? "Partial text evidence" : "Limited text evidence";
    const [title, programme] = displayTitle(row);
    scored.push({
      id: row.id || row.identifier || "", score, match_level: level, matched_terms: [...matched].sort(),
      missing_topics: [...specific].filter((term) => !actual.has(term)).sort(byWeight),
      evidence: [...topical].sort(byWeight).map((topic) => ({ topic, fields: ["title", "keywords", "description"].filter((key) => counts[key].has(topic)) })),
      eligibility: "Not assessed", kind: row.kind, identifier: row.identifier, title, programme_title: programme,
      description: excerpt(texts.description, new Set(topical), analyze), deadline: row.deadline,
      url: row.url || "", programme_code: row.programme_code || "",
    });
  }
  scored.sort((a, b) => b.score - a.score || compare(a.deadline, b.deadline) || compare(a.id, b.id));
  result.results = scored.slice(0, limit);
  result.count = result.results.length;
  result.total = scored.length;
  if (!scored.length) notices.push("No sufficient text evidence was found. Try fewer priority keywords or a different description; there may be no suitable open call in this collection.");
  else if (!scored.some((row) => row.match_level === "Strong text evidence")) notices.push("No strong text match was found. The results below cover only part of your description; review the missing topics and official scope.");
  return result;
}
function rankOpportunities(records, description, keywords, kind, config, limit = 20, now = Date.now()) {
  return assessOpportunities(records, description, keywords, kind, config, limit, now).results;
}
const OpportunityMatcher = { isOpenOpportunity, parseSourceDate, rankOpportunities, assessOpportunities, createAnalyzer };
if (typeof window !== "undefined") window.OpportunityMatcher = OpportunityMatcher;
if (typeof module !== "undefined") module.exports = OpportunityMatcher;
