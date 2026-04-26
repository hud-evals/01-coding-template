"""Generate HUD task bundles for TypeScript/Node projects.

Produces a task package that stages a temporary Node project at grading
time using a manifest-driven approach that preserves repo-relative paths,
bundles transitive local dependencies of hidden tests, and runs
``vitest run`` per test file.
"""

from __future__ import annotations

from pathlib import Path

from .evidence import Evidence
from .node_bundle import audit_bare_imports, build_manifest
from .node_repo_support import detect_node_project
from .shared_utils import slug as _slug, write_text as _write


def generate_graders(
    ev: Evidence,
    output_dir: str | Path,
    prompt_md: str | None = None,
    source_paths: list[str | Path] | None = None,
    test_paths: list[str | Path] | None = None,
) -> dict[str, str]:
    """Generate a complete TypeScript task bundle under *output_dir*."""

    output_dir = Path(output_dir)
    slug = _slug(ev.project_name)
    task_dir = output_dir / "tasks" / slug
    tests_dir = task_dir / "tests"
    golden_dir = task_dir / "golden"
    config_dir = task_dir / "config"
    support_dir = task_dir / "support"

    for d in (task_dir, tests_dir, golden_dir, config_dir, support_dir):
        d.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    init_content = ""
    _write(task_dir / "__init__.py", init_content)
    files[f"tasks/{slug}/__init__.py"] = init_content

    prompt_content = _load_prompt(output_dir, ev.project_name, prompt_md=prompt_md)
    _write(task_dir / "prompt.md", prompt_content)
    files[f"tasks/{slug}/prompt.md"] = prompt_content

    resolved_sources = [Path(p) for p in (source_paths or [mod.path for mod in ev.source_files])]
    resolved_tests = [Path(p) for p in (test_paths or [])]

    ctx = detect_node_project(
        resolved_sources,
        require_lockfile=True,
        auto_generate_lockfile=True,
    )
    if not ctx.is_supported:
        reasons = "\n  - ".join(ctx.unsupported_reasons)
        raise ValueError(
            "Node project is not supported by the TS generator yet:\n  - "
            f"{reasons}\n"
            "Resolve the listed issues (or split the source repo) before regenerating."
        )
    repo_root = ctx.root

    config_paths: list[Path] = []
    for name in ("package.json", "package-lock.json", ".npmrc"):
        candidate = repo_root / name
        if candidate.exists():
            config_paths.append(candidate)
    if ctx.tsconfig_path and ctx.tsconfig_path.exists():
        config_paths.append(ctx.tsconfig_path)
    if ctx.vitest_config_path and ctx.vitest_config_path.exists():
        config_paths.append(ctx.vitest_config_path)

    manifest = build_manifest(
        slug=slug,
        repo_root=repo_root,
        source_paths=resolved_sources,
        test_paths=resolved_tests,
        config_paths=config_paths,
    )

    dep_issues = audit_bare_imports(manifest, ctx.package_json)
    if dep_issues:
        issues_str = "\n".join(f"  - {i}" for i in dep_issues)
        raise ValueError(
            f"Hidden test dependency audit failed:\n{issues_str}\n"
            "All bare imports used by hidden tests must be declared in package.json."
        )

    for rel, content in manifest.source_files.items():
        dest = golden_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/golden/{rel}"] = content

    for rel, content in manifest.test_files.items():
        dest = tests_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/tests/{rel}"] = content

    for rel, content in manifest.support_files.items():
        dest = support_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/support/{rel}"] = content

    for rel, content in manifest.config_files.items():
        name = Path(rel).name
        _write(config_dir / name, content)
        files[f"tasks/{slug}/config/{name}"] = content

    manifest_json = manifest.to_json()
    _write(task_dir / "node_bundle_manifest.json", manifest_json)
    files[f"tasks/{slug}/node_bundle_manifest.json"] = manifest_json

    test_rel_paths = sorted(manifest.test_files.keys())
    golden_rel_paths = sorted(manifest.source_files.keys())

    task_py = _generate_task_py(
        ev=ev,
        slug=slug,
        test_files=test_rel_paths,
        golden_files=golden_rel_paths,
    )
    _write(task_dir / "task.py", task_py)
    files[f"tasks/{slug}/task.py"] = task_py

    return files


def _generate_task_py(
    ev: Evidence,
    slug: str,
    test_files: list[str],
    golden_files: list[str],
) -> str:
    """Generate the task.py content for a TypeScript task (v2, sync-only shape).

    Mirrors the Python generator: tests/config/support/manifest live on disk
    under the task dir and are read at import time by helpers in
    ``tasks/_helpers/``. The scenario (``ast-pilot:coding-task-v2``) stages
    them at grade time so adding a new TS task is a single ``hud sync`` —
    no image rebuild.
    """

    del golden_files  # golden staging is driven by helpers.golden_workspace_validation

    weight_per_check = round(1.0 / max(len(test_files), 1), 4)

    grader_lines = [
        f"                vitest_grader({rel!r}, task_file=__file__, weight={weight_per_check}),"
        for rel in test_files
    ]

    lines = [
        f'"""Task: build {ev.project_name} (TypeScript) from scratch."""',
        "",
        "from hud import Environment",
        "from hud.eval.task import Task",
        "",
        "from tasks._helpers import (",
        "    golden_workspace_validation,",
        "    load_node_project,",
        "    load_prompt,",
        "    load_support,",
        "    resolve_env_name,",
        "    vitest_grader,",
        ")",
        "",
        'SCENARIO_ID = "ast-pilot:coding-task-v2"',
        "",
        "task = Task(",
        "    env=Environment(resolve_env_name(__file__)),",
        "    scenario=SCENARIO_ID,",
        "    args={",
        '        "prompt": load_prompt(__file__),',
        '        "graders": [',
    ]
    for line in grader_lines:
        lines.append(line[4:] if line.startswith("    ") else line)
    lines += [
        "        ],",
        '        "support": load_support(__file__),',
        '        "node_project": load_node_project(__file__),',
        "    },",
        ")",
        f"task.slug = {slug!r}",
        "task.validation = golden_workspace_validation(__file__)",
        "",
    ]
    return "\n".join(lines)


def _load_prompt(output_root: Path, project_name: str, prompt_md: str | None = None) -> str:
    if prompt_md:
        return prompt_md

    candidates = [
        output_root / "prompt.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")

    return f"# {project_name}\n\nImplement the TypeScript library described below.\n"
