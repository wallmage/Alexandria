import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_pdf_pages.py"


class RenderPagesCommandTests(unittest.TestCase):
    def test_help_works_without_optional_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-S", str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--dpi", result.stdout)

    def test_refuses_nonempty_output_directory_before_loading_renderer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            output.mkdir()
            (output / "mine.txt").write_text("keep", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-S", str(SCRIPT), str(pdf), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("must be empty", result.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS PDFKit")
    def test_macos_default_renders_without_pdfium(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            with pdf.open("wb") as stream:
                writer.write(stream)

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    str(pdf),
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((output / "page-0001.png").is_file())

    @unittest.skipUnless(sys.platform == "darwin", "requires macOS PDFKit")
    def test_blueprint_background_matches_pdfkit_and_pdfium(self):
        from PIL import Image, ImageChops
        from weasyprint import HTML

        from scripts.pdf_templates import build_css
        from scripts.render_pdf_pages import render_pages

        css = build_css(
            "blueprint",
            font_sans='"Arial Unicode MS"',
            font_display='"Arial Unicode MS"',
            font_mono='"Arial Unicode MS"',
            header_text="",
            page_label="",
            page_suffix="",
            footer_text="",
            insight_label="",
            takeaway_label="",
        )
        html = (
            "<html><head><style>"
            + css
            + "</style></head><body>"
            '<div class="report template-blueprint">'
            '<section class="cover"></section>'
            "</div></body></html>"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "blueprint.pdf"
            native = temp / "pdfkit"
            cross_platform = temp / "pdfium"
            HTML(string=html).write_pdf(pdf)
            render_pages(pdf, native, dpi=96, backend="pdfkit")
            render_pages(pdf, cross_platform, dpi=96, backend="pdfium")
            pdfkit_page = Image.open(native / "page-0001.png").convert("RGB")
            pdfium_page = Image.open(
                cross_platform / "page-0001.png"
            ).convert("RGB")
            difference = ImageChops.difference(pdfkit_page, pdfium_page)
            changed_pixels = sum(
                max(pixel) > 2 for pixel in difference.get_flattened_data()
            )

        self.assertLess(
            changed_pixels,
            100,
            "Blueprint background must not depend on a tiled PDF pattern "
            "that Preview drops",
        )


if __name__ == "__main__":
    unittest.main()
