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

from scripts.gate_severity import hard_errors

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
        findings = validate_report.binding_findings(report, ledger)
        self.assertTrue(
            any(f.family == "binding/link-not-in-ledger" for f in findings)
        )
        self.assertTrue(
            any("not present in the ledger" in f.message for f in findings)
        )
        errors = validate_report.validate_report_against_ledger(report, ledger)
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

    def test_binding_findings_accept_normalized_alias_urls(self):
        report = """# Title

> 14 September 2026

Body cites an alias [here](https://EXAMPLE.com/a/?utm_source=x#frag).

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [
                {
                    "source_id": "S1",
                    "url": "https://example.com/a/",
                    "aliases": ["https://EXAMPLE.com/a"],
                }
            ],
            "claims": [],
        }
        findings = validate_report.binding_findings(report, ledger)
        self.assertEqual([], [f.message for f in findings])

    def test_binding_findings_name_nearest_ledger_url_for_unknown_link(self):
        report = """# Title

> 14 September 2026

Unknown [link](https://evil.example/nope).

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
            "claims": [],
        }
        messages = [f.message for f in validate_report.binding_findings(report, ledger)]
        self.assertTrue(any("https://example.com/a" in message for message in messages), messages)

    def test_binding_findings_auto_map_only_when_exactly_one_candidate(self):
        report = """# Title

> 14 September 2026

First mention [one](https://example.com/a).

Second mention also [one](https://example.com/a).

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
            "claims": [
                {
                    "claim_id": "C5",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                }
            ],
        }
        messages = [f.message for f in validate_report.binding_findings(report, ledger)]
        self.assertTrue(any("ambiguous" in message for message in messages), messages)
        self.assertTrue(any("alx claim bind C5:" in message for message in messages), messages)

        ledger["claims"][0]["report_paragraph"] = 1
        messages = [f.message for f in validate_report.binding_findings(report, ledger)]
        self.assertFalse(any("ambiguous" in message for message in messages), messages)

    def test_binding_findings_require_sources_last_and_equal_cited_set(self):
        report = """# Title

> 14 September 2026

Cites [a](https://example.com/a) and [b](https://example.com/b).

## Sources

- [Primary](https://example.com/a)

## After

Leftover.
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"},
                {"source_id": "S2", "url": "https://example.com/b"},
            ],
            "claims": [],
        }
        messages = [f.message for f in validate_report.binding_findings(report, ledger)]
        self.assertTrue(any("last" in message.lower() or "final" in message.lower() for message in messages), messages)

    def test_binding_findings_require_cited_set_when_sources_is_last(self):
        report = """# Title

> 14 September 2026

Cites [a](https://example.com/a) and [b](https://example.com/b).

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"},
                {"source_id": "S2", "url": "https://example.com/b"},
            ],
            "claims": [],
        }
        messages = [f.message for f in validate_report.binding_findings(report, ledger)]
        self.assertTrue(
            any("cited-source" in message or "equal the cited" in message for message in messages),
            messages,
        )

    def test_binding_findings_ignore_in_document_anchors(self):
        report = """# Title

> 14 September 2026

