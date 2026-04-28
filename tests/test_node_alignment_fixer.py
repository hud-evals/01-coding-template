"""Tests for alignment fixer behaviour with TypeScript tasks.

Verifies that the alignment fixer loop uses the correct validator and
handles TS test layouts properly.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.alignment_fixer import run_alignment_loop
from ast_pilot.alignment_review import AlignmentReview
from ast_pilot.evidence import Evidence
from ast_pilot.validator import ValidationIssue, ValidationResult


def _make_ts_task_dir(tmpdir: str, prompt: str = "# demo\n") -> Path:
    task_dir = Path(tmpdir) / "task"
    task_dir.mkdir()
    (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    tests_dir = task_dir / "tests" / "test"
    tests_dir.mkdir(parents=True)
    (tests_dir / "demo.test.ts").write_text(
        'import { test, expect } from "vitest";\n'
        'test("demo", () => { expect(1).toBe(1); });\n',
        encoding="utf-8",
    )
    return task_dir


def _make_py_task_dir(tmpdir: str, prompt: str = "# demo\n") -> Path:
    task_dir = Path(tmpdir) / "task"
    task_dir.mkdir()
    (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_demo.py").write_text("def test_a(): pass\n", encoding="utf-8")
    return task_dir


class AlignmentFixerTSRegressionTests(unittest.TestCase):
    def test_loop_skips_when_no_llm(self) -> None:
        ev = Evidence(project_name="demo", language="typescript")
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_ts_task_dir(tmpdir)
            result = run_alignment_loop(task_dir, ev, use_llm=False)
        self.assertTrue(result.is_clean)

    def test_loop_loads_nested_ts_tests_and_reviews(self) -> None:
        """After fix: alignment loop now loads nested TS tests and reviews them."""
        ev = Evidence(project_name="demo", language="typescript")
        clean = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_ts_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean):
                result = run_alignment_loop(task_dir, ev, use_llm=True)
        self.assertTrue(result.is_clean)

    def test_rollback_uses_node_validator_for_ts(self) -> None:
        """After fix: TS tasks use node_validator for rollback validation."""
        import ast_pilot.node_validator as nv_mod

        ev = Evidence(project_name="demo", language="typescript")

        fixable_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "underspecified",
            "title": "Missing format",
            "prompt_evidence": "...",
            "grader_evidence": "...",
            "rationale": "...",
            "safe_to_fix": True,
            "failure_demo": {
                "test_input": "render('hi')",
                "test_expects": "<b>hi</b>",
                "agent_following_prompt_produces": "**hi**",
            },
        }]})
        original_prompt = "# demo original\n"

        call_count = [0]

        def mock_llm(prompt, *, max_tokens=8192, expect_json=False, temperature=0):
            call_count[0] += 1
            if expect_json:
                if call_count[0] <= 4:
                    return fixable_response
                return json.dumps({"issues": []})
            return "# demo BROKEN\nInvented nonsense."

        bad_validation = ValidationResult(
            issues=[ValidationIssue("error", "symbols", "invented symbol", line=2)]
        )

        validate_calls = []

        def tracking_validate(ev_arg, md_path):
            validate_calls.append("node_validator")
            return bad_validation

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_ts_task_dir(tmpdir, prompt=original_prompt)

            with (
                patch("ast_pilot.alignment_review.call_text_llm", side_effect=mock_llm),
                patch("ast_pilot.alignment_fixer.call_text_llm", side_effect=mock_llm),
                patch.object(nv_mod, "validate", side_effect=tracking_validate),
            ):
                run_alignment_loop(task_dir, ev, use_llm=True, max_rounds=1)

            self.assertGreater(len(validate_calls), 0, "node_validator.validate was called for TS rollback")

    def test_python_layout_alignment_works(self) -> None:
        """Sanity: alignment loop works fine when tests are in the Python layout."""
        ev = Evidence(project_name="demo", language="python")
        clean = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_py_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean):
                result = run_alignment_loop(task_dir, ev, use_llm=True)
        self.assertTrue(result.is_clean)


if __name__ == "__main__":
    unittest.main()
