"""`alx` finds the managed runtime and relocates itself into it (hotfix 7a)."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import alx

WINDOWS = sys.platform == "win32"


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="alexandria-runtime-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runtime = self.root / "runtime"
        self.skill = self.root / "skill"
        (self.runtime / "env").mkdir(parents=True)
        self.skill.mkdir()
        patch = mock.patch.dict(
            os.environ, {"ALEXANDRIA_RUNTIME_DIR": str(self.runtime)}
        )
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("ALEXANDRIA_REEXEC", None)
        patch = mock.patch.object(alx, "ROOT", self.skill)
        patch.start()
        self.addCleanup(patch.stop)

    def write_manifest(self, folder, name):
        (folder / ".runtime.json").write_text(
            json.dumps({"command": [name]}), encoding="utf-8"
        )

    def touch(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


class DiscoveryTests(RuntimeCase):
    def test_runtime_manifest_wins_over_the_skill_copy(self):
        self.write_manifest(self.runtime, "runtime-python")
        self.write_manifest(self.skill, "skill-python")
        self.assertEqual(["runtime-python"], alx.runtime_command())

    def test_skill_manifest_used_when_the_runtime_has_none(self):
        self.write_manifest(self.skill, "skill-python")
        self.assertEqual(["skill-python"], alx.runtime_command())

    def test_micromamba_command_constructed_without_a_manifest(self):
        mamba = self.runtime / (
            "Library/bin/micromamba.exe" if WINDOWS else "bin/micromamba"
        )
        self.touch(mamba)
        self.touch(self.runtime / ("env/python.exe" if WINDOWS else "env/bin/python"))
        self.assertEqual(
            [
                str(mamba),
                "--no-rc",
                "run",
                "--prefix",
                str(self.runtime / "env"),
                "python",
            ],
            alx.runtime_command(),
        )

    def test_environment_interpreter_is_the_fallback(self):
        python = self.runtime / ("env/python.exe" if WINDOWS else "env/bin/python")
        self.touch(python)
        self.assertEqual([str(python)], alx.runtime_command())

    def test_no_runtime_at_all(self):
        self.assertIsNone(alx.runtime_command())


class RelocationTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(alx, "runtime_packages_present", return_value=False)
        patch.start()
        self.addCleanup(patch.stop)

    def recorder(self):
        """A stand-in runtime interpreter: record argv and environment, exit 7."""
        record = self.root / "argv.json"
        script = self.root / "recorder.py"
        script.write_text(
            "import json, os, sys\n"
            f"json.dump({{'argv': sys.argv[1:], 'reexec': os.environ.get"
            f"('ALEXANDRIA_REEXEC')}}, open({str(record)!r}, 'w'))\n"
            "sys.exit(7)\n",
            encoding="utf-8",
        )
        return [sys.executable, str(script)], record

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = alx.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_relocation_runs_the_runtime_command_once(self):
        command, record = self.recorder()
        with mock.patch.object(alx, "runtime_command", return_value=command):
            code, _out, err = self.run_main("--dir", str(self.root), "status")
        self.assertEqual(7, code)
        self.assertIn(f"alx: relocating to managed runtime {sys.executable}", err)
        recorded = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual("1", recorded["reexec"])
        self.assertEqual(
            [str(Path(alx.__file__).resolve()), "--dir", str(self.root), "status"],
            recorded["argv"],
        )

    def test_the_relocated_child_does_not_relocate_again(self):
        command, record = self.recorder()
        os.environ["ALEXANDRIA_REEXEC"] = "1"
        with mock.patch.object(alx, "runtime_command", return_value=command):
            code, out, err = self.run_main("--dir", str(self.root), "status")
        self.assertFalse(record.exists())
        self.assertEqual(1, code)
        self.assertEqual(
            f"runtime: {sys.executable} (host — relocation failed)",
            out.splitlines()[0],
        )
        self.assertIn("No Alexandria workspace", err)

    def test_missing_runtime_refuses_every_subcommand(self):
        with mock.patch.object(alx, "runtime_command", return_value=None):
            code, _out, err = self.run_main("--dir", str(self.root), "status")
        self.assertEqual(2, code)
        self.assertIn("RUNTIME MISSING — install it: sh ", err)
        self.assertIn(f"{self.skill}/scripts/install.sh", err)
        self.assertIn("Never pip-install into a host interpreter.", err)


class StatusLineTests(RuntimeCase):
    def test_status_reports_the_managed_interpreter_first(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = alx.main(["--dir", str(self.root), "status"])
        self.assertEqual(1, code)
        self.assertEqual(
            f"runtime: {sys.executable} (managed)", out.getvalue().splitlines()[0]
        )
        self.assertIn("No Alexandria workspace", err.getvalue())


if __name__ == "__main__":
    unittest.main()
