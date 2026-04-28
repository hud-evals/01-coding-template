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
            "failure_demo": {
                "test_input": "merge({'a': 1}, {'a': 1})",
                "test_expects": "False",
                "agent_following_prompt_produces": "raise ConflictError",
            },
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
            "failure_demo": {
                "test_input": "render('hi')",
                "test_expects": "<b>hi</b>",
                "agent_following_prompt_produces": "**hi**",
            },
        }]})
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=review_response):
                result = review_task_alignment(task_dir)
        self.assertFalse(result.has_blocking)
        self.assertEqual(len(result.fixable_issues), 1)

    def test_malformed_json_marks_review_unavailable(self) -> None:
        """LLM returning None on every retry is `unavailable`, not `clean` —
        a silent failure must NOT pass through as 'no issues found'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = _make_task_dir(tmpdir)
            with patch("ast_pilot.alignment_review.call_text_llm", return_value=None):
                result = review_task_alignment(task_dir)
        self.assertTrue(result.is_unavailable)
        self.assertFalse(result.is_clean)
        self.assertEqual(result.unavailable_tests, ["test_demo.py"])

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
        good = {
            "severity": "error",
            "title": "ok",
            "rationale": "agent would mis-format the date column",
            "failure_demo": {
                "test_input": "datetime(2024, 1, 2)",
                "test_expects": "2024-01-02",
                "agent_following_prompt_produces": "Tue Jan  2 00:00:00 2024",
            },
        }
        result = _parse_issues([42, "string", None, good])
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

    def test_parse_issues_filters_via_structural_failure_demo(self) -> None:
        """An issue is real only when the reviewer can name two materially
        different strings: what the test asserts vs what an agent following
        only the prompt would produce. When those strings match (or one is
        missing) the prompt is doing its job and there is no issue —
        regardless of how the LLM phrased the rationale.

        This is the higher-level fix for self-contradictory issues: instead
        of pattern-matching rationale text, we check the LLM's own concrete
        commitment. If the LLM cannot commit to a real failing example, the
        ``severity: error`` flag is noise."""
        cases = [
            # No failure_demo at all — reviewer never made the failure concrete.
            {
                "severity": "error",
                "category": "underspecified",
                "title": "vague concern, no demo",
                "rationale": "Prompt could be tighter about edge cases.",
                "safe_to_fix": False,
            },
            # Demo present but expects == produces (case + whitespace + quote
            # variants must still match for the structural check to be useful).
            {
                "severity": "error",
                "category": "direct_contradiction",
                "title": "expected matches predicted",
                "rationale": "Subtle wording issue.",
                "safe_to_fix": False,
                "failure_demo": {
                    "test_input": "is_truthy_value('yes')",
                    "test_expects": "True",
                    "agent_following_prompt_produces": "  TRUE  ",
                },
            },
            # Demo present but one side is empty — reviewer wouldn't commit.
            {
                "severity": "error",
                "category": "hidden_requirement",
                "title": "empty produces side",
                "rationale": "Test uses a fixture not mentioned by the prompt.",
                "safe_to_fix": False,
                "failure_demo": {
                    "test_input": "monkeypatch.setenv('X', '1')",
                    "test_expects": "True",
                    "agent_following_prompt_produces": "",
                },
            },
            # A REAL issue: produces materially differs from expects.
            {
                "severity": "error",
                "category": "direct_contradiction",
                "title": "real mismatch",
                "rationale": "Prompt says hyphenated, test asserts underscored.",
                "safe_to_fix": True,
                "failure_demo": {
                    "test_input": "slugify('Hello World')",
                    "test_expects": "hello-world",
                    "agent_following_prompt_produces": "hello_world",
                },
            },
        ]
        result = _parse_issues(cases)
        titles = [i.title for i in result.issues]
        self.assertEqual(titles, ["real mismatch"])


if __name__ == "__main__":
    unittest.main()
