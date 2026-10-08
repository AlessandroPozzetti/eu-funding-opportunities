"use strict";

const $ = (id) => document.getElementById(id);
const staticMode = document.documentElement.dataset.mode === "static";
const PAGE_SIZE = 6;
const state = { dataset: null, datasetPromise: null, results: [], total: 0, visible: PAGE_SIZE, query: null, request: 0 };
const EXAMPLES = {
  cyber: { description: "We develop AI-powered cybersecurity products to help small businesses detect attacks and respond to incidents.", keywords: ["cybersecurity", "SME", "AI"], kind: "grant" },
  culture: { description: "We develop extended reality experiences for cultural heritage sites and museums.", keywords: ["cultural heritage", "extended reality"], kind: "grant" },
  software: { description: "We develop software applications and provide ongoing maintenance for public organisations.", keywords: ["software", "maintenance"], kind: "tender" },
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

function loadDataset() {
  if (!state.datasetPromise) {
    state.datasetPromise = fetch(staticMode ? "opportunities.json" : "/api/opportunities", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("The opportunity collection is temporarily unavailable.");
        return response.json();
      })
      .then((snapshot) => {
        if (!Array.isArray(snapshot.records)) throw new Error("The collection could not be read. Please try again.");
        state.dataset = snapshot;
        return snapshot;
      })
      .catch((error) => { state.datasetPromise = null; throw error; });
  }
  return state.datasetPromise;
}

async function getMatches(payload) {
  if (staticMode) {
    const snapshot = await loadDataset();
    return window.OpportunityMatcher.assessOpportunities(
      snapshot.records, payload.description, payload.keywords, payload.kind, snapshot.matching_config);
  }
  const response = await fetch("/api/match", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The search could not be completed.");
  return data;
}

function formatDate(value) {
  const timestamp = window.OpportunityMatcher.parseSourceDate(value);
  if (!Number.isFinite(timestamp)) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "Europe/Brussels",
  }).format(timestamp);
}

function emptyState(title, message, symbol = "search") {
  const box = element("div", "empty-state");
  box.append(icon(symbol), element("h4", "", title), element("p", "", message));
  return box;
}

