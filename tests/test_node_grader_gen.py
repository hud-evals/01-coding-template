"""Tests for node_grader_gen: TypeScript task bundle generation."""

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


def _load_generated_task_module(task_dir: Path, env_vars: dict[str, str] | None = None):
    module_name = "_generated_node_task_under_test"
    task_path = task_dir / "task.py"
    project_root = Path(__file__).resolve().parents[1]

    class FakeEnvironment:
        def __init__(self, name: str):
            self.name = name
            self.connected = []

        def connect_hub(self, env_name: str) -> None:
            self.connected.append(env_name)

    class FakeTask:
        def __init__(self, env, scenario: str, args: dict):
            self.env = env
            self.scenario = scenario
            self.args = args
            self.validation = []
            self.slug = None

    class FakeMCPToolCall:
        def __init__(self, name: str, arguments: dict):
            self.name = name
            self.arguments = arguments

    fake_hud = types.ModuleType("hud")
    fake_hud.__path__ = []
    fake_hud.Environment = FakeEnvironment

    fake_hud_eval = types.ModuleType("hud.eval")
    fake_hud_eval.__path__ = []

    fake_hud_eval_task = types.ModuleType("hud.eval.task")
    fake_hud_eval_task.Task = FakeTask

    fake_hud_types = types.ModuleType("hud.types")
    fake_hud_types.MCPToolCall = FakeMCPToolCall

    spec = importlib.util.spec_from_file_location(module_name, task_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None

    with patch.dict(os.environ, env_vars or {}, clear=True):
        with patch.dict(
            sys.modules,
            {
                "hud": fake_hud,
                "hud.eval": fake_hud_eval,
                "hud.eval.task": fake_hud_eval_task,
                "hud.types": fake_hud_types,
            },
            clear=False,
        ):
            with patch.object(sys, "path", [str(project_root), *sys.path]):
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

    def test_golden_validation_writes_flat_to_workspace(self) -> None:
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

            task_py = files["tasks/demo/task.py"]
            self.assertIn("/home/ubuntu/workspace/lib.ts", task_py)
            self.assertNotIn("/home/ubuntu/workspace/src/lib.ts", task_py)

    def test_no_glob_workspace_copy_in_generated_task(self) -> None:
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

            task_py = files["tasks/demo/task.py"]
            self.assertNotIn("*.ts", task_py)
            self.assertNotIn("*.mts", task_py)

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

            generated_task_dir = output_dir / "tasks" / "demo"
            (output_dir / ".env").write_text("HUD_ENV_NAME=test-env\n", encoding="utf-8")

            module = _load_generated_task_module(generated_task_dir)
            self.assertEqual(module.task.env.name, "test-env")
            self.assertEqual(module.task.scenario, "ast-pilot:coding-task")
            self.assertEqual(module.task.slug, "demo")
            self.assertEqual(len(module.task.args["bash_checks"]), 1)
            self.assertEqual(module.task.args["bash_checks"][0]["name"], "tests/lib.test.ts")

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


if __name__ == "__main__":
    unittest.main()
