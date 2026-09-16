"""R38 remedy truth: one test per ruling this worker owns."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import alx, rewild_gate, validate_report
from tests.test_alx import CLAIM_BROKEN, CLAIM_ONE, AlxTestCase

ROOT = Path(__file__).resolve().parents[1]


class R38_0AdoptKeepsProducerTests(AlxTestCase):
    def test_adopt_never_replaces_a_producer_fix(self):
        kept = alx.adopt(
            [
                alx.Finding(
                    family="ledger/https",
                    severity="warn",
                    klass="A",
                    ids=["S5"],
                    message="S5: source.url must be https (actual: http://jds.example.cn/a)",
                    fix="alx source set S5 --url https://jds.example.cn/a",
                    remove="",
                )
            ]
        )[0]
        self.assertEqual(
            "alx source set S5 --url https://jds.example.cn/a", kept.fix
        )
        self.assertNotIn("alx fetch", kept.fix)


class R38_5ReviewStartTests(AlxTestCase):
    def test_review_start_refuses_a_filled_note_and_iter_moves_it_aside(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        from tests.test_alx import ReviewTests

        helper = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("root", "dir", "run_alx", "run_in", "state", "ledger"):
            setattr(helper, name, getattr(self, name))
        helper.fill_note("content")
        original = (self.dir / "reviews" / "content.json").read_text(encoding="utf-8")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        self.assertEqual(
            "reviews/content.json already has content — alx review finish "
            "content attests it; --iter starts a new blind read and moves it "
            "to reviews/content.iter<N>.json",
            out.splitlines()[0],
        )
        self.assertEqual(
            original,
            (self.dir / "reviews" / "content.json").read_text(encoding="utf-8"),
        )
        code, out = self.run_in("review", "start", "content", "--iter")
        self.assertEqual(0, code, out)
        archived = self.dir / "reviews" / "content.iter1.json"
        self.assertTrue(archived.is_file(), out)
        self.assertEqual(original, archived.read_text(encoding="utf-8"))
        note = json.loads((self.dir / "reviews" / "content.json").read_text(encoding="utf-8"))
        self.assertTrue(alx._is_blank_review_note(note, "content"))
        stale = alx.adopt(
            [
                alx.Finding(
                    family="review/content-stale",
                    severity="warn",
                    klass="A",
                    ids=[],
                    message="2 paragraph(s) changed since the content review",
                    fix="",
                    remove="",
                )
            ]
        )[0]
        self.assertEqual(
            "re-read the changed paragraphs, then alx review finish content",
            stale.fix,
        )


class R38_6ClaimAddTests(AlxTestCase):
    def test_paste_summary_only_when_a_paste_line_printed(self):
        self.init()
        self.fetch("https://example.org/study")
        miss = self.write_json("miss.json", [CLAIM_BROKEN])
        code, out = self.run_in("claim", "add", miss)
        self.assertEqual(1, code, out)
        self.assertIn("extract_or_location:", out)
        self.assertIn(
            "paste each extract_or_location line above into a new claims file",
            out.splitlines()[0],
        )
        (self.dir / "sources" / "S1.txt").unlink()
        (self.dir / "sources" / "S1.meta.json").unlink()
        missing = self.write_json("missing.json", [CLAIM_ONE])
        code, out = self.run_in("claim", "add", missing)
        self.assertEqual(1, code, out)
        fail = next(
            line for line in out.splitlines() if line.startswith("C1 FAIL")
        )
        self.assertIn("fidelity/cache-missing", fail)
        self.assertIn("Fix: alx fetch --id S1 --refresh", fail)
        self.assertNotIn("extract_or_location:", out)
        self.assertNotIn("paste each extract_or_location", out.splitlines()[0])


class R38_7ClaimParagraphTests(AlxTestCase):
    def test_out_of_range_bind_uses_candidates_never_paragraph_1(self):
        report = (
            "# Title\n\n> 16 September 2026\n\n"
            "One cites [a](https://example.com/a).\n\n"
            "Two cites [a](https://example.com/a) again.\n\n"
            "## Sources\n\n- [a](https://example.com/a)\n"
        )
        ledger = {
            "report_date": "2026-09-16",
            "sources": [{"source_id": "S1", "url": "https://example.com/a"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "source_ids": ["S1"],
                    "report_paragraph": 99,
                }
            ],
        }
        item = next(
            finding
            for finding in validate_report.binding_findings(report, ledger)
            if finding.family == "binding/claim-paragraph"
        )
        self.assertIn("candidates: 1, 2", item.message)
        self.assertNotIn("out of range", item.message)
        adopted = alx.adopt([item])[0]
        self.assertRegex(adopted.fix, r"^alx claim bind C1:[12]$")
        self.assertNotIn("--paragraph 1", adopted.fix)
        empty = alx.adopt(
            [
                alx.Finding(
                    family="binding/claim-paragraph",
                    severity="warn",
                    klass="A",
                    ids=["C9"],
                    message="Claim C9 report_paragraph 99 is out of range.",
                    fix="",
                    remove="",
                )
            ]
        )[0]
        self.assertNotIn("--paragraph 1", empty.fix)


class R38_8WordingTests(AlxTestCase):
    def test_wording_clock_reminders_and_prefixes(self):
        errors = rewild_gate._hard_checker_errors(
            {"warnings": [{"section": "Region", "message": "token"}], "sections": []},
            "en",
        )
        self.assertTrue(any(line.startswith("Rewild warning:") for line in errors))
        self.assertFalse(any("Hard Rewild" in line for line in errors))
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "rewild")
        blank = alx._blank_review_message(alx.Workspace(self.dir), "rewild")
        self.assertIn("fidelity_checks, findings", blank)
        self.assertNotIn("section_reviews", blank)
        self.assertIn("or report", alx.STALE_FIDELITY_WARN)
        self.set_remaining_seconds(30)
        _code, out = self.run_in("status")
        footer = out.strip().splitlines()[-1]
        self.assertIn("remaining 1 min", footer)
        self.assertNotIn("time is up", footer)
        ledger = self.ledger()
        extra = dict(ledger["claims"][0])
        extra["claim_id"] = "C9"
        extra["supports"] = ["C1"]
        extra["include_in_report"] = False
        ledger["claims"].append(extra)
        (self.dir / "ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
        )
        _code, out = self.run_in("claim", "drop", "C1")
        self.assertIn("WARN [ledger/excluded-supports]", out)
        self.assertNotIn("HARD until re-pointed", out)
        keyword = alx._find_keyword("C1: quantity '1916' is not in the extract")
        passage = alx.remedy(
            "paste-passage",
            source_id="S1",
            file="claims/x.json",
            keyword=keyword,
        )
        self.assertIn("alx find S1 1916", passage)
        self.assertNotIn("KEYWORD", passage)
        reminders = alx._render_reminders(
            [
                alx.Finding(
                    family="ledger/quantity",
                    severity="warn",
                    klass="A",
                    ids=["C1"],
                    message="C1: '53' is missing",
                    fix="alx find S13 53 — paste that window",
                    remove="",
                )
            ]
        )
        self.assertNotIn("=== HARD", reminders)

    def set_remaining_seconds(self, seconds):
        state = self.state()
        now = datetime.now(timezone.utc)
        state["deadline"] = (now + timedelta(seconds=seconds)).isoformat()
        (self.dir / ".alx" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )


class R38_9SourceSetAndLiveTests(AlxTestCase):
    def test_source_set_url_and_live_only_context_changed(self):
        self.bootstrap()
        source = self.ledger()["sources"][0]
        old_url = source["url"]
        cache = (self.dir / "sources" / "S1.txt").read_text(encoding="utf-8")
        https = old_url.replace("https://", "https://www.")
        code, out = self.run_in("source", "set", "S1", "--url", https)
        self.assertEqual(0, code, out)
        self.assertEqual(https, self.ledger()["sources"][0]["url"])
        self.assertEqual(
            cache, (self.dir / "sources" / "S1.txt").read_text(encoding="utf-8")
        )
        unreachable = alx.adopt(
            [
                alx.Finding(
                    family="fidelity/unreachable",
                    severity="warn",
                    klass="A",
                    ids=["S9"],
                    message="S9 UNREACHABLE (timeout)",
                    fix="",
                    remove="",
                )
            ]
        )[0]
        self.assertEqual("alx fetch --id S9 --refresh", unreachable.fix)
        checker = alx.adopt(
            [
                alx.Finding(
                    family="rewild/checker",
                    severity="warn",
                    klass="A",
                    ids=[],
                    message="Rewild checker timed out after 120 seconds",
                    fix="",
                    remove="",
                )
            ]
        )[0]
        self.assertEqual(
            "alx check again — the checker has a 120 s budget", checker.fix
        )
        rendered = alx.adopt(
            [
                alx.Finding(
                    family="tooling/render",
                    severity="warn",
                    klass="A",
                    ids=[],
                    message="academic not rendered: WeasyPrint exploded",
                    fix="academic not rendered: WeasyPrint exploded",
                    remove="",
                )
            ]
        )[0]
        self.assertEqual("academic not rendered: WeasyPrint exploded", rendered.fix)
        self.assertNotEqual("alx issue", rendered.fix)
        from tests.test_alx import FixRoundTests

        helper = FixRoundTests("test_context_changed_is_reported_with_the_two_step_remedy")
        for name in (
            "root",
            "dir",
            "run_alx",
            "run_in",
            "write_json",
            "init",
            "fetch",
            "bootstrap",
            "draft_report",
            "ledger",
            "state",
            "assertEqual",
            "assertIn",
        ):
            setattr(helper, name, getattr(self, name))
        helper.stale_context()
        _code, out = self.run_in("check")
        self.assertNotIn("fidelity/context-changed", out)


class R38_10GateErrorsBannedTokensTests(AlxTestCase):
    def test_gate_errors_fixes_have_no_banned_tokens(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        sections = re.split(r"\n### ", text)
        quality_stale = {
            "review/content-stale",
            "review/rewild",
            "content/score",
            "content/check",
            "content/critical-finding",
            "content/disclosure",
        }
        for section in sections[1:]:
            heading, _, body = section.partition("\n")
            match = re.match(r"`([^`]+)`", heading)
            if not match:
                continue
            family = match.group(1)
            fix_line = next(
                (
                    line
                    for line in body.splitlines()
                    if line.startswith("- **fix:**")
                ),
                "",
            )
            with self.subTest(family=family):
                self.assertNotRegex(
                    fix_line, r"alx source set S\S*\s*$"
                )
                self.assertNotIn("merge coverage.json", fix_line)
                self.assertNotIn("merge people.json", fix_line)
                self.assertNotIn("merge ledger-patch.json", fix_line)
                self.assertNotIn("--paragraph 1", fix_line)
                if family in quality_stale:
                    self.assertNotIn("--iter", fix_line)
