import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_ledger.py"
ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("validate_ledger", MODULE_PATH)
validate_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_ledger)

FIDELITY_SPEC = importlib.util.spec_from_file_location(
    "source_fidelity", ROOT / "scripts" / "source_fidelity.py"
)
source_fidelity = importlib.util.module_from_spec(FIDELITY_SPEC)
FIDELITY_SPEC.loader.exec_module(source_fidelity)


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
        self.assertTrue(any("'28' is in the claim" in error for error in errors), errors)

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
            any("'47' is in the claim" in error for error in errors),
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
                "'400' is in the claim but not in" in error
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
            if "2026-07-28" in error and "is in the claim" in error
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
                "'20' is in the claim but not in" in error
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
                "C1: key claim rests only on interested" in error
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


class AccountabilityNoteFloorTests(unittest.TestCase):
    def test_accountability_note_has_a_script_aware_prose_floor(self):
        """H7: schema floor 20 fits CJK; Latin notes still owe 40 characters."""
        data = living_harm_ledger()
        data["sources"][0]["accountability_note"] = "A signed docket entry."
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("accountability_note", joined)
        self.assertIn("threshold 40, actual 22", joined)
        data["sources"][0]["accountability_note"] = "监管机构在其案卷中公布了签署的执法记录。"
        self.assertNotIn(
            "accountability_note", " ".join(validate_ledger.validate_references(data))
        )


class EstimateTests(unittest.TestCase):
    def test_estimate_requires_assumptions_in_the_ledger(self):
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


class AnalysisReasoningTests(unittest.TestCase):
    """B1: analysis without reasoning is accepted + ledger/reference WARN."""

    def test_analysis_requires_reasoning_in_the_ledger(self):
        data = ledger_with_fact(
            kind="analysis",
            claim="The second review round is the only change between the figures.",
            extract_or_location="The second review round is the only change.",
        )
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("an analysis must record its reasoning" in error for error in errors),
            errors,
        )
        findings = [
            item
            for item in validate_ledger.collect_findings(data)
            if "an analysis must record its reasoning" in item.message
        ]
        self.assertEqual(1, len(findings), findings)
        self.assertEqual("ledger/reference", findings[0].family)
        self.assertEqual("warn", findings[0].severity)
        self.assertEqual(
            "set field reasoning in claims/*.json, then alx claim add claims/*.json",
            findings[0].fix,
        )
        printed = validate_ledger.render_grouped(findings)
        self.assertIn(
            "C2: an analysis must record its reasoning; "
            "state the inference that produced it",
            printed,
        )
        self.assertIn(
            "set field reasoning in claims/*.json, then alx claim add claims/*.json",
            printed,
        )
        self.assertEqual([], [item for item in findings if item.severity == "hard"])

    def test_reasoning_clears_the_analysis_warn(self):
        data = ledger_with_fact(
            kind="analysis",
            claim="The second review round is the only change between the figures.",
            extract_or_location="The second review round is the only change.",
            reasoning=(
                "The second review round is the only change between the two "
                "retention figures."
            ),
        )
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if "an analysis must record its reasoning" in error
        ]
        self.assertEqual([], errors)


class LedgerReferenceTests(unittest.TestCase):
    def test_two_evidence_records_for_one_source_are_allowed(self):
        # R22 restatement of test_direct_sources_need_one_unique_evidence_record
        # _each: two passages from one page are legitimate evidence; the
        # unlinked-source and extra-source_ids rules are unchanged.
        data = valid_quality_ledger()
        data["claims"][0]["source_evidence"] = [
            {
                "source_id": "S1",
                "extract_or_location": "The registry records the result.",
            },
            {
                "source_id": "S1",
                "extract_or_location": "A second passage from one source.",
            },
            {
                "source_id": "S9",
                "extract_or_location": "Evidence from an unrelated source.",
            },
        ]
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertNotIn("duplicate source_evidence", joined)
        self.assertIn("source_evidence references S9", joined)
        self.assertIn("extra source_ids", joined)

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
        self.assertNotIn("brief", joined)
        self.assertNotIn("synthesis", joined)

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
            any("1 key report claims are not in synthesis.central_judgment_claim_ids: C1" in error for error in errors),
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
        errors = validate_ledger.validate_schema(data, schema)
        self.assertFalse(
            any("synthesis.adversarial_tests" in error for error in errors),
            errors,
        )

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
            any("6800" in error and "is in the claim" in error for error in errors),
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
        self.assertEqual(["2026年7月28日"], [display for display, _ in obligations])
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
                errors = validate_ledger.validate_references(ledger)
                hard = [item for item in errors if not str(item).startswith("WARNING:")]
                self.assertEqual([], hard, errors)


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
        self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )
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

    def test_han_scale_magnitude_is_evidence_but_raises_no_finding(self):
        # R29: "三千萬"/"六億" still read as figures on the evidence side, so
        # they cover a digit claim; as a claim obligation they raise nothing.
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
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "年度成本將增加三千萬元。",
                    "extract_or_location": "年度成本將增加三億元。",
                }
            ),
        )

    def test_ten_leading_scale_magnitude_is_evidence_but_raises_no_finding(self):
        # 十 supplies a leading quantity of its own ("十八萬" is 1*10 + 8, then
        # times 10,000), so these read as figures exactly as "三千萬" does.
        # R29: as a claim obligation a Han numeral raises no finding, so the
        # mismatched extract below is silent too.
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
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C906",
                    "kind": "fact",
                    "claim": "全區已安裝十八萬個智慧水錶。",
                    "extract_or_location": "全區已安裝18,000個智慧水錶。",
                }
            ),
        )

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
        self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )

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
        self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )

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
        self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )

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

    def test_han_plain_count_raises_no_finding(self):
        # R29: a count spelled in Han numerals carries no obligation at all,
        # so an extract that says nothing about it is not a finding.
        for claim in (
            "研究人員揭露三個漏洞。",
            "第一期換表已完成十八個月。",
            "服務公司過去三年掉十一個百分點。",
        ):
            with self.subTest(claim=claim):
                self.assertEqual(
                    [],
                    validate_ledger.evidence_coverage_errors(
                        {
                            "claim_id": "C901",
                            "kind": "fact",
                            "claim": claim,
                            "extract_or_location": "本頁概述產品。",
                        }
                    ),
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

    def test_han_count_against_a_different_value_raises_no_finding(self):
        """R29: the Han-numeral obligation path is deleted, not downgraded."""
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C901",
                    "kind": "fact",
                    "claim": "研究人員揭露三個漏洞。",
                    "extract_or_location": "報告記錄5個漏洞。",
                }
            ),
        )

    def test_han_ordinals_do_not_create_obligations(self):
        # "第三"/"第十八" name a position, not a figure, mirroring the
        # exclusion English fractions and ordinal-units get.
        # R29: as evidence the page may offer the value; as a claim it never
        # becomes an obligation.
        for phrase in ("第三", "第十八", "第一級"):
            with self.subTest(phrase=phrase):
                self.assertEqual([], validate_ledger.quantitative_obligations(phrase))
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
                self.assertEqual([], validate_ledger.quantitative_obligations(phrase))
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
                self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )

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
                self.assertEqual([], validate_ledger.quantitative_obligations(phrase))

    def test_golden_ledgers_still_pass_with_han_numeral_scanning(self):
        for name in ("en", "zh-CN", "zh-HK"):
            ledger = json.loads(
                (
                    ROOT / "tests" / "fixtures" / "golden" / name / "ledger.json"
                ).read_text(encoding="utf-8")
            )
            with self.subTest(ledger=name):
                errors = validate_ledger.validate_references(ledger)
                hard = [item for item in errors if not str(item).startswith("WARNING:")]
                self.assertEqual([], hard, errors)


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


