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
        "schema_version": 4,
        "people": [],
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
                "publisher": "Example Registry",
                "source_family": "example.org",
                "provenance": "primary_interested",
                "roles": ["subject_official"],
                "accountability_basis": "none",
                "published": "2026-07-20",
                "accessed": "2026-07-28",
            },
            {
                "source_id": "S2",
                "url": "https://tests.example.net/result",
                "publisher": "Example Test Lab",
                "source_family": "example.net",
                "provenance": "primary_independent",
                "roles": ["independent_analysis"],
                "accountability_basis": "none",
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
                "source_evidence": [
                    {
                        "source_id": "S1",
                        "extract_or_location": (
                            "The registry records the accountable result."
                        ),
                    },
                    {
                        "source_id": "S2",
                        "extract_or_location": (
                            "The independent test reproduces the result."
                        ),
                    },
                ],
                "supports": [],
                "contradicts": [],
                "person_ids": [],
                "human_harm_review": None,
                "verified_at": "2026-07-28",
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


def fact_claim(**overrides):
    claim = {
        "claim_id": "C2",
        "claim": "The vendor recorded a 12.5% failure rate in 2026-07.",
        "kind": "fact",
        "importance": "supporting",
        "source_ids": ["S2"],
        "extract_or_location": 'Status page: "12.5% of runs failed in July 2026".',
        "source_evidence": [
            {
                "source_id": "S2",
                "extract_or_location": (
                    'Status page: "12.5% of runs failed in July 2026".'
                ),
            }
        ],
        "as_of": "2026-07-28",
        "supports": [],
        "contradicts": [],
        "person_ids": [],
        "human_harm_review": None,
        "confidence": "medium",
        "status": "supported",
        "include_in_report": False,
    }
    claim.update(overrides)
    return claim


def ledger_with_fact(**overrides):
    data = valid_quality_ledger()
    data["claims"].append(fact_claim(**overrides))
    return data


def living_harm_ledger():
    data = valid_quality_ledger()
    data["people"] = [
        {
            "person_id": "P1",
            "name": "Alex Doe",
            "aliases": ["Doe"],
            "living_status": "living",
            "public_role": "public",
            "relationship": "primary_subject",
        }
    ]
    data["sources"][0]["accountability_basis"] = "court_or_regulator_record"
    data["sources"][0]["accountability_note"] = (
        "The regulator published the signed enforcement record in its docket."
    )
    data["sources"][1]["accountability_basis"] = "none"
    data["claims"].append(
        {
            "claim_id": "C2",
            "claim": (
                "The regulator alleged that Alex Doe committed procurement "
                "fraud; no public response was found after the documented search."
            ),
            "kind": "reported_claim",
            "importance": "supporting",
            "source_ids": ["S1", "S2"],
            "source_evidence": [
                {
                    "source_id": "S1",
                    "extract_or_location": (
                        "The regulator alleged procurement fraud by Alex Doe."
                    ),
                },
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "The independent report describes the regulator's allegation."
                    ),
                },
            ],
            "extract_or_location": (
                "The regulator alleged procurement fraud and an independent "
                "report described the same allegation."
            ),
            "as_of": "2026-07-28",
            "verified_at": "2026-07-28",
            "supports": [],
            "contradicts": [],
            "confidence": "low",
            "status": "supported",
            "include_in_report": False,
            "person_ids": ["P1"],
            "person_claim_role": "harmful",
            "person_claim_assessment": {
                "classification": "harmful",
                "rationale": (
                    "This claim alleges criminal misconduct by a living "
                    "primary subject and therefore requires full review."
                ),
            },
            "human_harm_review": {
                "category": "wrongdoing",
                "legal_stage": "alleged",
                "source_floor": "met",
                "accountable_source_ids": ["S1"],
                "attributed_to": "The regulator",
                "sourcing_limitation_excerpt": None,
                "event_period": "2026",
                "resolution_status": "unresolved",
                "resolution_claim_ids": [],
                "resolution_search": {
                    "queries": ["Alex Doe procurement fraud resolution"],
                    "expected_locations": ["regulator docket and court index"],
                    "searched_at": "2026-07-28",
                },
                "right_of_reply": {
                    "status": "no_public_response",
                    "response_claim_ids": [],
                    "search_record": {
                        "queries": ["Alex Doe response procurement fraud"],
                        "expected_locations": [
                            "subject website and regulator docket"
                        ],
                        "searched_at": "2026-07-28",
                    },
                },
                "privacy_basis": "not_sensitive",
                "privacy_basis_source_ids": [],
                "governing_question_relevance": (
                    "The allegation directly affects the report's assessment "
                    "of public procurement responsibility."
                ),
            },
            "evidence_of_absence": {
                "queries": ["Alex Doe response procurement fraud"],
                "expected_locations": ["subject website and regulator docket"],
                "searched_at": "2026-07-28",
            },
            "reasoning": None,
            "decision_relevance": "It affects the assessment of public conduct.",
            "what_would_change": "A final adjudication or retraction.",
            "triangulation": {
                "status": "met",
                "rationale": "Two source families report the allegation.",
            },
            "resolution": None,
            "limitations": "The allegation remains unresolved.",
            "report_excerpts": [],
        }
    )
    return data


