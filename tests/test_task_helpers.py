"""Unit tests for tasks/_helpers — the task-build inliners.

Each helper reads files next to a task.py at import time and returns a
JSON-serializable payload that gets embedded in Task.args (or Task.validation
for golden staging). These tests exercise shapes, empty-dir behaviour, and
stable ordering so sync payloads don't churn between runs.
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks._helpers import (
    golden_validation,
    load_golden,
    load_prompt,
    load_requirements,
    load_support,
    pytest_grader,
)


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class LoadPromptTests(unittest.TestCase):
    def test_reads_prompt_md_next_to_task_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "mytask"
            task_dir.mkdir()
            (task_dir / "prompt.md").write_text("hello world", encoding="utf-8")
            task_file = task_dir / "task.py"
            task_file.write_text("# task", encoding="utf-8")
            self.assertEqual(load_prompt(str(task_file)), "hello world")


class LoadSupportTests(unittest.TestCase):
    def test_walks_support_recursively_and_returns_relative_posix_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "mytask"
            task_dir.mkdir()
            _write_tree(task_dir / "support", {
                "hermes_cli/__init__.py": "",
                "hermes_cli/config.py": "def load_config(): return {}",
                "tools/helper.py": "X = 1",
            })
            got = load_support(str(task_dir / "task.py"))
            self.assertEqual(set(got), {
                "hermes_cli/__init__.py",
                "hermes_cli/config.py",
                "tools/helper.py",
            })
            self.assertEqual(got["hermes_cli/config.py"], "def load_config(): return {}")

    def test_missing_dir_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "no_support"
            task_dir.mkdir()
            self.assertEqual(load_support(str(task_dir / "task.py")), {})

    def test_output_is_json_serializable(self) -> None:
        """Sync uploads args as JSON — any non-stringable value blows up the POST."""
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "support", {"a.py": "x = 1\n"})
            payload = load_support(str(task_dir / "task.py"))
            self.assertEqual(json.loads(json.dumps(payload)), payload)


class LoadGoldenTests(unittest.TestCase):
    def test_reads_golden_tree_same_shape_as_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "golden", {
                "agent/retry_utils.py": "def retry(fn): ...",
            })
            got = load_golden(str(task_dir / "task.py"))
            self.assertEqual(got, {"agent/retry_utils.py": "def retry(fn): ..."})

    def test_missing_dir_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            self.assertEqual(load_golden(str(task_dir / "task.py")), {})


class LoadRequirementsTests(unittest.TestCase):
    def test_reads_requirements_txt_content_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            (task_dir / "requirements.hidden.txt").write_text(
                "pyyaml>=6\nrich>=14\n", encoding="utf-8"
            )
            self.assertEqual(
                load_requirements(str(task_dir / "task.py")),
                "pyyaml>=6\nrich>=14\n",
            )

    def test_missing_file_returns_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            self.assertEqual(load_requirements(str(task_dir / "task.py")), "")


class PytestGraderTests(unittest.TestCase):
    def test_inlines_test_content_and_records_weight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "tests", {
                "test_retry.py": "def test_ok(): assert True\n",
            })
            grader = pytest_grader(
                "test_retry.py",
                task_file=str(task_dir / "task.py"),
                weight=0.5,
                timeout=60,
            )
            self.assertEqual(grader["kind"], "pytest")
            self.assertEqual(grader["name"], "test_retry")
            self.assertEqual(grader["test_name"], "test_retry.py")
            self.assertEqual(grader["script"], "def test_ok(): assert True\n")
            self.assertEqual(grader["weight"], 0.5)
            self.assertEqual(grader["timeout"], 60)

    def test_script_payload_survives_json_roundtrip(self) -> None:
        """Regex backslash escapes must survive JSON serialization intact."""
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            source = r'''import re
DANGEROUS = re.compile(r"\brm\b.*\b-rf\b")
assert DANGEROUS.search("rm -rf /")
'''
            _write_tree(task_dir / "tests", {"test_re.py": source})
            grader = pytest_grader(
                "test_re.py",
                task_file=str(task_dir / "task.py"),
            )
            roundtripped = json.loads(json.dumps(grader))
            self.assertEqual(roundtripped["script"], source)
            self.assertIn(r"\b", roundtripped["script"])


class GoldenValidationTests(unittest.TestCase):
    def test_no_golden_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            self.assertEqual(golden_validation(str(task_dir / "task.py")), [])

    def test_single_golden_file_produces_one_bash_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "golden", {
                "tools/ansi_strip.py": "def strip_ansi(s): return s\n",
            })
            calls = golden_validation(str(task_dir / "task.py"))
            self.assertEqual(len(calls), 1)
            call = calls[0]
            self.assertEqual(call.name, "bash")
            cmd = call.arguments["command"]
            self.assertIn("mkdir -p /home/ubuntu/workspace/tools", cmd)
            self.assertIn("/home/ubuntu/workspace/tools/ansi_strip.py", cmd)
            self.assertIn("| base64 -d >", cmd)
            # The encoded content must match the original when decoded.
            expected = base64.b64encode(b"def strip_ansi(s): return s\n").decode("ascii")
            self.assertIn(expected, cmd)

    def test_nested_golden_paths_each_get_mkdir_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "golden", {
                "a/b/c.py": "x = 1\n",
                "a/d.py": "y = 2\n",
            })
            calls = golden_validation(str(task_dir / "task.py"))
            self.assertEqual(len(calls), 1)
            cmd = calls[0].arguments["command"]
            self.assertIn("mkdir -p /home/ubuntu/workspace/a/b", cmd)
            self.assertIn("mkdir -p /home/ubuntu/workspace/a", cmd)
            self.assertIn("/home/ubuntu/workspace/a/b/c.py", cmd)
            self.assertIn("/home/ubuntu/workspace/a/d.py", cmd)

    def test_custom_workspace_dir_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "golden", {"x.py": "1\n"})
            calls = golden_validation(
                str(task_dir / "task.py"), workspace_dir="/mnt/work"
            )
            self.assertIn("/mnt/work/x.py", calls[0].arguments["command"])

    def test_payload_is_json_serializable_via_model_dump(self) -> None:
        """hud sync dumps MCPToolCall via pydantic — must roundtrip clean."""
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "t"
            task_dir.mkdir()
            _write_tree(task_dir / "golden", {"a.py": "x = 1\n"})
            calls = golden_validation(str(task_dir / "task.py"))
            dumped = [c.model_dump() for c in calls]
            self.assertEqual(json.loads(json.dumps(dumped)), dumped)


if __name__ == "__main__":
    unittest.main()
