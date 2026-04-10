from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.cli import _promote_generated_task, cmd_run
from ast_pilot.evidence import Evidence
from ast_pilot.validator import ValidationIssue, ValidationResult


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

    def test_run_stops_before_bundling_if_validation_errors_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            out_dir = root / "output" / "demo-task"

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=str(out_dir),
                no_llm=True,
            )
            validation = ValidationResult(
                issues=[ValidationIssue("error", "parameters", "documented signature drift", line=12)]
            )

            with (
                patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                patch("ast_pilot.spec_renderer.render_start_md", return_value="# demo-task\n"),
                patch("ast_pilot.validator.validate", return_value=validation),
                patch("ast_pilot.grader_gen.generate_graders") as generate_graders,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    cmd_run(args)

            self.assertEqual(ctx.exception.code, 2)
            generate_graders.assert_not_called()


if __name__ == "__main__":
    unittest.main()
