import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_readmes_explain_the_name_unlimited_scope_and_pdf_output(self):
        required_phrases = {
            "README.md": (
                "Library of Alexandria",
                "the world's knowledge",
                "anything",
                "no fixed subject limits",
                "professionally crafted",
                "beautiful PDF",
            ),
            "README.zh-CN.md": (
                "亚历山大图书馆",
                "全世界的知识",
                "任何主题",
                "没有固定的选题限制",
                "专业制作",
                "漂亮的 PDF",
            ),
            "README.zh-HK.md": (
                "亞歷山大圖書館",
                "全世界的知識",
                "任何題目",
                "沒有固定的選題限制",
                "專業製作",
                "漂亮的 PDF",
            ),
        }
        for filename, phrases in required_phrases.items():
            readme = (ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                for phrase in phrases:
                    self.assertIn(phrase, readme)

    def test_skill_references_existing_local_files(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        local_paths = set(
            re.findall(r"`((?:references|scripts)/[^` ]+\.(?:md|json|py))`", skill)
        )
        self.assertTrue(local_paths)
        missing = [path for path in sorted(local_paths) if not (ROOT / path).is_file()]
        self.assertEqual([], missing)

    def test_skill_is_progressively_disclosed_and_runtime_neutral(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(skill.split()), 3000)
        for legacy_token in (
            "AskUserQuestion",
            "WebSearch",
            "WebFetch",
            "present_files",
            "computer://",
            "Sonnet",
            "Opus",
        ):
            self.assertNotIn(legacy_token, skill)
        self.assertNotIn("python3 scripts/", skill)
        self.assertNotIn(".venv/bin/", skill)

    def test_pdf_commands_resolve_bundled_paths_from_skill_root(self):
        production = (ROOT / "references" / "pdf-production.md").read_text(
            encoding="utf-8"
        )
        for script in (
            "md_to_pdf.py",
            "validate_ledger.py",
            "validate_report.py",
            "render_pdf_pages.py",
        ):
            self.assertIn(f'$SKILL_ROOT/scripts/{script}', production)
        self.assertNotIn("python3 scripts/", production)

    def test_pdf_intake_is_non_blocking_and_offers_all_four_templates(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        templates = (ROOT / "references" / "pdf-templates.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Begin research in the same turn", skill)
        self.assertIn("Never wait for an answer", skill)
        self.assertIn("full two-sentence", skill)
        for label in (
            "A — Executive (Default)",
            "B — Spectrum",
            "C — Atlas",
            "D — Horizon",
        ):
            self.assertIn(label, templates)
        self.assertIn("Default: Off", templates)
        self.assertIn("if an answer arrives after a draft PDF was rendered", templates)

    def test_evidence_schema_declares_real_json_schema(self):
        schema = json.loads(
            (ROOT / "references" / "evidence-ledger.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
        )
        self.assertIn("claims", schema["required"])
        self.assertIn("sources", schema["required"])
        self.assertEqual(1, schema["properties"]["coverage"]["minItems"])
        self.assertEqual(1, schema["properties"]["sources"]["minItems"])
        self.assertEqual(1, schema["properties"]["claims"]["minItems"])


if __name__ == "__main__":
    unittest.main()
