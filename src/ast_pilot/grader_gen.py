"""Generate HUD task bundles with hidden support dependencies."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from .evidence import Evidence
from .repo_support import (
    RepoContext,
    ancestor_package_paths,
    collect_internal_imports,
    find_repo_context,
    load_project_dependencies,
    module_name_from_path,
    module_path_from_name,
    reference_to_module,
    resolve_from_module,
    resolve_module_candidates,
)
from .shared_utils import pkg_name as _pkg_name, slug as _slug, write_text as _write

WORKSPACE_DIR = "/home/ubuntu/workspace"
SMALL_TEST_SUPPORT_MAX_LINES = 400
ALLOW_UNSUPPORTED_TEST_REFS_ENV = "AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS"
REPO_ROOT_ENV = "AST_PILOT_REPO_ROOT"
_PATH_ANCHOR_NAMES = frozenset({
    "REPO_ROOT", "HERE", "BASE_DIR", "ROOT_DIR", "PROJECT_ROOT",
    "REPO_DIR", "WORKSPACE", "WORKSPACE_DIR", "SRC_ROOT", "SOURCE_ROOT", "ROOT",
})


@dataclass(frozen=True)
class TaskPaths:
    output_root: Path
    slug: str
    task_dir: Path
    tests_dir: Path
    golden_dir: Path
    support_dir: Path


@dataclass(frozen=True)
class SourceContext:
    repo: RepoContext | None
    source_paths: tuple[Path, ...]
    test_paths: tuple[Path, ...]
    target_module_map: dict[str, str]
    """Maps original dotted module name (e.g. ``agent.retry_utils``) to the
    workspace-relative path the agent must create (``agent/retry_utils.py``).
    Flat single-file scans collapse this to ``{stem: stem.py}``."""

    support_modules: frozenset[str]
    support_requirements: tuple[str, ...]
    bundled_assets: tuple[tuple[str, Path], ...] = ()
    """Pairs of ``(repo-relative path, absolute source path)`` for every
    non-code file we ship under ``support/``.  Populated from
    :attr:`ast_pilot.evidence.Evidence.runtime_assets` during bundling."""

    agent_created_assets: tuple[str, ...] = ()
    """Repo-relative paths for assets the agent must create themselves."""


def generate_graders(
    ev: Evidence,
    output_dir: str | Path,
    prompt_md: str | None = None,
    source_paths: list[str | Path] | None = None,
    test_paths: list[str | Path] | None = None,
) -> dict[str, str]:
    """Generate a complete task bundle under output_dir."""

    paths = _ensure_task_paths(Path(output_dir), ev.project_name)
    files: dict[str, str] = {}

    source_ctx = _build_source_context(ev, source_paths, test_paths)
    primary_module = _primary_module_name(ev, source_ctx)

    init_content = ""
    _write(paths.task_dir / "__init__.py", init_content)
    files[f"tasks/{paths.slug}/__init__.py"] = init_content

    prompt_content = _load_prompt(paths.output_root, ev.project_name, prompt_md=prompt_md)
    _write(paths.task_dir / "prompt.md", prompt_content)
    files[f"tasks/{paths.slug}/prompt.md"] = prompt_content

    files.update(_write_golden_files(paths, source_ctx))
    files.update(_write_support_files(paths, source_ctx))
    test_files = _write_test_files(paths, ev, source_ctx, primary_module)
    for generated_test in sorted(paths.tests_dir.glob("*.py")):
        files[f"tasks/{paths.slug}/tests/{generated_test.name}"] = generated_test.read_text(encoding="utf-8")

    golden_rel_paths = sorted(
        path.relative_to(paths.golden_dir).as_posix()
        for path in paths.golden_dir.rglob("*.py")
    )
    task_py = _generate_task_py(
        ev=ev,
        slug=paths.slug,
        test_files=test_files,
        golden_files=golden_rel_paths,
        support_enabled=bool(source_ctx.support_modules),
        has_hidden_requirements=bool(source_ctx.support_requirements),
        bundled_asset_paths=tuple(rel for rel, _ in source_ctx.bundled_assets),
    )
    _write(paths.task_dir / "task.py", task_py)
    files[f"tasks/{paths.slug}/task.py"] = task_py

    return files


def _ensure_task_paths(output_root: Path, project_name: str) -> TaskPaths:
    slug = _slug(project_name)
    task_dir = output_root / "tasks" / slug
    tests_dir = task_dir / "tests"
    golden_dir = task_dir / "golden"
    support_dir = task_dir / "support"
    for directory in (task_dir, tests_dir, golden_dir, support_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return TaskPaths(
        output_root=output_root,
        slug=slug,
        task_dir=task_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        support_dir=support_dir,
    )


def _build_source_context(
    ev: Evidence,
    source_paths: list[str | Path] | None,
    test_paths: list[str | Path] | None,
) -> SourceContext:
    resolved_sources = _resolve_existing_paths(source_paths or [mod.path for mod in ev.source_files], "source")
    resolved_tests = _resolve_existing_paths(test_paths or [], "test")
    repo = find_repo_context([*resolved_sources, *resolved_tests])
    target_module_map = _build_target_module_map(resolved_sources, repo)

    support_modules = frozenset(_build_support_module_closure(resolved_sources, repo, set(target_module_map)))
    if repo is not None and resolved_tests:
        support_modules = frozenset(
            set(support_modules)
            | _collect_small_test_support_modules(resolved_tests, repo, set(target_module_map))
        )
    support_requirements = tuple(load_project_dependencies(repo)) if repo is not None and support_modules else ()

    bundled_assets, agent_created_assets = _resolve_runtime_assets(ev, repo)

    return SourceContext(
        repo=repo,
        source_paths=resolved_sources,
        test_paths=resolved_tests,
        target_module_map=target_module_map,
        support_modules=support_modules,
        support_requirements=support_requirements,
        bundled_assets=bundled_assets,
        agent_created_assets=agent_created_assets,
    )


def _resolve_runtime_assets(
    ev: Evidence,
    repo: RepoContext | None,
) -> tuple[tuple[tuple[str, Path], ...], tuple[str, ...]]:
    """Split ``ev.runtime_assets`` into on-disk files we can bundle and
    agent-created files we must only describe in the prompt."""

    if not ev.runtime_assets:
        return (), ()

    bundled: list[tuple[str, Path]] = []
    to_create: list[str] = []
    for asset in ev.runtime_assets:
        if asset.kind == "bundled" and repo is not None:
            abs_path = (repo.root / asset.rel_path).resolve()
            if abs_path.is_file():
                bundled.append((asset.rel_path, abs_path))
                continue
        to_create.append(asset.rel_path)

    return tuple(sorted(bundled)), tuple(sorted(to_create))


def _resolve_existing_paths(paths: list[str | Path], label: str) -> tuple[Path, ...]:
    resolved: list[Path] = []
    missing: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            missing.append(str(path))
            continue
        resolved.append(path.resolve())

    if missing:
        rendered = ", ".join(missing[:5])
        if len(missing) > 5:
            rendered += ", ..."
        raise ValueError(f"Missing {label} path(s) required for task bundling: {rendered}")

    return tuple(resolved)


def _build_support_module_closure(
    source_paths: tuple[Path, ...],
    repo: RepoContext | None,
    target_modules: set[str],
) -> set[str]:
    if repo is None:
        return set()

    closure: set[str] = set()
    pending: list[str] = []
    for source_path in source_paths:
        pending.extend(sorted(collect_internal_imports(source_path, repo)))

    while pending:
        module_name = pending.pop()
        if module_name in closure or module_name in target_modules:
            continue
        module_path = repo.module_index.get(module_name)
        if module_path is None:
            continue
        closure.add(module_name)
        for dep in collect_internal_imports(module_path, repo):
            if dep not in closure and dep not in target_modules:
                pending.append(dep)

    return closure


def _collect_small_test_support_modules(
    test_paths: tuple[Path, ...],
    repo: RepoContext,
    target_modules: set[str],
) -> set[str]:
    candidates: set[str] = set()

    for test_path in test_paths:
        current_module = module_name_from_path(test_path, repo.root)
        if current_module is None:
            continue

        try:
            tree = ast.parse(test_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    candidates.update(resolve_module_candidates(alias.name, repo.module_index))
            elif isinstance(node, ast.ImportFrom):
                module_name = resolve_from_module(current_module, node.module, node.level)
                if not module_name:
                    continue
                candidates.update(resolve_module_candidates(module_name, repo.module_index))

    supported: set[str] = set()
    for module_name in sorted(candidates):
        if module_name in target_modules:
            continue
        module_path = repo.module_index.get(module_name)
        if module_path is None:
            continue
        if _line_count(module_path) > SMALL_TEST_SUPPORT_MAX_LINES:
            continue

        nested_internal = collect_internal_imports(module_path, repo) - target_modules
        if nested_internal:
            continue

        supported.add(module_name)

    return supported


def _load_prompt(output_root: Path, project_name: str, prompt_md: str | None = None) -> str:
    if prompt_md is not None:
        return prompt_md
    start_md = output_root / "prompt.md"
    if start_md.exists():
        return start_md.read_text(encoding="utf-8")
    raise ValueError(
        f"Missing prompt markdown for '{project_name}'. Pass prompt_md explicitly or provide {start_md}."
    )


def _write_golden_files(paths: TaskPaths, source_ctx: SourceContext) -> dict[str, str]:
    files: dict[str, str] = {}
    workspace_rel_by_abs = _workspace_rel_by_abs_path(source_ctx)
    for source_path in source_ctx.source_paths:
        content = source_path.read_text(encoding="utf-8", errors="replace")
        content = _rewrite_source_relative_imports(content, source_ctx.repo, source_path)
        workspace_rel = workspace_rel_by_abs.get(source_path.resolve(), source_path.name)
        destination = paths.golden_dir / workspace_rel
        _write(destination, content)
        files[f"tasks/{paths.slug}/golden/{workspace_rel}"] = content
    return files


def _workspace_rel_by_abs_path(source_ctx: SourceContext) -> dict[Path, str]:
    """Map resolved source abs path → its workspace-relative target path."""
    result: dict[Path, str] = {}
    for source_path in source_ctx.source_paths:
        if source_ctx.repo is not None:
            module_name = module_name_from_path(
                source_path,
                source_ctx.repo.root,
                import_roots=source_ctx.repo.import_roots,
            )
        else:
            module_name = None
        rel = source_ctx.target_module_map.get(module_name or "", "")
        result[source_path.resolve()] = rel or source_path.name
    return result


def _rewrite_source_relative_imports(
    content: str,
    repo: RepoContext | None,
    source_path: Path,
) -> str:
    """Rewrite ``from .X import Y`` to the absolute equivalent.

    After the golden source is flattened into the workspace, relative
    imports can't resolve (the file no longer lives inside its original
    package). Rewriting them to absolute form lets the workspace file
    find its package-internal dependencies via the support/ tree, which
    preserves the original package layout.
    """

    if repo is None:
        return content

    current_module = module_name_from_path(
        source_path, repo.root, import_roots=repo.import_roots
    )
    if not current_module or "." not in current_module:
        return content

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    rewrites: list[tuple[int, int, str]] = []
    lines = content.splitlines(keepends=True)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            continue
        target = resolve_from_module(current_module, node.module, node.level)
        if not target:
            continue

        end_line = node.end_lineno or node.lineno
        first_line = lines[node.lineno - 1]
        indent = first_line[: len(first_line) - len(first_line.lstrip())]

        rendered_names: list[str] = []
        for alias in node.names:
            if alias.asname:
                rendered_names.append(f"{alias.name} as {alias.asname}")
            else:
                rendered_names.append(alias.name)
        replacement = f"{indent}from {target} import {', '.join(rendered_names)}\n"
        rewrites.append((node.lineno, end_line, replacement))

    if not rewrites:
        return content

    for start_line, end_line, replacement in sorted(rewrites, reverse=True):
        lines[start_line - 1 : end_line] = [replacement]
    return "".join(lines)


def _write_support_files(paths: TaskPaths, source_ctx: SourceContext) -> dict[str, str]:
    files: dict[str, str] = {}
    repo = source_ctx.repo
    has_modules = repo is not None and bool(source_ctx.support_modules)

    if has_modules:
        modules_to_copy = set(source_ctx.support_modules)
        for module_name in source_ctx.support_modules:
            modules_to_copy.update(ancestor_package_paths(module_name, repo.module_index))

        for target_module in source_ctx.target_module_map:
            modules_to_copy.update(ancestor_package_paths(target_module, repo.module_index))

        # Packages that contain a workspace target must stay *namespace*
        # packages at grading time so Python merges the workspace and
        # support directories onto one import root. Shipping a concrete
        # ``pkg/__init__.py`` would turn ``pkg`` into a regular package,
        # and Python would refuse to look outside that one directory for
        # submodules like the agent's ``pkg/calc.py``.
        overlap_packages = _packages_overlapping_with_targets(
            source_ctx.target_module_map,
            repo.module_index,
        )

        # Target modules are written at their real workspace path by the
        # agent, not via a shim under support/, so we skip them here.
        for module_name in sorted(modules_to_copy - set(source_ctx.target_module_map)):
            original_path = repo.module_index.get(module_name)
            if original_path is None:
                continue

            if (
                original_path.name == "__init__.py"
                and module_name in overlap_packages
            ):
                continue

            content = original_path.read_text(encoding="utf-8", errors="replace")
            relative_path = module_path_from_name(module_name, original_path)
            destination = paths.support_dir / relative_path
            _write(destination, content)
            files[f"tasks/{paths.slug}/support/{relative_path.as_posix()}"] = content

        if source_ctx.support_requirements:
            requirements = "\n".join(source_ctx.support_requirements) + "\n"
            _write(paths.task_dir / "requirements.hidden.txt", requirements)
            files[f"tasks/{paths.slug}/requirements.hidden.txt"] = requirements

    for rel_path, absolute_path in source_ctx.bundled_assets:
        try:
            content = absolute_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        destination = paths.support_dir / rel_path
        _write(destination, content)
        files[f"tasks/{paths.slug}/support/{rel_path}"] = content

    return files


def _packages_overlapping_with_targets(
    target_module_map: dict[str, str],
    module_index: dict[str, Path],
) -> set[str]:
    """Return the set of package modules that contain one or more workspace
    target modules — their ``__init__.py`` files must be skipped at bundle
    time so runtime support + workspace can merge as a namespace package."""

    overlap: set[str] = set()
    for target_module in target_module_map:
        for ancestor in ancestor_package_paths(target_module, module_index):
            overlap.add(ancestor)
    return overlap


def _write_test_files(
    paths: TaskPaths,
    ev: Evidence,
    source_ctx: SourceContext,
    primary_module: str,
) -> list[str]:
    files: list[str] = []
    if source_ctx.test_paths:
        available_modules = source_ctx.support_modules | set(source_ctx.target_module_map)
        allow_unsupported_test_refs = _allow_unsupported_test_refs()
        cross_module_warnings: list[str] = []
        for test_path in source_ctx.test_paths:
            original = test_path.read_text(encoding="utf-8", errors="replace")
            rewritten = _rewrite_repo_root_assignments(original)
            rewritten = _guard_unsupported_test_refs(
                original_content=original,
                rewritten_content=rewritten,
                test_path=test_path,
                repo=source_ctx.repo,
                available_modules=available_modules,
                allow_downgrades=allow_unsupported_test_refs,
            )
            rewritten = _prepend_workspace_syspath(rewritten)
            warnings, skip_marks = _detect_cross_module_path_access(rewritten, test_path)
            cross_module_warnings.extend(warnings)
            if skip_marks and allow_unsupported_test_refs:
                rewritten = _insert_skip_marks(rewritten, skip_marks)
            destination = paths.tests_dir / test_path.name
            _write(destination, rewritten)
            files.append(test_path.name)
        if cross_module_warnings and not allow_unsupported_test_refs:
            # Same policy as `_guard_unsupported_test_refs`: hard-fail by default
            # so a generator run can't silently ship a task with weakened test
            # coverage. Set AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1 to downgrade
            # to pytest.mark.skip with a visible warning instead.
            raise ValueError(
                "Hidden tests use Path(__file__).parents[N] which resolves to /tmp at "
                "grading time, not the agent workspace. Set "
                f"{ALLOW_UNSUPPORTED_TEST_REFS_ENV}=1 to auto-skip these tests "
                "(weakens coverage) or rewrite the offending tests to avoid "
                "cross-module path walks. Offending references:\n  - "
                + "\n  - ".join(cross_module_warnings)
            )
        if cross_module_warnings:
            from .tui import ui as _ui
            _ui().warn(
                "hidden tests use Path(__file__).parents[N] — auto-skipped at "
                f"grading time (pytest.mark.skip) because {ALLOW_UNSUPPORTED_TEST_REFS_ENV}=1. "
                "Coverage is weakened; remove the env var to fail generation instead."
            )
            for warning in cross_module_warnings:
                _ui().detail(warning)
        return files

    synthetic_stem = primary_module.replace(".", "_")
    synthetic_name = f"test_{synthetic_stem}.py"
    synthetic = _generate_synthetic_tests(ev, primary_module)
    _write(paths.tests_dir / synthetic_name, synthetic)
    files.append(synthetic_name)
    return files


def _generate_task_py(
    ev: Evidence,
    slug: str,
    test_files: list[str],
    golden_files: list[str],
    support_enabled: bool,
    has_hidden_requirements: bool = False,
    bundled_asset_paths: tuple[str, ...] = (),
) -> str:
    """Emit a task.py that inlines all artifacts into ``Task.args``.

    The generated task calls helpers from :mod:`tasks._helpers` to read
    prompt/support/tests/requirements at task-import time and embed them
    into ``Task.args``; ``golden`` pre-staging flows through
    ``Task.validation`` as a single bash :class:`MCPToolCall` with base64
    content inlined. ``hud sync`` ships everything — no image rebuild is
    needed for task-side changes.

    The ``support_enabled``, ``bundled_asset_paths`` and
    ``has_hidden_requirements`` params are kept for call-site compatibility;
    the v2 template discovers those dirs/files directly at task-import time
    via the helpers, so it does not need to branch on them at generation.
    """
    del golden_files, support_enabled, bundled_asset_paths, has_hidden_requirements  # inferred at runtime

    weight_per_check = round(1.0 / max(len(test_files), 1), 4)

    grader_lines: list[str] = []
    for test_file in test_files:
        grader_lines.append(
            f"                pytest_grader({test_file!r}, task_file=__file__, weight={weight_per_check}),"
        )

    lines = [
        f'"""Task: build {ev.project_name} from scratch."""',
        "",
        "from hud.eval.task import Task",
        "",
        "from tasks._helpers import (",
        "    golden_validation,",
        "    load_prompt,",
        "    load_requirements,",
        "    load_support,",
        "    pytest_grader,",
        "    resolve_env_name,",
        ")",
        "",
        'SCENARIO_ID = "ast-pilot:coding-task-v2"',
        "",
        "task = Task(",
        # Pass env as a dict, NOT as Environment(...). The Task.env validator's
        # dict-path calls `connect_hub(name)` automatically; the Environment-instance
        # path does not, which breaks `hud eval .` (local task.py load) because
        # the env has no remote connection and routing falls back to a broken
        # local-render path. Dict-form is safe for both local-file and
        # synced-taskset eval flows.
        '    env={"name": resolve_env_name(__file__)},',
        "    scenario=SCENARIO_ID,",
        "    args={",
        '        "prompt": load_prompt(__file__),',
        '        "graders": [',
    ]
    # grader_lines is indented one level deeper in the v1 template; dedent
    # each entry by 4 spaces so it lines up with the new top-level task block.
    for line in grader_lines:
        lines.append(line[4:] if line.startswith("    ") else line)
    lines += [
        "        ],",
        '        "support": load_support(__file__),',
        '        "hidden_requirements": load_requirements(__file__),',
        "    },",
        ")",
        f"task.slug = {slug!r}",
        "task.validation = golden_validation(__file__)",
        "",
    ]
    return "\n".join(lines)


def _generate_synthetic_tests(ev: Evidence, module_name: str) -> str:
    lines = [
        f'"""Synthetic tests for {module_name}."""',
        "",
        "import sys",
        f'sys.path.insert(0, "{WORKSPACE_DIR}")',
        "",
        f"from {module_name} import *",
        "",
    ]

    for mod in ev.source_files:
        for cls in mod.classes:
            if cls.name.startswith("_"):
                continue
            lines.append(f"def test_{cls.name.lower()}_available():")
            lines.append(f"    assert {cls.name} is not None")
            lines.append("")

        for fn in mod.functions:
            if fn.name.startswith("_"):
                continue
            lines.append(f"def test_{fn.name}_callable():")
            lines.append(f"    assert callable({fn.name})")
            lines.append("")

        for name, value in mod.constants:
            if name.startswith("_") or len(value) >= 80 or "\n" in value or "{" in value:
                continue
            lines.append(f"def test_constant_{name.lower()}():")
            lines.append(f"    assert {name} == {value}")
            lines.append("")

    return "\n".join(lines)


def _rewrite_repo_root_assignments(content: str) -> str:
    """Rewrite module-level ``REPO_ROOT``/``HERE``/... assignments that derive
    from ``__file__`` to read ``AST_PILOT_REPO_ROOT`` instead.

    The generated ``task.py`` sets that env var to the agent workspace root,
    so tests that previously resolved paths relative to the test file
    (which lives in ``/tmp/`` at grading time) now resolve relative to the
    workspace where the agent wrote their files.
    """

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content

    rewrites: list[tuple[int, int, str]] = []
    for node in ast.iter_child_nodes(tree):
        name, end_line = _extract_path_anchor_assignment(node)
        if name is None:
            continue

        first_line = content.splitlines(keepends=True)[node.lineno - 1]
        indent = first_line[: len(first_line) - len(first_line.lstrip())]
        replacement = (
            f'{indent}{name} = os.environ.get('
            f'"{REPO_ROOT_ENV}", "{WORKSPACE_DIR}")'
        )
        rewrites.append((node.lineno, end_line, replacement))

    if not rewrites:
        return content

    lines = content.splitlines(keepends=True)
    for start_line, end_line, replacement in sorted(rewrites, reverse=True):
        original_end = lines[end_line - 1] if end_line - 1 < len(lines) else ""
        trailing = "\n" if original_end.endswith("\n") else ""
        lines[start_line - 1:end_line] = [replacement + trailing]
    rewritten = "".join(lines)

    if "import os" not in rewritten:
        rewritten = _ensure_os_import(rewritten)
    return rewritten


def _extract_path_anchor_assignment(node: ast.AST) -> tuple[str | None, int]:
    """If *node* is a path-anchor assignment derived from ``__file__``,
    return ``(name, end_line)``; otherwise ``(None, 0)``."""

    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in _PATH_ANCHOR_NAMES:
            if _references_dunder_file(node.value):
                return target.id, node.end_lineno or node.lineno
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if node.target.id in _PATH_ANCHOR_NAMES and node.value is not None:
            if _references_dunder_file(node.value):
                return node.target.id, node.end_lineno or node.lineno
    return None, 0


def _references_dunder_file(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "__file__":
            return True
    return False


def _detect_cross_module_path_access(
    content: str, test_path: Path
) -> tuple[list[str], list[tuple[int, str]]]:
    """Find ``Path(__file__).parents[N]`` patterns that walk outside the
    test's own directory. Tests are staged at ``/tmp/<name>.py`` at grading
    time, so any filesystem anchor derived from ``__file__`` resolves to
    ``/tmp`` — not the agent workspace or a sibling module tree.

    Returns ``(warnings, skip_marks)``. ``skip_marks`` is a list of
    ``(lineno, reason)`` for each test method containing the offending
    expression, ready to feed to :func:`_insert_skip_marks`.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [], []

    warnings: list[str] = []
    skip_marks: list[tuple[int, str]] = []
    for fn in _iter_test_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Subscript):
                continue
            target = node.value
            if not isinstance(target, ast.Attribute) or target.attr != "parents":
                continue
            if not _references_dunder_file(target.value):
                continue
            index_repr = "?"
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                index_repr = str(node.slice.value)
            reason = (
                f"cross-module Path(__file__).parents[{index_repr}] "
                "— unsupported at grading time"
            )
            warnings.append(
                f"{test_path.name}:{node.lineno} uses Path(__file__).parents[{index_repr}] "
                "— resolves to /tmp at grading time, not the agent workspace"
            )
            skip_marks.append((fn.lineno, reason))
            break
    return warnings, skip_marks


