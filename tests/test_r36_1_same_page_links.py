"""R36.1: same-page link variants (www / public-suffix only)."""

import json
import unittest

from scripts import alx, validate_report
from tests.test_alx import AlxTestCase

PATH = "/gn/2026/09-16/10512345.shtml"
COM = f"https://www.chinanews.com{PATH}"
CN = f"https://www.chinanews.com.cn{PATH}"


class SamePageVariantTests(unittest.TestCase):
    def test_same_page_variant_chinanews_path_and_segments(self):
        self.assertTrue(validate_report.same_page_variant(COM, CN))
        self.assertFalse(
            validate_report.same_page_variant(
                "https://www.chinanews.com/other/page.shtml",
                CN,
            )
        )
        self.assertFalse(
            validate_report.same_page_variant(
                "https://www.chinanews.com/foo",
                "https://www.chinanews.com.cn/foo",
            )
        )

    def test_same_page_ledger_source_finds_s1_for_com_variant(self):
        ledger = {"sources": [{"source_id": "S1", "url": CN}]}
        self.assertEqual(
            (CN, "S1"),
            validate_report.same_page_ledger_source(COM, ledger),
        )
        ledger["sources"][0]["url"] = "https://www.chinanews.com.cn/gn/2026/09-16/other.shtml"
        ledger["sources"][0]["aliases"] = [CN]
        self.assertEqual(
            (ledger["sources"][0]["url"], "S1"),
            validate_report.same_page_ledger_source(COM, ledger),
        )

    def test_binding_findings_fix_is_link_not_in_ledger_fix(self):
        findings = [
            item
            for item in validate_report.binding_findings(
                "[x](https://evil.example/nope/path)",
                {"sources": [{"source_id": "S1", "url": CN}]},
            )
            if item.family == "binding/link-not-in-ledger"
        ]
        self.assertTrue(findings)
        self.assertEqual(validate_report.LINK_NOT_IN_LEDGER_FIX, findings[0].fix)


class SamePageLinkFixTests(AlxTestCase):
    FOREIGN = "https://elsewhere.example/other/page"

    def test_check_fix_rewrites_same_page_variant(self):
        self.bootstrap()
        ledger = self.ledger()
        old = ledger["sources"][0]["url"]
        ledger["sources"][0]["url"] = CN
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        report = report.replace(old, CN)
        report = report.replace(
            f"[recorded in the study]({CN})",
            f"[recorded in the study]({COM})",
            1,
        )
        (self.dir / "report.md").write_text(report, encoding="utf-8")

        code, out = self.run_in("check", "--fix")
        self.assertEqual(0, code, out)
        self.assertIn(f"link rewritten: {COM} → {CN} (S1)", out)
        text = (self.dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(CN, text)
        self.assertNotIn(COM, text)
        self.assertNotIn("binding/link-not-in-ledger", out)

        text = text.replace(
            "so the counts above are",
            f"so the counts [above]({self.FOREIGN}) are",
        )
        (self.dir / "report.md").write_text(text, encoding="utf-8")
        ledger = self.ledger()
        items = [
            item
            for item in validate_report.binding_findings(text, ledger)
            if item.family == "binding/link-not-in-ledger"
            and self.FOREIGN in item.message
        ]
        self.assertTrue(items)
        self.assertEqual(validate_report.LINK_NOT_IN_LEDGER_FIX, items[0].fix)
        adopted = alx.adopt(items)
        self.assertTrue(
            any(
                "cite the nearest ledger URL instead" in f"{item.fix} {item.message}"
                for item in adopted
            ),
            adopted[0].fix if adopted else "no adopted findings",
        )
