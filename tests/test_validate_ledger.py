import importlib.util
import json
import re
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
                "claim": "A 47% rise leaves the vendor exposed.",
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
            ("Prices rose by twenty-five percent.", "the increase was 25%"),
            ("It rose thirty-seven percent.", "a 37% rise"),
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
                "extract_or_location" in error
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
                "The July 2026 index lists 1,200 packages at v2.10.3, "
                "three of them deprecated, 8.4 on the severity scale, and "
                "1.5 million downloads. See https://example.net/2099/44 and "
                "claim C1 for context."
            ),
            extract_or_location=(
                "Index page: 1200 packages at version 2.10.3; three entries "
                "are marked deprecated; severity 8.4; 1500000 downloads; "
                "dated 2026-07-14."
            ),
            source_evidence=[
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "Index page: 1200 packages at version 2.10.3; three "
                        "entries are marked deprecated; severity 8.4; "
                        "1500000 downloads; dated 2026-07-14."
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
                "extract_or_location" in error
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


class ChineseQuantityScanTests(unittest.TestCase):
    """Numbers are verified the same way in English and in Chinese.

    Han characters match ``\\w``, so the digit scan's word-boundary guard used to
    switch itself off in ordinary Chinese prose, where numerals sit flush
    against the characters beside them. Nothing between a Chinese claim and its
    evidence was checked.
    """

    def test_spaceless_chinese_claim_creates_obligations(self):
        for claim, figure in (
            ("营收增长12%。", "12"),
            ("全年用電量達" "6800" "萬度。", "68000000"),
        ):
            with self.subTest(claim=claim):
                obligations = validate_ledger.quantitative_obligations(claim)
                self.assertTrue(obligations, claim)
                self.assertIn(
                    f"n:{figure}",
                    set().union(*(forms for _, forms in obligations)),
                )

    def test_spaceless_chinese_extract_satisfies_the_same_figure(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "营收增长12%。",
                    "extract_or_location": (
                        "该公司报告营收增长12%。"
                    ),
                }
            ),
        )

    def test_a_scaled_figure_rejects_evidence_at_a_different_scale(self):
        # A scale word is part of the figure: keeping the bare digits as an
        # acceptable form let "6800萬" match "6800億" (and "5 million" match
        # "5 billion") through the shared digits.
        for claim, extract in (
            ("全年用電量達6800萬度。", "全年用電量達6800億度。"),
            ("全年用電量達6800萬度。", "全年用電量達6800度。"),
            ("增加了6800。", "增加至6800億。"),
            ("Usage reached 6800 million kWh.", "Usage reached 6800 billion kWh."),
            ("Usage reached 5 million users.", "Usage reached 5 billion users."),
        ):
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

    def test_a_scaled_figure_still_matches_equivalent_notations(self):
        for claim, extract in (
            ("全年用電量達6800萬度。", "電量為68,000,000度。"),
            ("增至0.68億度。", "電量為6800萬度。"),
            ("Usage reached 68 million kWh.", "metered at 68,000,000 kWh."),
        ):
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

    def test_a_chinese_figure_absent_from_the_extract_is_rejected(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "全年用電量達" "6800" "萬度。",
                "extract_or_location": (
                    "全年用電量達" "5200" "萬度。"
                ),
            }
        )
        self.assertTrue(
            any("6800" in error and "quantity" in error for error in errors),
            errors,
        )

    def test_chinese_scale_suffix_matches_the_written_out_figure(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "全年用電量達" "6800" "萬度。",
                    "extract_or_location": (
                        "全年用電量為" "68,000,000" "度。"
                    ),
                }
            ),
        )

    def test_a_chinese_date_is_one_obligation_not_three_numbers(self):
        obligations = validate_ledger.quantitative_obligations(
            "報告日期為" "2026" "年" "7" "月" "28" "日。"
        )
        self.assertEqual(["2026-07-28"], [display for display, _ in obligations])
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": (
                        "報告日期為" "2026" "年" "7"
                        "月" "28" "日。"
                    ),
                    "extract_or_location": (
                        "刊登於" "2026-07-28" "。"
                    ),
                }
            ),
        )

    def test_ledger_ids_and_identifiers_stay_excluded_in_chinese_prose(self):
        self.assertEqual(
            [],
            validate_ledger.quantitative_obligations(
                "見C12的說明，並参考S3。"
            ),
        )
        self.assertEqual(
            ["CVE-2021-1234"],
            [
                display
                for display, _ in validate_ledger.quantitative_obligations(
                    "漏洞CVE-2021-1234已修補。"
                )
            ],
        )
        self.assertEqual(
            ["v1.2.3"],
            [
                display
                for display, _ in validate_ledger.quantitative_obligations(
                    "本版本v1.2.3已發布。"
                )
            ],
        )

    def test_english_scanning_is_unchanged(self):
        self.assertEqual(
            [("12", {"n:12"}), ("2025", {"n:2025"})],
            validate_ledger.quantitative_obligations(
                "Revenue grew 12% in 2025."
            ),
        )
        self.assertEqual(
            [],
            validate_ledger.quantitative_obligations(
                "See https://example.com/a/2026-07-28 for claim C12."
            ),
        )
        for name in ("en", "zh-CN", "zh-HK"):
            ledger = json.loads(
                (
                    ROOT
                    / "tests"
                    / "fixtures"
                    / "golden"
                    / name
                    / "ledger.json"
                ).read_text(encoding="utf-8")
            )
            with self.subTest(ledger=name):
                self.assertEqual([], validate_ledger.validate_references(ledger))


