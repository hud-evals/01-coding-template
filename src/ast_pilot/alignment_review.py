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


def _log(msg: str, *, end: str = "\n") -> None:
    import sys
    print(msg, end=end, flush=True)

REVIEW_SYSTEM_PROMPT = """\
You are a strict benchmark contract auditor.

Your job is to compare a task prompt against its hidden grader tests and \
decide whether an agent reading ONLY the prompt can determine the exact \
behavior the tests require.

For every assertion or expected value in the test, ask yourself: \
"Could an agent produce this exact output from the prompt alone, with \
no guessing?" If the answer is no, that is an issue.

Be aggressive about finding issues. Common problems include:
- The test expects specific keys/properties in output that the prompt \
  doesn't specify (e.g. both alias AND primary key in a result object)
- The test expects errors to be thrown but the prompt doesn't say when \
  or what errors to throw
- The test expects exact string formatting (column alignment, spacing, \
  newlines) that the prompt doesn't define precisely
- The test expects a specific execution order (e.g. plugin hooks before/after \
  command logic) that the prompt doesn't describe
- The test expects edge case handling (e.g. hyphen-prefixed values, empty \
  inputs, negation flags) that the prompt doesn't mention
- The prompt uses vague language ("resolve both", "handle gracefully") where \
  the test checks a specific concrete behavior

Classify each issue as one of:
- underspecified: prompt is vague where test expects specific behavior
- hidden_requirement: test checks something the prompt never mentions
- direct_contradiction: prompt says X, test expects Y
- prompt_only_ungraded: prompt describes behavior no test checks
- unclear: ambiguous wording that could be read either way

Mark safe_to_fix=true when the prompt can be tightened to match the test \
without contradicting any existing explicit claims.

Mark safe_to_fix=false for contradictions or cases where fixing would \
require guessing intent.

Output strict JSON only.  If there are no issues, output:
{"issues": []}
"""

