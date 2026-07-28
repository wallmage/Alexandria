import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_ledger.py"
ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("validate_ledger", MODULE_PATH)
validate_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_ledger)


def valid_quality_ledger():
    return {
        "schema_version": 3,
        "report_date": "2026-07-28",
        "coverage": [
            {
                "area": "decision",
                "priority": "high",
                "status": "supported",
                "claim_ids": ["C1"],
                "gap_impact": None,
            }
        ],
        "sources": [
            {
                "source_id": "S1",
                "url": "https://records.example.org/result",
                "source_family": "official-record",
                "provenance": "primary_interested",
                "published": "2026-07-20",
                "accessed": "2026-07-28",
            },
            {
                "source_id": "S2",
                "url": "https://tests.example.net/result",
                "source_family": "independent-test",
                "provenance": "primary_independent",
                "published": "2026-07-21",
                "accessed": "2026-07-28",
            },
        ],
        "claims": [
            {
                "claim_id": "C1",
                "kind": "analysis",
                "importance": "key",
                "source_ids": ["S1", "S2"],
                "supports": [],
                "contradicts": [],
                "confidence": "high",
                "status": "supported",
                "include_in_report": True,
                "reasoning": "The independent test corroborates the accountable record.",
                "decision_relevance": "This determines the recommended option.",
                "what_would_change": "A repeatable test showing the opposite result.",
                "triangulation": {
                    "status": "met",
                    "rationale": "Two independent source families converge.",
                },
                "resolution": None,
                "limitations": None,
            }
        ],
        "synthesis": {
            "central_judgment_claim_ids": ["C1"],
            "counterevidence_claim_ids": [],
            "adversarial_tests": [
                {
                    "hypothesis": "The apparent result is only a fixture artifact.",
                    "test": "Compare the result against an independent implementation.",
                    "claim_ids": ["C1"],
                    "outcome": "rejected",
                    "result": "The independent implementation produced the same result.",
                    "effect_on_conclusion": "The central judgment remains unchanged.",
                }
            ],
            "implications": [
                {
                    "statement": "Use the result as a decision gate.",
                    "claim_ids": ["C1"],
                }
            ],
            "decisions_or_takeaways": [
                {
                    "statement": "Run the option under the stated boundary.",
                    "rationale_claim_ids": ["C1"],
                    "tradeoff": "The test takes time.",
                    "success_signal": "The result repeats.",
                    "failure_signal": "The result cannot be reproduced.",
                }
            ],
            "scenarios": [],
            "limitations": [],
            "research_stop_reason": "Priority questions reached their completion criteria.",
        },
    }


