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

from scripts import alx, content_gate
from tests.test_alx import (
    CLAIM_ONE,
    CLAIM_TWO,
    COVERAGE_PATCH,
    AlxTestCase,
    ReviewTests,
)
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
        return [
            error
            for error in validate_ledger.validate_references(
                self.ledger_with_claim(), cache_dir
            )
            if "is in the claim but not in" in error and "1945-09-04" in error
        ]

    def test_the_year_on_the_cached_page_covers_the_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            cache(directory, "1945年的记录如下。" + self.EXTRACT)
            self.assertEqual([], self.quantity_errors(directory))

    def test_without_the_cache_the_fragment_is_still_reported(self):
        items = self.quantity_errors(None)
        self.assertTrue(items)
        self.assertTrue(all(str(item).startswith("WARNING:") for item in items), items)

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
        findings = validate_report.binding_findings(text, ledger)
        self.assertEqual(
            [],
            [f for f in findings if f.family == "binding/link-not-in-ledger"],
            findings,
        )
        text_foreign = text.replace(
            "http://paper.example.cn/a.htm?div=-1", "https://elsewhere.example/x"
        )
        findings = validate_report.binding_findings(text_foreign, ledger)
        self.assertTrue(
            [f for f in findings if f.family == "binding/link-not-in-ledger"]
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


class LivingPersonRulesAreGoneTests(unittest.TestCase):
    """R25: nothing about a person blocks a claim any more."""

    def bogus_role_claim(self):
        return dict(
            named_claim(),
            person_ids=["P3"],
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

    def test_an_unregistered_person_id_only_warns(self):
        [item] = [
            item
            for item in validate_ledger.claim_findings(
                dict(named_claim(), person_ids=["P9"]), person_ledger("living")
            )
            if item.family == "ledger/person"
        ]
        self.assertEqual("warn", item.severity)
        self.assertEqual("A", item.klass)
        self.assertEqual(
            "C51: person_ids P9 not in ledger.people; run alx ledger merge "
            "people or drop the id",
            item.message,
        )
        self.assertEqual("alx ledger merge people.json", item.fix)
        self.assertEqual("", item.remove)


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
        self.assertTrue(all(item.remove == "" for item in warned), items)
        self.assertIn(
            "'1936-12-11' is in the claim but not in",
            " ".join(item.message for item in warned),
        )


class UnclassifiedSourcePortfolioTests(AlxTestCase):
    """R27: an unclassified evidence portfolio is a warn, not a refusal.

    `bootstrap` classifies both sources; this is the same workspace with the
    `alx source set` step left out, which is what a run out of time produces.
    """

    def workspace_without_classification(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(0, code, out)
        patch = self.write_json("coverage.json", COVERAGE_PATCH)
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.draft_report()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        reviews.dir, reviews.root = self.dir, self.root
        reviews.run_alx, reviews.run_in = self.run_alx, self.run_in
        reviews.finish_reviews()
        return self.run_in("check")

    def test_no_classification_finding_blocks_the_check(self):
        _code, out = self.workspace_without_classification()
        self.assertIn("no independent source", out)
        hard = out.split("=== WARN")[0]
        for family in ("ledger/portfolio", "ledger/provenance", "ledger/key-claim"):
            self.assertNotIn(family, hard)

    def test_every_classification_finding_is_a_warning(self):
        """Restates test_every_classification_finding_is_class_a: R28 prints no
        class suffix, so the tier is the whole label."""
        _code, out = self.workspace_without_classification()
        warn_block = out.split("=== WARN", 1)[1]
        self.assertNotIn("waivable by --deliver", warn_block.split("=== STATUS")[0])
        self.assertIn("[ledger/portfolio] 1", warn_block)
        self.assertIn("[ledger/provenance] 2", warn_block)
        self.assertIn("[ledger/key-claim] 1", warn_block)


class ClaimAddNamesTheClaimFileTests(AlxTestCase):
    """R20: a claim's remedy names the file the claim came from."""

    def test_a_warned_claim_names_its_own_input_file(self):
        """R28 restatement of test_a_rejected_claim_names_its_own_input_file.

        A dangling `supports` is ledger/reference, so the claim is accepted and
        the remedy is printed as a WARN — still naming the real input file.
        """
        self.bootstrap()
        claim = dict(CLAIM_ONE, claim_id="C9", supports=["C99"])
        path = self.write_json("late.json", [claim])
        code, out = self.run_in("claim", "add", path)
        self.assertEqual(0, code, out)
        self.assertIn("C9 WARN", out)
        self.assertIn("[ledger/reference]", out)
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

    def test_two_days_warn_and_name_as_of(self):
        """R28 restatement of test_two_days_stay_hard_and_name_as_of.

        Drift beyond the window is still reported with its fix, but
        ledger/reference is bookkeeping: it warns instead of refusing.
        """
        [item] = self.findings("2026-07-30")
        self.assertEqual("warn", item.severity)
        self.assertIn("2 days after verified_at 2026-07-28", item.message)
        self.assertIn("threshold 1 day", item.message)
        self.assertEqual(
            "set field as_of in claims/*.json, then alx claim add claims/*.json",
            alx.adopt([item])[0].fix,
        )


class RecoveredSchemaWarnTests(unittest.TestCase):
    """B2-B6: restored schema shape stays WARN and never refuses."""

    def test_schema_is_not_a_refuse_family(self):
        self.assertTrue(hasattr(alx, "REFUSE_FAMILIES"))
        self.assertNotIn("ledger/schema", alx.REFUSE_FAMILIES)

    def test_empty_arrays_and_hollow_brief_are_warn_only(self):
        findings = validate_ledger.collect_findings(
            {
                "schema_version": 4,
                "subject": "X",
                "research_question": "Y",
                "brief": {},
                "people": [],
                "report_date": "2026-07-28",
                "coverage": [],
                "sources": [],
                "claims": [],
                "synthesis": {
                    "central_judgment_claim_ids": [],
                    "counterevidence_claim_ids": [],
                    "adversarial_tests": [],
                    "implications": [],
                    "decisions_or_takeaways": [],
                    "scenarios": [],
                    "limitations": [],
                    "research_stop_reason": "stop",
                },
                "unresolved_questions": [],
            }
        )
        schema = [item for item in findings if item.family == "ledger/schema"]
        self.assertTrue(schema)
        self.assertEqual({"warn"}, {item.severity for item in schema})
        self.assertEqual([], [item for item in findings if item.severity == "hard"])
        printed = validate_ledger.render_grouped(schema, verbose=True)
        self.assertIn("[] should be non-empty", printed)
        messages = " ".join(item.message for item in schema)
        self.assertIn("sources", messages)
        self.assertIn("claims", messages)
        self.assertNotIn("brief", messages)
        self.assertNotIn("coverage", messages)
        self.assertTrue(
            any("in ledger.json" in item.fix for item in schema),
            [item.fix for item in schema],
        )


if __name__ == "__main__":
    unittest.main()
