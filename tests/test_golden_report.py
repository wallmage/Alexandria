"""End-to-end acceptance for realistic reports in all three delivery languages.

Every other test in this suite proves that one gate rejects one defect. This
module proves the opposite property, which no single-gate test can: a report
that follows the instructions in SKILL.md passes the whole delivery pipeline --
ledger validation, the Rewild gate, source fidelity, the content-quality gate,
Markdown validation, PDF rendering, and PDF validation -- with zero errors.

A change that starts rejecting legitimate reports fails here first. The fixtures
are permanent and are checked in beside this module; the receipts, review notes
and PDFs are derived at test time. Everything runs offline through the shared
production-transport boundary.
"""

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (  # noqa: E402
    md_to_pdf,
    pdf_compatibility,
    pdf_quality,
    validate_report,
)
from scripts.content_gate import run_content_gate  # noqa: E402
from scripts.gate_severity import hard_errors  # noqa: E402
from scripts.render_pdf_pages import render_pages  # noqa: E402
from scripts.report_contract import localized_date  # noqa: E402
from scripts.rewild_gate import file_sha256, run_gate  # noqa: E402
from scripts.source_fidelity import (  # noqa: E402
    issue_source_fidelity_receipt,
)
from scripts.validate_ledger import (  # noqa: E402
    DEFAULT_SCHEMA,
    validate_references,
    validate_schema,
)
from scripts.validate_report import SOURCE_HEADINGS, _h2_sections  # noqa: E402
from tests.source_fidelity_transport import (  # noqa: E402
    mock_production_transport,
)

GOLDEN_ROOT = ROOT / "tests" / "fixtures" / "golden"

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

#: One deliberate pre-Rewild wording per language. The gate needs a source
#: snapshot that differs from the delivered report; a meaning-preserving
#: synonym is the smallest honest difference that still proves a real edit.
CASES = (
    {
        "name": "en",
        "lang": "en",
        "profile": "rewild",
        "rewrite": (
            "That distinction is the whole question in this report",
            "That distinction is the entire question in this report",
        ),
        "expected_pdf_text": ("Fairhaven", "Ashcombe"),
        "length_flags": ("--min-words", "7500", "--max-words", "15000"),
        "min_text_chars": "5000",
    },
    {
        "name": "zh-CN",
        "lang": "zh-CN",
        "profile": "rewild-zh",
        "rewrite": (
            "委员会可以拿它当基准",
            "委员会可以把它当基准",
        ),
        "expected_pdf_text": ("清河片区", "夜间最小流量"),
        "length_flags": ("--min-chars", "5000", "--max-chars", "10000"),
        "min_text_chars": "3000",
    },
    {
        "name": "zh-HK",
        "lang": "zh-HK",
        "profile": "rewild-hk",
        "rewrite": (
            "這正是本報告的核心分別",
            "這正是本報告的關鍵分別",
        ),
        "expected_pdf_text": ("錦寧中心", "冷凍噸"),
        "length_flags": ("--min-chars", "5000", "--max-chars", "10000"),
        "min_text_chars": "3000",
    },
)


def available_cases():
    """Return the golden cases whose fixtures are checked in."""
    return tuple(
        case
        for case in CASES
        if (GOLDEN_ROOT / case["name"] / "report.md").is_file()
    )


def transport_responses(ledger):
    """Serve every recorded extract from the host that published it.

    The production path re-reads sources and asserts that each recorded extract
    is still in the fetched page, so the deterministic response for a host is
    simply every extract attributed to a source on that host.
    """
    by_host = {}
    sources = {
        source["source_id"]: source for source in ledger.get("sources", [])
    }
    for claim in ledger.get("claims", []):
        evidence = list(claim.get("source_evidence") or [])
        source_ids = claim.get("source_ids") or []
        if not evidence and len(source_ids) == 1:
            # Sampling falls back to the claim-level extract for a
            # single-source claim, so that extract has to be served too.
            evidence = [
                {
                    "source_id": source_ids[0],
                    "extract_or_location": claim.get("extract_or_location"),
                }
            ]
        for record in evidence:
            source = sources.get(record.get("source_id"))
            if source is None:
                continue
            host = source["url"].split("/")[2]
            by_host.setdefault(host, []).append(
                str(record.get("extract_or_location") or "")
            )
    responses = {}
    for host, extracts in by_host.items():
        body = "".join(f"<p>{extract}</p>" for extract in dict.fromkeys(extracts))
        responses[host] = (
            200,
            {"content-type": "text/html; charset=utf-8"},
            f"<html><body>{body}</body></html>".encode("utf-8"),
        )
    return responses


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def blind_review_note(path, *, report, source, case):
    write_json(
        path,
        {
            "schema_version": 1,
            "status": "completed",
            "report_sha256": file_sha256(report),
            "source_sha256": file_sha256(source),
            "report_lang": case["lang"],
            "profile": case["profile"],
            "fidelity_checks": {
                "facts_and_figures": True,
                "attribution_and_uncertainty": True,
                "direction_and_negation": True,
                "causality": True,
            },
            "findings": [],
        },
    )


