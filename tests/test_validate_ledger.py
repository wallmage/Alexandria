import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_ledger.py"
SPEC = importlib.util.spec_from_file_location("validate_ledger", MODULE_PATH)
validate_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_ledger)


class LedgerReferenceTests(unittest.TestCase):
    def test_accepts_known_source_and_claim_references(self):
        data = {
            "sources": [{"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "source_ids": ["S1"],
                    "supports": [],
                    "contradicts": [],
                }
            ],
        }
        self.assertEqual([], validate_ledger.validate_references(data))

    def test_rejects_duplicate_and_dangling_ids(self):
        data = {
            "sources": [{"source_id": "S1"}, {"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "source_ids": ["S2"],
                    "supports": ["C9"],
                    "contradicts": [],
                },
                {
                    "claim_id": "C1",
                    "source_ids": [],
                    "supports": [],
                    "contradicts": [],
                },
            ],
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("Duplicate source ID" in error for error in errors))
        self.assertTrue(any("Duplicate claim ID" in error for error in errors))
        self.assertTrue(any("unknown source S2" in error for error in errors))
        self.assertTrue(any("unknown claim C9" in error for error in errors))

        data["coverage"] = [{"area": "current", "claim_ids": ["C8"]}]
        errors = validate_ledger.validate_references(data)
        self.assertTrue(
            any(
                "Coverage current references unknown claim C8" in error
                for error in errors
            )
        )

    def test_cross_reference_check_tolerates_schema_invalid_shapes(self):
        self.assertEqual([], validate_ledger.validate_references([]))
        self.assertEqual(
            [],
            validate_ledger.validate_references(
                {"sources": ["bad"], "claims": [42, None]}
            ),
        )

    def test_rejects_circular_analysis_without_sourced_foundation(self):
        data = {
            "sources": [{"source_id": "S1"}],
            "claims": [
                {
                    "claim_id": "C1",
                    "kind": "analysis",
                    "source_ids": [],
                    "supports": ["C2"],
                    "contradicts": [],
                    "include_in_report": True,
                },
                {
                    "claim_id": "C2",
                    "kind": "analysis",
                    "source_ids": [],
                    "supports": ["C1"],
                    "contradicts": [],
                    "include_in_report": True,
                },
            ],
        }
        errors = validate_ledger.validate_references(data)
        self.assertTrue(any("circular support" in error for error in errors))
        self.assertTrue(any("no sourced foundation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
