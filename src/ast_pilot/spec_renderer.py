"""Spec renderer: produce a Claire-style prompt.md from an Evidence store.

Deterministic structure + Haiku 4.5 for prose-heavy sections.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from .evidence import Evidence, FunctionInfo
from .llm_client import call_text_llm
from .repo_support import (
    STDLIB_MODULES,
    RepoContext,
    find_repo_context,
    module_name_from_path,
    resolve_from_module,
    resolve_module_candidates,
)

WORKSPACE_DIR = "/home/ubuntu/workspace"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_start_md(
    ev: Evidence,
    output_path: str | Path | None = None,
    use_llm: bool = True,
) -> str:
    """Render a complete Claire-style prompt.md from an Evidence store.

    When *use_llm* is True, calls Haiku 4.5 for prose sections.
    When False, uses deterministic fallback prose (faster, no API key needed).
    """
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
    summary_facts = _build_project_facts(ev)

    if use_llm:
        prompt = f"""Write a 2-3 paragraph project overview for a Python library based on these facts.
Be specific and technical. Do NOT invent features not listed here.

Facts:
{summary_facts}

Write in the style of a detailed technical specification. Start with "## Overview"."""
        prose = _call_llm(prompt)
        if prose:
            return f"# {ev.project_name}\n\n{prose}"

    return f"# {ev.project_name}\n\n## Overview\n\n{summary_facts}"


def _build_project_facts(ev: Evidence) -> str:
    lines = [f"- Project name: {ev.project_name}"]
    lines.append(f"- Total lines of code: {ev.total_loc}")
    lines.append(f"- Number of source modules: {len(ev.source_files)}")

    all_classes = []
    all_functions = []
    for mod in ev.source_files:
        all_classes.extend(mod.classes)
        all_functions.extend(mod.functions)

    lines.append(f"- Classes: {len(all_classes)}")
    lines.append(f"- Module-level functions: {len(all_functions)}")

    if ev.readme_sections:
        first_section = next(iter(ev.readme_sections.values()), "")
        if first_section:
            lines.append(f"- README excerpt: {first_section[:500]}")

    for mod in ev.source_files:
        if mod.docstring:
            lines.append(f"- Module '{mod.module_name}' docstring: {mod.docstring[:300]}")

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
        prompt = f"""Write detailed natural language instructions for rebuilding this Python library from scratch.

CRITICAL RULES:
- The solution files live directly in `{WORKSPACE_DIR}`. Do NOT tell the agent to rely on editable installs or hidden package paths.
- Hidden tests import the implementation as top-level module file(s): {target_files}.
- Every symbol in the REQUIRED TESTED SYMBOLS section below must exist, including underscored/private helpers.
- If the original source depended on repo-internal modules, tell the agent to recreate the needed behavior locally instead of trying to install private packages.
- You MUST use the EXACT function/method signatures provided below. Do NOT change parameter names, types, defaults, or return types.
- Do NOT invent parameters or simplify signatures. Copy them exactly.
- Do NOT invent behaviors not described in the docstrings or test evidence below.
- Write requirements as a numbered list under a "### Behavioral Requirements" heading. Each requirement should describe WHAT a function/class does and HOW it should behave.

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

    # Deterministic fallback
    lines = ["## Natural Language Instructions", ""]
    lines.append("Before you start:")
    lines.append(f"- Create and edit the solution directly in `{WORKSPACE_DIR}`.")
    lines.append(f"- The hidden tests import these top-level module file(s): {target_files}.")
    lines.append("- Implement every symbol listed in `Required Tested Symbols`, including underscored/private helpers.")
    lines.append("- Recreate any repo-internal helper behavior locally instead of trying to install private packages.")
    lines.append("")
    lines.append("### Behavioral Requirements")
    lines.append("")

    # Collect ALL symbols that tests reference — these MUST be in the prompt
    tested_private = ev.tested_symbols() - {s.split(".")[-1] for s in ev.all_public_symbols()}

    req_num = 1
    for mod in ev.source_files:
        for cls in mod.classes:
            lines.append(f"{req_num}. Implement the `{cls.name}` class with all its methods:")
            for m in cls.methods:
                if not m.name.startswith("_") or m.name in (
                    "__init__", "__call__", "__repr__", "__str__",
                    "__enter__", "__exit__", "__iter__", "__next__",
                    "__getattr__", "__setattr__", "__post_init__",
                ) or m.name in tested_private:
                    lines.append(f"   - `{m.name}({_format_params_compact(m)})`")
            req_num += 1

        for fn in mod.functions:
            if not fn.name.startswith("_") or fn.name in tested_private:
                lines.append(f"{req_num}. Implement the function `{fn.name}({_format_params_compact(fn)})`")
                if fn.docstring:
                    lines.append(f"   {fn.docstring.split(chr(10))[0]}")
                req_num += 1

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 3: Environment Configuration
# ---------------------------------------------------------------------------

