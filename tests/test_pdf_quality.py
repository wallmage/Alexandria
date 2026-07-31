"""Tests for the programmatic PDF and design-token quality gate."""

import sys
import tempfile
import unittest
from pathlib import Path

from scripts import pdf_quality
from scripts.pdf_templates import (
    LINK_ON_DARK,
    LINK_ON_LIGHT,
    ON_ACCENT,
    TEMPLATES,
    build_css,
)

ROOT = Path(__file__).resolve().parents[1]


def render_html_to_pdf(html, target):
    from weasyprint import HTML

    HTML(string=html).write_pdf(target, pdf_tags=True)
    return target


def page_html(body, *, template="executive"):
    css = build_css(
        template,
        font_sans="sans-serif",
        font_display="serif",
        font_mono="monospace",
        header_text="Quality gate",
        page_label="",
        page_suffix="",
        footer_text="Alexandria",
        insight_label="Insight",
        takeaway_label="Takeaway",
    )
    return (
        '<html lang="en"><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body>"
        f'<div class="report template-{template}">{body}</div>'
        "</body></html>"
    )


class ColourMathTests(unittest.TestCase):
    def test_parse_hex_accepts_short_and_long_form(self):
        self.assertEqual(pdf_quality.parse_hex("#fff"), (255, 255, 255))
        self.assertEqual(pdf_quality.parse_hex("112233"), (17, 34, 51))

    def test_parse_hex_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            pdf_quality.parse_hex("#12345")
        with self.assertRaises(ValueError):
            pdf_quality.parse_hex("#gggggg")

    def test_contrast_ratio_matches_wcag_reference_values(self):
        self.assertAlmostEqual(
            pdf_quality.contrast_ratio("#000000", "#ffffff"), 21.0, places=4
        )
        self.assertAlmostEqual(
            pdf_quality.contrast_ratio("#ffffff", "#ffffff"), 1.0, places=4
        )
        # Published reference pair: #767676 is the lightest grey that clears
        # 4.5:1 on white.
        self.assertGreaterEqual(
            pdf_quality.contrast_ratio("#767676", "#ffffff"), 4.5
        )
        self.assertLess(pdf_quality.contrast_ratio("#777777", "#ffffff"), 4.5)

    def test_contrast_ratio_is_symmetric(self):
        self.assertAlmostEqual(
            pdf_quality.contrast_ratio("#16827c", "#ffffff"),
            pdf_quality.contrast_ratio("#ffffff", "#16827c"),
            places=9,
        )

    def test_adjust_to_contrast_reaches_the_target_and_is_stable(self):
        darkened = pdf_quality.adjust_to_contrast("#ff9800", "#ffffff", 4.5)
        self.assertGreaterEqual(
            pdf_quality.contrast_ratio(darkened, "#ffffff"), 4.5
        )
        # Idempotent: a colour that already clears the bar is returned as-is.
        self.assertEqual(
            pdf_quality.adjust_to_contrast(darkened, "#ffffff", 4.5), darkened
        )

    def test_adjust_to_contrast_lightens_against_a_dark_background(self):
        lightened = pdf_quality.adjust_to_contrast("#0062ff", "#1a1a1a", 4.5)
        self.assertGreaterEqual(
            pdf_quality.contrast_ratio(lightened, "#1a1a1a"), 4.5
        )