class LedgerReferenceTests(unittest.TestCase):
    def test_v3_ledger_requires_an_independent_source_portfolio(self):
        data = valid_quality_ledger()
        data["sources"][1]["provenance"] = "primary_interested"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("portfolio has no independent source" in error.lower() for error in errors),
            errors,
        )

    def test_supported_coverage_cannot_rely_only_on_interested_sources(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_ids"] = ["S1"]
        data["claims"][0]["triangulation"] = {
            "status": "limited",
            "rationale": "Only the subject's record was available.",
        }
        data["claims"][0]["confidence"] = "medium"
        data["claims"][0]["limitations"] = "No independent corroboration was found."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("supported coverage decision relies only on interested sources" in error.lower() for error in errors),
            errors,
        )

    def test_high_confidence_inference_requires_independent_foundation(self):
        data = valid_quality_ledger()
        data["claims"][0]["status"] = "inference"
        data["claims"][0]["source_ids"] = ["S1"]
        data["claims"][0]["triangulation"] = {
            "status": "limited",
            "rationale": "Only the subject's record was available.",
        }
        data["claims"][0]["limitations"] = "No independent corroboration was found."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("high-confidence inference" in error.lower() for error in errors),
            errors,
        )

    def test_schema_requires_the_research_brief_and_synthesis_contract(self):
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        incomplete = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        incomplete.pop("schema_version")
        incomplete.pop("brief")
        incomplete.pop("synthesis")
        errors = validate_ledger.validate_schema(incomplete, schema)
        joined = " ".join(errors)
        self.assertIn("schema_version", joined)
        self.assertIn("brief", joined)
        self.assertIn("synthesis", joined)

    def test_accepts_known_source_and_claim_references(self):
        data = {
            "sources": [{"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "source_ids": ["S1"],
                    "supports": [],
                    "contradicts": [],
                }
            ],
        }
        self.assertEqual([], validate_ledger.validate_references(data))

    def test_rejects_duplicate_and_dangling_ids(self):
        data = {
            "sources": [{"source_id": "S1"}, {"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "source_ids": ["S2"],
                    "supports": ["C9"],
                    "contradicts": [],
                },
                {
                    "claim_id": "C1",
                    "source_ids": [],
                    "supports": [],
                    "contradicts": [],
                },
            ],
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("Duplicate source ID" in error for error in errors))
        self.assertTrue(any("Duplicate claim ID" in error for error in errors))
        self.assertTrue(any("unknown source S2" in error for error in errors))
        self.assertTrue(any("unknown claim C9" in error for error in errors))

        data["coverage"] = [{"area": "current", "claim_ids": ["C8"]}]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "Coverage current references unknown claim C8" in error
                for error in errors
            )
        )

    def test_cross_reference_check_tolerates_schema_invalid_shapes(self):
        self.assertEqual([], validate_ledger.validate_references([]))
        self.assertEqual(
            [],
            validate_ledger.validate_references(
                {"sources": ["bad"], "claims": [42, None]}
            ),
        )

    def test_rejects_circular_analysis_without_sourced_foundation(self):
        data = {
            "sources": [{"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "kind": "analysis",
                    "source_ids": [],
                    "supports": ["C2"],
                    "contradicts": [],
                    "include_in_report": True,
                },
                {
                    "claim_id": "C2",
                    "kind": "analysis",
                    "source_ids": [],
                    "supports": ["C1"],
                    "contradicts": [],
                    "include_in_report": True,
                },
            ],
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("circular support" in error for error in errors))
        self.assertTrue(any("no sourced foundation" in error for error in errors))

    def test_high_priority_coverage_must_finish_or_state_the_gap_impact(self):
        data = valid_quality_ledger()
        data["coverage"][0]["status"] = "in_progress"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("High-priority coverage decision is unresolved" in error for error in errors),
            errors,
        )

        data["coverage"][0]["status"] = "gap"
        data["coverage"][0]["claim_ids"] = []
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("Coverage decision is a gap but has no gap impact" in error for error in errors),
            errors,
        )

    def test_key_analysis_must_have_honest_source_family_triangulation(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_ids"] = ["S1"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("declares triangulation met but has 1 normalized source family" in error for error in errors),
            errors,
        )

        data["claims"][0]["triangulation"] = {
            "status": "limited",
            "rationale": "Only the vendor record was available.",
        }
        data["claims"][0]["limitations"] = "No independent test was available."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("high-confidence key judgment cannot use limited triangulation" in error for error in errors),
            errors,
        )

    def test_triangulation_normalizes_families_and_requires_independent_evidence(self):
        data = valid_quality_ledger()
        data["sources"][0]["source_family"] = " Same-Family "
        data["sources"][1]["source_family"] = "same family"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("1 normalized source family" in error for error in errors),
            errors,
        )

        data = valid_quality_ledger()
        data["sources"][1]["provenance"] = "secondary_dependent"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("no independent source" in error for error in errors),
            errors,
        )

    def test_duplicate_source_urls_are_rejected_after_normalization(self):
        data = valid_quality_ledger()
        data["sources"][1]["url"] = "HTTPS://records.example.org/result/"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("Duplicate source URL" in error for error in errors), errors)

    def test_disputed_claims_need_reciprocal_contradictions_and_resolution(self):
        data = valid_quality_ledger()
        data["claims"].append(
            {
                "claim_id": "C2",
                "kind": "fact",
                "importance": "supporting",
                "source_ids": ["S2"],
                "supports": [],
                "contradicts": [],
                "confidence": "medium",
                "status": "supported",
                "include_in_report": False,
            }
        )
        data["claims"][0]["status"] = "disputed"
        data["claims"][0]["contradicts"] = ["C2"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("C1 is disputed but has no resolution" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("C1 contradicts C2, but the relationship is not reciprocal" in error for error in errors),
            errors,
        )

    def test_synthesis_must_use_included_key_claims_and_known_foundations(self):
        data = valid_quality_ledger()
        data["synthesis"]["central_judgment_claim_ids"] = ["C9"]
        data["synthesis"]["counterevidence_claim_ids"] = ["C6"]
        data["synthesis"]["implications"][0]["claim_ids"] = ["C8"]
        data["synthesis"]["decisions_or_takeaways"][0]["rationale_claim_ids"] = ["C7"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("unknown central judgment C9" in error for error in errors), errors)
        self.assertTrue(any("unknown counterevidence C6" in error for error in errors), errors)
        self.assertTrue(any("unknown implication claim C8" in error for error in errors), errors)
        self.assertTrue(any("unknown takeaway rationale C7" in error for error in errors), errors)

        data = valid_quality_ledger()
        data["synthesis"]["central_judgment_claim_ids"] = []
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("Key report claim C1 is missing from the central synthesis" in error for error in errors),
            errors,
        )

    def test_source_dates_cannot_postdate_the_report_or_access(self):
        data = valid_quality_ledger()
        data["sources"][0]["published"] = "2026-07-29"
        data["sources"][1]["accessed"] = "2026-07-20"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("S1 is published after the report date" in error for error in errors), errors)
        self.assertTrue(any("S2 is published after it was accessed" in error for error in errors), errors)

        data = valid_quality_ledger()
        data["sources"][0]["accessed"] = "2026-07-29"
        data["claims"][0]["as_of"] = "2026-07-30"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("S1 is accessed after the report date" in error for error in errors), errors)
        self.assertTrue(any("C1 is dated after the report date" in error for error in errors), errors)

    def test_gap_coverage_cannot_hide_claims(self):
        data = valid_quality_ledger()
        data["coverage"][0]["status"] = "gap"
        data["coverage"][0]["gap_impact"] = "The decision remains uncertain."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("gap but still references claims" in error for error in errors), errors)

    def test_coverage_status_must_match_the_referenced_claims(self):
        data = valid_quality_ledger()
        data["coverage"][0]["status"] = "supported"
        data["claims"][0]["status"] = "disputed"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("supported but references no supported claim" in error for error in errors),
            errors,
        )

    def test_implications_and_takeaways_must_connect_to_the_central_judgment(self):
        data = valid_quality_ledger()
        data["claims"].append(
            {
                "claim_id": "C2",
                "kind": "fact",
                "importance": "supporting",
                "source_ids": ["S2"],
                "supports": [],
                "contradicts": [],
                "confidence": "medium",
                "status": "supported",
                "include_in_report": False,
            }
        )
        data["synthesis"]["implications"][0]["claim_ids"] = ["C2"]
        data["synthesis"]["decisions_or_takeaways"][0]["rationale_claim_ids"] = ["C2"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("Implication is not linked" in error for error in errors), errors)
        self.assertTrue(any("Takeaway is not linked" in error for error in errors), errors)

    def test_adversarial_tests_are_required_and_reference_known_claims(self):
        data = valid_quality_ledger()
        data["synthesis"]["adversarial_tests"] = []
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(validate_ledger.validate_schema(data, schema))

        data = valid_quality_ledger()
        data["synthesis"]["adversarial_tests"][0]["claim_ids"] = ["C9"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("unknown adversarial-test claim C9" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
