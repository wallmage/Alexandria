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
        self.assertRegex(text, r"### `[^`]+` — [FAW]\b")

    def test_doc_severities_match_the_r28_table(self):
        """R28: F only for the fabrication/integrity list; every other family W."""
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        letters = {
            name: letter
            for name, letter in re.findall(r"### `([^`]+)`[^\n]*? — ([FW])(?:/[FW])?\b", text)
        }
        hard = {
            "runtime/missing", "ledger/quantity", "ledger/status", "ledger/direction",
            "ledger/derived", "ledger/claim-input", "ledger/schema", "ledger/reference",
            "integrity/control-chars", "integrity/replacement-char", "integrity/encoding",
            "integrity/quotation-lost", "binding/link-not-in-ledger",
            "binding/leftover-prose", "fidelity/mismatch", "fidelity/cache-missing",
            "fidelity/cache-detached", "fidelity/rewild",
        }
        for name, letter in sorted(letters.items()):
            with self.subTest(family=name):
                self.assertEqual("F" if name in hard else "W", letter)
        for downgraded in (
            "ledger/key-claim", "ledger/person", "ledger/portfolio", "integrity/length",
            "binding/claim-paragraph", "fidelity/context-changed", "fidelity/semantic",
            "rewild/region", "review/content-missing", "content/score", "tooling/receipt",
        ):
            with self.subTest(family=downgraded):
                self.assertEqual("W", letters[downgraded])
        self.assertIn("never blocks `issue`", text)
        self.assertNotIn("Class A only via", text)
        self.assertNotIn("### `ledger/harm`", text)

    def test_module_families_appear_when_exported(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        missing = [fam for fam in sorted(_families_from_modules()) if fam not in text]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
