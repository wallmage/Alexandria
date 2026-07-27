import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "md_to_pdf.py"


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

    def test_rejects_non_pdf_output_before_loading_render_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "report.md"
            source.write_text("# Report\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-S", str(SCRIPT), str(source), str(source.with_suffix(".txt"))],
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

    def test_detects_english_simplified_and_traditional_chinese(self):
        self.assertEqual(self.converter.detect_language("A report about markets."), "en")
        self.assertEqual(self.converter.detect_language("这是一份关于市场的研究报告。"), "zh-CN")
        self.assertEqual(self.converter.detect_language("這是一份關於市場的研究報告。"), "zh-HK")

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

            def write_pdf(self, target):
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
                self.converter.render_pdf(source, output)

            self.assertEqual(calls["base_url"], source.parent.resolve())
            self.assertTrue(output.exists())

    def test_failed_render_preserves_existing_pdf(self):
        class FailingHTML:
            def __init__(self, **kwargs):
                pass

            def write_pdf(self, target):
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
                    self.converter.render_pdf(source, output, force=True)

            self.assertEqual(b"existing", output.read_bytes())

    def test_existing_pdf_requires_explicit_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "report.md"
            output = temp / "report.pdf"
            source.write_text("# Report\n", encoding="utf-8")
            output.write_bytes(b"existing")

            with self.assertRaisesRegex(ValueError, "already exists"):
                self.converter.render_pdf(source, output)

            self.assertEqual(b"existing", output.read_bytes())

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
            ):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    self.converter.render_pdf(source, output, keep_html=True)

            self.assertEqual("mine", sidecar.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
