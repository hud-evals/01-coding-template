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
    _rewrite_repo_root_assignments,
    generate_graders,
)
from ast_pilot.scanner import scan


def _load_generated_task_module(task_dir: Path, env_vars: dict[str, str] | None = None):
    module_name = "_generated_task_under_test"
    task_path = task_dir / "task.py"

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

    repo_root = Path(__file__).resolve().parents[1]
    task_bootstrap_path = repo_root / "task_bootstrap.py"
    bootstrap_spec = importlib.util.spec_from_file_location(
        "task_bootstrap", task_bootstrap_path,
    )
    fake_task_bootstrap = importlib.util.module_from_spec(bootstrap_spec)
    assert bootstrap_spec is not None and bootstrap_spec.loader is not None
    bootstrap_spec.loader.exec_module(fake_task_bootstrap)

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
                "task_bootstrap": fake_task_bootstrap,
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

            golden = files["tasks/target-task/golden/target.py"]
            rewritten_test = files["tasks/target-task/tests/test_target.py"]
            task_py = files["tasks/target-task/task.py"]
            requirements = files["tasks/target-task/requirements.hidden.txt"]
            support_auth = files["tasks/target-task/support/helpers/auth.py"]
            support_prompt_caching = files["tasks/target-task/support/helpers/prompt_caching.py"]
            support_other_module = files["tasks/target-task/support/other_module.py"]
            support_shim = files["tasks/target-task/support/agent/target.py"]
            init_py = files["tasks/target-task/__init__.py"]

            self.assertIn("import helpers.auth as auth_mod", golden)
            self.assertIn("from target import run", rewritten_test)
            self.assertIn("other_module", rewritten_test)
            self.assertNotIn('@__import__("pytest").mark.xfail(', rewritten_test)
            self.assertNotIn("lambda *a, **kw", rewritten_test)
            self.assertIn("httpx>=0.28.0", requirements)
            self.assertIn("pyyaml>=6.0.0", requirements)
            self.assertIn('HELPER_VALUE = "ok"', support_auth)
            self.assertIn('return "cached"', support_prompt_caching)
            self.assertIn('return "sentinel"', support_other_module)
            self.assertIn("from target import *", support_shim)
            self.assertIn('IMAGE_TASK_DIR = Path("/mcp_server/tasks") / TASK_DIR.name', task_py)
            self.assertIn("LEGACY_SUPPORT_DIR = Path('/opt/ast_pilot_support') / TASK_DIR.name", task_py)
            self.assertIn("from task_bootstrap import require_hud_env_name", task_py)
            self.assertIn("ENV_NAME = require_hud_env_name(", task_py)
            self.assertIn('SCENARIO_ID = "ast-pilot:coding-task"', task_py)
            self.assertIn('BUNDLED_SUPPORT_DIR = IMAGE_TASK_DIR / "support"', task_py)
            self.assertIn('RUNTIME_ROOT = Path("/tmp/ast_pilot_task_runtime") / TASK_DIR.name', task_py)
            self.assertIn('WORKSPACE_DIR = "/home/ubuntu/workspace"', task_py)
            self.assertIn('LOCAL_HIDDEN_REQUIREMENTS = TASK_DIR / "requirements.hidden.txt"', task_py)
            self.assertIn('BUNDLED_HIDDEN_REQUIREMENTS = IMAGE_TASK_DIR / "requirements.hidden.txt"', task_py)
            self.assertIn("def _prepare_hidden_runtime(test_file: str, runtime_support_dir: Path) -> str:", task_py)
            self.assertIn('runtime_support_dir = RUNTIME_ROOT / Path(test_file).stem / "support"', task_py)
            self.assertIn("prepare = _prepare_hidden_runtime(test_file, runtime_support_dir)", task_py)
            self.assertIn('pythonpath = f"{WORKSPACE_DIR}:{runtime_support_dir}:$PYTHONPATH"', task_py)
            self.assertIn("HUD_ENV_NAME is required", task_py)
            self.assertIn("env = Environment(ENV_NAME)", task_py)
            self.assertNotIn("mario-claire", task_py)
            self.assertEqual(init_py, "")

            generated_task_dir = output_dir / "tasks" / "target-task"
            (output_dir / ".env").write_text("HUD_ENV_NAME=dotenv-env\n", encoding="utf-8")
            module = _load_generated_task_module(generated_task_dir)
            generated_command = module.task.args["bash_checks"][0]["command"]
            self.assertEqual(module.task.env.name, "dotenv-env")
            self.assertEqual(module.task.scenario, "ast-pilot:coding-task")
            self.assertIn("/mcp_server/tasks/target-task/support", generated_command)
            self.assertIn("/mcp_server/tasks/target-task/requirements.hidden.txt", generated_command)
            self.assertNotIn(str(root), generated_command)

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
            support_shim = files["tasks/target-task/support/agent/target.py"]

            self.assertIn("from target import run", rewritten_test)
            self.assertIn('return "auth"', support_auth)
            self.assertIn("from target import *", support_shim)
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

    def test_generated_task_py_passes_repo_root_env_var(self) -> None:
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
            self.assertIn(f'REPO_ROOT_ENV = "{REPO_ROOT_ENV}"', task_py)
            self.assertIn(
                f"{REPO_ROOT_ENV}={{workdir}} PYTHONPATH=",
                task_py,
            )

    def test_generated_task_py_stages_bundled_assets(self) -> None:
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
            source_path.write_text(
                "import sqlite3\n"
                "def run():\n"
                "    with open('schema.sql') as f:\n"
                "        return f.read()\n",
                encoding="utf-8",
            )
            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_target.py"
            test_path.write_text(
                "from app.target import run\n\ndef test_run(): run()\n",
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
            self.assertIn("BUNDLED_ASSETS = ['schema.sql']", task_py)
            self.assertIn("def _stage_runtime_assets(", task_py)
            self.assertIn("cp -n", task_py)
            self.assertIn("stage_assets = _stage_runtime_assets(", task_py)

    def test_generated_task_py_no_asset_helper_when_none_referenced(self) -> None:
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
            self.assertIn("BUNDLED_ASSETS = []", task_py)
            self.assertIn('stage_assets = ""', task_py)

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
            self.assertIn("from models import User", rewritten_test)

            support_files = sorted(
                p.relative_to(out_dir / "tasks" / "src-nested" / "support")
                for p in (out_dir / "tasks" / "src-nested" / "support").rglob("*.py")
            )
            self.assertIn(Path("src/helpers.py"), support_files)
            self.assertIn(Path("src/__init__.py"), support_files)

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
                out_dir / "tasks" / "rel-imports" / "golden" / "models.py"
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
                out_dir / "tasks" / "bare-rel" / "golden" / "facade.py"
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
                out_dir / "tasks" / "abs-imports" / "golden" / "models.py"
            ).read_text(encoding="utf-8")
            self.assertIn("from mypkg.helpers import upper", golden)


if __name__ == "__main__":
    unittest.main()
