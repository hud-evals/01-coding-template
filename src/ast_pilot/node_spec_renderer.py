"""Spec renderer for TypeScript projects.

Produces a Claire-style start.md adapted for TypeScript/Node tasks.
Deterministic structure with optional LLM prose sections.
"""

from __future__ import annotations

from pathlib import Path

from .evidence import Evidence, FunctionInfo
from .llm_client import call_text_llm

WORKSPACE_DIR = "/home/ubuntu/workspace"


def render_start_md(
    ev: Evidence,
    output_path: str | Path | None = None,
    use_llm: bool = True,
) -> str:
    sections = [
        _section_project_description(ev, use_llm),
        _section_instructions(ev, use_llm),
        _section_required_symbols(ev),
        _section_environment(ev),
        _section_directory_structure(ev),
        _section_api_usage(ev),
        _section_implementation_notes(ev, use_llm),
    ]

    md = "\n\n".join(s for s in sections if s)
    if output_path:
        Path(output_path).write_text(md, encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# Section 1: Project Description
# ---------------------------------------------------------------------------

def _section_project_description(ev: Evidence, use_llm: bool) -> str:
    facts = _build_project_facts(ev)
    if use_llm:
        prompt = f"""Write a 2-3 paragraph project overview for a TypeScript library based on these facts.
Be specific and technical. Do NOT invent features not listed here.

Facts:
{facts}

Write in the style of a detailed technical specification. Start with "## Overview"."""
        prose = _call_llm(prompt)
        if prose:
            return f"# {ev.project_name}\n\n{prose}"
    return f"# {ev.project_name}\n\n## Overview\n\n{facts}"


def _build_project_facts(ev: Evidence) -> str:
    lines = [f"- Project name: {ev.project_name}"]
    lines.append(f"- Language: TypeScript")
    lines.append(f"- Total lines of code: {ev.total_loc}")
    lines.append(f"- Number of source modules: {len(ev.source_files)}")

    all_classes = []
    all_functions = []
    for mod in ev.source_files:
        all_classes.extend(mod.classes)
        all_functions.extend(mod.functions)

    lines.append(f"- Classes: {len(all_classes)}")
    lines.append(f"- Module-level functions: {len(all_functions)}")
    lines.append(f"- Test runner: {ev.test_runner}")
    lines.append(f"- Module system: {ev.module_system}")

    if ev.readme_sections:
        first_section = next(iter(ev.readme_sections.values()), "")
        if first_section:
            lines.append(f"- README excerpt: {first_section[:500]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 2: Natural Language Instructions
# ---------------------------------------------------------------------------

def _section_instructions(ev: Evidence, use_llm: bool) -> str:
    facts = _build_project_facts(ev)
    exact_api = _build_exact_api_listing(ev)
    required_symbols = _build_required_symbols_text(ev)
    target_files = ", ".join(f"`{name}`" for name in _workspace_target_files(ev))

    if use_llm:
        prompt = f"""Write detailed natural language instructions for rebuilding this TypeScript library from scratch.

CRITICAL RULES:
- The solution files live directly in `{WORKSPACE_DIR}`. Do NOT tell the agent to rely on npm-linked packages or hidden paths.
- Hidden tests import the implementation from these module file(s): {target_files}.
- Every symbol in the REQUIRED TESTED SYMBOLS section below must exist, including private helpers prefixed with underscore.
- You MUST use the EXACT function/method signatures provided below. Do NOT change parameter names, types, defaults, or return types.
- Do NOT invent parameters or simplify signatures. Copy them exactly.
- Do NOT invent behaviors not described in the docstrings or test evidence below.
- This is a TypeScript project. All code should be written in TypeScript.
- Write requirements as a numbered list under a "### Behavioral Requirements" heading.

Project facts:
{facts}

Required tested symbols:
{required_symbols}

EXACT API (use these signatures verbatim):
{exact_api}

Test evidence ({len(ev.tests)} tests):
{_build_test_facts(ev)}

Start with "## Natural Language Instructions" and include a short bullet list of implementation constraints before the numbered requirements."""
        prose = _call_llm(prompt)
        if prose:
            return prose

    lines = ["## Natural Language Instructions", ""]
    lines.append("Before you start:")
    lines.append(f"- Create and edit the solution directly in `{WORKSPACE_DIR}`.")
    lines.append(f"- The hidden tests import these module file(s): {target_files}.")
    lines.append("- Implement every symbol listed in `Required Tested Symbols`.")
    lines.append("- All code must be valid TypeScript.")
    lines.append("")
    lines.append("### Behavioral Requirements")
    lines.append("")

    tested = ev.tested_symbols()
    req_num = 1
    for mod in ev.source_files:
        for cls in mod.classes:
            lines.append(f"{req_num}. Implement the `{cls.name}` class with all its methods:")
            for m in cls.methods:
                lines.append(f"   - `{m.name}({_format_params_compact(m)})`")
            req_num += 1

        for fn in mod.functions:
            lines.append(f"{req_num}. Implement the function `{fn.name}({_format_params_compact(fn)})`")
            if fn.docstring:
                lines.append(f"   {fn.docstring.split(chr(10))[0]}")
            req_num += 1

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 3: Required Tested Symbols
# ---------------------------------------------------------------------------

def _section_required_symbols(ev: Evidence) -> str:
    items = _build_required_symbol_items(ev)
    if not items:
        return ""
    lines = ["## Required Tested Symbols", ""]
    lines.append("The hidden tests import every symbol listed here. Implement all of them.")
    lines.append("")
    for item in items:
        lines.append(f"- `{item}`")
    return "\n".join(lines)


def _build_required_symbol_items(ev: Evidence) -> list[str]:
    tested = ev.tested_symbols()
    if not tested:
        all_exported: list[str] = []
        for mod in ev.source_files:
            all_exported.extend(mod.all_exports)
            for fn in mod.functions:
                all_exported.append(fn.name)
            for cls in mod.classes:
                all_exported.append(cls.name)
        return all_exported if all_exported else []

    items: list[str] = []
    seen: set[str] = set()

    def _append(item: str) -> None:
        if item not in seen:
            seen.add(item)
            items.append(item)

    for mod in ev.source_files:
        for cls in mod.classes:
            if cls.name in tested:
                _append(f"class {cls.name}")
            for method in cls.methods:
                if method.name in tested:
                    _append(_format_required_symbol(method, owner=cls.name))
        for fn in mod.functions:
            if fn.name in tested:
                _append(_format_required_symbol(fn))
        for name, _ in mod.constants:
            if name in tested:
                _append(name)
    return items


def _build_required_symbols_text(ev: Evidence) -> str:
    items = _build_required_symbol_items(ev)
    if not items:
        return "- No explicit tested symbols were extracted."
    return "\n".join(f"- {item}" for item in items)


def _format_required_symbol(fn: FunctionInfo, owner: str | None = None) -> str:
    prefix = "async " if fn.is_async else ""
    name = f"{owner}.{fn.name}" if owner else fn.name
    ret = f": {fn.return_annotation}" if fn.return_annotation else ""
    return f"{prefix}function {name}({_format_params_str(fn)}){ret}"


# ---------------------------------------------------------------------------
# Section 4: Environment Configuration
# ---------------------------------------------------------------------------

def _section_environment(ev: Evidence) -> str:
    lines = ["## Environment Configuration", ""]
    lines.append(f"### Runtime\n\nNode.js (TypeScript)")
    if ev.runtime_version:
        lines.append(f"\nNode version requirement: `{ev.runtime_version}`")
    lines.append("")

    lines.append("### Workspace")
    lines.append("")
    lines.append(f"- Put the implementation directly under `{WORKSPACE_DIR}`.")
    lines.append("- Your shell may start in a different current directory, so use absolute paths.")
    target_files = _workspace_target_files(ev)
    if target_files:
        rendered = ", ".join(f"`{name}`" for name in target_files)
        lines.append(f"- Hidden tests import the solution from: {rendered}.")
    lines.append("")

    if ev.dependencies:
        lines.append("### Dependencies\n")
        lines.append("The following npm packages are used:")
        lines.append("```")
        for dep in ev.dependencies:
            lines.append(dep)
        lines.append("```")
        lines.append("")
    else:
        lines.append("### Dependencies\n")
        lines.append("No runtime dependencies were detected.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 5: Directory Structure
# ---------------------------------------------------------------------------

def _section_directory_structure(ev: Evidence) -> str:
    lines = ["## Project Directory Structure", "", "```"]
    lines.append("workspace/")
    lines.append("├── package.json")
    lines.append("├── tsconfig.json")
    for name in _workspace_target_files(ev):
        lines.append(f"├── {name}")
    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6: API Usage Guide
# ---------------------------------------------------------------------------

def _section_api_usage(ev: Evidence) -> str:
    parts = ["## API Usage Guide", ""]

    parts.append("### 1. Module Import")
    parts.append("")
    parts.append("```typescript")
    pkg = _primary_module_name(ev)
    imports: list[str] = []
    for mod in ev.source_files:
        for cls in mod.classes:
            imports.append(cls.name)
        for fn in mod.functions:
            imports.append(fn.name)
        for name, _ in mod.constants:
            imports.append(name)
    if imports:
        parts.append(f"import {{ {', '.join(imports)} }} from './{pkg}';")
    else:
        parts.append(f"import * as {pkg} from './{pkg}';")
    parts.append("```")
    parts.append("")

    section_num = 2
    for mod in ev.source_files:
        for cls in mod.classes:
            parts.append(f"### {section_num}. `{cls.name}` Class")
            if cls.docstring:
                parts.append(f"\n{cls.docstring.strip()}")
            parts.append("")

            if cls.bases:
                parts.append(f"**Extends:** `{'`, `'.join(cls.bases)}`")
                parts.append("")

            parts.append("```typescript")
            extends = f" extends {', '.join(cls.bases)}" if cls.bases else ""
            parts.append(f"class {cls.name}{extends} {{")
            if cls.docstring:
                parts.append(f"  // {cls.docstring.split(chr(10))[0]}")
            parts.append("}")
            parts.append("```")
            parts.append("")

            for method in cls.methods:
                parts.extend(_render_function_block(method, is_method=True))
            section_num += 1

    for mod in ev.source_files:
        for fn in mod.functions:
            parts.append(f"### {section_num}. `{fn.name}` Function")
            parts.extend(_render_function_block(fn, is_method=False))
            section_num += 1

    all_constants = []
    for mod in ev.source_files:
        all_constants.extend(mod.constants)

    if all_constants:
        parts.append(f"### {section_num}. Constants and Configuration")
        parts.append("")
        parts.append("```typescript")
        for name, value in all_constants:
            if len(value) < 200:
                parts.append(f"export const {name} = {value};")
            else:
                parts.append(f"export const {name} = ...; // {len(value)} chars")
        parts.append("```")

    return "\n".join(parts)


def _render_function_block(fn: FunctionInfo, is_method: bool) -> list[str]:
    parts: list[str] = []
    if fn.docstring:
        parts.append(f"\n{fn.docstring.strip()}")
    parts.append("")

    prefix = "async " if fn.is_async else ""
    static = "static " if fn.is_staticmethod else ""
    parts.append("```typescript")
    params_str = _format_params_str(fn)
    ret = f": {fn.return_annotation}" if fn.return_annotation else ""
    if is_method:
        parts.append(f"{static}{prefix}{fn.name}({params_str}){ret}")
    else:
        parts.append(f"export {prefix}function {fn.name}({params_str}){ret}")
    parts.append("```")
    parts.append("")

    visible_params = [p for p in fn.params if p.name != "this"]
    if visible_params:
        parts.append("**Parameters:**")
        for p in visible_params:
            ann = f": {p.annotation}" if p.annotation else ""
            default = f" = {p.default}" if p.default else ""
            parts.append(f"- `{p.name}{ann}{default}`")
        parts.append("")

    if fn.return_annotation:
        parts.append(f"**Returns:** `{fn.return_annotation}`")
        parts.append("")

    return parts


# ---------------------------------------------------------------------------
# Section 7: Implementation Notes
# ---------------------------------------------------------------------------

def _section_implementation_notes(ev: Evidence, use_llm: bool) -> str:
    test_facts = _build_test_facts(ev)
    exact_api = _build_exact_api_listing(ev)

    const_facts = []
    for mod in ev.source_files:
        for name, value in mod.constants:
            if len(value) < 200:
                const_facts.append(f"export const {name} = {value}")

    if use_llm and test_facts:
        prompt = f"""Based on these test cases and the exact API for a TypeScript library, write implementation notes.

CRITICAL RULES:
- ONLY describe behaviors that are evident from the test code or the API signatures below.
- Do NOT invent behaviors, flags, or fields that are not in the source.
- Use EXACT constant names and values from the constants list below.
- Use EXACT method signatures from the API listing below.
- This is TypeScript, not Python. Use TypeScript conventions.

Constants (use exact values):
{chr(10).join(const_facts)}

Exact API signatures:
{exact_api}

Test evidence:
{test_facts}

Write grouped implementation notes. Start with "## Implementation Notes". Use "### Note N: <topic>"."""
        prose = _call_llm(prompt)
        if prose:
            return prose

    if not ev.tests:
        return ""

    lines = ["## Implementation Notes", ""]
    lines.append("The following behaviors are validated by the test suite:")
    lines.append("")

    for i, t in enumerate(ev.tests[:30], 1):
        lines.append(f"### Note {i}: {t.test_name}")
        if t.tested_symbols:
            lines.append(f"Tests symbols: `{'`, `'.join(t.tested_symbols)}`")
        if t.source_snippet:
            snippet = "\n".join(t.source_snippet.splitlines()[:20])
            lines.append(f"\n```typescript\n{snippet}\n```")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_params_str(fn: FunctionInfo) -> str:
    if fn.signature_params:
        return fn.signature_params
    parts: list[str] = []
    for p in fn.params:
        s = p.name
        if p.annotation:
            s += f": {p.annotation}"
        if p.default:
            s += f" = {p.default}"
        parts.append(s)
    return ", ".join(parts)


def _format_params_compact(fn: FunctionInfo) -> str:
    names = [p.name for p in fn.params if p.name not in ("this",)]
    return ", ".join(names)


def _build_exact_api_listing(ev: Evidence) -> str:
    lines: list[str] = []
    for mod in ev.source_files:
        for cls in mod.classes:
            bases = f" extends {', '.join(cls.bases)}" if cls.bases else ""
            lines.append(f"export class {cls.name}{bases} {{")
            for m in cls.methods:
                prefix = "async " if m.is_async else ""
                static = "static " if m.is_staticmethod else ""
                params = _format_params_str(m)
                ret = f": {m.return_annotation}" if m.return_annotation else ""
                lines.append(f"  {static}{prefix}{m.name}({params}){ret}")
            lines.append("}")
            lines.append("")

        for fn in mod.functions:
            prefix = "async " if fn.is_async else ""
            params = _format_params_str(fn)
            ret = f": {fn.return_annotation}" if fn.return_annotation else ""
            lines.append(f"export {prefix}function {fn.name}({params}){ret}")

        for name, value in mod.constants:
            if len(value) < 120:
                lines.append(f"export const {name} = {value}")

    return "\n".join(lines)


def _build_test_facts(ev: Evidence) -> str:
    if not ev.tests:
        return ""
    lines: list[str] = []
    for t in ev.tests[:40]:
        syms = ", ".join(t.tested_symbols[:10])
        lines.append(f"- {t.test_name} -> tests: {syms}")
        if t.source_snippet:
            import textwrap
            lines.append(textwrap.indent(t.source_snippet[:500], "  "))
    return "\n".join(lines)


def _workspace_target_files(ev: Evidence) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for mod in ev.source_files:
        name = Path(mod.path).name
        if not name or name in seen:
            continue
        seen.add(name)
        files.append(name)
    return files


def _primary_module_name(ev: Evidence) -> str:
    target_files = _workspace_target_files(ev)
    if target_files:
        return Path(target_files[0]).stem
    return ev.project_name.lower().replace("-", "_").replace(" ", "_")


def _call_llm(prompt: str, max_tokens: int = 16384) -> str | None:
    return call_text_llm(prompt, max_tokens=max_tokens)
