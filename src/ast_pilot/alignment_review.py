"""Alignment review: LLM-only contract audit of prompt vs hidden graders.

Compares the final ``prompt.md`` against the final hidden test files
and (optionally) ``task.py`` to detect prompt-grader mismatches.

Two-stage review:
  1. Per-test-file review — each test file is compared against the full prompt.
  2. Aggregate confirmation — dedupes and confirms issues.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .grader_expectations import (
    compute_gaps,
    extract_grader_expectations,
    extract_prompt_surface,
    format_asserted_literals_for_llm,
)
from .llm_client import call_text_llm
from .tui import ui as _ui

MAX_REVIEW_TOKENS = 32768
MAX_CONFIRM_TOKENS = 16384


def _log(msg: str) -> None:
    """Emit a pipeline log line through the shared TUI."""
    stripped = msg.strip()
    if stripped.startswith("[ALIGNMENT ROLLBACK]"):
        _ui().warn(stripped.removeprefix("[ALIGNMENT ROLLBACK] "))
        return
    if stripped.startswith("[ALIGNMENT FIX"):
        _ui().success(stripped)
        return
    _ui().detail(stripped)

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
- The test asserts a specific literal string appears in the output \
  (e.g. ``assert "123456789:***" in result``) but the prompt tells the \
  agent to apply a substitution/format rule that would produce a DIFFERENT \
  literal (e.g. calling a helper that returns first-6 + "..." + last-4). \
  Every asserted literal must be reproducible verbatim from the prompt's \
  instructions — if not, that is a direct_contradiction (safe_to_fix=true: \
  rewrite the instruction to produce the asserted literal).

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

Every issue MUST include a ``failure_demo`` object proving an agent would \
actually fail the hidden test. The downstream parser drops issues whose \
demo shows the agent's predicted output matching the test's expected value, \
so vague concerns are auto-filtered. Be concrete:

  "failure_demo": {
    "test_input": "<the exact input/setup the failing assertion uses>",
    "test_expects": "<the exact value the test asserts, verbatim>",
    "agent_following_prompt_produces": "<what an agent reading ONLY the prompt would actually output, made concrete from the prompt's rules>"
  }

If you cannot make ``test_expects`` and ``agent_following_prompt_produces`` \
into two strings that differ, the prompt is doing its job and there is no \
issue. Drop the entry instead of returning it.

When an ASSERTED TEST LITERALS section is present, you MUST also populate a \
``literal_checks`` array. Each entry is the structured result of simulating \
one asserted literal against the prompt's substitution rules. Fill every \
field on every entry — the downstream fixer consumes them directly.

Output strict JSON only. If there are no model-flagged issues AND no literal \
checks were requested, output ``{"issues": [], "literal_checks": []}``.
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

Each confirmed issue must keep its ``failure_demo`` object — the \
downstream parser drops any issue whose demo has matching \
``test_expects`` and ``agent_following_prompt_produces``. If you find \
yourself unable to write two materially different strings for those \
fields on a candidate issue, drop the candidate instead of confirming it.

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
    # Per-test-file review failures (LLM returned None / unparseable JSON).
    # When non-empty, the review is incomplete: callers must NOT treat
    # `is_clean` as "no problems" — coverage for these files is unknown.
    unavailable_tests: list[str] = field(default_factory=list)

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
        return len(self.issues) == 0 and not self.unavailable_tests

    @property
    def is_unavailable(self) -> bool:
        return bool(self.unavailable_tests)


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
    assertion_context = format_asserted_literals_for_llm(expectations)
    assertion_literal_count = (
        len(expectations.assertion_in_literals)
        + len(expectations.assertion_not_in_literals)
        + len(expectations.assertion_eq_literals)
    )
    if assertion_literal_count:
        _log(
            f"  Asserted literals for cross-check: {assertion_literal_count} "
            f"({len(expectations.assertion_in_literals)} in, "
            f"{len(expectations.assertion_not_in_literals)} not-in, "
            f"{len(expectations.assertion_eq_literals)} eq)"
        )
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
    raw_literal_checks: list[dict] = []
    unavailable_tests: list[str] = []
    t0 = _time.monotonic()
    n = len(test_files)

    def _consume(per_file: dict, test_name: str) -> str:
        if per_file.get("_review_failed"):
            unavailable_tests.append(test_name)
            return " (review unavailable)"
        issues = per_file.get("issues", []) or []
        checks = per_file.get("literal_checks", []) or []
        raw_issues.extend(issues)
        raw_literal_checks.extend(checks)
        failed = sum(1 for c in checks if isinstance(c, dict) and c.get("matches_literal") is False)
        tags = []
        if issues:
            tags.append(f"{len(issues)} issues")
        if failed:
            tags.append(f"{failed} failed literal checks")
        return f" ({', '.join(tags)})" if tags else ""

    if n == 1:
        test_name, test_content = test_files[0]
        with _ui().live_status(f"[1/1] reviewing {test_name}"):
            per_file = _review_single_test(
                prompt_md, test_name, test_content, task_py_summary,
                max_tokens=max_review_tokens,
                gap_context=gap_context,
                assertion_context=assertion_context,
            )
        _log(f"  [1/1] {test_name} done{_consume(per_file, test_name)} [{_time.monotonic() - t0:.1f}s]")
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _log(f"  Reviewing {n} test files in parallel…")
        futures = {}
        with _ui().live_status(f"reviewing {n} test files in parallel"):
            with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
                for test_name, test_content in test_files:
                    fut = pool.submit(
                        _review_single_test,
                        prompt_md, test_name, test_content, task_py_summary,
                        max_tokens=max_review_tokens,
                        gap_context=gap_context,
                        assertion_context=assertion_context,
                    )
                    futures[fut] = test_name

                done_count = 0
                for fut in as_completed(futures):
                    done_count += 1
                    test_name = futures[fut]
                    per_file = fut.result()
                    _log(f"  [{done_count}/{n}] {test_name}{_consume(per_file, test_name)}")

        _log(f"  all {n} reviews done [{_time.monotonic() - t0:.1f}s]")

    forced_issues = _forced_issues_from_failed_checks(raw_literal_checks)
    if forced_issues:
        _log(f"  forced issues from failed literal checks: {len(forced_issues)}")

    if unavailable_tests:
        _log(
            f"  [WARN] {len(unavailable_tests)}/{n} test file(s) had unavailable "
            "alignment review (LLM returned no parseable response). Coverage for "
            f"those files is UNKNOWN: {', '.join(unavailable_tests)}"
        )

    if not raw_issues and not forced_issues:
        with _ui().live_status("verdict pass"):
            verdict = _get_confidence_verdict(prompt_md, test_files, gap_context, issues=[])
        _log(f"  verdict pass done [{_time.monotonic() - t0:.1f}s total]")
        return AlignmentReview(unavailable_tests=unavailable_tests, **verdict)

    if raw_issues:
        with _ui().live_status(f"confirmation pass ({len(raw_issues)} candidate issues)"):
            confirmed = _confirmation_pass(
                prompt_md, raw_issues, test_files,
                max_tokens=max_confirm_tokens,
            )
        _log(f"  confirmation pass done ({len(confirmed)} confirmed)")
    else:
        confirmed = []

    final_issues = confirmed + forced_issues

    with _ui().live_status("verdict pass"):
        review = _parse_issues(final_issues)
        verdict = _get_confidence_verdict(prompt_md, test_files, gap_context, issues=final_issues)
    review.confidence = verdict.get("confidence", "")
    review.verdict = verdict.get("verdict", "")
    review.unavailable_tests = unavailable_tests
    _log(f"  verdict pass done [{_time.monotonic() - t0:.1f}s total]")
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
    assertion_context: str = "",
) -> dict:
    gap_section = ""
    if gap_context and "No deterministic gaps" not in gap_context:
        gap_section = f"""
