"""Helpers for reasoning about local Python repo structure."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

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
    module_index: dict[str, Path]
    pyproject_path: Path | None


def find_repo_root(path: str | Path) -> Path | None:
    candidate = Path(path).resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for parent in (start, *start.parents):
        if any((parent / marker).exists() for marker in PROJECT_MARKERS):
            return parent
    return None


def find_repo_context(paths: Sequence[str | Path]) -> RepoContext | None:
    roots: list[Path] = []
    for raw_path in paths:
        root = find_repo_root(raw_path)
        if root is not None:
            roots.append(root)
    if not roots:
        return None

    root = roots[0]
    module_index = build_module_index(root)
    pyproject_path = root / "pyproject.toml"
    return RepoContext(
        root=root,
        module_index=module_index,
        pyproject_path=pyproject_path if pyproject_path.exists() else None,
    )


def iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if _is_ignored_path(path.relative_to(root)):
            continue
        yield path


def build_module_index(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in iter_python_files(root):
        module_name = module_name_from_path(path, root)
        if module_name:
            index[module_name] = path
    return index


def module_name_from_path(path: str | Path, root: str | Path) -> str | None:
    path_obj = Path(path).resolve()
    root_obj = Path(root).resolve()
    try:
        relative = path_obj.relative_to(root_obj)
    except ValueError:
        return None

    if path_obj.suffix != ".py" or _is_ignored_path(relative):
        return None

    parts = list(relative.with_suffix("").parts)
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


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