class ChineseWordNumberScanTests(unittest.TestCase):
    """Han-numeral word forms, checked with English word-numbers as parity.

    English spells a count or a magnitude the same way ("three CVEs", "fifty
    percent") and scans both, excluding only ordinal-in-unit-context and
    fraction words. Chinese numerals double as grammatical filler far more
    often ("一起", "十分", "萬一"), so the same "scan everything" rule would
    manufacture obligations out of ordinary prose. Each test below either
    mirrors an English behavior directly or documents the narrower,
    context-gated substitute and why it is narrower.
    """

    def test_han_percent_is_an_evidence_obligation(self):
        # "百分之十二" is 12%, exactly as "12%" is: satisfiable by a digit
        # extract and vice versa, symmetric like every other quantity form.
        self.assertEqual({"n:12"}, validate_ledger.quantitative_evidence("百分之十二"))
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "违约率达百分之十二。",
                    "extract_or_location": "违约率为12%。",
                }
            ),
        )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "违约率达12%。",
                    "extract_or_location": "违约率为百分之十二。",
                }
            ),
        )

    def test_han_percent_decimal_is_an_evidence_obligation(self):
        # 點/点 is the decimal point; every digit after it is read on its own
        # ("三十五點五" -> 35.5, "零點八" -> 0.8), never through a place-value
        # unit. Before this, the decimal was silently dropped: "百分之三十五
        # 點五" resolved to a truncated 35, which rejected its own correct
        # evidence and let a genuinely wrong "35%" through instead.
        for phrase, expected in (("三十五點五", "35.5"), ("零點八", "0.8")):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence("百分之" + phrase),
                )
        # Word-decimal claim, matching digit-decimal evidence: accepted.
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C910",
                    "kind": "fact",
                    "claim": "增長百分之三十五點五。",
                    "extract_or_location": "報告稱增長35.5%。",
                }
            ),
        )
        # Word-decimal claim against a truncated digit extract: the figure is
        # genuinely different (35.5 != 35), so this must still be rejected --
        # on the quantity, not manufacture an unrelated direction error.
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C910",
                "kind": "fact",
                "claim": "增長百分之三十五點五。",
                "extract_or_location": "報告稱增長35%。",
            }
        )
        self.assertTrue(any("quantity" in error for error in errors), errors)
        self.assertFalse(any("direction" in error for error in errors), errors)
        # Digit-decimal claim, matching word-decimal evidence: symmetric.
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C910",
                    "kind": "fact",
                    "claim": "增長35.5%。",
                    "extract_or_location": "報告稱增長百分之三十五點五。",
                }
            ),
        )

    def test_han_cheng_percent_is_an_evidence_obligation(self):
        # 成 is tenths: "六成八" is 68%, "三成" alone is 30%.
        for phrase, expected in (("六成八", 68), ("三成", 30), ("一成二", 12)):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence(phrase),
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "產銷差水量的六成八歸因於管網漏損。",
                    "extract_or_location": "產銷差水量的68%歸因於管網漏損。",
                }
            ),
        )
        self.assertTrue(
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "產銷差水量的六成八歸因於管網漏損。",
                    "extract_or_location": "產銷差水量的12%歸因於管網漏損。",
                }
            )
        )

    def test_han_scale_magnitude_is_an_evidence_obligation(self):
        # "三千萬"/"六億" are figures exactly as "3000萬"/"6億" already are;
        # the leading digit (三/六) is what makes them unambiguous (see the
        # idiom tests below for the case without one).
        for phrase, expected in (("三千萬", 30_000_000), ("六億", 600_000_000)):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence(phrase),
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "年度成本將增加三千萬元。",
                    "extract_or_location": "年度成本將增加30,000,000元。",
                }
            ),
        )
        self.assertTrue(
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "年度成本將增加三千萬元。",
                    "extract_or_location": "年度成本將增加三億元。",
                }
            )
        )

    def test_ten_leading_scale_magnitude_is_an_evidence_obligation(self):
        # 十 supplies a leading quantity of its own ("十八萬" is 1*10 + 8, then
        # times 10,000), so these are figures exactly as "三千萬" is. The guard
        # for "萬一"/"千萬" demanded a bare *digit* at the head, and 十 is a
        # place-value unit rather than a digit -- so every 十-leading magnitude
        # walked past the whole check with no obligation at all.
        for phrase, expected in (
            ("十萬", 100_000),
            ("十八萬", 180_000),
            ("二十五萬", 250_000),
            ("十五億", 1_500_000_000),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence(phrase),
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C906",
                    "kind": "fact",
                    "claim": "全區已安裝十八萬個智慧水錶。",
                    "extract_or_location": "全區已安裝180,000個智慧水錶。",
                }
            ),
        )
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C906",
                "kind": "fact",
                "claim": "全區已安裝十八萬個智慧水錶。",
                "extract_or_location": "全區已安裝18,000個智慧水錶。",
            }
        )
        self.assertTrue(any("quantity" in error for error in errors), errors)

    def test_han_decimal_before_a_scale_word_is_an_evidence_obligation(self):
        # The decimal machinery (點/点) and the scale machinery have to compose:
        # "三點五萬" is 35,000 exactly as "3.5萬" is. They did not, so the
        # numeral run stopped at the fractional digit, the scale word was left
        # to match alone, and a Han decimal magnitude asserted nothing.
        for phrase, expected in (
            ("三點五萬", 35_000),
            ("三点五万", 35_000),
            ("零點八億", 80_000_000),
            ("一點二五億", 125_000_000),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    {f"n:{expected}"},
                    validate_ledger.quantitative_evidence(phrase),
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C907",
                    "kind": "fact",
                    "claim": "本期損失三點五萬元。",
                    "extract_or_location": "本期損失35,000元。",
                }
            ),
        )
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C907",
                "kind": "fact",
                "claim": "本期損失三點五萬元。",
                "extract_or_location": "本期損失3.5元。",
            }
        )
        self.assertTrue(any("quantity" in error for error in errors), errors)

    def test_mixed_digit_and_han_compound_is_one_number(self):
        # "3萬5千" is 35,000. The digit scanner took "3萬" off the front and
        # left "5" behind, so the claim asserted 30,000 *and* 5: it rejected its
        # own correct evidence ("35,000件") and accepted a fabricated extract
        # that merely carried 30000 and 5 somewhere.
        for phrase, expected in (
            ("3萬5千", 35_000),
            ("5萬3千", 53_000),
            ("1萬2千3百", 12_300),
            ("三萬5千", 35_000),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    [(phrase, {f"n:{expected}"})],
                    validate_ledger.quantitative_obligations(phrase),
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C908",
                    "kind": "fact",
                    "claim": "庫存達3萬5千件。",
                    "extract_or_location": "庫存為35,000件。",
                }
            ),
        )
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C908",
                "kind": "fact",
                "claim": "庫存達3萬5千件。",
                "extract_or_location": "庫存為30000件，另有5件待驗。",
            }
        )
        self.assertTrue(any("quantity" in error for error in errors), errors)

    def test_an_abbreviated_compound_offers_both_readings(self):
        # Bare digits after a scale word are genuinely ambiguous in writing:
        # "3萬5" is 35,000 read as an abbreviation and 30,005 read strictly by
        # place value. One token carrying both readings keeps the obligation
        # alive without rejecting a correct extract over the reading the writer
        # did not intend -- unlike the two wrong tokens this used to produce.
        self.assertEqual(
            {"n:35000", "n:30005"},
            validate_ledger.quantitative_evidence("3萬5"),
        )
        self.assertEqual(
            {"n:185000", "n:180005"},
            validate_ledger.quantitative_evidence("十八萬五"),
        )
        # An explicit 零 placeholder settles the reading: 十萬零一 is 100,001.
        self.assertEqual(
            {"n:100001"},
            validate_ledger.quantitative_evidence("十萬零一"),
        )
        obligations = validate_ledger.quantitative_obligations("庫存達3萬5件。")
        self.assertEqual(["3萬5"], [display for display, _ in obligations])
        for extract in ("庫存為35,000件。", "庫存為30,005件。"):
            with self.subTest(extract=extract):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C909",
                            "kind": "fact",
                            "claim": "庫存達3萬5件。",
                            "extract_or_location": extract,
                        }
                    ),
                )
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C909",
                "kind": "fact",
                "claim": "庫存達3萬5件。",
                "extract_or_location": "庫存為30000件。",
            }
        )
        self.assertTrue(any("quantity" in error for error in errors), errors)

    def test_a_scale_word_without_a_leading_quantity_stays_silent(self):
        # The counterpart to the 十-leading fix: opening *on* the scale word,
        # or the adverb 千萬, still creates nothing, mixed scripts included.
        for phrase in ("萬一", "千萬", "億", "萬五千"):
            with self.subTest(phrase=phrase):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(phrase))
        # Mixed scripts take the same exit: the digit is read as a digit, the
        # way English reads a bare "5", and no scaled figure is invented for it.
        self.assertEqual({"n:5"}, validate_ledger.quantitative_evidence("萬5千"))

    def test_han_scale_word_matches_the_digit_form_and_vice_versa(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "第二期覆蓋四萬二千戶。",
                    "extract_or_location": "第二期覆蓋42,000戶。",
                }
            ),
        )

    def test_han_plain_count_is_an_evidence_obligation(self):
        # Mirrors English's spelled counts ("three CVEs", "ten engineers"):
        # a Han count gated on the 個/个 classifier behaves the same way.
        for claim in (
            "研究人員揭露三個漏洞。",
            "第一期換表已完成十八個月。",
            "服務公司過去三年掉十一個百分點。",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C901",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": "本頁概述產品。",
                        }
                    )
                )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C901",
                    "kind": "fact",
                    "claim": "研究人員揭露三個漏洞。",
                    "extract_or_location": "報告記錄3個漏洞。",
                }
            ),
        )
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C901",
                    "kind": "fact",
                    "claim": "第一期換表已完成十八個月。",
                    "extract_or_location": "第一期換表已完成18個月。",
                }
            ),
        )

    def test_han_count_rejects_a_different_value(self):
        self.assertTrue(
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C901",
                    "kind": "fact",
                    "claim": "研究人員揭露三個漏洞。",
                    "extract_or_location": "報告記錄5個漏洞。",
                }
            )
        )

    def test_han_ordinals_do_not_create_obligations(self):
        # "第三"/"第十八" name a position, not a figure, mirroring the
        # exclusion English fractions and ordinal-units get.
        for phrase in ("第三", "第十八", "第一級"):
            with self.subTest(phrase=phrase):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(phrase))
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C902",
                    "kind": "fact",
                    "claim": "投資委員會將在第三次會議上表決。",
                    "extract_or_location": "本頁概述產品。",
                }
            ),
        )

    def test_han_fractions_do_not_create_obligations(self):
        # "三分之二" denotes 2/3, mirroring English's "two-thirds": neither
        # side of the fraction becomes an obligation.
        for phrase in ("三分之二", "十分之九", "四年之內增加約三分之二"):
            with self.subTest(phrase=phrase):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(phrase))
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C903",
                    "kind": "fact",
                    "claim": "產能約佔全公司三分之二。",
                    "extract_or_location": "本頁概述產品。",
                }
            ),
        )

    def test_bare_yi_is_not_a_count_but_larger_numerals_are(self):
        # "一個" is Chinese's indefinite article ("一個漏洞" reads as "a bug",
        # not "1 bug"), the role English gives to "a"/"an" -- words that never
        # appear in _NUMBER_WORDS. Nothing else in the digit table is
        # grammaticalized this way, so "兩個"/"三個" still count.
        self.assertEqual(set(), validate_ledger.quantitative_evidence("一個漏洞"))
        self.assertEqual({"n:2"}, validate_ledger.quantitative_evidence("兩個漏洞"))
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C904",
                    "kind": "fact",
                    "claim": "委員會每年開放一個撥款窗口。",
                    "extract_or_location": "本頁概述產品。",
                }
            ),
        )

    def test_idiomatic_numerals_stay_silent(self):
        # Every phrase below uses a numeral character idiomatically, not as a
        # figure. None has a classifier, scale word with a leading digit, or
        # percent/fraction marker behind it, so none creates an obligation --
        # the context guards exclude them without a stoplist.
        for phrase in (
            "萬一",       # "just in case"
            "千萬不要",     # "by all means, don't" (the adverb, not 10,000,000)
            "十分感謝",     # "very" (thankful)
            "大家一起努力",  # "together"
            "還有一些問題",  # "some"
            "情況一般",     # "so-so" / ordinary
            "一旦發生",     # "once/if"
            "這是二手貨",    # "secondhand"
            "亞洲國家之一",  # "one of the ..."
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(phrase))
        for claim in (
            "委員會決定千萬不要在本季度換表。",
            "沅安計量技術研究所提醒，這批表萬一失準會影響回收期。",
        ):
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C905",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": "本頁概述產品。",
                        }
                    ),
                )

    def test_simplified_and_traditional_forms_agree(self):
        pairs = (
            ("三千萬", "三千万"),
            ("六億", "六亿"),
            ("兩個漏洞", "两个漏洞"),
            ("十萬零一", "十万零一"),
            ("十八萬", "十八万"),
            ("三點五萬", "三点五万"),
            ("3萬5千", "3万5千"),
            ("三點五千瓦", "三点五千瓦"),
            ("一點五百分點", "一点五百分点"),
            ("五千噸", "五千吨"),
            ("五千瓦時", "五千瓦时"),
        )
        for traditional, simplified in pairs:
            with self.subTest(traditional=traditional, simplified=simplified):
                self.assertEqual(
                    validate_ledger.quantitative_evidence(traditional),
                    validate_ledger.quantitative_evidence(simplified),
                )

    def test_measure_unit_figures_normalize_to_the_units_base_scale(self):
        # 千 (kilo-) and 百 (hecto-) are unit prefixes as well as place values,
        # so one physical quantity has several spellings and a numeral run
        # cannot be read apart from the unit it modifies. Each figure with a
        # listed unit is converted to that unit's base scale and tagged with
        # its dimension, so 3,500 watts is one form however it is written --
        # and the un-normalized figure is never offered on its own, which is
        # what let a 5,000-watt claim pass on an extract reading 5瓦.
        for phrase, expected in (
            ("功率三點五千瓦。", ("三點五千瓦", {"u:W:3500", "n:3500"})),
            ("功率3.5千瓦。", ("3.5千瓦", {"u:W:3500", "n:3500"})),
            ("功率三千五百瓦。", ("三千五百瓦", {"u:W:3500", "n:3500"})),
            ("實測3,500瓦。", ("3,500瓦", {"u:W:3500", "n:3500"})),
            ("實測功率為 3.5 千瓦。", ("3.5 千瓦", {"u:W:3500", "n:3500"})),
            ("功率五千瓦。", ("五千瓦", {"u:W:5000", "n:5000"})),
            ("實測功率5瓦。", ("5瓦", {"u:W:5", "n:5"})),
            ("距離兩點五千米。", ("兩點五千米", {"u:m:2500", "n:2500"})),
            ("距離2,500米。", ("2,500米", {"u:m:2500", "n:2500"})),
            ("重量一點二千克。", ("一點二千克", {"u:g:1200", "n:1200"})),
            ("增加一點五百分點。", ("一點五百分點", {"u:pp:1.5", "n:1.5"})),
            ("能耗零點八千瓦時。", ("零點八千瓦時", {"u:Wh:800", "n:800"})),
            ("摄入一点五千卡。", ("一点五千卡", {"u:cal:1500", "n:1500"})),
            ("產量五千噸。", ("五千噸", {"u:t:5000", "n:5000"})),
            ("耗电五千瓦时。", ("五千瓦时", {"u:Wh:5000", "n:5000"})),
            ("摄入两千卡。", ("两千卡", {"u:cal:2000", "n:2000"})),
            ("感光元件五百萬像素。", ("五百萬像素", {"u:px:5000000", "n:5000000"})),
        ):
            display, forms = expected
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    [(display, forms)],
                    validate_ledger.quantitative_obligations(phrase),
                )

    def test_every_spelling_of_one_quantity_matches_every_other(self):
        # The false rejection the old both-readings split produced: a claim of
        # 三點五千瓦 emitted only 3.5 and refused an extract stating the
        # identical quantity as 3,500瓦. Normalization makes the four spellings
        # interchangeable in either role, claim or evidence.
        spellings = ("三點五千瓦", "3,500瓦", "3.5千瓦", "三千五百瓦")
        for claim_figure in spellings:
            for extract_figure in spellings:
                with self.subTest(claim=claim_figure, extract=extract_figure):
                    self.assertEqual(
                        [],
                        validate_ledger.evidence_coverage_errors(
                            {
                                "claim_id": "C920",
                                "kind": "fact",
                                "claim": f"水泵組的功率為{claim_figure}。",
                                "extract_or_location": f"實測功率為{extract_figure}。",
                            }
                        ),
                    )
        # 公里 and 千米 are one unit spelled two ways, so they share a
        # dimension and cross-match; 三百公里 is 300 km, never a 3 with a
        # "百公里" unit hung off it (the reading a 百公里 table entry invented).
        self.assertEqual(
            [("三百公里", {"u:m:300000", "n:300000"})],
            validate_ledger.quantitative_obligations("跑了三百公里。"),
        )
        for extract_figure in ("三百公里", "300公里", "300千米", "300,000米"):
            with self.subTest(extract=extract_figure):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C921",
                            "kind": "fact",
                            "claim": "車隊跑了三百公里。",
                            "extract_or_location": f"里程為{extract_figure}。",
                        }
                    ),
                )
        # Unit-less evidence at the base scale still satisfies the claim: the
        # normalized figure is offered untagged as well as tagged.
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C922",
                    "kind": "fact",
                    "claim": "水泵組的功率為三點五千瓦。",
                    "extract_or_location": "實測功率為3,500。",
                }
            ),
        )

    def test_a_figure_at_the_wrong_magnitude_is_rejected(self):
        # The wrong acceptance the both-readings split produced: 五千瓦 offered
        # a bare "5" alongside 5,000, and that 5 collided with the 5瓦 in the
        # extract -- a claim of 5,000 watts passed on evidence of 5 watts.
        # Each pair below states the same unit at a thousandfold difference.
        for claim, extract in (
            ("功率為五千瓦。", "實測功率5瓦。"),
            ("距離為八千米。", "實測距離8米。"),
            ("功率為三點五千瓦。", "實測功率3.5瓦。"),
            ("車隊跑了三百公里。", "里程為300米。"),
            ("感光元件五百萬像素。", "規格為5像素。"),
            # And a plainly different figure in the same unit, plus an extract
            # carrying no figure at all: neither may pass.
            ("功率為五千瓦。", "銘牌標示 800 瓦。"),
            ("功率為五千瓦。", "本頁概述產品。"),
        ):
            with self.subTest(claim=claim, extract=extract):
                errors = validate_ledger.evidence_coverage_errors(
                    {
                        "claim_id": "C923",
                        "kind": "fact",
                        "claim": claim,
                        "extract_or_location": extract,
                    }
                )
                self.assertTrue(any("quantity" in error for error in errors), errors)

    def test_a_swallowed_unit_prefix_only_reads_as_one_when_it_multiplies(self):
        # 百分點 is the one listed unit whose remainder after the prefix
        # ("分點") stands for nothing, so the swallowed-prefix reading is the
        # only one available: 五百分點 is 5 percentage points. It is accepted
        # only where the prefix actually multiplies what is left of the run --
        # 五百 is 五 hundreds, 三千五百 is not 三千五 hundreds.
        self.assertEqual(
            [("五百分點", {"u:pp:5", "n:5"})],
            validate_ledger.quantitative_obligations("服務公司掉五百分點。"),
        )
        self.assertEqual(
            [], validate_ledger.quantitative_obligations("服務公司掉三千五百分點。")
        )
        # Every compound spelling is worth its prefix times the base unit, so
        # the two ways a run can split ("五千"+"瓦" and "五"+"千瓦") always
        # normalize to the same figure and the reading never has to be guessed.
        for unit, (dimension, factor) in validate_ledger._CJK_MEASURE_UNITS.items():
            for taken in range(1, len(unit)):
                prefix, rest = unit[:taken], unit[taken:]
                base = validate_ledger._CJK_MEASURE_UNITS.get(rest)
                if base is None or not all(
                    char in validate_ledger._HAN_NUMERAL_CHARS for char in prefix
                ):
                    continue
                with self.subTest(unit=unit, prefix=prefix):
                    self.assertEqual(dimension, base[0])
                    self.assertEqual(
                        factor,
                        validate_ledger._han_phrase_value(prefix) * base[1],
                    )

    def test_measure_units_leave_plain_readings_alone(self):
        # A character sequence is only read as a unit if it is listed, because
        # 千/百 are ordinary place values everywhere else, and a unit phrase
        # needs a leading quantity of its own. Each phrase below keeps the
        # reading it already had.
        for phrase, expected in (
            ("增加了1.5百分點。", [("1.5百分點", {"u:pp:1.5", "n:1.5"})]),
            ("增加兩個百分點。", [("兩", {"n:2"})]),           # classifier count
            ("四年升了七点四个百分点", [("七点四", {"n:7.4"})]),
            ("營收三點五萬。", [("三點五萬", {"n:35000"})]),    # scale word
            ("第二期覆蓋五千戶。", []),      # 千 as a place value: 5,000 households
            ("消耗的千瓦電力較低。", []),     # a unit with no figure in front
            ("漏损集中在哪几百米上。", []),   # a vague "few hundred metres"
            ("油耗以每百公里計算。", []),     # 百公里 as a per-100km rate
            ("風機可達數千瓦。", []),        # "thousands of watts", no figure
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    expected, validate_ledger.quantitative_obligations(phrase)
                )
        # And the idiom guards are untouched: none of these opens a unit.
        for phrase in ("萬一", "千萬不要", "千萬分之一", "十分感謝", "第三次"):
            with self.subTest(phrase=phrase):
                self.assertEqual(set(), validate_ledger.quantitative_evidence(phrase))

    def test_golden_ledgers_still_pass_with_han_numeral_scanning(self):
        for name in ("en", "zh-CN", "zh-HK"):
            ledger = json.loads(
                (
                    ROOT / "tests" / "fixtures" / "golden" / name / "ledger.json"
                ).read_text(encoding="utf-8")
            )
            with self.subTest(ledger=name):
                self.assertEqual([], validate_ledger.validate_references(ledger))


