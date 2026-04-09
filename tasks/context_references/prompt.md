# context-references

## Overview

**context-references** is a lightweight Python library comprising 491 lines of code organized into a single source module. The library provides two primary classes and nineteen module-level functions designed to facilitate context-based reference management and manipulation. With its compact codebase and focused API surface, context-references offers a streamlined solution for handling contextual references within Python applications.

The library's architecture centers on two core classes that encapsulate the primary functionality for context reference operations. These classes work in conjunction with the nineteen module-level functions, which provide utility operations and convenience methods for common reference-handling tasks. This dual-layer design—combining object-oriented abstractions with functional utilities—enables developers to choose between class-based workflows for complex scenarios and direct function calls for simpler use cases.

The minimal footprint of context-references, with its single-module structure and lean implementation, makes it suitable for integration into projects where dependency overhead must be carefully managed. The library's focused scope on context references provides specialized functionality without the complexity of larger, multi-purpose frameworks.

## Natural Language Instructions

You are rebuilding a Python library called `context-references` that parses and expands context references in messages. The library allows users to embed references like `@file:path`, `@folder:path`, `@url:https://...`, `@diff`, `@staged`, and `@git:N` in text, then expands them into actual file contents, folder listings, or git output.

### Implementation Constraints

- All code must live in `/home/ubuntu/workspace/context_references.py` (single module file)
- The module must be importable as `from context_references import ...` (top-level)
- Implement exactly two dataclasses: `ContextReference` and `ContextReferenceResult`
- Implement exactly three public functions: `parse_context_references`, `preprocess_context_references`, and `preprocess_context_references_async`
- Implement all private helper functions with exact signatures (prefixed with `_`)
- Use the exact regex pattern and string constants provided
- Do NOT simplify or change any function signatures
- Handle both sync and async URL fetching
- Respect path security boundaries (allowed_root, HOME, HERMES_HOME)
- Support line range syntax in file references (e.g., `@file:path:1-10`)

### Behavioral Requirements

1. **ContextReference dataclass**: Store parsed reference metadata including raw text, kind (file/folder/git/url/diff/staged), target path/URL, character positions (start/end), and optional line range (line_start/line_end). All fields must be present as specified in the exact API.

2. **ContextReferenceResult dataclass**: Store the result of preprocessing including the modified message, original message, list of ContextReference objects, warning strings, token count of injected content, expanded flag, and blocked flag.

3. **parse_context_references(message)**: Use the provided REFERENCE_PATTERN regex to find all context references in the message. Extract kind (simple kinds like "diff"/"staged" or typed kinds like "file"/"folder"/"git"/"url"), target value, and character positions. Strip trailing punctuation from targets. Return a list of ContextReference objects with line_start/line_end parsed from "path:start-end" syntax (or None if not present).

4. **preprocess_context_references(message, cwd, context_length, url_fetcher, allowed_root)**: Parse references, expand each one, inject expanded content into the message, track warnings, and return a ContextReferenceResult. If allowed_root is None, default it to cwd. Respect context_length budget: warn if soft limit (75%) is exceeded, block expansion if hard limit (100%) would be exceeded. Remove reference tokens from the message and append "--- Attached Context ---" section with expanded content.

5. **preprocess_context_references_async(message, cwd, context_length, url_fetcher, allowed_root)**: Async version of preprocess_context_references. Use asyncio to expand references concurrently where possible. Handle both sync and async url_fetcher callables.

6. **_expand_reference(ref, cwd, url_fetcher, allowed_root)**: Async dispatcher that routes to appropriate expansion function based on ref.kind. Return tuple of (content, warning_message). Content is None if expansion failed; warning_message is None if no warning.

7. **_expand_file_reference(ref, cwd, allowed_root)**: Read file at ref.target (resolved relative to cwd). If line_start/line_end are set, extract only those lines. Check if file is binary and return appropriate warning. Validate path is within allowed_root. Return (content, warning).

