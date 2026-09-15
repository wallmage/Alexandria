import hashlib
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts import content_gate
from scripts.content_gate import (
    _schema_errors,
    run_check,
    run_content_gate,
    validate_content_receipt,
)
from scripts.content_gate import main as content_gate_main
from scripts.gate_severity import hard_errors
from scripts.source_fidelity import issue_source_fidelity_receipt
from scripts.validate_ledger import prose_floor_errors, validate_schema
from tests.source_fidelity_transport import mock_production_transport

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
        "visual_assets": [],
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
        source_receipt = work / "source-fidelity-receipt.json"
        source_url = (
            "https://example.com/research/"
            "a-very-long-but-valid-path-that-must-wrap-inside-the-page-"
            "instead-of-running-through-the-margin"
        )
        summary = (
            "This compact fixture checks typography, navigation, citations, "
            "and special characters. Its only factual purpose is to exercise "
            "the report pipeline."
        )
        outlook = (
            "The renderer should remain readable when headings, tables, code, "
            "and long links appear together."
        )
        report_text = (
            ROOT / "tests" / "fixtures" / "sample-report.md"
        ).read_text(encoding="utf-8")
        report_text = report_text.replace(
            "# R&D Systems: A Render Check",
            f"# [R&D Systems: A Render Check]({source_url})",
            1,
        )
        table_rows = (
            "Safe HTML Record",
            "A4 PDF Record",
            "Extractable text Record",
        )
        report_text = report_text.replace(
            summary, f"{summary} [Record]({source_url})"
        ).replace(outlook, f"{outlook} [Record]({source_url})")
        for row in (
            "| Parse | Safe HTML |",
            "| Render | A4 PDF |",
            "| Reopen | Extractable text |",
        ):
            report_text = report_text.replace(
                row,
                row[:-1] + f" [Record]({source_url}) |",
            )
        report.write_text(report_text, encoding="utf-8")
        ledger_data = json.loads(
            (ROOT / "tests" / "fixtures" / "evidence-ledger.json").read_text(
                encoding="utf-8"
            )
        )
        ledger_data["claims"][0]["report_excerpts"] = [
            "R&D Systems: A Render Check",
            (
                "This compact fixture checks typography, navigation, "
                "citations, and special characters."
            ),
            "Its only factual purpose is to exercise the report pipeline.",
            ledger_data["claims"][0]["report_excerpts"][0],
            outlook,
            *table_rows,
        ]
        ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
        write_review(review, report, ledger)
        with mock_production_transport(
            {
                "example.com": (
                    200,
                    {"content-type": "text/plain"},
                    b"Fixture",
                )
            }
        ):
            issue_source_fidelity_receipt(
                ledger,
                source_receipt,
                now=__import__("datetime").date(2026, 7, 28),
            )
        return report, ledger, review, receipt, source_receipt

    def test_source_fidelity_receipt_is_a_hard_prerequisite(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, _ = self.make_case(directory)
            errors = run_content_gate(report, ledger, review, receipt)
            self.assertTrue(
                any("Source-fidelity receipt is required" in error for error in errors),
                errors,
            )
            self.assertFalse(receipt.exists())

    def test_aligned_markdown_table_passes_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "|---|---|", "|:---|---:|"
                ),
                encoding="utf-8",
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = file_sha256(report)
            review.write_text(json.dumps(note), encoding="utf-8")

            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )

            self.assertEqual([], errors)
            self.assertTrue(receipt.exists())

    def test_content_receipt_cannot_overwrite_a_gate_input(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, _receipt, source_receipt = self.make_case(
                directory
            )
            original = report.read_bytes()

            errors = run_content_gate(
                report,
                ledger,
                review,
                report,
                source_fidelity_receipt_path=source_receipt,
            )

            self.assertTrue(
                any("must be separate" in error for error in errors),
                errors,
            )
            self.assertEqual(original, report.read_bytes())

    def test_existing_unrelated_content_receipt_needs_force(self):
        # Note: spec §7.5 — unrelated existing output still requires --force.
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            receipt.write_text("personal notes", encoding="utf-8")

            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )

            self.assertTrue(any("already exists" in error for error in errors), errors)
            self.assertEqual("personal notes", receipt.read_text(encoding="utf-8"))

    def test_clean_review_writes_a_bound_receipt_and_revalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            self.assertEqual(
                [],
                run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                ),
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
                    source_fidelity_receipt_path=source_receipt,
                    expected_lang="en",
                ),
            )

    def test_visual_asset_approval_is_hash_bound_into_the_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            cover = Path(directory) / "cover.png"
            cover.write_bytes(b"reviewed safe cover pixels")
            note = json.loads(review.read_text(encoding="utf-8"))
            note["visual_assets"] = [
                {
                    "path": "cover.png",
                    "sha256": file_sha256(cover),
                    "usage": "cover",
                    "visible_text_and_claims_review": (
                        "No visible text or externally checkable claim appears."
                    ),
                    "disposition": "approved",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")

            self.assertEqual(
                [],
                run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                ),
            )
            result = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    {
                        "path": "cover.png",
                        "sha256": file_sha256(cover),
                        "usage": "cover",
                    }
                ],
                result["approved_visual_assets"],
            )

            result["approved_visual_assets"][0]["usage"] = "body"
            errors = validate_content_receipt(
                report,
                ledger,
                result,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("visual asset approvals" in error.lower() for error in errors),
                errors,
            )

            result["approved_visual_assets"][0]["usage"] = "cover"
            cover.write_bytes(b"ALICE STOLE FUNDS")
            errors = validate_content_receipt(
                report,
                ledger,
                result,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("visual asset" in error.lower() for error in errors),
                errors,
            )

    def test_body_images_are_discovered_and_unused_approvals_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            body_image = Path(directory) / "body.png"
            body_image.write_bytes(b"ALICE STOLE FUNDS")
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "## Outlook",
                    "![](body.png)\n\n## Outlook",
                ),
                encoding="utf-8",
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = file_sha256(report)
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("unapproved visual asset" in error.lower() for error in errors),
                errors,
            )

            note["visual_assets"] = [
                {
                    "path": "body.png",
                    "sha256": file_sha256(body_image),
                    "usage": "body",
                    "visible_text_and_claims_review": (
                        "The visible text and claim content were reviewed."
                    ),
                    "disposition": "approved",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            self.assertEqual(
                [],
                run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                ),
            )

            original = body_image.read_bytes()
            errors = run_content_gate(
                report,
                ledger,
                review,
                body_image,
                source_fidelity_receipt_path=source_receipt,
                force=True,
            )
            self.assertTrue(
                any("must be separate" in error for error in errors),
                errors,
            )
            self.assertEqual(original, body_image.read_bytes())

        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            unused = Path(directory) / "unused.png"
            unused.write_bytes(b"reviewed but unused")
            note = json.loads(review.read_text(encoding="utf-8"))
            note["visual_assets"] = [
                {
                    "path": "unused.png",
                    "sha256": file_sha256(unused),
                    "usage": "body",
                    "visible_text_and_claims_review": (
                        "The visible text and claim content were reviewed."
                    ),
                    "disposition": "approved",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("unused visual asset" in error.lower() for error in errors),
                errors,
            )

    def test_embedded_data_images_cannot_bypass_visual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "## Outlook",
                    (
                        "![](data:image/png;base64,"
                        "QUxJQ0UgU1RPTEUgRlVORFM=)\n\n## Outlook"
                    ),
                ),
                encoding="utf-8",
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = file_sha256(report)
            review.write_text(json.dumps(note), encoding="utf-8")

            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("embedded data image" in error.lower() for error in errors),
                errors,
            )

    def test_every_rendered_nonlocal_image_form_is_rejected(self):
        cases = {
            "inline HTTP": "![Chart](https://example.com/chart.png)",
            "protocol relative": "![Chart](//example.com/chart.png)",
            "reference style": (
                "![Chart][figure]\n\n"
                "[figure]: https://example.com/chart.png"
            ),
            "raw quoted HTML": (
                '<img src="https://example.com/chart.png" alt="">'
            ),
            "raw unquoted HTML": (
                "<img src=https://example.com/chart.png alt=>"
            ),
            "raw data HTML": (
                '<img src=data:image/png;base64,QUxJQ0U= alt="">'
            ),
            "self-closing suppressed tag": (
                "<script/><img src=data:image/png;base64,QUxJQ0U= "
                'alt="Alice stole funds">'
            ),
        }
        for name, image_markup in cases.items():
            with self.subTest(image_form=name), tempfile.TemporaryDirectory() as directory:
                report, ledger, review, receipt, source_receipt = self.make_case(
                    directory
                )
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "## Outlook",
                        f"{image_markup}\n\n## Outlook",
                    ),
                    encoding="utf-8",
                )
                note = json.loads(review.read_text(encoding="utf-8"))
                note["report_sha256"] = file_sha256(report)
                review.write_text(json.dumps(note), encoding="utf-8")

                errors = run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                )

                self.assertTrue(
                    any(
                        "nonlocal image" in error.lower()
                        or "embedded data image" in error.lower()
                        for error in errors
                    ),
                    errors,
                )
                self.assertFalse(receipt.exists())

    def test_image_accessibility_text_cannot_add_an_ungated_assertion(self):
        for attribute in ("alt", "title"):
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory() as directory:
                report, ledger, review, receipt, source_receipt = self.make_case(
                    directory
                )
                image = Path(directory) / "figure.png"
                image.write_bytes(b"reviewed image")
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "## Outlook",
                        (
                            f'<img src=figure.png {attribute}="Alice stole funds">'
                            "\n\n## Outlook"
                        ),
                    ),
                    encoding="utf-8",
                )
                note = json.loads(review.read_text(encoding="utf-8"))
                note["report_sha256"] = file_sha256(report)
                note["visual_assets"] = [
                    {
                        "path": "figure.png",
                        "sha256": file_sha256(image),
                        "usage": "body",
                        "visible_text_and_claims_review": (
                            "The image accessibility text was reviewed."
                        ),
                        "disposition": "approved",
                    }
                ]
                review.write_text(json.dumps(note), encoding="utf-8")

                errors = run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                )

                self.assertTrue(
                    any("accessibility text" in error.lower() for error in errors),
                    errors,
                )
                self.assertFalse(receipt.exists())

    def test_link_tooltip_cannot_add_an_ungated_assertion(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            report_text, replacements = re.subn(
                r"\[Record\]\((https://[^)]+)\)",
                r'[Record](\1 "Alice Smith stole customer funds")',
                report.read_text(encoding="utf-8"),
                count=1,
            )
            self.assertEqual(1, replacements)
            report.write_text(report_text, encoding="utf-8")
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = file_sha256(report)
            review.write_text(json.dumps(note), encoding="utf-8")

            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )

            self.assertTrue(
                any("accessibility text" in error.lower() for error in errors),
                errors,
            )
            self.assertFalse(receipt.exists())

    def test_unsafe_links_and_active_html_are_rejected_from_markdown(self):
        cases = {
            "javascript link": "[Record](javascript:alert(1))",
            "data link": "[Record](data:text/html,unsafe)",
            "file link": "[Record](file:///etc/passwd)",
            "unledgered raw link": (
                '<a href="https://attacker.example/">Record</a>'
            ),
            "raw script": '<script src="https://attacker.example/x.js"></script>',
            "raw iframe": '<iframe src="https://attacker.example/"></iframe>',
            "raw form": '<form action="https://attacker.example/"></form>',
            "raw video": '<video src="https://attacker.example/x.mp4"></video>',
            "event handler": '<img src="missing.png" onerror="alert(1)">',
            "meta refresh": (
                '<meta http-equiv="refresh" '
                'content="0;url=https://attacker.example/">'
            ),
        }
        for name, markup in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                report, ledger, review, receipt, source_receipt = self.make_case(
                    directory
                )
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        "## Outlook",
                        f"{markup}\n\n## Outlook",
                    ),
                    encoding="utf-8",
                )
                note = json.loads(review.read_text(encoding="utf-8"))
                note["report_sha256"] = file_sha256(report)
                review.write_text(json.dumps(note), encoding="utf-8")

                errors = run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                )

                self.assertTrue(
                    any(
                        "link destination" in error.lower()
                        or "not present in the evidence ledger" in error.lower()
                        or "renderer allowlist" in error.lower()
                        for error in errors
                    ),
                    errors,
                )
                self.assertFalse(receipt.exists())

    def test_low_score_and_false_required_check_only_warn(self):
        """R28 restatement: content judgments warn; they no longer block."""
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["scores"]["evidence_strength"]["score"] = 3
            note["checks"]["counterevidence_tested"] = False
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            joined = " ".join(errors)
            self.assertIn("evidence_strength", joined)
            self.assertIn("counterevidence_tested", joined)
            self.assertEqual([], hard_errors(errors))
            self.assertTrue(receipt.exists())

    def test_every_content_family_is_warn_and_the_gate_still_issues(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_lang"] = "zh-CN"
            note["scores"]["writing_clarity"]["score"] = 2
            note["checks"]["counterevidence_tested"] = False
            note["findings"] = [
                {
                    "finding_id": "F1",
                    "severity": "critical",
                    "category": "evidence",
                    "location": "Outlook",
                    "finding": "A critical gap remains unaddressed in the outlook.",
                    "disposition": "rejected",
                    "rationale": "The reviewer left this critical finding open.",
                    "report_disclosure_excerpt": "",
                },
                {
                    "finding_id": "F2",
                    "severity": "major",
                    "category": "evidence",
                    "location": "Outlook",
                    "finding": "A limitation needs an in-report disclosure excerpt.",
                    "disposition": "accepted_limitation",
                    "rationale": "The limitation is accepted but must be disclosed.",
                    "report_disclosure_excerpt": "too short",
                },
            ]
            review.write_text(json.dumps(note), encoding="utf-8")

            findings = run_check(report, ledger, review)
            content = [
                item for item in findings if item.family.startswith("content/")
            ]
            self.assertEqual(
                {
                    "content/check",
                    "content/language",
                    "content/score",
                    "content/critical-finding",
                    "content/disclosure",
                },
                {item.family for item in content},
            )
            self.assertEqual({"warn"}, {item.severity for item in content})

            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertEqual([], hard_errors(errors))
            self.assertTrue(receipt.exists())

    def test_stale_report_or_ledger_hash_blocks_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_sha256"] = "0" * 64
            note["ledger_sha256"] = "1" * 64
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            joined = " ".join(errors)
            self.assertIn("final report", joined)
            self.assertIn("evidence ledger", joined)

    def test_review_language_must_match_the_ledger_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["report_lang"] = "zh-CN"
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("language does not match the evidence ledger" in error for error in errors),
                errors,
            )

    def test_unresolved_critical_finding_blocks_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
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
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(
                any("Critical finding F1 must be fixed" in error for error in errors),
                errors,
            )

    def test_major_accepted_limitation_must_be_disclosed_in_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
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
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
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
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["claims"][0]["report_excerpts"].append(disclosure)
            ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
            with mock_production_transport(
                {
                    "example.com": (
                        200,
                        {"content-type": "text/plain"},
                        b"Fixture",
                    )
                }
            ):
                source_receipt.unlink()
                issue_source_fidelity_receipt(
                    ledger,
                    source_receipt,
                    now=__import__("datetime").date(2026, 7, 28),
                )
            note["report_sha256"] = file_sha256(report)
            note["ledger_sha256"] = file_sha256(ledger)
            note["findings"][0]["report_disclosure_excerpt"] = disclosure
            review.write_text(json.dumps(note), encoding="utf-8")
            self.assertEqual(
                [],
                run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                ),
            )

    def test_receipt_becomes_stale_after_report_or_ledger_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            self.assertEqual(
                [],
                run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                ),
            )
            result = json.loads(receipt.read_text(encoding="utf-8"))
            report.write_text(
                report.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            errors = validate_content_receipt(
                report,
                ledger,
                result,
                source_fidelity_receipt_path=source_receipt,
            )
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
            errors = validate_content_receipt(
                report,
                ledger,
                result,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(any("current ledger" in error for error in errors), errors)

    def test_malformed_receipt_path_fields_fail_validation_without_crashing(self):
        receipt = {
            "schema_version": 2,
            "status": "passed",
            "report_path": "report.md",
            "ledger_path": "ledger.json",
            "content_review_schema_path": str(
                ROOT / "references" / "content-review.schema.json"
            ),
            "evidence_ledger_schema_path": str(
                ROOT / "references" / "evidence-ledger.schema.json"
            ),
            "review_note_path": "review.json",
        }
        for field in (
            "content_review_schema_path",
            "evidence_ledger_schema_path",
            "review_note_path",
        ):
            for value in ({"bad": "path"}, "\x00"):
                with self.subTest(field=field, value=value):
                    malformed = {**receipt, field: value}
                    errors = validate_content_receipt(
                        ROOT / "missing-report.md",
                        ROOT / "missing-ledger.json",
                        malformed,
                    )
                    self.assertTrue(
                        any("path" in error and "valid" in error for error in errors),
                        errors,
                    )

    def test_non_object_gate_inputs_fail_validation_without_crashing(self):
        for field in ("ledger", "review"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                report, ledger, review, receipt, source_receipt = self.make_case(
                    directory
                )
                target = ledger if field == "ledger" else review
                target.write_text("[]", encoding="utf-8")
                errors = run_content_gate(
                    report,
                    ledger,
                    review,
                    receipt,
                    source_fidelity_receipt_path=source_receipt,
                )
                self.assertTrue(
                    any("is not of type 'object'" in error for error in errors),
                    errors,
                )

    def test_every_substantive_section_needs_one_matching_value_review(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["section_reviews"].pop()
            note["section_reviews"].append(
                {
                    **note["section_reviews"][0],
                    "section_heading": "A section that is not in the report",
                }
            )
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            joined = " ".join(errors)
            self.assertIn("Outlook", joined)
            self.assertIn("not in the final report", joined)

    def test_section_review_must_end_in_keep(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(directory)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["section_reviews"][0]["disposition"] = "revise"
            review.write_text(json.dumps(note), encoding="utf-8")
            errors = run_content_gate(
                report, ledger, review, receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertTrue(any("section_reviews" in error for error in errors), errors)

    def test_run_check_collects_scores_critical_disclosure_and_support(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, _source_receipt = self.make_case(
                directory
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["scores"]["writing_clarity"]["score"] = 2
            note["findings"] = [
                {
                    "finding_id": "F-crit",
                    "severity": "critical",
                    "category": "evidence",
                    "location": "Outlook",
                    "finding": "A critical gap remains unaddressed in the outlook.",
                    "disposition": "open",
                    "rationale": "The reviewer left this critical finding open.",
                    "report_disclosure_excerpt": "",
                },
                {
                    "finding_id": "F-disc",
                    "severity": "major",
                    "category": "evidence",
                    "location": "Outlook",
                    "finding": "A limitation needs an in-report disclosure excerpt.",
                    "disposition": "accepted_limitation",
                    "rationale": "The limitation is accepted but must be disclosed.",
                    "report_disclosure_excerpt": "too short",
                },
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            findings = run_check(report, ledger, review)
            messages = [item.message for item in findings]
            families = [item.family for item in findings]
            self.assertTrue(any("writing_clarity" in message for message in messages), messages)
            self.assertTrue(any("F-crit" in message for message in messages), messages)
            self.assertTrue(any("disclosure" in message for message in messages), messages)
            # R29: claim<->paragraph binding is the binding gate's job.
            self.assertNotIn("content/claim-support", families)
            self.assertNotIn("content/claim-binding", families)
            self.assertFalse(receipt.exists())

    def test_run_check_emits_no_per_claim_binding_line(self):
        """R29: `content/claim-support` and `content/claim-binding` are gone.

        An absent excerpt re-emits validate_report's locate string as
        `content/check` WARN. The C1: bookkeeping line stays deleted.
        """
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, _receipt, _source_receipt = self.make_case(
                directory
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["claim_support"] = [
                {
                    "claim_id": "C1",
                    "paragraph": 1,
                    "disposition": "supported",
                    "note": "The mapped paragraph carries the claim.",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["claims"][0]["report_paragraph"] = 1
            ledger_data["claims"][0]["report_excerpts"] = [
                "This exact passage does not appear anywhere in the report body."
            ]
            ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
            findings = run_check(report, ledger, review)
            self.assertEqual(
                [],
                [
                    item.message
                    for item in findings
                    if item.message.startswith("C1:")
                ],
            )
            families = [item.family for item in findings]
            self.assertNotIn("content/claim-support", families)
            self.assertNotIn("content/claim-binding", families)
            located = [
                item
                for item in findings
                if "cannot be located in the report" in item.message
            ]
            self.assertTrue(located, findings)
            self.assertEqual("content/check", located[0].family)
            self.assertEqual("warn", located[0].severity)
            self.assertEqual("alx check --fix", located[0].fix)

    def test_run_check_can_skip_the_ledger_error_re_emission(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, _receipt, _source_receipt = self.make_case(
                directory
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["claim_support"] = [
                {
                    "claim_id": "C1",
                    "paragraph": 1,
                    "disposition": "supported",
                    "note": "The mapped paragraph carries the claim.",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["claims"][0]["report_paragraph"] = 1
            ledger_data["claims"][0]["supports"] = ["C404"]
            ledger_data["claims"][0]["report_excerpts"] = [
                "This compact fixture checks typography, navigation, "
                "citations, and special characters."
            ]
            ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
            source_url = ledger_data["sources"][0]["url"]
            text = report.read_text(encoding="utf-8")
            body, sources = text.split("## Sources", 1)
            report.write_text(
                body.replace(source_url, "")
                + "## Sources"
                + sources
                + "\n\nAn extra link to [an unlisted page](https://unlisted.example/x).\n",
                encoding="utf-8",
            )

            with_ledger = run_check(report, ledger, review)
            without_ledger = run_check(
                report, ledger, review, include_ledger_checks=False
            )
            self.assertTrue(
                any("C404" in item.message for item in with_ledger), with_ledger
            )
            self.assertFalse(
                any("C404" in item.message for item in without_ledger),
                without_ledger,
            )
            self.assertIn(
                "binding/link-not-in-ledger",
                [item.family for item in with_ledger],
            )
            self.assertNotIn(
                "binding/link-not-in-ledger",
                [item.family for item in without_ledger],
            )
            # R29: no C1: bookkeeping; validate_report's citation string is
            # re-emitted as content/check WARN even when ledger checks skip.
            self.assertEqual(
                [],
                [
                    item.message
                    for item in without_ledger
                    if item.message.startswith("C1:")
                ],
            )
            self.assertNotIn(
                "content/claim-support",
                [item.family for item in without_ledger],
            )
            self.assertNotIn(
                "content/claim-binding",
                [item.family for item in without_ledger],
            )
            nearby = [
                item
                for item in without_ledger
                if "has no nearby citation to its ledger source" in item.message
            ]
            self.assertTrue(nearby, without_ledger)
            self.assertEqual("content/check", nearby[0].family)
            self.assertEqual("warn", nearby[0].severity)
            self.assertEqual(
                "add the source link to paragraph <n> of report.md",
                nearby[0].fix,
            )

    def test_check_flag_is_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, _source_receipt = self.make_case(
                directory
            )
            note = json.loads(review.read_text(encoding="utf-8"))
            note["claim_support"] = [
                {
                    "claim_id": "C1",
                    "paragraph": 1,
                    "disposition": "supported",
                    "note": "The mapped paragraph carries the claim.",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")
            code = content_gate_main(
                [
                    str(report),
                    "--ledger",
                    str(ledger),
                    "--review-note",
                    str(review),
                    "--check",
                ]
            )
            self.assertFalse(receipt.exists())
            self.assertIn(code, (0, 1))

    def test_check_flag_prints_cannot_be_located_as_warning_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, _receipt, _source_receipt = self.make_case(
                directory
            )
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["claims"][0]["report_excerpts"] = [
                "This exact passage does not appear anywhere in the report body."
            ]
            ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = content_gate_main(
                    [
                        str(report),
                        "--ledger",
                        str(ledger),
                        "--review-note",
                        str(review),
                        "--check",
                    ]
                )
            printed = (
                "WARNING: Claim C1 cannot be located in the report: "
                "This exact passage does not appear anywhere in the report body."
            )
            self.assertEqual(0, code)
            self.assertIn(printed, err.getvalue())

    def test_check_flag_prints_no_nearby_citation_as_warning_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, _receipt, _source_receipt = self.make_case(
                directory
            )
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["claims"][0]["report_excerpts"] = [
                "This compact fixture checks typography, navigation, "
                "citations, and special characters."
            ]
            ledger.write_text(json.dumps(ledger_data), encoding="utf-8")
            source_url = ledger_data["sources"][0]["url"]
            text = report.read_text(encoding="utf-8")
            body, sources = text.split("## Sources", 1)
            report.write_text(
                body.replace(source_url, "") + "## Sources" + sources,
                encoding="utf-8",
            )
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = content_gate_main(
                    [
                        str(report),
                        "--ledger",
                        str(ledger),
                        "--review-note",
                        str(review),
                        "--check",
                    ]
                )
            printed = (
                "WARNING: Claim C1 has no nearby citation to its ledger source."
            )
            self.assertEqual(0, code)
            self.assertIn(printed, err.getvalue())

    def test_stale_content_receipt_overwritten_without_force(self):
        # Note: spec §7.5 stale receipts overwrite without --force.
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "passed",
                        "report_sha256": "0" * 64,
                        "ledger_sha256": "1" * 64,
                    }
                ),
                encoding="utf-8",
            )
            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )
            self.assertEqual([], [error for error in errors if "already exists" in error])
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(file_sha256(report), payload.get("report_sha256"))


if __name__ == "__main__":
    unittest.main()


class CjkReviewNoteFloorTests(unittest.TestCase):
    """J3: the content-review schema carries the CJK floor (spec §7.1 halving).

    A schema cannot be script-aware, so its string minimums are the CJK floor
    and the gate keeps the full floor for non-CJK prose, with threshold and
    actual in the message.
    """

    CONTENT_REVIEW_SCHEMA = ROOT / "references" / "content-review.schema.json"
    ZH_15 = "1915年残13天没有逐日表。"
    EN_15 = "Thin, unusable"

    def schema(self):
        return json.loads(self.CONTENT_REVIEW_SCHEMA.read_text(encoding="utf-8"))

    def note(self, text):
        return {
            "section_reviews": [
                {
                    "section_heading": "Findings",
                    "purpose": "Advance the report's governing question fully.",
                    "new_value": "Adds distinct evidence and decision value.",
                    "evidence_or_reasoning": "Supported by the bound ledger.",
                    "limitation_or_tradeoff": text,
                    "contribution_to_governing_question": "Moves to the judgment.",
                    "disposition": "keep",
                }
            ]
        }

    def floor_errors(self, text):
        return [
            error
            for error in prose_floor_errors(self.note(text), self.schema())
            if "limitation_or_tradeoff" in error
        ]

    def schema_errors(self, text):
        return [
            error
            for error in validate_schema(self.note(text), self.schema())
            if "limitation_or_tradeoff" in error
        ]

    def test_chinese_note_of_15_characters_passes_schema_and_floor(self):
        self.assertEqual(15, len(self.ZH_15))
        self.assertEqual([], self.schema_errors(self.ZH_15))
        self.assertEqual([], self.floor_errors(self.ZH_15))

    def test_english_note_of_15_characters_fails_the_full_floor(self):
        self.assertEqual(14, len(self.EN_15))
        self.assertEqual([], self.schema_errors(self.EN_15))
        errors = self.floor_errors(self.EN_15)
        self.assertTrue(
            any("threshold 20, actual 14" in error for error in errors), errors
        )

    def test_the_gate_reports_the_floor_with_the_schema_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "content-review.schema.json"
            path.write_text(
                self.CONTENT_REVIEW_SCHEMA.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            zh = _schema_errors(
                self.note(self.ZH_15), path, "Content review:", prose_floor=True
            )
            en = _schema_errors(
                self.note(self.EN_15), path, "Content review:", prose_floor=True
            )
        self.assertEqual(
            [], [error for error in zh if "limitation_or_tradeoff" in error]
        )
        self.assertTrue(
            any("limitation_or_tradeoff" in error for error in en), en
        )


class SkippedSourceFidelityReceiptTests(unittest.TestCase):
    """K4: inside the delivery reserve `alx` never issues that receipt."""

    make_case = ContentGateTests.make_case

    def test_a_missing_receipt_is_recorded_instead_of_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            report, ledger, review, receipt, source_receipt = self.make_case(
                directory
            )
            source_receipt.unlink()

            errors = run_content_gate(
                report,
                ledger,
                review,
                receipt,
                source_fidelity_receipt_path=source_receipt,
            )

            self.assertEqual([], errors)
            recorded = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertTrue(recorded["source_fidelity_receipt_skipped"])
            self.assertIsNone(recorded["source_fidelity_receipt_sha256"])
            self.assertEqual(
                [],
                validate_content_receipt(
                    report,
                    ledger,
                    recorded,
                    source_fidelity_receipt_path=source_receipt,
                ),
            )


class R29ReviewNoiseTests(unittest.TestCase):
    """R29/A4: the review gate no longer re-reports claim binding."""

    def test_the_two_deleted_families_are_unregistered(self):
        self.assertNotIn("content/claim-support", content_gate.FAMILIES)
        self.assertNotIn("content/claim-binding", content_gate.FAMILIES)

    def test_the_claim_support_field_stays_accepted(self):
        schema = json.loads(
            content_gate.CONTENT_REVIEW_SCHEMA.read_text(encoding="utf-8")
        )
        self.assertIn("claim_support", schema["properties"])
