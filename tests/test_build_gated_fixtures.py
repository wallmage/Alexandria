import unittest
from datetime import date

from scripts.report_contract import localized_date
from tests.build_gated_fixtures import CASES, bind_fixture_report_date


class GatedFixtureDateTests(unittest.TestCase):
    def test_each_fixture_uses_the_ledger_day_in_its_visible_date(self):
        for case in CASES:
            with self.subTest(lang=case["lang"]):
                source = "# Fixture\n\n> month only\n\n## Finding\n\nEvidence."
                source = source.replace(
                    "month only",
                    "July 2026" if case["lang"] == "en" else "2026年7月",
                )
                rendered = bind_fixture_report_date(
                    source,
                    case,
                    {"report_date": "2026-07-28"},
                )
                expected = localized_date(case["lang"], date(2026, 7, 28))
                self.assertIn(f"\n> {expected}\n", rendered)
                self.assertNotIn("month only", rendered)

    def test_missing_opening_date_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "visible report date"):
            bind_fixture_report_date(
                "# Fixture\n\n## Finding\n\nEvidence.",
                CASES[0],
                {"report_date": "2026-07-28"},
            )


if __name__ == "__main__":
    unittest.main()