def _iter_test_functions(tree: ast.AST):
    """Yield every ``def test_*`` FunctionDef in ``tree``, nested or not."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            yield node


def _insert_skip_marks(content: str, marks: list[tuple[int, str]]) -> str:
    """Prepend ``@pytest.mark.skip(reason=...)`` decorators to test methods."""
    if not marks:
        return content
    lines = content.splitlines()
    for offset, (lineno, reason) in enumerate(sorted(marks, key=lambda item: item[0])):
        index = lineno - 1 + offset
        if index < 0 or index >= len(lines):
            continue
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        decorator = f'{indent}@__import__("pytest").mark.skip(reason={reason!r})'
        if index > 0 and lines[index - 1].strip() == decorator.strip():
            continue
        lines.insert(index, decorator)
    return "\n".join(lines)


def _ensure_os_import(content: str) -> str:
    lines = content.splitlines(keepends=True)
    insert_at = 0
    for idx, line in enumerate(lines[:25]):
        stripped = line.strip()
        if stripped.startswith("from __future__"):
            insert_at = idx + 1
            continue
        if idx == 0 and stripped.startswith(('"""', "'''")):
            quote = stripped[:3]
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                insert_at = idx + 1
                continue
            for scan_idx in range(idx + 1, len(lines)):
                if lines[scan_idx].strip().endswith(quote):
                    insert_at = scan_idx + 1
                    break
            break
    lines.insert(insert_at, "import os\n")
    return "".join(lines)


