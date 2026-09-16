import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_pdf_pages.py"


class RenderPagesCommandTests(unittest.TestCase):
    def test_windows_finds_ghostscript_outside_path(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            program_files = Path(temp_dir) / "Program Files"
            executable = program_files / "gs" / "gs10.07.0" / "bin" / "gswin64c.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"")

            with (
                mock.patch.object(render_pdf_pages.sys, "platform", "win32"),
                mock.patch.object(
                    render_pdf_pages.shutil, "which", return_value=None
                ),
                mock.patch.dict(
                    os.environ,
                    {"PROGRAMFILES": str(program_files)},
                    clear=False,
                ),
            ):
                try:
                    command = render_pdf_pages._renderer_command(
                        "gs", "gswin64c", "gswin32c"
                    )
                except RuntimeError:
                    command = None

        self.assertEqual(str(executable), command)

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

    @unittest.skipUnless(
        all(shutil.which(command) for command in ("pdftocairo", "mutool", "gs")),
        "requires Poppler, MuPDF, and Ghostscript",
    )
    def test_portability_backends_render_every_page(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            writer.add_blank_page(width=300, height=400)
            with pdf.open("wb") as stream:
                writer.write(stream)

            for backend in ("poppler", "mupdf", "ghostscript"):
                with self.subTest(backend=backend):
                    output = temp / backend
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            str(pdf),
                            str(output),
                            "--backend",
                            backend,
                            "--dpi",
                            "72",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(2, len(list(output.glob("page-*.png"))))

    def test_out_dir_alias_matches_positional_output_dir(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            with mock.patch.object(render_pdf_pages, "render_pages") as render:
                code = render_pdf_pages.main(
                    [str(pdf), "--out-dir", str(output)]
                )
        self.assertEqual(0, code)
        render.assert_called_once()
        self.assertEqual(Path(output), Path(render.call_args.args[1]))

    def test_auto_fallback_tries_pdfium_then_pdfkit_then_poppler(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            output.mkdir()
            order = []

            def fail(name):
                def _inner(*args, **kwargs):
                    order.append(name)
                    raise RuntimeError(f"{name} exploded\nwith detail")

                return _inner

            def succeed(*args, **kwargs):
                order.append("poppler")
                (output / "page-0001.png").write_bytes(b"png")

            with (
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=fail("pdfkit")
                ),
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfium", side_effect=fail("pdfium")
                ),
                mock.patch.object(
                    render_pdf_pages, "render_with_poppler", side_effect=succeed
                ),
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock()),
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin"),
            ):
                selected, failures = render_pdf_pages.render_pages(
                    pdf, output, backend="auto"
                )

        self.assertEqual(["pdfium", "pdfkit", "poppler"], order)
        self.assertEqual("poppler", selected)
        self.assertTrue(any(item.startswith("pdfkit:") for item in failures), failures)
        self.assertTrue(any(item.startswith("pdfium:") for item in failures), failures)

    def test_darwin_auto_chain_tries_pdfium_before_pdfkit_and_isolates_subprocesses(
        self,
    ):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            order = []

            def fail_pdfium(*args, **kwargs):
                order.append("pdfium")
                raise RuntimeError("pdfium missing")

            def succeed_pdfkit(*args, **kwargs):
                order.append("pdfkit")
                (output / "page-0001.png").write_bytes(b"png")

            with (
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfium", side_effect=fail_pdfium
                ),
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=succeed_pdfkit
                ),
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock()),
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin"),
            ):
                selected, failures = render_pdf_pages.render_pages(
                    pdf, output, backend="auto"
                )

        self.assertEqual(["pdfium", "pdfkit"], order)
        self.assertEqual("pdfkit", selected)
        self.assertEqual(["pdfium: pdfium missing"], failures)

        recorded = []

        def fake_run(*args, **kwargs):
            recorded.append(kwargs)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(
                render_pdf_pages.subprocess, "run", side_effect=fake_run
            ),
            mock.patch.object(
                render_pdf_pages.shutil, "which", return_value="/usr/bin/swift"
            ),
        ):
            render_pdf_pages.render_with_pdfkit(Path("in.pdf"), Path("out"), dpi=96)
            render_pdf_pages._run_renderer(["/bin/true"], "Poppler")

        self.assertEqual(2, len(recorded))
        for kwargs in recorded:
            self.assertIs(kwargs.get("stdin"), subprocess.DEVNULL)
            self.assertIs(kwargs.get("start_new_session"), True)

    def test_auto_fallback_exposes_selected_backend_and_failures(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")

            def succeed(*args, **kwargs):
                (output / "page-0001.png").write_bytes(b"png")

            with (
                mock.patch.object(
                    render_pdf_pages,
                    "render_with_pdfium",
                    side_effect=RuntimeError("pdfium missing"),
                ),
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=succeed
                ),
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock()),
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin"),
            ):
                selected, failures = render_pdf_pages.render_pages(
                    pdf, output, backend="auto"
                )

        self.assertEqual("pdfkit", selected)
        self.assertEqual(["pdfium: pdfium missing"], failures)

    def test_fallback_errors_are_one_line_each(self):
        from scripts import render_pdf_pages

        cases = (
            ("darwin", ("pdfkit:", "pdfium:", "poppler:"), ()),
            ("linux", ("pdfium:", "poppler:"), ("pdfkit:",)),
        )
        for platform, present, absent in cases:
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp = Path(temp_dir)
                    pdf = temp / "report.pdf"
                    output = temp / "pages"
                    pdf.write_bytes(b"%PDF")
                    with (
                        mock.patch.object(
                            render_pdf_pages,
                            "render_with_pdfkit",
                            side_effect=RuntimeError("pdfkit failed\nstack"),
                        ),
                        mock.patch.object(
                            render_pdf_pages,
                            "render_with_pdfium",
                            side_effect=RuntimeError("pdfium failed\nstack"),
                        ),
                        mock.patch.object(
                            render_pdf_pages,
                            "render_with_poppler",
                            side_effect=RuntimeError("poppler failed\nstack"),
                        ),
                        mock.patch.object(
                            render_pdf_pages.sys, "platform", platform
                        ),
                        self.assertRaises(RuntimeError) as raised,
                    ):
                        render_pdf_pages.render_pages(
                            pdf, output, backend="auto"
                        )
                message = str(raised.exception)
                self.assertNotIn("\n", message)
                for token in present:
                    self.assertIn(token, message)
                for token in absent:
                    self.assertNotIn(token, message)

    def test_subprocess_renderers_use_90s_timeout(self):
        from scripts import render_pdf_pages

        captured = {}

        def fake_run(*args, **kwargs):
            captured.update(kwargs)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(render_pdf_pages.shutil, "which", return_value="/bin/pdftocairo"),
            mock.patch.object(render_pdf_pages.subprocess, "run", side_effect=fake_run),
            mock.patch.object(render_pdf_pages, "_normalize_page_names"),
        ):
            render_pdf_pages.render_with_poppler(
                Path("in.pdf"), Path("out"), dpi=72
            )
        self.assertEqual(90, captured.get("timeout"))

    def test_pdfium_timeout_falls_through_to_next_backend(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            order = []

            def timeout(*args, **kwargs):
                order.append("pdfium")
                raise subprocess.TimeoutExpired(cmd="pdfium", timeout=90)

            def succeed(*args, **kwargs):
                order.append("pdfkit")
                (output / "page-0001.png").write_bytes(b"png")

            with (
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfium", side_effect=timeout
                ),
                mock.patch.object(
                    render_pdf_pages, "render_with_pdfkit", side_effect=succeed
                ),
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock()),
                mock.patch.object(render_pdf_pages.sys, "platform", "darwin"),
            ):
                render_pdf_pages.render_pages(pdf, output, backend="auto")
        self.assertEqual(["pdfium", "pdfkit"], order)

    def test_force_allows_nonempty_output_directory(self):
        from scripts import render_pdf_pages

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            pdf = temp / "report.pdf"
            output = temp / "pages"
            pdf.write_bytes(b"%PDF")
            output.mkdir()
            (output / "mine.txt").write_text("keep", encoding="utf-8")
            with (
                mock.patch.object(
                    render_pdf_pages,
                    "render_with_pdfkit",
                    side_effect=RuntimeError("skip"),
                ),
                mock.patch.object(
                    render_pdf_pages,
                    "render_with_pdfium",
                    side_effect=RuntimeError("skip"),
                ),
                mock.patch.object(
                    render_pdf_pages,
                    "render_with_poppler",
                    side_effect=lambda *a, **k: (output / "page-0001.png").write_bytes(
                        b"png"
                    ),
                ),
                mock.patch.object(render_pdf_pages.sys, "stdout", mock.Mock()),
            ):
                render_pdf_pages.render_pages(
                    pdf, output, backend="auto", force=True
                )
            self.assertEqual("keep", (output / "mine.txt").read_text(encoding="utf-8"))
            self.assertTrue((output / "page-0001.png").is_file())


if __name__ == "__main__":
    unittest.main()
