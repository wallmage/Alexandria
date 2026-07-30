import contextlib
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_md_to_pdf import encoded_raster, load_converter


class RenderBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.converter = load_converter()

    def test_write_prepared_pdf_uses_reviewed_asset_snapshot_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "figure.png"
            output = root / "report.pdf"
            original = encoded_raster("PNG", size=(1, 1))
            replacement = encoded_raster("PNG", size=(2, 1))
            image.write_bytes(original)
            prepared = {
                "bound_html": '<html><body><img src="figure.png"></body></html>',
                "assets": self.converter.collect_render_assets(
                    '<img src="figure.png">',
                    root,
                ),
            }
            image.write_bytes(replacement)
            actual_factory = self.converter.make_snapshot_url_fetcher
            fetched = {}

            class FakeHTML:
                def __init__(self, **kwargs):
                    fetched.update(kwargs["url_fetcher"](image.as_uri()))

                def write_pdf(self, target, **_options):
                    Path(target).write_bytes(b"%PDF-1.7\n")

            with (
                mock.patch.object(
                    self.converter,
                    "make_snapshot_url_fetcher",
                    side_effect=lambda asset_root, assets: actual_factory(
                        asset_root,
                        assets,
                        default_fetcher=lambda _url: {},
                    ),
                ),
                mock.patch.object(
                    self.converter,
                    "load_weasyprint_html",
                    return_value=FakeHTML,
                ),
                mock.patch.object(
                    self.converter,
                    "deterministic_struct_ids",
                    return_value=contextlib.nullcontext(),
                ),
            ):
                self.converter.write_prepared_pdf(
                    prepared,
                    output,
                    asset_root=root,
                )

            self.assertEqual(original, fetched["string"])
            self.assertEqual(replacement, image.read_bytes())

    def test_source_receipt_swap_after_content_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "report.md"
            ledger = root / "ledger.json"
            source_receipt = root / "source-receipt.json"
            content_receipt = root / "content-receipt.json"
            report.write_text("# Report\n", encoding="utf-8")
            ledger.write_text("{}", encoding="utf-8")
            source_receipt.write_text('{"reviewed": true}', encoding="utf-8")
            content_receipt.write_text(
                json.dumps(
                    {
                        "report_lang": "en",
                        "source_fidelity_receipt_sha256": hashlib.sha256(
                            source_receipt.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )

            def swap_receipt(*_args, **_kwargs):
                source_receipt.write_text(
                    '{"forged": true}',
                    encoding="utf-8",
                )
                return []

            with (
                mock.patch.object(
                    self.converter,
                    "validate_content_receipt",
                    side_effect=swap_receipt,
                ),
                mock.patch.object(
                    self.converter,
                    "validate_source_fidelity_receipt_online",
                ) as online,
                self.assertRaisesRegex(
                    ValueError,
                    "changed after content review",
                ),
            ):
                self.converter.validate_content_for_render(
                    report,
                    ledger,
                    content_receipt,
                    "en",
                    source_receipt,
                )
            online.assert_not_called()

    def test_report_replacement_after_gate_cannot_enter_prepared_render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "report.md"
            output = root / "report.pdf"
            original = "# Reviewed report\n"
            report.write_text(original, encoding="utf-8")
            validated_receipt = {
                "report_sha256": hashlib.sha256(
                    original.encode("utf-8")
                ).hexdigest(),
                "approved_visual_assets": [],
            }

            def validate_then_replace(*_args, **_kwargs):
                report.write_text(
                    "# Unreviewed replacement\n",
                    encoding="utf-8",
                )
                return validated_receipt

            prepared = {"bound_html": "<html></html>", "assets": []}
            with (
                mock.patch.object(
                    self.converter,
                    "validate_rewild_for_render",
                    return_value=None,
                ),
                mock.patch.object(
                    self.converter,
                    "validate_content_for_render",
                    side_effect=validate_then_replace,
                ),
                mock.patch.object(
                    self.converter,
                    "prepare_pdf_render",
                    return_value=prepared,
                ) as prepare,
                mock.patch.object(
                    self.converter,
                    "write_prepared_pdf",
                    side_effect=lambda _prepared, target, **_kwargs: Path(
                        target
                    ).write_bytes(b"%PDF-1.7\n"),
                ),
            ):
                self.converter.render_pdf(
                    report,
                    output,
                    rewild_receipt=root / "rewild.json",
                    ledger=root / "ledger.json",
                    content_receipt=root / "content.json",
                    source_fidelity_receipt=root / "source.json",
                )

            self.assertEqual(
                original,
                prepare.call_args.kwargs["report_text"],
            )
            self.assertIs(
                validated_receipt,
                prepare.call_args.kwargs["content_receipt_data"],
            )
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
