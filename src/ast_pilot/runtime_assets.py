"""Detect non-Python runtime assets referenced by source or test files.

Python counterpart to :mod:`ast_pilot.node_bundle._bundle_runtime_file_refs`.
When a source or test file opens a file at runtime (``open("schema.sql")``,
``Path(__file__).parent / "fixtures/data.json"``, ``sqlite3.connect("app.db")``,
``importlib.resources.files("pkg").joinpath("asset.txt")``), the reference
shows up in the AST as a string literal combined with path-building calls.
This module reduces those expressions to concrete file paths so the bundler
can ship the referenced files alongside the hidden tests.

Limitations (documented rather than silently skipped):

* Only literal path components are resolved. A variable assigned from an
  ``os.environ`` lookup or a function argument is opaque to us.
* ``glob.glob("*.sql")`` is skipped — we never expand globs because
  the match set depends on runtime filesystem state.
* Binary assets are out of scope for v1; the bundler writes text only.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


SIZE_WARN_BYTES = 5 * 1024 * 1024
SIZE_REFUSE_BYTES = 50 * 1024 * 1024

TEXT_EXTENSIONS = frozenset({
    ".sql", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".txt", ".md", ".rst", ".csv", ".tsv", ".xml", ".html", ".htm",
    ".jinja", ".jinja2", ".j2", ".tmpl", ".template",
    ".env.example", ".sh", ".proto",
})

SECRET_PATTERNS = (
    ".env", ".env.local", ".env.production", ".env.development",
    "secrets", "credentials", "credential",
)
SECRET_SUFFIXES = (".pem", ".key", ".crt", ".p12", ".pfx")

PATH_VAR_NAMES = frozenset({
    "REPO_ROOT", "HERE", "BASE_DIR", "ROOT_DIR", "PROJECT_ROOT",
    "REPO_DIR", "WORKSPACE", "WORKSPACE_DIR", "SRC_ROOT", "SOURCE_ROOT",
    "ROOT", "__file__",
})

FILE_OPENERS: frozenset[str] = frozenset({
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
})

ATTR_CALL_OPENERS: frozenset[tuple[str, str]] = frozenset({
    ("sqlite3", "connect"),
    ("json", "load"),
    ("yaml", "safe_load"),
    ("yaml", "load"),
    ("toml", "load"),
    ("tomllib", "load"),
    ("configparser", "read"),
})


@dataclass(frozen=True)
class AssetReference:
    """One runtime-asset reference extracted from a source or test file."""

    referring_file: Path
    literal: str
    """The reduced string — joined path components with ``/`` separators."""


class _PathReducer(ast.NodeVisitor):
    """Accumulates :class:`AssetReference` entries from a module AST."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.refs: list[AssetReference] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        literal = _reduce_open_call(node)
        if literal is not None and _looks_like_asset_path(literal):
            self.refs.append(AssetReference(self.file_path, literal))
        self.generic_visit(node)


def extract_references(path: Path) -> list[AssetReference]:
    """Return every runtime-asset reference found in *path*'s AST."""

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    reducer = _PathReducer(path)
    reducer.visit(tree)
    return reducer.refs


