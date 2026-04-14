"""Tests for node_scanner: TypeScript source and test evidence extraction."""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.node_scanner import scan_typescript


class NodeScannerTests(unittest.TestCase):
    def _make_repo(self, root: Path) -> None:
        pkg = {
            "name": "demo",
            "version": "1.0.0",
            "type": "module",
            "devDependencies": {"vitest": "^1.0.0"},
        }
        (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        lock = {"name": "demo", "lockfileVersion": 3, "packages": {}}
        (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        (root / "src").mkdir()
        (root / "tests").mkdir()

    def test_scan_typescript_tracks_multiline_exports_and_import_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src" / "args.ts").write_text(
                textwrap.dedent(
                    """
                    export function defineCommand<
                      T extends string = string,
                    >(value: T): T {
                      return value;
                    }

                    export const parseArgs = <
                      T extends string = string,
                    >(value: T): T => value;
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "src" / "command.ts").write_text(
                textwrap.dedent(
                    """
                    export async function runCommand<
                      T extends string = string,
                    >(value: T): Promise<T> {
                      return value;
                    }

                    export async function resolveSubCommand(
                      value: string,
                    ): Promise<string> {
                      return value;
                    }
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "src" / "toolkit.ts").write_text(
                textwrap.dedent(
                    """
                    export default class Toolkit {
                      serialize(value: string): string {
                        return value;
                      }

                      static defaultInstance = new Toolkit();
                      static serialize = Toolkit.defaultInstance.serialize.bind(Toolkit.defaultInstance);
                    }

                    export const serializeValue = Toolkit.serialize;
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "src" / "index.ts").write_text(
                textwrap.dedent(
                    """
                    export { defineCommand } from "./args.ts";
                    export { runCommand, resolveSubCommand } from "./command.ts";
                    export { serializeValue } from "./toolkit.ts";
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            test_path = root / "tests" / "api.test.ts"
            test_path.write_text(
                textwrap.dedent(
                    """
                    import { describe, it, expect, vi } from "vitest";
                    import { defineCommand, serializeValue } from "../src/index.ts";
                    import { parseArgs } from "../src/args.ts";
                    import * as commandModule from "../src/command.ts";
                    import Toolkit from "../src/toolkit.ts";

                    describe("api", () => {
                      it.each([["value"]])("handles %s", (value) => {
                        expect(parseArgs(value)).toBe(value);
                        expect(defineCommand(value)).toBe(value);
                        expect(serializeValue(value)).toBe(value);
                      });

                      it("uses namespace import", async () => {
                        vi.spyOn(commandModule, "runCommand");
                        await commandModule.runCommand("x");
                        await commandModule.resolveSubCommand("y");
                      });

                      it("uses class static field", () => {
                        expect(Toolkit.serialize("x")).toBe("x");
                      });
                    });
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            ev = scan_typescript(
                source_paths=[
                    root / "src" / "args.ts",
                    root / "src" / "command.ts",
                    root / "src" / "toolkit.ts",
                    root / "src" / "index.ts",
                ],
                test_paths=[test_path],
                project_name="demo",
            )

            tested = ev.tested_symbols()
            self.assertTrue(
                {
                    "Toolkit",
                    "defineCommand",
                    "parseArgs",
                    "resolveSubCommand",
                    "runCommand",
                    "serialize",
                    "serializeValue",
                }.issubset(tested)
            )

            args_mod = next(mod for mod in ev.source_files if Path(mod.path).name == "args.ts")
            self.assertEqual([fn.name for fn in args_mod.functions], ["defineCommand", "parseArgs"])

            toolkit_mod = next(mod for mod in ev.source_files if Path(mod.path).name == "toolkit.ts")
            self.assertEqual([cls.name for cls in toolkit_mod.classes], ["Toolkit"])
            toolkit_cls = toolkit_mod.classes[0]
            self.assertEqual([method.name for method in toolkit_cls.methods], ["serialize"])
            self.assertEqual(
                {name for name, _ in toolkit_cls.class_variables},
                {"defaultInstance", "serialize"},
            )

    def test_scan_typescript_does_not_create_lockfile_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)
            (root / "package-lock.json").unlink()

            source_path = root / "src" / "args.ts"
            source_path.write_text(
                "export function parseArgs(value: string): string { return value; }\n",
                encoding="utf-8",
            )
            test_path = root / "tests" / "args.test.ts"
            test_path.write_text(
                'import { parseArgs } from "../src/args.ts";\n',
                encoding="utf-8",
            )

            ev = scan_typescript(
                source_paths=[source_path],
                test_paths=[test_path],
                project_name="demo",
            )

            self.assertEqual(ev.project_name, "demo")
            self.assertFalse((root / "package-lock.json").exists())


if __name__ == "__main__":
    unittest.main()
