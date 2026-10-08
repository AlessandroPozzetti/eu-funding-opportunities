import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import unittest

from bandi_eu.core import assess
from bandi_eu.matching import CONFIG, analyze

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE_DESCRIPTION = "We develop software applications and provide ongoing maintenance for public organisations."


def record(key, title, description="", kind="grant", **extra):
    return dict(id=key, identifier=key, title=title, description=description, kind=kind,
                status="open", deadline=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(), **extra)


class MatchingTests(unittest.TestCase):
    def test_generic_and_absent_queries_do_not_create_false_confidence(self):
        rows = {"digital": record("digital", "Digital communications")}
        self.assertEqual(assess(rows, "digital", [])["results"], [])
        self.assertIn("too broad", assess(rows, "digital", [])["notices"][0])
        self.assertEqual(assess(rows, "Digital platform", ["digital platform"])["results"], [])
        self.assertEqual(assess(rows, "Harpsichord manufacturing", ["harpsichord"])["results"], [])

    def test_battery_project_rejects_paper_recycling_and_generic_power(self):
        rows = {"battery": record("battery", "Battery recycling and energy storage"),
                "fusion": record("fusion", "Fusion power plants", "Energy and power systems"),
                "paper": record("paper", "Recycled paper supply")}
        results = assess(rows, "We develop recyclable batteries for local power grids", ["battery", "recycling", "energy storage"])["results"]
        self.assertEqual([row["id"] for row in results], ["battery"])

    def test_specific_call_title_takes_priority_over_parent_programme(self):
        rows = {"grant:COMPETITIVE_CALL-A": record("grant:COMPETITIVE_CALL-A", "Digital cybersecurity programme", "Office furniture", call_title="Furniture supply"),
                "grant:COMPETITIVE_CALL-B": record("grant:COMPETITIVE_CALL-B", "Digital programme", "Cybersecurity for SMEs", call_title="Cybersecurity implementation grants")}
        results = assess(rows, "cybersecurity", [])["results"]
        self.assertEqual([row["id"] for row in results], ["grant:COMPETITIVE_CALL-B"])
        self.assertEqual(results[0]["title"], "Cybersecurity implementation grants")

    def test_aliases_plurals_and_acronyms_preserve_meaning(self):
        self.assertEqual(analyze("batteries"), analyze("battery"))
        self.assertEqual(analyze("XR"), analyze("extended reality"))
        self.assertIn("artificial intelligence", analyze("AI"))
        self.assertNotIn("artificial intelligence", analyze("ai musei"))
        self.assertNotIn("photovoltaics", analyze("solar radiation modification"))

    def test_length_and_repetition_do_not_beat_specific_title(self):
        rows = {"specific": record("specific", "Battery recycling", "Recover materials from batteries"),
                "long": record("long", "General research", ("battery recycling unrelated paperwork " * 300))}
        results = assess(rows, "Battery recycling", [])["results"]
        self.assertEqual(results[0]["id"], "specific")

    def test_type_filter_does_not_change_scores(self):
        rows = {"grant": record("grant", "Battery recycling"),
                "tender": record("tender", "Battery recycling equipment", kind="tender")}
        both = assess(rows, "Battery recycling", [])["results"]
        grants = assess(rows, "Battery recycling", [], kind="grant")["results"]
        self.assertEqual(grants, [row for row in both if row["kind"] == "grant"])

    def test_priority_phrases_do_not_match_incidental_words(self):
        rows = {"water": record("water", "Sustainable water management"),
                "compute": record("compute", "AI computing", "Management of a data centre with water supply")}
        results = assess(rows, "Research on sustainable water management", ["water management"])["results"]
        self.assertEqual([row["id"] for row in results], ["water"])

    def test_evidence_is_traceable_and_missing_topics_are_explicit(self):
        rows = {"wood": record("wood", "Wood construction", "Wood construction prototypes")}
        result = assess(rows, "Wood construction and robotics", ["wood", "construction", "robotics"])["results"][0]
        self.assertIn("robotics", result["missing_topics"])
        self.assertEqual(result["eligibility"], "Not assessed")
        self.assertTrue(any(e["topic"] == "wood" and "title" in e["fields"] for e in result["evidence"]))

    def test_ongoing_does_not_change_software_matches_or_missing_topics(self):
        rows = {
            "complete": record("complete", "Software development and maintenance",
                               "Applications for public organisations", kind="tender"),
            "partial": record("partial", "Software application development",
                              "Applications for public organisations", kind="tender"),
            "unrelated": record("unrelated", "Ongoing office activities", kind="tender"),
        }
        for keywords in ([], ["software", "maintenance"], ["software", "ongoing maintenance"]):
            with self.subTest(keywords=keywords):
                result = assess(rows, SOFTWARE_DESCRIPTION, keywords, kind="tender")
                plain = assess(rows, SOFTWARE_DESCRIPTION.replace("ongoing ", ""), keywords, kind="tender")
                self.assertEqual(result, plain)
                self.assertEqual(result["query"]["topics"], ["maintenance", "software"])
                self.assertEqual([r["id"] for r in result["results"]], ["complete", "partial"])
                self.assertEqual(result["results"][0]["missing_topics"], [])
                self.assertEqual(result["results"][1]["missing_topics"], ["maintenance"])

    def test_technical_modifiers_remain_meaningful(self):
        rows = {
            "routine": record("routine", "Software maintenance"),
            "predictive": record("predictive", "Software for predictive maintenance"),
        }
        results = assess(rows, "Software for predictive maintenance", ["software", "maintenance"])["results"]
        self.assertEqual([r["id"] for r in results], ["predictive", "routine"])
        self.assertEqual(results[0]["missing_topics"], [])
        self.assertEqual(results[1]["missing_topics"], ["predictive"])

    def test_software_description_retrieves_relevant_frozen_tenders_without_false_gaps(self):
        fixture = json.loads((ROOT / "evaluation/fixtures/opportunities.json").read_text())
        rows = {row["id"]: row for row in fixture["records"]}
        targets = {"tender:fbbea1db-f251-41de-a4db-8c2c9e16b2ae-CN",
                   "tender:8a8d8225-ef94-4781-b70a-72acca9f4291-CN"}
        for keywords in ([], ["software", "maintenance"]):
            with self.subTest(keywords=keywords):
                result = assess(rows, SOFTWARE_DESCRIPTION, keywords, kind="tender",
                                now=datetime.fromisoformat(fixture["as_of"]))
                self.assertEqual({r["id"] for r in result["results"][:2]}, targets)
                for row in result["results"][:2]:
                    self.assertEqual(row["missing_topics"], [])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for browser/server parity")
    def test_browser_and_python_agree_on_all_frozen_scenarios(self):
        fixture = json.loads((ROOT / "evaluation/fixtures/opportunities.json").read_text())
        cases = json.loads((ROOT / "evaluation/cases.json").read_text())["cases"]
        cases += [dict(id=f"software_description_{index}", description=SOFTWARE_DESCRIPTION,
                       keywords=keywords, kind="tender")
                  for index, keywords in enumerate(([], ["software", "maintenance"]))]
        code = """
          const fs = require('node:fs');
          const {assessOpportunities} = require('./web/matcher.js');
          const input = JSON.parse(fs.readFileSync(0, 'utf8'));
          const results = input.cases.map(c => assessOpportunities(input.fixture.records, c.description,
            c.keywords, c.kind, input.config, 20, Date.parse(input.fixture.as_of)));
          process.stdout.write(JSON.stringify(results));
        """
        output = subprocess.run(["node", "-e", code], input=json.dumps(dict(fixture=fixture, cases=cases, config=CONFIG)),
                                text=True, capture_output=True, cwd=ROOT, timeout=60, check=True)
        browser = json.loads(output.stdout)
        rows = {row["id"]: row for row in fixture["records"]}
        for case, actual in zip(cases, browser):
            with self.subTest(case=case["id"]):
                expected = assess(rows, case["description"], case["keywords"], kind=case["kind"] or None,
                                  now=datetime.fromisoformat(fixture["as_of"]))
                self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