def _guard_unsupported_test_refs(
    original_content: str,
    rewritten_content: str,
    test_path: Path,
    repo: RepoContext | None,
    available_modules: set[str],
    allow_downgrades: bool,
) -> str:
    if repo is None:
        return rewritten_content

    try:
        tree = ast.parse(original_content)
    except SyntaxError:
        return rewritten_content

    current_module = module_name_from_path(test_path, repo.root)
    if current_module is None:
        return rewritten_content

    module_level_refs: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        module_level_refs.update(_collect_internal_refs_from_node(node, current_module, repo))

    unsupported_module_refs = sorted(ref for ref in module_level_refs if ref not in available_modules)
    marks: list[tuple[int, str]] = []
    handled_test_lines: set[int] = set()
    failures: list[str] = []

    if unsupported_module_refs:
        failures.append(
            f"{test_path.name} module scope depends on unsupported internal module(s): "
            f"{', '.join(unsupported_module_refs)}"
        )

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        helper_refs: set[str] = set()
        test_methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for child in node.body:
            if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if child.name.startswith("test"):
                test_methods.append(child)
            else:
                helper_refs.update(_collect_internal_refs_from_node(child, current_module, repo))

        unsupported_helpers = {ref for ref in helper_refs if ref not in available_modules}
        for test_method in test_methods:
            refs = _collect_internal_refs_from_node(test_method, current_module, repo)
            unsupported = sorted((refs | unsupported_helpers) - available_modules)
            if unsupported:
                marks.append((test_method.lineno, _unsupported_reason(unsupported)))
                failures.append(
                    f"{test_path.name}:{test_method.lineno} ({node.name}.{test_method.name}) depends on "
                    f"unsupported internal module(s): {', '.join(unsupported)}"
                )
                handled_test_lines.add(test_method.lineno)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or not node.name.startswith("test"):
            continue
        if node.lineno in handled_test_lines:
            continue
        refs = _collect_internal_refs_from_node(node, current_module, repo)
        unsupported = sorted(ref for ref in refs if ref not in available_modules)
        if unsupported:
            marks.append((node.lineno, _unsupported_reason(unsupported)))
            failures.append(
                f"{test_path.name}:{node.lineno} ({node.name}) depends on unsupported internal module(s): "
                f"{', '.join(unsupported)}"
            )

    if failures and not allow_downgrades:
        joined = "\n".join(f"  - {failure}" for failure in failures)
        raise ValueError(
            "Hidden tests reference unsupported internal modules.\n"
            "Refusing to silently inject skip/xfail markers.\n"
            f"{joined}\n"
            f"Set {ALLOW_UNSUPPORTED_TEST_REFS_ENV}=1 to allow downgraded coverage intentionally."
        )

    guarded = rewritten_content
    if unsupported_module_refs:
        guarded = _insert_module_level_skip(guarded, unsupported_module_refs)

    if failures and allow_downgrades:
        guarded = _prepend_unsupported_test_warning(guarded, failures)

    return _insert_function_marks(guarded, marks)


