import unittest
from datetime import date

import scripts.md_to_pdf as md_to_pdf
import scripts.validate_report as validate_report
from scripts.report_contract import (
    LENGTH_POLICIES,
    detect_language,
    localized_date,
    report_length_policy,
)


class ReportContractTests(unittest.TestCase):
    def test_language_detection_has_one_stable_neutral_chinese_result(self):
        self.assertEqual("en", detect_language("A concise English report."))
        self.assertEqual("zh", detect_language("人工智能模型性能分析"))
        self.assertEqual("zh-CN", detect_language("这是关于市场与发展的报告。"))
        self.assertEqual("zh-HK", detect_language("這是關於市場與發展的報告。"))

    def test_length_policy_is_centralized_by_report_language(self):
        self.assertEqual((7500, 15000, "words"), report_length_policy("en"))
        self.assertEqual(
            (5000, 10000, "report-body characters"),
            report_length_policy("zh-CN"),
        )
        self.assertEqual(
            LENGTH_POLICIES["zh-CN"],
            LENGTH_POLICIES["zh-HK"],
        )

    def test_localized_date_does_not_depend_on_process_locale(self):
        day = date(2026, 7, 28)
        self.assertEqual("28 July 2026", localized_date("en", day))
        self.assertEqual("2026年7月28日", localized_date("zh-CN", day))

    def test_package_imports_share_one_validation_module(self):
        self.assertIs(md_to_pdf.validate_markdown, validate_report.validate_markdown)
        self.assertIs(
            md_to_pdf.validate_rewild_receipt,
            validate_report.validate_rewild_receipt,
        )


if __name__ == "__main__":
    unittest.main()
