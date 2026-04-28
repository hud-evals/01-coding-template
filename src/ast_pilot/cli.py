"""CLI entrypoints for ast-pilot."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from .shared_utils import pkg_name as _pkg_name, slug as _slug
from .tui import ui

ALLOW_ALIGNMENT_UNAVAILABLE_ENV = "AST_PILOT_ALLOW_ALIGNMENT_UNAVAILABLE"


def _allow_alignment_unavailable(args: argparse.Namespace) -> bool:
    """``True`` when the user has explicitly opted into shipping a task whose
    alignment review never returned a parseable response.

    Defaults to ``False`` so a silent reviewer outage cannot promote a task
    with unknown coverage. Either ``--allow-alignment-unavailable`` or the
    ``AST_PILOT_ALLOW_ALIGNMENT_UNAVAILABLE`` env var (set to a truthy value)
    flips it on.
    """
    if getattr(args, "allow_alignment_unavailable", False):
        return True
    raw = os.environ.get(ALLOW_ALIGNMENT_UNAVAILABLE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_language(args: argparse.Namespace) -> str:
    from .languages import infer_language, validate_language

    explicit = getattr(args, "language", None)
    if explicit:
        return validate_language(explicit)
    sources = getattr(args, "sources", None) or []
    return infer_language(sources)


def cmd_scan(args: argparse.Namespace) -> None:
    language = _resolve_language(args)

    if language == "typescript":
        from .node_scanner import scan_typescript

        source_paths = [Path(p) for p in args.sources]
        test_paths = [Path(p) for p in args.tests] if args.tests else None
        readme = Path(args.readme) if args.readme else None
        ev = scan_typescript(
            source_paths=source_paths,
            test_paths=test_paths,
            project_name=args.name,
            readme_path=readme,
        )
    else:
        from .scanner import scan

        source_paths = [Path(p) for p in args.sources]
        test_paths = [Path(p) for p in args.tests] if args.tests else None
        readme = Path(args.readme) if args.readme else None
        ev = scan(
            source_paths=source_paths,
            test_paths=test_paths,
            project_name=args.name,
            readme_path=readme,
        )

    out = args.output or "evidence.json"
    ev.save(out)
    print(f"Scanned {ev.total_loc} LOC across {len(ev.source_files)} modules")
    print(f"  Classes: {sum(len(m.classes) for m in ev.source_files)}")
    print(f"  Functions: {sum(len(m.functions) for m in ev.source_files)}")
    print(f"  Tests mapped: {len(ev.tests)}")
    print(f"  Dependencies: {ev.dependencies}")
    print(f"Saved to {out}")


def cmd_spec(args: argparse.Namespace) -> None:
    from .evidence import Evidence

    ev = Evidence.load(args.evidence)
    out = args.output or "prompt.md"
    use_llm = not args.no_llm

    if ev.language == "typescript":
        from .node_spec_renderer import render_start_md
    else:
        from .spec_renderer import render_start_md

    md = render_start_md(ev, output_path=out, use_llm=use_llm)
    print(f"Generated {len(md)} chars -> {out}")
    if not use_llm:
        print("  (LLM disabled, used deterministic fallback)")


def cmd_bundle(args: argparse.Namespace) -> None:
    from .evidence import Evidence

    ev = Evidence.load(args.evidence)
    out_dir, cleanup_after_success = _prepare_bundle_root(args.output, ev.project_name)
    prompt_path = Path(args.prompt) if args.prompt else Path(args.evidence).with_name("prompt.md")
    prompt_md = _load_validated_prompt(ev, prompt_path)
    source_paths = [mod.path for mod in ev.source_files]
    test_paths = sorted({test.test_file for test in ev.tests})

    no_alignment = getattr(args, "no_alignment_autofix", False)
    alignment_max = getattr(args, "alignment_max_rounds", 2)
    use_llm = not getattr(args, "no_llm", False)

    if ev.language == "typescript":
        from .node_grader_gen import generate_graders
    else:
        from .grader_gen import generate_graders

    promoted_to: Path | None = None
    try:
        files = generate_graders(
            ev,
            output_dir=out_dir,
            prompt_md=prompt_md,
            source_paths=source_paths,
            test_paths=test_paths,
        )
        print(f"Generated {len(files)} files in {out_dir}/:")
        for path in sorted(files):
            print(f"  {path}")

        generated_task_dir = out_dir / "tasks" / _slug(ev.project_name)
        if use_llm and not no_alignment and generated_task_dir.is_dir():
            print("\n=== Running prompt-grader alignment review ===")
            alignment = _run_alignment_loop(
                generated_task_dir, ev, max_rounds=alignment_max, use_llm=use_llm,
            )
            if alignment.has_blocking:
                print("\nAlignment check failed: unresolved prompt-grader contradictions.")
                for issue in alignment.blocking_issues:
                    print(f"  [BLOCKING] {issue.title}: {issue.rationale}")
                _print_alignment_verdict(alignment)
                raise SystemExit(2)
            elif alignment.is_unavailable:
                print(
                    f"  Alignment: UNAVAILABLE ({len(alignment.unavailable_tests)} test file(s) — "
                    "coverage unknown, NOT clean):"
                )
                for name in alignment.unavailable_tests:
                    print(f"    - {name}")
                if not _allow_alignment_unavailable(args):
                    print(
                        f"\nRefusing to promote a task whose alignment review failed. Set "
                        f"--allow-alignment-unavailable or {ALLOW_ALIGNMENT_UNAVAILABLE_ENV}=1 "
                        "to ship anyway (coverage will be unknown)."
                    )
                    _print_alignment_verdict(alignment)
                    raise SystemExit(2)
            elif alignment.is_clean:
                print("  Alignment: PASSED (no issues)")
            else:
                print(f"  Alignment: OK ({len(alignment.issues)} remaining non-blocking issues)")
            _print_alignment_verdict(alignment)

        promoted_to = _promote_generated_task(out_dir, ev.project_name)
        if promoted_to is not None:
            print(f"Promoted task package -> {promoted_to}")
        print(_bundle_result_message(out_dir, promoted_to, kept_artifacts=bool(args.output)))
    finally:
        if cleanup_after_success and promoted_to is not None:
            shutil.rmtree(out_dir, ignore_errors=True)


def cmd_run(args: argparse.Namespace) -> None:
    """Full pipeline: scan -> spec -> bundle in one shot."""

    language = _resolve_language(args)

    raw_source_paths = [Path(p) for p in args.sources]
    raw_test_paths = [Path(p) for p in args.tests] if args.tests else None
    readme = Path(args.readme) if args.readme else None
    out_dir, cleanup_after_success = _prepare_bundle_root(args.output, args.name)
    use_llm = not args.no_llm

    if language == "typescript":
        from .node_grader_gen import generate_graders
        from .node_scanner import (
            _TS_SOURCE_EXTENSIONS,
            _TS_TEST_EXTENSIONS,
            _expand_node_paths,
            scan_typescript as scan,
        )
        from .node_spec_renderer import render_start_md

        source_paths = _expand_node_paths(raw_source_paths, _TS_SOURCE_EXTENSIONS)
        test_paths = (
            _expand_node_paths(raw_test_paths, _TS_TEST_EXTENSIONS)
            if raw_test_paths
            else None
        )
    else:
        from .grader_gen import generate_graders
        from .scanner import _expand_py_paths, scan
        from .spec_renderer import render_start_md

        source_paths = _expand_py_paths(raw_source_paths)
        test_paths = _expand_py_paths(raw_test_paths) if raw_test_paths else None

    # Expansion at the CLI boundary means scanner AND grader_gen both receive
    # a flat list of files. Otherwise the scanner sees expanded paths (its own
    # internal helper kicked in) but generate_graders receives raw directories
    # and crashes inside _write_golden_files when it does Path.read_text() on
    # a dir. Sub-agent verification (#2) caught this on multi-package source
    # trees — fixed in 2026-04-29.

    if getattr(args, "plain", False):
        from .tui import reset_ui
        console = reset_ui(plain=True)
    else:
        console = ui()
    pipeline_started = time.monotonic()
    alignment_extras: list[tuple[str, str]] = []

    console.banner(
        source=", ".join(str(p) for p in source_paths),
        name=args.name,
        language=language,
    )

    with console.phase("scan", icon="⌕") as p:
        ev = scan(
            source_paths=source_paths,
            test_paths=test_paths,
            project_name=args.name,
            readme_path=readme,
        )
        console.kv([
            ("loc", str(ev.total_loc)),
            ("classes", str(sum(len(m.classes) for m in ev.source_files))),
            ("functions", str(sum(len(m.functions) for m in ev.source_files))),
            ("tests", str(len(ev.tests))),
        ])
        p.set_detail(f"{ev.total_loc} loc · {len(ev.tests)} tests")

    ev.save(out_dir / "evidence.json")

    with console.phase("prompt", icon="✎") as p:
        if use_llm:
            with console.live_stream("generating prompt.md via llm"):
                md = render_start_md(ev, output_path=out_dir / "prompt.md", use_llm=use_llm)
        else:
            md = render_start_md(ev, output_path=out_dir / "prompt.md", use_llm=use_llm)
        console.kv([("chars", f"{len(md):,}"), ("mode", "llm" if use_llm else "deterministic")])
        p.set_detail(f"{len(md):,} chars")

    if language == "typescript":
        from .node_validator import validate
    else:
        from .validator import validate

    with console.phase("validate", icon="◈") as p:
        vr = validate(ev, out_dir / "prompt.md")
        # Paint a picture: what was checked, and the pass/warn/error breakdown.
        # "clean" means 0 blocking errors — warnings are informational and don't
        # halt the pipeline. If there are errors and llm is on, we spin up fix
        # rounds below to try to auto-repair.
        console.kv([
            ("errors", str(vr.error_count)),
            ("warnings", str(vr.warning_count)),
        ])
        if vr.issues:
            console.issues_table([
                (
                    "error" if i.severity == "error" else "warn",
                    f"{i.section} (line {i.line})" if i.line else i.section,
                    i.message,
                )
                for i in vr.issues
            ])
        if vr.error_count == 0:
            if vr.warning_count == 0:
                p.success("no factual issues")
                p.set_detail("clean")
            else:
                p.success(f"{vr.warning_count} non-blocking warnings")
                p.set_detail(f"{vr.warning_count} warnings")
        else:
            p.set_detail(f"{vr.error_count} errors — entering fix rounds")

    max_fix_rounds = 3
    dismissed_keys: set[str] = set()
    for fix_round in range(1, max_fix_rounds + 1):
        real_errors = _undismissed_errors(vr, dismissed_keys)
        if not real_errors or not use_llm:
            break

        with console.phase(f"fix round {fix_round}/{max_fix_rounds}", icon="✎") as p:
            console.detail(f"fixing {len(real_errors)} error(s)")
            from .fixer import fix_issues
            from .validator import ValidationResult

            filtered_vr = ValidationResult(issues=real_errors)
            with console.live_stream(f"re-writing prompt.md (round {fix_round})"):
                _, actions = fix_issues(ev, out_dir / "prompt.md", filtered_vr)

            fix_rows: list[tuple[str, str, str]] = []
            for a in actions:
                if a.action == "fixed":
                    snippet_old = a.old_text[:60].replace("\n", " ")
                    snippet_new = a.new_text[:60].replace("\n", " ")
                    fix_rows.append((
                        "fixed",
                        a.issue.message,
                        f"{snippet_old!r} → {snippet_new!r}",
                    ))
                elif a.action == "dismissed":
                    fix_rows.append(("dismissed", a.issue.message, a.reason))
                    dismissed_keys.add(f"{a.issue.line}:{a.issue.message[:60]}")
                else:
                    fix_rows.append((a.action.upper(), a.issue.message, a.reason))
            console.issues_table(fix_rows)

            with console.live_status(f"re-validating (round {fix_round})"):
                vr = validate(ev, out_dir / "prompt.md")
            remaining = _undismissed_errors(vr, dismissed_keys)
            if remaining:
                p.warn(f"{len(remaining)} error(s) remaining")
                for i in remaining:
                    console.detail(i.message)
                p.set_detail(f"{len(remaining)} still failing")
            else:
                p.success(f"passed ({len(dismissed_keys)} dismissed)")
                p.set_detail("clean")

    remaining_errors = _undismissed_errors(vr, dismissed_keys)
    if remaining_errors:
        console.error("validation failed — unresolved factual errors remain in prompt.md")
        for issue in remaining_errors:
            console.detail(issue.message)
        raise SystemExit(2)

    # The fix loop above rewrites prompt.md on disk; reload before bundling so
    # the task package matches what validation actually approved instead of the
    # pre-fix string still in `md`.
    md = (out_dir / "prompt.md").read_text(encoding="utf-8")

    promoted_to: Path | None = None
    try:
        with console.phase("bundle", icon="☰") as p:
            files = generate_graders(
                ev,
                output_dir=out_dir,
                prompt_md=md,
                source_paths=source_paths,
                test_paths=test_paths,
            )
            console.file_tree(f"{len(files)} files", sorted(files.keys()))
            p.set_detail(f"{len(files)} files")

        no_alignment = getattr(args, "no_alignment_autofix", False)
        alignment_max = getattr(args, "alignment_max_rounds", 2)
        generated_task_dir = out_dir / "tasks" / _slug(ev.project_name)

        if use_llm and not no_alignment and generated_task_dir.is_dir():
            with console.phase("alignment", icon="⚖") as p:
                alignment = _run_alignment_loop(
                    generated_task_dir, ev, max_rounds=alignment_max, use_llm=use_llm,
                )
                if alignment.has_blocking:
                    p.error("blocking contradictions")
                    console.issues_table([
                        ("blocking", issue.title, issue.rationale)
                        for issue in alignment.blocking_issues
                    ])
                    if alignment.confidence:
                        alignment_extras.append(("conf", alignment.confidence))
                    if alignment.verdict:
                        alignment_extras.append(("note", alignment.verdict))
                    p.set_detail("blocking")
                    raise SystemExit(2)
                elif alignment.is_unavailable:
                    p.warn(
                        f"alignment unavailable for {len(alignment.unavailable_tests)} test "
                        "file(s) — coverage unknown, NOT clean"
                    )
                    for name in alignment.unavailable_tests:
                        console.detail(name)
                    if not _allow_alignment_unavailable(args):
                        p.error("refusing to promote — alignment unknown")
                        console.detail(
                            f"set --allow-alignment-unavailable or "
                            f"{ALLOW_ALIGNMENT_UNAVAILABLE_ENV}=1 to ship anyway"
                        )
                        if alignment.confidence:
                            alignment_extras.append(("conf", alignment.confidence))
                        if alignment.verdict:
                            alignment_extras.append(("note", alignment.verdict))
                        p.set_detail("unavailable")
                        raise SystemExit(2)
                    p.set_detail("unavailable (allowed)")
                elif alignment.is_clean:
                    p.success("no issues")
                    p.set_detail("clean")
                else:
                    p.success(f"ok · {len(alignment.issues)} non-blocking issues")
                    p.set_detail(f"{len(alignment.issues)} non-blocking")
                if alignment.confidence:
                    alignment_extras.append(("conf", alignment.confidence))
                if alignment.verdict:
                    alignment_extras.append(("note", alignment.verdict))
        elif not use_llm:
            with console.phase("alignment", icon="⚖") as p:
                p.mark_skipped("llm disabled")

        with console.phase("promote", icon="⇪") as p:
            promoted_to = _promote_generated_task(out_dir, ev.project_name)
            if promoted_to is not None:
                p.set_detail(str(promoted_to))
            else:
                p.mark_skipped("no tasks/ directory")
    finally:
        if cleanup_after_success and promoted_to is not None:
            shutil.rmtree(out_dir, ignore_errors=True)

    total_elapsed = time.monotonic() - pipeline_started
    console.summary(
        task_path=str(promoted_to) if promoted_to else str(out_dir),
        total_elapsed=total_elapsed,
        extras=alignment_extras,
    )


def _print_alignment_verdict(alignment) -> None:
    if alignment.confidence:
        print(f"  Confidence: {alignment.confidence}")
    if alignment.verdict:
        print(f"  Verdict: {alignment.verdict}")


def _run_alignment_loop(task_dir: Path, ev, *, max_rounds: int = 2, use_llm: bool = True):
    from .alignment_fixer import run_alignment_loop
    return run_alignment_loop(task_dir, ev, max_rounds=max_rounds, use_llm=use_llm)


def _promote_generated_task(output_root: Path, project_name: str) -> Path | None:
    task_root = Path("tasks")
    if not task_root.is_dir():
        return None

    generated_slug = _slug(project_name)
    generated_task_dir = output_root / "tasks" / generated_slug
    if not generated_task_dir.is_dir():
        return None

    destination = task_root / _pkg_name(project_name)
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(generated_task_dir, destination)
    return destination.resolve()


def _undismissed_errors(vr, dismissed_keys: set[str]) -> list:
    return [
        issue
        for issue in vr.issues
        if issue.severity == "error"
        and f"{issue.line}:{issue.message[:60]}" not in dismissed_keys
    ]


def _load_validated_prompt(ev, prompt_path: Path) -> str:
    if ev.language == "typescript":
        from .node_validator import validate
    else:
        from .validator import validate

    if not prompt_path.is_file():
        print(f"Prompt markdown not found: {prompt_path}")
        raise SystemExit(2)

    print(f"=== Validating prompt markdown: {prompt_path} ===")
    vr = validate(ev, prompt_path)
    print(f"  {vr.summary()}")

    remaining_errors = _undismissed_errors(vr, set())
    if remaining_errors:
        print("\nValidation failed: unresolved factual errors remain in the prompt markdown.")
        for issue in remaining_errors:
            print(f"  [ERROR] {issue.message}")
        raise SystemExit(2)

    return prompt_path.read_text(encoding="utf-8")


def _prepare_bundle_root(output: str | None, project_name: str) -> tuple[Path, bool]:
    if output:
        return Path(output), False
    return Path(tempfile.mkdtemp(prefix=f"ast_pilot_{_pkg_name(project_name)}_")), True


def _bundle_result_message(out_dir: Path, promoted_to: Path | None, kept_artifacts: bool) -> str:
    if promoted_to is not None:
        if kept_artifacts:
            return f"Done. Task package updated at {promoted_to} and bundle artifacts kept in {out_dir}/"
        return f"Done. Task package updated at {promoted_to}"
    return f"Done. Bundle artifacts kept in {out_dir}/"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ast-pilot",
        description="Generate HUD coding tasks from Python and TypeScript source modules",
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Scan source files into evidence.json")
    p_scan.add_argument("sources", nargs="+", help="Source files to scan (.py or .ts)")
    p_scan.add_argument("--tests", nargs="*", help="Test files to map")
    p_scan.add_argument("--name", default="my-library", help="Project name")
    p_scan.add_argument("--readme", help="Path to README.md")
    p_scan.add_argument("--output", "-o", help="Output path (default: evidence.json)")
    p_scan.add_argument("--language", help="Source language (python|typescript). Auto-inferred from file extensions when omitted.")
    p_scan.set_defaults(func=cmd_scan)

    p_spec = sub.add_parser("spec", help="Generate prompt.md from evidence.json")
    p_spec.add_argument("evidence", help="Path to evidence.json")
    p_spec.add_argument("--output", "-o", help="Output path (default: prompt.md)")
    p_spec.add_argument("--no-llm", action="store_true", help="Skip LLM, use deterministic rendering")
    p_spec.set_defaults(func=cmd_spec)

    p_bundle = sub.add_parser("bundle", help="Generate HUD v5 grader bundle from evidence.json")
    p_bundle.add_argument("evidence", help="Path to evidence.json")
    p_bundle.add_argument("--prompt", help="Path to validated prompt markdown (default: sibling prompt.md)")
    p_bundle.add_argument("--output", "-o", help="Optional bundle root to keep generated artifacts")
    p_bundle.add_argument("--no-llm", action="store_true", help="Skip LLM calls")
    p_bundle.add_argument("--no-alignment-autofix", action="store_true", help="Skip post-bundle alignment review/fix")
    p_bundle.add_argument("--alignment-max-rounds", type=int, default=2, help="Max alignment fix rounds (default: 2)")
    p_bundle.add_argument(
        "--allow-alignment-unavailable",
        action="store_true",
        help=(
            "Promote even when the alignment review never returned a parseable "
            f"response. Equivalent to {ALLOW_ALIGNMENT_UNAVAILABLE_ENV}=1. "
            "Coverage will be unknown; only use when the LLM provider is degraded."
        ),
    )
    p_bundle.set_defaults(func=cmd_bundle)

    p_run = sub.add_parser("run", help="Full pipeline: scan -> spec -> bundle")
    p_run.add_argument("sources", nargs="+", help="Source files to scan (.py or .ts)")
    p_run.add_argument("--tests", nargs="*", help="Test files to map")
    p_run.add_argument("--name", default="my-library", help="Project name")
    p_run.add_argument("--readme", help="Path to README.md")
    p_run.add_argument("--output", "-o", help="Optional bundle root to keep generated artifacts")
    p_run.add_argument("--no-llm", action="store_true", help="Skip LLM, use deterministic rendering")
    p_run.add_argument("--no-alignment-autofix", action="store_true", help="Skip post-bundle alignment review/fix")
    p_run.add_argument("--alignment-max-rounds", type=int, default=2, help="Max alignment fix rounds (default: 2)")
    p_run.add_argument(
        "--allow-alignment-unavailable",
        action="store_true",
        help=(
            "Promote even when the alignment review never returned a parseable "
            f"response. Equivalent to {ALLOW_ALIGNMENT_UNAVAILABLE_ENV}=1. "
            "Coverage will be unknown; only use when the LLM provider is degraded."
        ),
    )
    p_run.add_argument("--plain", action="store_true", help="Disable the rich TUI — emit plain, uncoloured text (CI-friendly). Also honoured via AST_PILOT_PLAIN=1.")
    p_run.add_argument("--language", help="Source language (python|typescript). Auto-inferred from file extensions when omitted.")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
