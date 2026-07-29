import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from scripts import md_to_pdf
from scripts.render_binding import (
    binding_meta_tag,
    build_render_receipt,
    expected_render_binding,
    validate_render_binding,
    validate_render_receipt,
)


class RenderBindingTests(unittest.TestCase):
    def make_artifacts(self, root):
        paths = []
        for name, content in (
            ("report.md", "report"),
            ("ledger.json", "ledger"),
            ("rewild.json", "rewild"),
            ("content.json", "content"),
            ("source.json", "source"),
        ):
            path = root / name
            path.write_text(content, encoding="utf-8")
            paths.append(path)
        return paths

    def test_binding_changes_when_any_gated_artifact_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_artifacts(Path(directory))
            original = expected_render_binding(*paths)
            paths[2].write_text("changed rewild receipt", encoding="utf-8")
            changed = expected_render_binding(*paths)
        self.assertNotEqual(original, changed)

    def test_validation_rejects_pdf_bound_to_a_different_report(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_artifacts(Path(directory))
            stale = expected_render_binding(*paths)
            paths[0].write_text("a different report", encoding="utf-8")
            errors = validate_render_binding(stale, *paths)
        self.assertTrue(any("different gated artifacts" in error for error in errors))

    def test_metadata_tag_carries_only_the_canonical_binding_token(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_artifacts(Path(directory))
            binding = expected_render_binding(*paths)
            tag = binding_meta_tag(binding)
        self.assertEqual(
            f'<meta name="keywords" content="{binding}">',
            tag,
        )

    def test_render_receipt_rejects_different_pdf_bytes_with_copied_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_artifacts(root)
            pdf = root / "report.pdf"
            pdf.write_bytes(b"renderer output")
            binding = expected_render_binding(*paths)
            receipt = build_render_receipt(
                pdf,
                *paths,
                binding=binding,
                render_inputs={},
                rendered_html=None,
            )
            pdf.write_bytes(b"unrelated PDF with copied metadata token")
            errors = validate_render_receipt(
                pdf,
                receipt,
                *paths,
                pdf_binding=binding,
            )
        self.assertTrue(
            any("PDF bytes" in error for error in errors),
            errors,
        )

    def test_self_authored_receipt_for_clean_unrelated_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_artifacts(root)
            paths[0].write_text(
                "# Authorized report\n\n## Finding\n\nAuthorized evidence.",
                encoding="utf-8",
            )
            forged_pdf = root / "report.pdf"
            render_inputs = {
                "title": None,
                "subtitle": None,
                "lang": "en",
                "template": "executive",
                "client": None,
                "prepared_by": "Alexandria",
                "confidential": False,
                "report_date": "29 July 2026",
                "cover_image": None,
            }
            unrelated_html = md_to_pdf.md_to_html(
                "# Unrelated report\n\n## Finding\n\nInvented clean content.",
                **render_inputs,
            )
            assets = md_to_pdf.collect_render_assets(unrelated_html, root)
            binding = expected_render_binding(
                *paths,
                render_inputs=render_inputs,
                rendered_html=unrelated_html,
                assets=assets,
            )
            forged_html = unrelated_html.replace(
                "</head>",
                binding_meta_tag(binding) + "</head>",
                1,
            )
            HTML = md_to_pdf.load_weasyprint_html()
            with md_to_pdf.deterministic_struct_ids():
                HTML(
                    string=forged_html,
                    base_url=root,
                    url_fetcher=md_to_pdf.make_url_fetcher(root),
                ).write_pdf(forged_pdf, pdf_tags=True)
            receipt = build_render_receipt(
                forged_pdf,
                *paths,
                binding=binding,
                render_inputs=render_inputs,
                rendered_html=unrelated_html,
                assets=assets,
            )
            pdf_binding = (PdfReader(forged_pdf).metadata or {}).get(
                "/Keywords"
            )
            errors = validate_render_receipt(
                forged_pdf,
                receipt,
                *paths,
                pdf_binding=pdf_binding,
            )
        self.assertTrue(
            any("deterministic rerender" in error.lower() for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