CONFIRM_SYSTEM_PROMPT = """\
You are a strict benchmark contract auditor doing a confirmation pass.

You receive a list of candidate issues found by a first-pass reviewer. \
For each issue, verify it by checking: could an agent reading ONLY the \
prompt produce the exact output the test expects?

Rules for this pass:
- Remove exact duplicates (same issue reported from multiple test files)
- Keep issues where the prompt is vague but the test expects specific behavior
- Keep issues where the test checks edge cases the prompt never mentions
- Keep issues where exact output format (keys, order, spacing) matters \
  but the prompt doesn't specify it
- Only remove issues that are genuine false positives — where the prompt \
  actually DOES clearly specify the exact behavior the test checks
- Do NOT remove an issue just because the prompt "sort of" or "implicitly" \
  covers it. If an agent would have to guess, it's a real issue.
- Confirm the safe_to_fix classification

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
    confidence: str = ""
    verdict: str = ""

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
    language: str = "",
    max_review_tokens: int = MAX_REVIEW_TOKENS,
    max_confirm_tokens: int = MAX_CONFIRM_TOKENS,
) -> AlignmentReview:
    """Run a two-stage LLM alignment review on a generated task directory.

    *task_dir* must contain ``prompt.md`` and a ``tests/`` subtree.
    Optionally reads ``task.py`` for bash_checks context.

    *language* can be ``"python"`` or ``"typescript"``.  When empty the
    loader auto-detects based on file extensions found under ``tests/``.
    """
    task_dir = Path(task_dir)
    prompt_md = _load_prompt(task_dir)
    test_files = _load_test_files(task_dir, language=language)
    task_py_summary = _load_task_summary(task_dir)

    if not test_files:
        return AlignmentReview()

    import time as _time

    _log(f"  Loading {len(test_files)} hidden test file(s)…")
    expectations = extract_grader_expectations(test_files, language=language)
    surface = extract_prompt_surface(prompt_md, language=language)
    gap_report = compute_gaps(expectations, surface, language=language)
    gap_context = gap_report.format_for_llm()
    if gap_report.total_gaps == 0:
        _log("  Deterministic gap analysis: clean (0 gaps)")
    else:
        parts = []
        if gap_report.imports_not_in_prompt:
            parts.append(f"{len(gap_report.imports_not_in_prompt)} imports")
        if gap_report.methods_not_in_prompt:
            parts.append(f"{len(gap_report.methods_not_in_prompt)} methods")
        if gap_report.attributes_not_in_prompt:
            parts.append(f"{len(gap_report.attributes_not_in_prompt)} attrs")
        if gap_report.classes_not_in_prompt:
            parts.append(f"{len(gap_report.classes_not_in_prompt)} classes")
        if gap_report.module_mismatches:
            parts.append(f"{len(gap_report.module_mismatches)} modules")
        _log(f"  Deterministic gap analysis: {gap_report.total_gaps} candidates ({', '.join(parts)})")
        _log("    Most are test-internal (mock vars, test data, JS builtins) — LLM review filters real issues")

    raw_issues: list[dict] = []
    t0 = _time.monotonic()
    n = len(test_files)

    if n == 1:
        test_name, test_content = test_files[0]
        _log(f"  [1/1] Reviewing {test_name}…", end="")
        per_file = _review_single_test(
            prompt_md, test_name, test_content, task_py_summary,
            max_tokens=max_review_tokens,
            gap_context=gap_context,
        )
        issues_tag = f" ({len(per_file)} issues)" if per_file else ""
        _log(f" done{issues_tag} [{_time.monotonic() - t0:.1f}s]")
        raw_issues.extend(per_file)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _log(f"  Reviewing {n} test files in parallel…")
        futures = {}
        with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
            for test_name, test_content in test_files:
                fut = pool.submit(
                    _review_single_test,
                    prompt_md, test_name, test_content, task_py_summary,
                    max_tokens=max_review_tokens,
                    gap_context=gap_context,
                )
                futures[fut] = test_name

            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                test_name = futures[fut]
                per_file = fut.result()
                issues_tag = f" ({len(per_file)} issues)" if per_file else ""
                _log(f"    [{done_count}/{n}] {test_name}{issues_tag}")
                raw_issues.extend(per_file)

        _log(f"  All {n} reviews done [{_time.monotonic() - t0:.1f}s]")

    if not raw_issues:
        _log("  Verdict pass…", end="")
        verdict = _get_confidence_verdict(prompt_md, test_files, gap_context, issues=[])
        _log(f" done [{_time.monotonic() - t0:.1f}s total]")
        return AlignmentReview(**verdict)

    _log(f"  Confirmation pass ({len(raw_issues)} candidate issues)…", end="")
    confirmed = _confirmation_pass(
        prompt_md, raw_issues, test_files,
        max_tokens=max_confirm_tokens,
    )
    _log(f" done ({len(confirmed)} confirmed)")

    _log("  Verdict pass…", end="")
    review = _parse_issues(confirmed)
    verdict = _get_confidence_verdict(prompt_md, test_files, gap_context, issues=confirmed)
    review.confidence = verdict.get("confidence", "")
    review.verdict = verdict.get("verdict", "")
    _log(f" done [{_time.monotonic() - t0:.1f}s total]")
    return review


def _load_prompt(task_dir: Path) -> str:
    prompt_path = task_dir / "prompt.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Missing prompt.md in {task_dir}")
    return prompt_path.read_text(encoding="utf-8")


def _load_test_files(task_dir: Path, *, language: str = "") -> list[tuple[str, str]]:
    tests_dir = task_dir / "tests"
    if not tests_dir.is_dir():
        return []

    if not language:
        language = _detect_test_language(tests_dir)

    if language == "typescript":
        patterns = ("**/*.ts", "**/*.mts")
    else:
        patterns = ("**/*.py",)

    seen: set[Path] = set()
    files: list[tuple[str, str]] = []
    for pattern in patterns:
        for test_path in sorted(tests_dir.rglob(pattern.replace("**/", ""))):
            if test_path in seen or not test_path.is_file():
                continue
            seen.add(test_path)
            try:
                rel = str(test_path.relative_to(tests_dir))
            except ValueError:
                rel = test_path.name
            files.append((rel, test_path.read_text(encoding="utf-8")))
    return files


def _detect_test_language(tests_dir: Path) -> str:
    """Auto-detect language from the test files present."""
    has_ts = any(tests_dir.rglob("*.ts"))
    has_py = any(tests_dir.rglob("*.py"))
    if has_ts and not has_py:
        return "typescript"
    if has_py and not has_ts:
        return "python"
    if has_ts:
        return "typescript"
    return "python"


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

For EACH assertion in the test file, check whether the prompt gives enough \
information to produce the exact expected value. Report every case where an \
agent would need to guess. Be thorough — check output shapes, error conditions, \
execution order, exact string formatting, and edge cases.

If there are genuinely no issues, output {{"issues": []}}.
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


def _get_confidence_verdict(
    prompt_md: str,
    test_files: list[tuple[str, str]],
    gap_context: str,
    *,
    issues: list[dict],
) -> dict:
    test_names = ", ".join(name for name, _ in test_files)
    issue_summary = f"{len(issues)} issues found" if issues else "no issues found"

    user_prompt = f"""You just reviewed a coding task for prompt-grader alignment.

Task has {len(test_files)} test file(s): {test_names}
Review result: {issue_summary}

{gap_context}

Prompt length: {len(prompt_md)} chars

Rate your confidence that an agent following only the prompt would pass \
the hidden tests. Be honest and brief.

Output strict JSON:
{{
  "confidence": "high" | "medium" | "low",
  "verdict": "1-2 sentence summary of alignment quality and any residual risk"
}}"""

    response = call_text_llm(user_prompt, max_tokens=256, expect_json=True)
    if response is None:
        return {"confidence": "", "verdict": ""}

    try:
        data = json.loads(response)
        return {
            "confidence": str(data.get("confidence", "")),
            "verdict": str(data.get("verdict", "")),
        }
    except (json.JSONDecodeError, TypeError):
        return {"confidence": "", "verdict": ""}


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