def _section_environment(ev: Evidence) -> str:
    lines = ["## Environment Configuration", ""]
    lines.append(f"### Python Version\n\nPython {ev.python_version}")
    lines.append("")

    external_deps, internal_deps = _build_dependency_info(ev)

    lines.append("### Workspace")
    lines.append("")
    lines.append(f"- Put the implementation directly under `{WORKSPACE_DIR}`.")
    lines.append("- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.")
    target_files = _workspace_target_files(ev)
    if target_files:
        rendered_targets = ", ".join(f"`{name}`" for name in target_files)
        lines.append(f"- Hidden tests import the solution as top-level module file(s): {rendered_targets}.")
    lines.append("")

    if external_deps:
        lines.append("### External Dependencies\n")
        lines.append("Only use pip-installable packages for the external dependencies below.")
        lines.append("```")
        for dep in external_deps:
            lines.append(dep)
        lines.append("```")
        lines.append("")
    else:
        lines.append("### External Dependencies\n")
        lines.append("No third-party runtime dependencies were detected from the source file.")
        lines.append("")

    if internal_deps:
        lines.append("### Internal Helpers (implement locally)\n")
        lines.append("These names came from repo-internal modules. Do NOT try to `pip install` them.")
        lines.append("")
        for dep_name, description in internal_deps:
            lines.append(f"- `{dep_name}`: {description}")
        lines.append("")

    return "\n".join(lines)


def _section_required_symbols(ev: Evidence) -> str:
    items = _build_required_symbol_items(ev)
    if not items:
        return ""

    lines = ["## Required Tested Symbols", ""]
    lines.append("The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.")
    lines.append("")
    for item in items:
        lines.append(f"- `{item}`")
    return "\n".join(lines)


def _build_required_symbols_text(ev: Evidence) -> str:
    items = _build_required_symbol_items(ev)
    if not items:
        return "- No explicit tested symbols were extracted."
    return "\n".join(f"- {item}" for item in items)


def _build_required_symbol_items(ev: Evidence) -> list[str]:
    tested = ev.tested_symbols()
    if not tested:
        return []

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


def _format_required_symbol(fn: FunctionInfo, owner: str | None = None) -> str:
    prefix = "async def" if fn.is_async else "def"
    name = f"{owner}.{fn.name}" if owner else fn.name
    ret = f" -> {fn.return_annotation}" if fn.return_annotation else ""
    return f"{prefix} {name}({_format_params_str(fn)}){ret}"


def _build_dependency_info(ev: Evidence) -> tuple[list[str], list[tuple[str, str]]]:
    source_paths = [mod.path for mod in ev.source_files if Path(mod.path).exists()]
    repo = find_repo_context(source_paths)
    internal_refs = _collect_internal_dependency_references(ev, repo)
    internal_roots = {module_name.split(".")[0] for module_name in internal_refs}

    external_deps = sorted(
        dep
        for dep in ev.dependencies
        if dep not in STDLIB_MODULES and dep not in internal_roots
    )
    internal_deps = [
        (module_name, _describe_internal_dependency(module_name, imported_names))
        for module_name, imported_names in sorted(internal_refs.items())
    ]
    return external_deps, internal_deps


