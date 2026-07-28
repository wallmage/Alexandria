import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.content_gate import run_content_gate, validate_content_receipt

ROOT = Path(__file__).parents[1]
SCORES = (
    "question_answered",
    "evidence_strength",
    "evidence_coverage",
    "reasoning_integrity",
    "counterevidence",
    "explanatory_depth",
    "decision_value",
    "writing_clarity",
)
CHECKS = (
    "central_judgment_answers_question",
    "priority_coverage_resolved",
    "key_claims_traceable",
    "source_independence_calibrated",
    "counterevidence_tested",
    "uncertainty_visible",
    "recommendations_or_implications_supported",
    "forecasts_conditional",
    "section_value_density_reviewed",
    "length_is_substantive_not_padded",
)


def file_sha256(path):
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def write_review(path, report, ledger, *, report_lang="en"):
    review = {
        "schema_version": 2,
        "status": "completed",
        "report_path": str(report.resolve()),
        "report_sha256": file_sha256(report),
        "ledger_path": str(ledger.resolve()),
        "ledger_sha256": file_sha256(ledger),
        "report_lang": report_lang,
        "reviewed_at": "2026-07-28T12:00:00Z",
        "reviewer_mode": "fresh_eyes",
        "scores": {
            name: {
                "score": 4,
                "rationale": f"The final report satisfies the {name} standard.",
            }
            for name in SCORES
        },
        "checks": {name: True for name in CHECKS},
        "section_reviews": [
            {
                "section_heading": heading,
                "purpose": "Advance the report's governing question.",
                "new_value": "Adds distinct evidence, explanation, or decision value.",
                "evidence_or_reasoning": "The section is supported by the bound ledger.",
                "limitation_or_tradeoff": "Its scope is limited to the fixture contract.",
                "contribution_to_governing_question": "Moves the reader toward the central judgment.",
                "disposition": "keep",
            }
            for heading in ("Executive summary", "Key process", "Outlook")
        ],
        "findings": [],
        "evidence_limitations": [
            "The fixture tests production behavior rather than real-world research."
        ],
        "completion_note": "The final report is coherent, traceable, and fit for its fixture purpose.",
    }
    path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    return review


class ContentGateTests(unittest.TestCase):
    def make_case(self, directory):
        work = Path(directory)
        report = work / "report.md"
        ledger = work / "ledger.json"
        review = work / "content-review.json"
        receipt = work / "content-receipt.json"
        report.write_text(
            (ROOT / "tests" / "fixtures" / "sample-report.md").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        ledger.write_text(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        write_review(review, report, ledger)
        return report, ledger, review, receipt

    def test_clean_review_writes_a_bound_receipt_and_revalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            self.assertEqual(
                [],
                run_content_gate(report, ledger, review, receipt),
            )
            result = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("passed", result["status"])
            self.assertEqual(file_sha256(report), result["report_sha256"])
            self.assertEqual(file_sha256(ledger), result["ledger_sha256"])
            self.assertEqual(
                [],
                validate_content_receipt(
                    report,
                    ledger,
                    result,
                    expected_lang="en",
                ),
            )

    def test_low_score_and_false_required_check_block_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["scores"]["evidence_strength"]["score"] = 3
            note["checks"]["counterevidence_tested"] = False
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            joined = " ".join(errors)
            self.assertIn("evidence_strength", joined)
            self.assertIn("counterevidence_tested", joined)
            self.assertFalse(receipt.exists())

    def test_stale_report_or_ledger_hash_blocks_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = "0" * 64
            note["ledger_sha256"] = "1" * 64
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            joined = " ".join(errors)
            self.assertIn("final report", joined)
            self.assertIn("evidence ledger", joined)

    def test_review_language_must_match_the_ledger_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_lang"] = "zh-CN"
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            self.assertTrue(
                any("language does not match the evidence ledger" in error for error in errors),
                errors,
            )

    def test_unresolved_critical_finding_blocks_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["findings"] = [
                {
                    "finding_id": "F1",
                    "severity": "critical",
                    "category": "reasoning",
                    "location": "Executive summary",
                    "finding": "The conclusion reverses the evidence.",
                    "disposition": "rejected",
                    "rationale": "The draft author disagreed.",
                    "report_disclosure_excerpt": None,
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            self.assertTrue(
                any("Critical finding F1 must be fixed" in error for error in errors),
                errors,
            )

    def test_major_accepted_limitation_must_be_disclosed_in_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["findings"] = [
                {
                    "finding_id": "F2",
                    "severity": "major",
                    "category": "evidence",
                    "location": "Evidence limits",
                    "finding": "The fixture is not real-world evidence.",
                    "disposition": "accepted_limitation",
                    "rationale": "The limitation is inherent to a render fixture.",
                    "report_disclosure_excerpt": (
                        "This disclosure does not appear in the final report body."
                    ),
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            self.assertTrue(
                any("F2 disclosure cannot be located" in error for error in errors),
                errors,
            )

            disclosure = (
                "This fixture checks production behavior and does not establish "
                "real-world research quality."
            )
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "Its only factual purpose is to exercise the report pipeline.",
                    "Its only factual purpose is to exercise the report pipeline. "
                    + disclosure,
                ),
                encoding="utf-8",
            )
            note["report_sha256"] = file_sha256(report)
            note["findings"][0]["report_disclosure_excerpt"] = disclosure
            review.write_text(json.dumps(note), encoding="utf-8")
            self.assertEqual(
                [],
                run_content_gate(report, ledger, review, receipt),
            )

    def test_receipt_becomes_stale_after_report_or_ledger_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            self.assertEqual([], run_content_gate(report, ledger, review, receipt))
            result = json.loads(receipt.read_text(encoding="utf-8"))
            report.write_text(
                report.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            errors = validate_content_receipt(report, ledger, result)
            self.assertTrue(any("current report" in error for error in errors), errors)

            report.write_text(
                (ROOT / "tests" / "fixtures" / "sample-report.md").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            ledger.write_text(
                ledger.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            errors = validate_content_receipt(report, ledger, result)
            self.assertTrue(any("current ledger" in error for error in errors), errors)

    def test_every_substantive_section_needs_one_matching_value_review(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["section_reviews"].pop()
            note["section_reviews"].append(
                {
                    **note["section_reviews"][0],
                    "section_heading": "A section that is not in the report",
                }
            )
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            joined = " ".join(errors)
            self.assertIn("Outlook", joined)
            self.assertIn("not in the final report", joined)

    def test_section_review_must_end_in_keep(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["section_reviews"][0]["disposition"] = "revise"
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(report, ledger, review, receipt)
            self.assertTrue(any("section_reviews" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
