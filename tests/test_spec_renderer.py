from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.scanner import scan
from ast_pilot.spec_renderer import render_start_md


class SpecRendererTests(unittest.TestCase):
    def test_prompt_calls_out_workspace_private_symbols_and_internal_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    dependencies = []
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            (root / "agent").mkdir()
            (root / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "support.py").write_text(
                textwrap.dedent(
                    """
                    def helper_path() -> str:
                        return "/tmp/demo"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            source_path = root / "agent" / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    from __future__ import annotations

                    from pkg.support import helper_path


                    VALUE = "ready"


                    def _private_helper(text: str) -> str:
                        return text.upper()


                    def public_fn(value: str) -> str:
                        helper_path()
                        return _private_helper(value)
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
                    from agent.target import _private_helper, public_fn


                    def test_public_fn():
                        assert public_fn("hello") == "HELLO"


                    def test_private_helper():
                        assert _private_helper("world") == "WORLD"
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
            md = render_start_md(ev, use_llm=False)

            self.assertIn("## Required Tested Symbols", md)
            self.assertIn("def _private_helper(text: str) -> str", md)
            self.assertIn("Create and edit the solution directly in `/home/ubuntu/workspace`.", md)
            self.assertIn("Hidden tests import the solution as top-level module file(s): `target.py`.", md)
            self.assertIn("`pkg.support`", md)
            self.assertIn("No third-party runtime dependencies were detected", md)
            self.assertIn("├── target.py", md)
            self.assertNotIn("__future__", md)

    def test_exact_api_preserves_positional_only_and_keyword_only_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "target.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    def exact(value: str, /, scale: int = 1, *, mode: str = "strict") -> str:
                        return f"{value}:{scale}:{mode}"
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
                    from target import exact


                    def test_exact():
                        assert exact("hello", mode="strict") == "hello:1:strict"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(source_paths=[source_path], test_paths=[test_path], project_name="target-task")
            md = render_start_md(ev, use_llm=False)

            self.assertIn(
                'def exact(value: str, /, scale: int = 1, *, mode: str = "strict") -> str',
                md,
            )


if __name__ == "__main__":
    unittest.main()