8. **_expand_folder_reference(ref, cwd, allowed_root)**: Generate a folder listing for ref.target. Use ripgrep (rg) if available to list files, otherwise walk the directory. Limit to ~200 entries. Include file metadata (size, type). Return (listing_text, warning).

9. **_expand_git_reference(ref, cwd, args, label)**: Execute git command with given args in cwd. Capture stdout. Return (output, warning). Used for @diff, @staged, @git:N references.

10. **_fetch_url_content(url, url_fetcher)**: Async function that fetches URL content. If url_fetcher is provided, use it (handling both sync and async callables). Otherwise use _default_url_fetcher. Return the fetched content as string.

11. **_default_url_fetcher(url)**: Async function that fetches URL using urllib or similar. Return content as string. Used as fallback if no custom fetcher provided.

12. **_resolve_path(cwd, target, allowed_root)**: Convert target (which may be relative, absolute, or contain ~) to an absolute Path. Resolve relative paths against cwd. Validate the result is within allowed_root (if provided). Return the resolved Path.

13. **_ensure_reference_path_allowed(path)**: Check if path is in a sensitive location (HOME/.ssh, HOME/.aws, HOME/.config, HERMES_HOME/.env, etc.). Raise an exception if blocked. This prevents leaking credentials/secrets.

14. **_strip_trailing_punctuation(value)**: Remove trailing characters from TRAILING_PUNCTUATION set from the end of value string. Used to clean up reference targets extracted from text.

15. **_remove_reference_tokens(message, refs)**: Remove all reference tokens from message based on their start/end positions. Return cleaned message. Process refs in reverse order to maintain position validity.

16. **_is_binary_file(path)**: Detect if file at path is binary by reading first chunk and checking for null bytes or non-text patterns. Return True if binary, False if text.

17. **_build_folder_listing(path, cwd, limit)**: Generate a formatted text listing of folder contents. Include file names, sizes, and types. Limit to ~limit entries. Return formatted string suitable for inclusion in context.

18. **_iter_visible_entries(path, cwd, limit)**: List visible (non-hidden) entries in path directory. Return list of Path objects, limited to limit entries. Skip entries starting with dot.

19. **_rg_files(path, cwd, limit)**: Use ripgrep command (`rg --files`) to list files in path. Return list of Path objects or None if rg not available. Limit to limit entries.

20. **_file_metadata(path)**: Return a string describing file metadata (size, type, etc.) for display in folder listings.

21. **_code_fence_language(path)**: Determine appropriate language identifier for markdown code fence based on file extension. Return language string (e.g., "python", "javascript", "json") or empty string.

22. **REFERENCE_PATTERN**: Pre-compiled regex that matches @diff, @staged, @kind:value patterns. Must match the exact pattern provided.

23. **TRAILING_PUNCTUATION**: String constant ",.;!?" used to strip punctuation from reference targets.

24. **Token counting**: Estimate injected content size in tokens (roughly 1 token per 4 characters). Track total injected_tokens in result. Compare against context_length budget.

25. **Warning accumulation**: Collect all warnings (binary files, missing files, budget exceeded, blocked paths) in result.warnings list. Include warnings in the message output as well.

26. **Expanded flag**: Set to True if at least one reference was successfully expanded, False otherwise.

27. **Blocked flag**: Set to True if expansion was blocked due to hard budget limit or security restrictions, False otherwise.