=== DETERMINISTIC GAP ANALYSIS (review these carefully) ===
{gap_context}

The above gaps were found by automated analysis. For each gap, decide
whether it represents a real prompt-grader mismatch or a false positive.
Include confirmed gaps as issues in your output.
"""

    assertion_section = ""
    if assertion_context:
        assertion_section = f"""
=== ASSERTED TEST LITERALS (cross-check every one against the prompt) ===
{assertion_context}
"""

    user_prompt = f"""{REVIEW_SYSTEM_PROMPT}

=== PROMPT (the agent sees this) ===
{prompt_md}

=== HIDDEN TEST FILE: {test_name} ===
{test_content}

=== TASK METADATA ===
{task_summary or "(none)"}
{gap_section}{assertion_section}

For EACH assertion in the test file, check whether the prompt gives enough \
information to produce the exact expected value. Report every case where an \
agent would need to guess. Be thorough — check output shapes, error conditions, \
execution order, exact string formatting, and edge cases.

For every literal in ASSERTED TEST LITERALS, run this 4-step check:
  1. Read the test case and identify the INPUT the agent's code receives.
  2. Find which regex/pattern/rule in the prompt would match that input.
  3. Find the SUBSTITUTION the prompt prescribes for that rule (what exact \
     string it replaces the match with — call helpers, format strings, literal \
     constants).
  4. Mentally execute the substitution on the test input. Would the result \
     contain the asserted literal VERBATIM?

