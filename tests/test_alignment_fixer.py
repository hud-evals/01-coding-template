from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.alignment_fixer import autofix_prompt_alignment, run_alignment_loop
from ast_pilot.alignment_review import AlignmentIssue, AlignmentReview
from ast_pilot.evidence import Evidence
from ast_pilot.validator import ValidationResult


class AlignmentFixerTests(unittest.TestCase):
    def test_no_fixable_issues_returns_unchanged(self) -> None:
        review = AlignmentReview(issues=[
            AlignmentIssue("error", "direct_contradiction", "blocking", "", "", "", safe_to_fix=False),
        ])
        result = autofix_prompt_alignment(prompt_md="# demo\n", review=review)
        self.assertFalse(result.changed)
        self.assertEqual(result.updated_prompt, "# demo\n")
        self.assertEqual(result.applied_issue_titles, [])

    def test_fixable_issues_triggers_llm_rewrite(self) -> None:
        review = AlignmentReview(issues=[
            AlignmentIssue(
                "error", "underspecified", "Missing output format",
                "Prompt says bold", "Test expects <b>",
                "Need HTML tag", safe_to_fix=True,
            ),
        ])
        revised = "# demo\n\nUse `<b>` for bold text."

        with patch("ast_pilot.alignment_fixer.call_text_llm", return_value=revised):
            result = autofix_prompt_alignment(prompt_md="# demo\n", review=review)

        self.assertTrue(result.changed)
        self.assertIn("<b>", result.updated_prompt)
        self.assertEqual(result.applied_issue_titles, ["Missing output format"])

    def test_llm_failure_returns_unchanged(self) -> None:
        review = AlignmentReview(issues=[
            AlignmentIssue(
                "error", "underspecified", "Missing detail",
                "", "", "", safe_to_fix=True,
            ),
        ])

        with patch("ast_pilot.alignment_fixer.call_text_llm", return_value=None):
            result = autofix_prompt_alignment(prompt_md="# demo\n", review=review)

        self.assertFalse(result.changed)

    def test_identical_rewrite_returns_unchanged(self) -> None:
        review = AlignmentReview(issues=[
            AlignmentIssue(
                "error", "underspecified", "Minor",
                "", "", "", safe_to_fix=True,
            ),
        ])

        with patch("ast_pilot.alignment_fixer.call_text_llm", return_value="# demo"):
            result = autofix_prompt_alignment(prompt_md="# demo", review=review)

        self.assertFalse(result.changed)


class AlignmentLoopTests(unittest.TestCase):
    def test_loop_skipped_when_no_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "task"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text("# demo\n", encoding="utf-8")

            result = run_alignment_loop(task_dir, Evidence(), use_llm=False)
        self.assertTrue(result.is_clean)

    def test_loop_passes_clean_review(self) -> None:
        clean = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "task"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text("# demo\n", encoding="utf-8")
            tests_dir = task_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean):
                result = run_alignment_loop(task_dir, Evidence(), use_llm=True)
        self.assertTrue(result.is_clean)

    def test_loop_stops_on_blocking_issues(self) -> None:
        blocking_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "direct_contradiction",
            "title": "Fatal conflict",
            "prompt_evidence": "...",
            "grader_evidence": "...",
            "rationale": "Cannot fix safely.",
            "safe_to_fix": False,
        }]})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "task"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text("# demo\n", encoding="utf-8")
            tests_dir = task_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

            with patch("ast_pilot.alignment_review.call_text_llm", return_value=blocking_response):
                result = run_alignment_loop(task_dir, Evidence(), use_llm=True)
        self.assertTrue(result.has_blocking)

    def test_loop_auto_fixes_then_validates(self) -> None:
        fixable_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "underspecified",
            "title": "Missing format",
            "prompt_evidence": "Prompt says bold",
            "grader_evidence": "Test expects <b>",
            "rationale": "Need tag.",
            "safe_to_fix": True,
        }]})
        clean_response = json.dumps({"issues": []})

        call_count = [0]

        def mock_llm(prompt, *, max_tokens=8192, expect_json=False, temperature=0):
            call_count[0] += 1
            if expect_json:
                if call_count[0] <= 4:
                    return fixable_response
                return clean_response
            return "# demo revised\nUse <b> for bold."

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "task"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text("# demo\n", encoding="utf-8")
            tests_dir = task_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

            with (
                patch("ast_pilot.alignment_review.call_text_llm", side_effect=mock_llm),
                patch("ast_pilot.alignment_fixer.call_text_llm", side_effect=mock_llm),
                patch("ast_pilot.validator.validate", return_value=ValidationResult()),
            ):
                result = run_alignment_loop(task_dir, Evidence(), use_llm=True, max_rounds=2)

            prompt_after = (task_dir / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("revised", prompt_after)

    def test_loop_reverts_prompt_when_factual_validation_fails_after_fix(self) -> None:
        from ast_pilot.validator import ValidationIssue, ValidationResult

        fixable_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "underspecified",
            "title": "Missing format",
            "prompt_evidence": "...",
            "grader_evidence": "...",
            "rationale": "...",
            "safe_to_fix": True,
        }]})

        original_prompt = "# demo original\n"

        def mock_llm(prompt, *, max_tokens=8192, expect_json=False, temperature=0):
            if expect_json:
                return fixable_response
            return "# demo BROKEN\nInvented nonsense."

        bad_validation = ValidationResult(
            issues=[ValidationIssue("error", "symbols", "invented symbol", line=2)]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "task"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text(original_prompt, encoding="utf-8")
            tests_dir = task_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

            with (
                patch("ast_pilot.alignment_review.call_text_llm", side_effect=mock_llm),
                patch("ast_pilot.alignment_fixer.call_text_llm", side_effect=mock_llm),
                patch("ast_pilot.validator.validate", return_value=bad_validation),
            ):
                result = run_alignment_loop(task_dir, Evidence(), use_llm=True, max_rounds=1)

            prompt_after = (task_dir / "prompt.md").read_text(encoding="utf-8")
            self.assertEqual(prompt_after, original_prompt)


if __name__ == "__main__":
    unittest.main()
