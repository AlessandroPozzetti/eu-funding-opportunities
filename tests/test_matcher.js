"use strict";

const assert = require("node:assert/strict");
const { isOpenOpportunity, rankOpportunities } = require("../web/matcher.js");

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
  [titleMatch, descriptionMatch, expired], "battery recycling", [], "grant", ["and"]);
assert.equal(results.length, 2);
assert.equal(results[0].identifier, "A");
assert.ok(results[0].score > results[1].score);
assert.deepEqual(rankOpportunities([titleMatch], "battery", [], "tender", []), []);
console.log("Static portal matcher: OK");
