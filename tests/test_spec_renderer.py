from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence, ModuleInfo, TestEvidence
from ast_pilot.scanner import scan
from ast_pilot.spec_renderer import _build_exact_api_listing, _build_test_facts, render_start_md


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
            self.assertIn("Create and edit the solution under `/home/ubuntu/workspace`", md)
            self.assertIn("Workspace-relative paths for hidden-test imports: `agent/target.py`.", md)
            self.assertIn("`pkg.support`", md)
            self.assertIn("No third-party runtime dependencies were detected", md)
            self.assertIn("agent/", md)
            self.assertIn("target.py", md)
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

    def test_prompt_lists_bundled_runtime_asset_in_runtime_files_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "store-task"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (root / "schema.sql").write_text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY);\n",
                encoding="utf-8",
            )

            source_path = root / "store.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    import sqlite3
                    from pathlib import Path


                    def init_db(db_path: str) -> sqlite3.Connection:
                        conn = sqlite3.connect(db_path)
                        conn.executescript(Path("schema.sql").read_text())
                        return conn
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_store.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from store import init_db


                    def test_init_db(tmp_path):
                        conn = init_db(str(tmp_path / "demo.db"))
                        assert conn is not None
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="store-task",
            )
            md = render_start_md(ev, use_llm=False)

            self.assertIn("## Runtime Files", md)
            self.assertIn("### Files already provided", md)
            self.assertIn("`/home/ubuntu/workspace/schema.sql`", md)
            self.assertIn("schema.sql (provided)", md)
            self.assertNotIn("### Files you must create", md)

    def test_prompt_lists_agent_created_asset_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "loader-task"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            source_path = root / "loader.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path


                    def load_config() -> str:
                        return Path("config.yaml").read_text()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_loader.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from loader import load_config


                    def test_load_config():
                        assert isinstance(load_config(), str)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="loader-task",
            )
            md = render_start_md(ev, use_llm=False)

            self.assertIn("## Runtime Files", md)
            self.assertIn("### Files you must create", md)
            self.assertIn("`/home/ubuntu/workspace/config.yaml`", md)
            self.assertIn("config.yaml (you create)", md)
            self.assertNotIn("### Files already provided", md)

    def test_exact_api_includes_private_constants(self) -> None:
        """Private constants like `_PREFIX_PATTERNS` must reach LLM grounding.

        Regression: earlier filter `not name.startswith("_")` silently stripped
        long private lists of regex prefixes, which then caused generated prompts
        to summarise the list as "and others" — the #1 source of agent misses.
        """
        mod = ModuleInfo(
            path="redact.py",
            module_name="redact",
            docstring=None,
            constants=[
                ("_REDACT_ENABLED", "True"),
                ("_PREFIX_PATTERNS", '[r"sk-[A-Za-z0-9_-]{10,}", r"ghp_[A-Za-z0-9]{10,}"]'),
            ],
        )
        ev = Evidence(source_files=[mod], tests=[], python_version="3.12")
        out = _build_exact_api_listing(ev)
        self.assertIn("_REDACT_ENABLED", out)
        self.assertIn("_PREFIX_PATTERNS", out)
        self.assertIn("sk-[A-Za-z0-9_-]", out)
        self.assertIn("ghp_[A-Za-z0-9]", out)

    def test_exact_api_dumps_long_constant_values_verbatim(self) -> None:
        """Long constant values must not be filtered out by a length cap.

        Regression: earlier `len(value) < 120` cap silently dropped exactly the
        kind of value the LLM needs most (multi-pattern regex tables, long
        default config objects).
        """
        long_value = "[" + ", ".join(f'r"prefix{i}_[A-Za-z0-9]{{10,}}"' for i in range(20)) + "]"
        self.assertGreater(len(long_value), 120)
        mod = ModuleInfo(
            path="redact.py",
            module_name="redact",
            constants=[("LONG_LIST", long_value)],
        )
        ev = Evidence(source_files=[mod], tests=[], python_version="3.12")
        out = _build_exact_api_listing(ev)
        self.assertIn("LONG_LIST", out)
        self.assertIn("prefix0_", out)
        self.assertIn("prefix19_", out)

    def test_test_facts_preserve_long_snippets(self) -> None:
        """Snippet truncation must not strip assertion literals late in the test body.

        Regression: earlier `[:500]` cut off expected output strings at the end
        of longer tests, forcing the LLM to guess them.
        """
        body = "\n".join([f'    assert result[{i}] == "literal_value_{i}_xyz"' for i in range(40)])
        snippet = f"def test_long():\n{body}\n"
        self.assertGreater(len(snippet), 500)
        test_ev = TestEvidence(
            test_file="test_long.py",
            test_name="test_long",
            tested_symbols=["foo"],
            source_snippet=snippet,
        )
        ev = Evidence(source_files=[], tests=[test_ev], python_version="3.12")
        facts = _build_test_facts(ev)
        self.assertIn("literal_value_0_xyz", facts)
        self.assertIn("literal_value_39_xyz", facts)

    def test_prompt_omits_runtime_files_section_when_no_assets_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "pure.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    def add(a: int, b: int) -> int:
                        return a + b
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            test_path = tests_dir / "test_pure.py"
            test_path.write_text(
                textwrap.dedent(
                    """
                    from pure import add


                    def test_add():
                        assert add(2, 3) == 5
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="pure-task",
            )
            md = render_start_md(ev, use_llm=False)

            self.assertNotIn("## Runtime Files", md)
            self.assertNotIn("(provided)", md)
            self.assertNotIn("(you create)", md)


if __name__ == "__main__":
    unittest.main()
