"""Helpers for reasoning about Node/TypeScript repo structure."""

from __future__ import annotations

import json
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
        unsupported.append("package-lock.json is required for deterministic grading (npm ci).")
    if test_runner not in ("vitest",):
        unsupported.append(
            f"Test runner '{test_runner}' is not yet supported. Only Vitest is supported in v0."
        )

    _check_path_aliases(root, tsconfig, unsupported)

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


def collect_node_dependencies(pkg: dict) -> list[str]:
    """Collect runtime dependency names from package.json."""
    deps = pkg.get("dependencies", {})
    return sorted(deps.keys())
