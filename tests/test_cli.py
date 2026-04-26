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
from ast_pilot.evidence import Evidence, ModuleInfo, TestEvidence as EvidenceTestRecord
from ast_pilot.validator import ValidationIssue, ValidationResult


def _fake_render_start_md(ev, output_path, use_llm=True, **kwargs):
    """Match the real ``render_start_md`` contract: write prompt.md to disk
    and return the same content. ``cmd_run`` re-reads prompt.md from disk
    after the validation/fix loop, so a mock that only returns a string
    silently breaks tests."""
    content = "# demo-task\n"
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return content


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
                patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
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
                    patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
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
            prompt_path = root / "prompt.md"
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
            prompt_path = root / "prompt.md"
            prompt_path.write_text("# demo-task\n\nBuild it.\n", encoding="utf-8")
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            test_path = root / "test_demo.py"
            test_path.write_text("def test_demo():\n    assert True\n", encoding="utf-8")
            ev = Evidence(
                project_name="demo-task",
                source_files=[ModuleInfo(path=str(source_path), module_name="demo")],
                tests=[EvidenceTestRecord(test_file=str(test_path), test_name="test_demo")],
            )

            args = argparse.Namespace(
                evidence=str(evidence_path),
                prompt=str(prompt_path),
                output=str(root / "bundle-out"),
            )

            with (
                patch("ast_pilot.evidence.Evidence.load", return_value=ev),
                patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                patch("ast_pilot.grader_gen.generate_graders", return_value={}) as generate_graders,
                patch("ast_pilot.cli._promote_generated_task", return_value=None),
            ):
                cmd_bundle(args)

            generate_graders.assert_called_once_with(
                ev,
                output_dir=root / "bundle-out",
                prompt_md="# demo-task\n\nBuild it.\n",
                source_paths=[str(source_path)],
                test_paths=[str(test_path)],
            )


class CliAlignmentTests(unittest.TestCase):
    def test_run_blocks_promotion_on_alignment_contradiction(self) -> None:
        from ast_pilot.alignment_review import AlignmentIssue, AlignmentReview

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            out_dir = root / "output"

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=str(out_dir),
                no_llm=False,
                no_alignment_autofix=False,
                alignment_max_rounds=2,
            )

            blocking_review = AlignmentReview(issues=[
                AlignmentIssue("error", "direct_contradiction", "Fatal",
                               "prompt says X", "grader says Y", "conflict", safe_to_fix=False),
            ])

            def fake_generate(ev, output_dir, prompt_md, source_paths, test_paths):
                generated = Path(output_dir) / "tasks" / "demo-task"
                generated.mkdir(parents=True)
                (generated / "task.py").write_text("task = 1\n", encoding="utf-8")
                (generated / "prompt.md").write_text("# demo\n", encoding="utf-8")
                tests = generated / "tests"
                tests.mkdir()
                (tests / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
                return {"tasks/demo-task/task.py": "task = 1\n"}

            with (
                patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
                patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                patch("ast_pilot.grader_gen.generate_graders", side_effect=fake_generate),
                patch("ast_pilot.cli._run_alignment_loop", return_value=blocking_review),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    cmd_run(args)

            self.assertEqual(ctx.exception.code, 2)

    def test_run_promotes_when_alignment_is_clean(self) -> None:
        from ast_pilot.alignment_review import AlignmentReview

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            (root / "tasks").mkdir()
            out_dir = root / "output"

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=str(out_dir),
                no_llm=False,
                no_alignment_autofix=False,
                alignment_max_rounds=2,
            )

            def fake_generate(ev, output_dir, prompt_md, source_paths, test_paths):
                generated = Path(output_dir) / "tasks" / "demo-task"
                generated.mkdir(parents=True)
                (generated / "task.py").write_text("task = 1\n", encoding="utf-8")
                (generated / "prompt.md").write_text("# demo\n", encoding="utf-8")
                return {"tasks/demo-task/task.py": "task = 1\n"}

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with (
                    patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                    patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
                    patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                    patch("ast_pilot.grader_gen.generate_graders", side_effect=fake_generate),
                    patch("ast_pilot.cli._run_alignment_loop", return_value=AlignmentReview()),
                ):
                    cmd_run(args)
            finally:
                os.chdir(previous_cwd)

            self.assertTrue((root / "tasks" / "demo_task" / "task.py").exists())

    def test_run_skips_alignment_when_no_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            (root / "tasks").mkdir()
            out_dir = root / "output"

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=str(out_dir),
                no_llm=True,
                no_alignment_autofix=False,
                alignment_max_rounds=2,
            )

            def fake_generate(ev, output_dir, prompt_md, source_paths, test_paths):
                generated = Path(output_dir) / "tasks" / "demo-task"
                generated.mkdir(parents=True)
                (generated / "task.py").write_text("task = 1\n", encoding="utf-8")
                return {"tasks/demo-task/task.py": "task = 1\n"}

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with (
                    patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                    patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
                    patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                    patch("ast_pilot.grader_gen.generate_graders", side_effect=fake_generate),
                    patch("ast_pilot.cli._run_alignment_loop") as mock_loop,
                ):
                    cmd_run(args)
            finally:
                os.chdir(previous_cwd)

            mock_loop.assert_not_called()

    def test_run_skips_alignment_when_flag_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo():\n    return 1\n", encoding="utf-8")
            (root / "tasks").mkdir()
            out_dir = root / "output"

            args = argparse.Namespace(
                sources=[str(source_path)],
                tests=None,
                name="demo-task",
                readme=None,
                output=str(out_dir),
                no_llm=False,
                no_alignment_autofix=True,
                alignment_max_rounds=2,
            )

            def fake_generate(ev, output_dir, prompt_md, source_paths, test_paths):
                generated = Path(output_dir) / "tasks" / "demo-task"
                generated.mkdir(parents=True)
                (generated / "task.py").write_text("task = 1\n", encoding="utf-8")
                return {"tasks/demo-task/task.py": "task = 1\n"}

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with (
                    patch("ast_pilot.scanner.scan", return_value=Evidence(project_name="demo-task")),
                    patch("ast_pilot.spec_renderer.render_start_md", side_effect=_fake_render_start_md),
                    patch("ast_pilot.validator.validate", return_value=ValidationResult()),
                    patch("ast_pilot.grader_gen.generate_graders", side_effect=fake_generate),
                    patch("ast_pilot.cli._run_alignment_loop") as mock_loop,
                ):
                    cmd_run(args)
            finally:
                os.chdir(previous_cwd)

            mock_loop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
