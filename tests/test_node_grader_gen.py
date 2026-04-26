"""Tests for node_grader_gen: TypeScript task bundle generation (v2 shape)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence, ModuleInfo
from ast_pilot.node_grader_gen import generate_graders


def _load_generated_task_module(task_dir: Path):
    # Pre-import tasks._helpers while the real environment is still in place —
    # exec_module runs under patch.dict(clear=True) which strips os.environ and
    # would break any lazy import inside the helpers module.
    import tasks._helpers  # noqa: F401

    module_name = "_generated_node_task_under_test"
    task_path = task_dir / "task.py"

    class FakeTask:
        def __init__(self, scenario: str, args: dict, env=None):
            self.scenario = scenario
            self.args = args
            self.env = env
            self.validation = []
            self.slug = None

    class FakeMCPToolCall:
        def __init__(self, name: str, arguments: dict):
            self.name = name
            self.arguments = arguments

    fake_hud_eval_task = types.ModuleType("hud.eval.task")
    fake_hud_eval_task.Task = FakeTask

    fake_hud_types = types.ModuleType("hud.types")
    fake_hud_types.MCPToolCall = FakeMCPToolCall

    spec = importlib.util.spec_from_file_location(module_name, task_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None

    with patch.dict(os.environ, {}, clear=True):
        with patch.dict(
            sys.modules,
            {
                "hud.eval.task": fake_hud_eval_task,
                "hud.types": fake_hud_types,
            },
            clear=False,
        ):
            sys.modules.pop(module_name, None)
            spec.loader.exec_module(module)
            return module


class NodeGraderGenTests(unittest.TestCase):
    def _make_repo(self, root: Path, *, with_lockfile: bool = True) -> None:
        pkg = {
            "name": "demo",
            "version": "1.0.0",
            "type": "module",
            "devDependencies": {"vitest": "^1.0.0"},
        }
        (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        if with_lockfile:
            lock = {"name": "demo", "lockfileVersion": 3, "packages": {}}
            (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")

    def test_preserves_repo_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            (root / "tests").mkdir()
            test = root / "tests" / "lib.test.ts"
            test.write_text("import { x } from '../src/lib';\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[test],
            )

            self.assertIn("tasks/demo/golden/src/lib.ts", files)
            self.assertIn("tasks/demo/tests/tests/lib.test.ts", files)

    def test_emits_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[],
            )

            self.assertIn("tasks/demo/node_bundle_manifest.json", files)
            manifest = json.loads(files["tasks/demo/node_bundle_manifest.json"])
            self.assertEqual(manifest["slug"], "demo")
            self.assertIn("src/lib.ts", manifest["source_files"])

    def test_task_py_uses_v2_scenario_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            (root / "tests").mkdir()
            test = root / "tests" / "lib.test.ts"
            test.write_text("import { x } from '../src/lib';\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[test],
            )

            task_py = files["tasks/demo/task.py"]
            self.assertIn('SCENARIO_ID = "ast-pilot:coding-task-v2"', task_py)
            self.assertIn("from tasks._helpers import (", task_py)
            self.assertIn("vitest_grader(", task_py)
            self.assertIn("load_prompt(__file__)", task_py)
            self.assertIn("load_support(__file__)", task_py)
            self.assertIn("load_node_project(__file__)", task_py)
            self.assertIn("golden_workspace_validation(__file__)", task_py)
            # v1 transport/staging machinery must not leak into v2 task.py.
            self.assertNotIn("_inject_and_run", task_py)
            self.assertNotIn("_prepare_hidden_runtime", task_py)
            self.assertNotIn("_golden_setup", task_py)
            self.assertNotIn("import base64", task_py)
            self.assertNotIn("task_bootstrap", task_py)
            self.assertNotIn("_HUD_DEV_CHILD", task_py)
            self.assertNotIn("HUD_ENV_NAME", task_py)

    def test_bundles_transitive_support_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            fixtures = root / "tests" / "fixtures"
            fixtures.mkdir(parents=True)
            idx = fixtures / "index.ts"
            idx.write_text("export const a = 1;\n", encoding="utf-8")

            (root / "tests").mkdir(exist_ok=True)
            test = root / "tests" / "lib.test.ts"
            test.write_text(
                "import { x } from '../src/lib';\nimport * as fix from './fixtures/';\n",
                encoding="utf-8",
            )

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[test],
            )

            self.assertIn("tasks/demo/support/tests/fixtures/index.ts", files)

    def test_rejects_missing_bare_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            (root / "tests").mkdir()
            test = root / "tests" / "lib.test.ts"
            test.write_text(
                "import { ObjectID } from 'mongodb';\nimport { x } from '../src/lib';\n",
                encoding="utf-8",
            )

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            with self.assertRaisesRegex(ValueError, "mongodb"):
                generate_graders(
                    ev,
                    output_dir=root / "output",
                    prompt_md="# demo\n",
                    source_paths=[src],
                    test_paths=[test],
                )

    def test_generated_task_loads_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            (root / "tests").mkdir()
            test = root / "tests" / "lib.test.ts"
            test.write_text("import { x } from '../src/lib';\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            output_dir = root / "output"
            files = generate_graders(
                ev,
                output_dir=output_dir,
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[test],
            )

            # resolve_env_name reads .hud/config.json at the project root
            # (two levels up from a task dir) — mirror that layout.
            hud_dir = output_dir / ".hud"
            hud_dir.mkdir()
            (hud_dir / "config.json").write_text(
                json.dumps({"registryName": "demo-env"}), encoding="utf-8"
            )

            generated_task_dir = output_dir / "tasks" / "demo"
            module = _load_generated_task_module(generated_task_dir)

            self.assertEqual(module.task.scenario, "ast-pilot:coding-task-v2")
            self.assertEqual(module.task.slug, "demo")
            graders = module.task.args["graders"]
            self.assertEqual(len(graders), 1)
            self.assertEqual(graders[0]["kind"], "vitest")
            self.assertEqual(graders[0]["test_rel"], "tests/lib.test.ts")
            self.assertIsNotNone(module.task.args.get("node_project"))
            self.assertEqual(module.task.args["node_project"]["slug"], "demo")

    def test_duplicate_basenames_both_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src" / "a").mkdir(parents=True)
            (root / "src" / "b").mkdir(parents=True)
            src_a = root / "src" / "a" / "index.ts"
            src_a.write_text("export const a = 1;\n", encoding="utf-8")
            src_b = root / "src" / "b" / "index.ts"
            src_b.write_text("export const b = 2;\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [
                ModuleInfo(path=str(src_a), module_name="a_index"),
                ModuleInfo(path=str(src_b), module_name="b_index"),
            ]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src_a, src_b],
                test_paths=[],
            )

            self.assertIn("tasks/demo/golden/src/a/index.ts", files)
            self.assertIn("tasks/demo/golden/src/b/index.ts", files)

    def test_config_files_bundled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)
            (root / "tsconfig.json").write_text('{"compilerOptions": {}}', encoding="utf-8")

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            ev = Evidence(project_name="demo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# demo\n",
                source_paths=[src],
                test_paths=[],
            )

            self.assertIn("tasks/demo/config/package.json", files)
            self.assertIn("tasks/demo/config/package-lock.json", files)
            self.assertIn("tasks/demo/config/tsconfig.json", files)

    def test_node_grader_rejects_unsupported_ctx(self) -> None:
        """Regression: previously the generator computed ``ctx.is_supported``
        and ignored it, silently shipping half-baked bundles for unsupported
        repos (workspaces, missing lockfile, non-vitest, path aliases). The
        generator must now hard-fail with the unsupported reasons before
        writing anything to the output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Workspaces are explicitly unsupported by detect_node_project.
            pkg = {
                "name": "monorepo",
                "version": "1.0.0",
                "type": "module",
                "workspaces": ["packages/*"],
                "devDependencies": {"vitest": "^1.0.0"},
            }
            (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
            lock = {"name": "monorepo", "lockfileVersion": 3, "packages": {}}
            (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")

            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;\n", encoding="utf-8")

            ev = Evidence(project_name="monorepo", language="typescript")
            ev.source_files = [ModuleInfo(path=str(src), module_name="lib")]

            output_dir = root / "output"
            with self.assertRaises(ValueError) as ctx:
                generate_graders(
                    ev,
                    output_dir=output_dir,
                    prompt_md="# monorepo\n",
                    source_paths=[src],
                    test_paths=[],
                )
            self.assertIn("Monorepo workspaces", str(ctx.exception))
            # Output directory may have been created by mkdir, but the task
            # bundle must NOT exist — generation aborted before writing files.
            self.assertFalse((output_dir / "tasks" / "monorepo" / "task.py").exists())


if __name__ == "__main__":
    unittest.main()
