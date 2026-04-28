"""Scanner: extract structure from Python source files using AST + test/doc scraping."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from .evidence import (
    ClassInfo,
    Evidence,
    FunctionInfo,
    ModuleInfo,
    Parameter,
    RuntimeAsset,
    TestEvidence,
)
from .repo_support import find_repo_context, module_name_from_path
from .runtime_assets import collect_runtime_assets

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None


def _expand_py_paths(paths: list[str | Path] | None) -> list[Path]:
    """Expand a mixed list of files and directories to a flat list of ``.py`` files.

    Directories are walked recursively (`rglob("*.py")`); individual ``.py`` files
    pass through unchanged. Non-existent paths and non-Python files are dropped
    silently — same posture as ``_scan_module``'s pre-existing guard, but applied
    before the read so callers passing a directory don't either crash with
    ``IsADirectoryError`` (test path) or get silently skipped (source path).
    """
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in paths or []:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*.py")):
                resolved = child.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    out.append(child)
        elif path.suffix == ".py":
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(path)
    return out


def scan(
    source_paths: list[str | Path],
    test_paths: list[str | Path] | None = None,
    project_name: str = "",
    readme_path: str | Path | None = None,
) -> Evidence:
    """Scan source files, optional test files, and docs into an Evidence store."""

    source_paths = _expand_py_paths(source_paths)
    test_paths = _expand_py_paths(test_paths)

    ev = Evidence(project_name=project_name)
    ev.python_version = _detect_python_version(source_paths)

    resolved_source_paths = [Path(p).resolve() for p in source_paths if Path(p).exists()]
    source_repo = find_repo_context(resolved_source_paths) if resolved_source_paths else None

    for p in source_paths:
        mod = _scan_module(Path(p))
        if mod:
            _annotate_module_with_repo_context(mod, source_repo)
            ev.source_files.append(mod)
            ev.total_loc += mod.line_count

    if test_paths:
        all_symbols = {s for mod in ev.source_files for s in _module_symbols(mod)}
        for tp in test_paths:
            ev.tests.extend(_scan_tests(Path(tp), all_symbols))

    if readme_path:
        ev.readme_sections = _extract_readme(Path(readme_path))

    ev.dependencies = _collect_third_party_deps(ev)
    ev.runtime_assets = _collect_runtime_asset_evidence(source_paths, test_paths or [])
    return ev


def _annotate_module_with_repo_context(mod: ModuleInfo, repo) -> None:
    """Resolve the dotted module name + workspace target path from repo context.

    Falls back to the flat basename when no repo root was detected, so
    single-file scans keep working exactly as before.
    """
    path = Path(mod.path)
    if repo is not None:
        dotted = module_name_from_path(
            path, repo.root, import_roots=repo.import_roots
        )
        if dotted:
            mod.dotted_module_name = dotted
            mod.workspace_rel_path = dotted.replace(".", "/") + ".py"
            return
    mod.dotted_module_name = mod.module_name
    mod.workspace_rel_path = path.name


def _collect_runtime_asset_evidence(
    source_paths: list[str | Path],
    test_paths: list[str | Path],
) -> list[RuntimeAsset]:
    """Scan all source + test files for runtime file references."""

    scan_targets: list[Path] = []
    for raw in (*source_paths, *test_paths):
        candidate = Path(raw)
        if candidate.exists():
            scan_targets.append(candidate)
    if not scan_targets:
        return []

    repo = find_repo_context(scan_targets)
    if repo is None:
        return []

    known = set(repo.module_index.keys())
    resolved = collect_runtime_assets(
        scan_targets,
        repo.root,
        import_roots=repo.import_roots,
        known_python_modules=known,
    )
    assets: list[RuntimeAsset] = []
    for rel_path, asset in sorted(resolved.items()):
        assets.append(
            RuntimeAsset(
                rel_path=rel_path,
                kind=asset.kind,
                size_bytes=asset.size_bytes,
                referenced_by=list(asset.referenced_by),
            )
        )
    return assets


def _detect_python_version(source_paths: list[str | Path]) -> str:
    repo = find_repo_context(source_paths)
    if repo is not None and repo.pyproject_path is not None and tomllib is not None:
        try:
            data = tomllib.loads(repo.pyproject_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        requires_python = data.get("project", {}).get("requires-python")
        if isinstance(requires_python, str) and requires_python.strip():
            return requires_python.strip()
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _scan_module(path: Path) -> ModuleInfo | None:
    """Parse a single .py file and extract its structure."""

    if not path.exists() or path.suffix != ".py":
        return None

    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Failed to parse source file {path}: {exc.msg}") from exc

    lines = source.splitlines()
    mod = ModuleInfo(
        path=str(path),
        module_name=path.stem,
        line_count=len(lines),
        docstring=ast.get_docstring(tree) or "",
    )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod.imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [a.name for a in node.names]
                mod.from_imports.append((node.module, names))

        elif isinstance(node, ast.Assign):
            _extract_constants(node, lines, mod)

        elif isinstance(node, ast.AnnAssign):
            _extract_annotated_constant(node, lines, mod)

        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            mod.functions.append(_extract_function(node, mod.module_name, source))

        elif isinstance(node, ast.ClassDef):
            mod.classes.append(_extract_class(node, mod.module_name, source))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List | ast.Tuple):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                mod.all_exports.append(elt.value)

    mod.string_literals = _extract_string_literals(tree)
    return mod


def _extract_constants(node: ast.Assign, lines: list[str], mod: ModuleInfo) -> None:
    """Extract module-level UPPER_CASE assignments as constants."""

    for target in node.targets:
        if isinstance(target, ast.Name) and target.id.isupper():
            value_repr = _safe_source_segment(lines, node.value)
            mod.constants.append((target.id, value_repr))


def _extract_annotated_constant(node: ast.AnnAssign, lines: list[str], mod: ModuleInfo) -> None:
    if isinstance(node.target, ast.Name) and node.target.id.isupper() and node.value:
        value_repr = _safe_source_segment(lines, node.value)
        mod.constants.append((node.target.id, value_repr))


def _safe_source_segment(lines: list[str], node: ast.AST) -> str:
    """Get source text for a node, falling back to repr."""

    try:
        return ast.get_source_segment("\n".join(lines), node) or ast.dump(node)
    except Exception:
        return ast.dump(node)


def _extract_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_name: str,
    source: str,
) -> FunctionInfo:
    params = _extract_params(node.args, source)
    return FunctionInfo(
        name=node.name,
        qualname=f"{module_name}.{node.name}",
        module=module_name,
        lineno=node.lineno,
        decorators=[_decorator_name(d) for d in node.decorator_list],
        params=params,
        signature_params=_format_signature_params(node.args, source),
        return_annotation=_annotation_str(node.returns, source),
        docstring=ast.get_docstring(node) or "",
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _extract_class(node: ast.ClassDef, module_name: str, source: str) -> ClassInfo:
    ci = ClassInfo(
        name=node.name,
        qualname=f"{module_name}.{node.name}",
        module=module_name,
        lineno=node.lineno,
        bases=[_annotation_str(b, source) for b in node.bases],
        decorators=[_decorator_name(d) for d in node.decorator_list],
        docstring=ast.get_docstring(node) or "",
    )

    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            fi = _extract_function(child, module_name, source)
            fi.qualname = f"{module_name}.{node.name}.{child.name}"
            fi.is_method = True
            fi.is_property = "property" in fi.decorators
            fi.is_staticmethod = "staticmethod" in fi.decorators
            fi.is_classmethod = "classmethod" in fi.decorators
            ci.methods.append(fi)

        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            ann = _annotation_str(child.annotation, source)
            ci.class_variables.append((child.target.id, ann))

        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    ci.class_variables.append((target.id, ""))

    return ci


def _extract_params(args: ast.arguments, source: str) -> list[Parameter]:
    """Extract function parameters with types and defaults."""

    params: list[Parameter] = []

    all_args = args.posonlyargs + args.args
    defaults_offset = len(all_args) - len(args.defaults)

    for i, arg in enumerate(all_args):
        default = ""
        default_idx = i - defaults_offset
        if 0 <= default_idx < len(args.defaults):
            default = _annotation_str(args.defaults[default_idx], source)
        params.append(
            Parameter(
                name=arg.arg,
                annotation=_annotation_str(arg.annotation, source),
                default=default,
            )
        )

    if args.vararg:
        params.append(
            Parameter(
                name=f"*{args.vararg.arg}",
                annotation=_annotation_str(args.vararg.annotation, source),
            )
        )

    for i, arg in enumerate(args.kwonlyargs):
        default = ""
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = _annotation_str(args.kw_defaults[i], source)
        params.append(
            Parameter(
                name=arg.arg,
                annotation=_annotation_str(arg.annotation, source),
                default=default,
            )
        )

    if args.kwarg:
        params.append(
            Parameter(
                name=f"**{args.kwarg.arg}",
                annotation=_annotation_str(args.kwarg.annotation, source),
            )
        )

    return params


def _format_signature_params(args: ast.arguments, source: str) -> str:
    """Render an exact Python parameter list, preserving `/` and bare `*`."""

    parts: list[str] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults_offset = len(positional) - len(args.defaults)

    for i, arg in enumerate(args.posonlyargs):
        default = _positional_default(i, defaults_offset, args.defaults, source)
        parts.append(_format_arg(arg, source, default=default))
    if args.posonlyargs:
        parts.append("/")

    for i, arg in enumerate(args.args, start=len(args.posonlyargs)):
        default = _positional_default(i, defaults_offset, args.defaults, source)
        parts.append(_format_arg(arg, source, default=default))

    if args.vararg:
        parts.append(_format_arg(args.vararg, source, prefix="*"))
    elif args.kwonlyargs:
        parts.append("*")

    for i, arg in enumerate(args.kwonlyargs):
        default = ""
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = _annotation_str(args.kw_defaults[i], source)
        parts.append(_format_arg(arg, source, default=default))

    if args.kwarg:
        parts.append(_format_arg(args.kwarg, source, prefix="**"))

    return ", ".join(parts)


def _positional_default(index: int, defaults_offset: int, defaults: list[ast.expr], source: str) -> str:
    default_idx = index - defaults_offset
    if 0 <= default_idx < len(defaults):
        return _annotation_str(defaults[default_idx], source)
    return ""


def _format_arg(arg: ast.arg, source: str, default: str = "", prefix: str = "") -> str:
    rendered = f"{prefix}{arg.arg}"
    annotation = _annotation_str(arg.annotation, source)
    if annotation:
        rendered += f": {annotation}"
    if default:
        rendered += f" = {default}"
    return rendered


def _extract_string_literals(tree: ast.AST) -> list[str]:
    """Extract string literals used as dict keys, .get() args, and 'in' checks."""

    seen: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str) and 2 <= len(node.slice.value) <= 60:
                seen.add(node.slice.value)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            if 2 <= len(node.args[0].value) <= 60:
                seen.add(node.args[0].value)

        if isinstance(node, ast.Compare):
            for comparator_op in node.ops:
                if isinstance(comparator_op, ast.In | ast.NotIn):
                    if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                        if 2 <= len(node.left.value) <= 60:
                            seen.add(node.left.value)

    return sorted(seen)


def _annotation_str(node: ast.AST | None, source: str) -> str:
    """Convert an annotation AST node to source text."""

    if node is None:
        return ""
    try:
        seg = ast.get_source_segment(source, node)
        if seg:
            return seg
    except Exception:
        pass
    return ast.dump(node)


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ast.dump(node)


def _module_symbols(mod: ModuleInfo) -> list[str]:
    """All symbol names defined in a module (for test matching)."""

    names: list[str] = []
    for fn in mod.functions:
        names.append(fn.name)
    for cls in mod.classes:
        names.append(cls.name)
        for m in cls.methods:
            names.append(m.name)
    for name, _ in mod.constants:
        names.append(name)
    return names


def _scan_tests(path: Path, known_symbols: set[str]) -> list[TestEvidence]:
    """Scan a test file and map test functions to symbols they reference."""

    if not path.exists():
        return []

    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Failed to parse test file {path}: {exc.msg}") from exc

    results: list[TestEvidence] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test"):
            continue

        try:
            snippet_lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
            snippet = "\n".join(snippet_lines[:50])
        except Exception:
            snippet = ""

        referenced = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in known_symbols:
                referenced.add(child.id)
            elif isinstance(child, ast.Attribute) and child.attr in known_symbols:
                referenced.add(child.attr)

        results.append(
            TestEvidence(
                test_file=str(path),
                test_name=node.name,
                tested_symbols=sorted(referenced),
                source_snippet=snippet,
            )
        )

    return results


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _extract_readme(path: Path) -> dict[str, str]:
    """Extract heading→content sections from a markdown file."""

    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="replace")
    sections: dict[str, str] = {}
    matches = list(_HEADING_RE.finditer(text))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections[heading] = body[:2000]

    if not matches and text.strip():
        sections["README"] = text.strip()[:3000]

    return sections


_STDLIB_PREFIXES = set(sys.stdlib_module_names) | {"__future__"}


def _collect_third_party_deps(ev: Evidence) -> list[str]:
    """Collect likely third-party imports from all source modules."""

    seen: set[str] = set()
    own_modules = {m.module_name for m in ev.source_files}

    for mod in ev.source_files:
        for imp in mod.imports:
            root = imp.split(".")[0]
            if root not in _STDLIB_PREFIXES and root not in own_modules:
                seen.add(root)
        for from_mod, _ in mod.from_imports:
            root = from_mod.split(".")[0]
            if root not in _STDLIB_PREFIXES and root not in own_modules:
                seen.add(root)

    return sorted(seen)
