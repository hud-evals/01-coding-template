from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence, ModuleInfo
from ast_pilot.grader_gen import (
    REPO_ROOT_ENV,
    WORKSPACE_DIR,
    _detect_cross_module_path_access,
    _insert_skip_marks,
    _prepend_workspace_syspath,
    _rewrite_repo_root_assignments,
    generate_graders,
)
from ast_pilot.scanner import scan


def _load_generated_task_module(task_dir: Path, env_vars: dict[str, str] | None = None):
    # tasks/__init__.py eagerly discovers and imports every sibling task package.
    # Pre-import it once here so discovery happens under the host environment,
    # before the patch.dict(clear=True) below strips os.environ for the test run.
    import tasks._helpers  # noqa: F401

    module_name = "_generated_task_under_test"
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

    with patch.dict(os.environ, env_vars or {}, clear=True):
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


class GraderGenTests(unittest.TestCase):
    def test_bundle_keeps_golden_imports_and_adds_hidden_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    dependencies = [
                        "httpx>=0.28.0",
                        "pyyaml>=6.0.0",
                    ]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "agent").mkdir()
            (root / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (root / "helpers").mkdir()
            (root / "helpers" / "__init__.py").write_text("", encoding="utf-8")
            (root / "helpers" / "prompt_caching.py").write_text(
                textwrap.dedent(
                    """
                    def cache_helper() -> str:
                        return "cached"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            source_path = root / "agent" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    import helpers.auth as auth_mod
                    from helpers.auth import HELPER_VALUE


                    def run() -> str:
                        return f"{auth_mod.read_value()}-{HELPER_VALUE}"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "helpers" / "auth.py").write_text(
                textwrap.dedent(
                    """
                    HELPER_VALUE = "ok"


                    def read_value() -> str:
                        return "auth"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "other_module.py").write_text(
                textwrap.dedent(
                    """
                    def sentinel() -> str:
                        return "sentinel"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from agent.target import run
                    from helpers.prompt_caching import cache_helper


                    def test_run():
                        assert run() == "auth-ok"
                        assert cache_helper() == "cached"


                    def test_other_module():
                        from other_module import sentinel
                        assert sentinel() == "sentinel"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )

            output_dir = root / "output"
            files = generate_graders(
                ev,
                output_dir=output_dir,
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            golden = files["tasks/target-task/golden/agent/target.py"]
            rewritten_test = files["tasks/target-task/tests/test_target.py"]
            task_py = files["tasks/target-task/task.py"]
            requirements = files["tasks/target-task/requirements.hidden.txt"]
            support_auth = files["tasks/target-task/support/helpers/auth.py"]
            support_prompt_caching = files["tasks/target-task/support/helpers/prompt_caching.py"]
            support_other_module = files["tasks/target-task/support/other_module.py"]
            init_py = files["tasks/target-task/__init__.py"]

            self.assertIn("import helpers.auth as auth_mod", golden)
            self.assertIn("from agent.target import run", rewritten_test)
            self.assertIn("other_module", rewritten_test)
            self.assertNotIn('@__import__("pytest").mark.xfail(', rewritten_test)
            self.assertNotIn("lambda *a, **kw", rewritten_test)
            self.assertIn("httpx>=0.28.0", requirements)
            self.assertIn("pyyaml>=6.0.0", requirements)
            self.assertIn('HELPER_VALUE = "ok"', support_auth)
            self.assertIn('return "cached"', support_prompt_caching)
            self.assertIn('return "sentinel"', support_other_module)
            # With nested layout, the target module lives at its real workspace
            # path (agent/target.py). No shim under support/ is needed.
            self.assertNotIn("tasks/target-task/support/agent/target.py", files)
            self.assertIn('SCENARIO_ID = "ast-pilot:coding-task-v2"', task_py)
            self.assertIn("from tasks._helpers import (", task_py)
            self.assertIn("pytest_grader(", task_py)
            self.assertIn("load_prompt(__file__)", task_py)
            self.assertIn("load_support(__file__)", task_py)
            self.assertIn("load_requirements(__file__)", task_py)
            self.assertIn("golden_validation(__file__)", task_py)
            self.assertNotIn("mario-claire", task_py)
            # Generated task.py looks up its env name from .hud/config.json
            # via resolve_env_name — no task_bootstrap, no .env file, no
            # HUD_ENV_NAME environment variable. Emitted as a dict so the
            # Task.env validator's auto-connect_hub fires on `hud eval .`
            # (local-file load); the Environment-instance shape skips
            # connect_hub and breaks local-file evaluation.
            self.assertIn('env={"name": resolve_env_name(__file__)}', task_py)
            self.assertNotIn("Environment(resolve_env_name(__file__))", task_py)
            self.assertNotIn("connect_hub", task_py)
            self.assertNotIn("task_bootstrap", task_py)
            self.assertNotIn("HUD_ENV_NAME", task_py)
            # v1 transport/staging machinery has been removed from the task.py
            # template — it lives in the scenario (env.py) or the helpers module now.
            self.assertNotIn("import base64", task_py)
            self.assertNotIn("_inject_and_run", task_py)
            self.assertNotIn("_stage_hidden_support", task_py)
            self.assertNotIn("_stage_runtime_assets", task_py)
            self.assertNotIn("IMAGE_TASK_DIR", task_py)
            self.assertNotIn("LEGACY_SUPPORT_DIR", task_py)
            self.assertNotIn("BUNDLED_SUPPORT_DIR", task_py)
            self.assertNotIn("BUNDLED_HIDDEN_REQUIREMENTS", task_py)
            self.assertEqual(init_py, "")

            # resolve_env_name reads .hud/config.json at parents[2] of the
            # task file — materialize that so the generated task.py loads.
            (output_dir / ".hud").mkdir()
            (output_dir / ".hud" / "config.json").write_text(
                '{"registryName": "target-env"}', encoding="utf-8"
            )

            generated_task_dir = output_dir / "tasks" / "target-task"
            module = _load_generated_task_module(generated_task_dir)
            # task.env is a dict (FakeTask doesn't run pydantic validation);
            # the real Task validator turns this into an Environment with
            # connect_hub bound to the same name.
            self.assertEqual(module.task.env["name"], "target-env")
            self.assertEqual(module.task.scenario, "ast-pilot:coding-task-v2")

            args = module.task.args
            self.assertEqual(
                sorted(args.keys()),
                ["graders", "hidden_requirements", "prompt", "support", "support_binary"],
            )
            self.assertIn("# target-task", args["prompt"])
            self.assertEqual(len(args["graders"]), 1)
            grader = args["graders"][0]
            self.assertEqual(grader["kind"], "pytest")
            self.assertEqual(grader["test_name"], "test_target.py")
            # Test content travels inlined — the script is whatever
            # generate_graders wrote into tests/test_target.py.
            self.assertEqual(grader["script"], rewritten_test)
            # Support tree inlines under its repo-relative paths.
            self.assertIn("helpers/auth.py", args["support"])
            self.assertIn('HELPER_VALUE = "ok"', args["support"]["helpers/auth.py"])
            self.assertIn("helpers/prompt_caching.py", args["support"])
            self.assertIn("other_module.py", args["support"])
            self.assertIn("httpx>=0.28.0", args["hidden_requirements"])

            # Golden staging flows through Task.validation as a single bash
            # MCPToolCall with base64 content inlined — survives JSON → shell
            # transport intact (regression-proof against backslash-heavy
            # regex payloads).
            validation = module.task.validation
            self.assertEqual(len(validation), 1)
            self.assertEqual(validation[0].name, "bash")
            command = validation[0].arguments["command"]
            self.assertIn("mkdir -p /home/ubuntu/workspace/agent", command)
            self.assertIn("/home/ubuntu/workspace/agent/target.py", command)
            self.assertIn("base64 -d >", command)

    def test_bundle_handles_common_src_layout_import_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"

                    [tool.setuptools]
                    package-dir = {"" = "src"}
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "src" / "agent").mkdir(parents=True)
            (root / "src" / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (root / "src" / "helpers").mkdir(parents=True)
            (root / "src" / "helpers" / "__init__.py").write_text("", encoding="utf-8")
            (root / "src" / "helpers" / "auth.py").write_text(
                textwrap.dedent(
                    """
                    def read_value() -> str:
                        return "auth"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            source_path = root / "src" / "agent" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    from helpers.auth import read_value


                    def run() -> str:
                        return read_value()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from agent.target import run


                    def test_run():
                        assert run() == "auth"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            rewritten_test = files["tasks/target-task/tests/test_target.py"]
            support_auth = files["tasks/target-task/support/helpers/auth.py"]

            self.assertIn("from agent.target import run", rewritten_test)
            self.assertIn('return "auth"', support_auth)
            self.assertNotIn("tasks/target-task/support/agent/target.py", files)
            self.assertIn("tasks/target-task/golden/agent/target.py", files)
            self.assertNotIn("tasks/target-task/support/src/helpers/auth.py", files)

    def test_bundle_fails_when_hidden_tests_need_unsupported_internal_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "agent").mkdir()
            (root / "agent" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "agent" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    def run() -> str:
                        return "ok"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "helpers").mkdir()
            (root / "helpers" / "__init__.py").write_text("", encoding="utf-8")
            giant_support = root / "helpers" / "giant.py"
            giant_support.write_text(
                "VALUE = 0\n" + "\n".join(f"LINE_{idx} = {idx}" for idx in range(401)) + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from agent.target import run
                    from helpers.giant import VALUE


                    def test_run():
                        assert run() == "ok"
                        assert VALUE == 0
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )

            with self.assertRaisesRegex(ValueError, "Refusing to silently inject skip/xfail markers"):
                generate_graders(
                    ev,
                    output_dir=root / "output",
                    prompt_md="# target-task\n",
                    source_paths=[source_path],
                    test_paths=[test_path],
                )

    def test_bundle_includes_referenced_runtime_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "schema.sql").write_text(
                "CREATE TABLE t (id INTEGER PRIMARY KEY);\n", encoding="utf-8",
            )
            (root / "fixtures").mkdir()
            (root / "fixtures" / "records.json").write_text("[]\n", encoding="utf-8")

            (root / "app").mkdir()
            (root / "app" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "app" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sqlite3


                    def setup_schema(db_path: str) -> None:
                        conn = sqlite3.connect(db_path)
                        with open("schema.sql") as f:
                            conn.executescript(f.read())

                    def load_records() -> list:
                        return json.load(open("fixtures/records.json"))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from app.target import setup_schema, load_records


                    def test_setup():
                        setup_schema(":memory:")


                    def test_records():
                        assert load_records() == []
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )

            asset_rels = {asset.rel_path for asset in ev.runtime_assets}
            self.assertIn("schema.sql", asset_rels)
            self.assertIn("fixtures/records.json", asset_rels)
            for asset in ev.runtime_assets:
                self.assertEqual(asset.kind, "bundled")

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            self.assertIn("tasks/target-task/support/schema.sql", files)
            self.assertIn("tasks/target-task/support/fixtures/records.json", files)
            self.assertIn(
                "CREATE TABLE t",
                files["tasks/target-task/support/schema.sql"],
            )
            self.assertEqual(
                files["tasks/target-task/support/fixtures/records.json"].strip(),
                "[]",
            )

    def test_bundle_marks_unresolved_assets_for_agent_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "app").mkdir()
            (root / "app" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "app" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    def build() -> None:
                        with open("generated.sql") as f:
                            return f.read()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from app.target import build


                    def test_build():
                        build()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )

            asset_kinds = {asset.rel_path: asset.kind for asset in ev.runtime_assets}
            self.assertEqual(asset_kinds.get("generated.sql"), "to_create_by_agent")

            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )
            self.assertNotIn("tasks/target-task/support/generated.sql", files)

    def test_rewrite_repo_root_from_dunder_file(self) -> None:
        source = textwrap.dedent(
            """
            import os
            REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
            print(REPO_ROOT)
            """
        ).strip() + "\n"
        rewritten = _rewrite_repo_root_assignments(source)
        expected_line = (
            f'REPO_ROOT = os.environ.get("{REPO_ROOT_ENV}", "{WORKSPACE_DIR}")'
        )
        self.assertIn(expected_line, rewritten)
        self.assertNotIn("os.path.abspath(__file__)", rewritten)

    def test_rewrite_path_anchor_with_pathlib(self) -> None:
        source = textwrap.dedent(
            """
            from pathlib import Path
            HERE = Path(__file__).resolve().parent
            BASE_DIR = Path(__file__).parent.parent
            """
        ).strip() + "\n"
        rewritten = _rewrite_repo_root_assignments(source)
        self.assertIn(
            f'HERE = os.environ.get("{REPO_ROOT_ENV}", "{WORKSPACE_DIR}")',
            rewritten,
        )
        self.assertIn(
            f'BASE_DIR = os.environ.get("{REPO_ROOT_ENV}", "{WORKSPACE_DIR}")',
            rewritten,
        )
        self.assertIn("import os", rewritten)
        self.assertIn("from pathlib import Path", rewritten)

    def test_rewrite_skips_hardcoded_paths(self) -> None:
        source = textwrap.dedent(
            """
            REPO_ROOT = "/explicit/path"
            DATA_DIR = "data"
            """
        ).strip() + "\n"
        rewritten = _rewrite_repo_root_assignments(source)
        self.assertIn('REPO_ROOT = "/explicit/path"', rewritten)
        self.assertNotIn("AST_PILOT_REPO_ROOT", rewritten)

    def test_rewrite_skips_non_anchor_names(self) -> None:
        source = "CONFIG_PATH = os.path.dirname(os.path.abspath(__file__))\n"
        rewritten = _rewrite_repo_root_assignments(source)
        self.assertEqual(source, rewritten)

    def test_rewrite_preserves_function_scope_assignments(self) -> None:
        source = textwrap.dedent(
            """
            def find_root():
                REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
                return REPO_ROOT
            """
        ).strip() + "\n"
        rewritten = _rewrite_repo_root_assignments(source)
        self.assertEqual(source, rewritten)

    def test_rewrite_adds_os_import_when_missing(self) -> None:
        source = textwrap.dedent(
            """
            \"\"\"Module docstring.\"\"\"
            from pathlib import Path
            REPO_ROOT = Path(__file__).resolve().parent
            """
        ).strip() + "\n"
        rewritten = _rewrite_repo_root_assignments(source)
        self.assertIn("import os", rewritten)
        # os import comes after the docstring, not before it
        self.assertLess(
            rewritten.index('"""'), rewritten.index("import os"),
        )

    def test_generated_task_py_emits_v2_pytest_grader(self) -> None:
        """The generated task wires a pytest_grader call that carries the
        test filename — the scenario's ``_build_grader_command`` re-materialises
        the test script into /tmp at grade time. In v1 the task.py template
        also emitted ``AST_PILOT_REPO_ROOT={workdir} PYTHONPATH=...`` directly;
        that command-building is now scenario-side."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                "[project]\nname='demo'\nversion='0.1.0'\n",
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "app" / "target.py"
            source_path.write_text("def run(): return 1\n", encoding="utf-8")

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                "from app.target import run\n\ndef test_run(): assert run() == 1\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )
            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )
            task_py = files["tasks/target-task/task.py"]
            self.assertIn("pytest_grader('test_target.py', task_file=__file__, weight=1.0)", task_py)
            self.assertIn('SCENARIO_ID = "ast-pilot:coding-task-v2"', task_py)
            # scenario-side machinery: not in the task.py template anymore.
            self.assertNotIn(REPO_ROOT_ENV, task_py)
            self.assertNotIn("PYTHONPATH=", task_py)

    @unittest.skip(
        "v2 has no dedicated assets path yet — bundled assets (e.g. schema.sql) "
        "currently land in support/ and flow through load_support, which stages "
        "to /opt/task_support. Needs an `assets` scenario arg + helper before "
        "tasks that open() workspace-relative files can run under v2."
    )
    def test_generated_task_py_stages_bundled_assets(self) -> None:  # pragma: no cover
        pass

    def test_generated_task_py_does_not_emit_v1_asset_helpers(self) -> None:
        """v2 task.py has no bundled-asset machinery — the scenario side owns
        all staging. This test pins the absence so a v1-style regression is
        caught immediately."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                "[project]\nname='demo'\nversion='0.1.0'\n",
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "app" / "target.py"
            source_path.write_text("def run(): return 1\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                "from app.target import run\n\ndef test_run(): assert run() == 1\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )
            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )
            task_py = files["tasks/target-task/task.py"]
            self.assertNotIn("BUNDLED_ASSETS", task_py)
            self.assertNotIn("_stage_runtime_assets", task_py)
            self.assertNotIn("stage_assets", task_py)

    def test_rewrite_applies_inside_generated_test_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                "[project]\nname='demo'\nversion='0.1.0'\n",
                encoding="utf-8",
            )
            (root / "schema.sql").write_text("CREATE TABLE t (id);\n", encoding="utf-8")
            (root / "app").mkdir()
            (root / "app" / "__init__.py").write_text("", encoding="utf-8")
            source_path = root / "app" / "target.py"
            source_path.write_text("def run(): return 1\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    import os
                    from app.target import run

                    REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

                    def test_schema_exists():
                        with open(os.path.join(REPO_ROOT, "schema.sql")) as f:
                            assert f.read()
                    """
                ).strip() + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )
            files = generate_graders(
                ev,
                output_dir=root / "output",
                prompt_md="# target-task\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )
            rewritten_test = files["tasks/target-task/tests/test_target.py"]
            self.assertIn(
                f'REPO_ROOT = os.environ.get("{REPO_ROOT_ENV}", "{WORKSPACE_DIR}")',
                rewritten_test,
            )
            self.assertNotIn("os.path.abspath(__file__)", rewritten_test)

    def test_bundle_fails_when_evidence_source_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ev = Evidence(
                project_name="target-task",
                source_files=[ModuleInfo(path=str(root / "missing.py"), module_name="missing")],
            )

            with self.assertRaisesRegex(ValueError, "Missing source path"):
                generate_graders(
                    ev,
                    output_dir=root / "output",
                    prompt_md="# target-task\n",
                )

    def test_src_package_is_not_treated_as_import_root(self) -> None:
        """When ``src/__init__.py`` exists, ``src`` is a package — not an
        import root. Tests doing ``from src.X import Y`` must be
        recognised so the support/shim layer covers them."""

        from ast_pilot.repo_support import discover_import_roots

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "nested"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "__init__.py").write_text("", encoding="utf-8")
            (src_dir / "models.py").write_text(
                "class User:\n    pass\n", encoding="utf-8"
            )

            roots = discover_import_roots(root)
            self.assertNotIn(src_dir.resolve(), roots)

    def test_true_src_layout_still_treats_src_as_import_root(self) -> None:
        """Classic src-layout (``src/`` without ``__init__.py``) should
        keep ``src/`` as an import root so ``src/mypkg/foo.py`` resolves
        to module ``mypkg.foo``."""

        from ast_pilot.repo_support import discover_import_roots

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "classic"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "src" / "mypkg"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

            roots = discover_import_roots(root)
            self.assertIn((root / "src").resolve(), roots)

    def test_src_layout_generates_task_without_unsupported_refs_error(self) -> None:
        """End-to-end regression for the vendor report: a repo whose
        tests import ``from src.models import User`` and whose
        ``src/__init__.py`` exists must bundle successfully."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "src-nested"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "__init__.py").write_text("", encoding="utf-8")
            (src_dir / "helpers.py").write_text(
                "def upper_case(text):\n    return text.upper()\n",
                encoding="utf-8",
            )
            source_path = src_dir / "models.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    from src.helpers import upper_case


                    class User:
                        def __init__(self, name):
                            self.name = upper_case(name)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_models.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from src.models import User


                    def test_user_uppercases_name():
                        assert User("alice").name == "ALICE"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="src-nested",
            )

            out_dir = root / "out"
            generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# stub\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            rewritten_test = (
                out_dir / "tasks" / "src-nested" / "tests" / "test_models.py"
            ).read_text(encoding="utf-8")
            self.assertIn("from src.models import User", rewritten_test)

            support_files = sorted(
                p.relative_to(out_dir / "tasks" / "src-nested" / "support")
                for p in (out_dir / "tasks" / "src-nested" / "support").rglob("*.py")
            )
            self.assertIn(Path("src/helpers.py"), support_files)
            # ``src/__init__.py`` is intentionally skipped — ``src`` must
            # stay a PEP 420 namespace package so workspace + support
            # merge onto one import root for ``src.models`` + ``src.helpers``.
            self.assertNotIn(Path("src/__init__.py"), support_files)

    def test_golden_file_rewrites_relative_imports_to_absolute(self) -> None:
        """``from .helpers import X`` in source files must be rewritten
        to ``from pkg.helpers import X`` in the golden — otherwise the
        flattened workspace copy can't resolve the relative reference."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "rel-imports"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "mypkg"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "helpers.py").write_text(
                "def upper(s):\n    return s.upper()\n",
                encoding="utf-8",
            )
            source_path = pkg_dir / "models.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    from .helpers import upper


                    class User:
                        def __init__(self, name):
                            self.name = upper(name)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_models.py"
            test_path.write_text(
                "from mypkg.models import User\n\n"
                "def test_user(): assert User('a').name == 'A'\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="rel-imports",
            )

            out_dir = root / "out"
            generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# stub\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            golden = (
                out_dir / "tasks" / "rel-imports" / "golden" / "mypkg" / "models.py"
            ).read_text(encoding="utf-8")
            self.assertIn("from mypkg.helpers import upper", golden)
            self.assertNotIn("from .helpers import upper", golden)

    def test_golden_preserves_from_dot_import_name(self) -> None:
        """``from . import sub`` (bare relative) should still be
        rewritten to reference the full package."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "bare-rel"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "mypkg"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "sub.py").write_text(
                "value = 1\n", encoding="utf-8"
            )
            source_path = pkg_dir / "facade.py"
            source_path.write_text(
                "from . import sub\n\n"
                "def get_value():\n"
                "    return sub.value\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_facade.py"
            test_path.write_text(
                "from mypkg.facade import get_value\n\n"
                "def test_value(): assert get_value() == 1\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="bare-rel",
            )

            out_dir = root / "out"
            generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# stub\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            golden = (
                out_dir / "tasks" / "bare-rel" / "golden" / "mypkg" / "facade.py"
            ).read_text(encoding="utf-8")
            self.assertIn("from mypkg import sub", golden)

    def test_golden_leaves_absolute_imports_untouched(self) -> None:
        """Absolute imports in source files must not be rewritten —
        only relative (``from .X``) ones."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "abs-imports"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "mypkg"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "helpers.py").write_text(
                "def upper(s): return s.upper()\n", encoding="utf-8"
            )
            source_path = pkg_dir / "models.py"
            source_path.write_text(
                "from mypkg.helpers import upper\n\n"
                "def uppercase(s): return upper(s)\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_models.py"
            test_path.write_text(
                "from mypkg.models import uppercase\n\n"
                "def test_it(): assert uppercase('x') == 'X'\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="abs-imports",
            )

            out_dir = root / "out"
            generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# stub\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            golden = (
                out_dir / "tasks" / "abs-imports" / "golden" / "mypkg" / "models.py"
            ).read_text(encoding="utf-8")
            self.assertIn("from mypkg.helpers import upper", golden)

    def test_nested_package_preserves_workspace_rel_path(self) -> None:
        """Source file inside a repo-internal package must be staged at
        its nested path (``agent/retry_utils.py``) in both golden/ and at
        grading time — hidden tests keep their original
        ``from agent.retry_utils import …`` unchanged."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "nested-pkg"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "agent"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            source_path = pkg_dir / "retry_utils.py"
            source_path.write_text(
                "def jittered_backoff(attempt: int) -> float:\n"
                "    return 1.0 * attempt\n",
                encoding="utf-8",
            )
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_retry.py"
            test_path.write_text(
                "from agent.retry_utils import jittered_backoff\n\n"
                "def test_backoff():\n"
                "    assert jittered_backoff(2) == 2.0\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="nested-pkg",
            )

            out_dir = root / "out"
            files = generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# nested-pkg\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            # Golden lives at its nested workspace path.
            self.assertIn("tasks/nested-pkg/golden/agent/retry_utils.py", files)
            # No shim under support/ — the module is at the real workspace path.
            self.assertNotIn("tasks/nested-pkg/support/agent/retry_utils.py", files)

            # Test file keeps its original import — no flat rewrite.
            rewritten_test = files["tasks/nested-pkg/tests/test_retry.py"]
            self.assertIn("from agent.retry_utils import jittered_backoff", rewritten_test)
            self.assertNotIn("from retry_utils import jittered_backoff", rewritten_test)

            # task.validation stages golden into its nested workspace path.
            # golden_validation() walks golden/ at task-import time and emits
            # one base64-inlined bash MCPToolCall — load the module and check
            # the rendered command contains the exact workspace path.
            (out_dir / ".hud").mkdir()
            (out_dir / ".hud" / "config.json").write_text(
                '{"registryName": "nested-env"}', encoding="utf-8"
            )
            module = _load_generated_task_module(out_dir / "tasks" / "nested-pkg")
            self.assertEqual(len(module.task.validation), 1)
            command = module.task.validation[0].arguments["command"]
            self.assertIn("mkdir -p /home/ubuntu/workspace/agent", command)
            self.assertIn("/home/ubuntu/workspace/agent/retry_utils.py", command)
            self.assertIn("base64 -d >", command)

    def test_nested_package_skips_init_py_for_overlap_packages(self) -> None:
        """When the agent's target lives inside a package that also has
        hidden support files (e.g. ``pkg/helpers.py``), the bundler must
        skip ``pkg/__init__.py`` so ``pkg`` remains a PEP 420 namespace
        package. Otherwise Python treats ``pkg`` as a regular package
        rooted in support/ and refuses to see the workspace-written
        ``pkg/<target>.py``."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "ns-pkg"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            pkg_dir = root / "pkg"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "helpers.py").write_text(
                "def double(x: int) -> int:\n    return x * 2\n",
                encoding="utf-8",
            )
            source_path = pkg_dir / "calc.py"
            source_path.write_text(
                "from pkg.helpers import double\n\n"
                "def add_then_double(a, b):\n    return double(a + b)\n",
                encoding="utf-8",
            )
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_calc.py"
            test_path.write_text(
                "from pkg.calc import add_then_double\n\n"
                "def test_it(): assert add_then_double(2, 3) == 10\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="ns-pkg",
            )

            out_dir = root / "out"
            files = generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# ns-pkg\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            # Helpers shipped; __init__.py intentionally skipped so the
            # package remains a namespace package and merges the
            # agent-written pkg/calc.py from the workspace with
            # pkg/helpers.py from the support tree.
            self.assertIn("tasks/ns-pkg/support/pkg/helpers.py", files)
            self.assertNotIn("tasks/ns-pkg/support/pkg/__init__.py", files)
            # Target is not shimmed under support/.
            self.assertNotIn("tasks/ns-pkg/support/pkg/calc.py", files)

    def test_flat_source_still_writes_flat_golden(self) -> None:
        """Single-file scan (source at repo root) keeps the old flat
        behavior — the workspace target is just ``<basename>.py``."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "flat-pkg"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            source_path = root / "foo.py"
            source_path.write_text("def add(a, b): return a + b\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_foo.py"
            test_path.write_text(
                "from foo import add\n\ndef test_add(): assert add(2, 3) == 5\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="flat-pkg",
            )

            out_dir = root / "out"
            files = generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# flat-pkg\n",
                source_paths=[source_path],
                test_paths=[test_path],
            )

            self.assertIn("tasks/flat-pkg/golden/foo.py", files)
            self.assertNotIn("tasks/flat-pkg/golden/agent/foo.py", files)
            # task.validation stages flat golden at its workspace path.
            (out_dir / ".hud").mkdir()
            (out_dir / ".hud" / "config.json").write_text(
                '{"registryName": "flat-env"}', encoding="utf-8"
            )
            module = _load_generated_task_module(out_dir / "tasks" / "flat-pkg")
            self.assertEqual(len(module.task.validation), 1)
            command = module.task.validation[0].arguments["command"]
            self.assertIn("/home/ubuntu/workspace/foo.py", command)
            self.assertIn("base64 -d >", command)

    def test_prepend_syspath_imports_sys_before_using_it(self) -> None:
        """`import sys` must appear before `sys.path.insert(...)` even when an
        existing `import sys` lives later in the file.

        Regression: earlier logic stripped `import sys` from the injected
        header whenever it saw one anywhere in the first 10 lines, but the
        injection point sits right after `from __future__ ...` — which can be
        above the existing import. That made the test module NameError on
        load (`sys` not yet bound).
        """
        original = (
            '"""docstring"""\n\n'
            "from __future__ import annotations\n\n"
            "import sys\n"
            "import os\n\n\n"
            "def test_x():\n"
            "    pass\n"
        )
        rewritten = _prepend_workspace_syspath(original)
        lines = rewritten.splitlines()
        sys_import_line = next(
            i for i, line in enumerate(lines) if line.strip() == "import sys"
        )
        syspath_line = next(
            i
            for i, line in enumerate(lines)
            if f'sys.path.insert(0, "{WORKSPACE_DIR}")' in line
        )
        self.assertLess(
            sys_import_line,
            syspath_line,
            "import sys must be bound before sys.path.insert runs; "
            f"got order:\n{rewritten}",
        )

    def test_overlap_package_init_with_real_code_is_bundled_with_path_extension(self) -> None:
        """Regression: an overlap-package __init__.py with real module-level
        code (constants, exports, side-effect imports) used to be dropped
        wholesale, breaking transitive `from pkg import CONSTANT` imports
        from support modules. Now we bundle it with a __path__.append(...)
        preamble so the workspace's pkg/<target>.py is still merged into
        the package.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "src-pkg"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            src_pkg = root / "src"
            src_pkg.mkdir()
            (src_pkg / "__init__.py").write_text(
                '"""Top-level package init with a real constant."""\n'
                'SRC_VERSION = "1.2.3"\n',
                encoding="utf-8",
            )
            utils_pkg = src_pkg / "utils"
            utils_pkg.mkdir()
            (utils_pkg / "__init__.py").write_text(
                "from src import SRC_VERSION\n"
                "def helper(): return f'helper@{SRC_VERSION}'\n",
                encoding="utf-8",
            )
            cov_pkg = src_pkg / "coverage"
            cov_pkg.mkdir()
            target = cov_pkg / "__init__.py"
            target.write_text(
                "from src.utils import helper\n"
                "def coverage_fn(): return f'coverage/{helper()}'\n",
                encoding="utf-8",
            )
            tests = root / "tests"
            tests.mkdir()
            test_file = tests / "test_cov.py"
            test_file.write_text(
                "from src.coverage import coverage_fn\n"
                "def test(): assert coverage_fn() == 'coverage/helper@1.2.3'\n",
                encoding="utf-8",
            )

            ev = scan(source_paths=[target], test_paths=[test_file], project_name="src-pkg")
            out_dir = root / "out"
            files = generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md="# src-pkg\n",
                source_paths=[target],
                test_paths=[test_file],
            )

            self.assertIn("tasks/src-pkg/support/src/__init__.py", files)
            bundled_init = files["tasks/src-pkg/support/src/__init__.py"]
            # Original constant must survive bundling.
            self.assertIn('SRC_VERSION = "1.2.3"', bundled_init)
            # __path__ extension must allow the workspace pkg dir to merge.
            self.assertIn(
                f"__path__.append('{WORKSPACE_DIR}/src')",
                bundled_init,
            )

            # End-to-end: stage golden + support into a fake workspace and
            # confirm the import chain actually resolves at runtime.
            import subprocess
            workspace = root / "_workspace"
            workspace.mkdir()
            for path in (out_dir / "tasks" / "src-pkg" / "golden").rglob("*"):
                if path.is_file():
                    rel = path.relative_to(out_dir / "tasks" / "src-pkg" / "golden")
                    dest = workspace / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
            support_root = out_dir / "tasks" / "src-pkg" / "support"
            for path in support_root.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(support_root)
                    dest = workspace / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
            # Rewrite the WORKSPACE_DIR placeholder in bundled __init__ to
            # point at our test workspace, since the test isn't running at
            # /home/ubuntu/workspace.
            for init_path in workspace.rglob("__init__.py"):
                txt = init_path.read_text(encoding="utf-8")
                if WORKSPACE_DIR in txt:
                    init_path.write_text(
                        txt.replace(WORKSPACE_DIR, str(workspace)),
                        encoding="utf-8",
                    )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from src.coverage import coverage_fn\n"
                    "assert coverage_fn() == 'coverage/helper@1.2.3'\n",
                ],
                cwd=workspace,
                env={"PYTHONPATH": str(workspace), "PATH": ""},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )

    def test_prepend_syspath_skips_existing_workspace_insert_double_quotes(self) -> None:
        """If the file already has the canonical workspace insert with double
        quotes, don't prepend a second one."""
        original = (
            "import sys\n"
            f'sys.path.insert(0, "{WORKSPACE_DIR}")\n\n'
            "from foo import bar\n"
        )
        self.assertEqual(_prepend_workspace_syspath(original), original)

    def test_prepend_syspath_skips_existing_workspace_insert_single_quotes(self) -> None:
        """The dedupe regex must match either quote style."""
        original = (
            "import sys\n"
            f"sys.path.insert(0, '{WORKSPACE_DIR}')\n\n"
            "from foo import bar\n"
        )
        self.assertEqual(_prepend_workspace_syspath(original), original)

    def test_prepend_syspath_overrides_unrelated_insert_with_workspace_in_docstring(self) -> None:
        """Regression: the previous predicate was a substring check —
        WORKSPACE_DIR appearing in a docstring AND any sys.path.insert(...) in
        the file would skip the prepend entirely, leaving the test running
        without the workspace on sys.path[0]. The dedupe must require the
        EXACT canonical insert, not just a substring co-occurrence."""
        original = (
            f'"""Test workspace at {WORKSPACE_DIR} — note pre-existing path manipulation."""\n'
            "import sys\n"
            'sys.path.insert(0, "/tmp/extra")\n\n'
            "from foo import fn\n"
            "def test_fn():\n"
            "    assert fn() == 'foo'\n"
        )
        rewritten = _prepend_workspace_syspath(original)
        self.assertNotEqual(rewritten, original)
        self.assertIn(f'sys.path.insert(0, "{WORKSPACE_DIR}")', rewritten)
        # The workspace insert must precede the unrelated insert so it wins
        # the sys.path[0] slot.
        ws_idx = rewritten.index(f'"{WORKSPACE_DIR}"')
        other_idx = rewritten.index('"/tmp/extra"')
        self.assertLess(ws_idx, other_idx)

    def test_detect_cross_module_path_access_flags_parents_subscript(self) -> None:
        source = textwrap.dedent(
            """
            from pathlib import Path
            def test_reads_sibling():
                path = Path(__file__).resolve().parents[2] / "gateway" / "run.py"
                assert path.exists()
            """
        ).strip() + "\n"
        warnings, marks = _detect_cross_module_path_access(source, Path("test_foo.py"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("test_foo.py", warnings[0])
        self.assertIn("parents[2]", warnings[0])
        self.assertEqual(len(marks), 1)
        lineno, reason = marks[0]
        self.assertIn("parents[2]", reason)
        # Mark points at the `def test_reads_sibling` line (2nd non-blank line).
        self.assertEqual(source.splitlines()[lineno - 1].strip(), "def test_reads_sibling():")

    def test_detect_cross_module_path_access_flags_unresolved_parents(self) -> None:
        source = textwrap.dedent(
            """
            from pathlib import Path
            def test_reads_sibling():
                path = Path(__file__).parents[1] / "data.json"
            """
        ).strip() + "\n"
        warnings, marks = _detect_cross_module_path_access(source, Path("test_bar.py"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("parents[1]", warnings[0])
        self.assertEqual(len(marks), 1)

    def test_detect_cross_module_path_access_ignores_parent_without_subscript(self) -> None:
        source = textwrap.dedent(
            """
            from pathlib import Path
            HERE = Path(__file__).parent
            def test_ok():
                pass
            """
        ).strip() + "\n"
        warnings, marks = _detect_cross_module_path_access(source, Path("test_baz.py"))
        self.assertEqual(warnings, [])
        self.assertEqual(marks, [])

    def test_detect_cross_module_path_access_ignores_parents_without_dunder_file(self) -> None:
        source = textwrap.dedent(
            """
            from pathlib import Path
            def test_arbitrary():
                p = Path('/some/where').parents[1]
            """
        ).strip() + "\n"
        warnings, marks = _detect_cross_module_path_access(source, Path("test_qux.py"))
        self.assertEqual(warnings, [])
        self.assertEqual(marks, [])

    def test_insert_skip_marks_prepends_pytest_skip(self) -> None:
        source = textwrap.dedent(
            """
            class TestSomething:
                def test_reads_sibling(self):
                    path = Path(__file__).resolve().parents[2] / "gateway" / "run.py"
                    assert path.exists()
            """
        ).strip() + "\n"
        warnings, marks = _detect_cross_module_path_access(source, Path("test_x.py"))
        rewritten = _insert_skip_marks(source, marks)
        self.assertIn('@__import__("pytest").mark.skip', rewritten)
        self.assertIn("parents[2]", rewritten)
        # Decorator must sit directly above the test method, preserving indentation.
        decorator_line = next(
            line for line in rewritten.splitlines() if "pytest" in line and "skip" in line
        )
        self.assertTrue(decorator_line.startswith("    @"))

    def _build_cross_module_test_repo(self, root: Path) -> tuple[Path, Path]:
        (root / "pyproject.toml").write_text(
            "[project]\nname='demo'\nversion='0.1.0'\n",
            encoding="utf-8",
        )
        (root / "app").mkdir()
        (root / "app" / "__init__.py").write_text("", encoding="utf-8")
        source_path = root / "app" / "target.py"
        source_path.write_text("def run(): return 1\n", encoding="utf-8")

        tests_dir = root / "tests"
        tests_dir.mkdir()
        test_path = tests_dir / "test_target.py"
        test_path.write_text(
            textwrap.dedent(
                """
                from pathlib import Path
                from app.target import run

                def test_run(): assert run() == 1

                def test_reads_sibling():
                    p = Path(__file__).resolve().parents[2] / "other" / "file.py"
                    assert p.exists()
                """
            ).strip() + "\n",
            encoding="utf-8",
        )
        return source_path, test_path

    def test_cross_module_test_hard_fails_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path, test_path = self._build_cross_module_test_repo(root)
            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )
            with self.assertRaisesRegex(ValueError, r"Path\(__file__\)\.parents"):
                generate_graders(
                    ev,
                    output_dir=root / "out",
                    prompt_md="# demo\n",
                    source_paths=[source_path],
                    test_paths=[test_path],
                )

    def test_cross_module_test_auto_skipped_when_env_var_allows(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path, test_path = self._build_cross_module_test_repo(root)
            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="target-task",
            )
            prev = os.environ.get("AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS")
            os.environ["AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS"] = "1"
            try:
                files = generate_graders(
                    ev,
                    output_dir=root / "out",
                    prompt_md="# demo\n",
                    source_paths=[source_path],
                    test_paths=[test_path],
                )
            finally:
                if prev is None:
                    os.environ.pop("AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS", None)
                else:
                    os.environ["AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS"] = prev
            rewritten_test = files["tasks/target-task/tests/test_target.py"]
            self.assertIn('@__import__("pytest").mark.skip', rewritten_test)
            self.assertIn("parents[2]", rewritten_test)
            # The plain passing test must NOT be decorated.
            lines = rewritten_test.splitlines()
            idx_passing = next(
                i for i, line in enumerate(lines) if line.strip() == "def test_run(): assert run() == 1"
            )
            self.assertFalse(lines[idx_passing - 1].strip().startswith("@"))


if __name__ == "__main__":
    unittest.main()
