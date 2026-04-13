"""Tests for node_validator: TypeScript prompt validation against evidence."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ast_pilot.evidence import ClassInfo, Evidence, FunctionInfo, ModuleInfo, Parameter
from ast_pilot.node_validator import validate


class NodeValidatorSymbolTests(unittest.TestCase):
    def test_flags_missing_class(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    classes=[ClassInfo(name="Widget", qualname="lib.Widget", module="lib", lineno=1)],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text("# demo\n\nNo mention of the class.\n", encoding="utf-8")
            vr = validate(ev, md_path)
        self.assertTrue(any("Widget" in i.message and i.severity == "error" for i in vr.issues))

    def test_flags_missing_function(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    functions=[FunctionInfo(name="parseArgs", qualname="lib.parseArgs", module="lib", lineno=1)],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text("# demo\n\nNothing here.\n", encoding="utf-8")
            vr = validate(ev, md_path)
        self.assertTrue(any("parseArgs" in i.message and i.severity == "error" for i in vr.issues))

    def test_passes_when_all_symbols_present(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    functions=[FunctionInfo(name="parseArgs", qualname="lib.parseArgs", module="lib", lineno=1)],
                    classes=[ClassInfo(name="Widget", qualname="lib.Widget", module="lib", lineno=10)],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text("# demo\n\nUse `Widget` and `parseArgs`.\n", encoding="utf-8")
            vr = validate(ev, md_path)
        symbol_errors = [i for i in vr.issues if i.section == "symbols" and i.severity == "error"]
        self.assertEqual(len(symbol_errors), 0)


class NodeValidatorParamTests(unittest.TestCase):
    def test_flags_parameter_name_drift(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    functions=[
                        FunctionInfo(
                            name="repeat",
                            qualname="lib.repeat",
                            module="lib",
                            lineno=1,
                            params=[
                                Parameter(name="value", annotation="string"),
                                Parameter(name="count", annotation="number", default="1"),
                            ],
                            signature_params="value: string, count: number = 1",
                            return_annotation="string",
                        ),
                    ],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    ### 1. `repeat` Function

                    ```typescript
                    export function repeat(value: string, size: number = 1): string
                    ```
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
        self.assertTrue(any(i.section == "parameters" for i in vr.issues))


class NodeValidatorReturnTypeTests(unittest.TestCase):
    def test_flags_return_type_mismatch(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    functions=[
                        FunctionInfo(
                            name="fetch",
                            qualname="lib.fetch",
                            module="lib",
                            lineno=1,
                            return_annotation="Promise<string>",
                            is_async=True,
                        ),
                    ],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    ### 1. `fetch` Function

                    ```typescript
                    async function fetch(): string
                    ```
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
        self.assertTrue(any(i.section == "return_type" for i in vr.issues))


class NodeValidatorConstantTests(unittest.TestCase):
    def test_flags_constant_value_drift(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    constants=[("MAX_SIZE", "1024")],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    ```typescript
                    export const MAX_SIZE = 2048;
                    ```
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
        self.assertTrue(any(i.section == "constants" for i in vr.issues))


class NodeValidatorInventedSymbolTests(unittest.TestCase):
    def test_flags_invented_function(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    functions=[FunctionInfo(name="real", qualname="lib.real", module="lib", lineno=1)],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    Use `real`.

                    ```typescript
                    export function invented(x: string): void {
                    ```
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
        self.assertTrue(any(i.section == "invented_symbol" for i in vr.issues))


class NodeValidatorFieldCountTests(unittest.TestCase):
    def test_flags_wrong_field_count(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    classes=[
                        ClassInfo(
                            name="Widget",
                            qualname="lib.Widget",
                            module="lib",
                            lineno=1,
                            class_variables=[("first", "number"), ("second", "string")],
                        )
                    ],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    ### 1. `Widget` Class
                    This class has 5 fields.
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
            field_count_issues = [i for i in vr.issues if i.section == "field_count"]
            self.assertGreater(len(field_count_issues), 0, "field_count check now ported to TS")


class NodeValidatorStringLiteralTests(unittest.TestCase):
    def test_flags_unknown_key(self) -> None:
        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    string_literals=["accessToken"],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    ## Natural Language Instructions

                    The function returns result["badKey"] object.
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
            string_issues = [i for i in vr.issues if i.section == "string_literal"]
            self.assertGreater(len(string_issues), 0, "string_literal check now ported to TS")


class NodeValidatorInterfaceMemberTests(unittest.TestCase):
    def test_flags_missing_interface_member(self) -> None:
        from ast_pilot.evidence import InterfaceInfo

        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    interfaces=[
                        InterfaceInfo(
                            name="RegisterOptions",
                            module="lib",
                            lineno=1,
                            members=[("identifier", "string"), ("allowProps", "string[]")],
                        )
                    ],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    Use `RegisterOptions` with `identifier`.
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
            iface_issues = [i for i in vr.issues if i.section == "interface_member"]
            self.assertTrue(any("allowProps" in i.message for i in iface_issues))

    def test_passes_when_all_members_present(self) -> None:
        from ast_pilot.evidence import InterfaceInfo

        ev = Evidence(
            project_name="demo",
            language="typescript",
            source_files=[
                ModuleInfo(
                    path="/src/lib.ts",
                    module_name="lib",
                    interfaces=[
                        InterfaceInfo(
                            name="RegisterOptions",
                            module="lib",
                            lineno=1,
                            members=[("identifier", "string"), ("allowProps", "string[]")],
                        )
                    ],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "start.md"
            md_path.write_text(
                textwrap.dedent("""\
                    # demo

                    Use `RegisterOptions` with `identifier` and `allowProps`.
                """),
                encoding="utf-8",
            )
            vr = validate(ev, md_path)
            iface_issues = [i for i in vr.issues if i.section == "interface_member"]
            self.assertEqual(len(iface_issues), 0)


if __name__ == "__main__":
    unittest.main()