28. **Message reconstruction**: Original message is preserved. Modified message has reference tokens removed and "--- Attached Context ---" section appended with all expanded content in code fences.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def parse_context_references(message: str) -> list[ContextReference]`
- `def preprocess_context_references(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None = None, allowed_root: str | Path | None = None) -> ContextReferenceResult`
- `async def preprocess_context_references_async(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None = None, allowed_root: str | Path | None = None) -> ContextReferenceResult`

## Environment Configuration

### Python Version

Python 3.10

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `context_references.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `agent.model_metadata`: repo-private helper module; the original code imported `estimate_tokens_rough` from `agent.model_metadata`. Recreate the needed behavior locally.
- `hermes_constants`: repo-private constants or lightweight helper values; the original code imported `get_hermes_home` from `hermes_constants`. Recreate the needed behavior locally.
- `tools.web_tools`: repo-private helper module; the original code imported `web_extract_tool` from `tools.web_tools`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── context_references.py
```

## API Usage Guide

### 1. Module Import

```python
from context_references import (
    ContextReference,
    ContextReferenceResult,
    parse_context_references,
    preprocess_context_references,
    preprocess_context_references_async,
    REFERENCE_PATTERN,
    TRAILING_PUNCTUATION,
)
```

### 2. `ContextReference` Class

```python
class ContextReference():
```

**Class Variables:**
- `raw: str`
- `kind: str`
- `target: str`
- `start: int`
- `end: int`
- `line_start: int | None`
- `line_end: int | None`

### 3. `ContextReferenceResult` Class

```python
class ContextReferenceResult():
```

**Class Variables:**
- `message: str`
- `original_message: str`
- `references: list[ContextReference]`
- `warnings: list[str]`
- `injected_tokens: int`
- `expanded: bool`
- `blocked: bool`

### 4. `parse_context_references` Function

```python
def parse_context_references(message: str) -> list[ContextReference]:
```

**Parameters:**
- `message: str`

**Returns:** `list[ContextReference]`

### 5. `preprocess_context_references` Function

```python
def preprocess_context_references(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None = None, allowed_root: str | Path | None = None) -> ContextReferenceResult:
```

**Parameters:**
- `message: str`
- `cwd: str | Path`
- `context_length: int`
- `url_fetcher: Callable[[str], str | Awaitable[str]] | None = None`
- `allowed_root: str | Path | None = None`

**Returns:** `ContextReferenceResult`

### 6. `preprocess_context_references_async` Function

```python
async def preprocess_context_references_async(message: str, cwd: str | Path, context_length: int, url_fetcher: Callable[[str], str | Awaitable[str]] | None = None, allowed_root: str | Path | None = None) -> ContextReferenceResult:
```

**Parameters:**
- `message: str`
- `cwd: str | Path`
- `context_length: int`
- `url_fetcher: Callable[[str], str | Awaitable[str]] | None = None`
- `allowed_root: str | Path | None = None`

**Returns:** `ContextReferenceResult`

### 7. Constants and Configuration

```python
REFERENCE_PATTERN = re.compile(
    r"(?<![\w/])@(?:(?P<simple>diff|staged)\b|(?P<kind>file|folder|git|url):(?P<value>\S+))"
)
TRAILING_PUNCTUATION = ",.;!?"
_SENSITIVE_HOME_DIRS = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".azure", ".config/gh")
_SENSITIVE_HERMES_DIRS = (Path("skills") / ".hub",)
_SENSITIVE_HOME_FILES = ...  # 327 chars
```

## Implementation Notes

### Node 1: Reference Parsing with REFERENCE_PATTERN

The `parse_context_references()` function uses the `REFERENCE_PATTERN` regex to identify context references in messages. The pattern matches:
- Simple references: `@diff` and `@staged` (matched by `simple` group)
- Typed references: `@kind:value` where kind is one of `file`, `folder`, `git`, or `url` (matched by `kind` and `value` groups)
- The pattern explicitly ignores email addresses (negative lookbehind `(?<![\w/])`) and handles mentions like `@teammate`

Each matched reference produces a `ContextReference` with:
- `raw`: the original matched text
- `kind`: the reference type (e.g., "file", "diff", "staged", "git", "url")
- `target`: the extracted value (e.g., filename, URL, git commit)
- `start`, `end`: character positions in the original message
- `line_start`, `line_end`: optional line range for file references (parsed from `filename:start-end` syntax)

### Node 2: Trailing Punctuation Stripping

The `_strip_trailing_punctuation()` function removes characters from `TRAILING_PUNCTUATION` (",.;!?") from the end of extracted reference targets. This allows references like `@file:README.md,` or `@url:https://example.com/docs).` to be correctly parsed as `README.md` and `https://example.com/docs` respectively.