class TemplateContrastTests(unittest.TestCase):
    def test_every_template_clears_wcag_aa(self):
        findings, metrics = pdf_quality.check_template_contrast()
        self.assertEqual(
            [finding.format() for finding in findings],
            [],
            "colour tokens must clear WCAG AA for all eleven templates",
        )
        self.assertEqual(set(metrics), set(TEMPLATES))

    def test_contrast_table_covers_every_rule_for_every_template(self):
        for name in TEMPLATES:
            with self.subTest(template=name):
                rows = pdf_quality.template_contrast_table(name)
                self.assertEqual(len(rows), len(pdf_quality.CONTRAST_RULES))
                for label, _, _, ratio, minimum, passed in rows:
                    self.assertTrue(
                        passed, f"{name}/{label} is {ratio:.2f}:1, needs {minimum}"
                    )

    def test_takeaway_band_no_longer_paints_white_on_a_light_accent(self):
        # These five accents cannot carry white text: apricot measured 2.16:1.
        for name in ("maison", "blueprint", "sunbeam", "current", "apricot"):
            with self.subTest(template=name):
                self.assertNotEqual(ON_ACCENT[name], "#ffffff")
                self.assertGreaterEqual(
                    pdf_quality.contrast_ratio(
                        ON_ACCENT[name], TEMPLATES[name].accent
                    ),
                    4.5,
                )

    def test_link_token_is_independent_of_the_decorative_accent(self):
        for name, spec in TEMPLATES.items():
            with self.subTest(template=name):
                link = LINK_ON_LIGHT[name]
                self.assertGreaterEqual(
                    pdf_quality.contrast_ratio(link, "#ffffff"), 4.5
                )
                self.assertGreaterEqual(
                    pdf_quality.contrast_ratio(link, spec.pale), 4.5
                )
                if pdf_quality.contrast_ratio(spec.accent, "#ffffff") < 4.5:
                    self.assertNotEqual(link, spec.accent)

    def test_links_inside_the_dark_insight_panel_stay_legible(self):
        # Six templates previously left links at __LINK__ on __DARK__; terrain
        # measured 1.65:1.
        for name, spec in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertGreaterEqual(
                    pdf_quality.contrast_ratio(LINK_ON_DARK[name], spec.dark), 4.5
                )

    def test_generated_css_uses_the_on_dark_link_token(self):
        for name in TEMPLATES:
            with self.subTest(template=name):
                css = page_html("", template=name)
                self.assertIn(".insight-panel a", css)
                self.assertIn(LINK_ON_DARK[name], css)


class FontScriptTests(unittest.TestCase):
    def test_classifier_separates_simplified_from_traditional(self):
        cases = {
            "/ABCDEF+PingFang-SC": "simplified",
            "/ABCDEF+PingFang-HK": "traditional",
            "/ABCDEF+Songti-SC-Bold": "simplified",
            "/ABCDEF+Songti-TC-Bold": "traditional",
            "/ABCDEF+NotoSansCJKsc-Regular": "simplified",
            "/ABCDEF+NotoSerifCJKtc-Bold": "traditional",
            "/ABCDEF+SourceHanSansHK-Regular": "traditional",
            "/ABCDEF+HiraginoSansGB-W3": "simplified",
            "/ABCDEF+MicrosoftJhengHei": "traditional",
            "/ABCDEF+Arial-Unicode-MS": "universal",
            "/ABCDEF+Alexandria-Sans": "latin",
            "/ABCDEF+SourceSerif4": "latin",
        }
        for name, expected in cases.items():
            with self.subTest(font=name):
                self.assertEqual(pdf_quality.classify_font_script(name), expected)

    def test_mixed_script_render_is_an_error(self):
        original = pdf_quality.embedded_font_names
        pdf_quality.embedded_font_names = lambda _path: [
            "/A+PingFang-HK",
            "/B+Songti-SC-Bold",
            "/C+Alexandria-Sans",
        ]
        try:
            findings, _ = pdf_quality.check_cjk_fonts("ignored.pdf", "zh-HK")
        finally:
            pdf_quality.embedded_font_names = original
        self.assertTrue(findings)
        self.assertEqual(findings[0].severity, "error")
        self.assertIn("Simplified and Traditional", findings[0].message)

    def test_wrong_script_for_the_locale_is_an_error(self):
        original = pdf_quality.embedded_font_names
        pdf_quality.embedded_font_names = lambda _path: ["/A+PingFang-SC"]
        try:
            findings, _ = pdf_quality.check_cjk_fonts("ignored.pdf", "zh-HK")
        finally:
            pdf_quality.embedded_font_names = original
        self.assertTrue(findings)
        self.assertIn("simplified", findings[0].message)

    def test_script_pure_render_passes(self):
        original = pdf_quality.embedded_font_names
        pdf_quality.embedded_font_names = lambda _path: [
            "/A+PingFang-HK",
            "/B+PingFang-HK-Semi-Bold",
            "/C+Alexandria-Sans",
        ]
        try:
            findings, metrics = pdf_quality.check_cjk_fonts("ignored.pdf", "zh-HK")
        finally:
            pdf_quality.embedded_font_names = original
        self.assertEqual(findings, [])
        self.assertIn("traditional", metrics["by_script"])

    def test_english_documents_skip_the_check(self):
        findings, metrics = pdf_quality.check_cjk_fonts("ignored.pdf", "en")
        self.assertEqual(findings, [])
        self.assertEqual(metrics, {})

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS PingFang")
    def test_pingfang_cff_render_is_rejected_for_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "pingfang.pdf"
            render_html_to_pdf(
                """
                <html lang="zh-CN">
                  <style>body { font-family: "PingFang SC"; }</style>
                  <body><p>中文字体必须能在系统预览中完整显示。</p></body>
                </html>
                """,
                target,
            )
            findings, _ = pdf_quality.check_cjk_fonts(target, "zh-CN")

        preview_errors = [
            finding
            for finding in findings
            if finding.severity == "error" and "Preview" in finding.message
        ]
        self.assertTrue(
            preview_errors,
            "a PingFang CFF subset renders incompletely in macOS Preview",
        )

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS fonts")
    def test_simplified_stack_renders_preview_compatible_cjk(self):
        from scripts import md_to_pdf

        settings = md_to_pdf.localized_settings("zh-CN", "executive")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "simplified.pdf"
            render_html_to_pdf(
                f"""
                <html lang="zh-CN">
                  <style>body {{ font-family: {settings["font_sans"]}; }}</style>
                  <body><p>中文字体必须能在系统预览中完整显示。</p></body>
                </html>
                """,
                target,
            )
            findings, _ = pdf_quality.check_cjk_fonts(target, "zh-CN")

        errors = [finding for finding in findings if finding.severity == "error"]
        self.assertEqual(errors, [])

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS fonts")
    def test_traditional_stack_renders_preview_compatible_cjk(self):
        from scripts import md_to_pdf

        settings = md_to_pdf.localized_settings("zh-HK", "executive")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "traditional.pdf"
            render_html_to_pdf(
                f"""
                <html lang="zh-HK">
                  <style>body {{ font-family: {settings["font_sans"]}; }}</style>
                  <body><p>中文字體必須能在系統預覽中完整顯示。</p></body>
                </html>
                """,
                target,
            )
            findings, _ = pdf_quality.check_cjk_fonts(target, "zh-HK")

        errors = [finding for finding in findings if finding.severity == "error"]
        self.assertEqual(errors, [])


