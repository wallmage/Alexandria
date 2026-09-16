"""R36.2: claim-add FAIL prints like find, with a pasteable extract_or_location."""

import json
import unittest

from scripts import source_fidelity
from tests.test_alx import CLAIM_BROKEN, CLAIM_ONE, CLAIM_TWO, AlxTestCase


class ClosestPassageUnitTests(unittest.TestCase):
    def test_closest_passage_returns_cache_window_on_one_character_miss(self):
        cache = "The fleet landed at Leyte on 20 October 1944 after the landings."
        window = source_fidelity.normalize_text(cache.replace("Leyte", "Leyta"))
        self.assertEqual(cache, source_fidelity.closest_passage(cache, window))


class ClaimAddFailPrintTests(AlxTestCase):
    def test_fidelity_miss_prints_three_lines_and_paste_summary(self):
        self.init()
        self.fetch("https://example.org/study", "https://registry.example.net/note")
        batch = self.write_json("claims.json", [CLAIM_ONE, CLAIM_TWO, CLAIM_BROKEN])
        code, out = self.run_in("claim", "add", batch)
        self.assertEqual(1, code, out)
        lines = out.splitlines()
        summary = (
            "3 submitted, 2 accepted, 1 failed: C3 — paste each "
            "extract_or_location line above into a new claims file and alx claim add it"
        )
        self.assertEqual(summary, lines[0])
        fail = (
            "C3 FAIL [fidelity/mismatch] source_evidence[1] (S1) not found verbatim "
            "(searched: The archive released 9,999 documents.…)"
        )
        self.assertIn(fail, lines)
        idx = lines.index(fail)
        loc = lines[idx + 1]
        self.assertTrue(loc.startswith("  S1 extract_or_location: "))
        passage = json.loads(loc.split("  S1 extract_or_location: ", 1)[1])
        self.assertIsInstance(passage, str)
        self.assertTrue(passage)
        self.assertNotIn("Missing:", out)
        transcript = (self.dir / ".alx" / "last-claim-add.txt").read_text(
            encoding="utf-8"
        )
        self.assertTrue(transcript.startswith(summary + "\n"))
        self.assertIn(fail, transcript)

        ok = self.write_json("ok.json", [CLAIM_ONE, CLAIM_TWO])
        code, out = self.run_in("claim", "add", ok)
        self.assertEqual(0, code, out)
        self.assertEqual("2 submitted, 2 accepted, 0 failed", out.splitlines()[0])
