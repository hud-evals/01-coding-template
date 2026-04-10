from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence
from ast_pilot.fixer import _get_relevant_evidence, fix_issues
from ast_pilot.scanner import scan
from ast_pilot.validator import ValidationIssue, ValidationResult


class FixerTests(unittest.TestCase):
    def test_fix_issues_replaces_the_flagged_duplicate_line(self) -> None:
        original_md = "# demo\nrepeat me\nmiddle line\nrepeat me\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(original_md, encoding="utf-8")

            validation = ValidationResult(
                issues=[ValidationIssue("error", "parameters", "duplicate line needs correction", line=4)]
            )

            with patch("ast_pilot.fixer._call_llm", return_value="FIX: corrected line"):
                fixed_md, actions = fix_issues(Evidence(project_name="demo"), md_path, validation)

        self.assertEqual(actions[0].action, "fixed")
        self.assertEqual(fixed_md, "# demo\nrepeat me\nmiddle line\ncorrected line\n")

    def test_get_relevant_evidence_handles_dotted_method_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "sample.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    class Widget:
                        def render(self) -> str:
                            return "ok"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(source_paths=[source_path], project_name="sample")
            issue = ValidationIssue(
                "error",
                "return_type",
                "'Widget.render' return type: md says 'int', evidence says 'str'",
                line=1,
            )

            evidence_text = _get_relevant_evidence(ev, issue)

        self.assertIn("Widget.render(...) -> str", evidence_text)


if __name__ == "__main__":
    unittest.main()
