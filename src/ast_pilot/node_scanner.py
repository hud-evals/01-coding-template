"""Scanner for TypeScript source files.

Shells out to ``scan_node.mjs`` (Node helper) and converts the JSON
output into the standard ``Evidence`` store.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .evidence import (
    ClassInfo,
    Evidence,
    FunctionInfo,
    ModuleInfo,
    Parameter,
    TestEvidence,
)
from .node_repo_support import collect_node_dependencies, detect_node_project

_SCANNER_SCRIPT = Path(__file__).with_name("scan_node.mjs")


def scan_typescript(
    source_paths: list[str | Path],
    test_paths: list[str | Path] | None = None,
    project_name: str = "",
    readme_path: str | Path | None = None,
) -> Evidence:
    """Scan TypeScript source files and optional test files into an Evidence store."""

    resolved_sources = [str(Path(p).resolve()) for p in source_paths]
    resolved_tests = [str(Path(p).resolve()) for p in (test_paths or [])]

    ctx = detect_node_project(source_paths)
    if not ctx.is_supported:
        reasons = "\n".join(f"  - {r}" for r in ctx.unsupported_reasons)
        raise SystemExit(
            f"TypeScript project at {ctx.root} is not supported:\n{reasons}\n"
            "See USAGE.md for the supported TypeScript project matrix."
        )

    raw = _run_node_scanner(resolved_sources, resolved_tests)

    ev = Evidence(project_name=project_name)
    ev.language = "typescript"
    ev.runtime = "node"
    ev.runtime_version = ctx.node_version_floor
    ev.package_manager = "npm"
    ev.test_runner = ctx.test_runner
    ev.module_system = ctx.module_type
    ev.config_files = _collect_config_files(ctx)
    ev.dependencies = collect_node_dependencies(ctx.package_json)

    for mod_data in raw.get("source_files", []):
        ev.source_files.append(_module_from_dict(mod_data))
        ev.total_loc += mod_data.get("line_count", 0)

    for test_data in raw.get("tests", []):
        ev.tests.append(
            TestEvidence(
                test_file=test_data["test_file"],
                test_name=test_data["test_name"],
                tested_symbols=test_data.get("tested_symbols", []),
                source_snippet=test_data.get("source_snippet", ""),
            )
        )

    if readme_path:
        ev.readme_sections = _extract_readme(Path(readme_path))

    return ev


def _run_node_scanner(
    source_paths: list[str],
    test_paths: list[str],
) -> dict:
    cmd = ["node", str(_SCANNER_SCRIPT)]
    for s in source_paths:
        cmd.extend(["--sources", s])
    for t in test_paths:
        cmd.extend(["--tests", t])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit(
            "Node.js is required for TypeScript scanning but was not found on PATH.\n"
            "Install Node 20+ and try again."
        )

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"TypeScript scanner failed (exit {result.returncode}):\n{msg}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"TypeScript scanner produced invalid JSON: {exc}") from exc


def _module_from_dict(m: dict) -> ModuleInfo:
    mod = ModuleInfo(
        path=m["path"],
        module_name=m["module_name"],
        docstring=m.get("docstring", ""),
        imports=m.get("imports", []),
        from_imports=[tuple(fi) for fi in m.get("from_imports", [])],
        all_exports=m.get("all_exports", []),
        constants=[(c[0], c[1]) for c in m.get("constants", [])],
        string_literals=m.get("string_literals", []),
        line_count=m.get("line_count", 0),
    )
    for f in m.get("functions", []):
        mod.functions.append(_func_from_dict(f))
    for c in m.get("classes", []):
        ci = ClassInfo(
            name=c["name"],
            qualname=c["qualname"],
            module=c["module"],
            lineno=c["lineno"],
            bases=c.get("bases", []),
            decorators=c.get("decorators", []),
            docstring=c.get("docstring", ""),
            class_variables=[(v[0], v[1]) for v in c.get("class_variables", [])],
        )
        for method in c.get("methods", []):
            ci.methods.append(_func_from_dict(method))
        mod.classes.append(ci)
    return mod


def _func_from_dict(f: dict) -> FunctionInfo:
    params = [Parameter(**p) for p in f.get("params", [])]
    return FunctionInfo(
        name=f["name"],
        qualname=f["qualname"],
        module=f["module"],
        lineno=f["lineno"],
        decorators=f.get("decorators", []),
        params=params,
        signature_params=f.get("signature_params", ""),
        return_annotation=f.get("return_annotation", ""),
        docstring=f.get("docstring", ""),
        is_async=f.get("is_async", False),
        is_method=f.get("is_method", False),
        is_property=f.get("is_property", False),
        is_staticmethod=f.get("is_staticmethod", False),
        is_classmethod=f.get("is_classmethod", False),
    )


def _collect_config_files(ctx) -> list[str]:
    files = ["package.json"]
    if ctx.has_lockfile:
        files.append("package-lock.json")
    if ctx.tsconfig_path:
        files.append(ctx.tsconfig_path.name)
    if ctx.vitest_config_path:
        files.append(ctx.vitest_config_path.name)
    return files


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _extract_readme(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: dict[str, str] = {}
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections[heading] = body[:2000]
    if not matches and text.strip():
        sections["README"] = text.strip()[:3000]
    return sections
