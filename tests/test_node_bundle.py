"""Tests for node_bundle: manifest, closure, bare-import audit, staging."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.node_bundle import (
    NodeBundleManifest,
    audit_bare_imports,
    build_manifest,
    _extract_all_specifiers,
    _extract_local_specifiers,
    _is_local_specifier,
    _resolve_local_specifier,
    _bare_package_name,
)


class ManifestSerializationTests(unittest.TestCase):
    def test_roundtrip_json(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp/repo",
            source_files={"src/lib.ts": "export const x = 1;"},
            test_files={"tests/lib.test.ts": "import { x } from '../src/lib';"},
            support_files={},
            config_files={"package.json": "{}"},
            install_fingerprint="abc123",
        )
        json_str = m.to_json()
        restored = NodeBundleManifest.from_json(json_str)
        self.assertEqual(restored.slug, "demo")
        self.assertEqual(restored.source_files, m.source_files)
        self.assertEqual(restored.test_files, m.test_files)
        self.assertEqual(restored.install_fingerprint, "abc123")


class SpecifierExtractionTests(unittest.TestCase):
    def test_extract_es_import(self) -> None:
        code = "import { foo } from './lib';\nimport bar from '../utils';"
        specs = _extract_all_specifiers(code)
        self.assertIn("./lib", specs)
        self.assertIn("../utils", specs)

    def test_extract_bare_import(self) -> None:
        code = "import { expect } from 'vitest';\nimport SuperJSON from 'superjson';"
        specs = _extract_all_specifiers(code)
        self.assertIn("vitest", specs)
        self.assertIn("superjson", specs)

    def test_extract_require(self) -> None:
        code = "const fs = require('fs');\nconst lib = require('./lib');"
        specs = _extract_all_specifiers(code)
        self.assertIn("fs", specs)
        self.assertIn("./lib", specs)

    def test_extract_side_effect_import(self) -> None:
        code = "import './polyfill';"
        specs = _extract_all_specifiers(code)
        self.assertIn("./polyfill", specs)

    def test_extract_export_from(self) -> None:
        code = "export { foo } from './mod';\nexport * from '../base';"
        specs = _extract_all_specifiers(code)
        self.assertIn("./mod", specs)
        self.assertIn("../base", specs)

    def test_local_specifier_detection(self) -> None:
        self.assertTrue(_is_local_specifier("./foo"))
        self.assertTrue(_is_local_specifier("../bar"))
        self.assertFalse(_is_local_specifier("vitest"))
        self.assertFalse(_is_local_specifier("@scope/pkg"))
        self.assertFalse(_is_local_specifier("node:fs"))

    def test_extract_local_only(self) -> None:
        code = "import { x } from './local';\nimport { y } from 'vitest';"
        local = _extract_local_specifiers(code)
        self.assertEqual(local, ["./local"])

    def test_bare_package_name_scoped(self) -> None:
        self.assertEqual(_bare_package_name("@scope/pkg"), "@scope/pkg")
        self.assertEqual(_bare_package_name("@scope/pkg/sub"), "@scope/pkg")

    def test_bare_package_name_unscoped(self) -> None:
        self.assertEqual(_bare_package_name("vitest"), "vitest")
        self.assertEqual(_bare_package_name("mongodb/lib"), "mongodb")


class LocalSpecifierResolutionTests(unittest.TestCase):
    def test_resolve_exact_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            lib = root / "src" / "lib.ts"
            lib.write_text("export const x = 1;", encoding="utf-8")
            from_file = root / "tests" / "test.ts"

            (root / "tests").mkdir()
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("../src/lib.ts", from_file, root)
            self.assertEqual(result, lib.resolve())

    def test_resolve_extensionless(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            lib = root / "src" / "lib.ts"
            lib.write_text("export const x = 1;", encoding="utf-8")
            from_file = root / "tests" / "test.ts"
            (root / "tests").mkdir()
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("../src/lib", from_file, root)
            self.assertEqual(result, lib.resolve())

    def test_resolve_directory_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixtures = root / "tests" / "fixtures"
            fixtures.mkdir(parents=True)
            idx = fixtures / "index.ts"
            idx.write_text("export const a = 1;", encoding="utf-8")
            from_file = root / "tests" / "test.ts"
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("./fixtures/", from_file, root)
            self.assertEqual(result, idx.resolve())

    def test_resolve_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir()
            data = root / "data" / "sample.json"
            data.write_text("{}", encoding="utf-8")
            from_file = root / "tests" / "test.ts"
            (root / "tests").mkdir()
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("../data/sample.json", from_file, root)
            self.assertEqual(result, data.resolve())

    def test_resolve_outside_repo_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            from_file = root / "src" / "test.ts"
            (root / "src").mkdir()
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("../../outside", from_file, root)
            self.assertIsNone(result)

    def test_resolve_nonexistent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            from_file = root / "test.ts"
            from_file.write_text("", encoding="utf-8")

            result = _resolve_local_specifier("./nonexistent", from_file, root)
            self.assertIsNone(result)


class BuildManifestTests(unittest.TestCase):
    def test_basic_manifest_preserves_repo_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;", encoding="utf-8")

            (root / "tests").mkdir()
            test = root / "tests" / "lib.test.ts"
            test.write_text("import { x } from '../src/lib';", encoding="utf-8")

            pkg = root / "package.json"
            pkg.write_text('{"name": "demo"}', encoding="utf-8")

            m = build_manifest(
                slug="demo",
                repo_root=root,
                source_paths=[src],
                test_paths=[test],
                config_paths=[pkg],
            )

            self.assertIn("src/lib.ts", m.source_files)
            self.assertIn("tests/lib.test.ts", m.test_files)
            self.assertIn("package.json", m.config_files)

    def test_transitive_closure_bundles_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;", encoding="utf-8")

            fixtures = root / "tests" / "fixtures"
            fixtures.mkdir(parents=True)
            idx = fixtures / "index.ts"
            idx.write_text("export const a = 1;", encoding="utf-8")

            test = root / "tests" / "lib.test.ts"
            test.write_text(
                "import { x } from '../src/lib';\nimport * as fix from './fixtures/';\n",
                encoding="utf-8",
            )

            pkg = root / "package.json"
            pkg.write_text('{"name": "demo"}', encoding="utf-8")

            m = build_manifest(
                slug="demo",
                repo_root=root,
                source_paths=[src],
                test_paths=[test],
                config_paths=[pkg],
            )

            self.assertIn("tests/fixtures/index.ts", m.support_files)

    def test_transitive_closure_follows_chains(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            src = root / "src" / "lib.ts"
            src.write_text("export const x = 1;", encoding="utf-8")

            helpers = root / "tests" / "helpers"
            helpers.mkdir(parents=True)
            helper = helpers / "setup.ts"
            helper.write_text("import { deep } from './deep';\nexport const s = 1;", encoding="utf-8")
            deep = helpers / "deep.ts"
            deep.write_text("export const deep = 42;", encoding="utf-8")

            test = root / "tests" / "lib.test.ts"
            test.write_text("import { s } from './helpers/setup';", encoding="utf-8")

            pkg = root / "package.json"
            pkg.write_text('{"name": "demo"}', encoding="utf-8")

            m = build_manifest(
                slug="demo",
                repo_root=root,
                source_paths=[src],
                test_paths=[test],
                config_paths=[pkg],
            )

            self.assertIn("tests/helpers/setup.ts", m.support_files)
            self.assertIn("tests/helpers/deep.ts", m.support_files)

    def test_duplicate_basenames_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "a").mkdir(parents=True)
            (root / "src" / "b").mkdir(parents=True)

            src_a = root / "src" / "a" / "index.ts"
            src_a.write_text("export const a = 1;", encoding="utf-8")
            src_b = root / "src" / "b" / "index.ts"
            src_b.write_text("export const b = 2;", encoding="utf-8")

            pkg = root / "package.json"
            pkg.write_text('{"name": "demo"}', encoding="utf-8")

            m = build_manifest(
                slug="demo",
                repo_root=root,
                source_paths=[src_a, src_b],
                test_paths=[],
                config_paths=[pkg],
            )

            self.assertIn("src/a/index.ts", m.source_files)
            self.assertIn("src/b/index.ts", m.source_files)
            self.assertEqual(len(m.source_files), 2)


class AuditBareImportsTests(unittest.TestCase):
    def test_declared_deps_pass(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import { expect } from 'vitest';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        pkg = {"devDependencies": {"vitest": "^1.0.0"}}
        issues = audit_bare_imports(m, pkg)
        self.assertEqual(issues, [])

    def test_missing_dep_flagged(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import { ObjectID } from 'mongodb';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        pkg = {"devDependencies": {"vitest": "^1.0.0"}}
        issues = audit_bare_imports(m, pkg)
        self.assertEqual(len(issues), 1)
        self.assertIn("mongodb", issues[0])

    def test_node_builtins_pass(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import * as fs from 'fs';\nimport { join } from 'node:path';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        issues = audit_bare_imports(m, {})
        self.assertEqual(issues, [])

    def test_local_imports_not_flagged(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import { x } from './lib';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        issues = audit_bare_imports(m, {})
        self.assertEqual(issues, [])

    def test_scoped_packages_checked(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import { x } from '@vitest/coverage-v8';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        pkg = {"devDependencies": {"vitest": "^1.0.0"}}
        issues = audit_bare_imports(m, pkg)
        self.assertEqual(len(issues), 1)
        self.assertIn("@vitest/coverage-v8", issues[0])

    def test_package_own_name_passes(self) -> None:
        m = NodeBundleManifest(
            slug="demo",
            repo_root="/tmp",
            source_files={},
            test_files={"tests/t.ts": "import { x } from 'my-lib';"},
            support_files={},
            config_files={},
            install_fingerprint="x",
        )
        pkg = {"name": "my-lib", "devDependencies": {"vitest": "^1.0.0"}}
        issues = audit_bare_imports(m, pkg)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
