import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import install_runtime


class DownloadTests(unittest.TestCase):
    def test_bad_primary_download_uses_verified_mirror(self):
        data = b"verified package"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "package"
            with mock.patch.object(
                install_runtime, "urlopen",
                side_effect=[io.BytesIO(b"wrong bytes"), io.BytesIO(data)],
            ):
                install_runtime.download_verified(
                    ["https://primary.example/file", "https://mirror.example/file"],
                    target, hashlib.sha256(data).hexdigest(),
                )
            self.assertEqual(target.read_bytes(), data)

    def test_failed_download_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "package"
            target.write_bytes(b"original")
            with mock.patch.object(install_runtime, "urlopen", return_value=io.BytesIO(b"bad")):
                with self.assertRaises(RuntimeError):
                    install_runtime.download_verified(
                        ["https://primary.example/file"], target, "0" * 64,
                    )
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual([target], list(Path(folder).iterdir()))

    def test_verified_existing_file_needs_no_network(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "package"
            target.write_bytes(b"cached")
            with mock.patch.object(install_runtime, "urlopen", side_effect=AssertionError):
                install_runtime.download_verified(
                    ["https://primary.example/file"], target,
                    hashlib.sha256(b"cached").hexdigest(),
                )
            self.assertEqual(target.read_bytes(), b"cached")


class LauncherTests(unittest.TestCase):
    def test_install_writes_one_path_launchers_next_to_the_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root, runtime = Path(folder) / "skill", Path(folder) / "runtime"
            root.mkdir()
            runtime.mkdir()
            (root / "requirements.txt").write_text("pypdf==5.1.0\n", encoding="utf-8")
            with mock.patch.object(install_runtime, "ROOT", root), \
                    mock.patch.object(install_runtime, "verify_runtime"), \
                    mock.patch.object(
                        install_runtime.sys, "argv",
                        ["install_runtime.py", "--runtime", str(runtime), "--verify-only"],
                    ):
                install_runtime.main()
            posix = runtime / "bin" / "python"
            self.assertEqual(
                '#!/bin/sh\n'
                'here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n'
                'exec "$here/bin/micromamba" --no-rc run --prefix "$here/env" python "$@"\n',
                posix.read_text(encoding="utf-8"),
            )
            self.assertTrue(os.access(posix, os.X_OK))
            windows = (runtime / "bin" / "python.cmd").read_bytes().decode("utf-8")
            self.assertEqual(install_runtime.WINDOWS_LAUNCHER, windows)
            self.assertIn(
                '"%root%\\Library\\bin\\micromamba.exe" --no-rc run '
                '--prefix "%root%\\env" python %*\r\n',
                windows,
            )