def content_review_note(path, *, report, ledger_path, report_text, case):
    headings = [
        heading
        for heading, _ in _h2_sections(report_text)
        if heading.casefold() not in SOURCE_HEADINGS
    ]
    write_json(
        path,
        {
            "schema_version": 2,
            "status": "completed",
            "report_path": str(report.resolve()),
            "report_sha256": file_sha256(report),
            "ledger_path": str(ledger_path.resolve()),
            "ledger_sha256": file_sha256(ledger_path),
            "report_lang": case["lang"],
            "reviewed_at": "2026-07-28T12:00:00Z",
            "reviewer_mode": "fresh_eyes",
            "scores": {
                name: {
                    "score": 4,
                    "rationale": (
                        f"The golden report meets the {name} requirement: the "
                        "central judgment is answered from the ledger, the "
                        "counterevidence is carried, and the open question is "
                        "disclosed rather than inferred away."
                    ),
                }
                for name in SCORES
            },
            "checks": {name: True for name in CHECKS},
            "section_reviews": [
                {
                    "section_heading": heading,
                    "purpose": (
                        "Advance the governing question this section is "
                        "responsible for."
                    ),
                    "new_value": (
                        "Add evidence, mechanism, or decision value that no "
                        "other section carries."
                    ),
                    "evidence_or_reasoning": (
                        "Rests on the claims bound to this report in the "
                        "evidence ledger."
                    ),
                    "limitation_or_tradeoff": (
                        "States the limits of its own evidence, including the "
                        "unresolved night-window question."
                    ),
                    "contribution_to_governing_question": (
                        "Moves the reader toward the central judgment on "
                        "corridor capacity and cost."
                    ),
                    "disposition": "keep",
                }
                for heading in headings
            ],
            "visual_assets": [],
            "findings": [],
            "evidence_limitations": [
                "The subject is a synthetic acceptance case and every cited "
                "record sits on a documentation domain."
            ],
            "completion_note": (
                "Every claim in the report is traceable to the ledger and the "
                "report is fit to exercise the complete delivery pipeline."
            ),
        },
    )