class EvidenceCoverageTests(unittest.TestCase):
    def test_date_components_do_not_support_an_unrelated_count(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "The vendor recorded 28 incidents.",
                "extract_or_location": "Report dated 2026-07-28.",
            }
        )
        self.assertTrue(any("quantity '28'" in error for error in errors), errors)

    def test_spelled_count_is_an_evidence_obligation(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "Researchers disclosed three CVEs.",
                "extract_or_location": "The page describes the product.",
            }
        )
        self.assertTrue(any("three" in error for error in errors), errors)

    def test_negated_status_and_direction_do_not_support_affirmative_claims(self):
        patched = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "The defect was patched.",
                "extract_or_location": "The defect was not patched.",
            }
        )
        increased = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C901",
                "kind": "fact",
                "claim": "Revenue increased by 12%.",
                "extract_or_location": "Revenue did not increase by 12%.",
            }
        )
        self.assertTrue(patched, patched)
        self.assertTrue(increased, increased)

    def test_status_evidence_must_match_subject_and_polarity(self):
        extracts = (
            "The advisory rejects the claim that the defect was patched.",
            "It is false that the defect was patched.",
            "The patch proposal was rejected.",
            "The vendor disputed reports that the defect was patched.",
            "Claims that the defect was patched are incorrect.",
        )
        for extract in extracts:
            with self.subTest(extract=extract):
                errors = validate_ledger.evidence_coverage_errors(
                    {
                        "claim_id": "C900",
                        "kind": "fact",
                        "claim": "The defect was patched.",
                        "extract_or_location": extract,
                    }
                )
                self.assertTrue(
                    any("patched" in error for error in errors), errors
                )

    def test_status_evidence_rejects_a_different_named_carrier(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "The alpha defect was patched.",
                "extract_or_location": "The beta defect was patched.",
            }
        )
        self.assertTrue(
            any("patched" in error for error in errors),
            errors,
        )

    def test_direction_evidence_must_match_the_same_subject(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "Revenue increased.",
                "extract_or_location": "Costs increased.",
            }
        )
        self.assertTrue(
            any("direction" in error.lower() for error in errors),
            errors,
        )

    def test_partial_word_cannot_be_a_derived_status_expression(self):
        claim = {
            "claim_id": "C900",
            "kind": "fact",
            "claim": "The defect was patched.",
            "extract_or_location": "The advisory describes the defect.",
            "derived_assertions": [
                {
                    "expression": "patch",
                    "derivation": "A sufficiently long but invalid derivation." * 2,
                }
            ],
        }
        self.assertTrue(validate_ledger.derived_assertion_errors(claim))
        self.assertTrue(validate_ledger.evidence_coverage_errors(claim))

    def test_claim_summary_cannot_replace_per_source_evidence(self):
        data = ledger_with_fact(
            claim="The vendor recorded a 47% failure rate.",
            extract_or_location="The vendor recorded a 47% failure rate.",
            source_evidence=[
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "The source records a 12.5% failure rate."
                    ),
                }
            ],
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("quantity '47'" in error for error in errors),
            errors,
        )

    def test_source_records_cannot_pool_a_carrier_and_value(self):
        data = ledger_with_fact(
            claim="Latency was 20 ms.",
            extract_or_location="Latency was 20 ms.",
            source_ids=["S1", "S2"],
            source_evidence=[
                {
                    "source_id": "S1",
                    "extract_or_location": "Latency",
                },
                {
                    "source_id": "S2",
                    "extract_or_location": "20 ms.",
                },
            ],
        )
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("source_evidence[S1]", joined)
        self.assertIn("source_evidence[S2]", joined)

    def test_same_number_with_a_different_unit_is_not_evidence(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "The service reached 4 million users.",
                "extract_or_location": "The service recorded $4 million in revenue.",
            }
        )
        self.assertTrue(any("unit" in error.lower() for error in errors), errors)

    def test_quantities_preserve_sign_unit_magnitude_and_currency(self):
        cases = (
            ("The margin changed by -5%.", "The margin changed by +5%."),
            ("Latency was 20 milliseconds.", "Latency was 20 seconds."),
            ("Revenue was $4 million.", "Revenue was $4."),
            ("The archive is 2 GB.", "The archive is 2 MB."),
            ("The project ran for 1 month.", "The project ran for 2,629,800 seconds."),
            ("The service has 20 users.", "The service ran for 20 seconds."),
            ("Revenue was €5 million.", "Revenue was $5 million."),
            (
                "The archive holds 2 billion bytes.",
                "The archive holds 2 million bytes.",
            ),
            ("合約金額為九百萬元。", "合約金額為一萬元。"),
            ("估值為九億元。", "估值為一億元。"),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                errors = validate_ledger.evidence_coverage_errors(
                    {
                        "claim_id": "C900",
                        "kind": "fact",
                        "claim": claim,
                        "extract_or_location": extract,
                    }
                )
                self.assertTrue(errors, (claim, extract))

    def test_equivalent_quantities_match_across_notation_and_units(self):
        cases = (
            ("The margin changed by -5%.", "The margin changed by -5 percent."),
            ("Latency was 20 milliseconds.", "Latency was 0.02 seconds."),
            (
                "The service processed 3 thousand records.",
                "The service processed 3,000 records.",
            ),
            ("合約金額為九百萬元。", "合約金額為9,000,000元。"),
            ("估值為二億三千萬元。", "估值為230,000,000元。"),
            ("估值為一萬億元。", "估值為1,000,000,000,000元。"),
            ("估值為一兆二億元。", "估值為1,000,200,000,000元。"),
            ("利潤率變動負五%。", "利潤率變動-5%。"),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C900",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_quantities_are_bound_to_their_metric_carrier(self):
        cases = (
            (
                "Latency was 20 ms; timeout was 30 s.",
                "Latency was 30 s; timeout was 20 ms.",
            ),
            (
                "Revenue was US$20 million; profit was US$5 million.",
                "Revenue was US$5 million; profit was US$20 million.",
            ),
            (
                "Revenue was US$20 million.",
                "Profit was US$20 million.",
            ),
            (
                "Revenue was 20; profit was 5.",
                "Revenue was 5; profit was 20.",
            ),
            (
                "Net revenue was 20 / net profit was 5.",
                "Net revenue was 5 / net profit was 20.",
            ),
            (
                "Net revenue was 20 | net profit was 5.",
                "Net revenue was 5 | net profit was 20.",
            ),
            (
                "Net revenue was 20\nNet profit was 5.",
                "Net revenue was 5\nNet profit was 20.",
            ),
            (
                "Failure rate was 20%.",
                "Success rate was 20%.",
            ),
            (
                "Gross profit margin was 20%.",
                "Operating profit margin was 20%.",
            ),
            (
                "營業收入為20萬元。",
                "營業利潤為20萬元。",
            ),
            (
                "Latency was 20 ms.",
                "20 ms.",
            ),
            (
                "Latency was 20 ms.",
                "It was 20 ms.",
            ),
            (
                "North America operating profit margin was 20%.",
                "Europe operating profit margin was 20%.",
            ),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C910",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_quantity_comparators_are_not_interchangeable(self):
        cases = (
            ("Latency was >20 ms.", "Latency was <20 ms."),
            ("Latency was at least 20 ms.", "Latency was more than 20 ms."),
            ("Latency was at most 20 ms.", "Latency was less than 20 ms."),
            ("Latency was approximately 20 ms.", "Latency was exactly 20 ms."),
            ("Latency was no more than 20 ms.", "Latency was no fewer than 20 ms."),
            ("Latency was 20 ms or more.", "Latency was exactly 20 ms."),
            ("Latency was 20 ms or less.", "Latency was exactly 20 ms."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C911",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_equivalent_quantity_comparator_phrases_match(self):
        cases = (
            ("Latency was >=20 ms.", "Latency was at least 20 milliseconds."),
            ("Latency was <=20 ms.", "Latency was no more than 20 milliseconds."),
            ("Latency was >20 ms.", "Latency was more than 20 milliseconds."),
            ("Latency was <20 ms.", "Latency was less than 20 milliseconds."),
            ("Latency was ~20 ms.", "Latency was approximately 20 milliseconds."),
            ("Latency was >=20 ms.", "Latency was no less than 20 milliseconds."),
            (
                "Latency was >=20 ms.",
                "Latency was greater than or equal to 20 milliseconds.",
            ),
            (
                "Latency was <=20 ms.",
                "Latency was less than or equal to 20 milliseconds.",
            ),
            ("Latency was 20 ms or more.", "Latency was at least 20 ms."),
            ("Latency was 20 ms or less.", "Latency was at most 20 ms."),
            ("延遲不低於20毫秒。", "延遲至少20毫秒。"),
            ("延遲不高於20毫秒。", "延遲至多20毫秒。"),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C912",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_unresolved_comparator_like_text_fails_closed(self):
        for claim in (
            "Latency was somewhere above-ish 20 ms.",
            "Latency was 20 ms or thereabouts.",
            "Latency was 20 ms or more-ish.",
        ):
            with self.subTest(claim=claim):
                errors = validate_ledger.evidence_coverage_errors(
                    {
                        "claim_id": "C912",
                        "kind": "fact",
                        "claim": claim,
                        "extract_or_location": "Latency was 20 ms.",
                    }
                )
                self.assertTrue(errors, errors)

    def test_currency_and_unknown_units_fail_closed(self):
        cases = (
            ("Latency was 20 ms.", "Latency was 20 s."),
            ("Revenue was NT$20 million.", "Revenue was US$20 million."),
            ("收入為新台幣二千萬元。", "收入為人民幣二千萬元。"),
            ("The reading was 20 quarks.", "The reading was 20 widgets."),
            ("讀數為20弗隆。", "讀數為20秒。"),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C913",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_compound_units_and_accounting_sign_are_preserved(self):
        cases = (
            ("Speed was 20 km/h.", "Speed was 20 km."),
            ("Speed was 20 km per hour.", "Speed was 20 km."),
            ("Speed was 20 miles per hour.", "Speed was 20 miles."),
            ("Throughput was 20 MB/s.", "Throughput was 20 MB."),
            ("The loss was (US$20m).", "The loss was US$20m."),
            ("虧損為（新台幣二千萬元）。", "虧損為新台幣二千萬元。"),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C917",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_equivalent_worded_and_symbolic_compound_units_match(self):
        cases = (
            ("Speed was 20 km per hour.", "Speed was 20 km per hour."),
            (
                "Speed was 20 miles per hour.",
                "Speed was 20 miles per hour.",
            ),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C917",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_equivalent_currency_names_match(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C914",
                    "kind": "fact",
                    "claim": "Revenue was NT$20 million.",
                    "extract_or_location": "Revenue was 新台幣20,000,000元.",
                }
            ),
        )

    def test_iso_currency_and_unicode_time_units_are_typed(self):
        cases = (
            ("Revenue was CNY 20 million.", "Revenue was 20 million."),
            ("Revenue was cny 20 million.", "Revenue was usd 20 million."),
            ("Revenue was nt$20 million.", "Revenue was us$20 million."),
            ("Latency was 20 µs.", "Latency was 20."),
            ("Latency was 20 μs.", "Latency was 20 ms."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C915",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_temperature_and_unicode_compound_units_are_not_bare_scalars(self):
        cases = (
            ("Temperature was 20 °C.", "Temperature was 20."),
            ("Temperature was 20 ℃.", "Temperature was 20 °F."),
            ("Temperature was 20 K.", "Temperature was 20 °C."),
            ("Area was 20 m².", "Area was 20 m."),
            ("Acceleration was 20 m/s².", "Acceleration was 20 m/s."),
            ("Energy was 20 kg·m²/s².", "Energy was 20 kg."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim, extract=extract):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C915",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_equivalent_temperature_notation_matches(self):
        cases = (
            ("Temperature was 20 °C.", "Temperature was 20 ℃."),
            ("Temperature was 68 °F.", "Temperature was 68 degrees Fahrenheit."),
            ("Temperature was 20 K.", "Temperature was 20 kelvin."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C915",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_chinese_percentage_forms_have_numeric_meaning(self):
        cases = (
            ("完成率為五成。", "完成率為50%。"),
            ("完成率為百分之五。", "完成率為5%。"),
            ("增幅為五個百分點。", "增幅為5 percentage points."),
            ("增幅為五个百分点。", "增幅為5 percentage points."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C916",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_chinese_tenths_with_remainder_is_one_percentage(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C918",
                    "kind": "fact",
                    "claim": "完成率為五成二。",
                    "extract_or_location": "完成率為52%。",
                }
            ),
        )

    def test_chinese_idioms_do_not_create_quantities(self):
        for text in (
            "十分重要",
            "萬一發生",
            "万一发生",
            "千萬不要",
            "千万不要",
            "千萬別這樣做",
            "千万别这样做",
            "百事可樂",
            "百事可乐",
            "千方百計",
            "千方百计",
        ):
            with self.subTest(text=text):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(text))

    def test_comparator_detection_uses_token_boundaries(self):
        for text in (
            "Throughput was 20 MB.",
            "Roughness score was 20.",
            "The foremost score was 20.",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C919",
                            "kind": "fact",
                            "claim": text,
                            "extract_or_location": text,
                        }
                    ),
                )

    def test_cjk_words_containing_numeral_characters_are_not_quantities(self):
        for text in ("統一企業", "三一重工", "一方面", "唯一"):
            with self.subTest(text=text):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(text))

    def test_opposite_direction_is_not_evidence(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "Revenue increased by 12%.",
                "extract_or_location": "Revenue decreased by 12%.",
            }
        )
        self.assertTrue(
            any("direction" in error.lower() for error in errors),
            errors,
        )

    def test_analysis_cannot_launder_an_unsupported_assertion(self):
        # Relabelling a claim 'analysis' used to skip evidence coverage
        # entirely, so the same sentence passed as analysis and failed as fact.
        claim = "The vendor raised prices by 47% and the flaw is now patched."
        as_fact = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": claim,
                "extract_or_location": "The page describes the product broadly.",
            }
        )
        as_analysis = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "analysis",
                "claim": claim,
                "extract_or_location": "The page describes the product broadly.",
            }
        )
        self.assertTrue(as_fact)
        self.assertEqual(len(as_fact), len(as_analysis), as_analysis)

    def test_analysis_may_rest_on_inherited_evidence(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C901",
                "kind": "analysis",
                "claim": "A 47% list-price rise leaves the vendor exposed.",
                "extract_or_location": "",
            },
            (),
            "list price rose 47% between the two published tables",
        )
        self.assertEqual([], errors)

    def test_empty_extract_is_an_error_not_an_exemption(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C902",
                "kind": "fact",
                "claim": "Revenue reached $9.4B and the product was discontinued.",
                "extract_or_location": "   ",
            }
        )
        self.assertTrue(
            any("extract_or_location is empty" in error for error in errors),
            errors,
        )

    def test_spelled_out_magnitude_is_covered_by_digits_in_the_extract(self):
        # The word form and the digit form are the same figure.
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C905",
                    "kind": "fact",
                    "claim": "Prices rose fifty percent to four billion dollars.",
                    "extract_or_location": "list price rose 50% to $4bn",
                }
            ),
        )

    def test_spelled_out_phrase_resolves_to_one_complete_value(self):
        # Scanning word by word yielded {20, 5} for "twenty-five", which is
        # neither the asserted figure nor comparable to a digit form.
        for phrase, expected in (
            ("twenty-five percent", 25),
            ("thirty-seven percent", 37),
            ("one hundred percent", 100),
            ("one hundred and fifty percent", 150),
            ("four hundred million dollars", 400_000_000),
            ("four billion dollars", 4_000_000_000),
            # "dozen" multiplies the pending group; it used to add, so this
            # resolved to 14 and matched the wrong figure in an extract.
            ("two dozen units", 24),
            ("a dozen units", 12),
            # "half" was briefly dropped from the table, which silently exempted
            # every fractional magnitude from evidence coverage.
            ("half a percent", 0.5),
            ("half a second", 0.5),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence(phrase),
                )

    def test_compound_word_number_matches_its_digit_form(self):
        pairs = (
            ("Prices rose by twenty-five percent.", "prices increased by 25%"),
            ("Revenue rose thirty-seven percent.", "revenue rose by 37%"),
            (
                "Revenue hit four hundred million dollars.",
                "revenue was $400,000,000",
            ),
        )
        for claim, extract in pairs:
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C906",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_fractions_assert_no_figure(self):
        # "two-thirds" denotes 2/3. Emitting the numerator asserted 2, which
        # matched the wrong value in an extract and errored against the right
        # one. A vague proportion is the content review's job, not this gate's.
        for phrase in (
            "two-thirds of the market",
            "three quarters of users",
            "a third of revenue",
            "a quarter of the fleet",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    set(), validate_ledger.quantitative_evidence(phrase)
                )

    def test_ordinal_after_an_article_is_a_unit_not_a_number(self):
        # "half a second" is a duration. Reading `second` as the ordinal two
        # asserted a figure the sentence never made.
        self.assertEqual(
            {"n:0.5"}, validate_ledger.quantitative_evidence("half a second")
        )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C908",
                    "kind": "fact",
                    "claim": "Latency was half a second.",
                    "extract_or_location": "latency measured 0.5 seconds",
                }
            ),
        )

    def test_compound_word_number_does_not_match_a_different_value(self):
        # The old per-word scan let "twenty-five percent" pass against "5%".
        pairs = (
            ("Prices rose by twenty-five percent.", "the increase was 5%"),
            ("It rose thirty-seven percent.", "a 30% rise"),
            ("Revenue hit four hundred million dollars.", "revenue was $400"),
        )
        for claim, extract in pairs:
            with self.subTest(claim=claim):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C907",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_spelled_out_magnitudes_still_need_evidence(self):
        # Writing the figure as a word was a clean way past the digit scan.
        # Every separator and unit family below was a live bypass.
        extract = "The page describes the product broadly."
        for claim in (
            "The vendor raised prices by fifty percent.",
            "The vendor raised prices by fifty-percent.",
            "The vendor raised prices by twenty-five percent.",
            "The vendor raised prices by twenty five percent.",
            "Utilisation hit one hundred percent.",
            "Revenue reached four billion dollars.",
            "Revenue reached four hundred million dollars.",
            "Costs were three times higher.",
            "Costs were threefold higher.",
            "Throughput improved tenfold.",
            "It rose fifty per cent.",
            "Margin fell forty basis points.",
            "Latency was fifty milliseconds.",
            "Capacity is three gigawatts.",
            "The trial ran twelve weeks.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C903",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )

    def test_spelled_out_counts_are_obligations_but_numberlike_words_are_not(self):
        extract = "The page describes the product broadly."
        for claim in (
            "Researchers disclosed three CVEs in the client.",
            "It is one of two supported products.",
            "The agent runs on five surfaces.",
            "There are three vendors in scope.",
            "Ten engineers joined the team.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C904",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    )
                )
        for claim in (
            "The tender was reissued.",
            "A secondary market exists.",
        ):
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C904",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_number_in_claim_must_appear_in_the_extract(self):
        data = ledger_with_fact(
            claim="The vendor recorded a 12.5% failure rate and 400 incidents.",
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "quantity '400' appears in claim but not in "
                "source_evidence[S2]" in error
                for error in errors
            ),
            errors,
        )

    def test_appended_status_assertion_without_evidence_is_rejected(self):
        data = ledger_with_fact(
            claim=(
                "Researchers disclosed three chained CVEs (CVSS 7.8 to 9.9), "
                "all since patched."
            ),
            extract_or_location=(
                "Advisory: CVE-2026-35020 (CVSS 7.8), CVE-2026-35022 "
                "(up to 9.9 in non-interactive mode)."
            ),
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "C2: claim asserts 'patched'" in error
                and "records no evidence of it" in error
                for error in errors
            ),
            errors,
        )

    def test_status_evidence_requires_a_complete_token_with_matching_polarity(self):
        cases = (
            ("The defect was patched.", "The dispatch occurred on Tuesday."),
            ("The product was approved.", "The proposal was disapproved."),
        )
        for claim, extract in cases:
            with self.subTest(claim=claim):
                errors = validate_ledger.evidence_coverage_errors(
                    {
                        "claim_id": "C909",
                        "kind": "fact",
                        "claim": claim,
                        "extract_or_location": extract,
                    }
                )
                self.assertTrue(errors, (claim, extract))

    def test_equivalent_number_forms_do_not_raise_false_positives(self):
        data = ledger_with_fact(
            claim=(
                "In July 2026, the package total is 1,200 packages at v2.10.3, "
                "three of them deprecated, 8.4 on the severity scale, and "
                "the download total is 1.5 million downloads. See "
                "https://example.net/2099/44 and "
                "claim C1 for context."
            ),
            extract_or_location=(
                "Index page: package total is 1200 packages at version 2.10.3; "
                "three entries "
                "are marked deprecated; severity 8.4; the download total is "
                "1500000 downloads; dated 2026-07-14."
            ),
            source_evidence=[
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "Index page: package total is 1200 packages at version "
                        "2.10.3; three entries are marked deprecated; severity "
                        "8.4; the download total is 1500000 downloads; dated "
                        "2026-07-14."
                    ),
                }
            ],
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if error.startswith("C2:")
        ]
        self.assertEqual([], errors)

    def test_denied_status_is_not_treated_as_an_appended_assertion(self):
        data = ledger_with_fact(
            claim="The repository is not open source.",
            extract_or_location=(
                'LICENSE.md verbatim: "All rights reserved. Use is subject '
                'to the Commercial Terms of Service."'
            ),
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if error.startswith("C2:")
        ]
        self.assertEqual([], errors)

    def test_ledger_dates_cover_a_claim_date_the_extract_cannot_carry(self):
        data = ledger_with_fact(
            claim="As of 2026-07-28 the vendor lists a 12.5% failure rate.",
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if "2026-07-28" in error and "quantity" in error
        ]
        self.assertEqual([], errors)


