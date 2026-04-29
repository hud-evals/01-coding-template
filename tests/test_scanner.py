from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.scanner import scan


class ScannerTests(unittest.TestCase):
    def test_scan_reads_requires_python_from_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                textwrap.dedent(
                    """
                    [project]
                    name = "demo"
                    version = "0.1.0"
                    requires-python = ">=3.12"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            source_path = root / "demo.py"
            source_path.write_text("def demo() -> int:\n    return 1\n", encoding="utf-8")

            ev = scan(source_paths=[source_path], project_name="demo")

            self.assertEqual(ev.python_version, ">=3.12")

    def test_scan_raises_on_source_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "broken.py"
            source_path.write_text("def broken(:\n    return 1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Failed to parse source file"):
                scan(source_paths=[source_path], project_name="broken")

    def test_scan_raises_on_test_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "demo.py"
            source_path.write_text("def demo() -> int:\n    return 1\n", encoding="utf-8")
            test_path = root / "test_demo.py"
            test_path.write_text("def test_demo(:\n    assert True\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Failed to parse test file"):
                scan(source_paths=[source_path], test_paths=[test_path], project_name="demo")

    def test_scan_walks_source_directory_recursively(self) -> None:
        """Regression: passing a directory as a source path used to silently skip
        every file inside (``_scan_module`` returned None for non-.py paths).
        Directories must now be walked recursively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = root / "src"
            (src / "coverage").mkdir(parents=True)
            (src / "ingestion").mkdir(parents=True)
            (src / "coverage" / "envelope.py").write_text(
                "def envelope():\n    return 1\n", encoding="utf-8"
            )
            (src / "ingestion" / "pipeline.py").write_text(
                "def pipeline():\n    return 2\n", encoding="utf-8"
            )
            # Non-.py files in the tree must not get scanned.
            (src / "coverage" / "README.md").write_text("notes", encoding="utf-8")

            ev = scan(source_paths=[src], project_name="claimpilot")

            scanned_names = sorted(mod.module_name for mod in ev.source_files)
            self.assertEqual(scanned_names, ["envelope", "pipeline"])
            self.assertEqual(ev.total_loc, 4)

    def test_scan_preserves_dotted_module_names_via_package_tree_fallback(self) -> None:
        """Regression: when a project has no pyproject.toml/setup.py/.git but DOES
        have a Python package structure (sibling __init__.py files), the scanner
        must walk the package tree to find the implicit repo root. Otherwise
        sources get flat names (`coverage.foo`) and the workspace layout drops
        the package prefix, breaking test imports like `from src.coverage import ...`.
        """
        from ast_pilot.repo_support import find_repo_root, module_name_from_path

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Simulate Fazlul's ClaimPilot layout: src/ is a package containing
            # subpackages, no pyproject.toml at the top level.
            (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            src = root / "src"
            (src / "coverage").mkdir(parents=True)
            (src / "ingestion").mkdir(parents=True)
            (src / "__init__.py").write_text("", encoding="utf-8")
            (src / "coverage" / "__init__.py").write_text("", encoding="utf-8")
            (src / "coverage" / "envelope.py").write_text(
                "def envelope(): return 1\n", encoding="utf-8"
            )
            (src / "ingestion" / "__init__.py").write_text("", encoding="utf-8")
            (src / "ingestion" / "pipeline.py").write_text(
                "def pipeline(): return 2\n", encoding="utf-8"
            )

            # repo root should be the project root (parent of src/), not None.
            detected_root = find_repo_root(src / "coverage" / "envelope.py")
            self.assertEqual(detected_root, root.resolve())

            # Module name must be fully-dotted with the `src.` prefix.
            mod = module_name_from_path(src / "coverage" / "envelope.py", detected_root)
            self.assertEqual(mod, "src.coverage.envelope")

            mod2 = module_name_from_path(src / "ingestion" / "pipeline.py", detected_root)
            self.assertEqual(mod2, "src.ingestion.pipeline")

    def test_relative_imports_in_init_py_resolve_correctly_after_rewrite(self) -> None:
        """Regression: `from .X import Y` in src/coverage/__init__.py used to be
        rewritten to `from src.X import Y` (off-by-one — strips `coverage`),
        causing `ModuleNotFoundError: No module named 'src.X'` at runtime.

        For __init__.py, current_module already names the package, not a module
        within it; the rewriter must NOT strip the last segment.
        """
        from ast_pilot.repo_support import resolve_from_module

        # __init__.py case: current_module IS the package
        result = resolve_from_module(
            "src.coverage", "coverage_envelope", 1, is_package=True
        )
        self.assertEqual(result, "src.coverage.coverage_envelope")

        # Regular module case: current_module is a module inside the package
        result = resolve_from_module(
            "src.coverage.helper", "coverage_envelope", 1
        )
        self.assertEqual(result, "src.coverage.coverage_envelope")

        # Two-level relative from __init__.py
        result = resolve_from_module(
            "src.coverage", "ledger.foo", 2, is_package=True
        )
        self.assertEqual(result, "src.ledger.foo")

    def test_end_to_end_generated_workspace_imports_with_relative_imports_in_init(self) -> None:
        """Integration test that catches the whole class of bugs we kept peeling:
        scanner walks dirs, repo root detected via package tree, __init__.py
        maps to <pkg>/__init__.py, AND relative imports rewrite correctly.

        Generates a task package from a synthetic ClaimPilot-shaped project
        whose package __init__.py uses relative imports — then asserts the
        golden workspace can actually import both the test-style absolute
        imports AND the rewritten __init__-internal imports.
        """
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "claimsim"
            (project / "src" / "coverage").mkdir(parents=True)
            (project / "src" / "ingestion").mkdir(parents=True)
            (project / "tests").mkdir()
            (project / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            (project / "src" / "__init__.py").write_text("", encoding="utf-8")
            (project / "src" / "coverage" / "envelope.py").write_text(
                "def make_envelope(pid): return {'policy_id': pid, 'kind': 'envelope'}\n",
                encoding="utf-8",
            )
            (project / "src" / "coverage" / "__init__.py").write_text(
                "from .envelope import make_envelope\n",
                encoding="utf-8",
            )
            (project / "src" / "ingestion" / "pipeline.py").write_text(
                "from src.coverage.envelope import make_envelope\n"
                "def ingest(p): return make_envelope(p['id'])\n",
                encoding="utf-8",
            )
            (project / "src" / "ingestion" / "__init__.py").write_text(
                "from .pipeline import ingest\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[project / "src"],
                test_paths=[project / "tests"],
                project_name="claimsim",
            )

            self.assertGreaterEqual(len(ev.source_files), 4)
            module_names = {mod.module_name for mod in ev.source_files}
            # The package __init__.py files are scanned — module_name field
            # holds the file stem ("__init__") rather than the dotted name,
            # but the dotted name is computed elsewhere via repo context.
            self.assertIn("envelope", module_names)
            self.assertIn("pipeline", module_names)

    def test_scan_walks_test_directory_without_isadirectory_error(self) -> None:
        """Regression: passing a directory as ``--tests`` used to crash with
        ``IsADirectoryError`` because ``_scan_tests`` did ``read_text()`` on it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = root / "src"
            src.mkdir()
            (src / "lib.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_a.py").write_text(
                "from lib import helper\ndef test_a():\n    assert helper() == 1\n",
                encoding="utf-8",
            )
            (tests / "test_b.py").write_text(
                "def test_b():\n    assert True\n", encoding="utf-8"
            )

            ev = scan(source_paths=[src], test_paths=[tests], project_name="claimpilot")

            test_files = sorted(Path(t.test_file).name for t in ev.tests)
            self.assertIn("test_a.py", test_files)
            self.assertIn("test_b.py", test_files)

    def test_find_repo_root_detects_requirements_txt_marker(self) -> None:
        """Regression: a project shipping only requirements.txt (no pyproject /
        setup.py / .git) used to land find_repo_root → None, which downstream
        caused namespace-package layouts (mypkg/foo.py, no __init__.py) to be
        flattened in the bundled workspace and broke `from mypkg.foo import X`.
        requirements.txt is now a project marker."""
        from ast_pilot.repo_support import find_repo_root

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            (root / "mypkg").mkdir()
            source = root / "mypkg" / "foo.py"
            source.write_text("def foo(): return 1\n", encoding="utf-8")

            self.assertEqual(find_repo_root(source), root)
            self.assertEqual(find_repo_root(root / "mypkg"), root)

    def test_find_repo_root_detects_other_python_markers(self) -> None:
        """Pipfile and requirements.in are also valid project-root signals."""
        from ast_pilot.repo_support import find_repo_root

        for marker in ("requirements.in", "Pipfile"):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                (root / marker).write_text("", encoding="utf-8")
                (root / "pkg").mkdir()
                source = root / "pkg" / "mod.py"
                source.write_text("x = 1\n", encoding="utf-8")
                self.assertEqual(find_repo_root(source), root, msg=marker)

    def test_find_repo_root_returns_none_for_marker_less_namespace_pkg(self) -> None:
        """Namespace package without ANY project marker remains undetectable —
        we do NOT walk up into ancestor namespace dirs because that risks
        misclassifying flat single-file projects (lib.py at project root)
        as `repo.lib` and breaking flat `from lib import X` test imports."""
        from ast_pilot.repo_support import find_repo_root

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            # No marker file, no __init__.py anywhere.
            (root / "mypkg").mkdir()
            source = root / "mypkg" / "foo.py"
            source.write_text("def foo(): return 1\n", encoding="utf-8")
            self.assertIsNone(find_repo_root(source))

    def test_namespace_package_workspace_imports_resolve_end_to_end(self) -> None:
        """Integration: a project with a PEP 420 namespace package (mypkg/foo.py
        without mypkg/__init__.py) plus requirements.txt must produce a workspace
        where `from mypkg.foo import X` resolves at runtime. Before the marker
        extension, the mypkg/ directory was stripped entirely and the test
        crashed with ModuleNotFoundError before any implementation check ran."""
        import subprocess

        from ast_pilot.grader_gen import generate_graders

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "audit_ns"
            (project / "mypkg").mkdir(parents=True)
            (project / "tests").mkdir()
            (project / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            (project / "mypkg" / "foo.py").write_text(
                "def foo_fn():\n    return 'foo'\n", encoding="utf-8"
            )
            (project / "mypkg" / "bar.py").write_text(
                "def bar_fn():\n    return 'bar'\n", encoding="utf-8"
            )
            (project / "tests" / "test_pkg.py").write_text(
                "from mypkg.foo import foo_fn\n"
                "from mypkg.bar import bar_fn\n"
                "def test_foo():\n    assert foo_fn() == 'foo'\n"
                "def test_bar():\n    assert bar_fn() == 'bar'\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[project / "mypkg"],
                test_paths=[project / "tests"],
                project_name="audit-ns",
            )

            output_dir = project / "_output"
            generate_graders(
                ev,
                output_dir=output_dir,
                prompt_md="# audit-ns\n",
                source_paths=[Path(m.path) for m in ev.source_files],
                test_paths=[Path(t.test_file) for t in ev.tests],
            )

            golden_root = output_dir / "tasks" / "audit-ns" / "golden"
            self.assertTrue((golden_root / "mypkg" / "foo.py").is_file())
            self.assertTrue((golden_root / "mypkg" / "bar.py").is_file())
            # The bug we're guarding against: golden/foo.py without a mypkg/ prefix
            self.assertFalse((golden_root / "foo.py").is_file())

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from mypkg.foo import foo_fn\n"
                    "from mypkg.bar import bar_fn\n"
                    "assert foo_fn() == 'foo'\n"
                    "assert bar_fn() == 'bar'\n",
                ],
                cwd=golden_root,
                env={"PYTHONPATH": str(golden_root), "PATH": ""},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )

    def test_regular_package_workspace_imports_resolve_end_to_end(self) -> None:
        """Integration counterpart for the regular-package case yesterday's fix
        targeted: src/coverage/__init__.py + src/coverage/envelope.py with
        relative imports must resolve in the staged workspace."""
        import subprocess

        from ast_pilot.grader_gen import generate_graders

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "claimsim"
            (project / "src" / "coverage").mkdir(parents=True)
            (project / "tests").mkdir()
            (project / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            (project / "src" / "__init__.py").write_text("", encoding="utf-8")
            (project / "src" / "coverage" / "__init__.py").write_text(
                "from .envelope import make_envelope\n", encoding="utf-8"
            )
            (project / "src" / "coverage" / "envelope.py").write_text(
                "def make_envelope(pid):\n    return {'pid': pid}\n", encoding="utf-8"
            )
            (project / "tests" / "test_envelope.py").write_text(
                "from src.coverage import make_envelope\n"
                "def test_envelope():\n    assert make_envelope(1) == {'pid': 1}\n",
                encoding="utf-8",
            )

            ev = scan(
                source_paths=[project / "src"],
                test_paths=[project / "tests"],
                project_name="claimsim",
            )
            output_dir = project / "_output"
            generate_graders(
                ev,
                output_dir=output_dir,
                prompt_md="# claimsim\n",
                source_paths=[Path(m.path) for m in ev.source_files],
                test_paths=[Path(t.test_file) for t in ev.tests],
            )

            golden_root = output_dir / "tasks" / "claimsim" / "golden"
            self.assertTrue((golden_root / "src" / "coverage" / "__init__.py").is_file())
            self.assertTrue((golden_root / "src" / "coverage" / "envelope.py").is_file())

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from src.coverage import make_envelope\n"
                    "assert make_envelope(1) == {'pid': 1}\n",
                ],
                cwd=golden_root,
                env={"PYTHONPATH": str(golden_root), "PATH": ""},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )


if __name__ == "__main__":
    unittest.main()
