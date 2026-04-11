"""Alignment review: LLM-only contract audit of prompt vs hidden graders.

Compares the final ``prompt.md`` against the final hidden test files
and (optionally) ``task.py`` to detect prompt-grader mismatches.

Two-stage review:
  1. Per-test-file review — each test file is compared against the full prompt.
  2. Aggregate confirmation — dedupes and confirms issues.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .grader_expectations import (
    compute_gaps,
    extract_grader_expectations,
    extract_prompt_surface,
)
from .llm_client import call_text_llm

MAX_REVIEW_TOKENS = 8192
MAX_CONFIRM_TOKENS = 8192

REVIEW_SYSTEM_PROMPT = """\
You are a benchmark contract auditor.

Your job is to compare a task prompt against its hidden grader tests and \
decide whether they describe the same contract.

You must only report issues that are supported by direct quotations from \
both the prompt and the grader.

Classify each issue as one of:
- underspecified
- hidden_requirement
- direct_contradiction
- prompt_only_ungraded
- unclear

Mark safe_to_fix=true only when the prompt can be tightened without \
changing the intended behavior or contradicting the prompt's existing \
explicit claims.

Mark safe_to_fix=false for contradictions, incompatible grader \
expectations, or anything too ambiguous to repair safely.

Output strict JSON only.  If there are no issues, output:
{"issues": []}
"""

CONFIRM_SYSTEM_PROMPT = """\
You are a benchmark contract auditor doing a confirmation pass.

You receive a list of candidate issues found by a first-pass reviewer.  \
For each issue, verify that it is real by checking the quoted evidence \
against the prompt and grader snippets provided.

Remove duplicates.  Downgrade or remove issues that turn out to be \
false positives on closer reading.  Confirm the safe_to_fix \
classification.

