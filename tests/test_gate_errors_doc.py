"""gate-errors.md documents every family the gate modules actually emit.

Spec and legacy spellings live in the doc's Aliases table; only names a module
exports in FAMILIES are required to have their own section.
"""

from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAMILY_MODULES = (
    "scripts.validate_ledger",
    "scripts.source_fidelity",
    "scripts.rewild_gate",
    "scripts.content_gate",
    "scripts.validate_report",
    "scripts.gate_severity",
    "scripts.md_to_pdf",
    "scripts.render_pdf_pages",
    "scripts.alx",
)


def _families_from_modules() -> set[str]:
    found: set[str] = set()
    for name in FAMILY_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        families = getattr(mod, "FAMILIES", None)
        if families is None:
            continue
        found.update(str(item) for item in families)
    return found


class GateErrorsDocTests(unittest.TestCase):
    def test_doc_exists_and_has_columns(self):
        path = ROOT / "references" / "gate-errors.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        for marker in ("- **rule:**", "- **fix:**", "- **remove:**", "- **example:**"):
            self.assertIn(marker, text)
        self.assertRegex(text, r"### `[^`]+` — [FBW]\b")

    def test_doc_severities_match_the_r33_table(self):
        """R33: F = HARD-drop, B = HARD-refuse, W = WARN."""
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        letters = {
            name: letter
            for name, letter in re.findall(
                r"### `([^`]+)`[^\n]*? — ([FBW])(?:/[FBW])?\b", text
            )
        }
        hard_drop = {
            "ledger/derived", "ledger/claim-input", "ledger/reference",
            "integrity/control-chars", "integrity/replacement-char",
            "integrity/quotation-lost", "binding/link-not-in-ledger",
            "binding/leftover-prose", "fidelity/mismatch", "fidelity/cache-missing",
            "fidelity/cache-detached", "fidelity/rewild",
        }
        hard_refuse = {
            "integrity/encoding",
            "integrity/length",
            "review/unfinished",
        }
        for name, letter in sorted(letters.items()):
            with self.subTest(family=name):
                if name in hard_drop:
                    self.assertEqual("F", letter)
                elif name in hard_refuse:
                    self.assertEqual("B", letter)
                else:
                    self.assertEqual("W", letter)
        for warn_only in (
            "ledger/key-claim", "ledger/person", "ledger/portfolio",
            "binding/claim-paragraph", "fidelity/context-changed",
            "rewild/region", "ledger/status", "ledger/direction", "ledger/schema",
            "rewild/style", "content/score", "tooling/receipt",
        ):
            with self.subTest(family=warn_only):
                self.assertEqual("W", letters[warn_only])
        self.assertIn("HARD-drop", text)
        self.assertIn("HARD-refuse", text)
        self.assertIn("never changes the deliverable", text)
        self.assertIn("=== BLOCKED (fix, then alx issue again) ===", text)
        self.assertIn("no snapshot at `issue`", text)
        self.assertIn("alx snapshot", text)
        self.assertIn("en < 5,000 words", text)
        self.assertIn("zh-CN/zh-HK < 3,333", text)
        self.assertIn("under 500 characters", text)
        self.assertIn("higher|rose|growth", text)
        self.assertIn("first candidate for a better detector", text)
        self.assertIn("never blocks `issue`", text)
        self.assertNotIn("Class A", text)
        self.assertNotIn("alx issue --deliver", text)
        self.assertNotIn("machine-written Verification note", text)
        self.assertNotIn("reviews are optional and their absence is silent", text)
        self.assertNotIn("### `runtime/missing`", text)
        self.assertNotIn("### `ledger/harm`", text)
        # R29: every deleted family keeps its name only under "Removed families".
        for deleted in (
            "content/claim-support", "content/claim-binding",
            "rewild/humanization",
        ):
            with self.subTest(deleted=deleted):
                self.assertNotIn(f"### `{deleted}`", text)
        self.assertIn("alx check --verbose", text)

    def test_module_families_appear_when_exported(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        missing = [fam for fam in sorted(_families_from_modules()) if fam not in text]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
