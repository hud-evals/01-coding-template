"""Validator: cross-check a generated prompt.md against the evidence store.

Catches factual errors the LLM introduced: wrong param names, wrong return
types, invented symbols, wrong constant values, wrong dict key names.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .evidence import Evidence
from .scanner import _annotation_str, _format_signature_params


@dataclass
class ValidationIssue:
    severity: str  # "error" or "warning"
    section: str
    message: str
    line: int = 0


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def summary(self) -> str:
        if self.passed and self.warning_count == 0:
            return "PASSED: no factual issues found"
        lines = []
        if self.error_count:
            lines.append(f"ERRORS: {self.error_count}")
        if self.warning_count:
            lines.append(f"WARNINGS: {self.warning_count}")
        for issue in self.issues:
            prefix = "ERROR" if issue.severity == "error" else "WARN"
            loc = f" (line {issue.line})" if issue.line else ""
            lines.append(f"  [{prefix}] {issue.section}{loc}: {issue.message}")
        return "\n".join(lines)


@dataclass(frozen=True)
class DocumentedSignature:
    line: int
    owner: str
    name: str
    params: str
    return_annotation: str


def validate(ev: Evidence, md_path: str | Path) -> ValidationResult:
    """Validate a generated prompt.md against its evidence store."""

    md = Path(md_path).read_text(encoding="utf-8")
    md_lines = md.splitlines()
    result = ValidationResult()

    _check_symbols_exist(ev, md, md_lines, result)
    _check_param_names(ev, md, md_lines, result)
    _check_return_types(ev, md, md_lines, result)
    _check_constant_values(ev, md, md_lines, result)
    _check_field_counts(ev, md, md_lines, result)
    _check_string_literals(ev, md, md_lines, result)
    _check_no_invented_symbols(ev, md, md_lines, result)

    return result


def _check_symbols_exist(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Every public class/function in evidence must appear in the md."""

    for mod in ev.source_files:
        for cls in mod.classes:
            if cls.name.startswith("_"):
                continue
            if cls.name not in md:
                result.issues.append(
                    ValidationIssue("error", "symbols", f"public class '{cls.name}' not mentioned in prompt.md")
                )
            for method in cls.methods:
                if method.name.startswith("_") and not method.name.startswith("__"):
                    continue
                if method.name not in md:
                    result.issues.append(
                        ValidationIssue("warning", "symbols", f"method '{cls.name}.{method.name}' not mentioned")
                    )

        for fn in mod.functions:
            if fn.name.startswith("_"):
                continue
            if fn.name not in md:
                result.issues.append(
                    ValidationIssue("error", "symbols", f"public function '{fn.name}' not mentioned in prompt.md")
                )