def _collect_internal_refs_from_node(node: ast.AST, current_module: str, repo: RepoContext) -> set[str]:
    refs: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                refs.update(resolve_module_candidates(alias.name, repo.module_index))
        elif isinstance(child, ast.ImportFrom):
            module_name = resolve_from_module(current_module, child.module, child.level)
            if not module_name:
                continue
            refs.update(resolve_module_candidates(module_name, repo.module_index))
            for alias in child.names:
                if alias.name == "*":
                    continue
                refs.update(resolve_module_candidates(f"{module_name}.{alias.name}", repo.module_index))
        elif isinstance(child, ast.Call) and child.args:
            first_arg = child.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                module_ref = reference_to_module(first_arg.value.strip(), repo.module_index)
                if module_ref:
                    refs.add(module_ref)
    return refs


def _insert_module_level_skip(content: str, unsupported_modules: list[str]) -> str:
    lines = content.splitlines()
    insert_at = _find_header_insert_at(lines)
    skip_line = f'__import__("pytest").skip({_unsupported_reason(unsupported_modules)!r}, allow_module_level=True)'
    new_lines = lines[:insert_at] + [skip_line, ""] + lines[insert_at:]
    return "\n".join(new_lines)


def _insert_function_marks(content: str, marks: list[tuple[int, str]]) -> str:
    if not marks:
        return content

    lines = content.splitlines()
    for offset, (lineno, reason) in enumerate(sorted(marks, key=lambda item: item[0])):
        index = lineno - 1 + offset
        if index < 0 or index >= len(lines):
            continue
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        decorator = f'{indent}@__import__("pytest").mark.xfail(reason={reason!r})'
        if index > 0 and lines[index - 1].strip() == decorator.strip():
            continue
        lines.insert(index, decorator)
    return "\n".join(lines)