class RenderedPageTests(unittest.TestCase):
    """Render-derived checks over real PDFs produced by the real stylesheet."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        paragraph = (
            "<p>"
            + (
                "The evidence is only useful when it reaches the decision in "
                "time to change it. "
            )
            * 12
            + "</p>"
        )
        cls.dense_pdf = render_html_to_pdf(
            page_html(
                "<h1 id='a'>Section one</h1>"
                + paragraph * 4
                + "<h1 id='b'>Section two</h1>"
                + paragraph * 4
            ),
            root / "dense.pdf",
        )
        cls.blank_pdf = render_html_to_pdf(
            page_html(
                "<h1 id='a'>Section one</h1>"
                + paragraph * 3
                + '<div style="break-before: page">'
                + "<p>Two orphaned words.</p></div>"
                + '<div style="break-before: page">' + paragraph + "</div>"
            ),
            root / "blank.pdf",
        )
        cls.designed_opener_pdf = render_html_to_pdf(
            page_html(
                "<h1 id='a'>Section one</h1>"
                + paragraph * 3
                + (
                    '<section style="break-before: page">'
                    "<h1>Contents</h1><p>01 Evidence architecture</p>"
                    "</section>"
                )
                + (
                    '<section style="break-before: page; height: 220mm; '
                    'background: #172238; color: white; padding: 18mm">'
                    "<h2>Evidence architecture</h2>"
                    "<p>A deliberate visual opener with a short, useful "
                    "statement and substantial designed content.</p>"
                    "</section>"
                )
                + '<div style="break-before: page">' + paragraph + "</div>"
            ),
            root / "designed-opener.pdf",
        )
        cls.decorative_orphan_pdf = render_html_to_pdf(
            page_html(
                "<h1 id='a'>Section one</h1>"
                + paragraph * 3
                + (
                    '<section style="break-before: page">'
                    "<h1>Contents</h1><p>01 Evidence architecture</p>"
                    "</section>"
                )
                + (
                    '<section style="break-before: page">'
                    '<div style="height: 5mm; background: #172238"></div>'
                    "<p>Two orphaned words.</p>"
                    "</section>"
                )
                + '<div style="break-before: page">' + paragraph + "</div>"
            ),
            root / "decorative-orphan.pdf",
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_dense_document_passes_every_render_check(self):
        findings, metrics = pdf_quality.check_pdf(self.dense_pdf)
        self.assertEqual([f.format() for f in findings], [])
        self.assertGreater(metrics["page_count"], 1)

    def test_running_header_clears_the_first_body_line(self):
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(self.dense_pdf)
        try:
            gaps = []
            for index in range(1, len(document)):
                page = document[index]
                try:
                    gaps.append(pdf_quality.header_gap_mm(page))
                finally:
                    page.close()
        finally:
            document.close()
        measured = [gap for gap in gaps if gap is not None]
        self.assertTrue(measured)
        # The shipped bug measured 0.88mm on Executive.
        self.assertGreaterEqual(min(measured), pdf_quality.MIN_HEADER_GAP_MM)

    def test_a_near_blank_page_is_reported(self):
        findings, _ = pdf_quality.check_pdf(self.blank_pdf)
        blank = [f for f in findings if f.check == "blank_page"]
        self.assertTrue(blank, "a page holding one short line must fail the gate")
        self.assertEqual(blank[0].severity, "error")

    def test_a_visually_full_opener_is_not_rejected_for_short_text(self):
        findings, metrics = pdf_quality.check_pdf(self.designed_opener_pdf)
        opener = metrics["pages"][2]
        self.assertLess(opener["text_chars"], pdf_quality.MIN_PAGE_CHARS)
        self.assertGreaterEqual(opener["ink_ratio"], pdf_quality.MIN_INK_RATIO)
        self.assertEqual(
            [],
            [
                finding.format()
                for finding in findings
                if finding.check == "blank_page" and finding.where == "page 3"
            ],
        )

    def test_a_decorative_orphan_after_contents_still_fails(self):
        findings, metrics = pdf_quality.check_pdf(self.decorative_orphan_pdf)
        orphan = metrics["pages"][2]
        self.assertLess(orphan["text_chars"], pdf_quality.MIN_PAGE_CHARS)
        self.assertGreaterEqual(orphan["ink_ratio"], pdf_quality.MIN_INK_RATIO)
        self.assertLess(orphan["fill_ratio"], 0.50)
        self.assertTrue(
            [
                finding
                for finding in findings
                if finding.check == "blank_page" and finding.where == "page 3"
            ],
            findings,
        )

    def test_header_gap_threshold_is_configurable_and_enforced(self):
        findings, _ = pdf_quality.check_pdf(
            self.dense_pdf, min_header_gap_mm=999.0
        )
        self.assertTrue([f for f in findings if f.check == "header_gap"])

    def test_no_text_escapes_the_page_box(self):
        findings, _ = pdf_quality.check_pdf(self.dense_pdf)
        self.assertEqual([f for f in findings if f.check == "overflow"], [])

    def test_metrics_expose_trailing_whitespace(self):
        _, metrics = pdf_quality.check_pdf(self.dense_pdf)
        for page in metrics["pages"]:
            self.assertIn("trailing_blank_mm", page)
            self.assertIn("text_chars", page)
        self.assertIsInstance(metrics["mean_trailing_blank_mm"], float)


class EntryPointTests(unittest.TestCase):
    def test_token_only_run_needs_no_pdf(self):
        report = pdf_quality.run_quality_checks()
        self.assertTrue(report.ok)
        self.assertIn("contrast", report.metrics)
        self.assertNotIn("pdf", report.metrics)

    def test_report_serialises_for_receipts(self):
        report = pdf_quality.run_quality_checks()
        payload = report.to_dict()
        self.assertIn("ok", payload)
        self.assertIn("findings", payload)
        self.assertIn("metrics", payload)

    def test_missing_pdf_raises_a_clear_error(self):
        with self.assertRaises(ValueError):
            pdf_quality.check_pdf(ROOT / "does-not-exist.pdf")

    def test_warnings_do_not_fail_the_gate(self):
        report = pdf_quality.QualityReport()
        report.findings.append(
            pdf_quality.Finding("sparse_page", "warning", "short tail", "page 9")
        )
        self.assertTrue(report.ok)
        report.findings.append(
            pdf_quality.Finding("blank_page", "error", "empty", "page 10")
        )
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
