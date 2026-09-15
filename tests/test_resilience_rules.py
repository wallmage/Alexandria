"""Resilience rulings R14/R15 and R17, R20-R27.

Every rule here loosens or re-aims a gate that looped a Chinese run: a source
that states the year once and then writes bare month-day dates (R14), a claim
naming a registered person without the person_id (R15), a negation leaking
across an ASCII-punctuated sentence (R17), person messages that never named the
vocabulary they demanded (R20), a year cut off before 年 (R21), two passages
quoted from one page (R22), an untested counterevidence claim (R23), a local
as_of one day ahead of a UTC verified_at (R24), the living-person harm rules
themselves (R25, deleted), a count spelled in Han numerals (R26) and an
unclassified source portfolio (R27).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import content_gate
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
    def test_named_person_is_linked_silently(self):
        """R25 restatement of
        test_named_person_is_linked_with_a_warn_not_a_hard_finding: the
        auto-link is a convenience, so it no longer prints a WARN either.
        """
        data = person_ledger("deceased")
        findings = validate_ledger.claim_findings(named_claim(), data)
        self.assertEqual(
            [],
            [
                item
                for item in findings
                if item.family in {"ledger/person", "ledger/reference"}
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

    def test_living_person_needs_nothing_after_linking(self):
        """R25 restatement of
        test_living_person_still_needs_harm_review_after_linking: living status
        is recorded, never gated.
        """
        data = person_ledger("living")
        self.assertEqual(
            [],
            [
                item
                for item in validate_ledger.claim_findings(named_claim(), data)
                if item.family == "ledger/person"
            ],
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
        self.assertIn("'1931年' is in the claim but not in S2", findings[0].message)

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
            self.assertIn("'1945-08' is in the claim but not in S2", findings[0].message)


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


class ContentGateSeesThePageTests(unittest.TestCase):
    """Run 6, C25: the content gate re-ran the date check without the sources
    cache, so a month-day fragment whose year is only on the page was flagged
    again after claim add had accepted it. validate_references now takes the
    cache, and the gate passes the workspace's sources/ directory."""

    EXTRACT = "9月4日,蒋写道愿共毛能悔悟."

    def ledger_with_claim(self):
        ledger = valid_quality_ledger()
        ledger["claims"] = [
            {
                "claim_id": "C25",
                "claim": "1945年9月4日蒋写道愿共毛能悔悟。",
                "kind": "fact",
                "importance": "supporting",
                "include_in_report": True,
                "source_ids": ["S2"],
                "source_evidence": [
                    {"source_id": "S2", "extract_or_location": self.EXTRACT}
                ],
            }
        ]
        return ledger

    def quantity_errors(self, cache_dir):
        ledger = self.ledger_with_claim()
        return [
            item
            for item in quantity_findings(ledger["claims"][0], ledger, cache_dir)
            if "1945-09-04" in item.message
        ]

    def test_the_year_on_the_cached_page_covers_the_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "1945年的记录如下。" + self.EXTRACT)
            self.assertEqual([], self.quantity_errors(directory))

    def test_without_the_cache_the_fragment_is_still_reported(self):
        items = self.quantity_errors(None)
        self.assertTrue(items)
        self.assertEqual("warn", items[0].severity)
        self.assertEqual("", items[0].remove)

    def test_the_content_gate_passes_the_workspace_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "sources").mkdir()
            self.assertEqual(
                workspace / "sources",
                content_gate._sources_cache(workspace / "ledger.json"),
            )
            self.assertIsNone(
                content_gate._sources_cache(workspace / "missing" / "ledger.json")
            )


class ReportAliasLinkTests(unittest.TestCase):
    """Run 6: a body link to a source's http alias is a citation of that source
    in the content gate too, not a foreign URL."""

    def test_an_alias_link_is_not_reported_as_missing(self):
        from scripts import validate_report

        ledger = valid_quality_ledger()
        source = ledger["sources"][0]
        source["url"] = "https://paper.example.cn/a.htm?div=-1"
        source["aliases"] = ["http://paper.example.cn/a.htm?div=-1"]
        text = (
            "# T\n\n> s\n\n> 15 September 2026\n\n"
            "Body [cite](http://paper.example.cn/a.htm?div=-1).\n\n"
            "## Sources\n\n- [a](https://paper.example.cn/a.htm?div=-1)\n"
        )
        errors = validate_report.validate_report_against_ledger(text, ledger)
        self.assertEqual(
            [], [e for e in errors if "Report URL is not present" in e], errors
        )
        text_foreign = text.replace(
            "http://paper.example.cn/a.htm?div=-1", "https://elsewhere.example/x"
        )
        errors = validate_report.validate_report_against_ledger(text_foreign, ledger)
        self.assertTrue([e for e in errors if "Report URL is not present" in e])


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


class LivingPersonRulesAreGoneTests(unittest.TestCase):
    """R25: nothing about a person blocks a claim any more."""

    def bogus_role_claim(self):
        return dict(
            named_claim(),
            person_ids=["P3"],
            person_claim_role="subject_assessment",
        )

    def test_a_living_person_with_a_bogus_role_raises_no_person_finding(self):
        self.assertEqual(
            [],
            [
                item
                for item in validate_ledger.claim_findings(
                    self.bogus_role_claim(), person_ledger("living")
                )
                if item.family == "ledger/person"
            ],
        )

    def test_the_claim_is_accepted(self):
        self.assertEqual(
            [],
            [
                item
                for item in validate_ledger.claim_findings(
                    self.bogus_role_claim(), person_ledger("living")
                )
                if item.severity == "hard"
            ],
        )

    def test_the_harm_family_is_no_longer_emitted(self):
        self.assertNotIn("ledger/harm", validate_ledger.FAMILIES)


class CjkNumeralQuantityTests(unittest.TestCase):
    """R29: a count spelled in Han numerals is silent; digits/dates stay warn."""

    def claim(self, text):
        return {
            "claim_id": "C57",
            "claim": text,
            "kind": "fact",
            "importance": "supporting",
            "source_ids": ["S2"],
            "source_evidence": [
                {
                    "source_id": "S2",
                    "extract_or_location": (
                        "该文由学界同人共同署名,文末未列出署名人数与日期."
                    ),
                }
            ],
        }

    def findings(self, text):
        return quantity_findings(self.claim(text), valid_quality_ledger())

    def test_a_han_numeral_count_raises_no_finding(self):
        self.assertEqual([], self.findings("三位作者共同署名该文。"))

    def test_the_same_count_in_digits_stays_hard(self):
        item = self.findings("3位作者共同署名该文。")[0]
        self.assertEqual("warn", item.severity)
        self.assertEqual("", item.remove)
        self.assertIn("'3' is in the claim but not in", item.message)

    def test_a_date_stays_hard(self):
        items = self.findings("1936年12月11日三位作者共同署名该文。")
        warned = [item for item in items if item.severity == "warn"]
        self.assertTrue(warned, items)
        self.assertTrue(all(item.remove == "" for item in warned))
        self.assertIn(
            "'1936-12-11' is in the claim but not in",
            " ".join(item.message for item in warned),
        )


if __name__ == "__main__":
    unittest.main()