class DerivedAssertionTests(unittest.TestCase):
    def test_derivation_must_match_the_exact_quantity_it_excuses(self):
        data = ledger_with_fact(
            claim=(
                "The unsupported rate was 20 percent while the separately "
                "derived index reached 120 points."
            ),
            extract_or_location="The source describes the index methodology.",
            source_evidence=[
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "The source describes the index methodology."
                    ),
                }
            ],
            derived_assertions=[
                {
                    "expression": "120 points",
                    "derivation": (
                        "The index adds the twelve published ten-point "
                        "components, yielding exactly 120 points."
                    ),
                }
            ],
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "quantity '20' appears in claim but not in "
                "source_evidence[S2]" in error
                for error in errors
            ),
            errors,
        )

    def test_declared_derivation_excuses_an_uncovered_quantity(self):
        data = ledger_with_fact(
            claim="The vendor recorded a 12.5% failure rate over 400 runs.",
            derived_assertions=[
                {
                    "expression": "400",
                    "derivation": (
                        "50 failed runs divided by the 12.5% rate quoted on "
                        "the status page gives the 400-run denominator."
                    ),
                }
            ],
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if error.startswith("C2:")
        ]
        self.assertEqual([], errors)

    def test_escape_hatch_cannot_be_a_rubber_stamp(self):
        data = ledger_with_fact(
            claim="The vendor recorded a 12.5% failure rate over 400 runs.",
            derived_assertions=[
                {"expression": "900", "derivation": "x" * 40},
                {
                    "expression": "12.5%",
                    "derivation": "Quoted straight from the status page text.",
                },
                {"expression": "400", "derivation": "too short"},
            ],
        )
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("does not appear in claim", joined)
        self.assertIn("already appears in extract_or_location", joined)
        self.assertIn("at least 40 characters", joined)
        self.assertIn("derived assertions on a fact claim", joined)


