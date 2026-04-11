"""Deterministic extraction of grader expectations from hidden test files.

Uses AST to extract every concrete requirement the tests impose —
imported symbols, method calls, attribute accesses, constructor args,
file-path patterns — then diffs against what the prompt mentions.

This structured evidence is fed to the LLM reviewer so it does not
have to discover these needles on its own.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class GraderExpectations:
    """Concrete requirements extracted from hidden test files."""

    imported_names: list[str] = field(default_factory=list)
    imported_modules: list[str] = field(default_factory=list)
    called_methods: list[str] = field(default_factory=list)
    accessed_attributes: list[str] = field(default_factory=list)
    instantiated_classes: list[str] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    asserted_values: list[str] = field(default_factory=list)


@dataclass
class PromptSurface:
    """API surface mentioned in the prompt markdown."""

    mentioned_symbols: set[str] = field(default_factory=set)
    code_block_defs: set[str] = field(default_factory=set)
    mentioned_modules: set[str] = field(default_factory=set)


@dataclass
class GapReport:
    """Gaps between grader expectations and prompt surface."""

    imports_not_in_prompt: list[str] = field(default_factory=list)
    methods_not_in_prompt: list[str] = field(default_factory=list)
    attributes_not_in_prompt: list[str] = field(default_factory=list)
    classes_not_in_prompt: list[str] = field(default_factory=list)
    module_mismatches: list[str] = field(default_factory=list)

    @property
    def total_gaps(self) -> int:
        return (
            len(self.imports_not_in_prompt)
            + len(self.methods_not_in_prompt)
            + len(self.attributes_not_in_prompt)
            + len(self.classes_not_in_prompt)
            + len(self.module_mismatches)
        )

    def format_for_llm(self) -> str:
        if self.total_gaps == 0:
            return "No deterministic gaps found between test expectations and prompt."

        sections: list[str] = []
        sections.append(f"DETERMINISTIC GAP ANALYSIS ({self.total_gaps} gaps found):")
        sections.append("The following items are used by the hidden tests but NOT mentioned in the prompt.")
        sections.append("Each gap is a potential hidden requirement that the prompt should specify.\n")

        if self.imports_not_in_prompt:
            sections.append("IMPORTED NAMES not mentioned in prompt:")
            for name in self.imports_not_in_prompt:
                sections.append(f"  - {name}")

        if self.methods_not_in_prompt:
            sections.append("\nMETHOD CALLS not mentioned in prompt:")
            for name in self.methods_not_in_prompt:
                sections.append(f"  - {name}")

        if self.attributes_not_in_prompt:
            sections.append("\nATTRIBUTE ACCESSES not mentioned in prompt:")
            for name in self.attributes_not_in_prompt:
                sections.append(f"  - {name}")

        if self.classes_not_in_prompt:
            sections.append("\nCLASS INSTANTIATIONS not mentioned in prompt:")
            for name in self.classes_not_in_prompt:
                sections.append(f"  - {name}")

        if self.module_mismatches:
            sections.append("\nMODULE NAME ISSUES:")
            for issue in self.module_mismatches:
                sections.append(f"  - {issue}")

        return "\n".join(sections)


def extract_grader_expectations(test_files: list[tuple[str, str]]) -> GraderExpectations:
    """Extract all concrete expectations from test file contents.

    *test_files* is a list of ``(filename, content)`` tuples.
    """
    expectations = GraderExpectations()

    for _filename, content in test_files:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        _extract_imports(tree, expectations)
        _extract_calls_and_attrs(tree, expectations)
        _extract_string_literals(tree, expectations)
        _extract_assertions(tree, expectations)

    _dedupe(expectations)
    return expectations


def extract_prompt_surface(prompt_md: str) -> PromptSurface:
    """Extract the API surface mentioned in a prompt markdown."""
    surface = PromptSurface()

    for m in re.finditer(r"`(\w+)(?:\([^)]*\))?`", prompt_md):
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"(?:def|class)\s+(\w+)", prompt_md):
        surface.code_block_defs.add(m.group(1))
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"\.(\w+)\s*\(", prompt_md):
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"from\s+([\w.]+)\s+import", prompt_md):
        surface.mentioned_modules.add(m.group(1))

    for m in re.finditer(r"import\s+([\w.]+)", prompt_md):
        surface.mentioned_modules.add(m.group(1))

    for m in re.finditer(r"`([\w.]+\.py)`", prompt_md):
        stem = m.group(1).replace(".py", "")
        surface.mentioned_modules.add(stem)

    for m in re.finditer(r"(\w+)\.(\w+)", prompt_md):
        surface.mentioned_symbols.add(m.group(1))
        surface.mentioned_symbols.add(m.group(2))

    return surface


def compute_gaps(
    expectations: GraderExpectations,
    surface: PromptSurface,
) -> GapReport:
    """Compare grader expectations against prompt surface and find gaps."""
    report = GapReport()

    NOISE = {
        "self", "cls", "None", "True", "False", "str", "int", "float",
        "bool", "list", "dict", "set", "tuple", "bytes", "type",
        "Exception", "ValueError", "TypeError", "KeyError", "AttributeError",
        "RuntimeError", "FileNotFoundError", "IndexError", "StopIteration",
        "NotImplementedError", "OSError", "IOError", "ImportError",
        "AssertionError", "PermissionError",
        "pytest", "MagicMock", "patch", "monkeypatch", "tmp_path",
        "SimpleNamespace", "os", "sys", "json", "re", "time", "math",
        "pathlib", "Path", "tempfile", "textwrap", "unittest",
        "assert", "len", "range", "enumerate", "sorted", "isinstance",
        "print", "open", "getattr", "setattr", "hasattr", "super",
        "staticmethod", "classmethod", "property",
        "field", "dataclass", "dataclasses",
        "fixture", "parametrize", "mark", "raises",
        "return_value", "side_effect", "call_args", "called",
        "assert_called_once", "assert_called_with",
        "append", "extend", "insert", "pop", "remove", "clear",
        "get", "keys", "values", "items", "update",
        "strip", "split", "join", "replace", "lower", "upper",
        "startswith", "endswith", "format", "encode", "decode",
        "read", "write", "close", "seek", "tell",
        "exists", "is_file", "is_dir", "mkdir", "read_text", "write_text",
        "parent", "name", "stem", "suffix",
    }

    all_prompt = surface.mentioned_symbols | surface.code_block_defs

    for name in expectations.imported_names:
        if name in NOISE or name.startswith("_") or name.startswith("test"):
            continue
        if name not in all_prompt:
            report.imports_not_in_prompt.append(name)

    for method in expectations.called_methods:
        parts = method.split(".")
        method_name = parts[-1] if parts else method
        if method_name in NOISE or method_name.startswith("_"):
            continue
        if method_name not in all_prompt and method not in all_prompt:
            report.methods_not_in_prompt.append(method)

    for attr in expectations.accessed_attributes:
        parts = attr.split(".")
        attr_name = parts[-1] if parts else attr
        if attr_name in NOISE or attr_name.startswith("_"):
            continue
        if attr_name not in all_prompt and attr not in all_prompt:
            report.attributes_not_in_prompt.append(attr)

    for cls in expectations.instantiated_classes:
        if cls in NOISE or cls.startswith("_"):
            continue
        if cls not in all_prompt:
            report.classes_not_in_prompt.append(cls)

    for mod in expectations.imported_modules:
        mod_parts = mod.split(".")
        if any(part in NOISE for part in mod_parts):
            continue
        found = False
        for prompt_mod in surface.mentioned_modules:
            if mod == prompt_mod or mod.replace("_", "") == prompt_mod.replace("_", ""):
                found = True
                break
        if not found:
            stem = mod_parts[-1] if mod_parts else mod
            if stem in all_prompt or mod in all_prompt:
                found = True
        if not found:
            report.module_mismatches.append(
                f"Tests import from '{mod}' but prompt does not mention this module"
            )

    return report


def _extract_imports(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                exp.imported_modules.append(alias.name)
                local = alias.asname or alias.name.split(".")[-1]
                exp.imported_names.append(local)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                exp.imported_modules.append(node.module)
            for alias in node.names:
                exp.imported_names.append(alias.asname or alias.name)


def _extract_calls_and_attrs(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            chain = _resolve_call_chain(node.func)
            if chain:
                exp.called_methods.append(chain)
            if isinstance(node.func, ast.Name):
                exp.instantiated_classes.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                exp.called_methods.append(node.func.attr)

        elif isinstance(node, ast.Attribute):
            parent = _resolve_attr_chain(node)
            if parent and not isinstance(getattr(node, '_parent_is_call', None), ast.Call):
                exp.accessed_attributes.append(parent)


def _extract_string_literals(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.strip()
            if 3 <= len(val) <= 200 and not val.startswith("#"):
                exp.string_literals.append(val)


def _extract_assertions(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and node.test:
            if isinstance(node.test, ast.Compare):
                for comparator in node.test.comparators:
                    if isinstance(comparator, ast.Constant):
                        exp.asserted_values.append(repr(comparator.value))


def _resolve_call_chain(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_call_chain(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return ""


def _resolve_attr_chain(node: ast.Attribute) -> str:
    if isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    if isinstance(node.value, ast.Attribute):
        parent = _resolve_attr_chain(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return node.attr


def _dedupe(exp: GraderExpectations) -> None:
    exp.imported_names = sorted(set(exp.imported_names))
    exp.imported_modules = sorted(set(exp.imported_modules))
    exp.called_methods = sorted(set(exp.called_methods))
    exp.accessed_attributes = sorted(set(exp.accessed_attributes))
    exp.instantiated_classes = sorted(set(exp.instantiated_classes))
    exp.string_literals = sorted(set(exp.string_literals))
    exp.asserted_values = sorted(set(exp.asserted_values))
