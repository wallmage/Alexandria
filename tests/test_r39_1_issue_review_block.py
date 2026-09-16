"""R39.1: issue is BLOCKED on an unfinished or blank review."""

import json
from contextlib import ExitStack
from pathlib import Path

from scripts import alx
from tests.test_alx import AlxTestCase

ROOT = Path(__file__).resolve().parents[1]


class R39_1IssueReviewBlockTests(AlxTestCase):
    def helper(self):
        from tests.test_alx import IssueTests

        issue_tests = IssueTests("test_issue_writes_receipts_and_verification_note")
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
            "pad_report",
        ):
            setattr(issue_tests, name, getattr(self, name))
        return issue_tests

    def blocked_line(self, kind, reason):
        fields = (
            "fidelity_checks, findings"
            if kind == "rewild"
            else "scores, checks, section_reviews, completion_note"
        )
        path = (self.dir / "reviews" / f"{kind}.json").resolve()
        return (
            f"BLOCKED review/{kind}: reviews/{kind}.json is {reason} — "
            f"edit {path} ({fields}), then alx review finish {kind}, then alx issue"
        )

    def test_draft_review_blocks_issue(self):
        helper = self.helper()
        helper.prepared()
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["status"] = "draft"
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        state = self.state()
        state["reviews"]["content"]["finished"] = False
        (self.dir / ".alx" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        marker = {"schema_version": 1, "marker": "untouched"}
        (self.dir / "receipts" / "issue.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn(alx.BLOCKED_HEADER, out)
        self.assertIn(self.blocked_line("content", "not finished"), out)
        self.assertEqual(
            marker,
            json.loads((self.dir / "receipts" / "issue.json").read_text(encoding="utf-8")),
        )

    def test_blank_finished_review_blocks_issue(self):
        helper = self.helper()
        helper.prepared()
        ws = alx.Workspace(self.dir)
        skeleton = alx._note_skeleton(ws, self.state(), "content", self.ledger())
        (self.dir / "reviews" / "content.json").write_text(
            json.dumps(skeleton, ensure_ascii=False), encoding="utf-8"
        )
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        self.assertTrue(self.state()["reviews"]["content"]["finished"])
        self.assertTrue(
            alx._is_blank_review_note(
                json.loads((self.dir / "reviews" / "content.json").read_text(encoding="utf-8")),
                "content",
            )
        )
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(1, code, out)
        self.assertIn(alx.BLOCKED_HEADER, out)
        self.assertIn(self.blocked_line("content", "empty"), out)
        self.assertFalse((self.dir / "receipts" / "issue.json").exists())

    def test_one_score_filled_and_finished_issues(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.pad_report()
        self.run_in("snapshot")
        self.run_in("review", "start", "content")
        self.run_in("review", "start", "rewild")
        content = self.dir / "reviews" / "content.json"
        note = json.loads(content.read_text(encoding="utf-8"))
        note["scores"]["question_answered"]["score"] = 5
        content.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        rewild = self.dir / "reviews" / "rewild.json"
        rnote = json.loads(rewild.read_text(encoding="utf-8"))
        first = next(iter(rnote["fidelity_checks"]))
        rnote["fidelity_checks"][first] = True
        rewild.write_text(json.dumps(rnote, ensure_ascii=False), encoding="utf-8")
        self.run_in("review", "finish", "content")
        self.run_in("review", "finish", "rewild")
        helper = self.helper()
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        self.assertIn("receipts written:", out)
        self.assertTrue((self.dir / "receipts" / "issue.json").exists())

    def test_docs_name_the_r39_1_block(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        errors = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        self.assertIn(
            "issue refuses only while a review is unfinished or empty",
            skill,
        )
        self.assertIn(
            "BLOCKED review/<kind>: reviews/<kind>.json is <not finished|empty>",
            errors,
        )
        self.assertIn("### `review/unfinished` — B", errors)
