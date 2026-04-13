"""Tests for alignment review behaviour with TypeScript tasks.

Verifies that the current alignment review correctly (or incorrectly) handles
TS hidden test layouts, so we can track parity improvements.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.alignment_review import (
    AlignmentReview,
    review_task_alignment,
    _load_test_files,
)


def _make_task_dir(
    tmpdir: str,
    prompt: str = "# demo\n",
    test_layout: str = "python",
) -> Path:
    task_dir = Path(tmpdir) / "tasks" / "demo"
    task_dir.mkdir(parents=True)
    (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    if test_layout == "python":
        tests_dir = task_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_demo.py").write_text("def test_a(): pass\n", encoding="utf-8")
    elif test_layout == "ts_nested":
        tests_dir = task_dir / "tests" / "test"
        tests_dir.mkdir(parents=True)
        (tests_dir / "demo.test.ts").write_text(
            'import { describe, it, expect } from "vitest";\n'
            'describe("demo", () => { it("works", () => { expect(1).toBe(1); }); });\n',
            encoding="utf-8",
        )
    elif test_layout == "ts_src":
        tests_dir = task_dir / "tests" / "src"
        tests_dir.mkdir(parents=True)
        (tests_dir / "index.test.ts").write_text(
            'import { test, expect } from "vitest";\n'
            'test("index", () => { expect(true).toBe(true); });\n',
            encoding="utf-8",
        )
    return task_dir


class LoadTestFilesTests(unittest.TestCase):
    """Verify the current test loader behaviour so we know when we fix it."""

    def test_loads_python_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir, test_layout="python")
            files = _load_test_files(task_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0][0], "test_demo.py")

    def test_loads_nested_ts_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir, test_layout="ts_nested")
            files = _load_test_files(task_dir)
        self.assertEqual(len(files), 1)
        self.assertIn("test/demo.test.ts", files[0][0])

    def test_loads_ts_src_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir, test_layout="ts_src")
            files = _load_test_files(task_dir)
        self.assertEqual(len(files), 1)
        self.assertIn("src/index.test.ts", files[0][0])


class AlignmentReviewTSTests(unittest.TestCase):
    def test_review_loads_ts_tests_when_nested(self) -> None:
        """After fix, nested TS tests should be loaded and reviewed."""
        clean_response = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir, test_layout="ts_nested")
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean_response):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)

    def test_review_works_for_python_layout(self) -> None:
        clean_response = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir, test_layout="python")
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean_response):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)


class RealTaskAlignmentTests(unittest.TestCase):
    """Smoke tests against actual generated TS task directories."""

    def _get_task_dir(self, name: str) -> Path:
        return Path(__file__).resolve().parents[1] / "tasks" / name

    def test_citty_has_nested_ts_tests(self) -> None:
        task_dir = self._get_task_dir("citty")
        tests_dir = task_dir / "tests"
        if not tests_dir.is_dir():
            self.skipTest("citty task not present")
        ts_files = list(tests_dir.rglob("*.ts"))
        self.assertGreater(len(ts_files), 0, "citty has TS test files")
        top_level_py = list(tests_dir.glob("*.py"))
        self.assertEqual(len(top_level_py), 0, "citty has no top-level Python tests")

    def test_superjson_has_src_ts_tests(self) -> None:
        task_dir = self._get_task_dir("superjson")
        tests_dir = task_dir / "tests"
        if not tests_dir.is_dir():
            self.skipTest("superjson task not present")
        ts_files = list(tests_dir.rglob("*.ts"))
        self.assertGreater(len(ts_files), 0, "superjson has TS test files")

    def test_alignment_loader_finds_citty_tests(self) -> None:
        task_dir = self._get_task_dir("citty")
        if not (task_dir / "tests").is_dir():
            self.skipTest("citty task not present")
        files = _load_test_files(task_dir)
        self.assertGreater(len(files), 0, "loader now finds nested TS tests for citty")


if __name__ == "__main__":
    unittest.main()
