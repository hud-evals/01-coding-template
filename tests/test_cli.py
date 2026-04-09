from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.cli import _promote_generated_task


class CliTests(unittest.TestCase):
    def test_promote_generated_task_copies_slugged_bundle_into_package_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output" / "my-task"
            generated_dir = output_root / "tasks" / "my-task"
            generated_dir.mkdir(parents=True)
            (generated_dir / "task.py").write_text("task = 1\n", encoding="utf-8")

            tasks_dir = root / "tasks"
            tasks_dir.mkdir()
            existing = tasks_dir / "my_task"
            existing.mkdir()
            (existing / "old.txt").write_text("stale\n", encoding="utf-8")

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                promoted = _promote_generated_task(output_root, "my-task")
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(promoted, (tasks_dir / "my_task").resolve())
            self.assertFalse((tasks_dir / "my_task" / "old.txt").exists())
            self.assertEqual((tasks_dir / "my_task" / "task.py").read_text(encoding="utf-8"), "task = 1\n")


if __name__ == "__main__":
    unittest.main()
