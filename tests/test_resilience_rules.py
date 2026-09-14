"""Resilience rulings R14/R15 and R17, R20-R24.

Every rule here loosens or re-aims a gate that looped a Chinese run: a source
that states the year once and then writes bare month-day dates (R14), a claim
naming a registered person without the person_id (R15), a negation leaking
across an ASCII-punctuated sentence (R17), person messages that never named the
vocabulary they demanded (R20), a year cut off before 年 (R21), two passages
quoted from one page (R22), an untested counterevidence claim (R23) and a local
as_of one day ahead of a UTC verified_at (R24).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import alx
from tests.test_alx import CLAIM_ONE, AlxTestCase
from tests.test_validate_ledger import valid_quality_ledger, validate_ledger

EXTRACT = "12月10日的日记记载了当天的行程与会见安排，并注明随行人员。"
DAY_EXTRACT = "10日的日记记载了当天的行程与会见安排，并注明随行人员。"


def dated_claim(extract=EXTRACT):
    return {
        "claim_id": "C50",
        "claim": "1936年12月10日的日记记载了当天的行程与会见安排。",
        "kind": "fact",
        "importance": "supporting",
        "source_evidence": [{"source_id": "S2", "extract_or_location": extract}],
    }


def cache(directory, page_text):
    Path(directory, "S2.txt").write_text(page_text, encoding="utf-8")
    Path(directory, "S2.meta.json").write_text(
        json.dumps({"fetched_at": "2026-07-28T00:00:00Z", "probe_contexts": {}}),
        encoding="utf-8",
    )
    return directory


def quantity_findings(claim, ledger, cache_dir=None):
    return [
        item
        for item in validate_ledger.claim_findings(claim, ledger, cache_dir=cache_dir)
        if item.family == "ledger/quantity"
    ]


class DateYearCoverageTests(unittest.TestCase):
    def test_year_stated_once_in_the_page_covers_a_month_day_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "1936年12月，日记如下。" + EXTRACT)
            self.assertEqual(
                [], quantity_findings(dated_claim(), valid_quality_ledger(), directory)
            )

    def test_year_stated_once_also_covers_a_bare_day_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "1936年12月，日记如下。" + DAY_EXTRACT)
            self.assertEqual(
                [],
                quantity_findings(
                    dated_claim(DAY_EXTRACT), valid_quality_ledger(), directory
                ),
            )

    def test_page_without_the_year_stays_hard(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "民国年间，日记如下。" + EXTRACT)
            findings = quantity_findings(
                dated_claim(), valid_quality_ledger(), directory
            )
            self.assertTrue(findings)
            self.assertIn("1936-12-10", findings[0].message)

    def test_without_a_cache_the_rule_is_unchanged(self):
        findings = quantity_findings(dated_claim(), valid_quality_ledger())
        self.assertTrue(findings)
        self.assertIn("1936-12-10", findings[0].message)


def person_ledger(living_status):
    data = valid_quality_ledger()
    data["people"] = [
        {
            "person_id": "P3",
            "name": "Chen Bulei",
            "aliases": ["陈布雷"],
            "living_status": living_status,
            "public_role": "public",
            "relationship": "primary_subject",
        }
    ]
    return data


def named_claim():
    text = "陈布雷起草了这份文稿，档案与日记均记录了整个经过与时间。"
    return {
        "claim_id": "C51",
        "claim": text,
        "kind": "fact",
        "importance": "supporting",
        "source_evidence": [{"source_id": "S2", "extract_or_location": text}],
    }


class PersonAutoLinkTests(unittest.TestCase):
    def test_named_person_is_linked_with_a_warn_not_a_hard_finding(self):
        data = person_ledger("deceased")
        findings = validate_ledger.claim_findings(named_claim(), data)
        warns = [
            item
            for item in findings
            if item.family == "ledger/person" and item.severity == "warn"
        ]
        self.assertTrue(warns)
        self.assertIn("P3", warns[0].message)
        self.assertEqual(
            [],
            [
                item
                for item in findings
                if item.family in {"ledger/person", "ledger/reference"}
                and item.severity != "warn"
            ],
        )
        self.assertEqual(
            ["P3"],
            validate_ledger.expand_claim_input(
                named_claim(), data, cache_meta={}
            )["person_ids"],
        )

    def test_recorded_links_are_kept_and_derivation_is_idempotent(self):
        data = person_ledger("deceased")
        claim = dict(named_claim(), person_ids=["P3"])
        self.assertEqual(
            ["P3"], validate_ledger.derive_person_ids(claim, data["people"])
        )
        self.assertEqual(
            [],
            [
                item
                for item in validate_ledger.claim_findings(claim, data)
                if item.family == "ledger/person"
            ],
        )

    def test_living_person_still_needs_harm_review_after_linking(self):
        data = person_ledger("living")
        findings = validate_ledger.claim_findings(named_claim(), data)
        self.assertTrue(
            [
                item
                for item in findings
                if item.severity != "warn"
                and item.family in {"ledger/person", "ledger/harm"}
            ],
            findings,
        )


class DirectionNegationWindowTests(unittest.TestCase):
    """R17: a negation must not reach across a sentence that ends in ASCII.

    Scraped Chinese pages punctuate with "." and ",". `_is_negated` scanned the
    32 characters before an assertion and stopped only at the CJK full stop and semicolon, so the
    未 in "而未及中国主席,更为不当." denied the 增加 two sentences later and the
    claim's supported increase was reported as unevidenced. The carrier
    comparison then needed the same repair: a 0.75 bigram ratio is unreachable
    for Chinese clauses, so a shared four-character phrase carries the binding.
    """

    CLAIM = "并要求公告列名增加中国主席且置于英国首相之前。"
    EVIDENCE = (
        "此公告由美国总统与英国首相商定,而未及中国主席,更为不当."
        "蒋介石提出要求：公告中必须增加中国主席,而且置于英国首相之前."
    )

    def errors(self, claim, extract):
        return validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C53",
                "kind": "fact",
                "claim": claim,
                "extract_or_location": extract,
            }
        )

    def test_an_earlier_sentence_negation_does_not_deny_the_increase(self):
        self.assertEqual([], self.errors(self.CLAIM, self.EVIDENCE))

    def test_a_negation_in_the_assertion_sentence_still_denies_it(self):
        denied = self.EVIDENCE.replace("必须增加中国主席", "不增加中国主席")
        self.assertTrue(
            any("direction" in error for error in self.errors(self.CLAIM, denied)),
            denied,
        )

    def test_evidence_without_the_direction_is_still_hard(self):
        silent = self.EVIDENCE.replace("必须增加中国主席", "列名中国主席")
        self.assertTrue(
            any("direction" in error for error in self.errors(self.CLAIM, silent)),
            silent,
        )

    def test_a_different_subject_does_not_share_a_carrier_phrase(self):
        self.assertTrue(
            any(
                "direction" in error
                for error in self.errors("产品甲销量上升。", "产品乙销量上升。")
            )
        )


class YearNumberCoverageTests(unittest.TestCase):
    """R21: an extract cut before 年 still states the year as a number."""

    def claim(self, text):
        return {
            "claim_id": "C54",
            "claim": text,
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "资料图：胡佛研究中心,2006年3月31日起公开蒋介石1917"
                    ),
                }
            ],
        }

    def findings(self, text):
        return quantity_findings(self.claim(text), valid_quality_ledger())

    def test_a_year_in_the_claim_is_covered_by_the_bare_number(self):
        self.assertEqual([], self.findings("1917年的日记真迹已公开。"))

    def test_a_year_absent_from_the_extract_still_fails(self):
        findings = self.findings("1931年的日记真迹已公开。")
        self.assertTrue(findings)
        self.assertIn("d:1931", findings[0].message)

    def test_a_number_outside_the_year_range_is_not_a_year(self):
        self.assertFalse(
            validate_ledger._year_number_coverage({"d:0999"}, {"n:999"})
        )


class YearMonthFragmentCoverageTests(unittest.TestCase):
    """R14b: a month-day fragment covers a year-month claim."""

    EXTRACT = "8月2日,会议记录了当天的行程与随行人员安排,并注明时间。"

    def claim(self):
        return {
            "claim_id": "C55",
            "claim": "1945年8月的记录列明了当天的行程。",
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": self.EXTRACT}
            ],
        }

    def test_the_year_on_the_page_covers_the_year_month_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "1945年的会议记录如下。" + self.EXTRACT)
            self.assertEqual(
                [],
                quantity_findings(
                    self.claim(), valid_quality_ledger(), directory
                ),
            )

    def test_a_page_without_the_year_stays_hard(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "民国年间的会议记录如下。" + self.EXTRACT)
            findings = quantity_findings(
                self.claim(), valid_quality_ledger(), directory
            )
            self.assertTrue(findings)
            self.assertIn("d:1945-08", findings[0].message)


class YearInsideTheExtractCoverageTests(unittest.TestCase):
    """R14: the year written inside the extract itself covers a month-day
    fragment, with or without a cache (run 5, C9: content gate had no page)."""

    EXTRACT = "1936年12月,\"西安事變\"爆發前數小時.12月11日,蔣寫張學良形色急遽."

    def claim(self):
        return {
            "claim_id": "C9",
            "claim": "1936年12月11日蒋介石写张学良形色急遽。",
            "kind": "fact",
            "importance": "key",
            "source_ids": ["S2"],
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": self.EXTRACT}
            ],
        }

    def test_year_in_the_extract_covers_the_full_date_without_a_cache(self):
        self.assertEqual(
            [], quantity_findings(self.claim(), valid_quality_ledger(), None)
        )


class EvidenceEntryProbeTests(unittest.TestCase):
    """R22: two passages from one page are evidence, and each is probed."""

    PAGE = "第一段：会议于8月2日召开,记录在案.第二段：随行人员名单另有记载."
    FIRST = "会议于8月2日召开"
    SECOND = "随行人员名单另有记载"
    FABRICATED = "会议决定解散全部随行机构"

    def claim(self, second):
        return {
            "claim_id": "C56",
            "claim": "会议于8月2日召开。",
            "kind": "fact",
            "importance": "supporting",
            "source_evidence": [
                {"source_id": "S2", "extract_or_location": self.FIRST},
                {"source_id": "S2", "extract_or_location": second},
            ],
        }

    def findings(self, second, family):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, self.PAGE)
            return [
                item
                for item in validate_ledger.claim_findings(
                    self.claim(second), valid_quality_ledger(), cache_dir=directory
                )
                if item.family == family
            ]

    def test_two_real_extracts_from_one_source_are_accepted(self):
        self.assertEqual([], self.findings(self.SECOND, "fidelity/mismatch"))

    def test_a_fabricated_second_extract_is_still_caught(self):
        findings = self.findings(self.FABRICATED, "fidelity/mismatch")
        self.assertTrue(findings)
        self.assertIn(self.FABRICATED[:8], findings[0].message)

    def test_the_duplicate_source_evidence_finding_is_gone(self):
        self.assertEqual(
            [],
            [
                item
                for item in validate_ledger.claim_findings(
                    self.claim(self.SECOND), valid_quality_ledger()
                )
                if "duplicate source_evidence" in item.message
            ],
        )


class ProtectedPersonMessageTests(unittest.TestCase):
    """R20: the person messages carry the vocabulary they demand."""

    def findings(self):
        claim = dict(
            named_claim(),
            person_ids=["P3"],
            person_claim_role="subject_assessment",
            person_claim_assessment={"harm": "none", "note": "日记原文转引"},
        )
        return [
            item
            for item in validate_ledger.claim_findings(claim, person_ledger("living"))
            if item.family == "ledger/person" and item.severity == "hard"
        ]

    def test_the_role_message_names_the_person_the_roles_and_the_got_value(self):
        [message] = [
            item.message
            for item in self.findings()
            if "person_claim_role one of" in item.message
        ]
        self.assertIn("P3 Chen Bulei (living_status living)", message)
        self.assertIn(
            "neutral|harmful|sensitive_private_fact|response|resolution", message
        )
        self.assertIn("got 'subject_assessment'", message)

    def test_the_assessment_message_names_the_person_the_shape_and_the_floor(self):
        [message] = [
            item.message
            for item in self.findings()
            if "person_claim_assessment" in item.message
        ]
        self.assertIn("P3 Chen Bulei (living_status living)", message)
        self.assertIn(
            '{"classification": <person_claim_role>, "rationale": >=40 chars}',
            message,
        )
        self.assertIn("got None, 0 chars", message)

    def test_both_messages_stay_hard(self):
        self.assertEqual(2, len(self.findings()))


class ClaimAddNamesTheClaimFileTests(AlxTestCase):
    """R20: a rejected claim's remedy names the file the claim came from."""

    def test_a_rejected_claim_names_its_own_input_file(self):
        self.bootstrap()
        claim = dict(CLAIM_ONE, claim_id="C9", supports=["C99"])
        path = self.write_json("late.json", [claim])
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(1, code, out)
        self.assertIn(str(path), out)
        self.assertNotIn("claims/*.json", out)