class ResilienceLedgerApiTests(unittest.TestCase):
    """Spec §7.1 / §6.4 / §9 — findings, severities, quantities, claim-input."""

    def test_families_constant_is_exported(self):
        emitted = {item.family for item in self._family_fixture_findings()}
        self.assertEqual(validate_ledger.FAMILIES, emitted)
        self.assertTrue(emitted <= validate_ledger.FAMILIES)

    #: R28: every ledger family the severity table downgrades. The fixture
    #: above emits all of them (the assertion right here pins that), so one
    #: pass over it proves each one warns instead of refusing.
    R28_WARN_FAMILIES = frozenset(
        {
            "ledger/coverage",
            "ledger/excluded-supports",
            "ledger/freshness",
            "ledger/host-conflict",
            "ledger/https",
            "ledger/key-claim",
            "ledger/person",
            "ledger/portfolio",
            "ledger/provenance",
            "ledger/source-family",
            "ledger/source-ids",
            "ledger/synthesis",
            "ledger/triangulation",
            "ledger/undated-reason",
            # R29: lexical/semantic heuristics and ledger shape warn too.
            "ledger/direction",
            "ledger/schema",
            "ledger/status",
        }
    )
    R28_HARD_FAMILIES = frozenset()

    def test_r28_downgraded_families_are_warn(self):
        by_family = {}
        for item in self._family_fixture_findings():
            by_family.setdefault(item.family, []).append(item)
        for family in sorted(self.R28_WARN_FAMILIES):
            with self.subTest(family=family):
                items = by_family.get(family, [])
                self.assertTrue(items, f"{family} is not exercised")
                self.assertEqual(
                    {"warn"}, {item.severity for item in items}
                )
        for family in sorted(self.R28_HARD_FAMILIES):
            with self.subTest(family=family):
                self.assertIn(
                    "hard", {item.severity for item in by_family.get(family, [])}
                )

    def test_r28_reference_is_hard_only_for_an_unfetched_source(self):
        data = valid_quality_ledger()
        data["claims"][0]["source_ids"] = ["S1", "S2", "S99"]
        unfetched = [
            item
            for item in validate_ledger.collect_findings(data)
            if item.family == "ledger/reference"
            and "references unknown source" in item.message
        ]
        self.assertEqual(1, len(unfetched))
        self.assertEqual("hard", unfetched[0].severity)
        others = [
            item
            for item in self._family_fixture_findings()
            if item.family == "ledger/reference"
        ]
        self.assertTrue(others)
        self.assertEqual("warn", {item.severity for item in others}.pop())

    def _family_fixture_findings(self):
        findings = []
        data = valid_quality_ledger()
        data["claims"][0]["claim"] = "Revenue increased by 12%."
        data["claims"][0]["extract_or_location"] = "Revenue decreased by 12%."
        data["claims"][0]["source_evidence"][0]["extract_or_location"] = (
            "Revenue decreased by 12%."
        )
        data["claims"][0]["source_evidence"][1]["extract_or_location"] = (
            "Revenue decreased by 12%."
        )
        findings.extend(validate_ledger.collect_findings(data))
        https = valid_quality_ledger()
        https["sources"][0]["url"] = "http://records.example.org/result"
        findings.extend(validate_ledger.collect_findings(https))
        missing = valid_quality_ledger()
        missing["claims"][0].pop("source_ids")
        findings.extend(validate_ledger.collect_findings(missing))
        extras = valid_quality_ledger()
        extras["claims"][0]["source_ids"] = ["S1", "S2", "S3"]
        extras["sources"].append(
            {
                "source_id": "S3",
                "url": "https://other.example.net/x",
                "publisher": "Other",
                "source_family": "other.example.net",
                "provenance": "secondary_independent",
                "roles": ["independent_analysis"],
                "accountability_basis": "none",
                "published": "2026-07-21",
                "accessed": "2026-07-28",
            }
        )
        findings.extend(validate_ledger.collect_findings(extras))
        unverified = valid_quality_ledger()
        unverified["sources"][1]["provenance"] = "unverified"
        findings.extend(validate_ledger.collect_findings(unverified))
        findings.extend(
            validate_ledger.claim_findings(
                {
                    "claim_id": "C5",
                    "claim": "Revenue increased by 12%.",
                    "kind": "analysis",
                    "importance": "supporting",
                    "source_evidence": [
                        {"source_id": "S2", "extract_or_location": "short"},
                    ],
                    "person_ids": ["P9"],
                },
                valid_quality_ledger(),
            )
        )
        # R28: a claim input is refused for an empty extract, not for a missing
        # conditional field, so that is what now raises ledger/claim-input.
        findings.extend(
            validate_ledger.claim_findings(
                {
                    "claim_id": "C6",
                    "claim": "Revenue increased by 12%.",
                    "kind": "fact",
                    "importance": "supporting",
                    "source_evidence": [
                        {"source_id": "S2", "extract_or_location": ""},
                    ],
                },
                valid_quality_ledger(),
            )
        )
        unknown = valid_quality_ledger()
        unknown["people"] = [
            {
                "person_id": "P1",
                "name": "Alex Doe",
                "aliases": ["Doe"],
            }
        ]
        unknown["claims"][0]["person_ids"] = ["P1"]
        findings.extend(validate_ledger.collect_findings(unknown))
        dropped = fact_claim(claim_id="C9")
        dropped["reason"] = "drop"
        dropped["dropped_at"] = "2026-09-14T00:00:00Z"
        excluded = valid_quality_ledger()
        excluded["excluded_claims"] = [dropped]
        excluded["claims"][0]["supports"] = ["C9"]
        findings.extend(validate_ledger.collect_findings(excluded))
        host = valid_quality_ledger()
        host["sources"][1]["url"] = "https://records.example.org/other"
        host["sources"][1]["source_family"] = "example.org"
        findings.extend(validate_ledger.collect_findings(host))
        schema = validate_ledger.collect_findings({})
        findings.extend(schema)
        coverage = valid_quality_ledger()
        coverage["coverage"][0]["claim_ids"] = ["C2"]
        coverage["claims"].append(fact_claim(status="inference"))
        findings.extend(validate_ledger.collect_findings(coverage))
        derived = ledger_with_fact(
            claim="The vendor recorded a 12.5% failure rate.",
            derived_assertions=[{"expression": "failure rate", "derivation": "x" * 40}],
        )
        findings.extend(validate_ledger.collect_findings(derived))
        status = {
            "claim_id": "C70",
            "kind": "fact",
            "claim": "The defect was patched.",
            "extract_or_location": "The page describes the product.",
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": "The page describes the product."}
            ],
        }
        findings.extend(validate_ledger.collect_findings(ledger_with_fact(**status)))
        fresh = valid_quality_ledger()
        fresh["claims"][0]["time_sensitive"] = True
        fresh["claims"][0]["as_of"] = "2025-01-01"
        findings.extend(validate_ledger.collect_findings(fresh))
        undated = valid_quality_ledger()
        undated["claims"][0]["time_sensitive"] = True
        undated["claims"][0]["as_of"] = "2026-07-28"
        undated["sources"][0]["published"] = None
        undated["sources"][0]["undated_reason"] = "no date shown on the page"
        findings.extend(validate_ledger.collect_findings(undated))
        syn = valid_quality_ledger()
        syn["synthesis"]["central_judgment_claim_ids"] = ["C1", "C9"]
        findings.extend(validate_ledger.collect_findings(syn))
        dup = valid_quality_ledger()
        dup["sources"].append(dict(dup["sources"][0], source_id="S1", url="https://dup.example.org/x"))
        findings.extend(validate_ledger.collect_findings(dup))
        findings.extend(validate_ledger.collect_findings(living_harm_ledger()))
        return findings

    def test_threshold_messages_keep_their_own_family(self):
        data = valid_quality_ledger()
        data["sources"][0]["url"] = "http://records.example.org/result"
        data["claims"][0].pop("source_ids")
        families = {item.family for item in validate_ledger.collect_findings(data)}
        self.assertIn("ledger/https", families)
        self.assertIn("ledger/source-ids", families)
        self.assertNotIn(
            "ledger/quantity",
            {
                item.family
                for item in validate_ledger.collect_findings(data)
                if "https" in item.message or "source_ids" in item.message
            },
        )

    def test_bare_year_is_covered_by_any_date_of_that_year(self):
        """A5: the date-granularity family is gone; the year is simply covered."""
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C80",
                    "kind": "fact",
                    "claim": "事件发生在1918年。",
                    "extract_or_location": "档案记于1918年1月。",
                }
            ),
        )
        findings = validate_ledger.collect_findings(
            ledger_with_fact(
                claim_id="C80",
                claim="事件发生在1918年。",
                extract_or_location="档案记于1918年1月。",
                source_evidence=[
                    {"source_id": "S2", "extract_or_location": "档案记于1918年1月。"}
                ],
            )
        )
        self.assertEqual(
            [], [item for item in findings if item.family == "ledger/quantity"]
        )

    def test_a_dotted_date_in_an_extract_is_a_date_not_a_version(self):
        """A4: 1948.11.24 covers the claim's 1948年11月24日."""
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C81",
                    "kind": "fact",
                    "claim": "日记记于1948年11月24日。",
                    "extract_or_location": "档案编号 1948.11.24 的日记条目。",
                }
            ),
        )

    def test_quantity_remedy_never_names_extracts_as_a_source(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "The vendor recorded 28 incidents.",
                "extract_or_location": "Report dated 2026-07-28.",
            }
        )
        joined = " ".join(errors)
        self.assertNotIn("alx find extracts", joined)
        self.assertTrue(
            "alx find S" in joined or "set field extract_or_location" in joined,
            joined,
        )

    def test_date_fragment_day_is_covered_by_full_date(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "事件发生在12日。",
                    "extract_or_location": "记录写于1936年12月12日。",
                    "source_evidence": [
                        {
                            "source_id": "S16",
                            "extract_or_location": "记录写于1936年12月12日。",
                        }
                    ],
                }
            ),
        )

    def test_count_is_not_covered_by_date_parts(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "调集了12个师。",
                "extract_or_location": "会议开于12月12日。",
                "source_evidence": [
                    {
                        "source_id": "S16",
                        "extract_or_location": "会议开于12月12日。",
                    }
                ],
            }
        )
        self.assertTrue(
            any("is in the claim but not in" in error for error in errors), errors
        )
        self.assertTrue(any("'12' is in the claim" in error for error in errors), errors)

    def test_bare_year_is_not_covered_by_year_month_and_names_both_forms(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C8",
                "kind": "fact",
                "claim": "伤亡发生在1918。",
                "extract_or_location": "档案记于1918年1月。",
                "source_evidence": [
                    {
                        "source_id": "S16",
                        "extract_or_location": "档案记于1918年1月。",
                    }
                ],
            }
        )
        joined = " ".join(errors)
        self.assertIn("'1918' is in the claim but not in S16", joined)

    def test_bare_under_without_numeric_or_legal_carrier_is_not_a_direction(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "The review went under the wire.",
                    "extract_or_location": "The review finished on time.",
                }
            ),
        )

    def test_bare_settled_without_legal_carrier_is_not_a_status(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C900",
                    "kind": "fact",
                    "claim": "The dust settled after the announcement.",
                    "extract_or_location": "The announcement closed the day.",
                }
            ),
        )

    def test_increased_versus_decreased_is_a_warn(self):
        """R29: a direction heuristic is not verbatim fidelity."""
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C900",
                "kind": "fact",
                "claim": "Revenue increased by 12%.",
                "extract_or_location": "Revenue decreased by 12%.",
            }
        )
        self.assertTrue(any("direction" in error.lower() for error in errors), errors)
        self.assertTrue(all(error.startswith("WARNING:") for error in errors), errors)

    def test_unverified_provenance_is_interested_in_portfolio_and_key_claim(self):
        data = valid_quality_ledger()
        data["sources"][1]["provenance"] = "unverified"
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any("portfolio has no independent source" in error.lower() for error in errors),
            errors,
        )
        self.assertTrue(
            any("unverified" in error.lower() or "interested" in error.lower() for error in errors),
            errors,
        )

    def test_missing_source_ids_are_derived_as_a_warning(self):
        data = valid_quality_ledger()
        data["claims"][0].pop("source_ids")
        errors = validate_ledger.validate_references(data)
        warns = [error for error in errors if error.startswith("WARNING:")]
        self.assertTrue(any("source_ids" in error for error in warns), errors)

    def test_extras_on_source_ids_are_one_error_per_claim(self):
        data = valid_quality_ledger()
        data["sources"].append(
            {
                "source_id": "S3",
                "url": "https://other.example.net/x",
                "publisher": "Other",
                "source_family": "other.example.net",
                "provenance": "secondary_independent",
                "roles": ["independent_analysis"],
                "accountability_basis": "none",
                "published": "2026-07-21",
                "accessed": "2026-07-28",
            }
        )
        data["claims"][0]["source_ids"] = ["S1", "S2", "S3"]
        errors = [
            error
            for error in validate_ledger.validate_references(data)
            if "C1" in error and "extra" in error.lower()
        ]
        self.assertEqual(1, len(errors), errors)

    def test_http_source_url_is_hard_but_http_alias_is_allowed(self):
        data = valid_quality_ledger()
        data["sources"][0]["url"] = "http://records.example.org/result"
        data["sources"][0]["aliases"] = ["http://records.example.org/old"]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("https" in error.lower() and "S1" in error for error in errors), errors)
        data["sources"][0]["url"] = "https://records.example.org/result"
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("https" in error.lower() and "alias" in error.lower() for error in errors),
            errors,
        )

    def test_cjk_derivation_minimum_is_20_with_threshold_in_message(self):
        claim = {
            "claim_id": "C900",
            "kind": "fact",
            "claim": "营收增长12%。",
            "extract_or_location": "页面描述了产品。",
            "derived_assertions": [
                {"expression": "12%", "derivation": "推算说明偏短"},
            ],
        }
        errors = validate_ledger.derived_assertion_errors(claim)
        joined = " ".join(errors)
        self.assertIn("20", joined)
        self.assertRegex(joined, r"actual[: ]+\d+")

    def test_undated_reason_failure_prints_accepted_phrasings(self):
        data = valid_quality_ledger()
        data["claims"][0]["time_sensitive"] = True
        data["claims"][0]["as_of"] = "2026-07-28"
        data["sources"][0]["published"] = None
        data["sources"][0]["undated_reason"] = "no date shown on the page"
        errors = validate_ledger.validate_references(data)
        joined = " ".join(errors)
        self.assertIn("undated_reason", joined)
        self.assertTrue(
            "continuously" in joined.lower() or "持续更新" in joined,
            joined,
        )

    def test_host_conflicts_include_provenance_per_id(self):
        data = valid_quality_ledger()
        data["sources"][1]["url"] = "https://records.example.org/other"
        data["sources"][1]["source_family"] = "example.org"
        data["sources"][1]["provenance"] = "primary_independent"
        data["sources"][0]["family_justification"] = ""
        data["sources"][1]["family_justification"] = ""
        errors = validate_ledger.validate_references(data)
        host_errors = [error for error in errors if "host" in error.lower()]
        self.assertTrue(host_errors, errors)
        joined = " ".join(host_errors)
        self.assertIn("S1", joined)
        self.assertIn("S2", joined)
        self.assertIn("primary_interested", joined)
        self.assertIn("primary_independent", joined)

    def test_excluded_claims_are_not_validated_and_supports_to_them_are_hard(self):
        data = valid_quality_ledger()
        dropped = fact_claim(claim_id="C9", claim="Dropped 999 units.")
        dropped["extract_or_location"] = "no figure here"
        dropped["source_evidence"][0]["extract_or_location"] = "no figure here"
        dropped["reason"] = "Class F drop"
        dropped["dropped_at"] = "2026-09-14T00:00:00Z"
        data["excluded_claims"] = [dropped]
        data["claims"][0]["supports"] = ["C9"]
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("C9:" in error and "is in the claim" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("excluded" in error.lower() and "C9" in error for error in errors),
            errors,
        )

    def test_excuses_nothing_and_coverage_linkage_are_warnings(self):
        data = ledger_with_fact(
            claim="The vendor recorded a 12.5% failure rate.",
            derived_assertions=[
                {
                    "expression": "failure rate",
                    "derivation": "x" * 40,
                }
            ],
        )
        data["coverage"][0]["status"] = "supported"
        data["coverage"][0]["claim_ids"] = ["C2"]
        data["claims"][1]["status"] = "inference"
        errors = validate_ledger.validate_references(data)
        excuses = [error for error in errors if "excuses nothing" in error]
        linkage = [
            error
            for error in errors
            if "supported but references no supported claim" in error
        ]
        self.assertTrue(excuses, errors)
        self.assertTrue(all(error.startswith("WARNING:") for error in excuses), excuses)
        self.assertTrue(linkage, errors)
        self.assertTrue(all(error.startswith("WARNING:") for error in linkage), linkage)

    def test_collect_findings_and_grouped_main(self):
        import io
        import tempfile
        from contextlib import redirect_stderr, redirect_stdout
        from pathlib import Path

        data = valid_quality_ledger()
        data["claims"][0]["claim"] = "Revenue increased by 12%."
        data["claims"][0]["extract_or_location"] = "Revenue decreased by 12%."
        data["claims"][0]["source_evidence"][0]["extract_or_location"] = (
            "Revenue decreased by 12%."
        )
        data["claims"][0]["source_evidence"][1]["extract_or_location"] = (
            "Revenue decreased by 12%."
        )
        findings = validate_ledger.collect_findings(data)
        self.assertTrue(findings)
        self.assertTrue(all(hasattr(item, "family") for item in findings))
        self.assertTrue(any(item.family in validate_ledger.FAMILIES for item in findings))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = validate_ledger.main([str(path)])
        # R29: a direction heuristic warns, so the grouped output carries it
        # in the WARN tier and the command no longer refuses.
        self.assertEqual(0, code)
        self.assertIn("=== HARD", err.getvalue())
        self.assertIn("=== WARN", err.getvalue())

    def test_expanded_key_claim_input_validates_against_the_ledger_schema(self):
        """Pinned contract: claim-input -> full v4 claim (spec §6.4, §9)."""
        data = valid_quality_ledger()
        item = {
            "claim_id": "C7",
            "claim": "The registry logged 4,000 documents in March 2026.",
            "kind": "fact",
            "importance": "key",
            "decision_relevance": "Sets the scale of the registry backlog.",
            "what_would_change": "A corrected registry export.",
            "source_evidence": [
                {
                    "source_id": "S1",
                    "extract_or_location": (
                        "The registry logged 4,000 documents in March 2026."
                    ),
                },
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "The registry logged 4,000 documents in March 2026."
                    ),
                },
            ],
        }
        input_schema = json.loads(
            (ROOT / "references" / "claim-input.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual([], validate_ledger.validate_schema(item, input_schema))
        expanded = validate_ledger.expand_claim_input(item, data, cache_meta={})
        schema = json.loads(
            validate_ledger.DEFAULT_SCHEMA.read_text(encoding="utf-8")
        )
        claim_schema = dict(schema["$defs"]["claim"], **{"$defs": schema["$defs"]})
        self.assertEqual([], validate_ledger.validate_schema(expanded, claim_schema))

    def test_expand_claim_input_drops_the_report_paragraph_binding(self):
        data = valid_quality_ledger()
        item = {
            "claim_id": "C8",
            "claim": "Revenue increased by 12%.",
            "kind": "fact",
            "importance": "supporting",
            "report_paragraph": 4,
            "source_evidence": [
                {
                    "source_id": "S2",
                    "extract_or_location": "Revenue increased by 12% last year.",
                },
            ],
        }
        expanded = validate_ledger.expand_claim_input(item, data, cache_meta={})
        self.assertNotIn("report_paragraph", expanded)

    def test_expand_claim_input_and_claim_findings_do_not_short_circuit(self):
        data = valid_quality_ledger()
        item = {
            "claim_id": "C5",
            "claim": "Revenue increased by 12%.",
            "kind": "analysis",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": "short"},
            ],
            "person_ids": ["P9"],
        }
        expanded = validate_ledger.expand_claim_input(
            item, data, cache_meta={"S2": {"fetched_at": "2026-07-28"}}
        )
        self.assertEqual(["S2"], expanded["source_ids"])
        self.assertTrue(expanded["include_in_report"])
        self.assertEqual([], expanded["report_excerpts"])
        self.assertEqual("2026-07-28", expanded["verified_at"])
        # Pinned contract: claim-input -> full v4 claim. The expansion owns the
        # ledger-schema defaults, so `alx` never has to fill them itself.
        self.assertEqual("supported", expanded["status"])
        self.assertEqual("medium", expanded["confidence"])
        self.assertTrue((expanded.get("triangulation") or {}).get("rationale"))
        findings = validate_ledger.claim_findings(item, data)
        families = {item.family for item in findings}
        self.assertGreaterEqual(len(findings), 2)
        # B1 restatement of 01eb2db/e7e1258: analysis without reasoning is
        # accepted (no ledger/claim-input) and prints ledger/reference WARN.
        self.assertNotIn("ledger/claim-input", families)
        self.assertIn("ledger/reference", families)
        self.assertTrue(
            any("an analysis must record its reasoning" in item.message for item in findings),
            findings,
        )
        self.assertIn("ledger/extract-length", families)
        self.assertIn("ledger/person", families)

    def test_person_unknown_status_raises_no_person_finding(self):
        """R25 restatement: a registered person with no living_status field
        raises no ledger/person finding.
        """
        data = valid_quality_ledger()
        data["people"] = [
            {
                "person_id": "P1",
                "name": "Alex Doe",
                "aliases": ["Doe"],
            }
        ]
        data["claims"][0]["person_ids"] = ["P1"]
        findings = validate_ledger.claim_findings(data["claims"][0], data)
        self.assertEqual(
            [], [item for item in findings if item.family == "ledger/person"]
        )

    def test_schema_accepts_aliases_excluded_claims_and_tooling(self):
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        ledger = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        ledger["sources"][0]["aliases"] = ["https://example.com/old"]
        ledger["excluded_claims"] = [
            {
                "claim_id": "C99",
                "reason": "dropped",
                "dropped_at": "2026-09-14T00:00:00Z",
            }
        ]
        ledger["tooling"] = {"alx_version": "0", "state_path": ".alx/state.json"}
        self.assertEqual([], validate_ledger.validate_schema(ledger, schema))
        input_schema = json.loads(
            (ROOT / "references" / "claim-input.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("claim_id", input_schema["required"])
        self.assertIn("source_evidence", input_schema["required"])


class HanNumeralEvidenceTests(unittest.TestCase):
    """R29: a Han-numeral spelling on the page covers the claim's digits."""

    def test_an_ordinal_and_an_anniversary_offer_their_value(self):
        self.assertIn("n:13", validate_ledger.quantitative_evidence("本日为西安蒙难第十三年纪念日"))
        self.assertIn("n:13", validate_ledger.quantitative_evidence("十三周年"))

    def test_a_digit_claim_is_covered_by_the_han_spelling(self):
        self.assertEqual(
            [],
            validate_ledger.evidence_coverage_errors(
                {
                    "claim_id": "C28",
                    "kind": "fact",
                    "claim": "1949年12月12日（西安蒙难13周年）的日记。",
                    "extract_or_location": "1949年12月12日：本日为西安蒙难第十三年纪念日。",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()


EXTRACT = "The tariff rose to 12 percent in 2026."


def _cache_result(text):
    return source_fidelity.FetchResult(
        status="ok",
        reason_class="",
        reason="",
        text=text,
        charset="utf-8",
        url="https://example.org/p",
        final_url="https://example.org/p",
        aliases=[],
        http_status=200,
        title="Tariffs",
        published=None,
        text_sha256="",
    )


def _probe_ledger():
    return {
        "schema_version": 4,
        "sources": [{"source_id": "S1", "url": "https://example.org/p"}],
        "claims": [
            {
                "claim_id": "C1",
                "source_ids": ["S1"],
                "source_evidence": [
                    {"source_id": "S1", "extract_or_location": EXTRACT}
                ],
            }
        ],
    }


class OfflineContextChangeTests(unittest.TestCase):
    def test_collect_findings_reports_context_change_from_the_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            source_fidelity.write_cache(
                cache,
                "S1",
                _cache_result(
                    f"Background as researched. {EXTRACT} A neutral closing line."
                ),
            )
            source_fidelity.record_probe_contexts(
                cache, "S1", "C1", source_fidelity.probe_strings(EXTRACT)
            )
            source_fidelity.write_cache(
                cache,
                "S1",
                _cache_result(
                    f"更正: the earlier framing was withdrawn. {EXTRACT} "
                    "A rewritten closing line."
                ),
            )
            findings = validate_ledger.collect_findings(
                _probe_ledger(), cache_dir=cache
            )
            families = [item.family for item in findings]
            self.assertIn("fidelity/context-changed", families)
            self.assertNotIn("fidelity/mismatch", families)


class SchemaRemedyTests(unittest.TestCase):
    """J2: a schema finding's remedy names the field the schema error named."""

    def _schema_findings(self, ledger):
        return [
            item
            for item in validate_ledger.collect_findings(ledger)
            if item.family == "ledger/schema"
        ]

    def _fix_for(self, ledger, location, needle=""):
        for item in self._schema_findings(ledger):
            if item.message.startswith(f"{location}:") and needle in item.message:
                return item.fix
        self.fail(f"no schema finding for {location} {needle}")

    def test_short_claim_rationale_points_at_that_claim_path(self):
        ledger = living_harm_ledger()
        ledger["claims"][-1]["triangulation"]["rationale"] = ""
        path = "claims.1.triangulation.rationale"
        fix = self._fix_for(ledger, path)
        self.assertEqual(
            f"set field {path} in claims/*.json, then alx claim add claims/*.json",
            fix,
        )
        self.assertNotIn("schema_version", fix)

    def test_bad_top_level_field_points_at_that_field(self):
        ledger = living_harm_ledger()
        ledger.pop("subject", None)
        self.assertEqual(
            "set field subject in ledger.json",
            self._fix_for(ledger, "<root>", "subject"),
        )

    def test_empty_top_level_arrays_warn_with_schema_remedy(self):
        ledger = {
            "schema_version": 4,
            "subject": "X",
            "research_question": "Y",
            "brief": {},
            "people": [],
            "report_date": "2026-07-28",
            "coverage": [],
            "sources": [],
            "claims": [],
            "synthesis": {},
            "unresolved_questions": [],
        }
        findings = self._schema_findings(ledger)
        self.assertTrue(findings)
        self.assertEqual({"warn"}, {item.severity for item in findings})
        printed = validate_ledger.render_grouped(findings)
        self.assertIn("[] should be non-empty", printed)
        messages = " ".join(item.message for item in findings)
        self.assertIn("sources", messages)
        self.assertIn("claims", messages)
        self.assertNotIn("brief", messages)
        self.assertNotIn("coverage", messages)
        self.assertEqual(
            "set field sources in ledger.json",
            self._fix_for(ledger, "sources"),
        )

    def test_no_finding_names_a_field_its_message_did_not(self):
        ledger = living_harm_ledger()
        ledger["claims"][-1]["triangulation"]["rationale"] = ""
        for item in self._schema_findings(ledger):
            location = item.message.split(":", 1)[0]
            named = re.match(r"^set field (\S+) ", item.fix)
            with self.subTest(message=item.message):
                self.assertIsNotNone(named, item.fix)
                field = named.group(1)
                self.assertTrue(
                    field in item.message
                    or (location != "<root>" and field.startswith(f"{location}.")),
                    item.fix,
                )


VERBATIM_CJK = (
    "他在日记中将共产党的优点概括为七大方面：“一,组织严密；二,纪律严厉；"
    "三,精神紧张；四,手段彻底；五,军政公开......六,办事方法......"
    "七,组织内容......”.从日记中可以看出"
)


class ExtractLengthVerbatimTests(unittest.TestCase):
    @staticmethod
    def _claim(extract):
        return {
            "claim_id": "C21",
            "source_evidence": [
                {"source_id": "S11", "extract_or_location": extract}
            ],
        }

    def test_verbatim_window_with_in_source_ellipses_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            source_fidelity.write_cache(
                cache, "S11", _cache_result(f"背景。{VERBATIM_CJK}，反思与改革。")
            )
            self.assertEqual(
                [],
                validate_ledger._extract_length_findings(
                    self._claim(VERBATIM_CJK), cache_dir=cache
                ),
            )

    def test_short_piece_after_author_ellipsis_is_never_flagged(self):
        # R13: pieces carry no length floor; only the whole extract warns.
        self.assertEqual(
            [],
            validate_ledger._extract_length_findings(
                self._claim("A genuine quoted observation … short")
            ),
        )

    def test_short_whole_extract_is_a_warn_not_a_hard_finding(self):
        findings = validate_ledger._extract_length_findings(self._claim("short"))
        self.assertEqual(["ledger/extract-length"], [i.family for i in findings])
        self.assertEqual("warn", findings[0].severity)
        self.assertEqual("A", findings[0].klass)
        self.assertIn("threshold 20", findings[0].message)
        self.assertIn("length 5", findings[0].message)
        self.assertEqual("extend the quote in claims/<file>", findings[0].fix)

    def test_twelve_character_cjk_extract_carries_no_warn(self):
        self.assertEqual(
            [], validate_ledger._extract_length_findings(self._claim("一二三四五六七八九十十一"))
        )
        short = validate_ledger._extract_length_findings(self._claim("一二三四五"))
        self.assertEqual(["ledger/extract-length"], [i.family for i in short])
        self.assertIn("threshold 10", short[0].message)

class ClaimRemedyTests(unittest.TestCase):
    def _fixes(self, data, needle):
        return [
            item.fix
            for item in validate_ledger.collect_findings(data)
            if needle in item.message
        ]

    def test_unregistered_person_remedy_is_the_ledger_merge(self):
        """R25 restatement of test_unlinked_person_remedy_is_the_mechanical_link.

        The auto-link is silent now; the only person finding left is an id
        that names nobody in `ledger.people`.
        """
        data = valid_quality_ledger()
        data["claims"][0]["person_ids"] = ["P9"]
        self.assertEqual(
            ["set people in a patch file, then alx ledger merge <patch>"],
            self._fixes(data, "not in ledger.people"),
        )

    def test_two_extracts_from_one_source_raise_no_reference_finding(self):
        # R22 restatement of test_duplicate_evidence_remedy_names_source_
        # evidence: the finding it asked for a remedy for no longer exists.
        data = valid_quality_ledger()
        data["claims"][0]["source_evidence"] = [
            {"source_id": "S1", "extract_or_location": "The registry records it."},
            {"source_id": "S1", "extract_or_location": "A second passage."},
        ]
        self.assertEqual([], self._fixes(data, "source_evidence for S1"))

    def test_month_day_extract_remedy_names_the_find(self):
        """R29 restatement of test_month_day_extract_remedy_asks_for_the_year.

        The year-fragment hint is gone: the remedy is find, then paste or reword.
        """
        extract = "登記簿は12月10日に決定を記録した。"
        data = ledger_with_fact(
            claim="The registry recorded the decision on 1936-12-10.",
            extract_or_location=extract,
            source_evidence=[{"source_id": "S2", "extract_or_location": extract}],
        )
        self.assertEqual(
            [
                "alx find S2 1936-12-10 — paste that window into "
                "extract_or_location and alx claim add, or reword the claim"
            ],
            self._fixes(data, "'1936-12-10' is in the claim"),
        )


class DateFormResilienceTests(unittest.TestCase):
    """R29/B2: the forms a Chinese source actually writes a date in."""

    def forms(self, text):
        return sorted(
            form for _, claim_forms in validate_ledger.quantitative_obligations(text)
            for form in claim_forms
        )

    def test_a_cjk_day_range_yields_its_two_end_dates(self):
        self.assertEqual(
            ["d:1931-09-18", "d:1931-09-20"], self.forms("1931年9月18–20日在南昌")
        )

    def test_a_day_range_never_leaves_a_glued_token(self):
        for text in ("9月18—20日", "9月18-20日"):
            with self.subTest(text=text):
                self.assertEqual(["d:*-09-18", "d:*-09-20"], self.forms(text))
        self.assertEqual(["d:*-*-18", "d:*-*-20"], self.forms("18–20日"))

    def test_a_dotted_date_is_a_date_not_a_version(self):
        self.assertEqual(["d:1948-11-24"], self.forms("1948.11.24发布"))

    def test_an_unpadded_iso_date_is_the_same_day_as_the_padded_one(self):
        self.assertEqual(["d:1949-12-01"], self.forms("(1949-12-1)"))
        self.assertEqual(["d:1950-01-10"], self.forms("(1950-1-10)"))


class PageLevelCoverageTests(unittest.TestCase):
    """R29/B1: the cited source's cached page covers a figure the pasted
    extract omits; a figure on neither stays hard."""

    def cache(self, directory, text):
        Path(directory, "S2.txt").write_text(text, encoding="utf-8")
        Path(directory, "S2.meta.json").write_text(
            json.dumps({"probe_contexts": {}}), encoding="utf-8"
        )
        return directory

    def claim(self, claim_text, extract):
        return {
            "claim_id": "C90",
            "claim": claim_text,
            "kind": "fact",
            "importance": "supporting",
            "source_ids": ["S2"],
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": extract}
            ],
        }

    def findings(self, claim_text, extract, page):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = self.cache(directory, page) if page is not None else None
            return [
                item
                for item in validate_ledger.claim_findings(
                    self.claim(claim_text, extract),
                    valid_quality_ledger(),
                    cache_dir=cache_dir,
                )
                if item.family == "ledger/quantity"
            ]

    def test_a_range_is_covered_by_the_two_dates_on_the_page(self):
        """C13 in miniature."""
        self.assertEqual(
            [],
            self.findings(
                "研究者据蒋1931年9月18–20日的行止记录推断。",
                "从上述引证蒋氏日记分析,可以得出一个重要结论。",
                "1931年9月18日在南昌,9月19日,9月20日在舰上。",
            ),
        )

    def test_a_day_extract_is_covered_when_the_page_states_the_month(self):
        """C19 in miniature."""
        self.assertEqual(
            [],
            self.findings(
                "12月13日日记表白生而辱不如死而荣。",
                "他在13日的日记中表白生而辱不如死而荣。",
                "12月的日记记载了当天的行程与会见安排。",
            ),
        )

    def test_a_figure_on_neither_the_extract_nor_the_page_stays_hard(self):
        item = self.findings(
            "1945年10月毛泽东回延安当天蒋在日记中评价毛。",
            "杨天石：这个错误,最大的误判应该是这一次。",
            "杨天石谈蒋介石日记的史料价值。",
        )[0]
        self.assertEqual("warn", item.severity)
        self.assertEqual("", item.remove)
        self.assertNotIn("Remove:", item.message)
        self.assertEqual(
            "C90: '1945年10月' is in the claim but not in S2 (extracts or cached "
            "page). Fix: alx find S2 1945年10月 — paste that window into "
            "extract_or_location and alx claim add, or reword the claim",
            item.message,
        )

    def test_without_a_cache_only_the_extract_covers(self):
        self.assertTrue(
            self.findings(
                "12月13日日记表白生而辱不如死而荣。",
                "他在13日的日记中表白生而辱不如死而荣。",
                None,
            )
        )


class R29SeverityTests(unittest.TestCase):
    """R29/A1-A2: the downgraded families and the deleted Han-numeral path."""

    def test_the_three_downgraded_families_carry_no_remove_remedy(self):
        for family in sorted(validate_ledger.WARN_FAMILIES):
            with self.subTest(family=family):
                item = validate_ledger._f(
                    family, "C1: message", remove="alx claim drop C1 --apply"
                )
                self.assertEqual("warn", item.severity)
                self.assertEqual("", item.remove)

    def test_a_schema_defect_never_blocks(self):
        findings = validate_ledger.collect_findings({})
        schema = [item for item in findings if item.family == "ledger/schema"]
        self.assertTrue(schema)
        self.assertEqual({"warn"}, {item.severity for item in schema})
        self.assertEqual([], [item for item in findings if item.severity == "hard"])

    def test_a_han_numeral_quantity_raises_nothing_while_a_digit_stays_hard(self):
        han = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C1",
                "kind": "fact",
                "claim": "三位作者共同署名。",
                "extract_or_location": "本页概述产品。",
            }
        )
        self.assertEqual([], han)
        digits = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C1",
                "kind": "fact",
                "claim": "3位作者共同署名。",
                "extract_or_location": "本页概述产品。",
            }
        )
        self.assertTrue(digits)
        self.assertTrue(all(error.startswith("WARNING:") for error in digits), digits)


class NotesShapeFindingsTests(unittest.TestCase):
    """R35.14: merge/check warn only where a consumer reads a notes field."""

    def ledger(self):
        data = valid_quality_ledger()
        data["coverage"][0]["status"] = "done"
        data["synthesis"]["decisions_or_takeaways"] = ["a takeaway"]
        data["brief"] = {"editorial_mode": "x"}
        data["synthesis"]["outcome"] = "y"
        data["people"] = "ignored"
        data["unresolved_questions"] = "ignored"
        return data

    def test_notes_shape_findings_warns_coverage_status_and_string_takeaways(self):
        data = self.ledger()
        helper = validate_ledger.notes_shape_findings(data)
        collected = validate_ledger.collect_findings(data)
        status = (
            "coverage[0].status 'done' is not one of "
            "unstarted|in_progress|supported|disputed|gap — stored as given; "
            "check tracks coverage only for supported|disputed|gap"
        )
        takeaways = (
            "synthesis.decisions_or_takeaways[0] is a str; check links it to "
            "claims only through an object with rationale_claim_ids — stored as given"
        )
        by_message = {item.message: item for item in helper}
        self.assertIn(status, by_message)
        self.assertIn(takeaways, by_message)
        self.assertEqual("ledger/coverage", by_message[status].family)
        self.assertEqual("ledger/synthesis", by_message[takeaways].family)
        self.assertEqual("warn", by_message[status].severity)
        self.assertEqual("warn", by_message[takeaways].severity)
        silent = ("editorial_mode", "outcome", "people", "unresolved_questions")
        for item in helper:
            for needle in silent:
                self.assertNotIn(needle, item.message)
        collected_messages = {item.message: item for item in collected}
        self.assertIn(status, collected_messages)
        self.assertIn(takeaways, collected_messages)
        self.assertEqual("ledger/coverage", collected_messages[status].family)
        self.assertEqual("ledger/synthesis", collected_messages[takeaways].family)
        self.assertEqual("warn", collected_messages[status].severity)
        self.assertEqual("warn", collected_messages[takeaways].severity)

