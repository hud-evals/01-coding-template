"""Manifest-driven bundling and runtime staging for TypeScript/Node tasks.

Replaces the old flat-basename + glob approach with repo-relative path
preservation, transitive local-import closure, bare-import auditing,
and fingerprint-based cache invalidation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

NODE_IMPORT_EXTENSIONS = (".ts", ".mts", ".js", ".mjs", ".json", ".cjs", ".cts")

_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+"""
    r"""(?:type\s+)?"""
    r"""(?:\{[^}]*\}\s+from|[\w*]+\s+from|\*\s+as\s+\w+\s+from)"""
    r"""\s+['"]([^'"]+)['"]"""
)
_SIDE_EFFECT_IMPORT_RE = re.compile(r"""(?:^|\n)\s*import\s+['"]([^'"]+)['"]""")
_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_EXPORT_FROM_RE = re.compile(
    r"""(?:^|\n)\s*export\s+(?:\{[^}]*\}|\*)\s+from\s+['"]([^'"]+)['"]"""
)

NODE_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers",
    "tls", "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
    "worker_threads", "zlib",
})


@dataclass
class NodeBundleManifest:
    slug: str
    repo_root: str
    source_files: dict[str, str]
    test_files: dict[str, str]
    support_files: dict[str, str]
    config_files: dict[str, str]
    install_fingerprint: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> NodeBundleManifest:
        data = json.loads(text)
        return cls(**data)


def build_manifest(
    slug: str,
    repo_root: Path,
    source_paths: list[Path],
    test_paths: list[Path],
    config_paths: list[Path],
    extra_config_files: dict[str, str] | None = None,
) -> NodeBundleManifest:
    """Build a bundle manifest with transitive local-import closure.

    *extra_config_files* lets callers inject install-relevant config that does
    not live on disk in *repo_root* — e.g. an auto-generated ``package-lock.json``
    materialised in a temp dir. Keys are filenames (basename, no path prefix);
    values are file contents. Use this whenever you would otherwise be tempted
    to write a generated config back into the user's worktree.
    """
    source_files: dict[str, str] = {}
    for p in source_paths:
        rel = _repo_relative(p, repo_root)
        if p.exists():
            source_files[rel] = p.read_text(encoding="utf-8")

    test_files: dict[str, str] = {}
    for p in test_paths:
        rel = _repo_relative(p, repo_root)
        if p.exists():
            test_files[rel] = p.read_text(encoding="utf-8")

    config_files: dict[str, str] = {}
    for p in config_paths:
        rel = _repo_relative(p, repo_root)
        if p.exists():
            config_files[rel] = p.read_text(encoding="utf-8")

    if extra_config_files:
        for filename, content in extra_config_files.items():
            if "/" in filename or "\\" in filename:
                raise ValueError(
                    f"extra_config_files keys must be plain filenames, got {filename!r}"
                )
            config_files[filename] = content

    all_known = set(source_files) | set(test_files) | set(config_files)

    support_files: dict[str, str] = {}
    frontier = list(test_files.keys()) + list(source_files.keys())
    visited: set[str] = set(frontier)

    while frontier:
        current_rel = frontier.pop()
        current_abs = repo_root / current_rel
        if not current_abs.exists():
            continue
        content = current_abs.read_text(encoding="utf-8")
        for specifier in _extract_local_specifiers(content):
            resolved = _resolve_local_specifier(specifier, current_abs, repo_root)
            if resolved is None:
                continue
            resolved_rel = _repo_relative(resolved, repo_root)
            if resolved_rel in all_known or resolved_rel in support_files:
                continue
            if resolved_rel in visited:
                continue
            visited.add(resolved_rel)
            if resolved.exists():
                support_files[resolved_rel] = resolved.read_text(encoding="utf-8")
                all_known.add(resolved_rel)
                frontier.append(resolved_rel)

    _bundle_runtime_file_refs(repo_root, {**test_files, **support_files}, support_files, all_known)

    fingerprint = _compute_install_fingerprint(config_files)

    return NodeBundleManifest(
        slug=slug,
        repo_root=str(repo_root),
        source_files=source_files,
        test_files=test_files,
        support_files=support_files,
        config_files=config_files,
        install_fingerprint=fingerprint,
    )


