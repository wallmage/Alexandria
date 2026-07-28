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

    def test_refuses_nonempty_output_directory_before_loading_pdfium(self):
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


if __name__ == "__main__":
    unittest.main()
