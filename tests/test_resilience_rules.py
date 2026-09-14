"""R14 (date year read from the source) and R15 (person_ids auto-linked).

Both rulings loosen format-strict gates that looped Chinese runs: a source that
states the year once and then writes bare month-day dates, and a claim that
names a registered person without repeating the person_id.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