If step 4 is "no" — the prompt's substitution rule would produce a DIFFERENT \
string than the asserted literal — that is a direct_contradiction with \
safe_to_fix=true. Flag it with grader_evidence = the test assertion and \
prompt_evidence = the contradicting substitution instruction.

Do NOT accept "the literal is mentioned somewhere in the prompt as an example" \
as proof the rule produces it. The prompt can describe expected output in one \
place and prescribe a contradicting rule in another — that is exactly the bug \
you are here to catch.

Output strict JSON matching this schema:
{{
  "literal_checks": [
    {{
      "literal": "<exact literal string from ASSERTED TEST LITERALS>",
      "polarity": "in" | "not_in" | "eq",
      "test_input": "<the input value the agent's code receives in the relevant test>",
      "matching_rule": "<the specific prompt instruction / Node N / bullet that governs this input, verbatim or tight paraphrase>",
      "simulated_output": "<what the prompt's rule would actually emit when run on test_input>",
      "matches_literal": true | false,
      "note": "<one short sentence — required when matches_literal is false, optional otherwise>"
    }}
    // one entry per literal in ASSERTED TEST LITERALS
  ],
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
}}

Rules for literal_checks:
- One entry per literal in ASSERTED TEST LITERALS. Do not skip any.
- For polarity "in": matches_literal is true iff simulated_output contains the \
  literal VERBATIM as a substring. For "not_in": matches_literal is true iff \
  simulated_output does NOT contain the literal. For "eq": matches_literal is \
  true iff simulated_output equals the literal exactly.
- Do NOT also add an `issues` entry for failed literal checks — the fixer \
  converts every matches_literal=false into a direct_contradiction fix \
  automatically. The `issues` array is only for problems the literal-check \
  schema does not cover."""

    response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)
    if response is None:
        response = call_text_llm(user_prompt, max_tokens=max_tokens, expect_json=True)

    _dump_review_debug(test_name, response)

    if response is None:
        _log(
            f"    [WARN] reviewer returned unparseable/empty JSON for {test_name} — "
            "alignment check for this file was SKIPPED. Set AST_PILOT_DEBUG_REVIEW=<dir> "
            "to capture the raw response."
        )
        # Sentinel: caller must NOT treat this as "clean review with zero issues".
        # The review didn't run; coverage for this test file is unknown.
        return {"issues": [], "literal_checks": [], "_review_failed": True}

    return _parse_review_response(response)


def _dump_review_debug(test_name: str, response: str | None) -> None:
    """When AST_PILOT_DEBUG_REVIEW is set, write the raw reviewer response to disk."""
    debug_dir = os.environ.get("AST_PILOT_DEBUG_REVIEW")
    if not debug_dir:
        return
    dp = Path(debug_dir)
    dp.mkdir(parents=True, exist_ok=True)
    safe_name = test_name.replace("/", "_")
    (dp / f"{safe_name}.review.raw.txt").write_text(
        response if response is not None else "<response was None>",
        encoding="utf-8",
    )


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


def _parse_review_response(text: str) -> dict:
    """Parse a reviewer response into ``{'issues': [...], 'literal_checks': [...]}``.

    Tolerant to models that return only ``issues`` (older schema) or only
    ``literal_checks``.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = None
    if not isinstance(data, dict):
        return {"issues": [], "literal_checks": []}
    issues = data.get("issues")
    checks = data.get("literal_checks")
    return {
        "issues": issues if isinstance(issues, list) else [],
        "literal_checks": checks if isinstance(checks, list) else [],
    }


