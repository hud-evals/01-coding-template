from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.alignment_review import (
    AlignmentIssue,
    AlignmentReview,
    review_task_alignment,
    _parse_issues,
    _parse_raw_issues_json,
)


def _make_task_dir(tmpdir: str, prompt: str = "# demo\n", test_content: str = "def test_x(): pass\n") -> Path:
    task_dir = Path(tmpdir) / "tasks" / "demo"
    task_dir.mkdir(parents=True)
    (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_demo.py").write_text(test_content, encoding="utf-8")
    return task_dir


class AlignmentReviewTests(unittest.TestCase):
    def test_clean_review_returns_no_issues(self) -> None:
        clean_response = json.dumps({"issues": []})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=clean_response):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)
        self.assertEqual(len(result.issues), 0)

    def test_blocking_issue_is_detected(self) -> None:
        review_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "direct_contradiction",
            "title": "Conflict: raise vs return False",
            "prompt_evidence": "Prompt says raise ConflictError",
            "grader_evidence": "Test asserts returns False",
            "rationale": "Implementation that follows prompt will fail grader.",
            "safe_to_fix": False,
        }]})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=review_response):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.has_blocking)
        self.assertEqual(len(result.blocking_issues), 1)
        self.assertEqual(result.blocking_issues[0].category, "direct_contradiction")

    def test_fixable_issue_is_detected(self) -> None:
        review_response = json.dumps({"issues": [{
            "severity": "error",
            "category": "underspecified",
            "title": "Missing output format detail",
            "prompt_evidence": "Prompt says bold text",
            "grader_evidence": "Test expects <b> tag",
            "rationale": "Prompt should specify HTML tag.",
            "safe_to_fix": True,
        }]})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=review_response):
                result = review_task_alignment(task_dir)
        self.assertFalse(result.has_blocking)
        self.assertEqual(len(result.fixable_issues), 1)

    def test_malformed_json_retry_then_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=None):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)

    def test_malformed_json_string_retries_once(self) -> None:
        calls = []

        def side_effect(*args, **kwargs):
            calls.append(1)
            if len(calls) <= 2:
                return "not json"
            return json.dumps({"issues": []})

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", side_effect=side_effect):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)

    def test_parse_raw_issues_json_handles_non_dict(self) -> None:
        self.assertEqual(_parse_raw_issues_json("[]"), [])
        self.assertEqual(_parse_raw_issues_json("null"), [])
        self.assertEqual(_parse_raw_issues_json("invalid"), [])

    def test_parse_issues_skips_non_dict_entries(self) -> None:
        result = _parse_issues([42, "string", None, {"severity": "error", "title": "ok"}])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].title, "ok")

    def test_blocking_and_fixable_split(self) -> None:
        review = AlignmentReview(issues=[
            AlignmentIssue("error", "direct_contradiction", "blocking one", "", "", "", safe_to_fix=False),
            AlignmentIssue("error", "underspecified", "fixable one", "", "", "", safe_to_fix=True),
            AlignmentIssue("warning", "unclear", "warning one", "", "", "", safe_to_fix=True),
        ])
        self.assertEqual(len(review.blocking_issues), 1)
        self.assertEqual(len(review.fixable_issues), 1)
        self.assertFalse(review.is_clean)
        self.assertTrue(review.has_blocking)

    def test_review_returns_empty_when_no_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "tasks" / "demo"
            task_dir.mkdir(parents=True)
            (task_dir / "prompt.md").write_text("# demo\n", encoding="utf-8")
            result = review_task_alignment(task_dir)
        self.assertTrue(result.is_clean)


if __name__ == "__main__":
    unittest.main()
