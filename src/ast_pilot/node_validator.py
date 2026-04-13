"""Validator for TypeScript task prompts.

Cross-checks a generated start.md against the TypeScript evidence store.
Catches factual errors the LLM introduced: wrong param names, wrong return
types, invented symbols, wrong constant values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .evidence import Evidence
from .validator import ValidationIssue, ValidationResult


def validate(ev: Evidence, md_path: str | Path) -> ValidationResult:
    """Validate a generated start.md against TypeScript evidence."""
    md = Path(md_path).read_text(encoding="utf-8")
    md_lines = md.splitlines()
    result = ValidationResult()

    _check_symbols_exist(ev, md, result)
    _check_param_names(ev, md, md_lines, result)
    _check_return_types(ev, md, md_lines, result)
    _check_constant_values(ev, md, md_lines, result)
    _check_no_invented_symbols(ev, md, md_lines, result)

    return result


def _check_symbols_exist(ev: Evidence, md: str, result: ValidationResult) -> None:
    for mod in ev.source_files:
        for cls in mod.classes:
            if cls.name not in md:
                result.issues.append(
                    ValidationIssue("error", "symbols", f"exported class '{cls.name}' not mentioned in start.md")
                )
            for method in cls.methods:
                if method.name.startswith("_"):
                    continue
                if method.name not in md:
                    result.issues.append(
                        ValidationIssue("warning", "symbols", f"method '{cls.name}.{method.name}' not mentioned")
                    )

        for fn in mod.functions:
            if fn.name not in md:
                result.issues.append(
                    ValidationIssue("error", "symbols", f"exported function '{fn.name}' not mentioned in start.md")
                )


def _check_param_names(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    """Check that documented function signatures match the evidence."""
    sig_map: dict[tuple[str, str], str] = {}
    for mod in ev.source_files:
        for fn in mod.functions:
            sig_map[("", fn.name)] = fn.signature_params or _fallback_params(fn)
        for cls in mod.classes:
            for method in cls.methods:
                sig_map[(cls.name, method.name)] = method.signature_params or _fallback_params(method)

    for sig in _iter_documented_signatures(md_lines):
        ev_params = sig_map.get((sig["owner"], sig["name"]))
        if ev_params is None and sig["owner"]:
            ev_params = sig_map.get(("", sig["name"]))
        if ev_params is None:
            continue
        if _normalize_sig(sig["params"]) != _normalize_sig(ev_params):
            symbol = f"{sig['owner']}.{sig['name']}" if sig["owner"] else sig["name"]
            result.issues.append(
                ValidationIssue(
                    "error", "parameters",
                    f"'{symbol}' parameters: md says '{sig['params']}', evidence says '{ev_params}'",
                    line=sig["line"],
                )
            )


def _check_return_types(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    sig_map: dict[tuple[str, str], str] = {}
    for mod in ev.source_files:
        for fn in mod.functions:
            sig_map[("", fn.name)] = fn.return_annotation
        for cls in mod.classes:
            for method in cls.methods:
                sig_map[(cls.name, method.name)] = method.return_annotation

    for sig in _iter_documented_signatures(md_lines):
        ev_ret = sig_map.get((sig["owner"], sig["name"]))
        if ev_ret is None and sig["owner"]:
            ev_ret = sig_map.get(("", sig["name"]))
        if ev_ret is None or not ev_ret.strip():
            continue
        if sig["return_annotation"] and not _types_equivalent(sig["return_annotation"], ev_ret):
            symbol = f"{sig['owner']}.{sig['name']}" if sig["owner"] else sig["name"]
            result.issues.append(
                ValidationIssue(
                    "error", "return_type",
                    f"'{symbol}' return type: md says '{sig['return_annotation']}', evidence says '{ev_ret}'",
                    line=sig["line"],
                )
            )


def _check_constant_values(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    in_code_block = False
    for mod in ev.source_files:
        for name, value in mod.constants:
            if len(value) > 80 or "\n" in value or "{" in value or "[" in value:
                continue
            pattern = rf"(?:export\s+)?(?:const|let)\s+{re.escape(name)}\s*=\s*(.+)"
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
                md_value = m.group(1).rstrip(";").strip()
                ev_value = value.strip()
                if md_value and ev_value and _normalize_value(md_value) != _normalize_value(ev_value):
                    result.issues.append(
                        ValidationIssue(
                            "error", "constants",
                            f"'{name}': md has '{md_value}', evidence has '{ev_value}'",
                            line=i + 1,
                        )
                    )


def _check_no_invented_symbols(ev: Evidence, md: str, md_lines: list[str], result: ValidationResult) -> None:
    known_symbols: set[str] = set()
    for mod in ev.source_files:
        for fn in mod.functions:
            known_symbols.add(fn.name)
        for cls in mod.classes:
            known_symbols.add(cls.name)
            for m in cls.methods:
                known_symbols.add(m.name)

    in_code_block = False
    for i, line in enumerate(md_lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            continue
        for m in re.finditer(r"(?:export\s+)?(?:function|class)\s+(\w+)\s*[\(<{]", line):
            name = m.group(1)
            if name not in known_symbols and not name.startswith("test"):
                result.issues.append(
                    ValidationIssue(
                        "warning", "invented_symbol",
                        f"md references '{name}' which is not in the evidence",
                        line=i + 1,
                    )
                )


# ---------------------------------------------------------------------------
# Signature parsing from markdown
# ---------------------------------------------------------------------------

_TS_SIG_RE = re.compile(
    r"(?:export\s+)?(?:static\s+)?(?:async\s+)?(?:function\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*(.+?))?$"
)


def _iter_documented_signatures(md_lines: list[str]) -> list[dict]:
    signatures = []
    current_class = ""
    in_code_block = False

    for i, line in enumerate(md_lines):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        class_heading = re.match(r"^###\s+\d+\.\s+`(\w+)`\s+[Cc]lass$", stripped)
        if class_heading:
            current_class = class_heading.group(1)
            continue

        function_heading = re.match(r"^###\s+\d+\.\s+`(\w+)`\s+[Ff]unction$", stripped)
        if function_heading:
            current_class = ""
            continue

        if not in_code_block:
            continue

        m = _TS_SIG_RE.match(stripped)
        if m:
            signatures.append({
                "line": i + 1,
                "owner": current_class,
                "name": m.group(1),
                "params": m.group(2).strip(),
                "return_annotation": (m.group(3) or "").strip(),
            })

    return signatures


def _fallback_params(fn) -> str:
    parts: list[str] = []
    for p in fn.params:
        piece = p.name
        if p.annotation:
            piece += f": {p.annotation}"
        if p.default:
            piece += f" = {p.default}"
        parts.append(piece)
    return ", ".join(parts)


def _normalize_sig(value: str) -> str:
    return value.strip().replace(" ", "").replace('"', "'")


def _types_equivalent(a: str, b: str) -> bool:
    a = a.strip().replace(" ", "")
    b = b.strip().replace(" ", "")
    return a == b


def _normalize_value(v: str) -> str:
    return v.strip().replace(" ", "").replace('"', "'").replace("\n", "").rstrip(";")