def _collect_internal_dependency_references(
    ev: Evidence,
    repo: RepoContext | None,
) -> dict[str, set[str]]:
    if repo is None:
        return {}

    refs: dict[str, set[str]] = {}
    for mod in ev.source_files:
        source_path = Path(mod.path)
        if not source_path.exists():
            continue

        current_module = module_name_from_path(source_path, repo.root)
        if current_module is None:
            continue

        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    candidates = resolve_module_candidates(alias.name, repo.module_index)
                    if not candidates:
                        continue
                    chosen = _pick_module_candidate(alias.name, candidates)
                    if chosen == current_module:
                        continue
                    refs.setdefault(chosen, set())
            elif isinstance(node, ast.ImportFrom):
                module_name = resolve_from_module(current_module, node.module, node.level)
                if not module_name:
                    continue
                candidates = resolve_module_candidates(module_name, repo.module_index)
                if not candidates:
                    continue
                chosen = _pick_module_candidate(module_name, candidates)
                if chosen == current_module:
                    continue
                imported_names = refs.setdefault(chosen, set())
                for alias in node.names:
                    if alias.name != "*":
                        imported_names.add(alias.name)

    return refs


def _pick_module_candidate(requested: str, candidates: set[str]) -> str:
    if requested in candidates:
        return requested
    return max(candidates, key=len)


def _describe_internal_dependency(module_name: str, imported_names: set[str]) -> str:
    shown_names = sorted(imported_names)
    if module_name.endswith("constants") or any(name.isupper() for name in shown_names):
        prefix = "repo-private constants or lightweight helper values"
    elif "auth" in module_name.split("."):
        prefix = "repo-private authentication or credential helpers"
    elif any("path" in name.lower() or "home" in name.lower() for name in shown_names):
        prefix = "repo-private filesystem/path helpers"
    else:
        prefix = "repo-private helper module"

    if shown_names:
        rendered = ", ".join(f"`{name}`" for name in shown_names[:5])
        return f"{prefix}; the original code imported {rendered} from `{module_name}`. Recreate the needed behavior locally."
    return f"{prefix}; the original code referenced `{module_name}` directly. Recreate the needed behavior locally instead of importing it."


def _workspace_target_files(ev: Evidence) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for mod in ev.source_files:
        name = Path(mod.path).name
        if not name or name in seen or name == "__init__.py":
            continue
        seen.add(name)
        files.append(name)
    return files


def _primary_module_name(ev: Evidence) -> str:
    target_files = _workspace_target_files(ev)
    if target_files:
        return Path(target_files[0]).stem
    return ev.project_name.lower().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# Section 4: Directory Structure
# ---------------------------------------------------------------------------

def _section_directory_structure(ev: Evidence) -> str:
    lines = ["## Project Directory Structure", "", "```"]
    lines.append("workspace/")

    lines.append("├── pyproject.toml")
    for name in _workspace_target_files(ev):
        lines.append(f"├── {name}")

    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 5: API Usage Guide (the big one)
# ---------------------------------------------------------------------------

