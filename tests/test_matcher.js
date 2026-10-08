"use strict";

const assert = require("node:assert/strict");
const { isOpenOpportunity, rankOpportunities, assessOpportunities } = require("../web/matcher.js");
const config = require("../bandi_eu/matching_config.json");

const future = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
const past = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
assert.equal(isOpenOpportunity({ status: "open", listed: true, deadline: future.replace("Z", "+0000") }), true);
const base = {
  kind: "grant", identifier: "A", title: "Battery recycling", call_title: "",
  description: "Energy research", keywords: ["battery"], tags: [],
  deadline: future, url: "https://example.org/a", programme_code: "", status: "open", listed: true,
};
const titleMatch = { ...base };
const descriptionMatch = {
  ...base, identifier: "B", title: "Other research",
  description: "Battery recycling and energy systems", url: "https://example.org/b",
};
const expired = { ...base, identifier: "C", deadline: past };

assert.equal(isOpenOpportunity(titleMatch), true);
assert.equal(isOpenOpportunity(expired), false);
const results = rankOpportunities(
  [titleMatch, descriptionMatch, expired], "battery recycling", [], "grant", config);
assert.equal(results.length, 2);
assert.equal(results[0].identifier, "A");
assert.ok(results[0].score > results[1].score);
assert.deepEqual(rankOpportunities([titleMatch], "battery", [], "tender", config), []);
assert.deepEqual(rankOpportunities([titleMatch], "digital", [], "", config), []);
assert.equal(isOpenOpportunity({ ...base, deadline: "2026-10-08" }, Date.parse("2026-10-08T22:30:00Z")), false);
assert.equal(isOpenOpportunity({ ...base, deadline: "2026-01-08" }, Date.parse("2026-01-08T22:30:00Z")), true);
assert.equal(isOpenOpportunity({ ...base, deadline: "2026-99-99" }), false);
assert.equal(isOpenOpportunity({ ...base, deadline: "2026-02-30" }), false);

const softwareDescription = "We develop software applications and provide ongoing maintenance for public organisations.";
const tender = (id, title) => ({
  ...base, id, identifier: id, kind: "tender", title, description: "Applications for public organisations", keywords: [],
});
const softwareRecords = [
  tender("complete", "Software development and maintenance"),
  tender("partial", "Software application development"),
  tender("unrelated", "Ongoing office activities"),
];
for (const keywords of [[], ["software", "maintenance"], ["software", "ongoing maintenance"]]) {
  const actual = assessOpportunities(softwareRecords, softwareDescription, keywords, "tender", config);
  const plain = assessOpportunities(softwareRecords, softwareDescription.replace("ongoing ", ""), keywords, "tender", config);
  assert.deepEqual(actual, plain);
  assert.deepEqual(actual.query.topics, ["maintenance", "software"]);
  assert.deepEqual(actual.results.map(row => row.id), ["complete", "partial"]);
  assert.deepEqual(actual.results[0].missing_topics, []);
  assert.deepEqual(actual.results[1].missing_topics, ["maintenance"]);
}
const maintenanceRecords = [
  tender("routine", "Software maintenance"),
  tender("predictive", "Software for predictive maintenance"),
];
const maintenanceMatches = rankOpportunities(maintenanceRecords, "Software for predictive maintenance",
  ["software", "maintenance"], "tender", config);
assert.deepEqual(maintenanceMatches.map(row => row.id), ["predictive", "routine"]);
assert.deepEqual(maintenanceMatches[0].missing_topics, []);
assert.deepEqual(maintenanceMatches[1].missing_topics, ["predictive"]);
console.log("Static portal matcher: OK");
