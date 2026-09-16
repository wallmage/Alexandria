"""R37 W9a: one test per ruling this worker owns."""

import json
import unittest
from contextlib import ExitStack

from scripts import alx, validate_ledger, validate_report
from tests.test_alx import AlxTestCase
from tests.test_validate_ledger import valid_quality_ledger


class R37_1ProbeEveryRecordTests(AlxTestCase):
    def test_claim_add_fail_names_the_second_record(self):
        self.init()
        self.fetch("https://example.org/study")
        batch = self.write_json(
            "claims4.json",
            [
                {
                    "claim_id": "C16",
                    "claim": "Two S1 records; the second is not on the page.",
                    "kind": "fact",
                    "source_evidence": [
                        {
                            "source_id": "S1",
                            "extract_or_location": (
                                "The archive released 1,204 documents in March 2026, "
                                "and the registry confirmed the count."
                            ),
                        },
                        {
                            "source_id": "S1",
                            "extract_or_location": (
                                "The archive released 9,999 documents in March 2026, "
                                "and the registry confirmed the count."
                            ),
                        },
                    ],
                }
            ],
        )
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code, out)
        fail = next(
            line
            for line in out.splitlines()
            if line.startswith("C16 FAIL [fidelity/mismatch]")
        )
        self.assertIn("source_evidence[2] (S1)", fail)
        self.assertIn("9,999 documents", fail)
        self.assertNotIn("1,204 documents", fail)
        loc = next(
            line
            for line in out.splitlines()
            if "extract_or_location:" in line
        )
        passage = json.loads(loc.split("extract_or_location: ", 1)[1])
        self.assertIn("1,204 documents", passage)


