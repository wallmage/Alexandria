import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "md_to_pdf.py"


def fake_markdown_module():
    """Small deterministic Markdown boundary double for renderer unit tests."""

    def inline(value):
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)

    class MinimalMarkdown:
        def __init__(self, **kwargs):
            pass

        def convert(self, source):
            output = []
            paragraph = []
            quote = []

            def flush_paragraph():
                if paragraph:
                    output.append(f"<p>{inline(' '.join(paragraph))}</p>")
                    paragraph.clear()

            def flush_quote():
                if quote:
                    output.append(
                        "<blockquote><p>"
                        + "\n".join(inline(line) for line in quote)
                        + "</p></blockquote>"
                    )
                    quote.clear()

            for line in [*source.splitlines(), ""]:
                stripped = line.strip()
                if stripped.startswith(">"):
                    flush_paragraph()
                    quote.append(stripped.lstrip(">").strip())
                elif not stripped:
                    flush_paragraph()
                    flush_quote()
                elif stripped.startswith("### "):
                    flush_paragraph()
                    flush_quote()
                    text = stripped[4:]
                    output.append(f'<h3 id="{text.casefold().replace(" ", "-")}">{text}</h3>')
                elif stripped.startswith("## "):
                    flush_paragraph()
                    flush_quote()
                    text = stripped[3:]
                    output.append(f'<h2 id="{text.casefold().replace(" ", "-")}">{text}</h2>')
                elif stripped.startswith("# "):
                    flush_paragraph()
                    flush_quote()
                    text = stripped[2:]
                    output.append(f'<h1 id="{text.casefold().replace(" ", "-")}">{text}</h1>')
                else:
                    flush_quote()
                    paragraph.append(stripped)
            return "".join(output)

    return mock.Mock(Markdown=MinimalMarkdown)


