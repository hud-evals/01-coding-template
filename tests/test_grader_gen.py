from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.grader_gen import generate_graders
from ast_pilot.scanner import scan


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
            self.assertIn("SUPPORT_DIR = Path('/opt/ast_pilot_support') / TASK_DIR.name", task_py)
            self.assertIn("pythonpath = f\"/home/ubuntu/workspace:{SUPPORT_DIR}:$PYTHONPATH\"", task_py)
            self.assertIn("HUD_ENV_NAME is required", task_py)
            self.assertIn("env = Environment(ENV_NAME)", task_py)
            self.assertNotIn("mario-claire", task_py)
            self.assertEqual(init_py, "")

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
                    source_paths=[source_path],
                    test_paths=[test_path],
                )


if __name__ == "__main__":
    unittest.main()