class DirectionCarrierIgnoresNumeralNoiseTests(unittest.TestCase):
    """Regression cover for a direction-check false positive on Han numerals.

    evidence_coverage_errors binds a direction word ("增長") to its evidence
    by comparing "carrier" tokens drawn from the rest of the sentence. When
    the sentence has no Latin-script words, _assertion_carrier_tokens falls
    back to 2-character bigrams of every CJK character nearby. That fallback
    never excluded numerals, so a claim spelling its figure in Han words
    ("百分之三十五") turned the figure itself into the carrier -- while a
    digit-form figure ("35%") was never CJK to begin with and contributed
    nothing. Two claim/evidence pairs stating the identical figure then
    compared a numeral-bigram carrier ("百分","分之","之三",...) against an
    unrelated preamble ("報告","告稱"), found no overlap, and raised a
    direction error despite the evidence saying the same thing. Root cause:
    the CJK-bigram fallback treated numeral characters as carrier vocabulary
    instead of excluding them the way English number words already are.
    """

    def test_han_word_claim_against_digit_evidence_is_accepted(self):
        # The exact pair the coordinator reported as a false positive.
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C920",
                    "kind": "fact",
                    "claim": "增長百分之三十五。",
                    "extract_or_location": "報告稱增長35%。",
                }
            ),
        )

    def test_adjacent_variants_are_also_accepted(self):
        for claim, extract in (
            # Decrease direction, same word-vs-digit asymmetry.
            ("下降百分之三十五。", "報告稱下降35%。"),
            # Cheng-percent word form against a digit extract.
            ("增長六成八。", "報告稱增長68%。"),
            # Han-word claim against a Han-word extract (no ASCII at all).
            ("增長百分之三十五。", "報告稱增長百分之三十五。"),
            # A real subject noun alongside the word-form figure still
            # matches on that noun, not just the empty-carrier escape.
            ("營收增長百分之三十五。", "報告稱營收增長35%。"),
        ):
            with self.subTest(claim=claim, extract=extract):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C921",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": extract,
                        }
                    ),
                )

    def test_a_genuinely_unsupported_direction_is_still_rejected(self):
        # The fix must not turn the direction check into a no-op: a claim
        # asserting an increase against evidence with no increase language at
        # all (and a different, unrelated subject) is still flagged.
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C922",
                "kind": "fact",
                "claim": "營收增長百分之三十五。",
                "extract_or_location": "成本下降三成。",
            }
        )
        self.assertTrue(any("direction" in error for error in errors), errors)

    def test_carrier_tokens_exclude_numeral_characters(self):
        # Direct check on the mechanism itself: a sentence built entirely
        # from a Han-numeral phrase yields no carrier tokens at all, exactly
        # as a digit-form figure already does, rather than numeral bigrams.
        match = next(re.finditer("增長", "增長百分之三十五。"))
        self.assertEqual(
            set(),
            validate_ledger._assertion_carrier_tokens(
                "增長百分之三十五。", match
            ),
        )


if __name__ == "__main__":
    unittest.main()