class R37_3aFinishCopiesCurrentTests(AlxTestCase):
    def test_review_finish_copies_report_and_ledger(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        report = (self.dir / "report.md").read_text(encoding="utf-8")
        (self.dir / "report.md").write_text(
            report + "\n\nA later paragraph.\n", encoding="utf-8"
        )
        code, out = self.run_in("review", "finish", "content")
        self.assertEqual(0, code, out)
        copied = (
            self.dir / ".alx" / "reviews" / "content" / "1" / "report.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            (self.dir / "report.md").read_text(encoding="utf-8"), copied
        )
        self.assertTrue(
            (self.dir / ".alx" / "reviews" / "content" / "1" / "ledger.json").exists()
        )


class R37_3bCheckIssueDoNotStampHashesTests(AlxTestCase):
    def test_check_and_issue_leave_note_hashes(self):
        from tests.test_alx import IssueTests

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
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
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        before = {}
        for kind in ("rewild", "content"):
            before[kind] = json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )["report_sha256"]
        self.run_in("check")
        with ExitStack() as stack:
            helper.stub_gates(stack)
            self.run_in("issue")
        for kind in ("rewild", "content"):
            note = json.loads(
                (self.dir / "reviews" / f"{kind}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(before[kind], note["report_sha256"])


class R37_3cQualityLinesNotIncompleteTests(AlxTestCase):
    def test_check_prints_quality_lines_not_incomplete(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("review", "start", "content")
        from tests.test_alx import ReviewTests

        reviews = ReviewTests("test_start_copies_report_and_binds_hashes")
        for name in ("root", "dir", "run_alx", "run_in", "state", "ledger"):
            setattr(reviews, name, getattr(self, name))
        reviews.fill_note("content")
        path = self.dir / "reviews" / "content.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["scores"]["writing_clarity"]["score"] = 2
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        self.run_in("review", "finish", "content")
        code, out = self.run_in("check")
        self.assertEqual(0, code, out)
        self.assertIn("writing_clarity scored 2", out)
        self.assertNotIn("is incomplete", out)


class R37_3dViaAlxTests(AlxTestCase):
    def test_rewild_accepted_limitation_prints_no_skipped(self):
        self.bootstrap()
        self.run_in("check", "--fix")
        self.run_in("snapshot")
        self.run_in("review", "start", "rewild")
        path = self.dir / "reviews" / "rewild.json"
        note = json.loads(path.read_text(encoding="utf-8"))
        note["fidelity_checks"] = {
            name: True for name in alx.rewild_gate.REQUIRED_FIDELITY_CHECKS
        }
        note["findings"] = [
            {
                "category": "style",
                "finding": "punctuation waiver",
                "disposition": "accepted_limitation",
                "reason": "quoted source punctuation kept",
            }
        ]
        path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        missing = alx._note_completeness(
            alx.Workspace(self.dir), self.state(), self.ledger(), "rewild"
        )
        self.assertFalse(any("skipped" in item for item in missing), missing)
        code, out = self.run_in("review", "finish", "rewild")
        self.assertEqual(0, code, out)
        self.assertNotIn("skipped", out)


class R37_4CoverageClaimsAliasTests(unittest.TestCase):
    def test_claims_alias_and_neither_key_warn(self):
        data = valid_quality_ledger()
        data["coverage"] = [
            {"area": "dates", "status": "supported", "claims": ["C1"]},
            {"area": "faith", "status": "supported"},
        ]
        helper = validate_ledger.notes_shape_findings(data)
        self.assertFalse(
            any("references no supported claim" in item.message for item in helper)
        )
        self.assertTrue(
            any(
                item.message
                == "coverage[1] 'faith': no claim_ids — check reads claim_ids: [\"C1\", …]"
                for item in helper
            ),
            [item.message for item in helper],
        )
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("references no supported claim" in error for error in errors),
            errors,
        )


class R37_5ExcerptNormalizerTests(unittest.TestCase):
    def test_bold_excerpt_matches_report_prose(self):
        report = (
            "# Title\n\n## Body\n\n"
            "**1919年** the event happened.\n\n"
            "## Sources\n"
        )
        ledger = {
            "sources": [],
            "claims": [
                {
                    "claim_id": "C1",
                    "include_in_report": True,
                    "report_excerpts": ["**1919年** the event happened."],
                }
            ],
        }
        errors = validate_report.validate_report_against_ledger(report, ledger)
        self.assertFalse(
            any("cannot be located" in error for error in errors), errors
        )


class R37_6QuantitySurfaceAndSourcesTests(unittest.TestCase):
    def test_quantity_uses_surface_form_and_all_sources(self):
        errors = validate_ledger.evidence_coverage_errors(
            {
                "claim_id": "C3",
                "kind": "fact",
                "claim": "事件发生在1919年10月2日。",
                "extract_or_location": "档案未记该日。",
                "source_ids": ["S13", "S1"],
                "source_evidence": [
                    {"source_id": "S13", "extract_or_location": "档案未记该日。"},
                    {"source_id": "S1", "extract_or_location": "档案未记该日。"},
                ],
            }
        )
        joined = " ".join(errors)
        self.assertIn("'1919年10月2日'", joined)
        self.assertIn("not in S13 or S1", joined)
        self.assertIn("alx find S13 1919年10月2日", joined)
        self.assertNotIn("1919-10-02", joined)


class R37_7FidelityNoteTests(AlxTestCase):
    def test_issue_offline_fidelity_note_reworded(self):
        from tests.test_alx import IssueTests

        helper = IssueTests("test_issue_writes_receipts_and_verification_note")
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
        ):
            setattr(helper, name, getattr(self, name))
        helper.prepared()
        with ExitStack() as stack:
            helper.stub_gates(stack)
            code, out = self.run_in("issue")
        self.assertEqual(0, code, out)
        notes = json.loads(
            (self.dir / "receipts" / "delivery-notes.json").read_text(
                encoding="utf-8"
            )
        )["notes"]
        self.assertTrue(
            any(
                note
                == (
                    "source fidelity: offline — extracts were verified "
                    "verbatim at claim add; alx issue --live re-reads a "
                    "sample of cited pages"
                )
                for note in notes
            ),
            notes,
        )
        self.assertFalse(any("skipped" in note for note in notes), notes)
        self.assertFalse(any("is incomplete" in note for note in notes), notes)


class R37_8CollapseSynthesisAndPriorityTests(unittest.TestCase):
    def test_key_claims_and_priority_collapse(self):
        data = valid_quality_ledger()
        extra = {
            "claim_id": "C2",
            "kind": "fact",
            "importance": "key",
            "include_in_report": True,
            "status": "supported",
            "source_ids": ["S2"],
            "source_evidence": [
                {
                    "source_id": "S2",
                    "extract_or_location": "The independent test reproduces the result.",
                }
            ],
            "supports": [],
            "contradicts": [],
        }
        data["claims"].append(extra)
        data["synthesis"]["central_judgment_claim_ids"] = []
        errors = validate_ledger.validate_references(data)
        syn = [error for error in errors if "central_judgment_claim_ids" in error]
        self.assertEqual(1, len(syn), syn)
        self.assertIn("2 key report claims are not in", syn[0])
        self.assertIn("C1 C2", syn[0])
        findings = [
            item
            for item in validate_ledger.collect_findings(data)
            if item.family == "ledger/synthesis"
            and "central_judgment_claim_ids" in item.message
        ]
        self.assertEqual(
            [
                "put C1 C2 in synthesis.central_judgment_claim_ids in a patch "
                "file, then alx ledger merge <patch>"
            ],
            [item.fix for item in findings],
        )

        data = valid_quality_ledger()
        data["coverage"][0].pop("priority")
        data["synthesis"]["central_judgment_claim_ids"] = ["C1"]
        errors = validate_ledger.validate_references(data)
        self.assertFalse(
            any("high-priority research area" in error for error in errors),
            errors,
        )

        data = valid_quality_ledger()
        data["claims"].append(extra)
        data["synthesis"]["central_judgment_claim_ids"] = ["C1", "C2"]
        errors = validate_ledger.validate_references(data)
        pri = [error for error in errors if "high-priority research area" in error]
        self.assertEqual(1, len(pri), pri)
        self.assertIn("C2", pri[0])