def _forced_issues_from_failed_checks(literal_checks: list[dict]) -> list[dict]:
    """Convert ``matches_literal=false`` entries into direct_contradiction issues.

    Deduplicates on (literal, polarity) so parallel reviews cannot double-report
    the same asserted literal.
    """
    forced: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for check in literal_checks:
        if not isinstance(check, dict):
            continue
        if check.get("matches_literal") is not False:
            continue
        literal = str(check.get("literal", "")).strip()
        if not literal:
            continue
        polarity = str(check.get("polarity", "in")).strip() or "in"
        key = (literal, polarity)
        if key in seen:
            continue
        seen.add(key)

        rule = str(check.get("matching_rule", "")).strip()
        simulated = str(check.get("simulated_output", "")).strip()
        note = str(check.get("note", "")).strip()

        polarity_desc = {
            "in": "must APPEAR in output",
            "not_in": "must NOT appear in output",
            "eq": "output must EQUAL",
        }.get(polarity, polarity)

        rationale = (
            f"The prompt's rule, when executed on the test input, emits "
            f"{simulated!r} instead. Rewrite the rule so it emits {literal!r} verbatim."
        )
        if note:
            rationale = f"{rationale} Reviewer note: {note}"

        forced.append({
            "severity": "error",
            "category": "direct_contradiction",
            "title": f"Prompt rule does not reproduce asserted literal {literal!r}",
            "prompt_evidence": rule,
            "grader_evidence": f"Test asserts {literal!r} {polarity_desc}.",
            "rationale": rationale,
            "safe_to_fix": True,
        })
    return forced


_SELF_ADMITTED_NON_ISSUE_MARKERS = (
    "not a genuine issue",
    "not a real issue",
    "not an issue",
    "false positive",
    "does not represent a real",
    "is already specified",
    "is already documented",
)


def _is_self_admitted_non_issue(rationale: str) -> bool:
    """Detect rationales whose text outright says the issue isn't real.

    A small belt-and-suspenders backstop for the structural ``failure_demo``
    cross-check below — useful for legacy responses that don't carry a demo.
    """
    lowered = rationale.lower()
    return any(marker in lowered for marker in _SELF_ADMITTED_NON_ISSUE_MARKERS)


def _normalize_demo_value(text: str) -> str:
    """Lowercase, collapse whitespace, strip surrounding quotes/punctuation
    so semantically-equal demo strings compare equal even if the LLM tweaks
    casing or wraps one side in quotes."""
    lowered = " ".join(text.lower().split())
    return lowered.strip(" \t\n\"'`.,;:")


def _failure_demo_is_non_issue(raw: dict) -> tuple[bool, str]:
    """Return ``(is_non_issue, reason)`` for the issue's ``failure_demo``.

    The reviewer must commit to two strings — what the test asserts vs what
    an agent following only the prompt would produce. If those normalize to
    the same value the prompt is doing its job and there's nothing to fix;
    if either is empty the reviewer never made the failure concrete and we
    can't trust the entry to be an issue. Everything else passes through.
    """
    demo = raw.get("failure_demo")
    if not isinstance(demo, dict):
        return True, "missing failure_demo (no concrete failure described)"
    expects_raw = demo.get("test_expects", "")
    produces_raw = demo.get("agent_following_prompt_produces", "")
    if not isinstance(expects_raw, str) or not isinstance(produces_raw, str):
        return True, "failure_demo fields are not strings"
    expects = _normalize_demo_value(expects_raw)
    produces = _normalize_demo_value(produces_raw)
    if not expects or not produces:
        return True, "failure_demo strings are empty"
    if expects == produces:
        return True, "failure_demo shows the agent's output already matches the test"
    return False, ""


def _parse_issues(raw_issues: list[dict]) -> AlignmentReview:
    issues: list[AlignmentIssue] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue
        rationale = str(raw.get("rationale", ""))

        is_non_issue, demo_reason = _failure_demo_is_non_issue(raw)
        if is_non_issue:
            _log(
                "    [FILTERED non-issue] "
                f"{str(raw.get('title', ''))[:100]} — {demo_reason}"
            )
            continue

        if _is_self_admitted_non_issue(rationale):
            _log(
                "    [FILTERED non-issue] "
                f"{str(raw.get('title', ''))[:100]} — rationale admits this isn't real"
            )
            continue

        try:
            issues.append(AlignmentIssue(
                severity=str(raw.get("severity", "error")),
                category=str(raw.get("category", "unclear")),
                title=str(raw.get("title", "")),
                prompt_evidence=str(raw.get("prompt_evidence", "")),
                grader_evidence=str(raw.get("grader_evidence", "")),
                rationale=rationale,
                safe_to_fix=bool(raw.get("safe_to_fix", False)),
            ))
        except (TypeError, ValueError):
            continue
    return AlignmentReview(issues=issues)
