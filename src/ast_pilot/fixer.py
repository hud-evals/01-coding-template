"""Fixer: use an LLM to fix or dismiss validator errors in a generated start.md."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .evidence import Evidence
from .validator import ValidationIssue, ValidationResult


@dataclass
class FixAction:
    issue: ValidationIssue
    action: str  # "fixed" | "dismissed" | "failed"
    old_text: str = ""
    new_text: str = ""
    reason: str = ""


def fix_issues(
    ev: Evidence,
    md_path: str | Path,
    validation: ValidationResult,
) -> tuple[str, list[FixAction]]:
    """Fix validator errors in a start.md using targeted LLM calls.

    Returns (corrected_md, list of actions taken).
    """

    md = Path(md_path).read_text(encoding="utf-8")
    had_trailing_newline = md.endswith("\n")
    md_lines = md.splitlines()
    actions: list[FixAction] = []

    for issue in validation.issues:
        if issue.severity != "error":
            continue

        context = _get_context(md_lines, issue.line, window=5)
        evidence_snippet = _get_relevant_evidence(ev, issue)

        prompt = f"""You are a factual accuracy checker for a Python library specification document.

A validator found this issue:
  Section: {issue.section}
  Line {issue.line}: {issue.message}

Here is the text around line {issue.line}:
---
{context}
---

Here is the ground truth from the source code analysis:
---
{evidence_snippet}
---

Your job:
1. If this is a REAL ERROR (the md says something factually wrong vs the evidence), output EXACTLY:
   FIX: <the corrected version of ONLY the problematic line, preserving its format>
   The fix must be a single line that can directly replace the marked line (>>>).
   If the line is code (starts with "def "), output the corrected code line.
   If the line is prose, output the corrected prose line.
   Do NOT output explanations, only the replacement line.
2. If this is a FALSE POSITIVE (the md is actually correct, or the validator is comparing the wrong things), output EXACTLY:
   DISMISS: <one sentence explaining why>

Output ONLY one of those two lines. Nothing else."""

        response = _call_llm(prompt, max_tokens=512)
        if not response:
            actions.append(FixAction(issue=issue, action="failed", reason="LLM call failed"))
            continue

        response = response.strip()

        if response.startswith("FIX:"):
            fix_text = response[4:].strip()
            old_line = md_lines[issue.line - 1] if 0 < issue.line <= len(md_lines) else ""
            if old_line and fix_text:
                md_lines[issue.line - 1] = fix_text
                md = _join_lines(md_lines, had_trailing_newline)
                actions.append(
                    FixAction(
                        issue=issue,
                        action="fixed",
                        old_text=old_line,
                        new_text=fix_text,
                        reason="LLM fix applied",
                    )
                )
            else:
                actions.append(
                    FixAction(issue=issue, action="failed", reason="could not locate line to fix")
                )

        elif response.startswith("DISMISS:"):
            reason = response[8:].strip()
            actions.append(FixAction(issue=issue, action="dismissed", reason=reason))

        else:
            actions.append(
                FixAction(
                    issue=issue,
                    action="failed",
                    reason=f"unexpected LLM response: {response[:100]}",
                )
            )

    Path(md_path).write_text(md, encoding="utf-8")
    return md, actions


def _join_lines(lines: list[str], had_trailing_newline: bool) -> str:
    md = "\n".join(lines)
    if had_trailing_newline:
        md += "\n"
    return md


def _get_context(lines: list[str], line_num: int, window: int = 5) -> str:
    if line_num <= 0 or line_num > len(lines):
        return ""
    start = max(0, line_num - 1 - window)
    end = min(len(lines), line_num + window)
    result = []
    for i in range(start, end):
        marker = ">>>" if i == line_num - 1 else "   "
        result.append(f"{marker} {i + 1}: {lines[i]}")
    return "\n".join(result)


def _get_relevant_evidence(ev: Evidence, issue: ValidationIssue) -> str:
    """Extract the specific evidence relevant to this issue."""

    lines: list[str] = []

    if issue.section == "string_literal":
        for mod in ev.source_files:
            if mod.string_literals:
                lines.append(
                    f"String literals used in source: {', '.join(repr(s) for s in mod.string_literals[:30])}"
                )

    elif issue.section == "return_type":
        owner_name, fn_name = _issue_symbol(issue.message)
        for mod in ev.source_files:
            for fn in mod.functions:
                if not owner_name and fn.name == fn_name:
                    lines.append(f"def {fn.name}(...) -> {fn.return_annotation}")
            for cls in mod.classes:
                for method in cls.methods:
                    if cls.name == owner_name and method.name == fn_name:
                        lines.append(f"{cls.name}.{method.name}(...) -> {method.return_annotation}")
                    elif not owner_name and method.name == fn_name:
                        lines.append(f"{cls.name}.{method.name}(...) -> {method.return_annotation}")

    elif issue.section == "field_count":
        cls_name = ""
        m = re.match(r"'(\w+)'", issue.message)
        if m:
            cls_name = m.group(1)
        for mod in ev.source_files:
            for cls in mod.classes:
                if cls.name == cls_name:
                    lines.append(f"class {cls.name} has {len(cls.class_variables)} fields:")
                    for vname, vtype in cls.class_variables:
                        lines.append(f"  {vname}: {vtype}" if vtype else f"  {vname}")

    elif issue.section == "constants":
        for mod in ev.source_files:
            for name, value in mod.constants:
                if name in issue.message:
                    lines.append(f"{name} = {value}")

    elif issue.section == "symbols":
        lines.append("Public symbols in evidence:")
        for s in ev.all_public_symbols()[:30]:
            lines.append(f"  {s}")

    if not lines:
        lines.append(f"Issue: {issue.message}")

    return "\n".join(lines)


def _get_llm_client():
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return None


def _issue_symbol(message: str) -> tuple[str, str]:
    match = re.match(r"'([\w\.]+)'", message)
    if not match:
        return "", ""
    symbol = match.group(1)
    owner_name, _, symbol_name = symbol.rpartition(".")
    return owner_name, symbol_name or symbol


def _call_llm(prompt: str, max_tokens: int = 512) -> Optional[str]:
    client = _get_llm_client()
    if client is None:
        return None
    try:
        model = os.environ.get("AST_PILOT_MODEL", "claude-haiku-4-5")
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return response.content[0].text
    except Exception as e:
        print(f"[warn] Fixer LLM call failed: {e}")
        return None