See [below](#outlook) and [mail](mailto:x@example.com).

## Outlook

Body cites [a](https://example.com/a).

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-09-14",
            "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
            "claims": [],
        }
        families = [f.family for f in validate_report.binding_findings(report, ledger)]
        self.assertNotIn("binding/link-not-in-ledger", families)

    def test_integrity_findings_require_date_line_in_immediate_blockquote(self):
        report = """# Title

> A standfirst without a date.

Body.

## Sources

- [Primary](https://example.com/a)
"""
        ledger = {"report_date": "2026-09-14", "brief": {"report_language": "en"}}
        messages = [
            f.message
            for f in validate_report.integrity_findings(
                report, ledger, lang="en"
            )
        ]
        self.assertTrue(any("immediate blockquote" in message for message in messages), messages)
        self.assertTrue(any("14 September 2026" in message for message in messages), messages)

    def test_integrity_findings_count_length_with_thresholds(self):
        ledger = {"report_date": "2026-09-14", "brief": {"report_language": "en"}}
        report = """# Title

> 14 September 2026

Short.

## Sources

- [Primary](https://example.com/a)
"""
        messages = [
            f.message
            for f in validate_report.integrity_findings(
                report, ledger, lang="en"
            )
        ]
        self.assertTrue(any("7500" in message for message in messages), messages)
        self.assertTrue(any("words" in message for message in messages), messages)

    def test_integrity_findings_flag_control_chars(self):
        report = "# Title\n\n> 14 September 2026\n\nBad\x01char.\n\n## Sources\n\n- [A](https://example.com/a)\n"
        ledger = {"report_date": "2026-09-14"}
        families = [
            f.family
            for f in validate_report.integrity_findings(report, ledger, lang="en")
        ]
        self.assertIn("integrity/control-chars", families)

    def test_lang_is_alias_for_expected_lang(self):
        parser = validate_report.build_parser()
        args = parser.parse_args(["report.md", "--lang", "zh-CN"])
        self.assertEqual("zh-CN", args.expected_lang)

    def test_argument_errors_print_full_invocation(self):
        stderr = io.StringIO()
        with (
            redirect_stderr(stderr),
            self.assertRaises(SystemExit),
        ):
            validate_report.main(["report.md", "--not-a-real-flag"])
        text = stderr.getvalue()
        self.assertIn("report.md", text)
        self.assertIn("--not-a-real-flag", text)

    def _bound_receipts(self, work, report, ledger):
        report_hash = hashlib.sha256(report.read_bytes()).hexdigest()
        ledger_hash = hashlib.sha256(ledger.read_bytes()).hexdigest()
        bound = {"report_sha256": report_hash, "ledger_sha256": ledger_hash}
        rewild = work / "rewild.json"
        content = work / "content.json"
        fidelity = work / "fidelity.json"
        for path in (rewild, content, fidelity):
            path.write_text(json.dumps(bound), encoding="utf-8")
        return rewild, content, fidelity

    def test_fast_skips_receipt_replay_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            ledger = work / "ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "S1", "url": "https://example.com/a"},
                            {"source_id": "S2", "url": "https://example.org/b"},
                        ],
                        "claims": [],
                    }
                ),
                encoding="utf-8",
            )
            rewild, content, fidelity = self._bound_receipts(work, report, ledger)
            with (
                mock.patch.object(
                    validate_report, "validate_rewild_receipt"
                ) as rewild_fn,
                mock.patch.object(
                    validate_report,
                    "validate_source_fidelity_receipt_online",
                ) as online,
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
                        str(fidelity),
                        "--fast",
                    ]
                )
        self.assertEqual(0, code)
        rewild_fn.assert_not_called()
        online.assert_not_called()

    def test_fast_accepts_a_ledger_bound_source_fidelity_receipt(self):
        """T1 binds that receipt to the ledger; the report hash lives in issue.json."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            ledger = work / "ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "S1", "url": "https://example.com/a"},
                            {"source_id": "S2", "url": "https://example.org/b"},
                        ],
                        "claims": [],
                    }
                ),
                encoding="utf-8",
            )
            rewild, content, fidelity = self._bound_receipts(work, report, ledger)
            fidelity.write_text(
                json.dumps(
                    {
                        "policy": "weighted-source-evidence-v2",
                        "ledger_sha256": hashlib.sha256(
                            ledger.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with (
                redirect_stderr(stderr),
                mock.patch.object(validate_report, "validate_rewild_receipt"),
                mock.patch.object(
                    validate_report, "validate_source_fidelity_receipt_online"
                ),
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
                        str(fidelity),
                        "--fast",
                    ]
                )
        self.assertEqual(0, code, stderr.getvalue())
        self.assertNotIn("report_sha256", stderr.getvalue())

    def test_fast_rejects_stale_receipt_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            ledger = work / "ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "S1", "url": "https://example.com/a"},
                            {"source_id": "S2", "url": "https://example.org/b"},
                        ],
                        "claims": [],
                    }
                ),
                encoding="utf-8",
            )
            rewild, content, fidelity = self._bound_receipts(work, report, ledger)
            rewild.write_text(
                json.dumps({"report_sha256": "0" * 64, "ledger_sha256": "1" * 64}),
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
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
                        str(fidelity),
                        "--fast",
                    ]
                )
        self.assertEqual(1, code)
        self.assertIn("report_sha256", stderr.getvalue())

    def test_integrity_findings_unknown_lang_does_not_crash(self):
        findings = validate_report.integrity_findings(
            "# Title\n\n> 14 September 2026\n\nBody.\n\n## Sources\n\n- [A](https://example.com/a)\n",
            {"report_date": "2026-09-14"},
            lang="xx",
        )
        self.assertTrue(all(hasattr(item, "family") for item in findings))

    def test_integrity_findings_lists_all_lost_quotes(self):
        snapshot = 'He said "alpha word here" and 「第二段引文内容」.'
        report = "# Title\n\n> 14 September 2026\n\nPlain.\n\n## Sources\n\n- [A](https://example.com/a)\n"
        messages = [
            item.message
            for item in validate_report.integrity_findings(
                report,
                {"report_date": "2026-09-14"},
                snapshot_text=snapshot,
                lang="en",
            )
            if item.family == "integrity/quotation-lost"
        ]
        joined = " ".join(messages)
        self.assertIn("alpha word here", joined)
        self.assertIn("第二段引文内容", joined)

    def test_final_once_reuses_supplied_fidelity_result(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            report.write_text(GOOD_REPORT, encoding="utf-8")
            rewild = work / "rewild.json"
            content = work / "content.json"
            fidelity = work / "fidelity.json"
            ledger = work / "ledger.json"
            result = work / "fidelity-result.json"
            rewild.write_text("{}", encoding="utf-8")
            content.write_text("{}", encoding="utf-8")
            fidelity.write_text("{}", encoding="utf-8")
            ledger.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "S1", "url": "https://example.com/a"},
                            {"source_id": "S2", "url": "https://example.org/b"},
                        ],
                        "claims": [],
                    }
                ),
                encoding="utf-8",
            )
            result.write_text(
                json.dumps({"status": "passed", "mismatches": []}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    validate_report, "validate_rewild_receipt", return_value=[]
                ),
                mock.patch.object(
                    validate_report,
                    "validate_source_fidelity_receipt_online",
                ) as online,
                mock.patch.dict(
                    "sys.modules",
                    {
                        "content_gate": mock.Mock(
                            validate_content_receipt=mock.Mock(return_value=[])
                        )
                    },
                ),
            ):
                validate_report.main(
                    [
                        str(report),
                        "--ledger",
                        str(ledger),
                        "--rewild-receipt",
                        str(rewild),
                        "--content-receipt",
                        str(content),
                        "--source-fidelity-receipt",
                        str(fidelity),
                        "--final-once",
                        str(result),
                    ]
                )
        online.assert_not_called()

    def test_force_is_hidden_and_rejected(self):
        """§7.5: `--force` overwrites output files; this command writes none."""
        self.assertNotIn("--force", validate_report.build_parser().format_help())
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            validate_report.main(["report.md", "--force"])
        self.assertIn("--force is not accepted here", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()


class ParagraphNumberingTests(unittest.TestCase):
    REPORT = """# Title

