"""gate-errors.md documents every family the gate modules actually emit.

Spec and legacy spellings live in the doc's Aliases table; only names a module
exports in FAMILIES are required to have their own section.
"""

from __future__ import annotations

import importlib
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

    def test_module_families_appear_when_exported(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        missing = [fam for fam in sorted(_families_from_modules()) if fam not in text]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