def _prepend_unsupported_test_warning(content: str, failures: list[str]) -> str:
    lines = content.splitlines()
    insert_at = _find_header_insert_at(lines)
    warning_lines = [
        "# WARNING: ast-pilot downgraded unsupported hidden-test coverage.",
        f"# Set {ALLOW_UNSUPPORTED_TEST_REFS_ENV}=0 or unset it to fail instead.",
    ]
    for failure in failures[:5]:
        warning_lines.append(f"# {failure}")
    warning_lines.append("")
    return "\n".join(lines[:insert_at] + warning_lines + lines[insert_at:])


def _prepend_workspace_syspath(content: str) -> str:
    if WORKSPACE_DIR in content and "sys.path.insert" in content:
        return content

    lines = content.splitlines()
    insert_at = _find_header_insert_at(lines)

    # Always emit `import sys` in the header even when an existing `import sys`
    # appears later in the file. Stripping it and relying on the later import
    # puts the `sys.path.insert(...)` call above its own binding — the test
    # module fails to load with NameError. Re-importing `sys` is a no-op.
    header = ["import sys", f'sys.path.insert(0, "{WORKSPACE_DIR}")', ""]
    return "\n".join(lines[:insert_at] + header + lines[insert_at:])


def _find_header_insert_at(lines: list[str]) -> int:
    insert_at = 0
    in_docstring = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx == 0 and stripped.startswith(('"""', "'''")):
            quote = stripped[:3]
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                insert_at = idx + 1
                continue
            in_docstring = True
            insert_at = idx + 1
            continue

        if in_docstring:
            insert_at = idx + 1
            if stripped.endswith(('"""', "'''")):
                in_docstring = False
            continue

        if stripped.startswith("from __future__"):
            insert_at = idx + 1
            continue

        if not stripped or stripped.startswith("#"):
            continue
        break

    return insert_at


