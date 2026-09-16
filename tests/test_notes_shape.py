"""R35.14: ledger merge warns only where a notes-field consumer exists."""

from tests.test_alx import AlxTestCase

STATUS_WARN = (
    "coverage[0].status 'done' is not one of "
    "unstarted|in_progress|supported|disputed|gap — stored as given; "
    "check tracks coverage only for supported|disputed|gap"
)
TAKEAWAYS_WARN = (
    "synthesis.decisions_or_takeaways[0] is a str; check links it to "
    "claims only through an object with rationale_claim_ids — stored as given"
)


class NotesShapeMergeTests(AlxTestCase):
    def test_merge_warns_coverage_status_and_string_takeaways(self):
        self.bootstrap()
        patch = self.write_json(
            "notes.json",
            {
                "coverage": [{"status": "done"}],
                "synthesis": {
                    "decisions_or_takeaways": ["a takeaway"],
                    "outcome": "y",
                },
                "brief": {"editorial_mode": "x"},
            },
        )
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        self.assertIn(STATUS_WARN, out)
        self.assertIn(TAKEAWAYS_WARN, out)
        content = [
            line
            for line in out.splitlines()
            if line and not line.startswith("elapsed")
        ]
        self.assertFalse(any("editorial_mode" in line for line in content), content)
        self.assertFalse(
            any(line.startswith("WARN") and "outcome" in line for line in content),
            content,
        )
        for line in content:
            if line.startswith("WARN"):
                self.assertNotIn("x", line)
                self.assertNotIn("'y'", line)

    def test_merge_editorial_mode_and_unknown_outcome_print_only_merged(self):
        """W7: made-up editorial_mode and unknown outcome produce no helper line."""
        self.bootstrap()
        patch = self.write_json(
            "silence.json",
            {"brief": {"editorial_mode": "x"}, "synthesis": {"outcome": "y"}},
        )
        code, out = self.run_in("ledger", "merge", patch)
        self.assertEqual(0, code, out)
        content = [
            line
            for line in out.splitlines()
            if line and not line.startswith("elapsed")
        ]
        self.assertEqual(["merged: brief, synthesis"], content)
