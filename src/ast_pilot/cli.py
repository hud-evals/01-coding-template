"""CLI entrypoints for ast-pilot."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def cmd_scan(args: argparse.Namespace) -> None:
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
    from .spec_renderer import render_start_md

    ev = Evidence.load(args.evidence)
    out = args.output or "start.md"
    use_llm = not args.no_llm

    md = render_start_md(ev, output_path=out, use_llm=use_llm)
    print(f"Generated {len(md)} chars -> {out}")
    if not use_llm:
        print("  (LLM disabled, used deterministic fallback)")


def cmd_bundle(args: argparse.Namespace) -> None:
    from .evidence import Evidence
    from .grader_gen import generate_graders

    ev = Evidence.load(args.evidence)
    out_dir = args.output or "output"

    files = generate_graders(ev, output_dir=out_dir)
    print(f"Generated {len(files)} files in {out_dir}/:")
    for path in sorted(files):
        print(f"  {path}")

    promoted_to = _promote_generated_task(Path(out_dir), ev.project_name)
    if promoted_to is not None:
        print(f"Promoted task package -> {promoted_to}")


def cmd_run(args: argparse.Namespace) -> None:
    """Full pipeline: scan -> spec -> bundle in one shot."""

    from .scanner import scan
    from .spec_renderer import render_start_md
    from .grader_gen import generate_graders

    source_paths = [Path(p) for p in args.sources]
    test_paths = [Path(p) for p in args.tests] if args.tests else None
    readme = Path(args.readme) if args.readme else None
    out_dir = Path(args.output or f"output/{args.name}")
    use_llm = not args.no_llm

    print(f"=== Scanning {len(source_paths)} source files ===")
    ev = scan(
        source_paths=source_paths,
        test_paths=test_paths,
        project_name=args.name,
        readme_path=readme,
    )
    print(
        f"  {ev.total_loc} LOC, {sum(len(m.classes) for m in ev.source_files)} classes, "
        f"{sum(len(m.functions) for m in ev.source_files)} functions, "
        f"{len(ev.tests)} tests"
    )

    ev.save(out_dir / "evidence.json")

    print(f"\n=== Generating start.md {'(with LLM)' if use_llm else '(deterministic)'} ===")
    md = render_start_md(ev, output_path=out_dir / "start.md", use_llm=use_llm)
    print(f"  {len(md)} chars written")

    print("\n=== Validating start.md against evidence ===")
    from .validator import validate

    vr = validate(ev, out_dir / "start.md")
    print(f"  {vr.summary()}")

    max_fix_rounds = 3
    dismissed_keys: set[str] = set()
    for fix_round in range(1, max_fix_rounds + 1):
        real_errors = [
            issue
            for issue in vr.issues
            if issue.severity == "error"
            and f"{issue.line}:{issue.message[:60]}" not in dismissed_keys
        ]
        if not real_errors or not use_llm:
            break

        print(f"\n=== Fix round {fix_round}/{max_fix_rounds}: fixing {len(real_errors)} errors ===")
        from .fixer import fix_issues
        from .validator import ValidationResult

        filtered_vr = ValidationResult(issues=real_errors)
        _, actions = fix_issues(ev, out_dir / "start.md", filtered_vr)
        for a in actions:
            status = a.action.upper()
            if a.action == "fixed":
                print(f"  [{status}] {a.issue.message}")
                print(f"    old: {a.old_text[:80]}")
                print(f"    new: {a.new_text[:80]}")
            elif a.action == "dismissed":
                print(f"  [{status}] {a.issue.message}")
                print(f"    reason: {a.reason}")
                dismissed_keys.add(f"{a.issue.line}:{a.issue.message[:60]}")
            else:
                print(f"  [{status}] {a.issue.message}: {a.reason}")

        print(f"\n=== Re-validating (round {fix_round}) ===")
        vr = validate(ev, out_dir / "start.md")
        remaining = [
            i
            for i in vr.issues
            if i.severity == "error"
            and f"{i.line}:{i.message[:60]}" not in dismissed_keys
        ]
        if remaining:
            print(f"  {len(remaining)} errors remaining")
            for i in remaining:
                print(f"    [ERROR] {i.message}")
        else:
            print(f"  PASSED (0 errors, {len(dismissed_keys)} dismissed)")

    print("\n=== Generating task bundle ===")
    files = generate_graders(
        ev,
        output_dir=out_dir,
        source_paths=source_paths,
        test_paths=test_paths,
    )
    for path in sorted(files):
        print(f"  {path}")

    promoted_to = _promote_generated_task(out_dir, ev.project_name)
    if promoted_to is not None:
        print(f"\nPromoted task package -> {promoted_to}")

    print(f"\nDone. Output in {out_dir}/")


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


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


def _pkg_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ast-pilot",
        description="Scan Python repos and generate Claire-style task specs + HUD v5 graders",
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Scan source files into evidence.json")
    p_scan.add_argument("sources", nargs="+", help="Python source files to scan")
    p_scan.add_argument("--tests", nargs="*", help="Test files to map")
    p_scan.add_argument("--name", default="my-library", help="Project name")
    p_scan.add_argument("--readme", help="Path to README.md")
    p_scan.add_argument("--output", "-o", help="Output path (default: evidence.json)")
    p_scan.set_defaults(func=cmd_scan)

    p_spec = sub.add_parser("spec", help="Generate start.md from evidence.json")
    p_spec.add_argument("evidence", help="Path to evidence.json")
    p_spec.add_argument("--output", "-o", help="Output path (default: start.md)")
    p_spec.add_argument("--no-llm", action="store_true", help="Skip LLM, use deterministic rendering")
    p_spec.set_defaults(func=cmd_spec)

    p_bundle = sub.add_parser("bundle", help="Generate HUD v5 grader bundle from evidence.json")
    p_bundle.add_argument("evidence", help="Path to evidence.json")
    p_bundle.add_argument("--output", "-o", help="Output directory (default: output/)")
    p_bundle.set_defaults(func=cmd_bundle)

    p_run = sub.add_parser("run", help="Full pipeline: scan -> spec -> bundle")
    p_run.add_argument("sources", nargs="+", help="Python source files to scan")
    p_run.add_argument("--tests", nargs="*", help="Test files to map")
    p_run.add_argument("--name", default="my-library", help="Project name")
    p_run.add_argument("--readme", help="Path to README.md")
    p_run.add_argument("--output", "-o", help="Output directory")
    p_run.add_argument("--no-llm", action="store_true", help="Skip LLM, use deterministic rendering")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
