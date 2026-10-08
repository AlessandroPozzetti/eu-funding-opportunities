const $ = (id) => document.getElementById(id);

function formatDate(value) {
  const date = new Date(value);
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
  scoreNumber.textContent = `${result.score}%`;
  const scoreLabel = document.createElement("span");
  scoreLabel.textContent = "text match";
  score.append(scoreNumber, scoreLabel);
  top.append(meta, score);

  const title = document.createElement("h3");
  title.textContent = result.title;
  const description = document.createElement("p");
  description.textContent = result.description || "See the official source for details.";
  const terms = document.createElement("div");
  terms.className = "match-terms";
  terms.textContent = `Matched terms: ${result.matched_terms.join(", ")}`;
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
  card.append(top, title, description, terms, details);
  return card;
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("Unable to read dataset status");
    const status = await response.json();
    $("active-count").textContent = status.active.toLocaleString("en-GB");
    $("grant-count").textContent = `${status.active_grants.toLocaleString("en-GB")} grants`;
    $("tender-count").textContent = `${status.active_tenders.toLocaleString("en-GB")} tenders`;
    $("last-collected").textContent = status.last_collected ? `Last collected: ${formatDate(status.last_collected)}` : "No collection has run yet";
    if (!status.stored) {
      $("dataset-warning").textContent = "The dataset is empty. Run `python3 -m bandi_eu sync` from the project directory, then refresh this page.";
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
  $("results-subtitle").textContent = "Comparing your text with open opportunities…";
  results.replaceChildren(emptyState("Searching", "This may take a moment for a large dataset."));
  try {
    const payload = {
      description: $("description").value.trim(),
      keywords: $("keywords").value.split(",").map((part) => part.trim()).filter(Boolean),
      kind: $("kind").value,
    };
    const response = await fetch("/api/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Matching failed");
    $("results-subtitle").textContent = `${data.count} relevant open ${data.count === 1 ? "opportunity" : "opportunities"} found. Sorted by text match.`;
    if (!data.count) {
      results.replaceChildren(emptyState("No matches yet", "Try broader terms, add English keywords, or choose both grants and tenders."));
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