def _section_api_usage(ev: Evidence) -> str:
    parts = ["## API Usage Guide", ""]

    # Imports section
    parts.append("### 1. Module Import")
    parts.append("")
    parts.append("```python")
    pkg = _primary_module_name(ev)
    imports: list[str] = []
    for mod in ev.source_files:
        for cls in mod.classes:
            if not cls.name.startswith("_"):
                imports.append(cls.name)
        for fn in mod.functions:
            if not fn.name.startswith("_"):
                imports.append(fn.name)
        for name, _ in mod.constants:
            if not name.startswith("_"):
                imports.append(name)
    if imports:
        parts.append(f"from {pkg} import (")
        for imp in imports:
            parts.append(f"    {imp},")
        parts.append(")")
    else:
        parts.append(f"import {pkg}")
    parts.append("```")
    parts.append("")

    # Classes
    section_num = 2
    for mod in ev.source_files:
        for cls in mod.classes:
            parts.append(f"### {section_num}. `{cls.name}` Class")
            if cls.docstring:
                parts.append(f"\n{cls.docstring.strip()}")
            parts.append("")

            if cls.bases:
                parts.append(f"**Bases:** `{'`, `'.join(cls.bases)}`")
                parts.append("")

            parts.append("```python")
            parts.append(f"class {cls.name}({', '.join(cls.bases) if cls.bases else ''}):")
            if cls.docstring:
                parts.append(f'    """{cls.docstring.split(chr(10))[0]}"""')
            parts.append("```")
            parts.append("")

            # Class variables
            if cls.class_variables:
                parts.append("**Class Variables:**")
                for vname, vtype in cls.class_variables:
                    if vtype:
                        parts.append(f"- `{vname}: {vtype}`")
                    else:
                        parts.append(f"- `{vname}`")
                parts.append("")

            # Methods
            for method in cls.methods:
                parts.extend(_render_function_block(method, is_method=True))

            section_num += 1

    # Module-level functions
    for mod in ev.source_files:
        for fn in mod.functions:
            if fn.name.startswith("_"):
                continue
            parts.append(f"### {section_num}. `{fn.name}` Function")
            parts.extend(_render_function_block(fn, is_method=False))
            section_num += 1

    # Constants
    all_constants = []
    for mod in ev.source_files:
        all_constants.extend(mod.constants)

    if all_constants:
        parts.append(f"### {section_num}. Constants and Configuration")
        parts.append("")
        parts.append("```python")
        for name, value in all_constants:
            if len(value) < 200:
                parts.append(f"{name} = {value}")
            else:
                parts.append(f"{name} = ...  # {len(value)} chars")
        parts.append("```")

    return "\n".join(parts)


def _render_function_block(fn: FunctionInfo, is_method: bool) -> list[str]:
    """Render a function/method as a detailed API doc block."""
    parts: list[str] = []
    if fn.docstring:
        parts.append(f"\n{fn.docstring.strip()}")
    parts.append("")

    # Signature
    prefix = "async " if fn.is_async else ""
    parts.append("```python")
    params_str = _format_params_str(fn)
    ret = f" -> {fn.return_annotation}" if fn.return_annotation else ""
    parts.append(f"{prefix}def {fn.name}({params_str}){ret}:")
    parts.append("```")
    parts.append("")

    # Parameters table
    visible_params = [p for p in fn.params if p.name != "self" and p.name != "cls"]
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

    # Decorators
    if fn.decorators:
        parts.append(f"**Decorators:** `{'`, `'.join(fn.decorators)}`")
        parts.append("")

    return parts


def _format_params_str(fn: FunctionInfo) -> str:
    """Format just the parameter list (no parens, no return type)."""
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
    """Compact param list for inline references."""
    names = [p.name for p in fn.params if p.name not in ("self", "cls")]
    return ", ".join(names)


