#!/usr/bin/env python3
"""Compare retrieval versions on a fixed, explicitly labelled pilot corpus."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bandi_eu.core import assess
from evaluation.baseline import rank as baseline_rank


def evaluate() -> dict:
    fixture_path = ROOT / "evaluation/fixtures/opportunities.json"
    fixture = json.loads(fixture_path.read_text())
    labels = json.loads((ROOT / "evaluation/cases.json").read_text())
    rows = {row["id"]: row for row in fixture["records"]}
    now = datetime.fromisoformat(fixture["as_of"])
    cases = []
    for case in labels["cases"]:
        for key in case["expected"] + case["avoid"]:
            if key not in rows:
                raise ValueError(f"Unknown judgement record: {key}")
        old = baseline_rank(rows, case["description"], case["keywords"], len(rows), case["kind"] or None, as_of=now)
        new = assess(rows, case["description"], case["keywords"], len(rows), case["kind"] or None, now=now)
        entry = {"id": case["id"], "language": case["language"], "systems": {}}
        for name, results in (("baseline", old), ("current", new["results"])):
            positions = {row["id"]: i + 1 for i, row in enumerate(results)}
            expected = [positions.get(key) for key in case["expected"]]
            pairs = [positions.get(positive, float("inf")) < positions.get(negative, float("inf"))
                     for positive in case["expected"] for negative in case["avoid"]]
            output = {"target_ranks": expected, "returned": len(results), "pairs_passed": sum(pairs), "pairs_total": len(pairs),
                      "top_results": [{key: row[key] for key in ("id", "title", "score")} for row in results[:5]]}
            if expected:
                found = [position for position in expected if position is not None]
                output.update(hit_at_5=any(position <= 5 for position in found),
                              known_target_recall_at_5=sum(position <= 5 for position in found) / len(expected),
                              reciprocal_rank=1 / min(found) if found else 0)
            if case.get("expect_empty"):
                output["empty_query_passed"] = not results
            if case.get("no_strong"):
                output["forbidden_results_absent"] = not any(key in positions for key in case["avoid"])
                if name == "current":
                    output["no_strong_passed"] = not any(row["match_level"] == "Strong text evidence" for row in results)
            entry["systems"][name] = output
        cases.append(entry)
    summary = {}
    for language in ("en", "it"):
        language_cases = [case for case in cases if case["language"] == language]
        summary[language] = {}
        for name in ("baseline", "current"):
            results = [case["systems"][name] for case in language_cases]
            targets = [result for result in results if "hit_at_5" in result]
            summary[language][name] = {
                "target_queries": len(targets), "target_queries_hit_at_5": sum(r["hit_at_5"] for r in targets),
                "mean_known_target_recall_at_5": round(sum(r["known_target_recall_at_5"] for r in targets) / len(targets), 4),
                "mean_reciprocal_rank": round(sum(r["reciprocal_rank"] for r in targets) / len(targets), 4),
                "pairs_passed": sum(r["pairs_passed"] for r in results), "pairs_total": sum(r["pairs_total"] for r in results),
                "empty_queries_passed": sum(r.get("empty_query_passed", False) for r in results),
                "empty_queries_total": sum("empty_query_passed" in r for r in results),
            }
    return {"label_provenance": labels["label_provenance"], "as_of": fixture["as_of"], "corpus_size": len(rows),
            "corpus_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256((ROOT / "bandi_eu/matching_config.json").read_bytes()).hexdigest(),
            "summary": summary, "cases": cases}


def check(report: dict) -> None:
    failures = []
    for case in report["cases"]:
        current = case["systems"]["current"]
        if not current.get("hit_at_5", True) or current["pairs_passed"] != current["pairs_total"]:
            failures.append(case["id"])
        for gate in ("empty_query_passed", "forbidden_results_absent", "no_strong_passed"):
            if not current.get(gate, True):
                failures.append(f"{case['id']}:{gate}")
    if failures:
        raise SystemExit("Matching quality checks failed: " + ", ".join(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if labelled targets or rejection cases regress")
    parser.add_argument("--output", type=Path, help="Write a complete reproducible JSON report")
    args = parser.parse_args()
    report = evaluate()
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    if args.check:
        check(report)