> Standfirst sentence.
> 14 September 2026

## Executive summary

First prose paragraph cites [one](https://example.com/a).

```
fenced code

with a blank line
```

| column | column |
| --- | --- |

14 September 2026

Second prose paragraph cites [two](https://example.com/b).

## Sources

- [Primary](https://example.com/a)
- [Secondary](https://example.com/b)
"""

    def test_split_body_paragraphs_numbers_body_prose_only(self):
        numbered = validate_report.split_body_paragraphs(self.REPORT)
        self.assertEqual([1, 2], [number for number, _ in numbered])
        self.assertTrue(numbered[0][1].startswith("First prose paragraph"))
        self.assertTrue(numbered[1][1].startswith("Second prose paragraph"))

    def test_binding_candidates_use_the_body_paragraph_numbering(self):
        ledger = {
            "report_date": "2026-09-14",
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"},
                {"source_id": "S2", "url": "https://example.com/b"},
            ],
            "claims": [
                {
                    "claim_id": "C5",
                    "include_in_report": True,
                    "source_ids": ["S1", "S2"],
                }
            ],
        }
        message = next(
            finding.message
            for finding in validate_report.binding_findings(self.REPORT, ledger)
            if finding.family == "binding/claim-paragraph"
        )
        self.assertIn("candidates: 1, 2", message)


DATED_LEDGER = {
    "report_date": "2026-09-14",
    "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
    "claims": [],
}


class FindingClassTests(unittest.TestCase):
    """R28 restatement: these families warn instead of blocking `issue`."""

    def _date_line(self, date_line):
        report = f"# Title\n\n> Standfirst.\n> {date_line}\n\nBody.\n"
        findings = validate_report.integrity_findings(
            report, {"report_date": "2026-09-14"}, lang="en"
        )
        return next(
            finding
            for finding in findings
            if finding.family == "integrity/date-line"
        )

    def test_structure_defects_are_warnings(self):
        findings = validate_report.integrity_findings(
            "Body only.\n", {}, lang=None
        )
        structure = [
            finding for finding in findings
            if finding.family == "integrity/structure"
        ]
        self.assertEqual(2, len(structure))
        self.assertEqual({"warn"}, {finding.severity for finding in structure})
        self.assertEqual([], hard_errors(findings))

    def test_date_line_warns_whether_or_not_fix_can_repair_it(self):
        for date_line in ("14  September 2026", "September 14, 2026"):
            with self.subTest(date_line=date_line):
                finding = self._date_line(date_line)
                self.assertEqual("warn", finding.severity)
                self.assertEqual([], hard_errors([finding]))

    def test_length_outside_both_thresholds_only_warns(self):
        findings = [
            finding
            for finding in validate_report.integrity_findings(
                "# Title\n\n> 14 September 2026\n\nToo short.\n",
                DATED_LEDGER,
                lang="en",
            )
            if finding.family == "integrity/length"
        ]
        self.assertEqual(1, len(findings))
        self.assertEqual("warn", findings[0].severity)
        self.assertEqual([], hard_errors(findings))

    def test_language_mix_flags_an_english_run_in_zh(self):
        report = (
            "# 题目\n\n> 问题\n> 2026年9月14日\n\n"
            "## 正文\n\n"
            "档案公布了 The archive released many documents 这一事实。\n\n"
            "## Sources\n\n"
            "- [x](https://example.org/study)\n"
        )
        mix = [
            item
            for item in validate_report.integrity_findings(
                report, DATED_LEDGER, lang="zh-CN"
            )
            if item.family == "integrity/language-mix"
        ]
        self.assertEqual(1, len(mix))
        self.assertEqual("warn", mix[0].severity)
        self.assertIn("paragraph 1:", mix[0].message)
        self.assertIn("The archive released many documents", mix[0].message)
        self.assertEqual([], hard_errors(mix))

    def test_language_mix_ignores_a_short_proper_name(self):
        report = (
            "# 题目\n\n> 问题\n> 2026年9月14日\n\n"
            "## 正文\n\n"
            "材料藏于 Hoover Institution 档案室。\n\n"
            "## Sources\n\n"
            "- [x](https://example.org/study)\n"
        )
        mix = [
            item
            for item in validate_report.integrity_findings(
                report, DATED_LEDGER, lang="zh-CN"
            )
            if item.family == "integrity/language-mix"
        ]
        self.assertEqual([], mix)

    def test_language_mix_ignores_four_claim_markers(self):
        report = (
            "# 题目\n\n> 问题\n> 2026年9月14日\n\n"
            "## 正文\n\n"
            "档案公布了这一事实。[C1] [C2] [C3] [C4]\n\n"
            "## Sources\n\n"
            "- [x](https://example.org/study)\n"
        )
        mix = [
            item
            for item in validate_report.integrity_findings(
                report, DATED_LEDGER, lang="zh-CN"
            )
            if item.family == "integrity/language-mix"
        ]
        self.assertEqual([], mix)

    def test_altered_quotation_is_hard_and_a_removed_one_only_warns(self):
        snapshot = 'The memo said "alpha beta gamma delta" in full.'
        header = "# Title\n\n> 14 September 2026\n\n"

        def quotation_findings(body):
            return [
                finding
                for finding in validate_report.integrity_findings(
                    header + body,
                    DATED_LEDGER,
                    snapshot_text=snapshot,
                    lang="en",
                )
                if finding.family == "integrity/quotation-lost"
            ]

        altered = quotation_findings(
            'The memo said "alpha beta gamma omega" in full.\n'
        )
        self.assertEqual(["hard"], [finding.severity for finding in altered])
        self.assertIn("altered", altered[0].message)

        removed = quotation_findings("The memo said nothing at all.\n")
        self.assertEqual(["warn"], [finding.severity for finding in removed])
        self.assertIn("removed", removed[0].message)
        self.assertEqual([], hard_errors(removed))

    def test_sources_section_warns_and_fabrication_stays_hard(self):
        report = "# Title\n\n> 14 September 2026\n\nCites [x](https://other.example/x).\n"
        findings = validate_report.binding_findings(report, DATED_LEDGER)
        by_family = {finding.family: finding.severity for finding in findings}
        self.assertEqual("warn", by_family["binding/sources-section"])
        self.assertEqual("hard", by_family["binding/link-not-in-ledger"])

    def test_claim_paragraph_binding_defects_only_warn(self):
        report = (
            "# Title\n\n> 14 September 2026\n\n"
            "Body citing [a](https://example.com/a).\n\n"
            "## Sources\n\n- [a](https://example.com/a)\n"
        )
        ledger = {
            **DATED_LEDGER,
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "report_paragraph": 99,
                },
                {
                    "claim_id": "C2",
                    "include_in_report": True,
                    "source_ids": ["S404"],
                },
            ],
        }
        findings = validate_report.binding_findings(report, ledger)
        bindings = [
            finding
            for finding in findings
            if finding.family == "binding/claim-paragraph"
        ]
        self.assertEqual(1, len(bindings))
        self.assertEqual({"warn"}, {finding.severity for finding in bindings})
        self.assertEqual([], hard_errors(findings))


class RewildReceiptLedgerBindingTests(unittest.TestCase):
    def test_rewild_receipt_is_not_required_to_record_ledger_sha256(self):
        from scripts.rewild_gate import run_gate

        clean = (
            "# Report\n\n## First finding\n\n"
            + " ".join(f"word{index}" for index in range(4000))
            + ".\n\n## Second finding\n\n"
            + " ".join(f"term{index}" for index in range(3500))
            + ".\n\n## Sources\n\n[Source](https://example.com)"
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            receipt = work / "rewild.json"
            ledger = work / "ledger.json"
            report.write_text(clean, encoding="utf-8")
            source.write_text(clean, encoding="utf-8")
            ledger.write_text(json.dumps({"claims": []}), encoding="utf-8")
            review.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "completed",
                        "report_sha256": hashlib.sha256(
                            report.read_bytes()
                        ).hexdigest(),
                        "source_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "report_lang": "en",
                        "profile": "rewild",
                        "fidelity_checks": {
                            "facts_and_figures": True,
                            "attribution_and_uncertainty": True,
                            "direction_and_negation": True,
                            "causality": True,
                        },
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            gate_errors = run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertEqual([], gate_errors)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertNotIn("ledger_sha256", payload)

            args = SimpleNamespace(
                ledger=str(ledger),
                rewild_receipt=str(receipt),
                content_receipt=None,
                source_fidelity_receipt=None,
            )
            errors = validate_report._receipt_hash_errors(args, report)
            self.assertEqual([], errors)


class AsciiQuotePairingTests(unittest.TestCase):
    """Short ASCII-quoted terms must not desynchronize the span scanner."""

    SNAPSHOT = (
        '每日以"雪耻"开头。他写道："倭寇侮辱,非可以愤激制之"，此后转向强硬。'
    )

    def quotation_findings(self, body):
        return [
            finding
            for finding in validate_report.integrity_findings(
                "# Title\n\n> 14 September 2026\n\n" + body,
                DATED_LEDGER,
                snapshot_text=self.SNAPSHOT,
                lang="zh-CN",
            )
            if finding.family == "integrity/quotation-lost"
        ]

    def test_editing_prose_between_quotes_is_not_a_lost_quotation(self):
        findings = self.quotation_findings(
            '每日以"雪耻"为题。他记道："倭寇侮辱,非可以愤激制之"，从此转向强硬。\n'
        )
        self.assertEqual([], findings)

    def test_altering_the_quoted_text_is_hard(self):
        findings = self.quotation_findings(
            '每日以"雪耻"开头。他写道："倭寇侮辱,非可以愤激胜之"，此后转向强硬。\n'
        )
        self.assertEqual(["hard"], [finding.severity for finding in findings])

    def test_quoted_spans_drops_short_ascii_terms(self):
        self.assertEqual(
            ['"long enough"'],
            validate_report._quoted_spans('a "xy" b "long enough" c'),
        )
