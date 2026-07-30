"""The gates separate blocking errors from non-blocking warnings.

Fabrication, unsupported quantities, citations, source fidelity, person safety
and schema validity block delivery. Style and formatting judgments, which can be
overcautious, are reported and do not block.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import content_gate, rewild_gate, validate_ledger, validate_report  # noqa: E402
from scripts.gate_severity import (  # noqa: E402
    WARNING_PREFIX,
    emit_findings,
    hard_errors,
    is_warning,
    warning,
    warning_findings,
)

LEDGER_FIXTURE = ROOT / "tests" / "fixtures" / "evidence-ledger.json"


class SharedSeverityHelperTests(unittest.TestCase):
    def test_a_marked_finding_is_a_warning_and_is_idempotent(self):
        marked = warning("Rhythm is uniform.")
        self.assertTrue(marked.startswith(WARNING_PREFIX))
        self.assertTrue(is_warning(marked))
        self.assertEqual(marked, warning(marked))
        self.assertFalse(is_warning("Report needs one H1 title."))

    def test_partitioning_keeps_every_finding_in_exactly_one_tier(self):
        findings = [
            "Report needs one H1 title.",
            warning("Paragraph lengths are uniform."),
            "Report URL is not present in the ledger: https://example.com/",
        ]
        self.assertEqual(2, len(hard_errors(findings)))
        self.assertEqual(1, len(warning_findings(findings)))

    def test_warnings_alone_exit_zero_and_print_without_the_fail_marker(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = emit_findings(
                [warning("Sentence openers repeat.")],
                ok_message="[OK] done",
            )
        self.assertEqual(0, code)
        self.assertIn("WARNING: Sentence openers repeat.", err.getvalue())
        self.assertNotIn("[FAIL]", err.getvalue())
        self.assertIn("[OK] done", out.getvalue())

    def test_one_hard_error_beside_a_warning_still_exits_nonzero(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = emit_findings(
                ["Report is empty.", warning("Punctuation is uniform.")],
                ok_message="[OK] done",
            )
        self.assertEqual(1, code)
        self.assertIn("[FAIL] Report is empty.", err.getvalue())
        self.assertIn("WARNING: Punctuation is uniform.", err.getvalue())
        self.assertEqual("", out.getvalue())


class GateEntryPointSeverityTests(unittest.TestCase):
    """Every gate command reports both tiers through the shared helper."""

    def test_every_gate_main_uses_the_shared_emitter(self):
        for module in (
            validate_report,
            validate_ledger,
            content_gate,
            rewild_gate,
        ):
            with self.subTest(module=module.__name__):
                # scripts/ is importable both as a package and by directory, so
                # the two paths can yield distinct module objects; identity of
                # the helper's origin is what matters here.
                self.assertEqual(
                    "gate_severity",
                    module.emit_findings.__module__.rpartition(".")[2],
                )

    def test_ledger_command_still_fails_on_a_schema_error(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            ledger.write_text("{}", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = validate_ledger.main([str(ledger)])
        self.assertEqual(1, code)
        self.assertIn("[FAIL]", err.getvalue())

    def test_evidence_and_citation_findings_are_never_warnings(self):
        ledger = json.loads(LEDGER_FIXTURE.read_text(encoding="utf-8"))
        ledger["claims"][0]["extract_or_location"] = ""
        ledger["claims"][0]["source_evidence"][0]["extract_or_location"] = ""
        findings = validate_ledger.validate_references(ledger)
        self.assertTrue(findings)
        self.assertEqual(findings, hard_errors(findings))

    def test_markdown_structure_findings_are_never_warnings(self):
        findings = validate_report.validate_markdown(
            "Body text with no title and no sources.",
            min_sections=1,
        )
        self.assertTrue(findings)
        self.assertEqual(findings, hard_errors(findings))


class RewildStyleWarningTests(unittest.TestCase):
    """A retained style warning reports and issues a receipt; hard tiers do not."""

    def _report_text(self):
        # Long enough to satisfy the delivery length policy, and written so the
        # bundled checker raises style-tier findings rather than hard ones.
        sentence = (
            "The team reviewed the corridor timetable and recorded what it "
            "found in the working log. "
        )
        return "# Corridor log\n\n> 28 July 2026\n\n## Findings\n\n" + (
            sentence * 700
        ) + "\n\n## Sources\n\n- [Log](https://example.com/log)\n"

    def _write_review(self, review, report, source):
        review.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "completed",
                    "report_sha256": rewild_gate.file_sha256(report),
                    "source_sha256": rewild_gate.file_sha256(source),
                    "report_lang": "en",
                    "profile": "rewild",
                    "fidelity_checks": {
                        "facts_and_figures": True,
                        "attribution_and_uncertainty": True,
                        "direction_and_negation": True,
                        "causality": True,
                    },
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )

    def test_unwaived_style_warning_reports_but_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            text = self._report_text()
            report.write_text(text, encoding="utf-8")
            source.write_text(
                text.replace("The team reviewed", "The team examined", 1),
                encoding="utf-8",
            )
            self._write_review(review, report, source)
            findings = rewild_gate.run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertEqual([], hard_errors(findings))
            self.assertTrue(
                any(
                    finding.startswith(
                        f"{WARNING_PREFIX}Unresolved style warning"
                    )
                    for finding in findings
                ),
                findings,
            )
            # The receipt still issues, and it records only waived warnings.
            self.assertTrue(receipt.is_file())
            issued = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("passed", issued["status"])
            self.assertEqual([], issued["style_waivers"])

    def test_a_waived_style_warning_is_recorded_in_the_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            waivers = work / "style-waivers.json"
            text = self._report_text()
            report.write_text(text, encoding="utf-8")
            source.write_text(
                text.replace("The team reviewed", "The team examined", 1),
                encoding="utf-8",
            )
            self._write_review(review, report, source)
            findings = rewild_gate.run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            reported = [
                finding.removeprefix(WARNING_PREFIX).removeprefix(
                    "Unresolved style warning: "
                )
                for finding in warning_findings(findings)
            ]
            self.assertTrue(reported)
            section, _, message = reported[0].partition(": ")
            waivers.write_text(
                json.dumps(
                    {
                        "style_waivers": [
                            {
                                "section": section,
                                "message": message,
                                "reason": (
                                    "The repetition is deliberate in this "
                                    "fixture."
                                ),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            waived = rewild_gate.run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
                waiver_path=waivers,
                force=True,
            )
            self.assertEqual([], hard_errors(waived))
            self.assertNotIn(f"{section}: {message}", " ".join(waived))
            issued = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(
                [{"section": section, "message": message}],
                [
                    {"section": entry["section"], "message": entry["message"]}
                    for entry in issued["style_waivers"]
                ],
            )

    def test_style_warnings_are_the_only_waivable_tier(self):
        self.assertEqual(
            ("Fidelity", "Region", "AI vocabulary"),
            rewild_gate.HARD_WARNING_SECTIONS,
        )


class PdfPageQualitySeverityTests(unittest.TestCase):
    def test_a_missing_render_backend_is_a_warning_not_a_silent_pass(self):
        from unittest import mock

        from scripts import pdf_quality

        with mock.patch.object(
            pdf_quality,
            "run_quality_checks",
            side_effect=ImportError("no render backend"),
        ):
            findings = validate_report._page_quality_errors(Path("missing.pdf"))
        self.assertEqual([], hard_errors(findings))
        self.assertEqual(1, len(warning_findings(findings)))

    def test_a_failed_page_quality_run_stays_a_hard_error(self):
        from unittest import mock

        from scripts import pdf_quality

        with mock.patch.object(
            pdf_quality,
            "run_quality_checks",
            side_effect=ValueError("broken pdf"),
        ):
            findings = validate_report._page_quality_errors(Path("missing.pdf"))
        self.assertEqual(findings, hard_errors(findings))


if __name__ == "__main__":
    unittest.main()