def load_converter():
    spec = importlib.util.spec_from_file_location("alexandria_md_to_pdf", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CommandLineTests(unittest.TestCase):
    def test_help_works_without_optional_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-S", str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--subtitle", result.stdout)
        self.assertIn("--lang", result.stdout)
        self.assertIn("--template", result.stdout)
        self.assertIn("--client", result.stdout)
        self.assertIn("--prepared-by", result.stdout)
        self.assertIn("--confidential", result.stdout)
        self.assertIn("--date", result.stdout)
        self.assertIn("--cover-image", result.stdout)
        self.assertIn("--rewild-receipt", result.stdout)
        self.assertIn("--content-receipt", result.stdout)
        self.assertIn("--ledger", result.stdout)

    def test_rejects_non_pdf_output_before_loading_render_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "report.md"
            source.write_text("# Report\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    str(source),
                    str(source.with_suffix(".txt")),
                    "--rewild-receipt",
                    str(Path(temp_dir) / "receipt.json"),
                    "--ledger",
                    str(Path(temp_dir) / "ledger.json"),
                    "--content-receipt",
                    str(Path(temp_dir) / "content-receipt.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("must end in .pdf", result.stderr)


class ConverterUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.converter = load_converter()

    def render_html(self, source, **kwargs):
        with mock.patch.object(
            self.converter, "load_markdown", return_value=fake_markdown_module()
        ):
            return self.converter.md_to_html(source, **kwargs)

    def render_pdf(self, source, output, **kwargs):
        with mock.patch.object(
            self.converter, "validate_rewild_for_render", return_value=None
        ), mock.patch.object(
            self.converter, "validate_content_for_render", return_value=None
        ):
            return self.converter.render_pdf(
                source,
                output,
                rewild_receipt="receipt.json",
                content_receipt="content-receipt.json",
                ledger="ledger.json",
                **kwargs,
            )

    def test_render_rejects_a_missing_content_receipt_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "report.md"
            output = Path(temp_dir) / "report.pdf"
            source.write_text("# Report\n", encoding="utf-8")
            with mock.patch.object(
                self.converter, "validate_rewild_for_render", return_value=None
            ), self.assertRaisesRegex(ValueError, "Content quality"):
                self.converter.render_pdf(
                    source,
                    output,
                    rewild_receipt=Path(temp_dir) / "rewild.json",
                    ledger=Path(temp_dir) / "ledger.json",
                    content_receipt=None,
                )

    def test_detects_english_simplified_and_traditional_chinese(self):
        self.assertEqual(self.converter.detect_language("A report about markets."), "en")
        self.assertEqual(self.converter.detect_language("这是一份关于市场的研究报告。"), "zh-CN")
        self.assertEqual(self.converter.detect_language("這是一份關於市場的研究報告。"), "zh-HK")

    def test_explicit_template_wins_and_auto_selection_adapts_to_subject(self):
        cases = (
            ("A strategy review for a global bank", "auto", "executive"),
            ("A digital media product for a consumer startup", "auto", "spectrum"),
            ("A cultural history of river landscapes and field ecology", "auto", "atlas"),
            ("Climate-ready infrastructure, energy resilience, and supply chains", "auto", "horizon"),
            ("Luxury hospitality and service design in premium retail", "auto", "maison"),
            ("Operating model, process governance, and organizational design", "auto", "blueprint"),
            ("Wetland conservation, agriculture, and land-use ecology", "auto", "terrain"),
            ("Artificial intelligence, semiconductors, and advanced robotics", "auto", "orbit"),
            ("Youth entrepreneurship, civic participation, and community education", "auto", "sunbeam"),
            ("Mobility innovation, customer journeys, and the future of work", "auto", "current"),
            ("Workplace culture, public health, care, and lifelong learning", "auto", "apricot"),
            ("A cultural history of river landscapes", "spectrum", "spectrum"),
            ("A global bank strategy review", "sunbeam", "sunbeam"),
        )

        for subject, requested, expected in cases:
            with self.subTest(subject=subject, requested=requested):
                self.assertEqual(
                    self.converter.select_template(subject, requested), expected
                )

    def test_each_template_has_a_distinct_cover_and_visual_system(self):
        for template in (
            "executive",
            "spectrum",
            "atlas",
            "horizon",
            "maison",
            "blueprint",
            "terrain",
            "orbit",
            "sunbeam",
            "current",
            "apricot",
        ):
            rendered = self.render_html(
                "# Research title\n\n## Finding\n\nEvidence and implications.",
                template=template,
                report_date="28 July 2026",
            )
            with self.subTest(template=template):
                self.assertIn(f'class="report template-{template}"', rendered)
                self.assertIn(f'class="cover cover-{template} ', rendered)
                self.assertIn(f'data-template="{template}"', rendered)

        executive = self.render_html("# T\n\n## F\n\nBody.", template="executive")
        spectrum = self.render_html("# T\n\n## F\n\nBody.", template="spectrum")
        atlas = self.render_html("# T\n\n## F\n\nBody.", template="atlas")
        horizon = self.render_html("# T\n\n## F\n\nBody.", template="horizon")
        maison = self.render_html("# T\n\n## F\n\nBody.", template="maison")
        blueprint = self.render_html("# T\n\n## F\n\nBody.", template="blueprint")
        terrain = self.render_html("# T\n\n## F\n\nBody.", template="terrain")
        orbit = self.render_html("# T\n\n## F\n\nBody.", template="orbit")
        sunbeam = self.render_html("# T\n\n## F\n\nBody.", template="sunbeam")
        current = self.render_html("# T\n\n## F\n\nBody.", template="current")
        apricot = self.render_html("# T\n\n## F\n\nBody.", template="apricot")
        self.assertIn("#123047", executive)
        self.assertIn("#4f46e5", spectrum)
        self.assertIn("#173d2a", atlas)
        self.assertIn("#0b63f6", horizon)
        self.assertIn("#b39a61", maison)
        self.assertIn("#4a9fd8", blueprint)
        self.assertIn("#2d5e3a", terrain)
        self.assertIn("#0062ff", orbit)
        self.assertIn("#ff6b35", sunbeam)
        self.assertIn("#ff5c00", current)
        self.assertIn("#ff9800", apricot)

    def test_every_template_css_resolves_all_placeholders(self):
        for template in self.converter.TEMPLATES:
            with self.subTest(template=template):
                css = self.converter.build_css(
                    template,
                    font_sans="sans",
                    font_display="serif",
                    font_mono="mono",
                    header_text="Header",
                    page_label="",
                    page_suffix="",
                    footer_text="Footer",
                    insight_label="Insight",
                    takeaway_label="Takeaway",
                )
                self.assertIsNone(re.search(r"__[A-Z_]+__", css))

    def test_paged_media_css_keeps_rules_and_rows_out_of_content(self):
        css = self.converter.build_css(
            "executive",
            font_sans="sans",
            font_display="serif",
            font_mono="mono",
            header_text="Header",
            page_label="",
            page_suffix="",
            footer_text="Footer",
            insight_label="Insight",
            takeaway_label="Takeaway",
        )
        self.assertNotRegex(css, r"@top-(?:left|right)\s*\{[^}]*padding-bottom")
        self.assertNotRegex(css, r"@bottom-(?:left|right)\s*\{[^}]*padding-top")
        self.assertRegex(css, r"tr,\s*td,\s*th\s*\{[^}]*break-inside:\s*avoid")

    def test_sanitizer_drops_contents_of_active_or_embedded_elements(self):
        value = (
            "<p>Visible</p><script>alert(1)</script>"
            "<style>body{display:none}</style><iframe>fallback</iframe>"
        )
        sanitized = self.converter.sanitize_html_fragment(value)
        self.assertEqual(sanitized, "<p>Visible</p>")

    def test_extract_report_meta_ignores_headings_inside_fenced_code(self):
        source = "```markdown\n# Not the title\n```\n\n# Actual title\n\n> 28 July 2026\n"
        self.assertEqual(
            self.converter.extract_report_meta(source),
            ("Actual title", "28 July 2026"),
        )

    def test_every_small_text_palette_token_meets_wcag_aa_on_white(self):
        def luminance(color):
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        for name, spec in self.converter.TEMPLATES.items():
            with self.subTest(template=name):
                for token in (spec.accent_text, spec.muted):
                    ratio = (1.0 + 0.05) / (luminance(token) + 0.05)
                    self.assertGreaterEqual(ratio, 4.5)

    def test_new_templates_build_distinct_reference_compositions(self):
        expected_markers = {
            "maison": (
                "maison-photo",
                "maison-toc-editorial",
                "maison-feature-page",
            ),
            "blueprint": (
                "blueprint-datum",
                "blueprint-toc-map",
                "blueprint-feature-page",
            ),
            "terrain": (
                "terrain-aerial",
                "terrain-toc-map",
                "terrain-feature-page",
            ),
            "orbit": (
                "orbit-field",
                "orbit-toc-field",
                "orbit-feature-page",
            ),
            "sunbeam": (
                "sunbeam-motif",
                "sunbeam-toc-system",
                "sunbeam-feature-page",
            ),
            "current": (
                "current-flow-map",
                "current-toc-system",
                "current-feature-page",
            ),
            "apricot": (
                "apricot-photo",
                "apricot-toc-system",
                "apricot-feature-page",
            ),
        }
        source = (
            "# Research title\n\n"
            "## Executive brief\n\n"
            "A decision-grade view of the forces changing the market.\n\n"
            "> [!INSIGHT]\n"
            "> Evidence becomes useful when its route to judgment is visible.\n\n"
            "## Market structure\n\n"
            "How economics and competitive pressure are changing."
        )

        for template, markers in expected_markers.items():
            rendered = self.render_html(source, template=template)
            with self.subTest(template=template):
                for marker in markers:
                    self.assertIn(marker, rendered)

    def test_default_and_adaptive_companion_are_distinct_and_deterministic(self):
        subject = "Artificial intelligence, semiconductors, and robotics"

        self.assertEqual(
            self.converter.select_adaptive_companion(subject),
            self.converter.select_adaptive_companion(subject),
        )
        self.assertNotEqual(
            "executive",
            self.converter.select_adaptive_companion(subject),
        )

    def test_horizon_builds_the_reference_editorial_composition(self):
        rendered = self.render_html(
            "# The new geography of resilience\n\n"
            "## Executive brief\n\n"
            "A decision-grade view of the forces changing the market.\n\n"
            "> [!INSIGHT]\n"
            "> Evidence becomes useful when its route to judgment is visible.\n\n"
            "## Market structure\n\n"
            "How economics and competitive pressure are changing.",
            template="horizon",
            report_date="14 October 2025",
        )

        self.assertIn('class="horizon-firm-mark"', rendered)
        self.assertIn('class="horizon-figure-label"', rendered)
        self.assertIn('class="horizon-cover-folio"', rendered)
        self.assertIn('class="horizon-toc-band"', rendered)
        self.assertIn('class="horizon-reading-card"', rendered)
        self.assertIn('class="horizon-feature-page"', rendered)
        self.assertIn('class="horizon-feature-photo"', rendered)
        self.assertIn("data:image/jpeg;base64,", rendered)
        self.assertEqual(rendered.count(">Executive brief<"), 2)
        self.assertEqual(
            rendered.count(
                "Evidence becomes useful when its route to judgment is visible."
            ),
            1,
        )

    def test_horizon_feature_composition_does_not_leak_into_other_templates(self):
        rendered = self.render_html(
            "# Research title\n\n"
            "## Executive brief\n\n"
            "Evidence and implications.",
            template="executive",
        )

        self.assertNotIn("horizon-toc-band", rendered)
        self.assertNotIn("horizon-feature-page", rendered)
        self.assertNotIn("horizon-feature-photo", rendered)

    def test_horizon_scales_long_feature_insights(self):
        rendered = self.render_html(
            "# Research title\n\n"
            "## Executive brief\n\n"
            "Evidence and implications.\n\n"
            "> [!INSIGHT]\n"
            "> The decision depends less on a single benchmark than on where "
            "the work runs, how much autonomy the team can permit, which "
            "controls the organization requires, and how much of the delivery "
            "system should be encoded around the agent over time.",
            template="horizon",
        )

        self.assertIn(
            'class="horizon-feature-insight horizon-feature-insight-long"',
            rendered,
        )

    def test_cover_metadata_omits_empty_client_and_non_confidential_labels(self):
        rendered = self.render_html(
            "# Research title\n\n## Finding\n\nBody.",
            template="executive",
            report_date="28 July 2026",
        )

        self.assertIn("Prepared by", rendered)
        self.assertIn("Alexandria", rendered)
        self.assertIn("28 July 2026", rendered)
        self.assertNotIn(">Client<", rendered)
        self.assertNotIn("Strictly Confidential", rendered)
        self.assertNotIn("Controlled copy", rendered)
        self.assertNotIn("Not for external distribution", rendered)

    def test_report_metadata_uses_date_line_not_blockquote_deck(self):
        title, report_date = self.converter.extract_report_meta(
            "# Research title\n\n"
            "> A decision-grade comparison of two systems  \n"
            "> 28 July 2026\n\n"
            "## Finding\n\nBody."
        )

        self.assertEqual(title, "Research title")
        self.assertEqual(report_date, "28 July 2026")

    def test_confidential_client_metadata_is_opt_in(self):
        rendered = self.render_html(
            "# Research title\n\n## Finding\n\nBody.",
            template="spectrum",
            client="Asteron Group",
            prepared_by="Northline Advisory",
            confidential=True,
            report_date="28 July 2026",
        )

        self.assertIn(">Client<", rendered)
        self.assertIn("Asteron Group", rendered)
        self.assertIn("Northline Advisory", rendered)
        self.assertIn("Strictly Confidential", rendered)
        self.assertIn("Controlled copy", rendered)
        self.assertIn("Not for external distribution", rendered)

    def test_long_cover_content_activates_compact_title_and_metadata_layouts(self):
        rendered = self.render_html(
            "# A very long research title about infrastructure resilience, "
            "capital allocation, institutional change, and the next decade of adaptation\n\n"
            "## Finding\n\nBody.",
            subtitle=(
                "A decision-grade assessment of interconnected systems, constraints, "
                "trade-offs, and strategic choices."
            ),
            template="horizon",
            client="Northstar International Infrastructure and Resilience Partners",
            prepared_by="Alexandria Strategic Research and Transformation Advisory",
            confidential=True,
            report_date="28 July 2026",
        )

        self.assertIn("cover-title-very-long", rendered)
        self.assertIn("cover-meta-4", rendered)
        self.assertIn("cover-meta-long", rendered)
        self.assertIn(".cover.cover-title-very-long h1", rendered)
        self.assertIn(".cover.cover-horizon.cover-meta-4", rendered)

    def test_contents_page_uses_section_summaries_without_document_control(self):
        rendered = self.render_html(
            "# Research title\n\n"
            "## Market structure\n\n"
            "How value pools, incentives, and competitive positions are changing.\n\n"
            "### Evidence\n\n"
            "Supporting detail.\n\n"
            "## Recommendations\n\n"
            "The actions, sequencing, and trade-offs that follow.",
            template="atlas",
        )

        self.assertIn("How value pools, incentives, and competitive positions", rendered)
        self.assertIn("The actions, sequencing, and trade-offs", rendered)
        self.assertNotIn("Document control", rendered)
        self.assertNotIn("Reading guide", rendered)
        self.assertNotIn("Report to", rendered)
        self.assertNotIn("Version issued", rendered)

    def test_consulting_callout_markers_become_designed_components(self):
        rendered = self.render_html(
            "# Research title\n\n"
            "## Finding\n\n"
            "> [!METRIC]\n"
            "> **2.4×**\n"
            "> Higher renewal intent.\n\n"
            "> [!INSIGHT]\n"
            "> Judgment changes the decision.\n\n"
            "> [!TAKEAWAY]\n"
            "> Act before the window closes.",
            template="executive",
        )

        self.assertIn('class="metric-card"', rendered)
        self.assertIn('class="metric-value"', rendered)
        self.assertIn('class="insight-panel"', rendered)
        self.assertIn('class="takeaway-band"', rendered)
        self.assertNotIn("[!METRIC]", rendered)
        self.assertNotIn("[!INSIGHT]", rendered)
        self.assertNotIn("[!TAKEAWAY]", rendered)

    def test_adjacent_callouts_split_when_markdown_merges_their_blockquote(self):
        merged = (
            "<blockquote>\n"
            "<p>[!METRIC]\n<strong>2.4×</strong>\nHigher renewal intent.</p>\n"
            "<p>[!INSIGHT]\nJudgment changes the decision.</p>\n"
            "<p>[!TAKEAWAY]\nAct before the window closes.</p>\n"
            "</blockquote>"
        )

        transformed = self.converter.transform_callouts(merged)

        self.assertEqual(transformed.count('class="metric-card"'), 1)
        self.assertEqual(transformed.count('class="insight-panel"'), 1)
        self.assertEqual(transformed.count('class="takeaway-band"'), 1)
        self.assertNotIn("[!METRIC]", transformed)
        self.assertNotIn("[!INSIGHT]", transformed)
        self.assertNotIn("[!TAKEAWAY]", transformed)

    def test_toc_escapes_heading_text_and_keeps_anchor(self):
        body = '<h2 id="risk">Risk &amp; <em>reward</em> &lt;script&gt;</h2>'

        toc = self.converter.build_toc_html(body, "en")

        self.assertIn('href="#risk"', toc)
        self.assertIn("Risk &amp; reward &lt;script&gt;", toc)
        self.assertNotIn("<script>", toc)

    def test_hong_kong_toc_uses_traditional_chinese(self):
        toc = self.converter.build_toc_html('<h2 id="one">第一章</h2>', "zh-HK")

        self.assertIn("目錄", toc)
        self.assertNotIn("目录", toc)

    def test_new_template_chrome_follows_report_language(self):
        body = '<h2 id="one">第一章</h2><p>本章说明主要证据。</p>'

        maison = self.converter.build_toc_html(body, "zh-CN", "maison")
        orbit = self.converter.build_toc_html(body, "zh-HK", "orbit")

        self.assertIn("编辑脉络", maison)
        self.assertIn("閱讀方位", orbit)

    def test_generated_html_drops_active_or_embedded_raw_html(self):
        fake_markdown = mock.Mock()
        fake_markdown.Markdown.return_value.convert.return_value = (
            '<h2 id="safe">Safe</h2>'
            '<link rel="attachment" href="file:///etc/passwd">'
            '<object data="file:///etc/passwd"></object>'
            '<a href="file:///etc/passwd">local file</a>'
            '<img src="image.png" onerror="alert(1)">'
        )
        with mock.patch.object(
            self.converter, "load_markdown", return_value=fake_markdown
        ):
            rendered = self.converter.md_to_html("# Safe")
        self.assertNotIn("<link", rendered)
        self.assertNotIn("<object", rendered)
        self.assertNotIn("onerror", rendered)
        self.assertNotIn("file:///etc/passwd", rendered)
        self.assertIn('<img src="image.png">', rendered)

    def test_asset_url_fetcher_blocks_parent_paths_and_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "image.png").write_bytes(b"ok")
            fetched = []

            def default_fetcher(url):
                fetched.append(url)
                return {"string": b"ok"}

            fetch = self.converter.make_url_fetcher(root, default_fetcher)
            fetch((root / "image.png").as_uri())
            self.assertEqual(1, len(fetched))
            for blocked in (
                (root.parent / "secret.txt").as_uri(),
                "https://example.com/image.png",
                "http://127.0.0.1/secret",
                "data:text/html,unsafe",
                "data:image/svg+xml,<svg></svg>",
                "data:image/png-evil,unsafe",
            ):
                with self.assertRaises(ValueError):
                    fetch(blocked)

    def test_css_content_escaping_is_css_not_html(self):
        escaped = self.converter.escape_css_content(
            'A & B "quoted"\\line\nnext</style>'
        )

        self.assertEqual(
            escaped,
            'A & B \\"quoted\\"\\\\line\\A next\\3C /style\\3E ',
        )
        self.assertNotIn("&amp;", escaped)
        self.assertNotIn("</style>", escaped)

    def test_html_debug_path_uses_suffix_instead_of_string_replacement(self):
        self.assertEqual(
            self.converter.html_debug_path(Path("/tmp/report.PDF")),
            Path("/tmp/report.html"),
        )

    def test_render_uses_markdown_directory_for_relative_assets(self):
        calls = {}

        class FakeHTML:
            def __init__(self, *, string, base_url, url_fetcher):
                calls["string"] = string
                calls["base_url"] = Path(base_url)
                calls["url_fetcher"] = url_fetcher

            def write_pdf(self, target, **options):
                calls.update(options)
                Path(target).write_bytes(b"%PDF-1.7\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "nested" / "report.md"
            output = temp / "out" / "report.pdf"
            source.parent.mkdir()
            source.write_text("# Report\n", encoding="utf-8")

            with (
                mock.patch.object(self.converter, "md_to_html", return_value="<html></html>"),
                mock.patch.object(self.converter, "load_weasyprint_html", return_value=FakeHTML),
            ):
                self.render_pdf(source, output)

            self.assertEqual(calls["base_url"], source.parent.resolve())
            self.assertIs(calls["pdf_tags"], True)
            self.assertTrue(output.exists())
            self.assertEqual(0o644, os.stat(output).st_mode & 0o777)

    def test_failed_render_preserves_existing_pdf(self):
        class FailingHTML:
            def __init__(self, **kwargs):
                pass

            def write_pdf(self, target, **options):
                Path(target).write_bytes(b"partial")
                raise RuntimeError("render failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            source.write_text("# Report\n", encoding="utf-8")
            output.write_bytes(b"existing")

            with (
                mock.patch.object(self.converter, "md_to_html", return_value="<html></html>"),
                mock.patch.object(
                    self.converter, "load_weasyprint_html", return_value=FailingHTML
                ),
            ):
                with self.assertRaises(RuntimeError):
                    self.render_pdf(source, output, force=True)

            self.assertEqual(b"existing", output.read_bytes())

    def test_existing_pdf_requires_explicit_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            source.write_text("# Report\n", encoding="utf-8")
            output.write_bytes(b"existing")

            with self.assertRaisesRegex(ValueError, "already exists"):
                self.render_pdf(source, output)

            self.assertEqual(b"existing", output.read_bytes())

    def test_render_requires_rewild_receipt_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            source.write_text("# Report\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Rewild gate receipt"):
                self.converter.render_pdf(source, output)

    def test_keep_html_refuses_to_overwrite_existing_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            sidecar = temp / "report.html"
            source.write_text("# Report\n", encoding="utf-8")
            sidecar.write_text("mine", encoding="utf-8")

            with mock.patch.object(
                self.converter, "md_to_html", return_value="<html></html>"
            ), self.assertRaisesRegex(ValueError, "already exists"):
                self.render_pdf(source, output, keep_html=True)

            self.assertEqual("mine", sidecar.read_text(encoding="utf-8"))

    def test_html_contains_document_metadata(self):
        rendered = self.render_html(
            "# Research title\n\n## Finding\n\nEvidence.",
            prepared_by="Alexandria Research",
        )
        self.assertIn("<title>Research title</title>", rendered)
        self.assertIn('<meta name="author" content="Alexandria Research">', rendered)
        self.assertIn('<meta name="description"', rendered)

    def test_cover_image_rejects_low_resolution_raster(self):
        tiny_png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "report.md"
            image = root / "tiny.png"
            report.write_text("# Report\n", encoding="utf-8")
            image.write_bytes(tiny_png)
            with self.assertRaisesRegex(ValueError, "resolution"):
                self.converter.validate_cover_image(report, image)


if __name__ == "__main__":
    unittest.main()