def audit_bare_imports(
    manifest: NodeBundleManifest,
    package_json: dict,
) -> list[str]:
    """Check that bare imports used by hidden tests/support are declared in package.json."""
    all_deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        all_deps.update(package_json.get(key, {}).keys())

    pkg_name = package_json.get("name", "")
    if pkg_name:
        all_deps.add(pkg_name)

    issues: list[str] = []
    hidden_files = {**manifest.test_files, **manifest.support_files}

    for rel_path, content in hidden_files.items():
        for specifier in _extract_all_specifiers(content):
            if _is_local_specifier(specifier):
                continue
            bare_name = _bare_package_name(specifier)
            if bare_name in NODE_BUILTINS or specifier.startswith("node:"):
                continue
            if bare_name not in all_deps:
                issues.append(
                    f"Hidden file {rel_path} imports '{specifier}' "
                    f"but '{bare_name}' is not declared in package.json."
                )
    return issues


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RUNTIME_FILE_PATTERNS = [
    re.compile(r"""__dirname\s*\+\s*['"]/?([^'"]+)['"]"""),
    re.compile(r"""path\.(?:join|resolve)\s*\(\s*__dirname\s*,\s*['"]([^'"]+)['"]"""),
    re.compile(r"""`\$\{__dirname\}/([^`]+)`"""),
    re.compile(r"""new\s+URL\s*\(\s*['"]([^'"]+)['"]\s*,\s*import\.meta\.url"""),
    re.compile(r"""require\.resolve\s*\(\s*['"](\.[^'"]+)['"]"""),
]


def _bundle_runtime_file_refs(
    repo_root: Path,
    hidden_files: dict[str, str],
    support_files: dict[str, str],
    all_known: set[str],
) -> None:
    """Bundle files referenced via __dirname, path.join, template literals, or import.meta.url."""
    for rel, content in list(hidden_files.items()):
        base_dir = (repo_root / rel).parent
        for pattern in _RUNTIME_FILE_PATTERNS:
            for m in pattern.finditer(content):
                ref = m.group(1).lstrip("/")
                if not ref:
                    continue
                target = (base_dir / ref).resolve()
                if not target.is_file():
                    continue
                if not str(target).startswith(str(repo_root.resolve())):
                    continue
                target_rel = _repo_relative(target, repo_root)
                if target_rel in all_known:
                    continue
                try:
                    support_files[target_rel] = target.read_text(encoding="utf-8")
                    all_known.add(target_rel)
                except UnicodeDecodeError:
                    pass


def _repo_relative(path: Path, root: Path) -> str:
    """Return *path* as a posix string relative to *root*.

    Raises :class:`ValueError` when *path* is outside *root*. Falling back to
    an absolute path here was a footgun: the manifest entries flow into
    ``golden_dir / rel`` / ``tests_dir / rel`` writes, and ``pathlib`` happily
    discards the destination prefix when handed an absolute right-hand side,
    letting a stray source file overwrite something outside the task bundle.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        return resolved.relative_to(root_resolved).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"{resolved} is outside the Node project root {root_resolved}; "
            "refusing to bundle a path that would escape the task output directory."
        ) from exc


def _extract_local_specifiers(content: str) -> list[str]:
    """Extract import specifiers that look like local (relative or directory) references."""
    specifiers = []
    for spec in _extract_all_specifiers(content):
        if _is_local_specifier(spec):
            specifiers.append(spec)
    return specifiers


def _extract_all_specifiers(content: str) -> list[str]:
    """Extract all import/require specifiers from TypeScript/JavaScript source."""
    specifiers: list[str] = []
    for pattern in (_IMPORT_RE, _SIDE_EFFECT_IMPORT_RE, _REQUIRE_RE, _EXPORT_FROM_RE):
        for m in pattern.finditer(content):
            specifiers.append(m.group(1))
    return specifiers


def _is_local_specifier(spec: str) -> bool:
    return spec.startswith("./") or spec.startswith("../")


def _bare_package_name(spec: str) -> str:
    if spec.startswith("@"):
        parts = spec.split("/", 2)
        return "/".join(parts[:2]) if len(parts) >= 2 else spec
    return spec.split("/", 1)[0]


def _resolve_local_specifier(specifier: str, from_file: Path, repo_root: Path) -> Path | None:
    """Resolve a relative import specifier to an actual file path."""
    base_dir = from_file.parent
    candidate = (base_dir / specifier).resolve()

    if not str(candidate).startswith(str(repo_root.resolve())):
        return None

    if candidate.is_file():
        return candidate

    for ext in NODE_IMPORT_EXTENSIONS:
        with_ext = candidate.with_suffix(ext)
        if with_ext.is_file():
            return with_ext

    if candidate.is_dir():
        for index_name in ("index.ts", "index.mts", "index.js", "index.mjs", "index.json"):
            index = candidate / index_name
            if index.is_file():
                return index

    return None


def _compute_install_fingerprint(config_files: dict[str, str]) -> str:
    """Compute a fingerprint from install-relevant manifest entries.

    Only ``package.json``, ``package-lock.json`` and ``.npmrc`` contribute,
    matched by basename so an auto-generated lockfile injected via
    ``extra_config_files`` fingerprints identically to one read from disk.
    """
    h = hashlib.sha256()
    for name in ("package.json", "package-lock.json", ".npmrc"):
        for rel in sorted(config_files):
            if Path(rel).name == name:
                h.update(name.encode("utf-8"))
                h.update(config_files[rel].encode("utf-8"))
                break
    return h.hexdigest()[:16]
