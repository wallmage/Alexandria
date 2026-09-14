"""gate-errors.md lists every finding family (spec §6.7/§6.10/§7)."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Spec 6.7 / 6.10 / 7 + plan-pinned names. T2-T4 FAMILIES may add more.
SPEC_FAMILIES = (
    "ledger/quantity",
    "ledger/status",
    "ledger/direction",
    "ledger/schema",
    "ledger/unverified-key-claim",
    "ledger/person",
    "ledger/harm",
    "ledger/excluded-supports",
    "quotation-lost",
    "integrity/quotation-lost",
    "fidelity/quotation-lost",
    "Fidelity/quotations",
    "integrity/control-chars",
    "cache-detached",
    "cache-missing",
    "leftover-prose",
    "fidelity/mismatch",
    "fidelity/short-segment",
    "fidelity/context-changed",
    "binding/link-not-in-ledger",
    "binding/ambiguous",
    "binding/missing",
    "rewild/semantic-fidelity",
    "rewild/regional",
    "rewild/ai-vocabulary",
    "rewild/style",
    "rewild/review-stale",
    "rewild/humanization-none",
    "review/content-missing",
    "review/content-stale",
    "length-below-floor",
    "sources-section",
    "tooling/receipt",
    "tooling/renderer",
    "tooling/rasterizer",
    "fidelity/unreachable",
    "fidelity/undecodable",
    "ledger/coverage",
    "ledger/synthesis",
    "ledger/disputed",
    "ledger/family-label",
    "ledger/derived-assertions",
    "ledger/granularity",
    "ledger/source-ids",
)

FAMILY_MODULES = (
    "scripts.validate_ledger",
    "scripts.source_fidelity",
    "scripts.rewild_gate",
    "scripts.content_gate",
    "scripts.validate_report",
    "scripts.gate_severity",
    "scripts.md_to_pdf",
    "scripts.render_pdf_pages",
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

    def test_spec_families_appear(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        missing = [fam for fam in SPEC_FAMILIES if fam not in text]
        self.assertEqual([], missing)

    def test_module_families_appear_when_exported(self):
        text = (ROOT / "references" / "gate-errors.md").read_text(encoding="utf-8")
        missing = [fam for fam in sorted(_families_from_modules()) if fam not in text]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