def collect_runtime_assets(
    paths: Sequence[Path],
    repo_root: Path,
    *,
    import_roots: Sequence[Path] = (),
    known_python_modules: Iterable[str] = (),
    allow_secret_patterns: bool = False,
) -> dict[str, "ResolvedAsset"]:
    """Resolve every file referenced by *paths* to a concrete asset record.

    Returns a dict keyed by the asset's repo-relative path. When a
    referenced file cannot be located inside the repo we still emit a
    record (kind ``"to_create_by_agent"``) so the caller can include the
    filename in the prompt.
    """

    resolved_roots = _unique_dirs([repo_root, *import_roots])
    known_python = set(known_python_modules)

    all_refs: list[AssetReference] = []
    for path in paths:
        all_refs.extend(extract_references(path))

    bundled: dict[str, ResolvedAsset] = {}
    unresolved: dict[str, ResolvedAsset] = {}

    for ref in all_refs:
        abs_path = _resolve_literal(ref, resolved_roots)
        rel_path = _repo_relative_path(ref.literal, abs_path, repo_root)

        if rel_path is None:
            continue

        if _references_known_python_module(rel_path, known_python):
            continue

        if not allow_secret_patterns and _is_secret_file(rel_path):
            logger.warning(
                "Skipping suspected secret file reference: %s (from %s)",
                rel_path, ref.referring_file,
            )
            continue

        if abs_path is not None:
            size_bytes = abs_path.stat().st_size if abs_path.is_file() else 0
            if size_bytes > SIZE_REFUSE_BYTES:
                raise ValueError(
                    f"Refusing to bundle runtime asset above size limit: {rel_path} "
                    f"is {size_bytes} bytes (hard limit {SIZE_REFUSE_BYTES})."
                )
            if size_bytes > SIZE_WARN_BYTES:
                logger.warning(
                    "Bundling large runtime asset: %s (%.1f MB)",
                    rel_path, size_bytes / (1024 * 1024),
                )
            existing = bundled.get(rel_path)
            if existing is None:
                bundled[rel_path] = ResolvedAsset(
                    rel_path=rel_path,
                    absolute_path=abs_path,
                    kind="bundled",
                    size_bytes=size_bytes,
                    referenced_by=[str(ref.referring_file)],
                )
            elif str(ref.referring_file) not in existing.referenced_by:
                existing.referenced_by.append(str(ref.referring_file))
        else:
            existing = unresolved.get(rel_path)
            if existing is None:
                unresolved[rel_path] = ResolvedAsset(
                    rel_path=rel_path,
                    absolute_path=None,
                    kind="to_create_by_agent",
                    size_bytes=0,
                    referenced_by=[str(ref.referring_file)],
                )
            elif str(ref.referring_file) not in existing.referenced_by:
                existing.referenced_by.append(str(ref.referring_file))

    merged: dict[str, ResolvedAsset] = {}
    merged.update(bundled)
    for rel_path, asset in unresolved.items():
        if rel_path not in merged:
            merged[rel_path] = asset
    return merged


@dataclass
class ResolvedAsset:
    """A runtime asset ready to be bundled or handed to the prompt."""

    rel_path: str
    absolute_path: Path | None
    kind: str  # "bundled" or "to_create_by_agent"
    size_bytes: int
    referenced_by: list[str]


# ---------------------------------------------------------------------------
# AST reducers
# ---------------------------------------------------------------------------


def _reduce_open_call(node: ast.Call) -> str | None:
    """If *node* is a recognised file-opener call, return the reduced literal."""

    func = node.func
    target_arg: ast.AST | None = None

    if isinstance(func, ast.Name) and func.id in FILE_OPENERS:
        if node.args:
            target_arg = node.args[0]
    elif isinstance(func, ast.Attribute):
        owner = _attr_owner(func)
        if owner is not None and (owner, func.attr) in ATTR_CALL_OPENERS and node.args:
            target_arg = node.args[0]
        elif func.attr in FILE_OPENERS:
            target_arg = func.value

    if target_arg is None:
        return None
    return _reduce_path_expr(target_arg)


