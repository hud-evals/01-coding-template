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


if __name__ == "__main__":
    unittest.main()