class AdversarialTestWarnTests(unittest.TestCase):
    """R23: untested counterevidence is thin synthesis, not fabrication."""

    def findings(self, adversarial_tests):
        data = valid_quality_ledger()
        data["synthesis"]["counterevidence_claim_ids"] = ["C1"]
        data["synthesis"]["adversarial_tests"] = adversarial_tests
        return [
            item
            for item in validate_ledger.collect_findings(data)
            if "adversarial hypothesis" in item.message
        ]

    def test_an_untested_counterevidence_claim_only_warns(self):
        [item] = self.findings([])
        self.assertEqual("warn", item.severity)
        self.assertEqual("A", item.klass)
        self.assertEqual(["C1"], item.ids)
        self.assertIn("threshold: 1 adversarial_tests entry naming it", item.message)

    def test_the_fix_is_the_synthesis_merge_and_alx_accepts_it(self):
        [item] = self.findings([])
        self.assertEqual(
            "set field synthesis.adversarial_tests, "
            "then alx ledger merge synthesis",
            item.fix,
        )
        self.assertTrue(alx.valid_remedy(item.fix))
        self.assertEqual(item.fix, alx.adopt([item])[0].fix)

    def test_a_tested_counterevidence_claim_raises_nothing(self):
        self.assertEqual(
            [],
            self.findings(
                [
                    {
                        "hypothesis": "The result is a fixture artifact.",
                        "test": "Compare against an independent implementation.",
                        "claim_ids": ["C1"],
                        "outcome": "rejected",
                        "result": "The independent implementation agreed.",
                        "effect_on_conclusion": "Unchanged.",
                    }
                ]
            ),
        )


class AsOfDriftTests(unittest.TestCase):
    """R24: verified_at is the UTC fetch date; as_of is often the local one."""

    def findings(self, as_of):
        data = valid_quality_ledger()
        data["report_date"] = "2026-08-05"
        data["claims"][0]["verified_at"] = "2026-07-28"
        data["claims"][0]["as_of"] = as_of
        return [
            item
            for item in validate_ledger.collect_findings(data)
            if "after verified_at" in item.message
        ]

    def test_one_day_of_drift_is_not_a_finding(self):
        self.assertEqual([], self.findings("2026-07-29"))

    def test_the_same_day_is_not_a_finding(self):
        self.assertEqual([], self.findings("2026-07-28"))

    def test_two_days_stay_hard_and_name_as_of(self):
        [item] = self.findings("2026-07-30")
        self.assertEqual("hard", item.severity)
        self.assertIn("2 days after verified_at 2026-07-28", item.message)
        self.assertIn("threshold 1 day", item.message)
        self.assertEqual(
            "set field as_of in claims/*.json, then alx claim add claims/*.json",
            alx.adopt([item])[0].fix,
        )


if __name__ == "__main__":
    unittest.main()
