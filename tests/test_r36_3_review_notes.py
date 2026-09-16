"""R36.3: review notes are self-describing; blank finish is one WARN."""

import json

from scripts import validate_report
from tests.test_alx import AlxTestCase


class R36ReviewNotesTests(AlxTestCase):
    def reviewer(self):
        from tests.test_alx import ReviewTests

        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("root", "dir", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        return reviews

    def test_review_start_and_blank_finish(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        first = out.splitlines()[0]
        note_path = (self.dir / "reviews" / "content.json").resolve()
        self.assertEqual(f"Note to fill: {note_path} (edit in place)", first)
        self.assertIn("Report copy for the blind read:", out)
        self.assertIn("Edit reviews/content.json in place:", out)
        note = json.loads(note_path.read_text(encoding="utf-8"))
        headings = [
            h
            for h, _ in validate_report._h2_sections(
                (self.dir / "report.md").read_text(encoding="utf-8")
            )
        ]
        self.assertEqual(headings, [s["section_heading"] for s in note["section_reviews"]])
        for section in note["section_reviews"]:
            self.assertEqual("keep", section["disposition"])
            for key in (
                "purpose",
                "new_value",
                "evidence_or_reasoning",
                "limitation_or_tradeoff",
                "contribution_to_governing_question",
            ):
                self.assertEqual("", section[key])
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code)
        warn_lines = [ln for ln in out.splitlines() if ln.startswith("WARN review/content:")]
        self.assertEqual(1, len(warn_lines), out)
        self.assertEqual(
            f"WARN review/content: nothing filled yet — edit {note_path} "
            "(scores, checks, section_reviews, completion_note) and run "
            "alx review finish content again",
            warn_lines[0],
        )
        self.assertTrue(self.state()["reviews"]["content"]["finished"])
        code, out = self.run_in("check")
        self.assertIn("nothing filled yet — edit", out)
        code, out = self.run_in("review", "start", "rewild")
        self.assertEqual(
            f"Note to fill: {(self.dir / 'reviews' / 'rewild.json').resolve()} "
            "(edit in place)",
            out.splitlines()[0],
        )

    def test_partially_filled_note_still_lists_fields(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        code, out = self.run_in("review", "start", "content")
        self.assertEqual(0, code, out)
        self.reviewer().fill_note("content")
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["scores"]["writing_clarity"]["score"] = 2
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code)
        self.assertIn("writing_clarity scored 2", out)
        self.assertNotIn("nothing filled yet — edit", out)
