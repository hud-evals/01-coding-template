"""Tests for node_spec_renderer: TypeScript prompt rendering."""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import Evidence, ModuleInfo, TestEvidence
from ast_pilot.node_scanner import scan_typescript
from ast_pilot.node_spec_renderer import (
    _build_exact_api_listing,
    _build_test_facts,
    render_start_md,
)


class NodeSpecRendererTests(unittest.TestCase):
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

    def test_render_start_md_includes_tested_functions_and_class_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_repo(root)

            (root / "src" / "args.ts").write_text(
                textwrap.dedent(
                    """
                    export function defineCommand(value: string): string {
                      return value;
                    }

                    export const parseArgs = (value: string): string => value;
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "src" / "command.ts").write_text(
                textwrap.dedent(
                    """
                    export async function runCommand(value: string): Promise<string> {
                      return value;
                    }

                    export async function resolveSubCommand(value: string): Promise<string> {
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
            test_path = root / "tests" / "api.test.ts"
            test_path.write_text(
                textwrap.dedent(
                    """
                    import { describe, it, expect, vi } from "vitest";
                    import { defineCommand } from "../src/args.ts";
                    import { parseArgs } from "../src/args.ts";
                    import * as commandModule from "../src/command.ts";
                    import Toolkit, { serializeValue } from "../src/toolkit.ts";

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
                ],
                test_paths=[test_path],
                project_name="demo",
            )
            md = render_start_md(ev, use_llm=False)

            self.assertIn("## Required Tested Symbols", md)
            self.assertIn("function parseArgs(value: string): string", md)
            self.assertIn("function defineCommand(value: string): string", md)
            self.assertIn("async function runCommand(value: string): Promise<string>", md)
            self.assertIn("async function resolveSubCommand(value: string): Promise<string>", md)
            self.assertIn("serializeValue", md)
            self.assertIn("Toolkit.serialize", md)
            self.assertIn("**Class Variables:**", md)

    def test_exact_api_dumps_long_constant_values_verbatim(self) -> None:
        """Long TS constants (e.g. prefix arrays) must reach LLM grounding.

        Regression: earlier `len(value) < 120` cap silently dropped long list
        literals, forcing the LLM to summarise them as "and others".
        """
        long_value = "[" + ", ".join(f'/prefix{i}_[a-z]+/' for i in range(20)) + "]"
        self.assertGreater(len(long_value), 120)
        mod = ModuleInfo(
            path="parser.ts",
            module_name="parser",
            constants=[("PREFIX_PATTERNS", long_value)],
        )
        ev = Evidence(source_files=[mod], tests=[], python_version="")
        out = _build_exact_api_listing(ev)
        self.assertIn("PREFIX_PATTERNS", out)
        self.assertIn("prefix0_", out)
        self.assertIn("prefix19_", out)

    def test_test_facts_preserve_long_snippets(self) -> None:
        """TS snippet truncation must not strip assertion literals late in the test body.

        Regression: earlier `[:500]` cut off expected object literals near the
        end of longer vitest bodies.
        """
        body = "\n".join(
            [f'  expect(parseRawArgs([{i}])).toEqual({{ token: "lit_{i}_xyz" }});' for i in range(40)]
        )
        snippet = f'it("long", () => {{\n{body}\n}});'
        self.assertGreater(len(snippet), 500)
        test_ev = TestEvidence(
            test_file="parser.test.ts",
            test_name="long",
            tested_symbols=["parseRawArgs"],
            source_snippet=snippet,
        )
        ev = Evidence(source_files=[], tests=[test_ev], python_version="")
        facts = _build_test_facts(ev)
        self.assertIn("lit_0_xyz", facts)
        self.assertIn("lit_39_xyz", facts)


if __name__ == "__main__":
    unittest.main()