class SupportDirectionTests(unittest.TestCase):
    def test_mutual_supports_pair_is_rejected(self):
        data = valid_quality_ledger()
        data["claims"].append(fact_claim(supports=["C1"]))
        data["claims"][0]["supports"] = ["C2"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("circular support: C1 -> C2 -> C1" in error for error in errors),
            errors,
        )

    def test_longer_support_cycle_is_rejected(self):
        data = valid_quality_ledger()
        data["claims"].append(fact_claim(claim_id="C2", supports=["C3"]))
        data["claims"].append(fact_claim(claim_id="C3", supports=["C1"]))
        data["claims"][0]["supports"] = ["C2"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "circular support: C1 -> C2 -> C3 -> C1" in error
                for error in errors
            ),
            errors,
        )

    def test_triangulation_counts_only_one_declared_support_level(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_ids"] = ["S1"]
        data["claims"][0]["supports"] = ["C2"]
        data["claims"].append(
            fact_claim(claim_id="C2", source_ids=[], supports=["C3"])
        )
        data["claims"].append(fact_claim(claim_id="C3", source_ids=["S2"]))
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("1 normalized source family" in error for error in errors),
            errors,
        )


class SourceFamilyTests(unittest.TestCase):
    def test_descriptive_family_labels_are_allowed(self):
        # 'anthropic-docs' is a better label than 'claude.com'. Independence is
        # counted from the domain, so the label itself is never an error.
        data = valid_quality_ledger()
        data["sources"][1]["source_family"] = "independent-test-lab"
        errors = validate_ledger.validate_references(data)
        self.assertEqual([], errors)

    def test_one_domain_split_across_two_families_is_flagged(self):
        data = valid_quality_ledger()
        data["sources"].append(
            dict(
                data["sources"][0],
                source_id="S3",
                url="https://records.example.org/blog/why-we-win",
                source_family="example-registry-blog",
            )
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("is split across 2 source families" in error for error in errors),
            errors,
        )

    def test_split_labels_on_one_host_stay_a_single_family(self):
        # The exploit: two pages on one host given different family labels to
        # fake triangulation. The domain merge must defeat it.
        data = valid_quality_ledger()
        data["sources"][1]["url"] = "https://records.example.org/blog/why-we-win"
        data["sources"][1]["publisher"] = "Example Registry"
        data["sources"][1]["source_family"] = "example-registry-blog"
        data["sources"][1]["provenance"] = "primary_interested"
        families = validate_ledger._source_family_index(
            {source["source_id"]: source for source in data["sources"]}
        )
        self.assertEqual(
            1,
            len(set(families.values())),
            "pages on one registrable domain must collapse to one family",
        )

    def test_same_host_pages_cannot_split_into_two_independence_classes(self):
        data = valid_quality_ledger()
        data["sources"][0]["url"] = "https://acme.example.com/pricing"
        data["sources"][0]["source_family"] = "example.com"
        data["sources"][1]["url"] = "https://acme.example.com/blog/why-we-win"
        data["sources"][1]["source_family"] = "example.com"
        data["sources"][1]["publisher"] = "Acme"
        data["sources"][0]["publisher"] = "Acme"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "Sources on host acme.example.com declare different "
                "independence classes" in error
                for error in errors
            ),
            errors,
        )

    def test_same_publisher_cannot_be_split_into_two_families(self):
        data = valid_quality_ledger()
        data["sources"][1]["url"] = "https://blog.example.org/why-we-win"
        data["sources"][1]["source_family"] = "example.org"
        data["sources"][1]["publisher"] = "Example Registry"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("1 normalized source family" in error for error in errors),
            errors,
        )


