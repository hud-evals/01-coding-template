from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence, ModuleInfo
from ast_pilot.scanner import scan
from ast_pilot.validator import validate


class ValidatorTests(unittest.TestCase):
    def test_ignores_test_snippet_keys_inside_implementation_notes_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ev = Evidence(
                project_name="sample",
                source_files=[
                    ModuleInfo(
                        path=str(root / "sample.py"),
                        module_name="sample",
                        string_literals=["accessToken"],
                        line_count=1,
                    )
                ],
            )

            md_path = root / "start.md"
            md_path.write_text(
                textwrap.dedent(
                    """
                    # sample

                    ## Implementation Notes

                    ```python
                    result = resolve_turn_route("hello", None, primary)
                    assert result["runtime"]["credential_pool"] is None
                    ```
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            vr = validate(ev, md_path)
            self.assertFalse(any(issue.section == "string_literal" for issue in vr.issues))

    def test_still_flags_unknown_keys_outside_implementation_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ev = Evidence(
                project_name="sample",
                source_files=[
                    ModuleInfo(
                        path=str(root / "sample.py"),
                        module_name="sample",
                        string_literals=["accessToken"],
                        line_count=1,
                    )
                ],
            )

            md_path = root / "start.md"
            md_path.write_text(
                textwrap.dedent(
                    """
                    # sample

                    ## Natural Language Instructions

                    The function should return a result["runtime"] object.
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            vr = validate(ev, md_path)
            self.assertTrue(any(issue.section == "string_literal" for issue in vr.issues))

    def test_flags_parameter_name_drift_in_documented_defs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "sample.py"
            source_path.write_text(
                textwrap.dedent(
                    """
                    def repeat(value: str, count: int = 1) -> str:
                        return value * count
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan(source_paths=[source_path], project_name="sample")
            md_path = root / "start.md"
            md_path.write_text(
                textwrap.dedent(
                    """
                    # sample

                    ## API Usage Guide

                    ### 1. `repeat` Function

                    ```python
                    def repeat(value: str, size: int = 1) -> str:
                    ```
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            vr = validate(ev, md_path)
            self.assertTrue(any(issue.section == "parameters" and "size" in issue.message for issue in vr.issues))

    def test_flags_missing_signature_markers_in_documented_defs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "sample.py"
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

            ev = scan(source_paths=[source_path], project_name="sample")
            md_path = root / "start.md"
            md_path.write_text(
                textwrap.dedent(
                    """
                    # sample

                    ## API Usage Guide

                    ### 1. `exact` Function

                    ```python
                    def exact(value: str, scale: int = 1, mode: str = "strict") -> str:
                    ```
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            vr = validate(ev, md_path)
            self.assertTrue(any(issue.section == "parameters" and "/" in issue.message for issue in vr.issues))


if __name__ == "__main__":
    unittest.main()