def _primary_module_name(ev: Evidence, source_ctx: SourceContext) -> str:
    if source_ctx.target_module_map:
        return next(iter(source_ctx.target_module_map.keys()))
    if source_ctx.source_paths:
        return source_ctx.source_paths[0].stem
    if ev.source_files:
        dotted = ev.source_files[0].dotted_module_name
        if dotted:
            return dotted
        return Path(ev.source_files[0].path).stem
    return _pkg_name(ev.project_name)


def _build_target_module_map(
    resolved_sources: tuple[Path, ...],
    repo: RepoContext | None,
) -> dict[str, str]:
    """Return ``{dotted_module_name: workspace_rel_path}`` for each target source.

    The workspace-rel path mirrors the dotted name (``agent.retry_utils`` →
    ``agent/retry_utils.py``), so the agent writes the file at a path that
    matches the import statements in the hidden tests. Single-file scans
    without a detected repo root collapse to ``{stem: basename}``.
    """
    module_pairs: list[tuple[str, Path]] = []
    rel_path_to_sources: dict[str, list[Path]] = {}

    for source_path in resolved_sources:
        if repo is not None:
            module_name = module_name_from_path(
                source_path, repo.root, import_roots=repo.import_roots
            )
        else:
            module_name = source_path.stem
        if not module_name:
            continue
        module_pairs.append((module_name, source_path))

    target_map: dict[str, str] = {}
    for module_name, source_path in module_pairs:
        # __init__.py files map to <pkg>/__init__.py, not <pkg>.py — otherwise
        # the package import (`from src.coverage import ...`) fails because
        # `src.py` shadows the `src/` package directory at runtime.
        if source_path.name == "__init__.py":
            workspace_rel = module_name.replace(".", "/") + "/__init__.py"
        else:
            workspace_rel = module_name.replace(".", "/") + ".py"
        target_map[module_name] = workspace_rel
        rel_path_to_sources.setdefault(workspace_rel, []).append(source_path)

    duplicates = {
        rel: paths for rel, paths in rel_path_to_sources.items() if len(paths) > 1
    }
    if duplicates:
        rendered = ", ".join(
            f"{rel} -> {', '.join(str(path) for path in paths)}"
            for rel, paths in sorted(duplicates.items())
        )
        raise ValueError(
            "Selected source files map to the same workspace path. "
            f"Resolve the collision before generating: {rendered}"
        )

    return target_map


def _allow_unsupported_test_refs() -> bool:
    raw = os.environ.get(ALLOW_UNSUPPORTED_TEST_REFS_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _unsupported_reason(unsupported_modules: list[str]) -> str:
    joined = ", ".join(unsupported_modules[:4])
    if len(unsupported_modules) > 4:
        joined += ", ..."
    return f"depends on unsupported internal module(s): {joined}"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