class AbsenceRecordTests(unittest.TestCase):
    def test_negative_existence_claim_needs_a_search_record(self):
        for wording in (
            "No independent benchmark of any kind exists for this product.",
            "No published source measures the per-change cost.",
            "No public equivalent appears to exist for the rival product.",
            "None was located in the regulator's public register.",
            "We found no third-party audit of the pipeline.",
        ):
            with self.subTest(wording=wording):
                data = ledger_with_fact(claim=wording, extract_or_location="Searches")
                errors = validate_ledger.validate_references(data)
                self.assertTrue(
                    any(
                        "records no evidence_of_absence" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_absence_search_must_be_inside_the_freshness_window(self):
        data = ledger_with_fact(
            claim="No independent benchmark exists for this product.",
            extract_or_location="Searches run against the public registers.",
            evidence_of_absence={
                "queries": ["independent benchmark"],
                "expected_locations": ["public register"],
                "searched_at": "2019-01-01",
            },
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("the absence search ran" in error for error in errors),
            errors,
        )

    def test_a_current_absence_search_passes(self):
        data = ledger_with_fact(
            claim="No independent benchmark exists for this product.",
            extract_or_location="Searches run against the public registers.",
            evidence_of_absence={
                "queries": ["independent benchmark"],
                "expected_locations": ["public register"],
                "searched_at": "2026-07-27",
            },
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if "evidence_of_absence" in error or "absence search" in error
        ]
        self.assertEqual([], errors)


class EvidenceFreshnessTests(unittest.TestCase):
    def test_time_sensitive_claim_rejects_stale_access_and_publication(self):
        data = valid_quality_ledger()
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = "2026-07-28"
        data["claims"][0]["verified_at"] = "2026-07-28"
        for source in data["sources"]:
            source["published"] = "2019-04-01"
            source["accessed"] = "2020-05-02"
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("was last accessed", joined)
        self.assertIn("not published inside the freshness window", joined)

    def test_undated_reason_must_name_a_continuously_updated_page(self):
        data = valid_quality_ledger()
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = "2026-07-28"
        data["claims"][0]["verified_at"] = "2026-07-28"
        data["sources"][0]["published"] = None
        data["sources"][0]["undated_reason"] = "no date shown on the page"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "undated_reason does not state that the page is "
                "continuously updated" in error
                for error in errors
            ),
            errors,
        )

        data["sources"][0]["undated_reason"] = (
            "This is a living pricing page that the vendor updates in place."
        )
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("continuously updated" in error for error in errors), errors
        )


class VerificationDateTests(unittest.TestCase):
    def test_time_sensitive_claim_must_record_verified_at(self):
        data = valid_quality_ledger()
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = "2026-07-28"
        data["claims"][0].pop("verified_at")
        data["sources"][0]["undated_reason"] = (
            "Continuously updated official documentation page."
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "a time-sensitive claim needs verified_at" in error
                for error in errors
            ),
            errors,
        )

    def test_verified_at_cannot_outrun_the_report_or_the_source_reading(self):
        data = valid_quality_ledger()
        data["claims"][0]["verified_at"] = "2026-08-30"
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("verified_at is after the report date", joined)
        self.assertIn("later than the most recent source access", joined)


