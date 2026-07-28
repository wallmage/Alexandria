import json
import tempfile
import unittest
from pathlib import Path

from scripts.md_to_pdf import validate_rewild_for_render
from scripts.rewild_gate import (
    _carrier_predicate_tokens,
    _checker_prose,
    _direction_terms,
    _semantic_fidelity_errors,
    file_sha256,
    run_gate,
)
from scripts.validate_report import validate_rewild_receipt


def write_review(path, *, report=None, source=None, report_lang="en"):
    report = Path(report or path.parent / "report.md")
    source = Path(source or path.parent / "pre-rewild.md")
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "report_sha256": file_sha256(report),
                "source_sha256": file_sha256(source),
                "report_lang": report_lang,
                "profile": {
                    "en": "rewild",
                    "zh-CN": "rewild-zh",
                    "zh-HK": "rewild-hk",
                }[report_lang],
                "fidelity_checks": {
                    "facts_and_figures": True,
                    "attribution_and_uncertainty": True,
                    "direction_and_negation": True,
                    "causality": True,
                },
                "findings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class RewildReceiptTests(unittest.TestCase):
    def test_semantic_tokenizers_cache_repeated_clauses(self):
        _carrier_predicate_tokens.cache_clear()
        _direction_terms.cache_clear()
        clause = "Costs remain above the industry average."
        _carrier_predicate_tokens(clause, "en")
        _carrier_predicate_tokens(clause, "en")
        _direction_terms(clause)
        _direction_terms(clause)
        self.assertGreaterEqual(_carrier_predicate_tokens.cache_info().hits, 1)
        self.assertGreaterEqual(_direction_terms.cache_info().hits, 1)

    def test_document_fallback_does_not_override_successful_clause_alignment(self):
        source = (
            "Costs remain above the industry average. "
            "The deployment guide describes the supported platforms."
        )
        report = (
            "The deployment guide describes the supported platforms. "
            "A separate appendix discusses results below the average."
        )
        errors = _semantic_fidelity_errors(source, report, "en")
        self.assertFalse(
            any("Semantic direction reversal:" in error for error in errors),
            errors,
        )

    def test_document_level_direction_words_do_not_reject_a_faithful_rewrite(self):
        source = "Costs are above the average across every plant we reviewed."
        report = (
            "Across every plant we reviewed, costs remain above the average; "
            "none fell below it."
        )
        self.assertEqual([], _semantic_fidelity_errors(source, report, "en"))

    def test_identical_files_cannot_claim_resolved_rewild_findings(self):
        clean = (
            "# Report\n\n## First finding\n\n"
            + " ".join(f"word{index}" for index in range(4000))
            + ".\n\n## Second finding\n\n"
            + " ".join(f"term{index}" for index in range(3500))
            + ".\n\n## Sources\n\n[Source](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            report.write_text(clean, encoding="utf-8")
            source.write_text(clean, encoding="utf-8")
            write_review(review, report=report, source=source)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["findings"] = [
                {
                    "category": "style",
                    "finding": "Repeated formulaic contrast was removed.",
                    "disposition": "resolved",
                    "reason": "The final report now uses direct affirmative prose.",
                }
            ]
            review.write_text(json.dumps(note), encoding="utf-8")

            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertTrue(
                any("identical" in error.lower() and "resolved" in error.lower() for error in errors),
                errors,
            )
            self.assertFalse(receipt.exists())

    def test_clean_report_creates_a_receipt_bound_to_the_exact_file(self):
        clean = (
            "# Report\n\n## First finding\n\n"
            + " ".join(f"word{index}" for index in range(4000))
            + ".\n\n## Second finding\n\n"
            + " ".join(f"term{index}" for index in range(3500))
            + ".\n\n## Sources\n\n[Source](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "blind-review.md"
            receipt = work / "rewild-receipt.json"
            report.write_text(clean, encoding="utf-8")
            source.write_text(clean, encoding="utf-8")
            write_review(review)

            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertEqual([], errors)
            self.assertTrue(receipt.is_file())
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(
                [],
                validate_rewild_receipt(report, data, expected_lang="en"),
            )
            validate_rewild_for_render(report, receipt, "en")

            report.write_text(clean + "\nChanged after the gate.", encoding="utf-8")
            self.assertIn(
                "does not match",
                " ".join(
                    validate_rewild_receipt(report, data, expected_lang="en")
                ),
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_rewild_for_render(report, receipt, "en")

    def test_receipt_is_not_written_when_blind_review_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            receipt = work / "rewild-receipt.json"
            report.write_text("A short clean sentence.", encoding="utf-8")
            source.write_text("A short clean sentence.", encoding="utf-8")

            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=work / "missing.md",
                receipt_path=receipt,
            )
            self.assertTrue(errors)
            self.assertFalse(receipt.exists())

    def test_hong_kong_register_warning_cannot_be_waived(self):
        text = (
            "這份報告係說明，新系統一樣處理到工作。"
            "項目團隊會在下星期再檢查結果。"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "blind-review.md"
            receipt = work / "rewild-receipt.json"
            waivers = work / "waivers.json"
            report.write_text(text, encoding="utf-8")
            source.write_text(text, encoding="utf-8")
            write_review(review, report_lang="zh-HK")
            waivers.write_text(
                json.dumps(
                    {
                        "style_waivers": [
                            {
                                "section": "Hong Kong flavor (informational)",
                                "message": "Cantonese syntax in 書面語",
                                "reason": "Attempting to waive a hard register defect.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            errors = run_gate(
                report,
                source,
                report_lang="zh-HK",
                review_note_path=review,
                receipt_path=receipt,
                waiver_path=waivers,
            )
            self.assertIn("Hard Rewild warning", " ".join(errors))
            self.assertFalse(receipt.exists())

    def test_semantic_direction_reversal_is_blocked(self):
        source_text = "研究顯示，銷售額上升。"
        report_text = "研究顯示，銷售額下跌。"
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(source_text, encoding="utf-8")
            report.write_text(report_text, encoding="utf-8")
            write_review(review, report_lang="zh-HK")

            errors = run_gate(
                report,
                source,
                report_lang="zh-HK",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("direction", " ".join(errors).lower())
            self.assertFalse(receipt.exists())

    def test_causal_substitution_is_blocked(self):
        source_text = "服務中斷是設定錯誤所致。"
        report_text = "服務中斷是網絡攻擊所致。"
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(source_text, encoding="utf-8")
            report.write_text(report_text, encoding="utf-8")
            write_review(review, report_lang="zh-HK")

            errors = run_gate(
                report,
                source,
                report_lang="zh-HK",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("causal", " ".join(errors).lower())
            self.assertFalse(receipt.exists())

    def test_multi_claim_direction_swap_is_blocked(self):
        errors = _semantic_fidelity_errors(
            "Revenue increased while costs decreased.",
            "Revenue decreased while costs increased.",
            "en",
        )
        self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Revenue climbed while costs declined.",
            "Revenue declined while costs climbed.",
            "en",
        )
        self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The footprint expanded while headcount shrank.",
            "The footprint shrank while headcount expanded.",
            "en",
        )
        self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Revenue surged while costs plunged.",
            "Revenue plunged while costs surged.",
            "en",
        )
        self.assertIn("semantic", " ".join(errors).lower())

        for source, report in (
            ("Revenue surged this year.", "Revenue plunged this year."),
            ("The gap widened.", "The gap narrowed."),
            ("Company A outperformed.", "Company A underperformed."),
        ):
            with self.subTest(source=source):
                errors = _semantic_fidelity_errors(source, report, "en")
                self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "产品甲销量上升，产品乙销量下降。",
            "产品乙销量上升，产品甲销量下降。",
            "zh-CN",
        )
        self.assertIn("semantic", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "产品甲销量上升，产品乙销量下降。",
            "产品甲销量下降，产品乙销量上升。",
            "zh-CN",
        )
        self.assertIn("direction", " ".join(errors).lower())

    def test_negation_relocation_and_removal_are_blocked(self):
        errors = _semantic_fidelity_errors(
            "The team did not approve A; it approved B.",
            "The team approved A; it did not approve B.",
            "en",
        )
        self.assertIn("negation", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The system can process requests.",
            "The system cannot process requests.",
            "en",
        )
        self.assertIn("negation", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "系统无风险，数据无偏差。",
            "系统存在风险，数据存在偏差。",
            "zh-CN",
        )
        self.assertIn("negation", " ".join(errors).lower())

    def test_common_chinese_direction_synonyms_are_blocked(self):
        errors = _semantic_fidelity_errors(
            "产品甲销量上升，产品乙销量下降。",
            "产品甲销量回落，产品乙销量走高。",
            "zh-CN",
        )
        self.assertIn("direction", " ".join(errors).lower())

    def test_magnitude_reversal_and_correlation_to_causation_are_blocked(self):
        errors = _semantic_fidelity_errors(
            "Revenue doubled.",
            "Revenue halved.",
            "en",
        )
        self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The treatment was associated with recovery.",
            "The treatment explains recovery.",
            "en",
        )
        self.assertIn("causal", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Profits grew.",
            "Profits contracted.",
            "en",
        )
        self.assertIn("direction", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The system can process requests.",
            "The system is unable to process requests.",
            "en",
        )
        self.assertIn("negation", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Recovery followed treatment.",
            "Recovery occurred because the treatment worked.",
            "en",
        )
        self.assertIn("causal", " ".join(errors).lower())

    def test_full_gate_blocks_correlation_rewritten_as_causation(self):
        filler = " ".join(f"word{index}" for index in range(7500))
        source_text = (
            "# Report\n\n## Finding\n\n"
            "The treatment was associated with recovery. "
            f"{filler}.\n\n## Sources\n\n[Source](https://example.com)"
        )
        report_text = source_text.replace(
            "was associated with",
            "explains",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(source_text, encoding="utf-8")
            report.write_text(report_text, encoding="utf-8")
            write_review(review)

            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("causal", " ".join(errors).lower())
            self.assertFalse(receipt.exists())

    def test_full_gate_blocks_common_semantic_paraphrase_reversals(self):
        filler = " ".join(f"word{index}" for index in range(7500))
        source_text = (
            "# Report\n\n## Finding\n\n"
            "Profits grew. The system can process requests. "
            "Recovery followed treatment. "
            f"{filler}.\n\n## Sources\n\n[Source](https://example.com)"
        )
        report_text = source_text.replace(
            "Profits grew.",
            "Profits contracted.",
        ).replace(
            "can process requests.",
            "is unable to process requests.",
        ).replace(
            "Recovery followed treatment.",
            "Recovery occurred because the treatment worked.",
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(source_text, encoding="utf-8")
            report.write_text(report_text, encoding="utf-8")
            write_review(review)

            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            joined = " ".join(errors).lower()
            self.assertIn("direction", joined)
            self.assertIn("negation", joined)
            self.assertIn("causal", joined)
            self.assertFalse(receipt.exists())

    def test_blind_review_is_bound_to_report_source_language_and_profile(self):
        first = (
            "# Report\n\n## Finding\n\n"
            + " ".join(f"alpha{index}" for index in range(7500))
            + ".\n\n## Sources\n\n[Source](https://example.com)"
        )
        second = first.replace("alpha", "bravo")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(first, encoding="utf-8")
            report.write_text(first, encoding="utf-8")
            write_review(review)

            source.write_text(second, encoding="utf-8")
            report.write_text(second, encoding="utf-8")
            errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("blind-review note", " ".join(errors).lower())
            self.assertFalse(receipt.exists())

    def test_checker_prose_includes_table_cells_but_excludes_sources(self):
        text = (
            "# 報告\n\n## 發現\n\n"
            "| 指標 | 結論 |\n| --- | --- |\n| 網路 | 軟體專案品質 |\n\n"
            "## 資料來源\n\n[台灣軟體產業報告](https://example.com)"
        )
        prose = _checker_prose(text)
        self.assertIn("網路", prose)
        self.assertIn("軟體專案品質", prose)
        self.assertNotIn("台灣軟體產業報告", prose)

    def test_full_gate_rejects_traditional_body_as_simplified_chinese(self):
        traditional = (
            "經濟風險評估趨勢監測維護規劃環境財務審計價值"
            "運營競爭優勢投資決策治理機制"
        )
        body = traditional * 180
        text = (
            f"# 报告\n\n## 分析\n\n{body}\n\n"
            "## 来源\n\n[资料](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(text, encoding="utf-8")
            report.write_text(text, encoding="utf-8")
            write_review(review, report_lang="zh-CN")

            errors = run_gate(
                report,
                source,
                report_lang="zh-CN",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("traditional", " ".join(errors).lower())
            self.assertFalse(receipt.exists())

            checker = (
                Path(__file__).resolve().parents[1]
                / "references"
                / "rewild"
                / "rewild-zh"
                / "scripts"
                / "naturalness-check.py"
            )
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "passed",
                        "report_lang": "zh-CN",
                        "report_path": str(report.resolve()),
                        "report_sha256": file_sha256(report),
                        "source_path": str(source.resolve()),
                        "source_sha256": file_sha256(source),
                        "checker_path": str(checker.resolve()),
                        "checker_sha256": file_sha256(checker),
                        "review_note_path": str(review.resolve()),
                        "review_note_sha256": file_sha256(review),
                        "review_status": "completed",
                        "style_waivers": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Traditional"):
                validate_rewild_for_render(report, receipt, "zh-CN")

    def test_simplified_script_check_ignores_preserved_traditional_quote(self):
        body = "市场研究显示数据支持结论风险可控方案有效。" * 300
        quote = (
            "> 「香港證券及期貨事務監察委員會指出，"
            "該機構將繼續監察市場風險，並維護投資者權益。」"
        )
        text = (
            f"# 报告\n\n## 分析\n\n{body}\n\n{quote}\n\n"
            "## 来源\n\n[资料](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(text, encoding="utf-8")
            report.write_text(text, encoding="utf-8")
            write_review(review, report_lang="zh-CN")

            errors = run_gate(
                report,
                source,
                report_lang="zh-CN",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertNotIn("traditional", " ".join(errors).lower())

    def test_quote_containers_cannot_hide_traditional_report_body(self):
        traditional = (
            "經濟風險評估趨勢監測維護規劃環境財務審計價值"
            "運營競爭優勢投資決策治理機制"
        ) * 180
        for wrapped in (f"> {traditional}", f"「{traditional}」"):
            with self.subTest(container=wrapped[:1]):
                text = (
                    f"# 报告\n\n## 分析\n\n{wrapped}\n\n"
                    "## 来源\n\n[资料](https://example.com)"
                )
                with tempfile.TemporaryDirectory() as directory:
                    work = Path(directory)
                    source = work / "pre-rewild.md"
                    report = work / "report.md"
                    review = work / "review.json"
                    receipt = work / "receipt.json"
                    source.write_text(text, encoding="utf-8")
                    report.write_text(text, encoding="utf-8")
                    write_review(review, report_lang="zh-CN")

                    errors = run_gate(
                        report,
                        source,
                        report_lang="zh-CN",
                        review_note_path=review,
                        receipt_path=receipt,
                    )
                    self.assertIn(
                        "traditional",
                        " ".join(errors).lower(),
                    )
                    self.assertFalse(receipt.exists())

    def test_visual_callout_is_not_treated_as_a_verbatim_quote(self):
        simplified = "市场研究显示数据支持结论风险可控方案有效。" * 250
        traditional = "經濟風險評估趨勢監測維護規劃環境財務審計價值。" * 25
        text = (
            f"# 报告\n\n## 分析\n\n{simplified}\n\n"
            f"> [!INSIGHT]\n> 「{traditional}」\n\n"
            "## 来源\n\n[资料](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(text, encoding="utf-8")
            report.write_text(text, encoding="utf-8")
            write_review(review, report_lang="zh-CN")

            errors = run_gate(
                report,
                source,
                report_lang="zh-CN",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("traditional", " ".join(errors).lower())

    def test_nested_protected_spans_do_not_double_credit_script_budget(self):
        simplified = "市场研究显示数据支持结论风险可控方案有效。" * 350
        traditional = "經濟風險評估趨勢監測維護規劃環境財務審計價值。" * 15
        text = (
            f"# 报告\n\n## 分析\n\n{simplified}\n\n"
            f"{traditional}\n\n> 「{traditional}」\n\n"
            "## 来源\n\n[资料](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "pre-rewild.md"
            report = work / "report.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            source.write_text(text, encoding="utf-8")
            report.write_text(text, encoding="utf-8")
            write_review(review, report_lang="zh-CN")

            errors = run_gate(
                report,
                source,
                report_lang="zh-CN",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertIn("traditional", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "系统并非安全，数据可靠。",
            "数据并非安全，系统可靠。",
            "zh-CN",
        )
        self.assertIn("semantic", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "审计认为，该系统并非安全。",
            "审计认为，该系统安全。",
            "zh-CN",
        )
        self.assertIn("negation", " ".join(errors).lower())

    def test_multi_claim_causal_swap_is_blocked(self):
        errors = _semantic_fidelity_errors(
            "服務甲是設定錯誤所致。服務乙是網絡攻擊所致。",
            "服務甲是網絡攻擊所致。服務乙是設定錯誤所致。",
            "zh-HK",
        )
        self.assertIn("causal", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The delay stemmed from weather. The outage stemmed from configuration.",
            "The delay stemmed from configuration. The outage stemmed from weather.",
            "en",
        )
        self.assertIn("causal", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Delay originated in weather; outage originated in configuration.",
            "Delay originated in configuration; outage originated in weather.",
            "en",
        )
        self.assertIn("semantic", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "The delay originated in configuration.",
            "The delay originated in weather.",
            "en",
        )
        self.assertIn("causal", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "Weather triggered the delay.",
            "Configuration triggered the delay.",
            "en",
        )
        self.assertIn("causal", " ".join(errors).lower())

        errors = _semantic_fidelity_errors(
            "服务中断是配置错误所致，数据丢失是人为操作所致。",
            "数据丢失是配置错误所致，服务中断是人为操作所致。",
            "zh-CN",
        )
        self.assertIn("semantic", " ".join(errors).lower())

    def test_handcrafted_receipt_cannot_skip_the_checker(self):
        boilerplate = (
            "In today's rapidly evolving landscape, it is worth noting that "
            "this groundbreaking platform serves as a testament to innovation. "
        )
        body = " ".join(boilerplate for _ in range(250))
        text = (
            f"# Report\n\n## Finding one\n\n{body}\n\n"
            f"## Finding two\n\n{body}\n\n"
            "## Sources\n\n[Source](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            report.write_text(text, encoding="utf-8")
            source.write_text(text, encoding="utf-8")
            write_review(review)
            checker = (
                Path(__file__).resolve().parents[1]
                / "references"
                / "rewild"
                / "rewild"
                / "scripts"
                / "naturalness-check.py"
            )
            forged = {
                "schema_version": 1,
                "status": "passed",
                "report_lang": "en",
                "report_path": str(report.resolve()),
                "report_sha256": file_sha256(report),
                "source_path": str(source.resolve()),
                "source_sha256": file_sha256(source),
                "checker_path": str(checker.resolve()),
                "checker_sha256": file_sha256(checker),
                "review_note_path": str(review.resolve()),
                "review_note_sha256": file_sha256(review),
                "review_status": "completed",
                "style_waivers": [],
            }

            errors = validate_rewild_receipt(
                report,
                forged,
                expected_lang="en",
            )
            self.assertIn("recheck failed", " ".join(errors).lower())


if __name__ == "__main__":
    unittest.main()
