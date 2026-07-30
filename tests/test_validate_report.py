import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("validate_report", MODULE_PATH)
validate_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_report)


GOOD_REPORT = """# A useful report

> July 2026

## Executive summary

This is a compact but substantive summary with evidence [from a source](https://example.com/a).

## Analysis

The analysis explains the mechanism, trade-offs, and uncertainty in enough detail to be useful.

## Outlook

The outlook separates observation from inference and names what could change the conclusion.

## Sources

- [Primary source](https://example.com/a)
- [Corroborating source](https://example.org/b)
"""


class MarkdownValidationTests(unittest.TestCase):
    def test_accepts_well_formed_report(self):
        errors = validate_report.validate_markdown(
            GOOD_REPORT, min_words=40, min_chars=100, min_sources=2, min_sections=3
        )
        self.assertEqual([], errors)

    def test_character_floor_supports_chinese_reports(self):
        errors = validate_report.validate_markdown(
            "# 标题\n\n## 正文\n\n内容很短。\n\n## 来源\n\n- [资料](https://example.com)",
            min_chars=200,
            min_sources=1,
            min_sections=2,
        )
        self.assertTrue(any("characters" in error for error in errors))

    def test_rejects_reports_above_word_or_character_ceiling(self):
        errors = validate_report.validate_markdown(
            GOOD_REPORT,
            max_words=10,
            max_chars=50,
            min_sources=1,
            min_sections=1,
        )
        self.assertTrue(any("maximum is 10" in error for error in errors))
        self.assertTrue(any("maximum is 50" in error for error in errors))

    def test_length_excludes_sources_urls_markup_and_code(self):
        inflated = """# Title

## Analysis

Thin.

```text
one two three four five six seven eight nine ten
```

    eleven twelve thirteen fourteen fifteen

<pre>sixteen seventeen eighteen nineteen twenty</pre>

````text
```
payload payload payload payload payload payload payload payload payload payload
````

## Sources

- [Source](https://example.com/{})
""".format("/research" * 500)
        errors = validate_report.validate_markdown(
            inflated,
            min_words=10,
            min_chars=100,
            min_sources=1,
            min_sections=2,
        )
        self.assertTrue(any("words" in error for error in errors))
        self.assertTrue(any("characters" in error for error in errors))

    def test_expected_language_distinguishes_chinese_variants(self):
        simplified = "# 标题\n\n## 正文\n\n这是关于市场与发展的报告。\n\n## 来源\n\n- [资料](https://example.com)"
        errors = validate_report.validate_markdown(
            simplified,
            min_sources=1,
            min_sections=2,
            expected_lang="zh-HK",
        )
        self.assertTrue(any("expected zh-HK" in error for error in errors))

        neutral = simplified.replace(
            "这是关于市场与发展的报告",
            "人工智能模型性能分析\n\n```js\n"
            + ("identifierName " * 100)
            + "\n```",
        )
        errors = validate_report.validate_markdown(
            neutral,
            min_sources=1,
            min_sections=2,
            expected_lang="zh-CN",
        )
        self.assertFalse(any("expected zh-CN" in error for error in errors))

        traditional = (
            "# 报告\n\n## 分析\n\n"
            + "經濟風險評估趨勢監測維護規劃環境財務審計價值運營競爭優勢決策治理"
            * 20
            + "\n\n## 来源\n\n[资料](https://example.com)"
        )
        errors = validate_report.validate_markdown(
            traditional,
            min_sources=1,
            min_sections=2,
            expected_lang="zh-CN",
        )
        self.assertTrue(
            any("Traditional" in error for error in errors),
            errors,
        )

        simplified_with_quote = (
            "# 报告\n\n## 分析\n\n"
            + "市场研究显示数据支持结论风险可控方案有效。" * 250
            + "\n\n> 「香港證券及期貨事務監察委員會指出，"
            "該機構將繼續監察市場風險，並維護投資者權益。」"
            "\n\n## 来源\n\n[资料](https://example.com)"
        )
        errors = validate_report.validate_markdown(
            simplified_with_quote,
            min_sources=1,
            min_sections=2,
            expected_lang="zh-CN",
        )
        self.assertFalse(
            any("Traditional" in error for error in errors),
            errors,
        )

    def test_rejects_empty_or_structurally_incomplete_report(self):
        errors = validate_report.validate_markdown(
            "", min_words=1, min_sources=1, min_sections=1
        )
        self.assertIn("Report is empty.", errors)

        errors = validate_report.validate_markdown(
            "# Title\n\n## Sources\n\n- https://example.com",
            min_words=20,
            min_sources=1,
            min_sections=2,
        )
        self.assertTrue(any("words" in error for error in errors))
        self.assertTrue(any("sections" in error for error in errors))

    def test_requires_sources_as_final_section_and_markdown_links(self):
        report = """# Title

## Sources
- https://example.com/raw

## Epilogue
Words after the sources section.
"""
        errors = validate_report.validate_markdown(
            report, min_words=1, min_sources=1, min_sections=1
        )
        self.assertIn("Sources must be the final H2 section.", errors)
        self.assertTrue(any("Markdown links" in error for error in errors))

    def test_cli_does_not_create_success_for_invalid_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text("", encoding="utf-8")
            self.assertEqual(1, validate_report.main([str(path), "--min-words", "1"]))

    def test_cli_requires_rewild_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            path.write_text(
                "# Report\n\n## Finding\n\nEvidence.\n\n"
                "## Sources\n\n[Source](https://example.com)",
                encoding="utf-8",
            )
            self.assertEqual(1, validate_report.main([str(path)]))

    def test_cli_requires_content_receipt_after_rewild_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            report = work / "report.md"
            rewild = work / "rewild.json"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            rewild.write_text("{}", encoding="utf-8")
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    validate_report,
                    "validate_rewild_receipt",
                    return_value=[],
                ),
                redirect_stderr(stderr),
            ):
                result = validate_report.main(
                    [
                        str(report),
                        "--rewild-receipt",
                        str(rewild),
                    ]
                )
            self.assertEqual(1, result)
            self.assertIn("Content quality gate receipt is required", stderr.getvalue())

    def test_delivery_validation_rechecks_source_fidelity_online(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            report = work / "report.md"
            ledger = work / "ledger.json"
            rewild = work / "rewild.json"
            content = work / "content.json"
            source = work / "source.json"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            ledger.write_text("{}", encoding="utf-8")
            rewild.write_text("{}", encoding="utf-8")
            source.write_text('{"status": "passed"}', encoding="utf-8")
            content.write_text(
                json.dumps(
                    {
                        "source_fidelity_receipt_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest()
                    }
                ),
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(validate_report, "validate_markdown", return_value=[]),
                mock.patch.object(
                    validate_report,
                    "validate_report_against_ledger",
                    return_value=[],
                ),
                mock.patch.object(
                    validate_report,
                    "validate_rewild_receipt",
                    return_value=[],
                ),
                mock.patch(
                    "content_gate.validate_content_receipt",
                    return_value=[],
                ),
                mock.patch.object(
                    validate_report,
                    "validate_source_fidelity_receipt_online",
                    return_value=["Live source changed."],
                ) as online,
                redirect_stderr(stderr),
            ):
                code = validate_report.main(
                    [
                        str(report),
                        "--ledger",
                        str(ledger),
                        "--rewild-receipt",
                        str(rewild),
                        "--content-receipt",
                        str(content),
                        "--source-fidelity-receipt",
                        str(source),
                    ]
                )

            self.assertEqual(1, code)
            self.assertIn("Live source changed", stderr.getvalue())
            online.assert_called_once_with(ledger, {"status": "passed"})

    def test_delivery_rejects_source_receipt_swap_before_live_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            report = work / "report.md"
            ledger = work / "ledger.json"
            rewild = work / "rewild.json"
            content = work / "content.json"
            source = work / "source.json"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            ledger.write_text("{}", encoding="utf-8")
            rewild.write_text("{}", encoding="utf-8")
            source.write_text('{"reviewed": true}', encoding="utf-8")
            content.write_text(
                json.dumps(
                    {
                        "source_fidelity_receipt_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest()
                    }
                ),
                encoding="utf-8",
            )
            stderr = io.StringIO()

            def swap_source(*_args, **_kwargs):
                source.write_text('{"forged": true}', encoding="utf-8")
                return []

            with (
                mock.patch.object(validate_report, "validate_markdown", return_value=[]),
                mock.patch.object(
                    validate_report,
                    "validate_report_against_ledger",
                    return_value=[],
                ),
                mock.patch.object(
                    validate_report,
                    "validate_rewild_receipt",
                    return_value=[],
                ),
                mock.patch(
                    "content_gate.validate_content_receipt",
                    side_effect=swap_source,
                ),
                mock.patch.object(
                    validate_report,
                    "validate_source_fidelity_receipt_online",
                ) as online,
                redirect_stderr(stderr),
            ):
                code = validate_report.main(
                    [
                        str(report),
                        "--ledger",
                        str(ledger),
                        "--rewild-receipt",
                        str(rewild),
                        "--content-receipt",
                        str(content),
                        "--source-fidelity-receipt",
                        str(source),
                    ]
                )

            self.assertEqual(1, code)
            self.assertIn(
                "changed after content review",
                stderr.getvalue(),
            )
            online.assert_not_called()

    def test_pdf_validation_counts_clickable_links(self):
        class Annotation:
            def get_object(self):
                return {"/Subtype": "/Link", "/A": {"/URI": "https://example.com"}}

        class Page:
            mediabox = SimpleNamespace(width=595.28, height=841.89)

            def extract_text(self):
                return "enough report text"

            def get(self, key, default):
                return [Annotation()] if key == "/Annots" else default

        fake_pypdf = SimpleNamespace(PdfReader=lambda path: SimpleNamespace(
            pages=[Page()],
            metadata={"/Title": "Report", "/Author": "Alexandria"},
            root_object={
                "/Lang": "en",
                "/MarkInfo": {"/Marked": True},
                "/StructTreeRoot": {},
                "/Outlines": {},
            },
        ))
        with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
            errors = validate_report.validate_pdf(
                Path("report.pdf"), min_pages=1, min_text_chars=5, min_links=2
            )
        self.assertTrue(any("clickable links" in error for error in errors))

    def test_pdf_validation_rejects_missing_production_semantics(self):
        class Page:
            mediabox = SimpleNamespace(width=600, height=800)

            def extract_text(self):
                return "report text"

            def get(self, key, default):
                return default

        fake_pypdf = SimpleNamespace(PdfReader=lambda path: SimpleNamespace(
            pages=[Page()],
            metadata={},
            root_object={},
        ))
        with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
            errors = validate_report.validate_pdf(
                Path("report.pdf"),
                expected_lang="en",
            )
        joined = " ".join(errors)
        for phrase in ("title metadata", "author metadata", "tagged", "language", "A4", "bookmarks"):
            self.assertIn(phrase, joined)

    def test_pdf_validation_resolves_indirect_mark_info(self):
        class Indirect:
            def get_object(self):
                return {"/Marked": True}

        class Page:
            mediabox = SimpleNamespace(width=595.28, height=841.89)

            def extract_text(self):
                return "report text"

            def get(self, key, default):
                return default

        fake_pypdf = SimpleNamespace(PdfReader=lambda path: SimpleNamespace(
            pages=[Page()],
            metadata={"/Title": "Title", "/Author": "Author"},
            root_object={
                "/MarkInfo": Indirect(),
                "/StructTreeRoot": {},
                "/Outlines": {},
                "/Lang": "en",
            },
        ))
        with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
            errors = validate_report.validate_pdf(
                Path("report.pdf"),
                expected_lang="en",
            )
        self.assertFalse(any("could not be reopened" in error for error in errors), errors)

    def test_report_ledger_check_requires_known_urls_and_claim_locations(self):
        report = GOOD_REPORT
        ledger = {
            "sources": [{"source_id": "S1", "url": "https://example.org/other"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "report_excerpts": [
                        "This exact passage does not appear anywhere in the report body."
                    ],
                },
                {
                    "claim_id": "C2",
                    "include_in_report": False,
                    "report_excerpts": [],
                },
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(any("not present in the ledger" in error for error in errors))
        self.assertTrue(any("cannot be located" in error for error in errors))

    def test_markdown_url_parser_keeps_balanced_parentheses(self):
        url = "https://en.wikipedia.org/wiki/Function_(mathematics)"
        report = f"# Title\n\n## Body\n\n[Source]({url})\n\n## Sources\n\n- [Source]({url})"
        self.assertEqual([url, url], validate_report.extract_markdown_urls(report))

    def test_markdown_url_parser_handles_angles_titles_and_code(self):
        text = """[Angle](<https://example.com/a(b)>)
[Title](https://example.com/a "A title")
`[Inline](https://example.com/inline)`
<!-- [Comment](https://example.com/comment) -->
![Image](https://example.com/image.png)

```text
[Fake](https://example.com/fake)
```
"""
        self.assertEqual(
            ["https://example.com/a(b)", "https://example.com/a"],
            validate_report.extract_markdown_urls(text),
        )
        self.assertEqual([], validate_report.find_raw_urls(text))

    def test_reference_style_link_definitions_are_not_raw_urls(self):
        text = """A [reference-style link][source].

[source]: https://example.com/research "Source title"
"""
        self.assertEqual([], validate_report.find_raw_urls(text))

    def test_fenced_sources_heading_does_not_satisfy_structure(self):
        report = """# Title

## Analysis

Substantive claim with an inline [citation](https://example.com).

```md
## Sources
- [Fake](https://example.com)
```
"""
        errors = validate_report.validate_markdown(
            report, min_sources=1, min_sections=2
        )
        self.assertTrue(any("final H2 Sources" in error for error in errors))
        self.assertTrue(any("H2 sections" in error for error in errors))

        for fenced in (
            " ```md\n## Sources\n- [Fake](https://example.com)\n ```",
            "````md\n~~~\n## Sources\n- [Fake](https://example.com)\n````",
        ):
            report = f"# Title\n\n## Analysis\n\nBody.\n\n{fenced}\n"
            errors = validate_report.validate_markdown(
                report, min_sources=1, min_sections=2
            )
            self.assertTrue(any("final H2 Sources" in error for error in errors))

        no_title = """```md
# Fake title
```

## Analysis
Body.

## Sources
- [Source](https://example.com)
"""
        errors = validate_report.validate_markdown(
            no_title, min_sources=1, min_sections=2
        )
        self.assertIn("Report needs one H1 title.", errors)

    def test_claim_source_must_be_cited_in_mapped_paragraph(self):
        report = """# Title

## Analysis

This consequential claim is long enough to map but has no nearby citation.

## Sources

- [Source](https://example.com/evidence)
"""
        ledger = {
            "sources": [
                {
                    "source_id": "S1",
                    "url": "https://example.com/evidence",
                }
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "report_excerpts": [
                        "This consequential claim is long enough to map but has no nearby citation."
                    ],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(any("nearby citation" in error for error in errors))

    def test_analysis_must_cite_transitive_foundation(self):
        report = """# Title

## Analysis

This analytical conclusion is mapped but does not cite its foundation.

## Sources

- [Unrelated](https://example.com/unrelated)
"""
        ledger = {
            "sources": [
                {"source_id": "S1", "url": "https://example.com/foundation"},
                {"source_id": "S2", "url": "https://example.com/unrelated"},
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": [],
                    "supports": ["C2"],
                    "report_excerpts": [
                        "This analytical conclusion is mapped but does not cite its foundation."
                    ],
                },
                {
                    "claim_id": "C2",
                    "include_in_report": False,
                    "source_ids": ["S1"],
                    "supports": [],
                    "report_excerpts": [],
                },
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(any("nearby citation" in error for error in errors))
        self.assertTrue(any("foundation" in error and "Sources" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
