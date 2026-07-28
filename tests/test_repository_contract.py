import json
import re
import subprocess
import sys
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
            "content_gate.py",
            "md_to_pdf.py",
            "validate_ledger.py",
            "validate_report.py",
            "render_pdf_pages.py",
        ):
            self.assertIn(f'$SKILL_ROOT/scripts/{script}', production)
        self.assertNotIn("python3 scripts/", production)

    def test_pdf_intake_is_non_blocking_and_offers_all_eleven_templates(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        templates = (ROOT / "references" / "pdf-templates.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Begin research in the same turn", skill)
        self.assertIn("Never wait for an answer", skill)
        self.assertIn("complete one-sentence", skill)
        for label in (
            "A — Executive (Default)",
            "B — Spectrum",
            "C — Atlas",
            "D — Horizon",
            "E — Maison",
            "F — Blueprint",
            "G — Terrain",
            "H — Orbit",
            "I — Sunbeam",
            "J — Current",
            "K — Apricot",
        ):
            self.assertIn(label, templates)
        self.assertIn("all eleven", skill)
        self.assertIn("Sunbeam", production := (
            ROOT / "references" / "pdf-production.md"
        ).read_text(encoding="utf-8"))
        self.assertIn("Current", production)
        self.assertIn("Apricot", production)
        self.assertIn("Default: Off", templates)
        self.assertIn("if an answer arrives after a draft PDF was rendered", templates)
        self.assertIn("two PDFs", templates)
        self.assertIn("same report content", templates)

    def test_rewild_is_a_bundled_hard_gate_for_every_report_language(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        expected_profiles = {
            "en": ROOT / "references" / "rewild" / "rewild",
            "zh-CN": ROOT / "references" / "rewild" / "rewild-zh",
            "zh-HK": ROOT / "references" / "rewild" / "rewild-hk",
        }

        self.assertIn("Rewild hard gate", skill)
        self.assertIn("Every report must pass", skill)
        self.assertIn("Do not proceed to Step 7", skill)
        self.assertIn("scripts/rewild_gate.py", skill)
        self.assertIn("--rewild-receipt", skill)
        self.assertNotIn(
            "If the user explicitly asks to remove AI-like writing", skill
        )
        for report_lang, profile_root in expected_profiles.items():
            with self.subTest(report_lang=report_lang):
                self.assertTrue((profile_root / "SKILL.md").is_file())
                self.assertTrue(
                    (profile_root / "references" / "patterns.md").is_file()
                )
                self.assertTrue(
                    (profile_root / "scripts" / "naturalness-check.py").is_file()
                )

    def test_ci_pdf_samples_pass_through_the_rewild_gate(self):
        workflow = (
            ROOT / ".github" / "workflows" / "test.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tests/build_gated_fixtures.py", workflow)
        self.assertGreaterEqual(workflow.count("--rewild-receipt"), 6)
        for template in (
            "executive", "spectrum", "atlas", "horizon", "maison",
            "blueprint", "terrain", "orbit", "sunbeam", "current", "apricot",
        ):
            self.assertIn(template, workflow)
        self.assertIn("pip_audit", workflow)

    def test_content_quality_gate_is_bundled_required_and_ci_exercised(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        protocol = (ROOT / "references" / "research-protocol.md").read_text(
            encoding="utf-8"
        )
        quality = ROOT / "references" / "content-quality.md"
        schema_path = ROOT / "references" / "content-review.schema.json"
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
            encoding="utf-8"
        )

        self.assertTrue(quality.is_file())
        self.assertTrue(schema_path.is_file())
        self.assertIn("Content quality hard gate", skill)
        self.assertIn("scripts/content_gate.py", skill)
        self.assertIn("--content-receipt", skill)
        self.assertIn("counterevidence", protocol.casefold())
        self.assertIn("research stop", protocol.casefold())
        self.assertGreaterEqual(workflow.count("--content-receipt"), 3)

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(2, schema["properties"]["schema_version"]["const"])
        self.assertIn("section_reviews", schema["required"])
        self.assertEqual(4, schema["$defs"]["score"]["properties"]["score"]["minimum"])
        result = subprocess.run(
            [sys.executable, "-S", str(ROOT / "scripts" / "content_gate.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--review-note", result.stdout)

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
        self.assertEqual(3, schema["properties"]["schema_version"]["const"])
        self.assertIn(
            "adversarial_tests",
            schema["$defs"]["synthesis"]["required"],
        )
        self.assertEqual(1, schema["properties"]["coverage"]["minItems"])
        self.assertEqual(1, schema["properties"]["sources"]["minItems"])
        self.assertEqual(1, schema["properties"]["claims"]["minItems"])


if __name__ == "__main__":
    unittest.main()