def _check_param_names(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check that documented function signatures match the evidence exactly."""

    sig_map: dict[tuple[str, str], str] = {}
    for mod in ev.source_files:
        for fn in mod.functions:
            sig_map[("", fn.name)] = fn.signature_params or _fallback_signature_params(fn)
        for cls in mod.classes:
            for method in cls.methods:
                sig_map[(cls.name, method.name)] = method.signature_params or _fallback_signature_params(method)

    for sig in _iter_documented_signatures(md_lines):
        ev_params = sig_map.get((sig.owner, sig.name))
        if ev_params is None and sig.owner:
            ev_params = sig_map.get(("", sig.name))
        if ev_params is None:
            continue
        if _normalize_signature(sig.params) != _normalize_signature(ev_params):
            symbol = _display_symbol(sig.owner, sig.name)
            result.issues.append(
                ValidationIssue(
                    "error",
                    "parameters",
                    f"'{symbol}' parameters: md says '{sig.params}', evidence says '{ev_params}'",
                    line=sig.line,
                )
            )


def _check_return_types(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check return types mentioned in the md match the evidence.

    Uses class context: when a `def load(...)` appears in the md, we look
    backwards for the nearest class heading to determine which class's `load`
    we're comparing against. This prevents cross-contamination when multiple
    classes share a method name.
    """

    sig_map: dict[tuple[str, str], str] = {}
    for mod in ev.source_files:
        for fn in mod.functions:
            sig_map[("", fn.name)] = fn.return_annotation
        for cls in mod.classes:
            for method in cls.methods:
                sig_map[(cls.name, method.name)] = method.return_annotation

    for sig in _iter_documented_signatures(md_lines):
        ev_ret = sig_map.get((sig.owner, sig.name))
        if ev_ret is None and sig.owner:
            ev_ret = sig_map.get(("", sig.name))
        if ev_ret is None:
            continue

        ev_ret = ev_ret.strip().strip('"').strip("'")
        if not _types_equivalent(sig.return_annotation, ev_ret):
            symbol = _display_symbol(sig.owner, sig.name)
            result.issues.append(
                ValidationIssue(
                    "error",
                    "return_type",
                    f"'{symbol}' return type: md says '{sig.return_annotation}', evidence says '{ev_ret}'",
                    line=sig.line,
                )
            )


def _check_constant_values(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check constant values in md match the evidence."""

    in_code_block = False
    for mod in ev.source_files:
        for name, value in mod.constants:
            if name.startswith("_") or len(value) > 80:
                continue
            if "\n" in value or "{" in value or "[" in value:
                continue
            pattern = rf"^{re.escape(name)}\s*=\s*(.+)$"
            for i, line in enumerate(md_lines):
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if not in_code_block:
                    continue
                m = re.search(pattern, stripped)
                if not m:
                    continue
                md_value = m.group(1).strip().rstrip(",").strip()
                ev_value = value.strip()
                if md_value and ev_value and _normalize_value(md_value) != _normalize_value(ev_value):
                    result.issues.append(
                        ValidationIssue(
                            "error",
                            "constants",
                            f"'{name}': md has '{md_value}', evidence has '{ev_value}'",
                            line=i + 1,
                        )
                    )


def _check_field_counts(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check that field/method counts match."""

    for mod in ev.source_files:
        for cls in mod.classes:
            if cls.name.startswith("_"):
                continue
            actual_fields = len(cls.class_variables)
            if actual_fields == 0:
                continue
            for i, line in enumerate(md_lines):
                m = re.search(r"(\d+)\s+fields?", line)
                window = md_lines[max(0, i - 2) : i + 1]
                if m and any(cls.name.lower() in candidate.lower() for candidate in window):
                    claimed = int(m.group(1))
                    if claimed != actual_fields:
                        result.issues.append(
                            ValidationIssue(
                                "error",
                                "field_count",
                                f"'{cls.name}': md claims {claimed} fields, evidence has {actual_fields}",
                                line=i + 1,
                            )
                        )


def _check_string_literals(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check that dict key names and string literals in md match the source."""

    all_literals: set[str] = set()
    for mod in ev.source_files:
        all_literals.update(mod.string_literals)

    if not all_literals:
        return

    known_names: set[str] = set()
    for mod in ev.source_files:
        known_names.add(mod.module_name)
        for fn in mod.functions:
            known_names.add(fn.name)
            for p in fn.params:
                known_names.add(p.name)
        for cls in mod.classes:
            known_names.add(cls.name)
            for v, _ in cls.class_variables:
                known_names.add(v)
            for m in cls.methods:
                known_names.add(m.name)
                for p in m.params:
                    known_names.add(p.name)
        for name, _ in mod.constants:
            known_names.add(name)

    key_patterns = [
        r'(?:entry|dict|data|payload|obj|item|result|record)\["(\w+)"\]',
        r'"(\w+)"\s+key\b',
        r'\bkey\s+"(\w+)"',
        r'(?:a|the|with a)\s+"(\w+)"\s+(?:key|field)',
        r"'(\w+)'\s+key\b",
        r"\bkey\s+'(\w+)'",
    ]

    current_section = ""
    in_code_block = False

    for i, line in enumerate(md_lines):
        stripped = line.strip()
        if not in_code_block and stripped.startswith("## "):
            current_section = stripped[3:].strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block and current_section == "Implementation Notes":
            continue

        for pattern in key_patterns:
            for m in re.finditer(pattern, line):
                mentioned = m.group(1)
                if len(mentioned) < 3:
                    continue
                if mentioned in all_literals or mentioned in known_names:
                    continue
                candidates = [lit for lit in all_literals if len(lit) > 3 and lit not in known_names]
                if candidates:
                    result.issues.append(
                        ValidationIssue(
                            "error",
                            "string_literal",
                            f'md mentions key "{mentioned}" which is not in the source. Source dict keys include: {", ".join(sorted(candidates)[:5])}',
                            line=i + 1,
                        )
                    )


def _check_no_invented_symbols(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check for method/function names in the md that don't exist in evidence."""

    known_symbols: set[str] = set()
    for mod in ev.source_files:
        for fn in mod.functions:
            known_symbols.add(fn.name)
        for cls in mod.classes:
            known_symbols.add(cls.name)
            for m in cls.methods:
                known_symbols.add(m.name)

    for i, line in enumerate(md_lines):
        for m in re.finditer(r"def\s+(\w+)\s*\(", line):
            name = m.group(1)
            if name not in known_symbols and not name.startswith("test"):
                result.issues.append(
                    ValidationIssue(
                        "warning",
                        "invented_symbol",
                        f"md references 'def {name}(...)' which is not in the evidence",
                        line=i + 1,
                    )
                )


def _types_equivalent(a: str, b: str) -> bool:
    """Check if two type annotations are equivalent despite formatting."""

    a = a.strip().replace(" ", "").replace('"', "").replace("'", "").rstrip(")").rstrip("`").rstrip("*")
    b = b.strip().replace(" ", "").replace('"', "").replace("'", "").rstrip(")").rstrip("`").rstrip("*")
    return a == b


def _iter_documented_signatures(md_lines: list[str]) -> list[DocumentedSignature]:
    signatures: list[DocumentedSignature] = []
    current_class = ""

    for i, line in enumerate(md_lines):
        stripped = line.strip()

        class_heading = re.match(r"^###\s+\d+\.\s+`(\w+)`\s+[Cc]lass$", stripped)
        if class_heading:
            current_class = class_heading.group(1)
            continue

        function_heading = re.match(r"^###\s+\d+\.\s+`(\w+)`\s+[Ff]unction$", stripped)
        if function_heading:
            current_class = ""
            continue

        parsed = _parse_signature_line(stripped)
        if parsed is None:
            continue

        fn_name, params, ret = parsed
        signatures.append(
            DocumentedSignature(
                line=i + 1,
                owner=current_class,
                name=fn_name,
                params=params,
                return_annotation=ret,
            )
        )

    return signatures


def _parse_signature_line(line: str) -> tuple[str, str, str] | None:
    if not line.startswith(("def ", "async def ")):
        return None

    wrapped = f"{line}\n    pass\n"
    try:
        tree = ast.parse(wrapped)
    except SyntaxError:
        return None

    node = tree.body[0] if tree.body else None
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return None

    params = _format_signature_params(node.args, wrapped)
    return_annotation = _annotation_str(node.returns, wrapped).strip().strip('"').strip("'")
    return node.name, params, return_annotation


def _fallback_signature_params(fn) -> str:
    parts: list[str] = []
    for param in fn.params:
        piece = param.name
        if param.annotation:
            piece += f": {param.annotation}"
        if param.default:
            piece += f" = {param.default}"
        parts.append(piece)
    return ", ".join(parts)


def _normalize_signature(value: str) -> str:
    return value.strip().replace(" ", "").replace('"', "'")


def _display_symbol(owner: str, name: str) -> str:
    return f"{owner}.{name}" if owner else name


def _normalize_value(v: str) -> str:
    return v.strip().replace(" ", "").replace('"', "'").replace("\n", "")
