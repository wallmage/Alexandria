"""W18 R/T: keep prose after Sources; local date from fetched_at."""

import json
import unittest
from datetime import datetime
from pathlib import Path

from scripts import alx
from tests.test_alx import AlxTestCase

STAMP = "2026-09-16T19:14:04Z"
AFTER_LIST = "Kept after the Sources list."
BETWEEN = "Note between the Sources heading and the list."


def _local_date(stamp):
    return (
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        .astimezone()
        .date()
        .isoformat()
    )


class SourcesTrailingProseTests(AlxTestCase):
    def test_paragraph_after_the_sources_list_survives_check_fix(self):
        self.bootstrap()
        path = self.dir / "report.md"
        path.write_text(
            path.read_text(encoding="utf-8").rstrip("\n") + f"\n\n{AFTER_LIST}\n",
            encoding="utf-8",
        )
        self.run_in("check", "--fix")
        report = path.read_text(encoding="utf-8")
        self.assertIn(AFTER_LIST, report)
        self.assertGreater(report.index(AFTER_LIST), report.index("## Sources"))

    def _primary_sources_block(self, list_line):
        self.bootstrap()
        ledger = self.ledger()
        ledger["sources"][0]["title"] = "Primary"
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        url = ledger["sources"][0]["url"]
        path = self.dir / "report.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text[: text.index("## Sources")]
            + f"## Sources\n\n{BETWEEN}\n\n{list_line.format(url=url)}\n",
            encoding="utf-8",
        )
        self.run_in("check", "--fix")
        return path.read_text(encoding="utf-8")

    def test_paragraph_between_heading_and_list_survives_check_fix(self):
        report = self._primary_sources_block("- [Primary]({url})")
        self.assertIn(BETWEEN, report)
        self.assertEqual(1, report.count("- [Primary]"))
        self.assertGreater(report.index(BETWEEN), report.index("- [Primary]"))

    def test_star_bullet_between_heading_does_not_duplicate_the_list(self):
        report = self._primary_sources_block("* [Primary]({url})")
        self.assertIn(BETWEEN, report)
        self.assertEqual(1, report.count("- [Primary]"))
        self.assertNotIn("* [Primary]", report)

    def test_url_less_list_lines_kept_and_rewrite_printed(self):
        after = "- 注：条目之后保留。"
        between = "- 标题与条目之间的列表项"
        self.bootstrap()
        ledger = self.ledger()
        ledger["sources"][0]["title"] = "Primary"
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        url = ledger["sources"][0]["url"]
        path = self.dir / "report.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text[: text.index("## Sources")]
            + f"## Sources\n\n{between}\n\n- [Primary]({url})\n\n{after}\n",
            encoding="utf-8",
        )
        before = path.read_text(encoding="utf-8")
        n = len(alx._cited_sources(self.ledger(), before))
        code, out = self.run_in("check", "--fix")
        self.assertEqual(0, code, out)
        report = path.read_text(encoding="utf-8")
        self.assertIn(after, report)
        self.assertIn(between, report)
        self.assertEqual(1, report.count("- [Primary]"))
        self.assertGreater(report.index(after), report.index("- [Primary]"))
        self.assertGreater(report.index(between), report.index("- [Primary]"))
        self.assertIn(f"sources section rewritten: {n} entries, 2 lines kept", out)

    def test_no_heading_appends_heading_and_list(self):
        self.bootstrap()
        path = self.dir / "report.md"
        text = path.read_text(encoding="utf-8")
        body = text[: text.index("## Sources")].rstrip("\n") + "\n"
        path.write_text(body, encoding="utf-8")
        self.run_in("check", "--fix")
        report = path.read_text(encoding="utf-8")
        self.assertTrue(report.startswith(body.rstrip("\n")))
        self.assertIn("## Sources\n\n- [", report)
        self.assertGreater(report.index("## Sources"), report.index("## Findings"))
        url = self.ledger()["sources"][0]["url"]
        self.assertIn(f"]({url})", report[report.index("## Sources") :])


class FetchedAtLocalDateTests(AlxTestCase):
    def test_check_fix_uses_local_date_of_fetched_at_not_utc_prefix(self):
        self.bootstrap()
        expected = _local_date(STAMP)
        utc_prefix = STAMP[:10]
        for source_id in ("S1", "S2"):
            meta_path = Path(self.dir / "sources" / f"{source_id}.meta.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["fetched_at"] = STAMP
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.run_in("check", "--fix")
        ledger = self.ledger()
        accessed = {source["source_id"]: source["accessed"] for source in ledger["sources"]}
        self.assertEqual(expected, accessed["S1"])
        self.assertEqual(expected, accessed["S2"])
        verified = {claim["claim_id"]: claim["verified_at"] for claim in ledger["claims"]}
        self.assertEqual(expected, verified["C1"])
        self.assertEqual(expected, verified["C2"])
        if expected != utc_prefix:
            self.assertNotEqual(utc_prefix, accessed["S1"])
            self.assertNotEqual(utc_prefix, verified["C1"])


if __name__ == "__main__":
    unittest.main()