class KeyClaimFoundationTests(unittest.TestCase):
    def test_key_claim_cannot_rest_only_on_interested_sources(self):
        data = valid_quality_ledger()
        data["sources"][1]["provenance"] = "secondary_dependent"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "C1: key claim rests only on interested sources" in error
                for error in errors
            ),
            errors,
        )

    def test_key_claim_without_any_foundation_is_reported(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_ids"] = []
        data["claims"][0]["supports"] = []
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "C1: key claim has no direct source" in error
                for error in errors
            ),
            errors,
        )

    def test_key_claim_needs_a_source_outside_the_subject_role(self):
        data = valid_quality_ledger()
        for source in data["sources"]:
            source["roles"] = ["subject_official"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "every source under this key claim is subject_official"
                in error
                for error in errors
            ),
            errors,
        )


class LivingPersonSafetyTests(unittest.TestCase):
    def test_unregistered_cjk_and_lowercase_names_trigger_harm_review(self):
        cases = (
            ("監管機構指控王小明涉嫌欺詐。", "王小明"),
            ("The filing says alice chen lied to investigators.", "alice chen"),
            (
                "The regulator alleged procurement fraud by alice chen.",
                "alice chen",
            ),
            ("王小明遭監管機構指控欺詐。", "王小明"),
        )
        for claim_text, name in cases:
            with self.subTest(name=name):
                data = ledger_with_fact(
                    claim=claim_text,
                    extract_or_location=claim_text,
                )
                joined = " ".join(validate_ledger.validate_references(data))
                self.assertIn("register the named person", joined)
                self.assertIn(name, joined)
                self.assertIn("human_harm_review", joined)

    def test_united_nations_is_not_classified_as_a_person(self):
        data = ledger_with_fact(
            claim="The United Nations reported alleged procurement fraud.",
            extract_or_location=(
                "The United Nations reported alleged procurement fraud."
            ),
        )
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("register the named person" in error for error in errors),
            errors,
        )

    def test_additional_named_person_harm_grammars_trigger_review(self):
        cases = (
            ("監管機構指控王小明欺詐。", "王小明"),
            ("The filing says alice chen was accused of lying.", "alice chen"),
            ("The filing accuses alice chen of lying.", "alice chen"),
            ("The filing says alice chen is accused of lying.", "alice chen"),
            ("監管機構稱王小明遭指控欺詐。", "王小明"),
            ("監管機構稱歐陽娜娜遭指控欺詐。", "歐陽娜娜"),
        )
        for claim_text, name in cases:
            with self.subTest(name=name):
                data = ledger_with_fact(
                    claim=claim_text,
                    extract_or_location=claim_text,
                )
                joined = " ".join(validate_ledger.validate_references(data))
                self.assertIn("register the named person", joined)
                self.assertIn(name, joined)
                self.assertIn("human_harm_review", joined)

    def test_human_rights_organizations_are_not_classified_as_people(self):
        for organization in (
            "Amnesty International",
            "Human Rights Watch",
            "Doctors Without Borders",
            "Transparency International",
        ):
            with self.subTest(organization=organization):
                text = f"{organization} reported alleged procurement fraud."
                data = ledger_with_fact(
                    claim=text,
                    extract_or_location=text,
                    named_subjects=[
                        {
                            "name": organization,
                            "subject_type": "organization",
                            "person_id": None,
                        }
                    ],
                )
                errors = validate_ledger.validate_references(data)
                self.assertFalse(
                    any("register the named person" in error for error in errors),
                    errors,
                )
                self.assertFalse(
                    any("human_harm_review" in error for error in errors),
                    errors,
                )

    def test_person_names_cannot_be_retyped_as_organizations(self):
        cases = (
            ("The regulator alleged Alex Doe committed fraud.", "Alex Doe"),
            ("The filing says alice chen lied.", "alice chen"),
            ("監管機構指控王小明涉嫌欺詐。", "王小明"),
            (
                "The regulator alleged procurement fraud by alice chen.",
                "alice chen",
            ),
            ("王小明遭監管機構指控欺詐。", "王小明"),
        )
        for text, name in cases:
            with self.subTest(name=name):
                data = ledger_with_fact(
                    claim=text,
                    extract_or_location=text,
                    named_subjects=[
                        {
                            "name": name,
                            "subject_type": "organization",
                            "person_id": None,
                        }
                    ],
                )
                joined = " ".join(validate_ledger.validate_references(data))
                self.assertIn("cannot be declared as an organization", joined)
                self.assertIn("register the named person", joined)
                self.assertIn("human_harm_review", joined)

    def test_untyped_named_organization_fails_subject_inventory(self):
        text = "Transparency International reported alleged procurement fraud."
        data = ledger_with_fact(
            claim=text,
            extract_or_location=text,
        )
        joined = " ".join(validate_ledger.validate_references(data))
        self.assertIn("named_subjects", joined)

    def test_person_subject_inventory_requires_registry_linkage(self):
        text = "The filing accuses alice chen of lying."
        data = ledger_with_fact(
            claim=text,
            extract_or_location=text,
            named_subjects=[
                {
                    "name": "alice chen",
                    "subject_type": "person",
                    "person_id": None,
                }
            ],
        )
        joined = " ".join(validate_ledger.validate_references(data))
        self.assertIn("person_id", joined)
        self.assertIn("register", joined)

    def test_named_subject_inventory_schema_types_person_and_organization(self):
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        fixture["claims"][0]["named_subjects"] = [
            {
                "name": "Example Organization",
                "subject_type": "organization",
                "person_id": None,
            }
        ]
        self.assertEqual([], validate_ledger.validate_schema(fixture, schema))
        fixture["claims"][0]["named_subjects"] = [
            {
                "name": "Alice Chen",
                "subject_type": "person",
                "person_id": None,
            }
        ]
        errors = validate_ledger.validate_schema(fixture, schema)
        self.assertTrue(
            any("person_id" in error for error in errors),
            errors,
        )

    def test_typed_harm_without_person_linkage_fails_closed(self):
        data = ledger_with_fact(
            claim="The filing accuses the unnamed executive of misconduct.",
            person_claim_role="harmful",
            person_claim_assessment={
                "classification": "harmful",
                "rationale": (
                    "The claim is explicitly typed as harmful to a person, "
                    "but the required identity and status are unresolved."
                ),
            },
        )
        joined = " ".join(validate_ledger.validate_references(data))
        self.assertIn("register", joined)
        self.assertIn("person_ids", joined)
        self.assertIn("human_harm_review", joined)

    def test_named_person_harm_cannot_bypass_safeguards_without_registry(self):
        data = ledger_with_fact(
            claim=(
                "The regulator alleged that Alex Doe committed procurement "
                "fraud."
            ),
            extract_or_location=(
                "The regulator alleged that Alex Doe committed procurement "
                "fraud."
            ),
        )
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("register the named person", joined)
        self.assertIn("human_harm_review", joined)

    def test_harmful_report_excerpt_requires_person_registry_and_review(self):
        data = ledger_with_fact(
            claim="The filing concerns a procurement review.",
            extract_or_location="The filing concerns a procurement review.",
            report_excerpts=[
                "The report says Alex Doe committed procurement fraud."
            ],
        )
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("register the named person", joined)
        self.assertIn("human_harm_review", joined)

    def test_unregistered_person_review_still_runs_every_harm_safeguard(self):
        data = ledger_with_fact(
            claim=(
                "The regulator alleged that Alex Doe committed procurement "
                "fraud."
            ),
            person_claim_role="harmful",
            person_claim_assessment={
                "classification": "harmful",
                "rationale": (
                    "This claim alleges criminal misconduct by a named person "
                    "and therefore requires the complete safety review."
                ),
            },
            human_harm_review={
                "category": "wrongdoing",
                "legal_stage": "alleged",
                "source_floor": "met",
                "accountable_source_ids": [],
                "attributed_to": "An unnamed source",
                "resolution_status": "unresolved",
                "resolution_search": None,
                "right_of_reply": None,
                "governing_question_relevance": "",
            },
        )
        joined = " ".join(validate_ledger.validate_references(data))
        for expected in (
            "register the named person",
            "two independent source families",
            "accountable source",
            "must be attributed",
            "resolution search",
            "right of reply",
            "governing-question relevance",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, joined)

    def test_named_organizations_do_not_trigger_person_safeguards(self):
        data = ledger_with_fact(
            claim=(
                "The New York Times reported alleged procurement fraud by "
                "Acme Corp."
            ),
            extract_or_location=(
                "The New York Times reported alleged procurement fraud by "
                "Acme Corp."
            ),
        )
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("register the named person" in error for error in errors),
            errors,
        )

    def test_explicit_person_claim_role_triggers_review_beyond_keyword_lists(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = "The regulator reported that Alex Doe embezzled public funds."
        claim["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("protected-person harm claim requires" in error for error in errors),
            errors,
        )

    def test_registered_person_name_always_requires_the_person_link(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = "Alex Doe embezzled public funds."
        claim["person_ids"] = []
        claim.pop("person_claim_role")
        claim["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("does not link that person_id" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("human_harm_review" in error for error in errors),
            errors,
        )

    def test_person_link_requires_an_explicit_claim_role(self):
        data = living_harm_ledger()
        data["claims"][-1].pop("person_claim_role")
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("person_claim_role classification" in error for error in errors),
            errors,
        )

    def test_neutral_classification_cannot_override_harmful_wording(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = "Alex Doe embezzled public funds."
        claim["person_claim_role"] = "neutral"
        claim["person_claim_assessment"] = {
            "classification": "neutral",
            "rationale": (
                "This deliberately incorrect assessment attempts to label "
                "an accusation of embezzlement as neutral background."
            ),
        }
        claim["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("harmful wording conflicts" in error for error in errors),
            errors,
        )

    def test_person_claim_assessment_is_required_and_role_bound(self):
        data = living_harm_ledger()
        data["claims"][-1].pop("person_claim_assessment")
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("person_claim_assessment" in error for error in errors),
            errors,
        )

    def test_unrelated_same_person_claim_cannot_count_as_a_response(self):
        data = living_harm_ledger()
        response = data["claims"][0]
        response["claim"] = "Alex Doe founded a company."
        response["person_ids"] = ["P1"]
        response["person_claim_role"] = "neutral"
        response["person_claim_assessment"] = {
            "classification": "neutral",
            "rationale": (
                "This claim records an ordinary company-founding fact and "
                "does not answer or resolve the alleged misconduct."
            ),
        }
        review = data["claims"][-1]["human_harm_review"]
        review["right_of_reply"] = {
            "status": "documented",
            "response_claim_ids": ["C1"],
            "search_record": None,
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("must reciprocally respond" in error for error in errors),
            errors,
        )

    def test_unrelated_same_person_claim_cannot_count_as_a_resolution(self):
        data = living_harm_ledger()
        resolution = data["claims"][0]
        resolution["claim"] = "Alex Doe founded a company."
        resolution["person_ids"] = ["P1"]
        resolution["person_claim_role"] = "neutral"
        resolution["person_claim_assessment"] = {
            "classification": "neutral",
            "rationale": (
                "This claim records an ordinary company-founding fact and "
                "does not answer or resolve the alleged misconduct."
            ),
        }
        review = data["claims"][-1]["human_harm_review"]
        review["resolution_status"] = "resolved"
        review["resolution_claim_ids"] = ["C1"]
        review["resolution_search"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("must reciprocally resolve" in error for error in errors),
            errors,
        )

    def test_person_brief_pronoun_cannot_omit_the_primary_subject_link(self):
        data = living_harm_ledger()
        data["brief"] = {"archetype": "person"}
        claim = data["claims"][-1]
        claim["claim"] = (
            "The regulator alleged that he committed procurement fraud."
        )
        claim["person_ids"] = []
        claim["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "must link the protected primary subject P1" in error
                for error in errors
            ),
            errors,
        )

    def test_legal_allegation_cannot_be_classified_as_nonlegal(self):
        data = living_harm_ledger()
        data["claims"][-1]["human_harm_review"]["legal_stage"] = "nonlegal"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("cannot be classified as nonlegal" in error for error in errors),
            errors,
        )

    def test_denied_allegation_is_not_support_for_an_allegation(self):
        data = living_harm_ledger()
        for evidence in data["claims"][-1]["source_evidence"]:
            evidence["extract_or_location"] = (
                "The source states that the regulator did not allege "
                "procurement fraud by Alex Doe."
            )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("source evidence does not establish" in error for error in errors),
            errors,
        )

    def test_withdrawal_evidence_cannot_remain_marked_unresolved(self):
        data = living_harm_ledger()
        data["claims"][-1]["source_evidence"][0][
            "extract_or_location"
        ] += " The regulator later withdrew the allegation."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("unresolved harm conflicts" in error for error in errors),
            errors,
        )

    def test_legal_allegation_cannot_skip_resolution_review(self):
        data = living_harm_ledger()
        review = data["claims"][-1]["human_harm_review"]
        review["resolution_status"] = "not_applicable"
        review["resolution_search"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("cannot mark resolution as not_applicable" in error for error in errors),
            errors,
        )

    def test_unrelated_second_source_does_not_count_as_harm_corroboration(self):
        data = living_harm_ledger()
        data["claims"][-1]["source_evidence"][1][
            "extract_or_location"
        ] = "The weather report says the sky was clear."
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("two independent source families" in error for error in errors),
            errors,
        )

    def test_harm_claim_must_state_the_declared_legal_stage(self):
        data = living_harm_ledger()
        data["claims"][-1]["claim"] = (
            "The regulator reported that Alex Doe committed procurement fraud."
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("legal stage" in error.lower() for error in errors),
            errors,
        )

    def test_right_of_reply_cannot_be_marked_not_applicable(self):
        data = living_harm_ledger()
        data["claims"][-1]["human_harm_review"]["right_of_reply"] = {
            "status": "not_applicable",
            "response_claim_ids": [],
            "search_record": None,
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("cannot be not_applicable" in error for error in errors),
            errors,
        )

    def test_right_of_reply_claim_must_belong_to_the_same_person(self):
        data = living_harm_ledger()
        data["claims"][-1]["human_harm_review"]["right_of_reply"] = {
            "status": "documented",
            "response_claim_ids": ["C1"],
            "search_record": None,
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("same protected person" in error for error in errors),
            errors,
        )

    def test_person_archetype_requires_a_registered_primary_subject(self):
        data = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        data["brief"]["archetype"] = "person"
        data["people"] = []
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = validate_ledger.validate_schema(data, schema)
        self.assertTrue(any("people" in error for error in errors), errors)

    def test_duplicate_person_ids_cannot_disable_protection(self):
        data = living_harm_ledger()
        data["people"].append(
            {
                "person_id": "P1",
                "name": "Historical Person",
                "aliases": [],
                "living_status": "deceased",
                "public_role": "public",
                "relationship": "adjacent",
            }
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("Duplicate person ID" in error for error in errors),
            errors,
        )

    def test_charged_battery_is_not_a_legal_harm_claim(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = "Alex Doe charged the battery before the field test."
        claim["person_claim_role"] = "neutral"
        claim["person_claim_assessment"] = {
            "classification": "neutral",
            "rationale": (
                "The verb describes charging an electronic battery and not "
                "a legal accusation or harmful personal claim."
            ),
        }
        claim["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("human_harm_review" in error for error in errors),
            errors,
        )

    def test_sensitive_fact_cannot_use_a_nonprivacy_review_category(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = (
            "The regulator reported Alex Doe's private medical diagnosis."
        )
        claim["human_harm_review"]["category"] = "wrongdoing"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("sensitive_private_fact" in error for error in errors),
            errors,
        )

    def test_single_source_harm_cannot_feed_a_key_report_claim(self):
        data = living_harm_ledger()
        harm_claim = data["claims"][-1]
        limitation = "Only one accountable source was available."
        harm_claim["claim"] += " " + limitation
        harm_claim["human_harm_review"]["source_floor"] = (
            "single_source_limited"
        )
        harm_claim["human_harm_review"][
            "sourcing_limitation_excerpt"
        ] = limitation
        harm_claim["triangulation"]["status"] = "limited"
        data["claims"][0]["supports"] = ["C2"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("key report claim" in error.lower() for error in errors),
            errors,
        )

    def test_named_protected_person_cannot_bypass_review_by_omitting_person_id(self):
        data = living_harm_ledger()
        data["claims"][-1]["person_ids"] = []
        data["claims"][-1]["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("does not link that person_id" in error for error in errors),
            errors,
        )

    def test_legal_stage_cannot_exceed_what_the_sources_establish(self):
        data = living_harm_ledger()
        claim = data["claims"][-1]
        claim["claim"] = (
            "The regulator said Alex Doe was convicted of procurement fraud."
        )
        claim["human_harm_review"]["legal_stage"] = "convicted"
        claim["human_harm_review"]["attributed_to"] = "The regulator"
        claim["source_evidence"] = [
            {
                "source_id": "S1",
                "extract_or_location": (
                    "The regulator charged Alex Doe with procurement fraud."
                ),
            },
            {
                "source_id": "S2",
                "extract_or_location": (
                    "The independent report confirms that charges were filed."
                ),
            },
        ]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("legal stage" in error.lower() for error in errors),
            errors,
        )

    def test_known_resolution_must_travel_with_the_harmful_report_excerpt(self):
        data = living_harm_ledger()
        harm_claim = data["claims"][-1]
        resolution_claim = data["claims"][0]
        resolution_claim["claim"] = "The conviction was overturned."
        resolution_claim["report_excerpts"] = [
            "A later court overturned the conviction."
        ]
        harm_claim["include_in_report"] = True
        harm_claim["report_excerpts"] = [
            "The regulator alleged procurement fraud by Alex Doe."
        ]
        harm_claim["human_harm_review"]["resolution_status"] = "resolved"
        harm_claim["human_harm_review"]["resolution_claim_ids"] = ["C1"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("same report excerpt" in error.lower() for error in errors),
            errors,
        )

    def test_harmful_claim_about_a_living_person_requires_a_bound_review(self):
        data = living_harm_ledger()
        data["claims"][1]["human_harm_review"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("C2: protected-person harm claim requires" in error for error in errors),
            errors,
        )

    def test_corroboration_needs_two_families_and_an_accountable_source(self):
        data = living_harm_ledger()
        data["sources"][1]["source_family"] = data["sources"][0]["source_family"]
        data["sources"][0]["accountability_basis"] = "none"
        data["sources"][0].pop("accountability_note")
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("needs two independent source families", joined)
        self.assertIn("needs an accountable source", joined)

    def test_right_of_reply_cannot_be_omitted(self):
        data = living_harm_ledger()
        data["claims"][1]["human_harm_review"]["right_of_reply"] = None
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("right of reply" in error for error in errors),
            errors,
        )

    def test_complete_living_person_safety_record_passes(self):
        errors = [
            error
            for error in validate_ledger.validate_references(living_harm_ledger())
            if error.startswith("C2:")
        ]
        self.assertEqual([], errors)


