const $ = (id) => document.getElementById(id);
const staticMode = document.documentElement.dataset.mode === "static";
let staticDataPromise;

function loadStaticData() {
  if (!staticDataPromise) {
    staticDataPromise = fetch("opportunities.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error("Unable to load the current opportunities");
      return response.json();
    });
  }
  return staticDataPromise;
}

async function getStatus() {
  if (staticMode) {
    const snapshot = await loadStaticData();
    const active = snapshot.records.filter((row) => window.OpportunityMatcher.isOpenOpportunity(row));
    return {
      stored: snapshot.stored,
      active: active.length,
      active_grants: active.filter((row) => row.kind === "grant").length,
      active_tenders: active.filter((row) => row.kind === "tender").length,
      last_collected: snapshot.last_collected,
    };
  }
  const response = await fetch("/api/status", { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to read dataset status");
  return response.json();
}

async function getMatches(payload) {
  if (staticMode) {
    const snapshot = await loadStaticData();
    return window.OpportunityMatcher.assessOpportunities(
      snapshot.records, payload.description, payload.keywords, payload.kind, snapshot.matching_config);
  }
  const response = await fetch("/api/match", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Matching failed");
  return data;
}

function formatDate(value) {
  const date = new Date(window.OpportunityMatcher.parseSourceDate(value));
  if (Number.isNaN(date.getTime())) return value || "Unknown";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Europe/Brussels" }).format(date);
}

function emptyState(title, message) {
  const box = document.createElement("div");
  box.className = "empty-state";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const text = document.createElement("p");
  text.textContent = message;
  box.append(heading, text);
  return box;
}

function renderResult(result) {
  const card = document.createElement("article");
  card.className = "result-card";
  const top = document.createElement("div");
  top.className = "result-top";
  const meta = document.createElement("div");
  meta.className = "result-meta";
  const type = document.createElement("span");
  type.className = "tag";
  type.textContent = result.kind === "tender" ? "Tender" : "Grant";
  const id = document.createElement("span");
  id.textContent = result.identifier;
  meta.append(type, id);
  const score = document.createElement("div");
  score.className = "score";
  const scoreNumber = document.createElement("strong");
  scoreNumber.textContent = `${result.score}/100`;
  const scoreLabel = document.createElement("span");
  scoreLabel.textContent = "relevance index";
  score.title = "An uncalibrated index of text evidence. Compare results within this search; this is not a probability or an eligibility decision.";
  score.append(scoreNumber, scoreLabel);
  top.append(meta, score);

  const title = document.createElement("h3");
  title.textContent = result.title;
  const description = document.createElement("p");
  description.textContent = result.description || "See the official source for details.";
  const terms = document.createElement("div");
  terms.className = "match-terms";
  terms.textContent = `Supported topics: ${result.evidence.map((item) => `${item.topic} (${item.fields.join(", ")})`).join("; ")}`;
  const level = document.createElement("p");
  level.className = "match-level";
  level.textContent = result.match_level;
  const missing = document.createElement("p");
  missing.className = "missing-topics";
  missing.textContent = result.missing_topics.length
    ? `Not found in available text: ${result.missing_topics.join(", ")}.`
    : "Your search topics appear in the available text. Confirm the full scope in the official documents.";
  const eligibility = document.createElement("p");
  eligibility.className = "eligibility-note";
  eligibility.textContent = "Eligibility not assessed: check country, organisation type, consortium and eligible activities.";
  const details = document.createElement("div");
  details.className = "result-details";
  const deadline = document.createElement("span");
  deadline.textContent = `Deadline: ${formatDate(result.deadline)}`;
  details.append(deadline);
  if (result.url && /^https:\/\//.test(result.url)) {
    const link = document.createElement("a");
    link.href = result.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Official opportunity ↗";
    details.append(link);
  }
  card.append(top, title, level, description, terms, missing, eligibility, details);
  return card;
}

async function refreshStatus() {
  try {
    const status = await getStatus();
    $("active-count").textContent = status.active.toLocaleString("en-GB");
    $("grant-count").textContent = `${status.active_grants.toLocaleString("en-GB")} grants`;
    $("tender-count").textContent = `${status.active_tenders.toLocaleString("en-GB")} tenders`;
    $("last-collected").textContent = status.last_collected ? `Last collected: ${formatDate(status.last_collected)}` : "No collection has run yet";
    if (!status.stored) {
      $("dataset-warning").textContent = staticMode
        ? "No opportunities have been published yet. Please try again after the next update."
        : "The dataset is empty. Run `python3 -m bandi_eu sync` from the project directory, then refresh this page.";
      $("dataset-warning").hidden = false;
    }
  } catch (error) {
    $("dataset-warning").textContent = error.message;
    $("dataset-warning").hidden = false;
  }
}

$("match-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("submit-button");
  const results = $("results");
  button.disabled = true;
  button.textContent = "Finding opportunities…";
  $("search-notes").hidden = true;
  $("results-subtitle").textContent = "Comparing your text with open opportunities…";
  results.replaceChildren(emptyState("Searching", "This may take a moment for a large dataset."));
  try {
    const payload = {
      description: $("description").value.trim(),
      keywords: $("keywords").value.split(",").map((part) => part.trim()).filter(Boolean),
      kind: $("kind").value,
    };
    const data = await getMatches(payload);
    $("results-subtitle").textContent = `Showing ${data.count} of ${data.total} open opportunities with text evidence. Sorted by relevance index.`;
    const notes = $("search-notes");
    notes.replaceChildren();
    for (const text of [...data.notices, data.score_note]) {
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      notes.append(paragraph);
    }
    if (data.query.priority_topics.length) {
      const paragraph = document.createElement("p");
      paragraph.textContent = `Priority topics: ${data.query.priority_topics.join(", ")}.`;
      notes.append(paragraph);
    }
    notes.hidden = false;
    if (!data.count) {
      results.replaceChildren(emptyState("No sufficient match found", "Add specific English terms or adjust your priority keywords. The current collection may not contain a suitable open opportunity."));
    } else {
      results.replaceChildren(...data.results.map(renderResult));
    }
  } catch (error) {
    $("results-subtitle").textContent = "The search could not be completed.";
    results.replaceChildren(emptyState("Something went wrong", error.message));
  } finally {
    button.disabled = false;
    button.replaceChildren(document.createTextNode("Find matching opportunities "), Object.assign(document.createElement("span"), { textContent: "→" }));
  }
});

refreshStatus();
