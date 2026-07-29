import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.render_binding import expected_render_binding

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
    def test_typed_identity_metadata_is_not_an_ungated_prose_channel(self):
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        safe_report = """# Report

> Client: Acme Research
> Prepared by: Alice Smith

## Analysis

## Sources

- [Source](https://example.com/a)
"""
        self.assertEqual(
            [],
            validate_report.validate_report_against_ledger(
                safe_report,
                ledger,
            ),
        )

        for field, value in (
            ("Client", "Alice Stole Funds"),
            ("Prepared by", "Alice Killed Bob"),
            ("Client", "Acme Failed Audit"),
        ):
            with self.subTest(field=field, value=value):
                report = (
                    "# Report\n\n"
                    f"> {field}: {value}\n\n"
                    "## Analysis\n\n"
                    "## Sources\n\n"
                    "- [Source](https://example.com/a)\n"
                )
                errors = validate_report.validate_report_against_ledger(
                    report,
                    ledger,
                )
                self.assertTrue(
                    any(
                        value in error
                        and "maps to no ledger claim" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_visible_assertions_cannot_bypass_ledger_validation_by_block_style(self):
        cases = {
            "heading": "### Revenue increased by 50 percent.",
            "table": (
                "| Metric | Result |\n"
                "| --- | --- |\n"
                "| Revenue | Increased by 50 percent. |"
            ),
            "blockquote": "> Revenue increased by 50 percent.",
            "callout": "> [!METRIC]\n> Revenue increased by 50 percent.",
            "cover standfirst": "> Revenue increased by 50 percent.",
            "question": "Did revenue increase by 50 percent?",
            "transition prefix": (
                "This section examines why revenue increased by 50 percent."
            ),
        }
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        for name, assertion in cases.items():
            with self.subTest(block_style=name):
                report = (
                    "# Report\n\n"
                    f"{assertion}\n\n"
                    "## Analysis\n\n"
                    "Context only.\n\n"
                    "## Sources\n\n"
                    "- [Source](https://example.com/a)\n"
                )
                errors = validate_report.validate_report_against_ledger(
                    report,
                    ledger,
                )
                self.assertTrue(
                    any(
                        "maps to no ledger claim" in error
                        and (
                            "revenue" in error.lower()
                            or "increased" in error.lower()
                        )
                        for error in errors
                    ),
                    errors,
                )

    def test_duplicate_sources_heading_does_not_hide_later_visible_assertion(self):
        report = """# Report

## Sources

- [Early source](https://example.com/a)

## Analysis

Revenue increased by 50 percent.

## Sources

- [Final source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("maps to no ledger claim" in error for error in errors),
            errors,
        )

    def test_terminal_sources_allows_only_bibliography_entries(self):
        report = """# Report

## Analysis

Supported analysis.

## Sources

- [Source](https://example.com/a)

### Hidden conclusion

Acme committed criminal fraud.
"""
        structure_errors = validate_report.validate_markdown(report)
        self.assertTrue(
            any("bibliography" in error.lower() for error in structure_errors),
            structure_errors,
        )

        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        ledger_errors = validate_report.validate_report_against_ledger(
            report,
            ledger,
        )
        self.assertTrue(
            any(
                "criminal fraud" in error.lower()
                and "maps to no ledger claim" in error
                for error in ledger_errors
            ),
            ledger_errors,
        )

    def test_short_factual_heading_must_map_to_a_ledger_claim(self):
        report = """# Report

## Analysis

### Acme committed criminal fraud

## Sources

- [Source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "criminal fraud" in error.lower()
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_each_table_row_requires_its_own_claim_mapping(self):
        supported = "Acme revenue increased by 10 percent."
        report = f"""# Report

## Analysis

| Finding |
| --- |
| {supported} |
| Acme committed criminal fraud. |

## Sources

- [Source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": supported,
                    "kind": "fact",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "extract_or_location": supported,
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": supported,
                        }
                    ],
                    "report_excerpts": [supported],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "criminal fraud" in error.lower()
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_factual_table_header_cannot_pose_as_a_column_label(self):
        report = """# Report

## Analysis

| Acme committed criminal fraud |
| --- |

## Sources

- [Source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "criminal fraud" in error.lower()
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_bibliography_link_label_cannot_carry_an_unsupported_claim(self):
        report = """# Report

## Analysis

Context only.

## Sources

- [Acme committed criminal fraud](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "criminal fraud" in error.lower()
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_present_tense_short_heading_must_map_to_a_claim(self):
        report = """# Report

## Analysis

### Beta launches Nova

## Sources

- [Normal source title](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "Beta launches Nova" in error
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_irregular_verb_assertions_in_headings_and_source_labels_must_map(self):
        assertions = (
            "Beta won the contract",
            "Beta led the market",
            "Beta sold Nova",
        )
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        for assertion in assertions:
            for location, rendered in (
                ("heading", f"### {assertion}"),
                (
                    "source label",
                    f"- [{assertion}](https://example.com/a)",
                ),
            ):
                with self.subTest(assertion=assertion, location=location):
                    report = (
                        "# Report\n\n"
                        "## Analysis\n\n"
                        f"{rendered if location == 'heading' else 'Context only.'}\n\n"
                        "## Sources\n\n"
                        f"{rendered if location == 'source label' else '- [Source](https://example.com/a)'}\n"
                    )
                    errors = validate_report.validate_report_against_ledger(
                        report,
                        ledger,
                    )
                    self.assertTrue(
                        any(
                            assertion in error
                            and "maps to no ledger claim" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_structural_suffix_cannot_hide_an_assertion(self):
        assertions = (
            "Acme failed audit",
            "Acme falsified audit",
            "Beta lost market audit",
        )
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        for assertion in assertions:
            for location, rendered in (
                ("heading", f"### {assertion}"),
                (
                    "source label",
                    f"- [{assertion}](https://example.com/a)",
                ),
            ):
                with self.subTest(assertion=assertion, location=location):
                    report = (
                        "# Report\n\n"
                        "## Analysis\n\n"
                        f"{rendered if location == 'heading' else ''}\n\n"
                        "## Sources\n\n"
                        f"{rendered if location == 'source label' else '- [Source](https://example.com/a)'}\n"
                    )
                    errors = validate_report.validate_report_against_ledger(
                        report,
                        ledger,
                    )
                    self.assertTrue(
                        any(
                            assertion in error
                            and "maps to no ledger claim" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_exact_ledger_source_title_remains_a_valid_source_label(self):
        report = """# Report

## Analysis

Context only.

## Sources

- [Beta won the contract](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {
                    "source_id": "S1",
                    "url": "https://example.com/a",
                    "title": "Beta won the contract",
                }
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertFalse(
            any("Beta won the contract" in error for error in errors),
            errors,
        )

    def test_mapped_table_cell_does_not_cover_unrelated_sibling_cell(self):
        supported = "Alpha revenue increased."
        report = f"""# Report

## Analysis

| Supported finding | Unrelated finding |
| --- | --- |
| {supported} [Source](https://example.com/a) | Beta launches Nova. |

## Sources

- [Normal source title](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": supported,
                    "kind": "fact",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "extract_or_location": supported,
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": supported,
                        }
                    ],
                    "report_excerpts": [supported],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "Beta launches Nova" in error
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_mapped_excerpt_does_not_cover_an_appended_assertion_in_same_cell(self):
        supported = "Alpha revenue increased."
        unsupported = "Beta won the contract."
        report = f"""# Report

## Analysis

| Finding |
| --- |
| {supported} {unsupported} |

## Sources

- [Source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": supported,
                    "kind": "fact",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "extract_or_location": supported,
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": supported,
                        }
                    ],
                    "report_excerpts": [supported],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                unsupported in error
                and "maps to no ledger claim" in error
                for error in errors
            ),
            errors,
        )

    def test_sentence_units_do_not_split_decimal_numbers(self):
        supported = "Alpha revenue reached 3.14 percent."
        report = f"""# Report

## Analysis

{supported} [Source](https://example.com/a)

## Sources

- [Source](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": supported,
                    "kind": "fact",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "extract_or_location": supported,
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": supported,
                        }
                    ],
                    "report_excerpts": [supported],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertEqual([], errors)

    def test_cited_qualitative_fact_must_map_to_a_ledger_claim(self):
        report = """# Report

## Finding

The supported figure is 15 incidents.

The vendor filed for bankruptcy and its CEO resigned. [Audit](https://example.com/a)

## Sources

- [Audit](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": "The supported figure is 15 incidents.",
                    "source_ids": ["S1"],
                    "supports": [],
                    "include_in_report": True,
                    "report_excerpts": [
                        "The supported figure is 15 incidents."
                    ],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("maps to no ledger claim" in error for error in errors),
            errors,
        )

    def test_uncited_qualitative_fact_must_map_to_a_ledger_claim(self):
        report = """# Report

## Finding

The supported figure is 15 incidents.

The vendor filed for bankruptcy and its CEO resigned.

## Sources

- [Audit](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": "The supported figure is 15 incidents.",
                    "source_ids": ["S1"],
                    "supports": [],
                    "include_in_report": True,
                    "report_excerpts": [
                        "The supported figure is 15 incidents."
                    ],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("maps to no ledger claim" in error for error in errors),
            errors,
        )

    def test_unmapped_factual_paragraph_cannot_hide_behind_a_known_citation(self):
        report = """# Report

## Finding

The supported figure is 15 incidents.

The later total was 900 incidents, all patched [Record](https://example.com/a).

## Sources

- [Record](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": "The supported figure is 15 incidents.",
                    "source_ids": ["S1"],
                    "supports": [],
                    "include_in_report": True,
                    "report_excerpts": [
                        "The supported figure is 15 incidents."
                    ],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("maps to no ledger claim" in error for error in errors),
            errors,
        )

    def test_named_protected_person_harm_must_map_to_a_reviewed_claim(self):
        report = """# Report

## Finding

The regulator alleged procurement fraud by Alex Doe.

## Sources

- [Record](https://example.com/a)
"""
        ledger = {
            "report_date": "2026-07-29",
            "people": [
                {
                    "person_id": "P1",
                    "name": "Alex Doe",
                    "aliases": ["Doe"],
                    "living_status": "living",
                }
            ],
            "sources": [
                {"source_id": "S1", "url": "https://example.com/a"}
            ],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("Protected-person harm" in error for error in errors),
            errors,
        )

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

    def test_requires_exactly_one_terminal_sources_heading(self):
        report = """# Title

## Sources

- [Early](https://example.com/early)

## Analysis

Visible analysis.

## Sources

- [Final](https://example.com/final)
"""
        errors = validate_report.validate_markdown(
            report,
            min_sources=1,
            min_sections=1,
        )
        self.assertTrue(
            any("exactly one" in error.lower() for error in errors),
            errors,
        )

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

    def test_pdf_validation_rejects_binding_for_a_different_report(self):
        class Page:
            mediabox = SimpleNamespace(width=595.28, height=841.89)

            def extract_text(self):
                return "report text"

            def get(self, key, default):
                return default

        fake_pypdf = SimpleNamespace(PdfReader=lambda path: SimpleNamespace(
            pages=[Page()],
            metadata={
                "/Title": "Title",
                "/Author": "Author",
                "/Keywords": "alexandria-input-v1:" + "0" * 64,
            },
            root_object={
                "/MarkInfo": {"/Marked": True},
                "/StructTreeRoot": {},
                "/Outlines": {},
                "/Lang": "en",
            },
        ))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = []
            for index in range(5):
                artifact = root / f"artifact-{index}"
                artifact.write_text(f"artifact {index}", encoding="utf-8")
                artifacts.append(artifact)
            with mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}):
                errors = validate_report.validate_pdf(
                    Path("report.pdf"),
                    expected_lang="en",
                    artifact_paths=tuple(artifacts),
                )
        self.assertIn("different gated artifacts", " ".join(errors))

    def test_pdf_validation_requires_renderer_issued_output_proof(self):
        class Page:
            mediabox = SimpleNamespace(width=595.28, height=841.89)

            def extract_text(self):
                return "unrelated PDF text"

            def get(self, key, default):
                return default

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "unrelated.pdf"
            pdf.write_bytes(b"not the renderer output")
            artifacts = []
            for index in range(5):
                artifact = root / f"artifact-{index}"
                artifact.write_text(f"artifact {index}", encoding="utf-8")
                artifacts.append(artifact)
            binding = expected_render_binding(*artifacts)
            fake_pypdf = SimpleNamespace(
                PdfReader=lambda path: SimpleNamespace(
                    pages=[Page()],
                    metadata={
                        "/Title": "Title",
                        "/Author": "Author",
                        "/Keywords": binding,
                    },
                    root_object={
                        "/MarkInfo": {"/Marked": True},
                        "/StructTreeRoot": {},
                        "/Outlines": {},
                        "/Lang": "en",
                    },
                )
            )
            with (
                mock.patch.dict("sys.modules", {"pypdf": fake_pypdf}),
                mock.patch.object(
                    validate_report,
                    "_page_quality_errors",
                    return_value=[],
                ),
            ):
                errors = validate_report.validate_pdf(
                    pdf,
                    expected_lang="en",
                    artifact_paths=tuple(artifacts),
                )
        self.assertTrue(
            any("render receipt" in error.lower() for error in errors),
            errors,
        )

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

    def test_mapped_report_unit_cannot_append_unsupported_assertions(self):
        supported = (
            "The independent audit recorded 15 incidents in the first review."
        )
        report = f"""# Title

## Analysis

{supported} The vendor later recorded 900 incidents, all patched.
[Audit](https://example.com/audit)

## Sources

- [Audit](https://example.com/audit)
"""
        ledger = {
            "sources": [
                {"source_id": "S1", "url": "https://example.com/audit"}
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "claim": supported,
                    "kind": "fact",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "extract_or_location": (
                        "The audit records 15 incidents in the first review."
                    ),
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": (
                                "The audit records 15 incidents in the first review."
                            ),
                        }
                    ],
                    "report_excerpts": [supported],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        joined = " ".join(errors)
        self.assertIn("maps to no ledger claim", joined)
        self.assertIn("900 incidents, all patched", joined)

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

    def test_unmapped_decision_language_requires_a_citation_or_claim(self):
        report = """# Title

## Decision

Choose Alpha because it wins on the operating constraints that matter.

## Sources

- [Source](https://example.com/evidence)
"""
        ledger = {
            "sources": [{"source_id": "S1", "url": "https://example.com/evidence"}],
            "claims": [],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("Decision language is not traceable" in error for error in errors),
            errors,
        )

    def test_mapped_decision_language_is_traceable(self):
        sentence = (
            "Choose Alpha because it wins on the operating constraints "
            "that matter."
        )
        report = f"""# Title

## Decision

{sentence} [Evidence](https://example.com/evidence)

## Sources

- [Source](https://example.com/evidence)
"""
        ledger = {
            "sources": [{"source_id": "S1", "url": "https://example.com/evidence"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "report_excerpts": [sentence],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertFalse(
            any("Decision language is not traceable" in error for error in errors),
            errors,
        )

    def test_evidence_of_absence_requires_a_search_record(self):
        sentence = "No independent benchmark was found for the two systems."
        report = f"""# Title

## Evidence limits

{sentence}

## Sources

- [Search index](https://example.com/search)
"""
        ledger = {
            "sources": [{"source_id": "S1", "url": "https://example.com/search"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": [],
                    "supports": [],
                    "report_excerpts": [sentence],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("evidence-of-absence search record" in error for error in errors),
            errors,
        )

        ledger["claims"][0]["evidence_of_absence"] = {
            "queries": ["independent benchmark Claude Code Codex"],
            "expected_locations": [
                "vendor benchmark pages and independent evaluation indexes"
            ],
            "searched_at": "2026-07-28",
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertFalse(
            any("evidence-of-absence search record" in error for error in errors),
            errors,
        )
    def test_decision_language_must_cite_a_source_that_backs_a_claim(self):
        report = """# Title

## Decision

Choose Alpha because it wins on the operating constraints that matter.
[Company home](https://example.com/home)

## Sources

- [Company home](https://example.com/home)
- [Evidence](https://example.com/evidence)
"""
        ledger = {
            "sources": [
                {"source_id": "S1", "url": "https://example.com/evidence"},
                {"source_id": "S2", "url": "https://example.com/home"},
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": False,
                    "source_ids": ["S1"],
                    "supports": [],
                    "report_excerpts": [],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any(
                "Decision language cites no source that backs a ledger claim"
                in error
                for error in errors
            ),
            errors,
        )

        ledger["claims"][0]["source_ids"] = ["S1", "S2"]
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertFalse(
            any("Decision language" in error for error in errors),
            errors,
        )

    def test_softly_worded_absence_claims_are_caught(self):
        for sentence in (
            "No published source measures the per-change cost of either tool.",
            "No public equivalent appears to exist on the rival platform.",
            "None was located in the regulator's public register.",
        ):
            with self.subTest(sentence=sentence):
                report = f"""# Title

## Evidence limits

{sentence}

## Sources

- [Search index](https://example.com/search)
"""
                ledger = {
                    "sources": [
                        {"source_id": "S1", "url": "https://example.com/search"}
                    ],
                    "claims": [
                        {
                            "claim_id": "C1",
                            "include_in_report": True,
                            "source_ids": [],
                            "supports": [],
                            "report_excerpts": [sentence],
                        }
                    ],
                }
                errors = validate_report.validate_report_against_ledger(
                    report, ledger
                )
                self.assertTrue(
                    any(
                        "evidence-of-absence search record" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_absence_search_must_be_inside_the_freshness_window(self):
        sentence = "No independent benchmark was found for the two systems."
        report = f"""# Title

## Evidence limits

{sentence}

## Sources

- [Search index](https://example.com/search)
"""
        ledger = {
            "report_date": "2026-07-28",
            "sources": [{"source_id": "S1", "url": "https://example.com/search"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": [],
                    "supports": [],
                    "report_excerpts": [sentence],
                    "evidence_of_absence": {
                        "queries": ["independent benchmark"],
                        "expected_locations": ["evaluation indexes"],
                        "searched_at": "2019-01-01",
                    },
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertTrue(
            any("rests on a search older than" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
