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
    # Literals the tests assert must appear in the agent's output
    # (e.g. ``assert "123456789:***" in result``).
    assertion_in_literals: list[str] = field(default_factory=list)
    # Literals the tests assert must NOT appear in the agent's output.
    assertion_not_in_literals: list[str] = field(default_factory=list)
    # Literals the tests assert exact equality against (e.g. ``assert x == "foo"``).
    assertion_eq_literals: list[str] = field(default_factory=list)


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


def extract_grader_expectations(
    test_files: list[tuple[str, str]],
    *,
    language: str = "",
) -> GraderExpectations:
    """Extract all concrete expectations from test file contents.

    *test_files* is a list of ``(filename, content)`` tuples.
    *language* can be ``"python"`` or ``"typescript"``; auto-detected from
    file extensions when empty.
    """
    if not language:
        for fname, _ in test_files:
            if fname.endswith((".ts", ".mts")):
                language = "typescript"
                break
        else:
            language = "python"

    if language == "typescript":
        return _extract_ts_expectations(test_files)

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


def extract_prompt_surface(prompt_md: str, *, language: str = "") -> PromptSurface:
    """Extract the API surface mentioned in a prompt markdown."""
    surface = PromptSurface()

    for m in re.finditer(r"`(\w+)(?:\([^)]*\))?`", prompt_md):
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"(?:def|class|function|interface|type)\s+(\w+)", prompt_md):
        surface.code_block_defs.add(m.group(1))
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"\.(\w+)\s*\(", prompt_md):
        surface.mentioned_symbols.add(m.group(1))

    for m in re.finditer(r"from\s+([\w.]+)\s+import", prompt_md):
        surface.mentioned_modules.add(m.group(1))

    for m in re.finditer(r"import\s+([\w.]+)", prompt_md):
        surface.mentioned_modules.add(m.group(1))

    for m in re.finditer(r"import\s+\{([^}]+)\}\s+from", prompt_md):
        for name in m.group(1).split(","):
            name = name.strip().split(" as ")[0].strip()
            if name:
                surface.mentioned_symbols.add(name)

    for m in re.finditer(r"`([\w.]+\.(?:py|ts|mts))`", prompt_md):
        stem = re.sub(r"\.(py|ts|mts)$", "", m.group(1))
        surface.mentioned_modules.add(stem)

    for m in re.finditer(r"(\w+)\.(\w+)", prompt_md):
        surface.mentioned_symbols.add(m.group(1))
        surface.mentioned_symbols.add(m.group(2))

    for m in re.finditer(r"(\w+)\??\s*:\s*", prompt_md):
        surface.mentioned_symbols.add(m.group(1))

    return surface


_TS_NOISE = {
    # test framework
    "describe", "it", "test", "expect", "vi", "beforeEach", "afterEach",
    "beforeAll", "afterAll", "jest", "vitest", "assert",
    "toBe", "toEqual", "toStrictEqual", "toThrow", "toThrowError",
    "toBeUndefined", "toBeDefined", "toBeNull", "toBeTruthy", "toBeFalsy",
    "toContain", "toHaveLength", "toHaveProperty", "toMatch", "toMatchObject",
    "toHaveBeenCalled", "toHaveBeenCalledWith", "toHaveBeenCalledTimes",
    "toMatchInlineSnapshot", "toMatchSnapshot", "toHaveReturnedWith",
    "spyOn", "fn", "mock", "mockReturnValue", "mockImplementation",
    "each", "skip", "only", "todo", "concurrent", "fails",
    "expectTypeOf", "assertType",
    # JS keywords / operators the regex picks up
    "if", "else", "for", "while", "do", "switch", "case", "break",
    "continue", "return", "throw", "try", "catch", "finally",
    "new", "delete", "typeof", "instanceof", "in", "of", "void",
    "var", "let", "const", "function", "class", "extends", "super",
    "import", "export", "default", "as", "from", "async", "await",
    "yield", "with", "debugger",
    # primitives / builtin types
    "any", "undefined", "null", "true", "false",
    "string", "number", "boolean", "object", "symbol", "bigint", "never", "unknown",
    # builtin globals
    "Array", "Map", "Set", "Date", "Error", "RegExp", "Promise", "WeakMap", "WeakSet",
    "Int8Array", "Uint8Array", "Int16Array", "Uint16Array",
    "Int32Array", "Uint32Array", "Float32Array", "Float64Array",
    "BigInt64Array", "BigUint64Array", "ArrayBuffer", "SharedArrayBuffer", "DataView",
    "Proxy", "Reflect", "Symbol", "Intl", "WeakRef", "FinalizationRegistry",
    "console", "log", "warn", "error", "info", "debug", "trace",
    "JSON", "Math", "Object", "String", "Number", "Boolean",
    "require", "module", "exports", "process",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "Buffer", "URL", "TextEncoder", "TextDecoder",
    # common builtin methods / properties
    "length", "push", "pop", "shift", "unshift", "splice", "slice", "concat",
    "map", "filter", "reduce", "find", "findIndex", "some", "every", "flat", "flatMap",
    "sort", "reverse", "indexOf", "includes", "join", "fill",
    "keys", "values", "entries", "has", "get", "set", "delete", "clear", "add",
    "toString", "valueOf", "constructor", "prototype", "__proto__",
    "bind", "call", "apply",
    "then", "catch", "resolve", "reject", "all", "allSettled", "race", "any",
    "assign", "create", "defineProperty", "freeze", "isFrozen",
    "getPrototypeOf", "setPrototypeOf", "getOwnPropertyDescriptor",
    "is", "isArray", "isNaN", "isFinite", "isInteger", "isSafeInteger",
    "from", "of", "parse", "stringify",
    "name", "message", "stack", "cause", "code",
    "configurable", "enumerable", "writable", "value",
    "iterator", "toStringTag", "hasInstance", "toPrimitive",
    # short generic identifiers that are always test-data noise
    "ext", "num", "arr", "obj", "val", "res", "ret", "tmp", "str", "msg",
    "foo", "bar", "baz", "qux", "boo",
    "deep", "nested",
}