Output strict JSON only with the same schema:
{"issues": [...]}
"""


@dataclass
class AlignmentIssue:
    severity: str  # "warning" | "error"
    category: str  # "underspecified" | "hidden_requirement" | "direct_contradiction" | "prompt_only_ungraded" | "unclear"
    title: str
    prompt_evidence: str
    grader_evidence: str
    rationale: str
    safe_to_fix: bool


@dataclass
class AlignmentReview:
    issues: list[AlignmentIssue] = field(default_factory=list)

    @property
    def blocking_issues(self) -> list[AlignmentIssue]:
        return [i for i in self.issues if not i.safe_to_fix]

    @property
    def fixable_issues(self) -> list[AlignmentIssue]:
        return [i for i in self.issues if i.safe_to_fix and i.severity == "error"]

    @property
    def has_blocking(self) -> bool:
        return len(self.blocking_issues) > 0

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0


def review_task_alignment(
    task_dir: str | Path,
    *,
    max_review_tokens: int = MAX_REVIEW_TOKENS,
    max_confirm_tokens: int = MAX_CONFIRM_TOKENS,
) -> AlignmentReview:
    """Run a two-stage LLM alignment review on a generated task directory.

    *task_dir* must contain ``prompt.md`` and ``tests/*.py``.
    Optionally reads ``task.py`` for bash_checks context.
    """
    task_dir = Path(task_dir)
    prompt_md = _load_prompt(task_dir)
    test_files = _load_test_files(task_dir)
    task_py_summary = _load_task_summary(task_dir)

    if not test_files:
        return AlignmentReview()

    expectations = extract_grader_expectations(test_files)
    surface = extract_prompt_surface(prompt_md)
    gap_report = compute_gaps(expectations, surface)
    gap_context = gap_report.format_for_llm()

    raw_issues: list[dict] = []
    for test_name, test_content in test_files:
        per_file = _review_single_test(
            prompt_md, test_name, test_content, task_py_summary,
            max_tokens=max_review_tokens,
            gap_context=gap_context,
        )
        raw_issues.extend(per_file)

    if not raw_issues:
        return AlignmentReview()

    confirmed = _confirmation_pass(
        prompt_md, raw_issues, test_files,
        max_tokens=max_confirm_tokens,
    )

    return _parse_issues(confirmed)


def _load_prompt(task_dir: Path) -> str:
    prompt_path = task_dir / "prompt.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Missing prompt.md in {task_dir}")
    return prompt_path.read_text(encoding="utf-8")


def _load_test_files(task_dir: Path) -> list[tuple[str, str]]:
    tests_dir = task_dir / "tests"
    if not tests_dir.is_dir():
        return []
    files = []
    for test_path in sorted(tests_dir.glob("*.py")):
        files.append((test_path.name, test_path.read_text(encoding="utf-8")))
    return files


def _load_task_summary(task_dir: Path) -> str:
    task_path = task_dir / "task.py"
    if not task_path.is_file():
        return ""
    content = task_path.read_text(encoding="utf-8")
    lines = []
    for line in content.splitlines():
        if '"name"' in line or "bash_checks" in line or "weight" in line:
            lines.append(line.strip())
    return "\n".join(lines) if lines else "(task.py present but no bash_checks extracted)"


def _review_single_test(
    prompt_md: str,
    test_name: str,
    test_content: str,
    task_summary: str,
    *,
    max_tokens: int,
    gap_context: str = "",
) -> list[dict]:
    gap_section = ""
    if gap_context and "No deterministic gaps" not in gap_context:
        gap_section = f"""
=== DETERMINISTIC GAP ANALYSIS (review these carefully) ===
{gap_context}

The above gaps were found by automated analysis. For each gap, decide
whether it represents a real prompt-grader mismatch or a false positive.
Include confirmed gaps as issues in your output.
"""

    user_prompt = f"""{REVIEW_SYSTEM_PROMPT}

=== PROMPT (the agent sees this) ===
{prompt_md}

=== HIDDEN TEST FILE: {test_name} ===
{test_content}

=== TASK METADATA ===
{task_summary or "(none)"}
{gap_section}

Report alignment issues between the prompt and THIS test file.
If there are no issues, output {{"issues": []}}.
Output strict JSON matching this schema:
{{
  "issues": [
    {{
      "severity": "error",
      "category": "underspecified",
      "title": "...",
      "prompt_evidence": "...",
      "grader_evidence": "...",
      "rationale": "...",
      "safe_to_fix": true
    }}
  ]
}}"""

    response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)
    if response is None:
        response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)
    if response is None:
        return []

    return _parse_raw_issues_json(response)


def _confirmation_pass(
    prompt_md: str,
    raw_issues: list[dict],
    test_files: list[tuple[str, str]],
    *,
    max_tokens: int,
) -> list[dict]:
    grader_snippets = "\n\n".join(
        f"--- {name} (excerpt) ---\n{content[:2000]}"
        for name, content in test_files
    )

    raw_json = json.dumps(raw_issues, indent=2)

    user_prompt = f"""{CONFIRM_SYSTEM_PROMPT}

=== PROMPT ===
{prompt_md}

=== GRADER SNIPPETS ===
{grader_snippets}

=== CANDIDATE ISSUES FROM FIRST PASS ===
{raw_json}

Deduplicate, verify, and return the confirmed issues as strict JSON:
{{"issues": [...]}}"""

    response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)
    if response is None:
        response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)
    if response is None:
        return raw_issues

    return _parse_raw_issues_json(response) or raw_issues


def _parse_raw_issues_json(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, dict):
        return data.get("issues", [])
    return []


def _parse_issues(raw_issues: list[dict]) -> AlignmentReview:
    issues: list[AlignmentIssue] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue
        try:
            issues.append(AlignmentIssue(
                severity=str(raw.get("severity", "error")),
                category=str(raw.get("category", "unclear")),
                title=str(raw.get("title", "")),
                prompt_evidence=str(raw.get("prompt_evidence", "")),
                grader_evidence=str(raw.get("grader_evidence", "")),
                rationale=str(raw.get("rationale", "")),
                safe_to_fix=bool(raw.get("safe_to_fix", False)),
            ))
        except (TypeError, ValueError):
            continue
    return AlignmentReview(issues=issues)
