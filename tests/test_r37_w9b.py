"""R37.2 / R37.3d / R37.3e / R37.9 — W9b pins."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts import rewild_gate, source_fidelity


def _style_report_text():
    sentence = (
        "The team reviewed the corridor timetable and recorded what it "
        "found in the working log. "
    )
    return "# Corridor log\n\n> 28 July 2026\n\n## Findings\n\n" + (
        sentence * 700
    ) + "\n\n## Sources\n\n- [Log](https://example.com/log)\n"


def _write_style_review(review, report, source):
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "report_sha256": rewild_gate.file_sha256(report),
                "source_sha256": rewild_gate.file_sha256(source),
                "report_lang": "en",
                "profile": "rewild",
                "fidelity_checks": {
                    "facts_and_figures": True,
                    "attribution_and_uncertainty": True,
                    "direction_and_negation": True,
                    "causality": True,
                },
                "findings": [],
            }
        ),
        encoding="utf-8",
    )


class R37ScriptFoldingTests(unittest.TestCase):
    def test_ts_characters_fold_wei_and_neighbors(self):
        source_fidelity._script_character_maps.cache_clear()
        self.assertEqual(
            source_fidelity._to_simplified("作為確認變"),
            "作为确认变",
        )


class R37ReviewFindingTests(unittest.TestCase):
    def test_unknown_category_and_disposition_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "source.md"
            note = work / "review.json"
            report.write_text("r", encoding="utf-8")
            source.write_text("s", encoding="utf-8")
            note.write_text(
                json.dumps(
                    {
                        "fidelity_checks": {
                            "facts_and_figures": True,
                            "attribution_and_uncertainty": True,
                            "direction_and_negation": True,
                            "causality": True,
                        },
                        "findings": [
                            {
                                "category": "mystery",
                                "finding": "punctuation kept",
                                "disposition": "accepted_limitation",
                                "reason": "quote",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            data, warns = rewild_gate._load_review_note(
                note,
                report_path=report,
                source_path=source,
                report_lang="en",
            )
            self.assertFalse(any("skipped" in warn for warn in warns), warns)
            self.assertEqual("style", data["findings"][0]["category"])
            self.assertEqual("rejected", data["findings"][0]["disposition"])


class R37StyleWaiverTests(unittest.TestCase):
    def test_a_style_finding_suppresses_unresolved_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            report = work / "report.md"
            source = work / "pre-rewild.md"
            review = work / "review.json"
            receipt = work / "receipt.json"
            text = _style_report_text()
            report.write_text(text, encoding="utf-8")
            source.write_text(
                text.replace("The team reviewed", "The team examined", 1),
                encoding="utf-8",
            )
            _write_style_review(review, report, source)
            note = json.loads(review.read_text(encoding="utf-8"))
            note["findings"] = [
                {
                    "category": "style",
                    "finding": "half-width punctuation in quotes",
                    "disposition": "accepted_limitation",
                    "reason": "transcript",
                }
            ]
            review.write_text(
                json.dumps(note, ensure_ascii=False), encoding="utf-8"
            )
            findings = rewild_gate.run_gate(
                report,
                source,
                report_lang="en",
                review_note_path=review,
                receipt_path=receipt,
            )
            self.assertFalse(
                any(
                    "Unresolved style warning" in finding for finding in findings
                ),
                findings,
            )
            self.assertFalse(
                any("skipped" in finding for finding in findings),
                findings,
            )
            check = rewild_gate.run_check(
                report,
                source,
                lang="en",
                review_note_path=review,
            )
            self.assertFalse(
                any(
                    "Unresolved style warning" in item.message for item in check
                ),
                [item.message for item in check],
            )


class R37DocsTests(unittest.TestCase):
    def test_docs_state_post_r37_review_and_folding_rules(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        errors = (root / "references" / "gate-errors.md").read_text(
            encoding="utf-8"
        )
        rewild = (root / "references" / "rewild-gate.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "review finish attests to the current report; run it after the last edit",
            skill,
        )
        self.assertIn(
            "A later edit makes the review stale (check says so)",
            skill,
        )
        self.assertIn(
            "Unknown or missing category is treated as style",
            errors,
        )
        self.assertIn(
            "unknown or missing disposition as rejected",
            errors,
        )
        self.assertIn(
            "Printed only when the rewild note has no style finding",
            errors,
        )
        self.assertIn(
            "Readers accept `claim_ids` or `claims`",
            errors,
        )
        self.assertIn(
            "not in S13 or S1",
            errors,
        )
        self.assertIn(
            "source fidelity: offline — extracts were verified verbatim at claim add; alx issue --live re-reads a sample of cited pages",
            errors,
        )
        self.assertIn("other words are accepted as style", rewild)
        self.assertIn("other words are accepted as rejected", rewild)
        for text in (skill, errors, rewild):
            self.assertNotRegex(text, r"is incomplete|findings\[\d+\] skipped")