def compute_gaps(
    expectations: GraderExpectations,
    surface: PromptSurface,
    *,
    language: str = "",
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

    if language == "typescript":
        NOISE |= _TS_NOISE

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
        if language == "typescript" and any(p in NOISE for p in parts):
            continue
        if method_name not in all_prompt and method not in all_prompt:
            report.methods_not_in_prompt.append(method)

    for attr in expectations.accessed_attributes:
        parts = attr.split(".")
        attr_name = parts[-1] if parts else attr
        if attr_name in NOISE or attr_name.startswith("_"):
            continue
        if language == "typescript" and any(p in NOISE for p in parts):
            continue
        if language == "typescript" and len(attr_name) <= 3:
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


_LITERAL_MIN_LEN = 3
_LITERAL_MAX_LEN = 200


def _keep_literal(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not (_LITERAL_MIN_LEN <= len(stripped) <= _LITERAL_MAX_LEN):
        return False
    return not stripped.startswith("#")


def _extract_string_literals(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and _keep_literal(node.value):
            exp.string_literals.append(node.value.strip())


def _extract_assertions(tree: ast.AST, exp: GraderExpectations) -> None:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assert) and node.test):
            continue
        if not isinstance(node.test, ast.Compare):
            continue
        if len(node.test.ops) != 1:
            continue
        op = node.test.ops[0]
        left = node.test.left
        right = node.test.comparators[0]

        left_lit = left.value if isinstance(left, ast.Constant) else None
        right_lit = right.value if isinstance(right, ast.Constant) else None

        if isinstance(op, (ast.Eq, ast.NotEq)):
            for side in (left_lit, right_lit):
                if _keep_literal(side):
                    exp.asserted_values.append(repr(side))
                    if isinstance(op, ast.Eq):
                        exp.assertion_eq_literals.append(side)
        elif isinstance(op, ast.In) and _keep_literal(left_lit):
            exp.assertion_in_literals.append(left_lit)
        elif isinstance(op, ast.NotIn) and _keep_literal(left_lit):
            exp.assertion_not_in_literals.append(left_lit)


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


def _extract_ts_expectations(test_files: list[tuple[str, str]]) -> GraderExpectations:
    """Regex-based extraction of grader expectations from TypeScript test files."""
    exp = GraderExpectations()

    _TS_IMPORT_RE = re.compile(
        r"""import\s+(?:type\s+)?"""
        r"""(?:\{([^}]+)\}\s+from|([A-Za-z_$]\w*)\s+from|\*\s+as\s+(\w+)\s+from)"""
        r"""\s+['"]([^'"]+)['"]"""
    )
    _TS_CALL_RE = re.compile(r"(\w+(?:\.\w+)*)\s*\(")
    _TS_MEMBER_RE = re.compile(r"(\w+)\.(\w+)")
    _TS_NEW_RE = re.compile(r"new\s+(\w+)\s*\(")
    _TS_STRING_RE = re.compile(r"""['"](\w[\w.-]{2,})['"]""")
    _TS_EXPECT_RE = re.compile(r"(?:toBe|toEqual|toStrictEqual)\s*\(\s*(.+?)\s*\)")
    _TS_OBJ_PROP_RE = re.compile(r"(\w+)\s*:")

    for _filename, content in test_files:
        for m in _TS_IMPORT_RE.finditer(content):
            named = m.group(1)
            default = m.group(2)
            namespace = m.group(3)
            module = m.group(4)
            exp.imported_modules.append(module)
            if named:
                for name in named.split(","):
                    name = name.strip().split(" as ")[0].strip()
                    if name and name != "type":
                        exp.imported_names.append(name)
            if default:
                exp.imported_names.append(default)
            if namespace:
                exp.imported_names.append(namespace)

        for m in _TS_CALL_RE.finditer(content):
            chain = m.group(1)
            exp.called_methods.append(chain)
            parts = chain.split(".")
            if len(parts) > 1:
                exp.accessed_attributes.append(chain)

        for m in _TS_MEMBER_RE.finditer(content):
            exp.accessed_attributes.append(f"{m.group(1)}.{m.group(2)}")

        for m in _TS_NEW_RE.finditer(content):
            exp.instantiated_classes.append(m.group(1))

        for m in _TS_STRING_RE.finditer(content):
            val = m.group(1)
            if 3 <= len(val) <= 200:
                exp.string_literals.append(val)

        for m in _TS_EXPECT_RE.finditer(content):
            exp.asserted_values.append(m.group(1).strip())

        for m in _TS_OBJ_PROP_RE.finditer(content):
            prop = m.group(1)
            if len(prop) >= 3 and not prop[0].isupper():
                exp.accessed_attributes.append(prop)

        _extract_ts_assertion_literals(content, exp)

    _dedupe(exp)
    return exp


_TS_CONTAIN_RE = re.compile(
    r"""(\.not)?\.toContain\s*\(\s*['"`]([^'"`]+)['"`]"""
)
_TS_EQUALITY_RE = re.compile(
    r"""\.(?:toBe|toEqual|toStrictEqual)\s*\(\s*['"`]([^'"`]+)['"`]"""
)


def _extract_ts_assertion_literals(content: str, exp: GraderExpectations) -> None:
    for m in _TS_CONTAIN_RE.finditer(content):
        literal = m.group(2)
        if not _keep_literal(literal):
            continue
        if m.group(1):
            exp.assertion_not_in_literals.append(literal)
        else:
            exp.assertion_in_literals.append(literal)

    for m in _TS_EQUALITY_RE.finditer(content):
        literal = m.group(1)
        if _keep_literal(literal):
            exp.assertion_eq_literals.append(literal)


def _dedupe(exp: GraderExpectations) -> None:
    exp.imported_names = sorted(set(exp.imported_names))
    exp.imported_modules = sorted(set(exp.imported_modules))
    exp.called_methods = sorted(set(exp.called_methods))
    exp.accessed_attributes = sorted(set(exp.accessed_attributes))
    exp.instantiated_classes = sorted(set(exp.instantiated_classes))
    exp.string_literals = sorted(set(exp.string_literals))
    exp.asserted_values = sorted(set(exp.asserted_values))
    exp.assertion_in_literals = sorted(set(exp.assertion_in_literals))
    exp.assertion_not_in_literals = sorted(set(exp.assertion_not_in_literals))
    exp.assertion_eq_literals = sorted(set(exp.assertion_eq_literals))


_ASSERTION_LITERAL_CAP = 60


def format_asserted_literals_for_llm(exp: GraderExpectations) -> str:
    """Render asserted test literals into a reviewer-facing section.

    Returns an empty string when the tests assert no notable literals, so the
    caller can skip the section entirely.
    """
    sections: list[str] = []

    def _emit(heading: str, literals: list[str]) -> None:
        if not literals:
            return
        by_len = sorted(literals, key=lambda s: (-len(s), s))[:_ASSERTION_LITERAL_CAP]
        sections.append(heading)
        for lit in by_len:
            sections.append(f"  - {lit!r}")
        overflow = len(literals) - len(by_len)
        if overflow > 0:
            sections.append(f"  (+ {overflow} more omitted)")

    _emit(
        "Must appear in agent output (assert <literal> in result):",
        exp.assertion_in_literals,
    )
    _emit(
        "\nMust NOT appear in agent output (assert <literal> not in result):",
        exp.assertion_not_in_literals,
    )
    _emit(
        "\nExact equality (assert x == <literal>):",
        exp.assertion_eq_literals,
    )

    if not sections:
        return ""

    header = (
        "ASSERTED TEST LITERALS (cross-check every one against the prompt):\n"
        "For each literal below, locate the prompt instruction that produces it. "
        "If the prompt's substitution or formatting rule would emit a DIFFERENT "
        "literal, that is a direct_contradiction — report it with safe_to_fix=true "
        "so the instruction can be rewritten to match the asserted literal.\n"
    )
    return header + "\n".join(sections)