def _build_exact_api_listing(ev: Evidence) -> str:
    """Full exact API listing with signatures, types, and docstrings for LLM grounding."""
    lines: list[str] = []
    for mod in ev.source_files:
        for cls in mod.classes:
            decorators = " ".join(f"@{d}" for d in cls.decorators)
            bases = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"{decorators}\nclass {cls.name}{bases}:")
            if cls.docstring:
                lines.append(f'    """{cls.docstring.split(chr(10))[0]}"""')
            if cls.class_variables:
                for vname, vtype in cls.class_variables:
                    ann = f": {vtype}" if vtype else ""
                    lines.append(f"    {vname}{ann}")
            for m in cls.methods:
                prefix = "async " if m.is_async else ""
                params = _format_params_str(m)
                ret = f" -> {m.return_annotation}" if m.return_annotation else ""
                decs = " ".join(f"@{d}" for d in m.decorators)
                if decs:
                    lines.append(f"    {decs}")
                lines.append(f"    {prefix}def {m.name}({params}){ret}:")
                if m.docstring:
                    lines.append(f'        """{m.docstring.split(chr(10))[0]}"""')
            lines.append("")

        for fn in mod.functions:
            prefix = "async " if fn.is_async else ""
            params = _format_params_str(fn)
            ret = f" -> {fn.return_annotation}" if fn.return_annotation else ""
            lines.append(f"{prefix}def {fn.name}({params}){ret}:")
            if fn.docstring:
                lines.append(f'    """{fn.docstring.split(chr(10))[0]}"""')

        for name, value in mod.constants:
            if not name.startswith("_") and len(value) < 120:
                lines.append(f"{name} = {value}")

        if mod.string_literals:
            lines.append("")
            lines.append(f"# String literals used as dict keys / data fields in {mod.module_name}:")
            lines.append(f"# {', '.join(repr(s) for s in mod.string_literals[:50])}")

    return "\n".join(lines)


def _build_api_summary_compact(ev: Evidence) -> str:
    """Compact text summary of the API surface for LLM prompts."""
    lines: list[str] = []
    for mod in ev.source_files:
        for cls in mod.classes:
            methods = [m.name for m in cls.methods if not m.name.startswith("_") or m.name.startswith("__")]
            lines.append(f"class {cls.name}: methods={methods}")
        for fn in mod.functions:
            if not fn.name.startswith("_"):
                lines.append(f"function {fn.name}({_format_params_compact(fn)})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6: Implementation Notes
# ---------------------------------------------------------------------------

def _section_implementation_notes(ev: Evidence, use_llm: bool) -> str:
    test_facts = _build_test_facts(ev)
    exact_api = _build_exact_api_listing(ev)

    # Collect constant values for grounding
    const_facts = []
    for mod in ev.source_files:
        for name, value in mod.constants:
            if len(value) < 200:
                const_facts.append(f"{name} = {value}")

    if use_llm and test_facts:
        prompt = f"""Based on these test cases and the exact API for a Python library, write implementation notes.

CRITICAL RULES:
- ONLY describe behaviors that are evident from the test code or the API signatures below.
- Do NOT invent behaviors, flags, or fields that are not in the source.
- Use EXACT constant names and values from the constants list below.
- Use EXACT method signatures from the API listing below.

Constants (use exact values):
{chr(10).join(const_facts)}

Exact API signatures:
{exact_api}

Test evidence:
{test_facts}

Write grouped implementation notes. Start with "## Implementation Notes". Use "### Node N: <topic>"."""
        prose = _call_llm(prompt)
        if prose:
            return prose

    # Deterministic fallback
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
            # Show first 20 lines of the test
            snippet = "\n".join(t.source_snippet.splitlines()[:20])
            lines.append(f"\n```python\n{snippet}\n```")
        lines.append("")

    return "\n".join(lines)


def _build_test_facts(ev: Evidence) -> str:
    """Build a compact summary of test evidence for LLM prompts."""
    if not ev.tests:
        return ""
    lines: list[str] = []
    for t in ev.tests[:40]:
        syms = ", ".join(t.tested_symbols[:10])
        lines.append(f"- {t.test_name} -> tests: {syms}")
        if t.source_snippet:
            lines.append(textwrap.indent(t.source_snippet[:500], "  "))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM layer — delegates to the shared llm_client module
# ---------------------------------------------------------------------------


def _call_llm(prompt: str, max_tokens: int = 16384) -> str | None:
    """Call the configured LLM for a single section draft."""
    return call_text_llm(prompt, max_tokens=max_tokens)