function sourceLink(result) {
  if (!result.url || !/^https:\/\//.test(result.url)) return null;
  const link = element("a", "source-link", "View official call");
  link.href = result.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.append(icon("external"));
  return link;
}

function explanation(result) {
  const details = element("details", "match-explanation");
  details.append(element("summary", "", "Why this matches"));
  const content = element("div", "evidence-content");
  content.append(element("blockquote", "", result.description || "No source excerpt is available."));
  content.append(element("h5", "", "Supporting topics"));
  const topics = element("div", "topic-tags");
  for (const evidence of result.evidence || []) {
    const tag = element("span", "", evidence.topic);
    tag.title = `Found in: ${evidence.fields.join(", ")}`;
    topics.append(tag);
  }
  content.append(topics, element("h5", "", "Still to check"));
  content.append(element("p", "", result.missing_topics.length
    ? `Not found in the available text: ${result.missing_topics.join(", ")}.`
    : "Your search topics appear in the available text. Confirm the complete scope in the official documents."));
  content.append(element("p", "eligibility-note", "Eligibility is not assessed. Check country, applicant type, consortium, budget and eligible activities in the official call."));
  details.append(content);
  return details;
}

function renderResult(result) {
  const isMatch = typeof result.score === "number";
  const card = element("article", "result-card");
  const top = element("div", "result-top");
  const meta = element("div", "result-meta");
  meta.append(element("span", `tag ${result.kind}`, result.kind === "tender" ? "Public contract" : "Grant"));
  meta.append(element("span", "identifier", result.identifier));
  top.append(meta);
  const remaining = window.OpportunityMatcher.parseSourceDate(result.deadline) - Date.now();
  if (remaining >= 0 && remaining < 7 * 86400000) {
    top.append(element("span", "deadline-count soon", remaining < 86400000 ? "Closes within 24h" : `Closes in ${Math.ceil(remaining / 86400000)} days`));
  }
  const heading = element("div", "card-heading");
  heading.append(element("h4", "", result.title));
  if (isMatch) {
    const score = element("div", "score");
    score.title = "Relevance index out of 100. Compare results within this search. This is not a probability or an eligibility decision.";
    score.setAttribute("aria-label", `Relevance index: ${result.score} out of 100`);
    score.append(element("strong", "", String(result.score)), element("span", "", "/100"));
    heading.append(score);
  }
  card.append(top, heading, element("p", "description", result.description || "Open the official call for the full scope and requirements."));
  if (isMatch) {
    card.append(element("p", `evidence-level ${result.match_level.startsWith("Strong") ? "strong" : ""}`, result.match_level));
    card.append(explanation(result));
  }
  const footer = element("div", "result-details");
  const deadline = element("span", "deadline");
  deadline.append(icon("clock"), document.createTextNode(`Closes ${formatDate(result.deadline)}`));
  footer.append(deadline);
  const link = sourceLink(result);
  if (link) footer.append(link);
  card.append(footer);
  return card;
}

function setBusy(busy) {
  $("submit-button").disabled = busy;
  $("submit-button").replaceChildren(element("span", "", busy ? "Comparing your project…" : "Find my matches"), icon("arrow"));
  $("results").setAttribute("aria-busy", String(busy));
}

function renderList() {
  const matching = state.query !== null;
  const rows = [...state.results];
  if ($("sort").value === "deadline") {
    rows.sort((a, b) => window.OpportunityMatcher.parseSourceDate(a.deadline) - window.OpportunityMatcher.parseSourceDate(b.deadline) || a.title.localeCompare(b.title));
  } else {
    rows.sort((a, b) => b.score - a.score);
  }
  const shown = rows.slice(0, state.visible);
  $("results-title").replaceChildren(document.createTextNode(matching ? "Your opportunity matches " : "Open opportunities "), element("span", "count-badge", state.total.toLocaleString("en-GB")));
  $("results-eyebrow").textContent = matching ? "A SHORTLIST FOR YOUR PROJECT" : "THE CURRENT LANDSCAPE";
  $("results-subtitle").textContent = matching
    ? `${rows.length} ranked ${rows.length === 1 ? "result" : "results"} from ${state.total} text matches.`
    : "Open calls from the latest collection.";
  $("clear-search").hidden = !matching;
  $("sort").querySelector('[value="relevance"]').disabled = !matching;
  $("results").replaceChildren(...(shown.length ? shown.map(renderResult) : [emptyState(
    matching ? "No sufficient match found" : "No open calls in this view",
    matching ? "Try a more specific English description, adjust your priority topics or explore both grants and tenders. The collection may not include a suitable call." : "Try another opportunity type or check back after the next collection.",
  )]));
  $("visible-count").textContent = rows.length ? `Showing ${shown.length} of ${rows.length}${matching ? " ranked results" : " opportunities"}` : "";
  $("load-more").hidden = shown.length >= rows.length;
  $("results").setAttribute("aria-busy", "false");
}

function browse() {
  if (!state.dataset) return;
  state.query = null;
  state.visible = PAGE_SIZE;
  const kind = $("kind").value;
  state.results = state.dataset.records.filter((row) => window.OpportunityMatcher.isOpenOpportunity(row) && (!kind || row.kind === kind)).map((row) => ({
    ...row,
    title: (row.id || "").includes("COMPETITIVE_CALL") && row.call_title ? row.call_title : row.title,
    description: (row.description || "").slice(0, 360),
  }));
  state.total = state.results.length;
  $("sort").value = "deadline";
  $("search-notes").hidden = true;
  renderList();
}

function showNotes(data) {
  const notes = $("search-notes");
  notes.replaceChildren();
  for (const notice of data.notices) notes.append(element("p", "", notice));
  if (data.query.priority_topics.length) notes.append(element("p", "", `Priority topics: ${data.query.priority_topics.join(", ")}.`));
  notes.append(element("p", "score-note", "The relevance index compares text evidence within this search. It is not a funding probability; eligibility still requires review."));
  notes.hidden = false;
}

async function search(payload) {
  const request = ++state.request;
  state.query = payload;
  setBusy(true);
  $("search-notes").hidden = true;
  $("load-more").hidden = true;
  $("visible-count").textContent = "";
  $("results-subtitle").textContent = "Reading the evidence for your project…";
  $("results").replaceChildren(emptyState("Connecting the dots", "Comparing your priority topics with the available call descriptions."));
  try {
    if (payload.keywords.length > 25 || payload.keywords.some((keyword) => keyword.length > 80)) throw new Error("Use up to 25 priority topics, each at most 80 characters.");
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const data = await getMatches(payload);
    if (request !== state.request) return;
    state.results = data.results;
    state.total = data.total;
    state.visible = PAGE_SIZE;
    $("sort").value = "relevance";
    showNotes(data);
    renderList();
  } catch (error) {
    if (request !== state.request) return;
    state.results = [];
    state.total = 0;
    $("clear-search").hidden = false;
    $("results-subtitle").textContent = "The search could not be completed.";
    $("results").replaceChildren(emptyState("Let’s try that again", error.message));
  } finally {
    if (request === state.request) setBusy(false);
  }
}

async function initialise() {
  try {
    const dataset = await loadDataset();
    const active = dataset.records.filter((row) => window.OpportunityMatcher.isOpenOpportunity(row));
    $("active-count").textContent = active.length.toLocaleString("en-GB");
    $("grant-count").textContent = active.filter((row) => row.kind === "grant").length.toLocaleString("en-GB");
    $("tender-count").textContent = active.filter((row) => row.kind === "tender").length.toLocaleString("en-GB");
    $("last-collected").textContent = dataset.last_collected ? `Updated ${formatDate(dataset.last_collected)}` : "Awaiting the first collection";
    $("privacy-copy").textContent = staticMode ? "Your project stays in your browser. No account required." : "Processed on your local server. No saved project descriptions.";
    const warning = $("dataset-warning");
    warning.hidden = true;
    const age = Date.now() - Date.parse(dataset.last_collected);
    if (!dataset.stored || !Number.isFinite(age) || age > 36 * 3600000) {
      warning.textContent = dataset.stored ? "This collection is older than the usual daily update. Check current availability on the official call pages." : "The opportunity collection is not available yet. Please check back after the next update.";
      warning.hidden = false;
    }
    if (!state.query) browse();
  } catch (error) {
    const warning = $("dataset-warning");
    const retry = element("button", "", "Try again");
    retry.type = "button";
    retry.addEventListener("click", initialise);
    warning.replaceChildren(document.createTextNode(error.message), retry);
    warning.hidden = false;
    $("results").replaceChildren(emptyState("The catalogue is taking a moment", "Try loading it again using the button above."));
    $("results").setAttribute("aria-busy", "false");
    $("results-subtitle").textContent = "Collection unavailable";
  }
}

$("match-form").addEventListener("submit", (event) => {
  event.preventDefault();
  search({ description: $("description").value.trim(), keywords: $("keywords").value.split(",").map((word) => word.trim()).filter(Boolean), kind: $("kind").value });
});
$("kind").addEventListener("change", () => state.query ? search({ ...state.query, kind: $("kind").value }) : browse());
$("sort").addEventListener("change", renderList);
$("load-more").addEventListener("click", () => { state.visible += PAGE_SIZE; renderList(); });
$("clear-search").addEventListener("click", () => {
  state.request += 1;
  $("description").value = "";
  $("keywords").value = "";
  setBusy(false);
  browse();
});
for (const button of document.querySelectorAll("[data-example]")) {
  button.addEventListener("click", () => {
    const example = EXAMPLES[button.dataset.example];
    $("description").value = example.description;
    $("keywords").value = example.keywords.join(", ");
    $("kind").value = example.kind;
    $("match-form").requestSubmit();
  });
}
for (const button of document.querySelectorAll("[data-browse-kind]")) {
  button.addEventListener("click", () => {
    state.request += 1;
    setBusy(false);
    $("kind").value = button.dataset.browseKind;
    browse();
    $("explore").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  });
}
initialise();
