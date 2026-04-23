"""Alignment fixer: LLM-driven minimal prompt repair for safe issues.

Only edits the prompt — never touches grader code.
After each fix the caller must re-run source-truth validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .alignment_review import AlignmentIssue, AlignmentReview
from .llm_client import call_text_llm

MAX_FIX_TOKENS = 16384

FIXER_SYSTEM_PROMPT = """\
You are editing a generated coding-task prompt so that it matches the \
hidden grader more precisely.

Rules:
- preserve the prompt's existing structure and tone
- keep edits minimal and local
- only fix the listed safe issues
- do not invent behavior that is not supported by the current prompt \
and grader evidence
- do not remove required source-truth details
- return only the full revised markdown
"""


@dataclass
class AlignmentFixResult:
    updated_prompt: str
    changed: bool
    applied_issue_titles: list[str] = field(default_factory=list)


def autofix_prompt_alignment(
    *,
    prompt_md: str,
    review: AlignmentReview,
    max_tokens: int = MAX_FIX_TOKENS,
) -> AlignmentFixResult:
    """Rewrite the prompt to address fixable alignment issues.

    Only issues where ``safe_to_fix`` is True and ``severity`` is
    ``"error"`` are sent to the LLM.  The returned
    ``AlignmentFixResult.updated_prompt`` contains the full revised
    markdown.  If the LLM fails or there is nothing to fix, the
    original prompt is returned unchanged.
    """
    fixable = review.fixable_issues
    if not fixable:
        return AlignmentFixResult(updated_prompt=prompt_md, changed=False)

    issues_text = _format_issues(fixable)

    user_prompt = f"""{FIXER_SYSTEM_PROMPT}

=== CURRENT PROMPT ===
{prompt_md}

=== SAFE ISSUES TO FIX ===
{issues_text}

Preferred sections to edit first:
- ## Natural Language Instructions
- ## Required Tested Symbols
- ## API Usage Guide
- ## Implementation Notes

Return ONLY the full revised prompt markdown. No explanation, no \
code fences around the markdown."""

    response = call_text_llm(user_prompt, max_tokens=max_tokens)
    if response is None:
        return AlignmentFixResult(updated_prompt=prompt_md, changed=False)

    revised = response.strip()

    if not revised or revised == prompt_md.strip():
        return AlignmentFixResult(updated_prompt=prompt_md, changed=False)

    return AlignmentFixResult(
        updated_prompt=revised,
        changed=True,
        applied_issue_titles=[i.title for i in fixable],
    )


def _format_issues(issues: list[AlignmentIssue]) -> str:
    parts: list[str] = []
    for idx, issue in enumerate(issues, 1):
        parts.append(
            f"{idx}. [{issue.category}] {issue.title}\n"
            f"   Prompt evidence: {issue.prompt_evidence}\n"
            f"   Grader evidence: {issue.grader_evidence}\n"
            f"   Rationale: {issue.rationale}"
        )
    return "\n\n".join(parts)


def _validate_prompt(language: str, ev, prompt_path):
    """Dispatch to the correct language-specific validator."""
    if language == "typescript":
        from . import node_validator
        return node_validator.validate(ev, prompt_path)
    from . import validator
    return validator.validate(ev, prompt_path)


def run_alignment_loop(
    task_dir: str | Path,
    ev,
    *,
    max_rounds: int = 2,
    use_llm: bool = True,
) -> AlignmentReview:
    """Run the full alignment review/fix loop on a generated task.

    Returns the final ``AlignmentReview``.  If blocking issues remain
    after *max_rounds*, the caller should refuse to promote the task.
    """
    from .alignment_review import review_task_alignment

    language = getattr(ev, "language", "python") or "python"

    task_dir = Path(task_dir)
    prompt_path = task_dir / "prompt.md"

    if not use_llm or not prompt_path.is_file():
        return AlignmentReview()

    for round_num in range(1, max_rounds + 1):
        review = review_task_alignment(task_dir, language=language)

        if review.is_clean:
            return review

        if not review.fixable_issues:
            return review

        if review.has_blocking and not review.fixable_issues:
            return review

        prompt_md = prompt_path.read_text(encoding="utf-8")
        fix_result = autofix_prompt_alignment(prompt_md=prompt_md, review=review)

        if not fix_result.changed:
            return review

        prompt_path.write_text(fix_result.updated_prompt, encoding="utf-8")
        from .tui import ui as _ui
        _ui().success(
            f"round {round_num} applied {len(fix_result.applied_issue_titles)} fix(es)"
        )
        _ui().issues_table([
            ("fixed", title, "") for title in fix_result.applied_issue_titles
        ])

        vr = _validate_prompt(language, ev, prompt_path)
        if vr.error_count > 0:
            _ui().warn("alignment rollback — factual validation failed, reverting prompt")
            prompt_path.write_text(prompt_md, encoding="utf-8")
            return review

    final_review = review_task_alignment(task_dir, language=language)
    return final_review
