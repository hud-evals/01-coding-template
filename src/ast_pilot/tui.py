"""Rich-backed TUI for the ast-pilot pipeline.

Exposes a module-level :func:`ui` singleton plus a small set of helpers
that replace the ad-hoc ``print()`` calls scattered across the pipeline.
When stdout is not a TTY (CI logs, pipes, etc.) rich gracefully
degrades to plain output — no ANSI escapes, same content.

Theme: HUD green. The primary accent is a vivid HUD green; teal is the
secondary accent; amber/red handle warn/error. Nothing pink or purple.
"""

from __future__ import annotations

import contextlib
import os
import time
from dataclasses import dataclass, field
from typing import Iterator

from rich.align import Align
from rich.box import ROUNDED
from rich.columns import Columns
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.segment import Segment
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

# --------------------------------------------------------------- brand + palette
_BRAND = "ast-pilot"
_TAGLINE = "task forge"

# HUD palette — muted forest greens, white on black for the logo, amber/red for status.
# Tuned down from earlier "neon" greens to match HUD's actual brand (darker, more
# corporate — vivid green used as sparing accent, not a primary fill).
HUD_GREEN = "#4ade80"         # accent for success glyphs and emphasis text
HUD_GREEN_BRIGHT = "#86efac"  # subtle highlight
HUD_GREEN_DEEP = "#15803d"    # chip backgrounds, sparkbars (darker than before)
HUD_GREEN_DARK = "#14532d"    # phase borders, timing table edges
HUD_GREEN_MID = "#166534"     # gutter — lighter than border so it reads as an edge
HUD_MINT = "#86efac"          # pale green for label accents
HUD_AMBER = "#fbbf24"         # warn
HUD_RED = "#ef4444"           # error
HUD_DIM = "#94a3b8"           # muted text
HUD_BLACK = "#000000"         # logo canvas — explicit so it survives transparent terminals

_HUD_LOGO = (
    "██╗  ██╗██╗   ██╗██████╗ \n"
    "██║  ██║██║   ██║██╔══██╗\n"
    "███████║██║   ██║██║  ██║\n"
    "██╔══██║██║   ██║██║  ██║\n"
    "██║  ██║╚██████╔╝██████╔╝\n"
    "╚═╝  ╚═╝ ╚═════╝ ╚═════╝ "
)

_STATUS_STYLES = {
    "running": ("  ", HUD_GREEN),
    "ok": ("✓ ", f"bold {HUD_GREEN}"),
    "warn": ("! ", f"bold {HUD_AMBER}"),
    "error": ("✗ ", f"bold {HUD_RED}"),
    "skipped": ("· ", HUD_DIM),
}

_SPARK_CHARS = "✦✧✵✶★"


def _sparkbar(value: float, max_value: float, width: int = 10) -> str:
    """Render a tiny horizontal bar comparing `value` against `max_value`."""
    if max_value <= 0 or value < 0:
        return "░" * width
    ratio = min(1.0, value / max_value)
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


