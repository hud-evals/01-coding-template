from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.tui import UI, _sparkbar, reset_ui, ui


def _ui_with_buffer() -> tuple[UI, io.StringIO]:
    buf = io.StringIO()
    console = Console(
        file=buf,
        force_terminal=False,
        no_color=True,
        width=120,
        legacy_windows=False,
    )
    return UI(console=console), buf


class TestTUI(unittest.TestCase):
    def test_banner_includes_brand_source_and_name(self) -> None:
        u, buf = _ui_with_buffer()
        u.banner(source="path/to/foo.py", name="foo-task", language="python")
        output = buf.getvalue()
        self.assertIn("ast-pilot", output)
        self.assertIn("path/to/foo.py", output)
        self.assertIn("foo-task", output)
        self.assertIn("python", output)

    def test_phase_records_elapsed_and_status(self) -> None:
        u, buf = _ui_with_buffer()
        with u.phase("scan") as p:
            p.set_detail("877 loc")
        self.assertEqual(len(u.phases), 1)
        phase = u.phases[0]
        self.assertEqual(phase.name, "scan")
        self.assertEqual(phase.status, "ok")
        self.assertGreaterEqual(phase.elapsed, 0.0)
        self.assertIn("scan", buf.getvalue())

    def test_phase_marks_error_on_exception(self) -> None:
        u, _ = _ui_with_buffer()
        with self.assertRaises(RuntimeError):
            with u.phase("boom"):
                raise RuntimeError("kaboom")
        self.assertEqual(u.phases[0].status, "error")

    def test_phase_records_skipped(self) -> None:
        u, _ = _ui_with_buffer()
        with u.phase("alignment") as p:
            p.mark_skipped("llm disabled")
        self.assertEqual(u.phases[0].status, "skipped")
        self.assertEqual(u.phases[0].detail, "llm disabled")

    def test_phase_warn_escalates_status(self) -> None:
        u, _ = _ui_with_buffer()
        with u.phase("validate") as p:
            p.warn("1 error remaining")
        self.assertEqual(u.phases[0].status, "warn")

    def test_warn_and_error_render_distinct_glyphs(self) -> None:
        u, buf = _ui_with_buffer()
        u.warn("cross-module parents[2]")
        u.error("validation failed")
        output = buf.getvalue()
        self.assertIn("cross-module", output)
        self.assertIn("validation failed", output)
        # Both warn and error should use non-default glyphs so the user sees them
        self.assertTrue(
            any(glyph in output for glyph in ("!", "✗", "x"))
            and any(glyph in output for glyph in ("!", "✗", "warn"))
        )

    def test_file_tree_groups_by_top_level(self) -> None:
        u, buf = _ui_with_buffer()
        u.file_tree(
            "3 files",
            [
                "tasks/foo/task.py",
                "tasks/foo/prompt.md",
                "tasks/foo/support/helper.py",
            ],
        )
        output = buf.getvalue()
        self.assertIn("tasks", output)
        self.assertIn("task.py", output)
        self.assertIn("helper.py", output)

    def test_summary_emits_phase_timings_and_extras(self) -> None:
        u, buf = _ui_with_buffer()
        with u.phase("scan") as p:
            p.set_detail("done")
        with u.phase("bundle") as p:
            p.set_detail("done")
        u.summary(
            task_path="/tmp/tasks/foo",
            total_elapsed=3.14,
            extras=[("conf", "low"), ("note", "severe gaps")],
        )
        output = buf.getvalue()
        self.assertIn("scan", output)
        self.assertIn("bundle", output)
        self.assertIn("total", output)
        self.assertIn("3.1s", output)
        self.assertIn("/tmp/tasks/foo", output)
        self.assertIn("low", output)
        self.assertIn("severe gaps", output)

    def test_issues_table_with_mixed_severities(self) -> None:
        u, buf = _ui_with_buffer()
        u.issues_table([
            ("fixed", "prompt contradicts test", "old → new"),
            ("blocking", "missing key", "literal mismatch"),
            ("dismissed", "false positive", "note"),
        ])
        output = buf.getvalue()
        self.assertIn("fixed", output)
        self.assertIn("blocking", output)
        self.assertIn("dismissed", output)
        self.assertIn("missing key", output)

    def test_live_status_context_does_not_raise(self) -> None:
        u, _ = _ui_with_buffer()
        # Just exercise the entry/exit path; output is transient so we don't
        # assert on buffer content.
        with u.live_status("doing work") as status:
            status.update("still doing work")
            status.set_hint("tokens: 1,234")

    def test_sparkbar_bounds(self) -> None:
        self.assertEqual(_sparkbar(0.0, 10.0, width=5), "░░░░░")
        self.assertEqual(_sparkbar(10.0, 10.0, width=5), "█████")
        self.assertEqual(_sparkbar(5.0, 10.0, width=4), "██░░")
        # degenerate max
        self.assertEqual(_sparkbar(1.0, 0.0, width=3), "░░░")
        # overshoot clamps to full
        self.assertEqual(_sparkbar(20.0, 10.0, width=3), "███")

    def test_summary_renders_sparkbar_column(self) -> None:
        u, buf = _ui_with_buffer()
        with u.phase("scan"):
            pass
        u.summary(task_path="/tmp/x", total_elapsed=1.0, extras=None)
        # summary appends a sparkbar column — in a non-TTY buffer the
        # celebration is skipped but the block char must appear in timing.
        self.assertIn("█", buf.getvalue())

    def test_celebrate_noop_on_non_tty(self) -> None:
        u, buf = _ui_with_buffer()
        # is_terminal=False in the test console, so celebrate should be silent
        u.celebrate()
        self.assertEqual(buf.getvalue(), "")

    def test_phase_content_has_left_gutter(self) -> None:
        u, buf = _ui_with_buffer()
        with u.phase("scan") as p:
            p.log("inside line", style="white")
            p.detail("more detail")
        output = buf.getvalue()
        # Top + bottom borders, and each in-phase line gutter-prefixed with │
        self.assertIn("╭─", output)
        self.assertIn("╰─", output)
        self.assertIn("│", output)
        # The log/detail text must still be visible in output
        self.assertIn("inside line", output)
        self.assertIn("more detail", output)

    def test_non_phase_output_has_no_gutter(self) -> None:
        u, buf = _ui_with_buffer()
        u.info("standalone line")
        output = buf.getvalue()
        self.assertIn("standalone line", output)
        self.assertNotIn("│", output)

    def test_plain_mode_emits_no_box_chars(self) -> None:
        # Plain mode bypasses the rich Console entirely and uses print(), so
        # capture stdout directly rather than the rich buffer.
        import io
        from contextlib import redirect_stdout
        u = UI(plain=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            u.banner(source="x.py", name="demo", language="python")
            with u.phase("scan") as p:
                p.log("loc: 44")
                p.success("all good")
            u.summary(
                task_path="/tmp/x",
                total_elapsed=1.0,
                extras=[("conf", "high")],
            )
        output = buf.getvalue()
        # No box-drawing or gutter characters
        for ch in ("╭", "╰", "│", "━", "█"):
            self.assertNotIn(ch, output, f"plain mode should not emit {ch!r}")
        # Informative content is still there
        self.assertIn("demo", output)
        self.assertIn("scan", output)
        self.assertIn("loc: 44", output)
        self.assertIn("OK: all good", output)
        self.assertIn("total: 1.0s", output)
        self.assertIn("conf: high", output)

    def test_ui_singleton_is_replaceable(self) -> None:
        original = ui()
        replacement = reset_ui()
        self.assertIsNot(original, replacement)
        self.assertIs(ui(), replacement)


if __name__ == "__main__":
    unittest.main()