class GoldenReportPipelineTests(unittest.TestCase):
    maxDiff = None

    def test_golden_fixtures_exist_for_every_delivery_language(self):
        self.assertEqual(
            [case["name"] for case in CASES],
            [case["name"] for case in available_cases()],
            "Every delivery language needs a checked-in golden fixture.",
        )

    def test_golden_report_passes_every_delivery_gate(self):
        schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
        for case in available_cases():
            with self.subTest(lang=case["lang"]):
                self._run_case(case, schema)

    def test_a_long_contents_list_paginates_without_a_blank_page(self):
        """A report with many H2 sections must not spill an unlabeled,
        near-blank continuation page off the back of the contents list.

        Reducing the golden English fixture to 14 H2 sections previously
        worked around this: at ~20 sections the single, unchunked contents
        block overflowed onto a following page that carried a handful of
        leftover entries and no heading, which the PDF quality gate correctly
        flagged as near-blank. The fix paginates the contents list into
        balanced, separately headed pages before it ever reaches layout, so a
        legitimately long report must render clean.
        """
        case = next(case for case in CASES if case["name"] == "en")
        case_root = GOLDEN_ROOT / case["name"]
        if not (case_root / "report.md").is_file():
            self.skipTest("English golden fixture is not checked in.")
        schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))

        report_text = (case_root / "report.md").read_text(encoding="utf-8")
        # Every H3 in the fixture is a subsection of some H2; promoting them
        # all turns the golden report's 14 H2 sections into 20, reproducing
        # the section count that triggered the defect, without inventing new
        # prose that would need its own ledger and fidelity coverage.
        many_sections_text = re.sub(r"(?m)^### ", "## ", report_text)
        h2_count = len(re.findall(r"(?m)^## ", many_sections_text))
        self.assertGreaterEqual(
            h2_count, 20, "fixture no longer promotes to enough H2 sections"
        )

        pdf = self._render_case_with_report_text(
            case, schema, many_sections_text
        )

        findings, _ = pdf_quality.check_pdf(pdf)
        self.assertEqual(
            [],
            [f.format() for f in findings if f.severity == "error"],
            "a long contents list must render with zero hard PDF findings",
        )
        near_blank = [
            f for f in findings if f.check in ("blank_page", "sparse_page")
        ]
        self.assertEqual(
            [],
            [f.format() for f in near_blank],
            "the contents continuation page must not read as near-blank",
        )

        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        contents_pages = [
            page
            for page in reader.pages[:4]
            if "contents" in (page.extract_text() or "").casefold()
        ]
        self.assertGreaterEqual(
            len(contents_pages),
            2,
            "expected the contents list to span more than one labeled page",
        )

    def _render_case_with_report_text(self, case, schema, report_text):
        """Run the full delivery pipeline for ``case`` against ``report_text``
        instead of the checked-in fixture text, and return the rendered PDF
        path (inside a directory the caller's test owns via ``addCleanup``).
        """
        case_root = GOLDEN_ROOT / case["name"]
        ledger = case_root / "ledger.json"
        ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            validate_schema(ledger_data, schema)
            + validate_references(ledger_data),
        )
        report_day = date.fromisoformat(ledger_data["report_date"])

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        work = Path(directory.name)
        report = work / "report.md"
        report.write_text(report_text, encoding="utf-8")
        source = work / "pre-rewild.md"
        blind_review = work / "blind-review.json"
        rewild_receipt = work / "rewild-receipt.json"
        source_receipt = work / "source-fidelity-receipt.json"
        content_review = work / "content-review.json"
        content_receipt = work / "content-receipt.json"
        pdf = work / "report.pdf"

        final_text, source_text = case["rewrite"]
        self.assertIn(final_text, report_text)
        source.write_text(
            report_text.replace(final_text, source_text, 1),
            encoding="utf-8",
        )
        blind_review_note(blind_review, report=report, source=source, case=case)

        with mock_production_transport(transport_responses(ledger_data)):
            self.assertEqual(
                [],
                hard_errors(
                    run_gate(
                        report,
                        source,
                        report_lang=case["lang"],
                        review_note_path=blind_review,
                        receipt_path=rewild_receipt,
                    )
                ),
            )

            issue_source_fidelity_receipt(ledger, source_receipt, now=report_day)

            content_review_note(
                content_review,
                report=report,
                ledger_path=ledger,
                report_text=report_text,
                case=case,
            )
            self.assertEqual(
                [],
                hard_errors(
                    run_content_gate(
                        report,
                        ledger,
                        content_review,
                        content_receipt,
                        source_fidelity_receipt_path=source_receipt,
                    )
                ),
            )

            receipt_flags = [
                "--ledger",
                str(ledger),
                "--rewild-receipt",
                str(rewild_receipt),
                "--source-fidelity-receipt",
                str(source_receipt),
                "--content-receipt",
                str(content_receipt),
                "--expected-lang",
                case["lang"],
                "--min-sections",
                "3",
                "--min-sources",
                "1",
                *case["length_flags"],
            ]

            self.assertEqual(
                0, validate_report.main([str(report), *receipt_flags])
            )

            md_to_pdf.render_pdf(
                report,
                pdf,
                lang=case["lang"],
                template="executive",
                rewild_receipt=rewild_receipt,
                ledger=ledger,
                source_fidelity_receipt=source_receipt,
                content_receipt=content_receipt,
                report_date=localized_date(case["lang"], report_day),
            )
            self.assertTrue(pdf.is_file())

            self.assertEqual(
                0,
                validate_report.main(
                    [
                        str(report),
                        *receipt_flags,
                        "--pdf",
                        str(pdf),
                        "--min-pages",
                        "10",
                        "--min-links",
                        "1",
                        "--min-text-chars",
                        case["min_text_chars"],
                    ]
                ),
            )
        return pdf

    def _run_case(self, case, schema):
        case_root = GOLDEN_ROOT / case["name"]
        report = case_root / "report.md"
        ledger = case_root / "ledger.json"
        report_text = report.read_text(encoding="utf-8")
        ledger_data = json.loads(ledger.read_text(encoding="utf-8"))

        # 1. Evidence ledger.
        self.assertEqual(
            [],
            validate_schema(ledger_data, schema)
            + validate_references(ledger_data),
        )
        self.assertEqual(case["lang"], ledger_data["brief"]["report_language"])
        report_day = date.fromisoformat(ledger_data["report_date"])
        self.assertIn(localized_date(case["lang"], report_day), report_text)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            blind_review = work / "blind-review.json"
            rewild_receipt = work / "rewild-receipt.json"
            source_receipt = work / "source-fidelity-receipt.json"
            content_review = work / "content-review.json"
            content_receipt = work / "content-receipt.json"
            pdf = work / "report.pdf"

            final_text, source_text = case["rewrite"]
            self.assertIn(final_text, report_text)
            source.write_text(
                report_text.replace(final_text, source_text, 1),
                encoding="utf-8",
            )
            blind_review_note(
                blind_review,
                report=report,
                source=source,
                case=case,
            )

            with mock_production_transport(transport_responses(ledger_data)):
                # 2. Rewild hard gate.
                self.assertEqual(
                    [],
                    hard_errors(
                        run_gate(
                            report,
                            source,
                            report_lang=case["lang"],
                            review_note_path=blind_review,
                            receipt_path=rewild_receipt,
                        )
                    ),
                )
                self.assertTrue(rewild_receipt.is_file())

                # 3. Source fidelity, re-read through the production transport.
                issue_source_fidelity_receipt(
                    ledger,
                    source_receipt,
                    now=report_day,
                )

                # 4. Content quality gate.
                content_review_note(
                    content_review,
                    report=report,
                    ledger_path=ledger,
                    report_text=report_text,
                    case=case,
                )
                self.assertEqual(
                    [],
                    hard_errors(
                        run_content_gate(
                            report,
                            ledger,
                            content_review,
                            content_receipt,
                            source_fidelity_receipt_path=source_receipt,
                        )
                    ),
                )

                receipt_flags = [
                    "--ledger",
                    str(ledger),
                    "--rewild-receipt",
                    str(rewild_receipt),
                    "--source-fidelity-receipt",
                    str(source_receipt),
                    "--content-receipt",
                    str(content_receipt),
                    "--expected-lang",
                    case["lang"],
                    "--min-sections",
                    "3",
                    "--min-sources",
                    "1",
                    *case["length_flags"],
                ]

                # 5. Markdown validation.
                self.assertEqual(
                    0,
                    validate_report.main([str(report), *receipt_flags]),
                )

                # 6. Render.
                md_to_pdf.render_pdf(
                    report,
                    pdf,
                    lang=case["lang"],
                    template="executive",
                    rewild_receipt=rewild_receipt,
                    ledger=ledger,
                    source_fidelity_receipt=source_receipt,
                    content_receipt=content_receipt,
                    report_date=localized_date(case["lang"], report_day),
                )
                self.assertTrue(pdf.is_file())

                # 7. PDF validation, including page quality.
                self.assertEqual(
                    0,
                    validate_report.main(
                        [
                            str(report),
                            *receipt_flags,
                            "--pdf",
                            str(pdf),
                            "--min-pages",
                            "10",
                            "--min-links",
                            "1",
                            "--min-text-chars",
                            case["min_text_chars"],
                        ]
                    ),
                )

            self._assert_pdf_carries_report_text(pdf, case)
            self._assert_native_render_matches_pdfium(pdf, case)

    def _assert_pdf_carries_report_text(self, pdf, case):
        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        for expected in case["expected_pdf_text"]:
            self.assertIn(
                expected,
                extracted,
                f"{case['lang']} PDF lost expected text: {expected}",
            )
        if case["lang"] != "en":
            self.assertGreaterEqual(
                len(re.findall(r"[㐀-鿿]", extracted)),
                1000,
                f"{case['lang']} PDF did not render CJK text.",
            )

    def _assert_native_render_matches_pdfium(self, pdf, case):
        if sys.platform != "darwin":
            return
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            render_pages(pdf, root / "pdfium", dpi=96, backend="pdfium")
            render_pages(pdf, root / "pdfkit", dpi=96, backend="pdfkit")
            errors, _ = pdf_compatibility.compare_render_sets(
                root / "pdfium", root / "pdfkit"
            )
        self.assertEqual(
            [],
            errors,
            f"{case['lang']} changed position or lost content in macOS PDFKit",
        )


if __name__ == "__main__":
    unittest.main()
