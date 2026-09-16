"""W18 U (binding/claim-marker) and V (init H1 strip)."""

from scripts import validate_report
from tests.test_alx import AlxTestCase

LEDGER = {
    "report_date": "2026-09-14",
    "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
    "claims": [{"claim_id": "C1", "include_in_report": False}],
}


def _report(body):
    return (
        "# Title\n\n"
        "> Standfirst.\n"
        "> 14 September 2026\n\n"
        f"{body}\n\n"
        "## Sources\n\n"
        "- [Primary](https://example.com/a)\n"
    )


def _markers(report, ledger=LEDGER):
    return [
        item
        for item in validate_report.binding_findings(report, ledger)
        if item.family == "binding/claim-marker"
    ]


class ClaimMarkerWarnTests(AlxTestCase):
    def test_unknown_c99_warns_with_paragraph_number(self):
        hits = _markers(_report("The archive released the files [C99]."))
        self.assertEqual(1, len(hits))
        self.assertEqual("warn", hits[0].severity)
        self.assertEqual("", hits[0].fix)
        self.assertIn("paragraph 1", hits[0].message)
        self.assertIn("[C99]", hits[0].message)

    def test_known_c1_is_silent(self):
        self.assertEqual([], _markers(_report("The archive released the files [C1].")))

    def test_markdown_link_text_is_not_a_bare_marker(self):
        self.assertEqual(
            [],
            _markers(_report("See [C99](https://example.com/a) and [C98][ref].")),
        )


class InitHeadingStripTests(AlxTestCase):
    def test_init_keeps_a_single_h1_when_the_brief_starts_with_hash(self):
        subject = self.root / "subject.txt"
        subject.write_text("# HK smoke\n", encoding="utf-8")
        code, out = self.run_alx(
            "init", self.dir, "--lang", "en", "--subject", subject
        )
        self.assertEqual(0, code, out)
        first = (self.dir / "report.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual("# HK smoke", first)