### Node 3: Reference Expansion and Message Reconstruction

The `preprocess_context_references()` and `preprocess_context_references_async()` functions:
- Parse references from the input message
- Expand each reference by calling `_expand_reference()` (or its async variant)
- Remove reference tokens from the original message using `_remove_reference_tokens()`
- Append expanded content under a "--- Attached Context ---" section
- Return a `ContextReferenceResult` containing:
  - `message`: the modified message with references removed and content appended
  - `original_message`: the unmodified input
  - `references`: list of parsed `ContextReference` objects
  - `warnings`: list of warning strings (e.g., for binary files, missing files, budget overages)
  - `injected_tokens`: count of tokens added from expanded content
  - `expanded`: boolean indicating whether any references were successfully expanded
  - `blocked`: boolean indicating whether expansion was blocked (hard budget exceeded)

### Node 4: File Reference Expansion

The `_expand_file_reference()` function:
- Resolves the target path relative to `cwd` using `_resolve_path()`
- Validates the path is allowed using `_ensure_reference_path_allowed()`
- Returns `(None, warning_message)` if the file is binary (detected by `_is_binary_file()`)
- Returns `(None, warning_message)` if the file does not exist
- Returns `(content, metadata)` where metadata includes file size and language hint from `_file_metadata()` and `_code_fence_language()`
- Supports line ranges (e.g., `src/main.py:1-2`) to extract only specified lines

### Node 5: Folder Reference Expansion

The `_expand_folder_reference()` function:
- Resolves the target path relative to `cwd`
- Validates the path is allowed
- Builds a folder listing using `_build_folder_listing()` with a default limit of 200 entries
- Uses `_iter_visible_entries()` to list visible files (respecting `.gitignore` via `_rg_files()` when available)
- Returns `(listing_content, metadata)` or `(None, warning_message)` if the folder does not exist

### Node 6: Git Reference Expansion

The `_expand_git_reference()` function handles:
- `@diff`: runs `git diff` to show unstaged changes
- `@staged`: runs `git diff --staged` to show staged changes
- `@git:N`: runs `git log -N -p` to show the last N commits with patches
- Returns `(output, label)` from git command execution or `(None, warning_message)` on failure

### Node 7: URL Reference Expansion

The `_fetch_url_content()` function:
- Accepts an optional `url_fetcher` callable that can be sync or async
- Falls back to `_default_url_fetcher()` if no fetcher is provided
- Handles both sync and async fetchers transparently
- Returns the fetched content as a string

The `preprocess_context_references()` (sync) function can accept async fetchers and will run them using an event loop.

### Node 8: Path Resolution and Security

The `_resolve_path()` function:
- Resolves relative paths against `cwd`
- Respects `allowed_root` parameter to restrict access to a specific directory tree
- Defaults `allowed_root` to `cwd` if not specified

The `_ensure_reference_path_allowed()` function blocks access to sensitive directories:
- Home directory subdirectories: `.ssh`, `.aws`, `.gnupg`, `.kube`, `.docker`, `.azure`, `.config/gh` (from `_SENSITIVE_HOME_DIRS`)
- Hermes-specific directories: `skills/.hub` (from `_SENSITIVE_HERMES_DIRS`)
- Raises an exception if a blocked path is detected

### Node 9: Context Length Budget Management

The `context_length` parameter enforces token budgets:
- **Soft budget**: If expanded content exceeds 75% of `context_length`, a warning is added but expansion proceeds
- **Hard budget**: If expanded content would exceed `context_length`, expansion is blocked entirely and `blocked=True` is set in the result
- `injected_tokens` tracks the actual token count of injected content

### Node 10: Binary File Detection

The `_is_binary_file()` function identifies binary files to prevent their inclusion in context. When a binary file is referenced, a warning is generated and the file content is not expanded.

### Node 11: Code Fence Language Detection

The `_code_fence_language()` function determines the appropriate language identifier for markdown code fences based on file extension, enabling syntax highlighting in the expanded content.