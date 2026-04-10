from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.cli import _promote_generated_task, cmd_bundle, cmd_run
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

    def test_run_without_output_promotes_task_without_creating_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            (root / "tasks").mkdir()

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=None,
                no_llm=True,
            )

            def fake_generate_graders(ev, output_dir, prompt_md, source_paths, test_paths):
                generated_dir = Path(output_dir) / "tasks" / "demo-task"
                generated_dir.mkdir(parents=True)
                (generated_dir / "task.py").write_text("task = 1\n", encoding="utf-8")
                return {"tasks/demo-task/task.py": "task = 1\n"}

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with (
                    patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                    patch("ast_pilot.spec_renderer.render_start_md", return_value="# demo-task\n"),
                    patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                    patch("ast_pilot.grader_gen.generate_graders", side_effect=fake_generate_graders),
                ):
                    cmd_run(args)
            finally:
                os.chdir(previous_cwd)

            self.assertEqual((root / "tasks" / "demo_task" / "task.py").read_text(encoding="utf-8"), "task = 1\n")
            self.assertFalse((root / "output").exists())

    def test_bundle_stops_before_generating_when_prompt_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            evidence_path = root / "evidence.json"
            evidence_path.write_text("{}", encoding="utf-8")
            prompt_path = root / "start.md"
            prompt_path.write_text("# demo-task\n", encoding="utf-8")

            args = argparse.Namespace(
                evidence=str(evidence_path),
                prompt=str(prompt_path),
                output=str(root / "bundle-out"),
            )
            validation = ValidationResult(
                issues=[ValidationIssue("error", "parameters", "documented signature drift", line=12)]
            )

            with (
                patch("ast_pilot.evidence.Evidence.load", return_value=Evidence(project_name="demo-task")),
                patch("ast_pilot.validator.validate", return_value=validation),
                patch("ast_pilot.grader_gen.generate_graders") as generate_graders,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    cmd_bundle(args)

            self.assertEqual(ctx.exception.code, 2)
            generate_graders.assert_not_called()

    def test_bundle_passes_validated_prompt_into_grader_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            evidence_path = root / "evidence.json"
            evidence_path.write_text("{}", encoding="utf-8")
            prompt_path = root / "start.md"
            prompt_path.write_text("# demo-task\n\nBuild it.\n", encoding="utf-8")

            args = argparse.Namespace(
                evidence=str(evidence_path),
                prompt=str(prompt_path),
                output=str(root / "bundle-out"),
            )

            with (
                patch("ast_pilot.evidence.Evidence.load", return_value=Evidence(project_name="demo-task")),
                patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                patch("ast_pilot.grader_gen.generate_graders", return_value={}) as generate_graders,
                patch("ast_pilot.cli._promote_generated_task", return_value=None),
            ):
                cmd_bundle(args)

            generate_graders.assert_called_once_with(
                Evidence(project_name="demo-task"),
                output_dir=root / "bundle-out",
                prompt_md="# demo-task\n\nBuild it.\n",
            )


if __name__ == "__main__":
    unittest.main()
