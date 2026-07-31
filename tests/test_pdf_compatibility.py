import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from scripts import pdf_compatibility


class PdfCompatibilityTests(unittest.TestCase):
    def test_identical_render_sets_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            for directory in (reference, candidate):
                Image.new("RGB", (100, 120), "white").save(
                    directory / "page-0001.png"
                )

            errors, metrics = pdf_compatibility.compare_render_sets(
                reference, candidate
            )

        self.assertEqual(errors, [])
        self.assertEqual(metrics["page_count"], 1)

    def test_missing_visual_detail_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            detailed = Image.new("RGB", (100, 120), "white")
            for x in range(10, 90, 4):
                for y in range(10, 110):
                    detailed.putpixel((x, y), (0, 0, 0))
            detailed.save(reference / "page-0001.png")
            Image.new("RGB", (100, 120), "white").save(
                candidate / "page-0001.png"
            )

            errors, _ = pdf_compatibility.compare_render_sets(
                reference, candidate
            )

        self.assertTrue(errors)
        self.assertIn("visual detail", errors[0])

    def test_renderer_sharpness_is_not_treated_as_missing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            for directory in (reference, candidate):
                Image.new("RGB", (100, 120), "white").save(
                    directory / "page-0001.png"
                )

            with mock.patch.object(
                pdf_compatibility,
                "_edge_energy",
                side_effect=(1.0, 1.5),
            ):
                errors, _ = pdf_compatibility.compare_render_sets(
                    reference, candidate
                )

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
