import tempfile
import threading
import unittest
from pathlib import Path

from scripts.artifact_safety import publish_temp_file

ROOT = Path(__file__).resolve().parents[1]


class AtomicPublishTests(unittest.TestCase):
    def test_no_force_concurrent_publish_never_overwrites_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "result.json"
            temporary_paths = []
            barrier = threading.Barrier(2)
            outcomes = []

            def publish(value):
                temporary = root / f".result-{value}.tmp"
                temporary.write_text(value, encoding="utf-8")
                temporary_paths.append(temporary)
                barrier.wait()
                try:
                    publish_temp_file(temporary, target, force=False)
                except FileExistsError:
                    outcomes.append(("exists", value))
                else:
                    outcomes.append(("published", value))

            threads = [
                threading.Thread(target=publish, args=(value,))
                for value in ("alpha", "bravo")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(1, [kind for kind, _ in outcomes].count("published"))
            self.assertEqual(1, [kind for kind, _ in outcomes].count("exists"))
            winner = next(value for kind, value in outcomes if kind == "published")
            self.assertEqual(winner, target.read_text(encoding="utf-8"))
            self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_force_atomically_replaces_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "result.json"
            temporary = root / ".result-new.tmp"
            target.write_text("old", encoding="utf-8")
            temporary.write_text("new", encoding="utf-8")

            publish_temp_file(temporary, target, force=True)

            self.assertEqual("new", target.read_text(encoding="utf-8"))
            self.assertFalse(temporary.exists())

    def test_rejects_a_temporary_file_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            destination_dir = root / "destination"
            source_dir.mkdir()
            destination_dir.mkdir()
            temporary = source_dir / ".result.tmp"
            temporary.write_text("new", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "same directory"):
                publish_temp_file(
                    temporary,
                    destination_dir / "result.json",
                    force=False,
                )

            self.assertFalse((destination_dir / "result.json").exists())
            self.assertFalse(temporary.exists())

    def test_all_production_writers_use_the_shared_publisher(self):
        for relative in (
            "scripts/md_to_pdf.py",
            "scripts/content_gate.py",
            "scripts/rewild_gate.py",
            "scripts/source_fidelity.py",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("publish_temp_file(", source)


if __name__ == "__main__":
    unittest.main()
