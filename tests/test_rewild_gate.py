import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REWILD_ROOT = ROOT / "references" / "rewild"
PROFILES = {
    "en": ("rewild", "en"),
    "zh-CN": ("rewild-zh", "zh"),
    "zh-HK": ("rewild-hk", "hk"),
}


def run_checker(text, *, report_lang, source=None):
    profile, checker_lang = PROFILES[report_lang]
    checker = REWILD_ROOT / profile / "scripts" / "naturalness-check.py"
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        report = work / "report.md"
        report.write_text(text, encoding="utf-8")
        command = [sys.executable, str(checker), str(report), "--lang", checker_lang]
        if source is not None:
            original = work / "source.md"
            original.write_text(source, encoding="utf-8")
            command.extend(["--source", str(original)])
        return subprocess.run(command, capture_output=True, text=True, check=False)


class RewildGateTests(unittest.TestCase):
    def test_each_profile_ships_the_same_complete_checker(self):
        checkers = []
        for profile, _ in PROFILES.values():
            path = REWILD_ROOT / profile / "scripts" / "naturalness-check.py"
            checkers.append(path.read_bytes())
        self.assertEqual(1, len(set(checkers)))

    def test_english_ai_formula_is_blocked(self):
        result = run_checker(
            "In today's rapidly evolving landscape, it is worth noting that "
            "our groundbreaking platform serves as a testament to innovation. "
            "Moreover, it provides a seamless, intuitive, and powerful "
            "experience. In conclusion, the future is bright.",
            report_lang="en",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("warning", result.stdout.lower())

    def test_simplified_chinese_ai_formula_is_blocked(self):
        result = run_checker(
            "近年来，随着人工智能技术的快速发展，行业经历了深刻变革。"
            "首先，我们全面赋能业务；其次，我们打造创新闭环；"
            "最后，我们将持续深耕。总的来说，未来将更加美好。",
            report_lang="zh-CN",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("warning", result.stdout.lower())

    def test_hong_kong_profile_blocks_wrong_region_vocabulary(self):
        result = run_checker(
            "我們的網路團隊正在更新軟體，專案下星期上線。",
            report_lang="zh-HK",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Taiwan vocabulary", result.stdout)

    def test_fidelity_drift_is_blocked(self):
        source = (
            "Observers cited onboarding friction as a barrier. "
            "Setup took 45 minutes."
        )
        result = run_checker(
            "Onboarding friction is the barrier. Setup took 12 minutes. "
            "We will fix it next week.",
            report_lang="en",
            source=source,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Fidelity", result.stdout)
        self.assertIn("figures not in the original", result.stdout)


if __name__ == "__main__":
    unittest.main()