@dataclass
class _Phase:
    name: str
    icon: str = "⬥"
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    status: str = "running"
    detail: str = ""

    @property
    def elapsed(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return end - self.started_at


class _Gutter:
    """Wraps a renderable with a colored left gutter so every line reads
    like it belongs to the surrounding phase block.

    Rich doesn't have a first-class left-only border, so we render the
    inner content, split its segments into lines, and prepend a colored
    prefix segment to each one.
    """

    def __init__(self, renderable, char: str = "│  ", style: str = HUD_GREEN_MID):
        self.renderable = renderable
        self.char = char
        self.style = style

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        prefix_width = len(self.char)
        sub_options = options.update(width=max(1, options.max_width - prefix_width))
        lines = console.render_lines(self.renderable, sub_options, pad=False)
        style = console.get_style(self.style)
        prefix = Segment(self.char, style)
        for line in lines:
            yield prefix
            yield from line
            yield Segment.line()


class UI:
    """Thin wrapper around a :class:`rich.console.Console` with pipeline-aware
    phase tracking and reusable status/warning helpers.

    When `plain=True` (or ``AST_PILOT_PLAIN=1`` in the environment), the UI
    degrades to uncoloured, unboxed ``print``-style output suitable for CI
    logs. Animations are suppressed; everything reads as flat text lines.
    """

    def __init__(self, console: Console | None = None, *, plain: bool = False) -> None:
        self.plain = plain or bool(os.environ.get("AST_PILOT_PLAIN"))
        self.console = console or Console(
            highlight=False,
            soft_wrap=False,
            no_color=self.plain,
            force_terminal=False if self.plain else None,
        )
        self.phases: list[_Phase] = []
        self._warnings: list[str] = []
        self._current_phase: _Phase | None = None

    # ------------------------------------------------------------------ banner
    def banner(self, *, source: str, name: str, language: str) -> None:
        """Opening splash: white HUD logo on a black canvas, brand tagline,
        task metadata. Panel border subtly pulses through dark-green shades
        for a breath of motion; the logo itself stays crisp white and doesn't
        animate. Animation is suppressed in non-TTY. Plain mode prints a
        one-line header instead."""
        if self.plain:
            print(f"ast-pilot | task={name} | lang={language}", flush=True)
            print(f"source: {source}", flush=True)
            print(flush=True)
            return
        bg = f"on {HUD_BLACK}"

        # Logo: solid white, no gradient. Each line styled with explicit
        # black bg so the interior reads as a black canvas in any terminal.
        logo_lines = _HUD_LOGO.splitlines()
        logo = Text()
        for idx, line in enumerate(logo_lines):
            logo.append(line, style=f"bold white {bg}")
            if idx < len(logo_lines) - 1:
                logo.append("\n")

        tagline = Text()
        tagline.append("▲ ", style=f"bold {HUD_GREEN} {bg}")
        tagline.append(_BRAND, style=f"bold white {bg}")
        tagline.append("  ·  ", style=f"{HUD_DIM} {bg}")
        tagline.append(_TAGLINE, style=f"italic {HUD_MINT} {bg}")

        body = Text()
        body.append("source   ", style=f"{HUD_DIM} {bg}")
        body.append(source, style=f"bold white {bg}")
        body.append("\n")
        body.append("task     ", style=f"{HUD_DIM} {bg}")
        body.append(name, style=f"bold {HUD_GREEN} {bg}")
        body.append("  ")
        body.append(f"[{language}]", style=f"{HUD_MINT} {bg}")

        border_cycle = (
            HUD_GREEN_DARK,
            HUD_GREEN_MID,
            HUD_GREEN_DEEP,
            HUD_GREEN_MID,
        )

        def _make_panel(offset: int) -> Panel:
            border = border_cycle[offset % len(border_cycle)]
            return Panel(
                Group(logo, Text("", style=bg), tagline, Text("", style=bg), body),
                box=ROUNDED,
                border_style=f"bold {border}",
                style=bg,
                padding=(1, 3),
            )

        self.console.print()
        if self.console.is_terminal:
            with Live(
                _make_panel(0),
                console=self.console,
                refresh_per_second=12,
                transient=False,
            ) as live:
                for offset in range(1, 12):
                    time.sleep(0.07)
                    live.update(_make_panel(offset))
        else:
            self.console.print(_make_panel(0))
        self.console.print()

    # -------------------------------------------------------------------- phase
    @contextlib.contextmanager
    def phase(self, name: str, *, icon: str = "⬥") -> Iterator["_PhaseHandle"]:
        """Context manager for a pipeline phase.

        Prints a top border with the phase name chip, renders all in-phase
        output inside a green left-gutter (so every log line visibly belongs
        to the phase), and closes with a bottom border carrying status glyph
        and elapsed time. Exceptions flip the phase to error before re-raise.
        """
        phase = _Phase(name=name, icon=icon)
        self.phases.append(phase)
        handle = _PhaseHandle(self, phase)
        self._current_phase = phase

        self._render_phase_top(icon, name)

        try:
            yield handle
        except BaseException:
            phase.ended_at = time.monotonic()
            phase.status = "error"
            self._render_phase_bottom(phase)
            self._current_phase = None
            raise
        else:
            phase.ended_at = time.monotonic()
            if phase.status == "running":
                phase.status = "ok"
            self._render_phase_bottom(phase)
            self._current_phase = None

    def _phase_width(self) -> int:
        return min(self.console.width, 96)

    @staticmethod
    def _cells(s: str) -> int:
        """Terminal-cell width of a string (handles wide glyphs correctly)."""
        return Text(s).cell_len

    @staticmethod
    def _clip_detail(detail: str, limit: int = 48) -> str:
        """Keep the border on one line: ellipsize over-long detail strings
        (e.g. long file paths) from the front."""
        detail = detail.strip()
        if len(detail) <= limit:
            return detail
        return "…" + detail[-(limit - 1):]

    def _render_phase_top(self, icon: str, name: str) -> None:
        if self.plain:
            print(f"=== {name} ===", flush=True)
            return
        width = self._phase_width()
        chip = f" {icon}  {name} "
        chip_cells = self._cells(chip)
        filler_count = max(2, width - chip_cells - 3)
        top = Text()
        top.append("╭─", style=HUD_GREEN_DARK)
        top.append(chip, style=f"bold white on {HUD_GREEN_DEEP}")
        top.append("─" + ("─" * filler_count), style=HUD_GREEN_DARK)
        self.console.print(top)

    def _render_phase_bottom(self, phase: _Phase) -> None:
        if self.plain:
            detail = phase.detail.strip()
            tail = f" · {detail}" if detail else ""
            print(f"[{phase.status}] {phase.name}{tail} ({phase.elapsed:.1f}s)", flush=True)
            print(flush=True)
            return
        glyph, color = _STATUS_STYLES.get(phase.status, _STATUS_STYLES["ok"])
        width = self._phase_width()
        detail = self._clip_detail(phase.detail)
        if detail:
            tail = f" {glyph}{detail}  ·  {phase.elapsed:.1f}s "
        else:
            tail = f" {glyph}{phase.elapsed:.1f}s "
        tail_cells = self._cells(tail)
        filler_count = max(2, width - tail_cells - 3)
        bottom = Text()
        bottom.append("╰─", style=HUD_GREEN_DARK)
        bottom.append("─" * filler_count, style=HUD_GREEN_DARK)
        bottom.append("─", style=HUD_GREEN_DARK)
        bottom.append(tail, style=f"bold {color}")
        self.console.print(bottom)
        self.console.print()

    # ------------------------------------------------------------------ logging
    def _emit(self, renderable) -> None:
        """Print a renderable — left-gutter it if we're inside a phase,
        otherwise just indent it."""
        if self._current_phase is not None:
            self.console.print(_Gutter(renderable))
        else:
            self.console.print(Padding(renderable, (0, 0, 0, 2)))

    def _plain_line(self, prefix: str, msg: str) -> None:
        indent = "  " if self._current_phase is not None else ""
        print(f"{indent}{prefix}{msg}", flush=True)

    def log(self, msg: str, *, style: str = "") -> None:
        if self.plain:
            self._plain_line("", msg)
            return
        self._emit(Text(msg, style=style))

    def info(self, msg: str) -> None:
        self.log(msg, style="white")

    def detail(self, msg: str) -> None:
        self.log(msg, style=HUD_DIM)

    def warn(self, msg: str) -> None:
        self._warnings.append(msg)
        if self.plain:
            self._plain_line("WARN: ", msg)
            return
        txt = Text()
        txt.append("⚠  ", style=f"bold {HUD_AMBER}")
        txt.append(msg, style=HUD_AMBER)
        self._emit(txt)

    def error(self, msg: str) -> None:
        if self.plain:
            self._plain_line("ERROR: ", msg)
            return
        txt = Text()
        txt.append("✗  ", style=f"bold {HUD_RED}")
        txt.append(msg, style=HUD_RED)
        self._emit(txt)

    def success(self, msg: str) -> None:
        if self.plain:
            self._plain_line("OK: ", msg)
            return
        txt = Text()
        txt.append("✓  ", style=f"bold {HUD_GREEN}")
        txt.append(msg, style=HUD_GREEN)
        self._emit(txt)

    # ----------------------------------------------------------- live spinners
    @contextlib.contextmanager
    def live_status(self, msg: str) -> Iterator["_LiveStatus"]:
        """Show a live spinner with elapsed-time counter during a blocking
        operation (typically an LLM call). Callers can push a `hint` via
        the handle for live token/round/etc. context next to the timer.
        Spinner renders in HUD green; line is transient and disappears
        when the context exits. Plain mode prints a one-line start/end."""
        if self.plain:
            self._plain_line("... ", msg)
            start = time.monotonic()
            yield _PlainLiveStatus()
            elapsed = time.monotonic() - start
            self._plain_line("... ", f"{msg} (done {elapsed:.1f}s)")
            return
        progress = Progress(
            SpinnerColumn(style=HUD_GREEN, spinner_name="dots12"),
            TextColumn(f"[bold {HUD_GREEN}]" + "{task.description}"),
            TextColumn("[dim]·"),
            TimeElapsedColumn(),
            TextColumn(f"[{HUD_DIM}]" + "{task.fields[hint]}"),
            console=self.console,
            transient=True,
        )
        task_id = progress.add_task(msg, total=None, hint="")
        handle = _LiveStatus(progress, task_id)
        progress.start()
        try:
            yield handle
        finally:
            progress.stop()

    # ------------------------------------------------------------ live streams
    @contextlib.contextmanager
    def live_stream(
        self, label: str, *, tail_width: int = 64
    ) -> Iterator[_LiveStream]:
        """Live LLM streaming display.

        Registers a :data:`llm_client.llm_stream_sink` for the duration of the
        block, so any ``call_text_llm`` invocations inside automatically stream
        their tokens through. The display shows a spinner + label + elapsed +
        char/word counts + scrolling tail preview; it re-renders on Rich's own
        refresh heartbeat (12fps), so the spinner animates smoothly even when
        tokens are slow and the first-token wait is visible (not dead air).

        Plain mode prints a one-line start marker, counts chars without
        rendering, and emits a final "done · N chars · Ns" line on exit.
        """
        from .llm_client import llm_stream_sink

        state = _StreamState(label=label)

        if self.plain:
            self._plain_line("... ", f"{label} [streaming]")
            handle = _PlainLiveStream()
            token = llm_stream_sink.set(handle.feed)
            try:
                yield handle
            finally:
                llm_stream_sink.reset(token)
                state.ended_at = time.monotonic()
                elapsed = state.elapsed
                self._plain_line(
                    "... ",
                    f"{label} done · {handle.char_count:,} chars ({elapsed:.1f}s)",
                )
            return

        handle = _LiveStream(state)
        renderable = _StreamRenderable(state, tail_width=tail_width)
        token = llm_stream_sink.set(handle.feed)
        live = Live(
            renderable,
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        live.start()
        try:
            yield handle
        finally:
            state.ended_at = time.monotonic()
            live.stop()
            llm_stream_sink.reset(token)

    # ------------------------------------------------------------------- lists
    def file_tree(self, title: str, files: list[str]) -> None:
        """Render a list of generated file paths as a compact HUD-green tree."""
        if self.plain:
            self._plain_line("", title)
            for path in sorted(files):
                self._plain_line("  ", path)
            return
        tree = Tree(
            Text(title, style=f"bold {HUD_GREEN}"),
            guide_style=HUD_GREEN_DARK,
        )
        groups: dict[str, list[str]] = {}
        leaves: list[str] = []
        for path in files:
            head, _, tail = path.partition("/")
            if tail:
                groups.setdefault(head, []).append(tail)
            else:
                leaves.append(head)

        for leaf in sorted(leaves):
            tree.add(Text(leaf, style="white"))
        for head in sorted(groups):
            sub = tree.add(Text(head + "/", style=f"bold {HUD_GREEN_BRIGHT}"))
            for child in sorted(groups[head]):
                sub.add(Text(child, style="white"))
        self._emit(tree)

    def fix_list(
        self, title: str, items: list[str], *, style: str = HUD_AMBER
    ) -> None:
        """Bulleted list for alignment fixes or validation diffs."""
        if not items:
            return
        group: list = [Text(title, style=f"bold {style}")]
        for item in items:
            bullet = Text()
            bullet.append("    • ", style=HUD_DIM)
            bullet.append(item, style=style)
            group.append(bullet)
        self._emit(Group(*group))

    # --------------------------------------------------------------- key-value
    def kv(self, pairs: list[tuple[str, str]]) -> None:
        """Render a dim key / bold white value list as a compact grid."""
        if self.plain:
            for key, value in pairs:
                self._plain_line("", f"{key}: {value}")
            return
        table = Table.grid(padding=(0, 2, 0, 0))
        table.add_column(style="dim", justify="right")
        table.add_column(style="bold white")
        for key, value in pairs:
            table.add_row(key, value)
        self._emit(table)

    # ------------------------------------------------------------------ tables
    def issues_table(self, issues: list[tuple[str, str, str]]) -> None:
        """Render a table of (tag, title, detail) tuples — used for the
        per-round alignment fix list."""
        if not issues:
            return
        if self.plain:
            for tag, title, detail in issues:
                self._plain_line(f"[{tag}] ", f"{title} — {detail}")
            return
        table = Table(
            show_header=True,
            header_style=f"bold {HUD_GREEN}",
            box=ROUNDED,
            border_style=HUD_GREEN_DARK,
            expand=False,
        )
        table.add_column("", style="bold", min_width=10, no_wrap=True)
        table.add_column("issue", style="white", no_wrap=False)
        table.add_column("detail", style=HUD_DIM, no_wrap=False)
        for tag, title, detail in issues:
            tag_style = HUD_AMBER
            if tag.lower() == "blocking":
                tag_style = HUD_RED
            elif tag.lower() == "fixed":
                tag_style = HUD_GREEN
            table.add_row(Text(tag, style=f"bold {tag_style}"), title, detail)
        self._emit(table)

    # ------------------------------------------------------------ celebration
    def celebrate(self) -> None:
        """Brief sparkle animation — the victory curtain call before the
        summary. No-op when stdout isn't a TTY or in plain mode."""
        if self.plain or not self.console.is_terminal:
            return
        frames: list[Align] = []
        for step in range(14):
            top = "   ".join(
                _SPARK_CHARS[(step + i) % len(_SPARK_CHARS)] for i in range(5)
            )
            bot = "   ".join(
                _SPARK_CHARS[(step + i + 2) % len(_SPARK_CHARS)] for i in range(5)
            )
            frame = Text()
            frame.append(top, style=f"bold {HUD_GREEN}")
            frame.append("\n\n")
            frame.append("T A S K   F O R G E D", style=f"bold {HUD_GREEN_BRIGHT}")
            frame.append("\n\n")
            frame.append(bot, style=f"bold {HUD_GREEN}")
            frames.append(Align.center(frame))

        with Live(
            frames[0],
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            for frame in frames[1:]:
                time.sleep(0.09)
                live.update(frame)

    # ----------------------------------------------------------------- summary
    def summary(
        self,
        *,
        task_path: str,
        total_elapsed: float,
        extras: list[tuple[str, str]] | None = None,
        celebrate: bool = True,
    ) -> None:
        """Bombastic closer: phase timing table side-by-side with a verdict
        panel. Sparkbar column visualises phase duration distribution; the
        verdict panel carries path + caller-supplied extras (confidence,
        verdict, etc.). When no phase errored, a brief sparkle animation
        fires first (suppressed in non-TTY or when `celebrate=False`).
        Plain mode prints a flat timing + verdict block."""
        if self.plain:
            print("=== summary ===", flush=True)
            for phase in self.phases:
                print(f"{phase.name}: {phase.elapsed:.1f}s ({phase.status})", flush=True)
            print(f"total: {total_elapsed:.1f}s", flush=True)
            print(flush=True)
            print(f"path: {task_path}", flush=True)
            for key, value in extras or []:
                print(f"{key}: {value}", flush=True)
            return
        if celebrate and all(p.status != "error" for p in self.phases):
            self.celebrate()

        max_elapsed = max((p.elapsed for p in self.phases), default=0.0)
        timing = Table(
            box=ROUNDED,
            border_style=HUD_GREEN_DARK,
            show_header=True,
            header_style=f"bold {HUD_GREEN}",
            expand=False,
        )
        timing.add_column("phase", style="white")
        timing.add_column("time", style="bold", justify="right")
        timing.add_column("", style=HUD_GREEN_DEEP, no_wrap=True)
        for phase in self.phases:
            icon, color = _STATUS_STYLES.get(phase.status, _STATUS_STYLES["ok"])
            label = Text()
            label.append(f"{icon}", style=color)
            label.append(phase.name, style="white")
            bar = _sparkbar(phase.elapsed, max_elapsed)
            timing.add_row(
                label,
                f"{phase.elapsed:.1f}s",
                Text(bar, style=HUD_GREEN_DEEP),
            )
        timing.add_row(
            Text("total", style=f"bold {HUD_GREEN}"),
            Text(f"{total_elapsed:.1f}s", style=f"bold {HUD_GREEN}"),
            Text(""),
        )

        verdict_body: list = [
            Text.assemble(("path  ", "dim"), (task_path, f"bold {HUD_GREEN}"))
        ]
        for key, value in extras or []:
            verdict_body.append(
                Text.assemble((f"{key:<6}", "dim"), (value, "bold white"))
            )
        verdict_panel = Panel(
            Group(*verdict_body) if verdict_body else Text(""),
            title=Text(" verdict ", style=f"bold white on {HUD_GREEN_DEEP}"),
            box=ROUNDED,
            border_style=HUD_GREEN_DARK,
            padding=(0, 2),
        )

        self.console.print()
        self.console.print(
            Columns([timing, Padding(verdict_panel, (0, 0, 0, 2))], padding=0)
        )
        self.console.print()

    # ----------------------------------------------------- convenience helpers
    def rule(self, title: str, *, style: str = HUD_GREEN) -> None:
        from rich.rule import Rule

        self.console.print(
            Rule(Text(f" {title} ", style=f"bold {style}"), style=style)
        )

    def blank(self) -> None:
        self.console.print()


class _PhaseHandle:
    """Handle yielded by :meth:`UI.phase` for in-phase logging + status
    updates. Keeping phase-scoped methods on this handle (rather than the
    UI singleton) keeps call sites tidy."""

    def __init__(self, ui: UI, phase: _Phase) -> None:
        self._ui = ui
        self._phase = phase

    def log(self, msg: str, *, style: str = "") -> None:
        self._ui.log(msg, style=style)

    def detail(self, msg: str) -> None:
        self._ui.detail(msg)

    def warn(self, msg: str) -> None:
        self._ui.warn(msg)
        if self._phase.status == "running":
            self._phase.status = "warn"

    def error(self, msg: str) -> None:
        self._ui.error(msg)
        self._phase.status = "error"

    def success(self, msg: str) -> None:
        self._ui.success(msg)

    def set_detail(self, detail: str) -> None:
        self._phase.detail = detail

    def mark_skipped(self, detail: str = "skipped") -> None:
        self._phase.status = "skipped"
        self._phase.detail = detail


class _LiveStatus:
    """Handle yielded by :meth:`UI.live_status` for updating the in-place
    spinner description while a long-running call is happening."""

    def __init__(self, progress: Progress, task_id) -> None:
        self._progress = progress
        self._task_id = task_id

    def update(self, msg: str) -> None:
        self._progress.update(self._task_id, description=msg)

    def set_hint(self, hint: str) -> None:
        """Update the trailing dim hint text (tokens, round counter, etc.)."""
        self._progress.update(self._task_id, hint=hint)


@dataclass
class _StreamState:
    """Mutable state for a live LLM stream: accumulated text, counters, and
    the start time used to compute elapsed. Fed one chunk at a time; read by
    the live renderable on every refresh."""

    label: str
    text: str = ""
    char_count: int = 0
    word_count: int = 0
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None

    def feed(self, chunk: str) -> None:
        self.text += chunk
        self.char_count += len(chunk)
        # Recompute word count from scratch — cheap for prompt-sized text and
        # handles boundary tokens (partial words arriving across chunks).
        self.word_count = len(self.text.split())

    @property
    def elapsed(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return end - self.started_at


class _StreamRenderable:
    """Rich renderable that re-reads :class:`_StreamState` on every refresh.

    Each tick draws: a green spinner, the phase label, elapsed time, running
    char + word counts, and a scrolling tail preview of the last ``tail_width``
    chars of generated text. Passing this directly to ``Live`` (rather than
    calling ``live.update()`` per token) means the spinner animates smoothly
    between tokens and the counter updates even during the first-token wait.
    """

    def __init__(
        self,
        state: _StreamState,
        *,
        spinner_name: str = "dots12",
        tail_width: int = 64,
    ) -> None:
        self._state = state
        self._spinner = Spinner(spinner_name, text="", style=HUD_GREEN)
        self._tail_width = tail_width

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        header = Table.grid(padding=(0, 1))
        header.add_column(no_wrap=True)
        header.add_column(no_wrap=True)
        header.add_column(style=HUD_DIM, no_wrap=True)

        stats = (
            f"{self._state.elapsed:5.1f}s  ·  "
            f"{self._state.char_count:,} chars  ·  "
            f"{self._state.word_count:,} words"
        )
        header.add_row(
            self._spinner,
            Text(self._state.label, style=f"bold {HUD_GREEN}"),
            Text(stats, style=HUD_DIM),
        )

        if self._state.text:
            tail_raw = self._state.text[-self._tail_width:]
        else:
            tail_raw = "(waiting for first token…)"
        tail_raw = tail_raw.replace("\n", " ↵ ")
        tail = Text()
        tail.append("  ▸ ", style=HUD_GREEN_MID)
        tail.append(tail_raw, style=f"italic {HUD_DIM}")

        yield from console.render(Group(header, tail), options)


class _LiveStream:
    """Handle yielded by :meth:`UI.live_stream`.

    Exposes :meth:`feed` for the LLM client (via the context-var sink) and a
    read-only view of accumulated state for callers that want to log the final
    char count after the stream closes.
    """

    def __init__(self, state: _StreamState) -> None:
        self._state = state

    def feed(self, chunk: str) -> None:
        self._state.feed(chunk)

    @property
    def char_count(self) -> int:
        return self._state.char_count

    @property
    def word_count(self) -> int:
        return self._state.word_count

    @property
    def text(self) -> str:
        return self._state.text


class _PlainLiveStream:
    """No-op stream handle for plain mode — same duck-typed surface as
    :class:`_LiveStream` so call sites don't need to branch."""

    def __init__(self) -> None:
        self._char_count = 0
        self._word_count = 0

    def feed(self, chunk: str) -> None:
        self._char_count += len(chunk)
        self._word_count += len(chunk.split())

    @property
    def char_count(self) -> int:
        return self._char_count

    @property
    def word_count(self) -> int:
        return self._word_count

    @property
    def text(self) -> str:
        return ""


class _PlainLiveStatus:
    """No-op live status for plain mode — same duck-typed API as
    :class:`_LiveStatus` so call sites don't need to branch."""

    def update(self, msg: str) -> None:
        pass

    def set_hint(self, hint: str) -> None:
        pass


# ----------------------------------------------------------------------- singleton
_ui: UI | None = None


def ui() -> UI:
    """Return the process-wide UI singleton, creating it on first use."""
    global _ui
    if _ui is None:
        _ui = UI()
    return _ui


def reset_ui(console: Console | None = None, *, plain: bool = False) -> UI:
    """Replace the singleton (used by tests to capture output and by the
    ``--plain`` CLI flag to force uncoloured CI output)."""
    global _ui
    _ui = UI(console=console, plain=plain)
    return _ui
