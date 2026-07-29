import base64
import hashlib
import importlib.util
import io
import json
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


def encoded_raster(image_format, *, size=(1, 1), frames=1):
    """Return a real raster fixture encoded by Pillow."""
    from PIL import Image

    images = [
        Image.new("RGB", size, color=(index % 2 * 255, 0, 0))
        for index in range(frames)
    ]
    output = io.BytesIO()
    images[0].save(
        output,
        format=image_format,
        save_all=frames > 1,
        append_images=images[1:],
        duration=10,
        loop=0,
    )
    return output.getvalue()


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
        self.assertIn("--source-fidelity-receipt", result.stdout)
        self.assertIn("--content-receipt", result.stdout)
        self.assertIn("--ledger", result.stdout)
        self.assertIn("--render-receipt", result.stdout)

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
                    "--source-fidelity-receipt",
                    str(Path(temp_dir) / "source-fidelity-receipt.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("must end in .pdf", result.stderr)


class ConverterUnitTests(unittest.TestCase):
    def test_immediate_blockquote_deck_becomes_default_cover_standfirst(self):
        report = """# A Report Title

> A decision-grade standfirst for the intended reader.
> 28 July 2026

## Analysis

Body.

## Sources

- [Source](https://example.com)
"""
        rendered = self.converter.md_to_html(
            report,
            lang="en",
            template="executive",
        )
        self.assertIn(
            '<div class="subtitle">A decision-grade standfirst for the intended reader.</div>',
            rendered,
        )
        self.assertNotIn("A decision-grade standfirst for the intended reader.</blockquote>", rendered)

    def test_standfirst_without_date_uses_the_current_date_slot(self):
        title, report_date, standfirst = self.converter.extract_report_header(
            "# Title\n\n> A useful standfirst.\n\n## Body\n\nText."
        )
        self.assertEqual("Title", title)
        self.assertEqual("", report_date)
        self.assertEqual("A useful standfirst.", standfirst)

    def test_formatted_standfirst_does_not_leak_into_report_body(self):
        rendered = self.converter.md_to_html(
            "# Title\n\n> A *useful* standfirst.\n> 28 July 2026\n\n"
            "## Body\n\nText.\n\n## Sources\n\n- [Source](https://example.com)",
            lang="en",
            template="executive",
        )
        self.assertIn('<div class="subtitle">A useful standfirst.</div>', rendered)
        self.assertNotIn("<blockquote><p>A <em>useful</em> standfirst.", rendered)

    def test_inline_citations_receive_print_source_numbers(self):
        rendered = self.converter.md_to_html(
            "# Title\n\n> A useful standfirst.\n> 28 July 2026\n\n"
            "## Finding\n\nA claim with [evidence](https://example.com/a).\n\n"
            "## Sources\n\n- [Source A](https://example.com/a)",
            lang="en",
            template="executive",
        )
        # A bare superscript numeral in the text face is the editorial
        # convention; the earlier bold-mono "[01]" broke the line rhythm wherever
        # a sentence carried more than one citation.
        self.assertIn('<sup class="source-ref">01</sup>', rendered)
        self.assertNotIn("[01]", rendered)

    def test_image_covers_have_contrast_protection_for_all_overlay_text(self):
        css = self.converter.build_css(
            "terrain",
            font_sans="sans",
            font_display="serif",
            font_mono="mono",
            header_text="header",
            page_label="",
            page_suffix="",
            footer_text="footer",
            insight_label="insight",
            takeaway_label="takeaway",
        )
        self.assertIn(".template-terrain .cover-kicker", css)
        self.assertIn("text-shadow:", css)
        self.assertIn("linear-gradient", css)

    def test_maison_cover_copy_stays_below_the_image_plate(self):
        css = self.converter.build_css(
            "maison",
            font_sans="sans",
            font_display="serif",
            font_mono="mono",
            header_text="header",
            page_label="",
            page_suffix="",
            footer_text="footer",
            insight_label="insight",
            takeaway_label="takeaway",
        )
        self.assertIn(".maison-art {\n    inset: 0 0 auto;\n    height: 88mm;", css)
        self.assertIn(
            ".template-maison .cover-copy {\n"
            "    position: absolute;\n"
            "    left: 17mm;\n"
            "    right: 17mm;\n"
            "    top: 104mm;",
            css,
        )

    def test_section_leads_stay_with_the_first_body_block(self):
        css = self.converter.build_css(
            "executive",
            font_sans="sans",
            font_display="serif",
            font_mono="mono",
            header_text="header",
            page_label="",
            page_suffix="",
            footer_text="footer",
            insight_label="insight",
            takeaway_label="takeaway",
        )
        # Only paragraphs certified short by is_lede_paragraph() are set as
        # ledes, and a lede never breaks across pages. break-after: avoid was
        # deliberately dropped: it pushed whole blocks to the next sheet and
        # left up to 70mm of trailing white space on the page before.
        self.assertRegex(
            css,
            r"h1 \+ p\.section-lede,\s*h2 \+ p\.section-lede \{[^}]*break-inside: avoid",
        )
        lede_rule = re.search(
            r"h1 \+ p\.section-lede,\s*h2 \+ p\.section-lede \{[^}]*\}", css
        ).group(0)
        self.assertNotIn("break-after: avoid", lede_rule)

    def test_only_short_paragraphs_are_set_as_ledes(self):
        short = "A compact standfirst that introduces the section."
        long = "word " * 200
        self.assertTrue(self.converter.is_lede_paragraph(short))
        self.assertFalse(self.converter.is_lede_paragraph(long))
        self.assertFalse(self.converter.is_lede_paragraph(""))

        body = f"<h2>Section</h2>\n<p>{short}</p>\n<h2>Other</h2>\n<p>{long}</p>"
        marked = self.converter.mark_section_ledes(body)
        self.assertIn(f'<p class="section-lede">{short}</p>', marked)
        self.assertIn(f"<p>{long}</p>", marked)

    def test_cjk_ledes_count_glyphs_as_double_width(self):
        # A CJK paragraph occupies roughly twice the measure per character, so
        # the unit budget must halve the character count it accepts.
        han = "研" * (self.converter.MAX_LEDE_UNITS // 2 + 5)
        self.assertFalse(self.converter.is_lede_paragraph(han))
        self.assertTrue(
            self.converter.is_lede_paragraph("研" * (self.converter.MAX_LEDE_UNITS // 4))
        )

    def test_multi_page_toc_exposes_page_index_for_crop_variation(self):
        headings = "\n\n".join(
            f"## Section {index}\n\nDistinct section summary {index}."
            for index in range(1, 14)
        )
        report = (
            "# Report\n\n> A useful standfirst.\n> 28 July 2026\n\n"
            + headings
            + "\n\n## Sources\n\n- [Source](https://example.com)"
        )
        rendered = self.converter.md_to_html(
            report,
            lang="en",
            template="terrain",
        )
        self.assertIn("toc-chunk-01", rendered)
        self.assertIn("toc-chunk-02", rendered)
        self.assertIn("toc-chunk-03", rendered)

    def test_template_css_has_no_accidental_nested_duplicate_selector(self):
        for template in self.converter.TEMPLATES:
            css = self.converter.build_css(
                template,
                font_sans="sans",
                font_display="serif",
                font_mono="mono",
                header_text="header",
                page_label="",
                page_suffix="",
                footer_text="footer",
                insight_label="insight",
                takeaway_label="takeaway",
            )
            self.assertNotRegex(
                css,
                r"(?m)^([.#][^{\n]+)\s*\{\s*\n\1\s*\{",
                template,
            )

    def test_data_url_limit_matches_decoded_asset_limit(self):
        image = encoded_raster("PNG")
        encoded = base64.b64encode(image).decode("ascii")
        with mock.patch.object(self.converter, "MAX_ASSET_BYTES", len(image)):
            fetcher = self.converter.make_url_fetcher(
                Path("."),
                default_fetcher=lambda url: {"string": url},
            )
            self.assertEqual(
                {"string": f"data:image/png;base64,{encoded}"},
                fetcher(f"data:image/png;base64,{encoded}"),
            )
            with self.assertRaisesRegex(ValueError, "resource limit"):
                fetcher(f"data:image/png;base64,{encoded}AAAA")

    def test_percent_encoded_data_url_is_bounded_before_unquoting(self):
        with (
            mock.patch.object(self.converter, "MAX_ASSET_BYTES", 1),
            mock.patch.object(
                self.converter,
                "unquote_to_bytes",
                side_effect=AssertionError("oversized payload was expanded"),
            ),
            self.assertRaisesRegex(ValueError, "resource limit"),
        ):
            self.converter.decode_image_data_url("data:image/png,%41%42")

    def test_photo_cover_sources_are_html_attribute_escaped(self):
        hostile = 'cover"><p id="injected">UNREVIEWED</p><img src="cover.png'

        for template in ("maison", "terrain", "apricot", "horizon"):
            with self.subTest(template=template):
                rendered = self.converter.cover_art_html(template, hostile)
                self.assertNotIn('<p id="injected">', rendered)
                self.assertIn(
                    'src="cover&quot;&gt;&lt;p id=&quot;injected&quot;&gt;'
                    "UNREVIEWED&lt;/p&gt;&lt;img src=&quot;cover.png\"",
                    rendered,
                )

    def test_cover_rejects_allowed_suffix_with_disallowed_decoded_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "report.md"
            image = root / "cover.png"
            report.write_text("# Report\n", encoding="utf-8")
            image.write_bytes(encoded_raster("BMP", size=(1000, 600)))

            with self.assertRaisesRegex(ValueError, "decoded image format"):
                self.converter.validate_cover_image(report, image)

    def test_local_image_rejects_allowed_suffix_with_disallowed_decoded_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "figure.png"
            image.write_bytes(encoded_raster("BMP"))
            fetcher = self.converter.make_url_fetcher(
                root, default_fetcher=lambda url: {"string": url}
            )

            with self.assertRaisesRegex(ValueError, "decoded image format"):
                fetcher(image.as_uri())

    def test_local_image_returns_the_exact_bytes_that_were_validated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "figure.png"
            original = encoded_raster("PNG")
            replacement = encoded_raster("BMP")
            image.write_bytes(original)

            def swapping_fetcher(url):
                image.write_bytes(replacement)
                return {"string": image.read_bytes()}

            fetcher = self.converter.make_url_fetcher(root, swapping_fetcher)
            fetched = fetcher(image.as_uri())

            self.assertEqual(original, fetched["string"])
            self.assertEqual("image/png", fetched["mime_type"])
            self.assertEqual(original, image.read_bytes())

    def test_local_image_rejects_symbolic_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.png"
            target.write_bytes(encoded_raster("PNG"))
            linked = root / "linked.png"
            linked.symlink_to(target.name)
            fetcher = self.converter.make_url_fetcher(
                root, default_fetcher=lambda url: {"string": url}
            )

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                fetcher(linked.as_uri())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_local_image_rejects_non_regular_files_before_decoding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fifo = root / "stream.png"
            os.mkfifo(fifo)
            fetcher = self.converter.make_url_fetcher(
                root, default_fetcher=lambda url: {"string": url}
            )

            with (
                mock.patch.object(
                    self.converter,
                    "validate_raster_image",
                    side_effect=AssertionError("non-regular file was decoded"),
                ),
                self.assertRaisesRegex(ValueError, "regular file"),
            ):
                fetcher(fifo.as_uri())

    def test_data_image_rejects_disallowed_decoded_format_despite_allowed_mime(self):
        payload = base64.b64encode(encoded_raster("BMP")).decode("ascii")
        fetcher = self.converter.make_url_fetcher(
            Path("."), default_fetcher=lambda url: {"string": url}
        )

        with self.assertRaisesRegex(ValueError, "decoded image format"):
            fetcher(f"data:image/png;base64,{payload}")

    def test_local_image_rejects_decoded_pixel_budget_overrun(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "figure.png"
            image.write_bytes(encoded_raster("PNG", size=(7, 7)))
            fetcher = self.converter.make_url_fetcher(
                root, default_fetcher=lambda url: {"string": url}
            )

            with (
                mock.patch.dict(self.converter.__dict__, {"MAX_IMAGE_PIXELS": 40}),
                self.assertRaisesRegex(ValueError, "pixel limit"),
            ):
                fetcher(image.as_uri())

    def test_data_image_rejects_decoded_frame_budget_overrun(self):
        payload = base64.b64encode(encoded_raster("GIF", frames=2)).decode("ascii")
        fetcher = self.converter.make_url_fetcher(
            Path("."), default_fetcher=lambda url: {"string": url}
        )

        with (
            mock.patch.dict(self.converter.__dict__, {"MAX_IMAGE_FRAMES": 1}),
            self.assertRaisesRegex(ValueError, "frame limit"),
        ):
            fetcher(f"data:image/gif;base64,{payload}")

    def test_data_image_rejects_total_decoded_pixel_budget_overrun(self):
        payload = base64.b64encode(
            encoded_raster("GIF", size=(3, 3), frames=2)
        ).decode("ascii")
        fetcher = self.converter.make_url_fetcher(
            Path("."), default_fetcher=lambda url: {"string": url}
        )

        with (
            mock.patch.dict(
                self.converter.__dict__, {"MAX_IMAGE_TOTAL_PIXELS": 10}
            ),
            self.assertRaisesRegex(ValueError, "total decoded pixel limit"),
        ):
            fetcher(f"data:image/gif;base64,{payload}")

    def test_every_visual_system_reaches_the_report_body(self):
        for template in self.converter.TEMPLATES:
            css = self.converter.build_css(
                template,
                font_sans="sans",
                font_display="serif",
                font_mono="mono",
                header_text="header",
                page_label="",
                page_suffix="",
                footer_text="footer",
                insight_label="insight",
                takeaway_label="takeaway",
            )
            self.assertIn(f".template-{template} .report-body", css, template)
    @classmethod
    def setUpClass(cls):
        cls.converter = load_converter()

    def render_html(self, source, **kwargs):
        with mock.patch.object(
            self.converter, "load_markdown", return_value=fake_markdown_module()
        ):
            return self.converter.md_to_html(source, **kwargs)

    def render_pdf(self, source, output, **kwargs):
        artifact_defaults = {
            "rewild_receipt": source.parent / "rewild-receipt.json",
            "content_receipt": source.parent / "content-receipt.json",
            "ledger": source.parent / "ledger.json",
            "source_fidelity_receipt": (
                source.parent / "source-fidelity-receipt.json"
            ),
        }
        for name, path in artifact_defaults.items():
            if name not in kwargs:
                path.write_text(
                    (
                        json.dumps({"approved_visual_assets": []})
                        if name == "content_receipt"
                        else name
                    ),
                    encoding="utf-8",
                )
                kwargs[name] = path
        with mock.patch.object(
            self.converter, "validate_rewild_for_render", return_value=None
        ), mock.patch.object(
            self.converter, "validate_content_for_render", return_value=None
        ):
            return self.converter.render_pdf(
                source,
                output,
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
                self.assertIn('@font-face', css)
                self.assertIn('font-family: "Alexandria Sans"', css)

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

    def test_paragraph_splits_keep_a_full_reading_block_on_each_page(self):
        css = self.converter.build_css(
            "horizon",
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
        self.assertIn("orphans: 8", css)
        self.assertIn("widows: 8", css)

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
            image_bytes = encoded_raster("PNG")
            (root / "image.png").write_bytes(image_bytes)
            fetched = []

            def default_fetcher(url):
                fetched.append(url)
                return {"string": b"ok"}

            fetch = self.converter.make_url_fetcher(root, default_fetcher)
            result = fetch((root / "image.png").as_uri())
            self.assertEqual(image_bytes, result["string"])
            self.assertEqual("image/png", result["mime_type"])
            self.assertEqual([], fetched)
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

    def test_rendered_pdf_records_the_exact_gated_artifact_binding(self):
        from pypdf import PdfReader

        from scripts.render_binding import (
            file_sha256,
            validate_render_receipt,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            source.write_text("# Report\n\n## Finding\n\nEvidence.", encoding="utf-8")
            self.render_pdf(source, output)
            metadata = PdfReader(output).metadata or {}
            receipt = json.loads(
                output.with_suffix(".render.json").read_text(encoding="utf-8")
            )
            output_hash = file_sha256(output)
            receipt_errors = validate_render_receipt(
                output,
                receipt,
                source,
                temp / "ledger.json",
                temp / "rewild-receipt.json",
                temp / "content-receipt.json",
                temp / "source-fidelity-receipt.json",
                pdf_binding=metadata.get("/Keywords"),
            )
        self.assertEqual(receipt["binding"], metadata.get("/Keywords"))
        self.assertEqual(output_hash, receipt["pdf_sha256"])
        self.assertEqual([], receipt_errors)

    def test_assertive_title_or_subtitle_absent_from_markdown_cannot_render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            source.write_text(
                "# Authorized report\n\n"
                "> Authorized standfirst.\n\n"
                "## Finding\n\nAuthorized evidence.",
                encoding="utf-8",
            )
            for option in ("title", "subtitle"):
                output = temp / f"{option}.pdf"
                with (
                    self.subTest(option=option),
                    self.assertRaisesRegex(
                        ValueError,
                        rf"{option}.*gated Markdown",
                    ),
                ):
                    self.render_pdf(
                        source,
                        output,
                        **{option: "Acme committed criminal fraud."},
                    )
                self.assertFalse(output.exists())

    def test_client_and_prepared_by_accept_only_bounded_identifier_labels(self):
        cases = (
            ("client", "Acme committed criminal fraud"),
            ("client", "Alice Stole Funds"),
            ("prepared_by", "Alice Killed Bob"),
            ("client", "Acme Failed Audit"),
            ("prepared_by", "Alexandria\nAcme Research"),
            ("client", "A" * 81),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            source.write_text(
                "# Authorized report\n\n## Finding\n\nAuthorized evidence.",
                encoding="utf-8",
            )
            for option, value in cases:
                output = temp / f"{option}-{len(value)}.pdf"
                with (
                    self.subTest(option=option, value=value),
                    self.assertRaisesRegex(ValueError, "identifier label"),
                ):
                    self.render_pdf(
                        source,
                        output,
                        **{option: value},
                    )
                self.assertFalse(output.exists())

    def test_custom_identity_labels_must_come_from_typed_markdown_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "report.md"
            source.write_text(
                "# Authorized report\n\n"
                "> Client: Acme Research\n"
                "> Prepared by: Alice Smith\n"
                "> Authorized standfirst.\n\n"
                "## Finding\n\nAuthorized evidence.",
                encoding="utf-8",
            )
            md_text, resolved = self.converter.resolve_render_inputs(
                source,
                {
                    "title": None,
                    "subtitle": None,
                    "lang": "en",
                    "template": "executive",
                    "client": "Acme Research",
                    "prepared_by": "Alice Smith",
                    "confidential": False,
                    "report_date": None,
                    "cover_image": None,
                },
            )
            self.assertEqual(source.read_text(encoding="utf-8"), md_text)
            self.assertEqual("Acme Research", resolved["client"])
            self.assertEqual("Alice Smith", resolved["prepared_by"])
            self.assertEqual(
                (
                    "Authorized report",
                    "",
                    "Authorized standfirst.",
                ),
                self.converter.extract_report_header(md_text),
            )

    def test_visible_subtitle_changes_the_render_binding(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            source.write_text(
                "# Report\n\n## Finding\n\n"
                "First subtitle\n\nSecond subtitle\n\nEvidence.",
                encoding="utf-8",
            )
            artifacts = {
                "rewild_receipt": temp / "rewild.json",
                "ledger": temp / "ledger.json",
                "content_receipt": temp / "content.json",
                "source_fidelity_receipt": temp / "source.json",
            }
            for name, path in artifacts.items():
                path.write_text(
                    (
                        json.dumps({"approved_visual_assets": []})
                        if name == "content_receipt"
                        else name
                    ),
                    encoding="utf-8",
                )
            bindings = []
            with (
                mock.patch.object(
                    self.converter,
                    "validate_rewild_for_render",
                    return_value=None,
                ),
                mock.patch.object(
                    self.converter,
                    "validate_content_for_render",
                    return_value=None,
                ),
            ):
                for index, subtitle in enumerate(("First subtitle", "Second subtitle")):
                    output = temp / f"report-{index}.pdf"
                    self.converter.render_pdf(
                        source,
                        output,
                        subtitle=subtitle,
                        **artifacts,
                    )
                    bindings.append(
                        (PdfReader(output).metadata or {}).get("/Keywords")
                    )
        self.assertNotEqual(bindings[0], bindings[1])

    def test_local_image_bytes_change_the_render_binding(self):
        from PIL import Image
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            image = temp / "figure.png"
            source.write_text(
                "# Report\n\n## Finding\n\n![Figure](figure.png)",
                encoding="utf-8",
            )
            artifacts = {
                "rewild_receipt": temp / "rewild.json",
                "ledger": temp / "ledger.json",
                "content_receipt": temp / "content.json",
                "source_fidelity_receipt": temp / "source.json",
            }
            for name, path in artifacts.items():
                path.write_text(
                    (
                        json.dumps({"approved_visual_assets": []})
                        if name == "content_receipt"
                        else name
                    ),
                    encoding="utf-8",
                )
            bindings = []
            with (
                mock.patch.object(
                    self.converter,
                    "validate_rewild_for_render",
                    return_value=None,
                ),
                mock.patch.object(
                    self.converter,
                    "validate_content_for_render",
                    return_value=None,
                ),
            ):
                for index, color in enumerate(("red", "blue")):
                    Image.new("RGB", (8, 8), color=color).save(image)
                    artifacts["content_receipt"].write_text(
                        json.dumps(
                            {
                                "approved_visual_assets": [
                                    {
                                        "path": "figure.png",
                                        "sha256": hashlib.sha256(
                                            image.read_bytes()
                                        ).hexdigest(),
                                    }
                                ]
                            }
                        ),
                        encoding="utf-8",
                    )
                    output = temp / f"image-report-{index}.pdf"
                    self.converter.render_pdf(
                        source,
                        output,
                        **artifacts,
                    )
                    bindings.append(
                        (PdfReader(output).metadata or {}).get("/Keywords")
                    )
        self.assertNotEqual(bindings[0], bindings[1])

    def test_unapproved_custom_cover_image_cannot_render(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            cover = temp / "cover.png"
            source.write_text("# Report\n\n## Finding\n\nEvidence.", encoding="utf-8")
            Image.new("RGB", (1000, 600), "white").save(cover)
            content_receipt = temp / "content.json"
            content_receipt.write_text(
                json.dumps({"approved_visual_assets": []}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unapproved visual asset"):
                self.render_pdf(
                    source,
                    output,
                    cover_image=cover,
                    template="maison",
                    content_receipt=content_receipt,
                )
            self.assertFalse(output.exists())

    def test_approved_custom_cover_image_can_render(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            cover = temp / "cover.png"
            source.write_text("# Report\n\n## Finding\n\nEvidence.", encoding="utf-8")
            Image.new("RGB", (1000, 600), "white").save(cover)
            content_receipt = temp / "content.json"
            content_receipt.write_text(
                json.dumps(
                    {
                        "approved_visual_assets": [
                            {
                                "path": "cover.png",
                                "sha256": hashlib.sha256(
                                    cover.read_bytes()
                                ).hexdigest(),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.render_pdf(
                source,
                output,
                cover_image=cover,
                template="maison",
                content_receipt=content_receipt,
            )
            self.assertTrue(output.exists())

    def test_unapproved_markdown_body_image_cannot_render(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            body_image = temp / "body.png"
            Image.new("RGB", (1000, 600), "white").save(body_image)
            source.write_text(
                "# Report\n\n## Finding\n\n![](body.png)",
                encoding="utf-8",
            )
            content_receipt = temp / "content.json"
            content_receipt.write_text(
                json.dumps({"approved_visual_assets": []}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unapproved visual asset"):
                self.render_pdf(
                    source,
                    output,
                    content_receipt=content_receipt,
                )
            self.assertFalse(output.exists())

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


class DesignRegressionTests(unittest.TestCase):
    """Regressions for defects an editorial review found in shipped PDFs."""

    def setUp(self):
        self.converter = load_converter()
        self.css = self.converter.build_css(
            "blueprint",
            font_sans="sans",
            font_display="serif",
            font_mono="mono",
            header_text="header",
            page_label="",
            page_suffix="",
            footer_text="footer",
            insight_label="insight",
            takeaway_label="takeaway",
        )

    def rule(self, pattern):
        match = re.search(pattern, self.css, re.DOTALL)
        self.assertIsNotNone(match, f"no CSS rule matched {pattern!r}")
        return match.group(0)

    def test_running_header_is_centred_in_a_deeper_top_margin(self):
        # vertical-align: bottom in a 21mm margin parked the running head about
        # 2mm above the first body baseline on roughly half the pages.
        page_rule = self.rule(r"@page \{.*?\n\}")
        self.assertIn("margin: 26mm 18mm 19mm 18mm", page_rule)
        top_boxes = page_rule.split("@bottom-left")[0]
        self.assertNotIn("vertical-align: bottom", top_boxes)
        self.assertEqual(top_boxes.count("vertical-align: middle"), 2)

    def test_h2_accent_rule_uses_padding_so_it_survives_a_page_break(self):
        rule = self.rule(r"\nh2 \{[^}]*\}")
        self.assertIn("padding: 7mm 0 3.5mm", rule)
        self.assertNotIn("margin: 11mm", rule)

    def test_inline_code_does_not_break_across_lines(self):
        self.assertIn("white-space: nowrap", self.rule(r"\ncode \{[^}]*\}"))
        self.assertIn("white-space: inherit", self.rule(r"\npre code \{[^}]*\}"))

    def test_body_links_carry_a_non_colour_affordance(self):
        rule = self.rule(r"\na \{[^}]*\}")
        self.assertIn("text-decoration: underline", rule)
        # Mid-word breaking belongs to raw URLs, not to link titles.
        self.assertNotIn("overflow-wrap", rule)
        self.assertIn("a[href]::after,", self.css)

    def test_citation_marker_is_a_bare_numeral_in_the_text_face(self):
        rule = self.rule(r"\.source-ref \{[^}]*\}")
        self.assertNotIn("__FONT_MONO__", rule)
        self.assertNotIn("mono", rule)
        self.assertIn("vertical-align: super", rule)

    def test_sources_page_groups_each_url_with_its_own_entry(self):
        rule = self.rule(r'\.sources-section a\[href\^="http"\]::after \{[^}]*\}')
        # The literal \A injected a phantom blank line that pushed every URL
        # toward the following entry instead of its own.
        content = re.search(r"content: [^;]+;", rule).group(0)
        self.assertEqual(content, "content: attr(href);")
        self.assertIn("margin-top", rule)

    def test_sources_entries_have_a_hanging_indent_and_their_own_page(self):
        item_rule = self.rule(r"\.sources-section li \{[^}]*\}")
        self.assertIn("padding-left: 9mm", item_rule)
        self.assertIn("text-indent: -9mm", item_rule)
        section_rule = self.rule(r"\.sources-section \{[^}]*\}")
        self.assertIn("page-break-before: always", section_rule)
        self.assertIn("page: sources", section_rule)
        self.assertIn("ALEXANDRIA  /  SOURCES", self.rule(r"@page sources \{[^}]*\}"))

    def test_toc_folio_is_not_optically_smaller_than_the_title(self):
        folio = self.rule(r"\.toc-page-number \{[^}]*\}")
        size = float(re.search(r"font-size: ([\d.]+)pt", folio).group(1))
        self.assertGreaterEqual(size, 10.0)
        # Truncated teasers are gone entirely.
        self.assertNotIn("toc-summary", self.css)

    def test_opener_never_spills_onto_a_second_sheet(self):
        rule = self.rule(
            r"\.horizon-feature-lower,\s*\.horizon-feature-narrative,"
            r"\s*\.horizon-feature-path \{[^}]*\}"
        )
        self.assertIn("break-inside: avoid", rule)

    def test_toc_pages_are_balanced_not_fixed_size(self):
        chunks = self.converter.balanced_toc_chunks(list(range(15)), 12)
        self.assertEqual([len(chunk) for chunk in chunks], [8, 7])
        self.assertEqual(
            [len(c) for c in self.converter.balanced_toc_chunks(list(range(12)), 12)],
            [12],
        )
        # No page is ever left holding two entries above a sheet of blank paper.
        for size in range(1, 40):
            with self.subTest(entries=size):
                counts = [
                    len(c)
                    for c in self.converter.balanced_toc_chunks(list(range(size)), 12)
                ]
                self.assertLessEqual(max(counts) - min(counts), 1)

    def test_toc_entries_carry_no_teaser_text(self):
        rendered = self.converter.build_toc_html(
            '<h2 id="one">One</h2><p>A summary that used to be truncated.</p>'
            '<h2 id="two">Two</h2><p>Another summary.</p>',
            "en",
            "executive",
        )
        self.assertNotIn("toc-summary", rendered)
        self.assertNotIn("used to be truncated", rendered)

    def test_opener_numbering_is_derived_from_the_real_section(self):
        body = (
            '<h2 id="one">Opening section</h2><p>Short lede.</p>'
            '<h2 id="two">Second</h2><p>More.</p>'
        )
        feature, _ = self.converter.build_reference_feature_html(
            body, "en", "blueprint", None, decorative_image=True
        )
        # The shipped opener always claimed "03" while sitting on section 01.
        self.assertIn("System note 01", feature)
        self.assertNotIn("System note 03", feature)
        self.assertNotIn("{sec}", feature)

    def test_templates_without_photography_get_a_generated_plate(self):
        body = '<h2 id="one">Opening section</h2><p>Short lede.</p>'
        feature, _ = self.converter.build_reference_feature_html(
            body, "en", "blueprint", None, decorative_image=True
        )
        self.assertIn('class="feature-plate"', feature)
        self.assertNotIn("<img", feature)
        # Blueprint borrowed Orbit's photograph and Sunbeam borrowed Current's.
        self.assertNotIn("blueprint", self.converter.BUNDLED_TEMPLATE_IMAGES)
        self.assertNotIn("sunbeam", self.converter.BUNDLED_TEMPLATE_IMAGES)

    def test_opener_card_is_capped_so_the_lower_grid_still_fits(self):
        long_insight = "word " * 400
        body = (
            '<h2 id="one">Opening section</h2>'
            f'<aside class="insight-panel"><p>{long_insight}</p></aside>'
            "<p>A short narrative paragraph.</p>"
        )
        feature, remaining = self.converter.build_reference_feature_html(
            body, "en", "blueprint", None, decorative_image=True
        )
        self.assertNotIn(long_insight.strip(), feature)
        self.assertIn("insight-panel", remaining)

    def test_zh_stacks_are_script_pure(self):
        simplified = self.converter.FONT_SANS_CN + self.converter.FONT_SERIF_CN
        traditional = self.converter.FONT_SANS_HK + self.converter.FONT_SERIF_HK
        for marker in ("HK", "TC", "JhengHei", "PMingLiU"):
            self.assertNotIn(marker, simplified)
        for marker in ("SC", "YaHei", "SimSun"):
            self.assertNotIn(marker, traditional)
        # No generic terminator: fontconfig answered `serif` with Songti in
        # whichever script it felt like, which is how a zh-HK document ended up
        # carrying Songti SC-Bold.
        for stack in (self.converter.FONT_SANS_CN, self.converter.FONT_SERIF_CN,
                      self.converter.FONT_SANS_HK, self.converter.FONT_SERIF_HK):
            self.assertFalse(stack.rstrip().endswith("serif"))
        # Hiragino is Japanese and has no business in a Chinese document.
        self.assertNotIn("Hiragino", traditional)

    def test_mono_stack_is_locale_aware(self):
        settings = self.converter.localized_settings("zh-HK", "maison")
        self.assertIn("PingFang HK", settings["font_mono"])
        self.assertFalse(settings["font_mono"].rstrip().endswith("monospace"))
        english = self.converter.localized_settings("en", "maison")["font_mono"]
        self.assertTrue(english.rstrip().endswith("monospace"))

    def test_cjk_typography_is_not_latin_css(self):
        block = self.rule(r'html\[lang\^="zh"\] body \{[^}]*\}')
        self.assertIn("text-align: justify", block)
        self.assertIn("line-break: strict", block)
        self.assertIn("text-spacing", block)

    def test_struct_ids_are_deterministic(self):
        from weasyprint.pdf import tags

        one, two = object(), object()
        with self.converter.deterministic_struct_ids():
            first, second = tags.id(one), tags.id(two)
            self.assertNotEqual(first, second)
            self.assertEqual(first, tags.id(one))
            self.assertIsInstance(first, int)
        self.assertNotIn("id", tags.__dict__)

    def test_reproducible_epoch_is_restored_after_a_render(self):
        import os

        before = os.environ.get("SOURCE_DATE_EPOCH")
        with self.converter.deterministic_struct_ids():
            self.assertIn("SOURCE_DATE_EPOCH", os.environ)
        self.assertEqual(os.environ.get("SOURCE_DATE_EPOCH"), before)

    def test_blueprint_cover_drawing_snaps_to_the_datum_grid(self):
        # 17mm..185mm x 111mm..255mm on a 24mm grid anchored at 17mm/15mm.
        self.assertIn("background-position: 17mm 15mm", self.css)
        self.assertIn("inset: 111mm 25mm 42mm 17mm", self.css)
        for offset in ("left: 24mm", "top: 24mm", "width: 48mm", "height: 48mm"):
            self.assertIn(offset, self.css)
        self.assertIn("top: 72mm", self.css)
        self.assertIn("left: 96mm", self.css)
        # Body text starts on a grid line rather than 6mm off one.
        body_rule = self.rule(r"\.template-blueprint \.report-body \{[^}]*\}")
        self.assertIn("padding-left: 8mm", body_rule)

    def test_cover_diagrams_do_not_pretend_to_be_informative(self):
        art = self.converter.cover_art_html("blueprint")
        # A/B/C node labels had no legend and no referent.
        self.assertNotIn(">A<", art)
        self.assertNotIn(">B<", art)
        self.assertNotIn(">C<", art)
        self.assertNotIn(".executive-scale::after", self.css)


if __name__ == "__main__":
    unittest.main()
