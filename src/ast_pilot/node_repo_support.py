"""Helpers for reasoning about Node/TypeScript repo structure."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VITEST_CONFIG_NAMES = (
    "vitest.config.ts",
    "vitest.config.mts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vite.config.ts",
    "vite.config.mts",
    "vite.config.js",
    "vite.config.mjs",
)

TSCONFIG_NAMES = ("tsconfig.json", "tsconfig.build.json")

_SETUP_FILES_RE = re.compile(r"""setupFiles\s*:\s*\[([^\]]*)\]""", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"""['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class NodeRepoContext:
    root: Path
    package_json: dict
    has_lockfile: bool
    tsconfig_path: Path | None
    vitest_config_path: Path | None
    test_runner: str
    module_type: str
    node_version_floor: str
    unsupported_reasons: list[str] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        return len(self.unsupported_reasons) == 0


def find_node_repo_root(path: str | Path) -> Path | None:
    candidate = Path(path).resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for parent in (start, *start.parents):
        if (parent / "package.json").exists():
            return parent
    return None


def detect_node_project(source_paths: list[str | Path]) -> NodeRepoContext:
    """Detect and validate a Node/TypeScript project from source file paths."""
    if not source_paths:
        raise ValueError("No source paths provided for TypeScript scanning.")

    root = find_node_repo_root(source_paths[0])
    if root is None:
        raise ValueError(
            f"Could not find package.json above {source_paths[0]}. "
            "TypeScript scanning requires a Node project root."
        )

    pkg_path = root / "package.json"
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Could not read {pkg_path}: {exc}") from exc

    if not (root / "package-lock.json").exists():
        _auto_generate_lockfile(root)
    has_lockfile = (root / "package-lock.json").exists()

    tsconfig = _find_first(root, TSCONFIG_NAMES)
    vitest_config = _find_first(root, VITEST_CONFIG_NAMES)
    test_runner = _detect_test_runner(pkg, vitest_config)
    module_type = pkg.get("type", "commonjs")

    engines = pkg.get("engines", {})
    node_version = engines.get("node", "")

    unsupported: list[str] = []
    if pkg.get("workspaces"):
        unsupported.append("Monorepo workspaces are not supported in v0 TypeScript mode.")
    if not has_lockfile:
        unsupported.append(
            "package-lock.json is required and could not be auto-generated. "
            "Ensure npm is installed and package.json is valid."
        )
    if test_runner not in ("vitest",):
        unsupported.append(
            f"Test runner '{test_runner}' is not yet supported. Only Vitest is supported in v0."
        )

    _check_path_aliases(root, tsconfig, unsupported)
    _check_vitest_config_local_refs(root, vitest_config, unsupported)

    return NodeRepoContext(
        root=root,
        package_json=pkg,
        has_lockfile=has_lockfile,
        tsconfig_path=tsconfig,
        vitest_config_path=vitest_config,
        test_runner=test_runner,
        module_type=module_type,
        node_version_floor=node_version,
        unsupported_reasons=unsupported,
    )


def _auto_generate_lockfile(root: Path) -> None:
    """Auto-generate package-lock.json when missing (e.g. pnpm/yarn repos)."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return
    print(f"  [node] No package-lock.json found, generating from package.json...", file=sys.stderr)
    import tempfile
    env = {**__import__("os").environ, "NPM_CONFIG_CACHE": tempfile.mkdtemp(prefix="ast_pilot_npm_")}
    try:
        result = subprocess.run(
            ["npm", "install", "--package-lock-only", "--legacy-peer-deps", "--ignore-scripts"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode == 0:
            print(f"  [node] Generated package-lock.json", file=sys.stderr)
        else:
            msg = result.stderr.strip()[:200] if result.stderr else "unknown error"
            print(f"  [node] Failed to generate package-lock.json: {msg}", file=sys.stderr)
    except FileNotFoundError:
        print(f"  [node] npm not found on PATH, cannot generate package-lock.json", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"  [node] Timed out generating package-lock.json", file=sys.stderr)


def _find_first(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _detect_test_runner(pkg: dict, vitest_config: Path | None) -> str:
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "vitest" in all_deps or vitest_config is not None:
        return "vitest"
    if "jest" in all_deps or "ts-jest" in all_deps:
        return "jest"
    scripts = pkg.get("scripts", {})
    test_script = scripts.get("test", "")
    if "vitest" in test_script:
        return "vitest"
    if "jest" in test_script:
        return "jest"
    return "unknown"


def _check_path_aliases(root: Path, tsconfig_path: Path | None, unsupported: list[str]) -> None:
    if tsconfig_path is None:
        return
    try:
        raw = tsconfig_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return

    paths = data.get("compilerOptions", {}).get("paths")
    if paths and any(key != "*" for key in paths):
        unsupported.append(
            "tsconfig.json path aliases are not supported in v0 TypeScript mode."
        )


def _check_vitest_config_local_refs(
    root: Path, vitest_config: Path | None, unsupported: list[str]
) -> None:
    """Detect local setupFiles or plugin imports in vitest/vite config that we cannot safely bundle."""
    if vitest_config is None:
        return
    try:
        content = vitest_config.read_text(encoding="utf-8")
    except OSError:
        return

    setup_match = _SETUP_FILES_RE.search(content)
    if setup_match:
        inner = setup_match.group(1)
        for lit_match in _STRING_LITERAL_RE.finditer(inner):
            ref = lit_match.group(1)
            if ref.startswith("./") or ref.startswith("../"):
                target = (vitest_config.parent / ref).resolve()
                if not target.exists():
                    found = False
                    for ext in (".ts", ".mts", ".js", ".mjs"):
                        if target.with_suffix(ext).exists():
                            found = True
                            break
                    if not found:
                        unsupported.append(
                            f"Vitest config references local setupFile '{ref}' "
                            "which could not be resolved. Local config helpers "
                            "are not yet supported."
                        )


def collect_node_dependencies(pkg: dict) -> list[str]:
    """Collect runtime dependency names from package.json."""
    deps = pkg.get("dependencies", {})
    return sorted(deps.keys())


def collect_all_declared_deps(pkg: dict) -> set[str]:
    """Collect all dependency names across all sections of package.json."""
    all_deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        all_deps.update(pkg.get(key, {}).keys())
    return all_deps