class EstimateTests(unittest.TestCase):
    def test_estimate_requires_assumptions_in_the_ledger_and_the_schema(self):
        data = ledger_with_fact(
            kind="estimate",
            claim="A team of 12 engineers costs about 4800 per month.",
            extract_or_location="Pricing page: 400 per seat per month.",
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("an estimate must record its assumptions" in error for error in errors),
            errors,
        )
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        schema_errors = validate_ledger.validate_schema(
            {"claims": [data["claims"][1]]},
            {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": schema["$defs"]["claim"],
                    }
                },
                "$defs": schema["$defs"],
            },
        )
        self.assertTrue(
            any("assumptions" in error for error in schema_errors),
            schema_errors,
        )

    def test_assumptions_carry_the_arithmetic_behind_an_estimate(self):
        data = ledger_with_fact(
            kind="estimate",
            claim="A team of 12 engineers costs about 4800 per month.",
            extract_or_location="Pricing page: 400 per seat per month.",
            assumptions=[
                "Twelve seats at the listed 400 per seat gives 4800 a month.",
            ],
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if error.startswith("C2:")
        ]
        self.assertEqual([], errors)


class LedgerReferenceTests(unittest.TestCase):
    def test_direct_sources_need_one_unique_evidence_record_each(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_evidence"] = [
            {
                "source_id": "S1",
                "extract_or_location": "The registry records the result.",
            },
            {
                "source_id": "S1",
                "extract_or_location": "A duplicate record for one source.",
            },
            {
                "source_id": "S9",
                "extract_or_location": "Evidence from an unrelated source.",
            },
        ]
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("duplicate source_evidence for S1", joined)
        self.assertIn("source_evidence references S9", joined)
        self.assertIn("source_evidence is missing S2", joined)

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
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": "Known source evidence.",
                        }
                    ],
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

    def test_time_sensitive_claims_need_current_dates_and_dated_sources(self):
        data = valid_quality_ledger()
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = None
        data["sources"][0]["published"] = None
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("time-sensitive", joined)
        self.assertIn("undated_reason", joined)

        data["claims"][0]["as_of"] = "2026-07-28"
        data["sources"][0]["undated_reason"] = (
            "This is a continuously updated official documentation page."
        )
        errors = validate_ledger.validate_references(data)
        self.assertFalse(any("time-sensitive" in error for error in errors), errors)
        self.assertFalse(any("undated_reason" in error for error in errors), errors)

    def test_stale_time_sensitive_claim_is_reported(self):
        data = valid_quality_ledger()
        data["report_date"] = "2026-07-28"
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = "2026-05-01"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("88 days before" in error for error in errors), errors)

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
