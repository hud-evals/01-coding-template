"""Tests for node_repo_support: project detection and preflight validation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.node_repo_support import (
    NodeRepoContext,
    collect_all_declared_deps,
    collect_node_dependencies,
    detect_node_project,
    find_node_repo_root,
)


class FindNodeRepoRootTests(unittest.TestCase):
    def test_finds_root_from_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("", encoding="utf-8")

            result = find_node_repo_root(src)
            self.assertEqual(result, root.resolve())

    def test_returns_none_without_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = root / "lib.ts"
            src.write_text("", encoding="utf-8")

            result = find_node_repo_root(src)
            self.assertIsNone(result)


class DetectNodeProjectTests(unittest.TestCase):
    def _make_supported_repo(self, root: Path) -> Path:
        pkg = {
            "name": "demo",
            "type": "module",
            "devDependencies": {"vitest": "^1.0.0"},
        }
        (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        lock = {"name": "demo", "lockfileVersion": 3, "packages": {}}
        (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        (root / "src").mkdir()
        src = root / "src" / "lib.ts"
        src.write_text("export const x = 1;", encoding="utf-8")
        return src

    def test_supported_vitest_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)

            ctx = detect_node_project([src])
            self.assertTrue(ctx.is_supported)
            self.assertEqual(ctx.test_runner, "vitest")
            self.assertEqual(ctx.module_type, "module")

    def test_rejects_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            pkg = json.loads((root / "package.json").read_text())
            pkg["workspaces"] = ["packages/*"]
            (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

            ctx = detect_node_project([src])
            self.assertFalse(ctx.is_supported)
            self.assertTrue(any("workspace" in r.lower() for r in ctx.unsupported_reasons))

    def test_auto_generates_lockfile_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            (root / "package-lock.json").unlink()
            self.assertFalse((root / "package-lock.json").exists())

            ctx = detect_node_project(
                [src],
                require_lockfile=True,
                auto_generate_lockfile=True,
            )
            self.assertTrue((root / "package-lock.json").exists())
            self.assertTrue(ctx.is_supported)

    def test_readonly_detection_does_not_generate_lockfile_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            (root / "package-lock.json").unlink()
            self.assertFalse((root / "package-lock.json").exists())

            ctx = detect_node_project([src])

            self.assertFalse((root / "package-lock.json").exists())
            self.assertTrue(ctx.is_supported)

    def test_rejects_jest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pkg = {
                "name": "demo",
                "devDependencies": {"jest": "^29.0.0"},
            }
            (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;", encoding="utf-8")

            ctx = detect_node_project([src])
            self.assertFalse(ctx.is_supported)
            self.assertTrue(any("jest" in r.lower() for r in ctx.unsupported_reasons))

    def test_rejects_tsconfig_path_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            tsconfig = {
                "compilerOptions": {
                    "paths": {"@lib/*": ["src/*"]},
                },
            }
            (root / "tsconfig.json").write_text(json.dumps(tsconfig), encoding="utf-8")

            ctx = detect_node_project([src])
            self.assertFalse(ctx.is_supported)
            self.assertTrue(any("alias" in r.lower() for r in ctx.unsupported_reasons))

    def test_detects_vitest_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            (root / "vitest.config.ts").write_text(
                "import { defineConfig } from 'vitest/config';\nexport default defineConfig({});",
                encoding="utf-8",
            )

            ctx = detect_node_project([src])
            self.assertIsNotNone(ctx.vitest_config_path)

    def test_rejects_unresolvable_vitest_setup_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            src = self._make_supported_repo(root)
            (root / "vitest.config.ts").write_text(
                "export default { test: { setupFiles: ['./setup-not-here.ts'] } };",
                encoding="utf-8",
            )

            ctx = detect_node_project([src])
            self.assertFalse(ctx.is_supported)
            self.assertTrue(any("setupFile" in r for r in ctx.unsupported_reasons))


class CollectDependenciesTests(unittest.TestCase):
    def test_collect_runtime_deps(self) -> None:
        pkg = {"dependencies": {"copy-anything": "^4", "debug": "^4.3"}}
        result = collect_node_dependencies(pkg)
        self.assertEqual(result, ["copy-anything", "debug"])

    def test_collect_all_declared(self) -> None:
        pkg = {
            "dependencies": {"copy-anything": "^4"},
            "devDependencies": {"vitest": "^1.0.0"},
            "peerDependencies": {"react": "^18"},
        }
        result = collect_all_declared_deps(pkg)
        self.assertEqual(result, {"copy-anything", "vitest", "react"})


if __name__ == "__main__":
    unittest.main()