def _reduce_path_expr(node: ast.AST) -> str | None:
    """Reduce a path-building expression to a ``/``-joined string."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                if isinstance(value.value, ast.Name) and value.value.id in PATH_VAR_NAMES:
                    continue
                if isinstance(value.value, ast.Attribute) and _attr_tail(value.value) in PATH_VAR_NAMES:
                    continue
                return None
            else:
                return None
        return "".join(parts).lstrip("/") or None

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _reduce_path_expr(node.left)
        right = _reduce_path_expr(node.right)
        if left is None and _is_path_anchor(node.left):
            left = ""
        if right is None and _is_path_anchor(node.right):
            return None
        if right is None:
            return None
        if left is None:
            return right
        return _joinpath(left, right)

    if isinstance(node, ast.Call):
        func = node.func

        if isinstance(func, ast.Attribute) and func.attr == "join":
            owner = _attr_owner(func)
            if owner == "os.path":
                parts = _reduce_sequence(node.args)
                if parts is not None:
                    return _joinpath(*parts)

        if isinstance(func, ast.Attribute) and func.attr == "joinpath":
            base = _reduce_path_expr(func.value)
            parts = _reduce_sequence(node.args)
            if base is None and _is_path_anchor(func.value):
                base = ""
            if parts is None:
                return None
            if base is None:
                return _joinpath(*parts)
            return _joinpath(base, *parts)

        if isinstance(func, ast.Name) and func.id == "Path":
            if not node.args:
                return None
            parts = _reduce_sequence(node.args)
            if parts is None:
                return None
            return _joinpath(*parts)

    if isinstance(node, ast.Attribute):
        if node.attr in {"parent", "parents"} and _is_path_anchor(node.value):
            return ""

    if isinstance(node, ast.Name) and node.id in PATH_VAR_NAMES:
        return ""

    return None


def _reduce_sequence(nodes: Sequence[ast.AST]) -> list[str] | None:
    parts: list[str] = []
    for item in nodes:
        reduced = _reduce_path_expr(item)
        if reduced is None:
            if _is_path_anchor(item):
                continue
            return None
        if reduced:
            parts.append(reduced)
    return parts


def _is_path_anchor(node: ast.AST) -> bool:
    """Return True if *node* refers to a known path-root anchor."""

    if isinstance(node, ast.Name) and node.id in PATH_VAR_NAMES:
        return True
    if isinstance(node, ast.Attribute):
        tail = _attr_tail(node)
        if tail in PATH_VAR_NAMES:
            return True
        if node.attr in {"parent", "parents"} and _is_path_anchor(node.value):
            return True
    if isinstance(node, ast.Subscript):
        return _is_path_anchor(node.value)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Path" and node.args:
            return _is_path_anchor(node.args[0])
        if isinstance(func, ast.Attribute) and func.attr in {"parent", "resolve"}:
            return _is_path_anchor(func.value)
    return False


def _attr_owner(node: ast.Attribute) -> str | None:
    """Produce the dotted owner path for ``os.path.join`` → ``"os.path"``."""

    if isinstance(node.value, ast.Name):
        return node.value.id
    if isinstance(node.value, ast.Attribute):
        inner = _attr_owner(node.value)
        if inner is None:
            return None
        return f"{inner}.{node.value.attr}"
    return None


def _attr_tail(node: ast.Attribute) -> str:
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    if isinstance(cur, ast.Name):
        return cur.id
    return ""


def _joinpath(*parts: str) -> str:
    cleaned: list[str] = []
    for part in parts:
        if not part:
            continue
        cleaned.append(part.strip("/"))
    return "/".join(cleaned)


# ---------------------------------------------------------------------------
# Resolution + filtering
# ---------------------------------------------------------------------------


def _resolve_literal(ref: AssetReference, roots: Sequence[Path]) -> Path | None:
    """Try each plausible root until the referenced file is found."""

    literal = ref.literal.strip()
    if not literal:
        return None

    candidate = Path(literal)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None

    tries: list[Path] = [ref.referring_file.parent / literal]
    for root in roots:
        tries.append(root / literal)

    for trial in tries:
        try:
            resolved = trial.resolve(strict=False)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _repo_relative_path(
    literal: str, abs_path: Path | None, repo_root: Path,
) -> str | None:
    """Normalise a path reference into a repo-relative string key."""

    if abs_path is not None:
        try:
            return str(abs_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            return None

    cleaned = literal.strip().lstrip("/")
    if not cleaned:
        return None
    return cleaned


def _references_known_python_module(rel_path: str, known: set[str]) -> bool:
    suffix = Path(rel_path).suffix
    if suffix not in {".py", ".pyi", ".pyx", ".pxd"}:
        return False
    stem_dotted = rel_path[: -len(suffix)].replace("/", ".")
    return stem_dotted in known


def _is_secret_file(rel_path: str) -> bool:
    name = Path(rel_path).name.lower()
    if any(name == pattern or name.startswith(pattern + ".") for pattern in SECRET_PATTERNS):
        return True
    if any(name.endswith(suffix) for suffix in SECRET_SUFFIXES):
        return True
    return False


KNOWN_BARE_NAMES = frozenset({
    ".env", ".env.local", ".env.development", ".env.production", ".env.test",
    ".gitignore", ".dockerignore", ".npmrc", ".editorconfig",
    "Dockerfile", "Makefile", "Procfile", "requirements.txt", "requirements.in",
})


def _looks_like_asset_path(literal: str) -> bool:
    """Reject obvious non-paths (SQL, URLs, query strings, commands)."""

    literal = literal.strip()
    if not literal:
        return False
    if "\n" in literal:
        return False
    if " " in literal and "/" not in literal:
        return False
    if literal.startswith(("http://", "https://", "ftp://", "sqlite://", "postgresql://", "mysql://")):
        return False
    if literal.startswith(("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ")):
        return False

    name = Path(literal).name
    if name in KNOWN_BARE_NAMES:
        return True

    suffix = Path(literal).suffix.lower()
    if not suffix:
        return False
    if suffix in TEXT_EXTENSIONS or suffix in {".db", ".sqlite", ".sqlite3"}:
        return True
    return False


def _unique_dirs(candidates: Iterable[Path]) -> list[Path]:
    seen: dict[Path, None] = {}
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in seen:
            seen[resolved] = None
    return list(seen.keys())
