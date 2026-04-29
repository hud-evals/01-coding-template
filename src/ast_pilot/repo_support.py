"""Helpers for reasoning about local Python repo structure."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None


PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git")
IGNORED_PATH_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "venv",
}
STDLIB_MODULES = frozenset(sys.stdlib_module_names) | {"__future__"}
_DOTTED_REF_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]*")


@dataclass(frozen=True)
class RepoContext:
    root: Path
    import_roots: tuple[Path, ...]
    module_index: dict[str, Path]
    pyproject_path: Path | None


def find_repo_root(path: str | Path) -> Path | None:
    candidate = Path(path).resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for parent in (start, *start.parents):
        if any((parent / marker).exists() for marker in PROJECT_MARKERS):
            return parent
    # Fallback: if the source file lives inside a Python package (sibling
    # __init__.py), walk up until we exit the package tree. The first
    # ancestor whose parent is *not* a package is the implicit repo root.
    # Lets us preserve `src.coverage.foo`-style dotted names in projects
    # that ship only a `requirements.txt` (no pyproject.toml/setup.py/.git).
    return _find_repo_root_via_package_tree(start)


def _find_repo_root_via_package_tree(start: Path) -> Path | None:
    p = start
    if not (p / "__init__.py").is_file():
        return None  # not inside a package, can't infer
    while p.parent != p and (p.parent / "__init__.py").is_file():
        p = p.parent
    return p.parent if p.parent != p else None


def find_repo_context(paths: Sequence[str | Path]) -> RepoContext | None:
    roots: list[Path] = []
    for raw_path in paths:
        root = find_repo_root(raw_path)
        if root is not None:
            roots.append(root)
    if not roots:
        return None

    root = roots[0]
    import_roots = discover_import_roots(root)
    module_index = build_module_index(root, import_roots=import_roots)
    pyproject_path = root / "pyproject.toml"
    return RepoContext(
        root=root,
        import_roots=import_roots,
        module_index=module_index,
        pyproject_path=pyproject_path if pyproject_path.exists() else None,
    )


def iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if _is_ignored_path(path.relative_to(root)):
            continue
        yield path


def build_module_index(root: Path, import_roots: Sequence[Path] | None = None) -> dict[str, Path]:
    index: dict[str, Path] = {}
    resolved_roots = tuple(import_roots or discover_import_roots(root))
    for path in iter_python_files(root):
        for module_name in module_names_from_path(path, root, import_roots=resolved_roots):
            index.setdefault(module_name, path)
    return index


def module_name_from_path(
    path: str | Path,
    root: str | Path,
    import_roots: Sequence[Path] | None = None,
) -> str | None:
    module_names = module_names_from_path(path, root, import_roots=import_roots)
    return module_names[0] if module_names else None


def module_names_from_path(
    path: str | Path,
    root: str | Path,
    import_roots: Sequence[Path] | None = None,
) -> list[str]:
    path_obj = Path(path).resolve()
    root_obj = Path(root).resolve()
    try:
        repo_relative = path_obj.relative_to(root_obj)
    except ValueError:
        return []

    if path_obj.suffix != ".py" or _is_ignored_path(repo_relative):
        return []

    names: list[str] = []
    for import_root in tuple(import_roots or discover_import_roots(root_obj)):
        try:
            relative = path_obj.relative_to(import_root)
        except ValueError:
            continue

        parts = list(relative.with_suffix("").parts)
        if not parts:
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue

        module_name = ".".join(parts)
        if module_name not in names:
            names.append(module_name)

    return names


def module_path_from_name(module_name: str, original_path: Path) -> Path:
    if original_path.name == "__init__.py":
        return Path(*module_name.split(".")) / "__init__.py"
    return Path(*module_name.split(".")).with_suffix(".py")


def discover_import_roots(root: Path) -> tuple[Path, ...]:
    return _discover_import_roots_cached(str(root.resolve()))


@cache
def _discover_import_roots_cached(root_str: str) -> tuple[Path, ...]:
    root = Path(root_str)
    roots: list[Path] = []

    def add(candidate: Path | None) -> None:
        if candidate is None:
            return
        candidate = candidate.resolve()
        if not candidate.exists() or not candidate.is_dir():
            return
        if candidate == root:
            return
        if (candidate / "__init__.py").exists():
            return
        if candidate not in roots:
            roots.append(candidate)

    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists() and tomllib is not None:
        try:
            data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        _collect_configured_import_roots(root, data, add)

    add(root / "src")
    add(root / "lib")

    roots.append(root)
    return tuple(roots)


def _collect_configured_import_roots(root: Path, data: dict, add_root) -> None:
    tool = data.get("tool", {})

    setuptools = tool.get("setuptools", {})
    package_dir = setuptools.get("package-dir", {})
    if isinstance(package_dir, dict):
        for value in package_dir.values():
            if isinstance(value, str) and value:
                add_root(root / value)

    setuptools_packages = setuptools.get("packages", {})
    find_config = setuptools_packages.get("find", {}) if isinstance(setuptools_packages, dict) else {}
    where_entries = find_config.get("where", [])
    if isinstance(where_entries, list):
        for entry in where_entries:
            if isinstance(entry, str) and entry:
                add_root(root / entry)

    poetry = tool.get("poetry", {})
    poetry_packages = poetry.get("packages", [])
    if isinstance(poetry_packages, list):
        for entry in poetry_packages:
            if not isinstance(entry, dict):
                continue
            from_dir = entry.get("from")
            if isinstance(from_dir, str) and from_dir:
                add_root(root / from_dir)

    hatch = tool.get("hatch", {})
    hatch_build = hatch.get("build", {})
    hatch_targets = hatch_build.get("targets", {})
    wheel_target = hatch_targets.get("wheel", {}) if isinstance(hatch_targets, dict) else {}
    packages = wheel_target.get("packages", [])
    if isinstance(packages, list):
        for entry in packages:
            if not isinstance(entry, str) or not entry:
                continue
            package_path = Path(entry)
            add_root(root / package_path.parent if package_path.parent != Path(".") else root)


def collect_internal_imports(path: str | Path, ctx: RepoContext) -> set[str]:
    source_path = Path(path)
    current_module = module_name_from_path(source_path, ctx.root)
    if current_module is None or not source_path.exists():
        return set()

    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.update(resolve_module_candidates(alias.name, ctx.module_index))
        elif isinstance(node, ast.ImportFrom):
            module_name = resolve_from_module(current_module, node.module, node.level)
            if not module_name:
                continue
            found.update(resolve_module_candidates(module_name, ctx.module_index))
            for alias in node.names:
                if alias.name == "*":
                    continue
                found.update(resolve_module_candidates(f"{module_name}.{alias.name}", ctx.module_index))
        elif isinstance(node, ast.Call):
            for ref in _iter_reference_strings(node):
                module_ref = reference_to_module(ref, ctx.module_index)
                if module_ref:
                    found.add(module_ref)
    return found


def resolve_module_candidates(module_name: str, module_index: dict[str, Path]) -> set[str]:
    candidates: set[str] = set()
    if module_name in module_index:
        candidates.add(module_name)

    parts = module_name.split(".")
    for idx in range(len(parts), 0, -1):
        candidate = ".".join(parts[:idx])
        if candidate in module_index:
            candidates.add(candidate)
            break

    return candidates


def resolve_from_module(current_module: str, module_name: str | None, level: int) -> str | None:
    if level == 0:
        return module_name

    package_parts = current_module.split(".")[:-1]
    if level - 1 > len(package_parts):
        return module_name

    base_parts = package_parts[: len(package_parts) - (level - 1)]
    if module_name:
        base_parts.extend(module_name.split("."))
    return ".".join(part for part in base_parts if part)


def reference_to_module(reference: str, module_index: dict[str, Path]) -> str | None:
    if reference in module_index:
        return reference
    if not _DOTTED_REF_RE.fullmatch(reference):
        return None

    parts = reference.split(".")
    for idx in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:idx])
        if candidate in module_index:
            return candidate
    return None


def load_project_dependencies(ctx: RepoContext) -> list[str]:
    if ctx.pyproject_path and tomllib is not None:
        try:
            data = tomllib.loads(ctx.pyproject_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        project = data.get("project", {})
        raw_deps = project.get("dependencies", [])
        deps = [str(dep).strip() for dep in raw_deps if str(dep).strip()]
        if deps:
            return deps

    for filename in ("requirements.txt", "requirements.in"):
        req_path = ctx.root / filename
        if not req_path.exists():
            continue
        deps = [
            line.strip()
            for line in req_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if deps:
            return deps

    return []


def ancestor_package_paths(module_path: str, module_index: dict[str, Path]) -> Iterable[str]:
    parts = module_path.split(".")
    for idx in range(1, len(parts)):
        candidate = ".".join(parts[:idx])
        if candidate in module_index:
            yield candidate


def _iter_reference_strings(node: ast.Call) -> Iterator[str]:
    if not node.args:
        return
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return
    value = first_arg.value.strip()
    if "." not in value:
        return
    yield value


def _is_ignored_path(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORED_PATH_PARTS:
            return True
        if part.startswith(".") and part not in {"__init__.py"}:
            return True
    return False
