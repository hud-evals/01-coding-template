# hermes-file-operations-large-e2e

## Overview

**hermes-file-operations-large-e2e** is a Python library that abstracts file manipulation operations across heterogeneous execution environments. The library provides a unified interface for read, write, patch, and search operations that transparently execute against multiple terminal backends, including local shells, Docker containers, Singularity containers, SSH connections, Modal functions, and Daytona instances. By expressing all file operations as shell commands, the library leverages the underlying terminal backend's command execution capabilities, enabling consistent file handling semantics regardless of the target execution environment.

The library is implemented as a single source module (`file_operations`) containing 9 classes and 2 module-level functions, totaling 1,082 lines of code. This focused design provides a cohesive abstraction layer for file operations without introducing unnecessary complexity. The module-level functions serve as entry points or utility helpers, while the class hierarchy encapsulates the distinct file operation types and their environment-specific implementations. This architecture ensures that users can perform file manipulations through a consistent API while the library handles the translation to appropriate shell commands for each backend.

The core design principle—that file operations reduce to shell command execution—allows the library to achieve backend agnosticity without duplicating logic across different execution environments. This approach minimizes maintenance burden and ensures that new terminal backends can be supported by implementing the terminal interface rather than reimplementing file operation logic.

# Natural Language Instructions for Rebuilding hermes-file-operations-large-e2e

## Implementation Constraints

- **Single module file**: All code must live in `/home/ubuntu/workspace/file_operations.py`
- **No external private packages**: Recreate all needed behavior locally using only standard library and common packages
- **Exact signatures**: Use the function/method signatures provided verbatim—do not rename parameters or change defaults
- **Dataclass design**: Use `@dataclass` decorator for all result types; implement `to_dict()` methods that omit `None` values and empty lists
- **Shell-based operations**: All file operations are implemented via shell commands executed through a terminal backend
- **Write protection**: Implement deny-list checking for sensitive paths like `~/.ssh/`, `~/.aws/`, `~/.kube/`, `~/.netrc`

---

## Behavioral Requirements

### 1. Module-Level Constants and Functions

1. Define `IMAGE_EXTENSIONS` as a set containing `{'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}`.
2. Define `MAX_LINES = 2000` and `MAX_LINE_LENGTH = 2000` as module-level constants.
3. Define `MAX_FILE_SIZE = 50 * 1024` (50 KB) as the maximum file size for reading.
4. Implement `_get_safe_write_root() -> Optional[str]` that returns the resolved path from the `HERMES_WRITE_SAFE_ROOT` environment variable, or `None` if unset.
5. Implement `_is_write_denied(path: str) -> bool` that:
   - Expands tilde (`~`) and `~user` paths to absolute home directory paths
   - Returns `True` if the path matches any of these deny patterns:
     - `~/.ssh/authorized_keys`
     - `~/.ssh/id_rsa` (and other SSH key files)
     - `~/.netrc`
     - `~/.aws/*` (any file under `.aws/`)
     - `~/.kube/*` (any file under `.kube/`)
   - Returns `False` for all other paths
   - Uses case-sensitive path matching

### 2. Result Dataclasses

6. Implement `ReadResult` as a dataclass with fields:
   - `content: str` (default `""`)
   - `total_lines: int` (default `0`)
   - `file_size: int` (default `0`)
   - `truncated: bool` (default `False`)
   - `hint: Optional[str]` (default `None`)
   - `is_binary: bool` (default `False`)
   - `is_image: bool` (default `False`)
   - `base64_content: Optional[str]` (default `None`)
   - `mime_type: Optional[str]` (default `None`)
   - `dimensions: Optional[str]` (default `None`)
   - `error: Optional[str]` (default `None`)
   - `similar_files: List[str]` (default `[]`)
   - Implement `to_dict(self) -> dict` that returns a dictionary with all non-None fields and non-empty lists; omit fields with `None` values and empty lists

7. Implement `WriteResult` as a dataclass with fields:
   - `bytes_written: int` (default `0`)
   - `dirs_created: bool` (default `False`)
   - `error: Optional[str]` (default `None`)
   - `warning: Optional[str]` (default `None`)
   - Implement `to_dict(self) -> dict` that omits `None` values

8. Implement `PatchResult` as a dataclass with fields:
   - `success: bool` (default `False`)
   - `diff: str` (default `""`)
   - `files_modified: List[str]` (default `[]`)
   - `files_created: List[str]` (default `[]`)
   - `files_deleted: List[str]` (default `[]`)
   - `lint: Optional[Dict[str, Any]]` (default `None`)
   - `error: Optional[str]` (default `None`)
   - Implement `to_dict(self) -> dict` that omits `None` values and empty lists

9. Implement `SearchMatch` as a dataclass with fields:
   - `path: str`
   - `line_number: int` (default `0`)
   - `content: str` (default `""`)
   - `mtime: float` (default `0.0`)

10. Implement `SearchResult` as a dataclass with fields:
    - `matches: List[SearchMatch]` (default `[]`)
    - `files: List[str]` (default `[]`)
    - `counts: Dict[str, int]` (default `{}`)
    - `total_count: int` (default `0`)
    - `truncated: bool` (default `False`)
    - `error: Optional[str]` (default `None`)
    - Implement `to_dict(self) -> dict` that:
      - Omits `matches` if the list is empty
      - Omits `files` if the list is empty
      - Omits `counts` if the dict is empty
      - Omits `error` if `None`
      - Always includes `total_count` and `truncated`
      - Converts each `SearchMatch` in `matches` to a dict

11. Implement `LintResult` as a dataclass with fields:
    - `success: bool` (default `False`)
    - `skipped: bool` (default `False`)
    - `output: str` (default `""`)
    - `message: str` (default `""`)
    - Implement `to_dict(self) -> dict` that:
      - Maps `success=True` to `"status": "ok"`
      - Maps `skipped=True` to `"status": "skipped"`
      - Maps `success=False` to `"status": "error"`
      - Includes `message` and `output` fields
      - Omits `None` values

12. Implement `ExecuteResult` as a dataclass with fields:
    - `stdout: str`
    - `exit_code: int`

### 3. Abstract Base Class

13. Implement `FileOperations` as an abstract base class with abstract methods:
    - `read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult`
    - `write_file(self, path: str, content: str) -> WriteResult`
    - `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult`
    - `patch_v4a(self, patch_content: str) -> PatchResult`
    - `search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult`

### 4. ShellFileOperations Implementation

14. Implement `ShellFileOperations` as a concrete subclass of `FileOperations` with:
    - `__init__(self, terminal_env, cwd: str = None)` that:
      - Stores `terminal_env` as `self.terminal_env`
      - Sets `self.cwd` to the provided `cwd` parameter, or falls back to `terminal_env.cwd` if available, or `"/"` if neither is provided
      - Initializes an empty dict `self._command_cache` for caching command availability checks

15. Implement `_exec(self, command: str, cwd: str = None, timeout: int = None, stdin_data: str = None) -> ExecuteResult` that:
    - Calls `self.terminal_env.execute(command, cwd=cwd, timeout=timeout, stdin_data=stdin_data)`
    - Extracts `stdout` from the result (or empty string if missing)
    - Extracts `exit_code` from the result (or `returncode` field as fallback)
    - Returns an `ExecuteResult` with the extracted values

16. Implement `_has_command(self, cmd: str) -> bool` that:
    - Checks `self._command_cache` first and returns cached result if present
    - Executes `command -v {cmd}` to check if the command exists
    - Caches the result (True if exit code is 0, False otherwise)
    - Returns the boolean result

17. Implement `_is_likely_binary(self, path: str, content_sample: str = None) -> bool` that:
    - Returns `True` if the file extension is in a known binary set (`.pyc`, `.so`, `.o`, `.a`, `.exe`, `.dll`, `.bin`, `.db`, `.sqlite`, `.zip`, `.tar`, `.gz`, `.jpg`, `.png`, `.gif`, `.pdf`, `.doc`, `.xls`, etc.)
    - If `content_sample` is provided, analyzes the content:
      - Counts non-printable characters (bytes < 32 or > 126, excluding common whitespace like `\n`, `\r`, `\t`)
      - Returns `True` if the ratio of non-printable chars exceeds ~30% of the sample
    - Returns `False` otherwise

18. Implement `_is_image(self, path: str) -> bool` that:
    - Returns `True` if the file extension (lowercased) is in `IMAGE_EXTENSIONS`
    - Returns `False` otherwise

19. Implement `_add_line_numbers(self, content: str, start_line: int = 1) -> str` that:
    - Splits content by newlines
    - For each line, prepends a right-aligned line number followed by `|` and the content
    - Line numbers are formatted with 5-character width (right-aligned)
    - If a line exceeds `MAX_LINE_LENGTH`, truncate it and append `[truncated]`
    - Joins lines back with newlines
    - Returns the formatted string

20. Implement `_expand_path(self, path: str) -> str` that:
    - Expands `~` to the current user's home directory
    - Expands `~username` to that user's home directory
    - Returns the expanded absolute path

21. Implement `_escape_shell_arg(self, arg: str) -> str` that:
    - Wraps the argument in single quotes for shell safety
    - Escapes any single quotes within the argument by replacing `'` with `'\''` (end quote, escaped quote, start quote)
    - Returns the safely escaped string

22. Implement `_unified_diff(self, old_content: str, new_content: str, filename: str) -> str` that:
    - Generates a unified diff format between old and new content
    - Includes the filename in the diff header
    - Returns the diff as a string (can use Python's `difflib.unified_diff`)

23. Implement `read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult` that:
    - Expands the path using `_expand_path()`
    - Checks if the file exists; if not, calls `_suggest_similar_files()` and returns that result
    - Reads the file content using shell commands (e.g., `cat`)
    - Detects if the file is binary using `_is_likely_binary()`
    - If binary and is an image, encodes as base64 and sets `base64_content`
    - Counts total lines in the file
    - Implements pagination: returns lines from `offset` to `offset + limit`
    - Sets `truncated=True` if there are more lines beyond the limit
    - Adds line numbers to the returned content using `_add_line_numbers()`
    - Returns a `ReadResult` with all relevant fields populated

24. Implement `_suggest_similar_files(self, path: str) -> ReadResult` that:
    - When a file is not found, searches for similar filenames in the same directory
    - Uses shell commands (e.g., `find` or `ls`) to locate files with similar names
    - Returns a `ReadResult` with `error` set and `similar_files` populated with up to 5 suggestions

25. Implement `write_file(self, path: str, content: str) -> WriteResult` that:
    - Checks if the path is write-denied using `_is_write_denied()`; if so, return error
    - Expands the path using `_expand_path()`
    - Creates parent directories as needed using `mkdir -p`
    - Writes the content to the file using shell commands (e.g., `cat > file`)
    - Tracks the number of bytes written
    - Tracks whether directories were created
    - Returns a `WriteResult` with all relevant fields

26. Implement `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult` that:
    - Checks if the path is write-denied; if so, return error
    - Reads the current file content
    - Performs fuzzy string matching to find `old_string` in the content (allows for minor whitespace differences)
    - Replaces the first occurrence (or all occurrences if `replace_all=True`)
    - Generates a unified diff using `_unified_diff()`
    - Writes the modified content back to the file
    - Runs `_check_lint()` on the file after modification
    - Returns a `PatchResult` with the diff, modified files list, and lint results

27. Implement `patch_v4a(self, patch_content: str) -> PatchResult` that:
    - Parses V4A format patch content (a specific patch format)
    - Applies the patch to the specified files
    - Returns a `PatchResult` with success/error status and list of modified files

28. Implement `_check_lint(self, path: str) -> LintResult` that:
    - Determines the file type from the extension
    - Runs appropriate linter (e.g., `python -m py_compile` for `.py`, `node --check` for `.js`, etc.)
    - Returns a `LintResult` with:
      - `success=True` if linting passes
      - `success=False` if linting fails
      - `skipped=True` if no linter is available for the file type
      - `output` containing linter output
      - `message` containing a summary message

29. Implement `search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult` that:
    - Validates that the `path` exists; if not, returns error
    - Routes to `_search_files()` if `target == "files"`
    - Routes to `_search_content()` if `target == "content"`
    - Returns a `SearchResult` with matches, file list, counts, and truncation status

30. Implement `_search_files(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult` that:
    - Searches for files matching a glob-like pattern
    - Uses `find` or `ls` commands to locate files
    - Returns a `SearchResult` with the `files` list populated
    - Implements pagination using `limit` and `offset`

31. Implement `_search_files_rg(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult` that:
    - Uses `ripgrep --files` mode to search for files
    - Filters results by the pattern
    - Returns a `SearchResult` with the `files` list

32. Implement `_search_content(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Searches for content inside files
    - Respects the `file_glob` parameter to filter which files to search
    - Implements pagination using `limit` and `offset`
    - Supports different `output_mode` values (e.g., `"content"`, `"count"`)
    - Includes context lines around matches if `context > 0`
    - Returns a `SearchResult` with `matches` populated

33. Implement `_search_with_rg(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Uses `ripgrep` (rg) for fast content searching
    - Handles exit codes:
      - Exit code 0: matches found
      - Exit code 1: no matches found (not an error)
      - Exit code 2: error condition (return error in result)
    - Parses ripgrep output to extract file paths, line numbers, and content
    - Returns a `SearchResult` with matches

34. Implement `_search_with_grep(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Uses `grep` as a fallback when ripgrep is not available
    - Parses grep output to extract matches
    - Returns a `SearchResult` with matches

---

## Implementation Notes

- **Terminal Backend Integration**: The `terminal_env` parameter is an object with an `execute()` method that runs shell commands. Adapt all file operations to use this interface.
- **Error Handling**: All methods should gracefully handle missing files, permission errors, and command failures by returning appropriate result objects with error messages.
- **Performance**: Use efficient shell commands (prefer `ripgrep` over `grep` when available) and implement caching for command availability checks.
- **Path Handling**: Always expand paths using `_expand_path()` before executing shell commands to handle tilde expansion correctly.
- **Dataclass Defaults**: Use `field(default_factory=...)` for mutable defaults (lists, dicts) in dataclasses.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `class ReadResult`
- `def ReadResult.to_dict(self) -> dict`
- `class WriteResult`
- `def WriteResult.to_dict(self) -> dict`
- `class PatchResult`
- `def PatchResult.to_dict(self) -> dict`
- `class SearchMatch`
- `class SearchResult`
- `def SearchResult.to_dict(self) -> dict`
- `class LintResult`
- `def LintResult.to_dict(self) -> dict`
- `def FileOperations.write_file(self, path: str, content: str) -> WriteResult`
- `def FileOperations.patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult`
- `def FileOperations.search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult`
- `class ShellFileOperations`
- `def ShellFileOperations._is_likely_binary(self, path: str, content_sample: str = None) -> bool`
- `def ShellFileOperations._is_image(self, path: str) -> bool`
- `def ShellFileOperations._add_line_numbers(self, content: str, start_line: int = 1) -> str`
- `def ShellFileOperations._escape_shell_arg(self, arg: str) -> str`
- `def ShellFileOperations._unified_diff(self, old_content: str, new_content: str, filename: str) -> str`
- `def ShellFileOperations.write_file(self, path: str, content: str) -> WriteResult`
- `def ShellFileOperations.patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult`
- `def ShellFileOperations.search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult`
- `def _is_write_denied(path: str) -> bool`
- `MAX_LINE_LENGTH`

## Environment Configuration

### Python Version

Python >=3.11

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `file_operations.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `hermes_constants`: repo-private constants or lightweight helper values; the original code imported `get_hermes_home` from `hermes_constants`. Recreate the needed behavior locally.
- `tools.binary_extensions`: repo-private constants or lightweight helper values; the original code imported `BINARY_EXTENSIONS` from `tools.binary_extensions`. Recreate the needed behavior locally.
- `tools.fuzzy_match`: repo-private helper module; the original code imported `fuzzy_find_and_replace` from `tools.fuzzy_match`. Recreate the needed behavior locally.
- `tools.patch_parser`: repo-private helper module; the original code imported `apply_v4a_operations`, `parse_v4a_patch` from `tools.patch_parser`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── file_operations.py
```

## API Usage Guide

### 1. Module Import

```python
from file_operations import (
    ReadResult,
    WriteResult,
    PatchResult,
    SearchMatch,
    SearchResult,
    LintResult,
    ExecuteResult,
    FileOperations,
    ShellFileOperations,
    WRITE_DENIED_PATHS,
    WRITE_DENIED_PREFIXES,
    IMAGE_EXTENSIONS,
    LINTERS,
    MAX_LINES,
    MAX_LINE_LENGTH,
    MAX_FILE_SIZE,
)
```

### 2. `ReadResult` Class

Result from reading a file.

```python
class ReadResult():
    """Result from reading a file."""
```

**Class Variables:**
- `content: str`
- `total_lines: int`
- `file_size: int`
- `truncated: bool`
- `hint: Optional[str]`
- `is_binary: bool`
- `is_image: bool`
- `base64_content: Optional[str]`
- `mime_type: Optional[str]`
- `dimensions: Optional[str]`
- `error: Optional[str]`
- `similar_files: List[str]`


```python
def to_dict(self) -> dict:
```

**Returns:** `dict`

### 3. `WriteResult` Class

Result from writing a file.

```python
class WriteResult():
    """Result from writing a file."""
```

**Class Variables:**
- `bytes_written: int`
- `dirs_created: bool`
- `error: Optional[str]`
- `warning: Optional[str]`


```python
def to_dict(self) -> dict:
```

**Returns:** `dict`

### 4. `PatchResult` Class

Result from patching a file.

```python
class PatchResult():
    """Result from patching a file."""
```

**Class Variables:**
- `success: bool`
- `diff: str`
- `files_modified: List[str]`
- `files_created: List[str]`
- `files_deleted: List[str]`
- `lint: Optional[Dict[str, Any]]`
- `error: Optional[str]`


```python
def to_dict(self) -> dict:
```

**Returns:** `dict`

### 5. `SearchMatch` Class

A single search match.

```python
class SearchMatch():
    """A single search match."""
```

**Class Variables:**
- `path: str`
- `line_number: int`
- `content: str`
- `mtime: float`

### 6. `SearchResult` Class

Result from searching.

```python
class SearchResult():
    """Result from searching."""
```

**Class Variables:**
- `matches: List[SearchMatch]`
- `files: List[str]`
- `counts: Dict[str, int]`
- `total_count: int`
- `truncated: bool`
- `error: Optional[str]`


```python
def to_dict(self) -> dict:
```

**Returns:** `dict`

### 7. `LintResult` Class

Result from linting a file.

```python
class LintResult():
    """Result from linting a file."""
```

**Class Variables:**
- `success: bool`
- `skipped: bool`
- `output: str`
- `message: str`


```python
def to_dict(self) -> dict:
```

**Returns:** `dict`

### 8. `ExecuteResult` Class

Result from executing a shell command.

```python
class ExecuteResult():
    """Result from executing a shell command."""
```

**Class Variables:**
- `stdout: str`
- `exit_code: int`

### 9. `FileOperations` Class

Abstract interface for file operations across terminal backends.

**Bases:** `ABC`

```python
class FileOperations(ABC):
    """Abstract interface for file operations across terminal backends."""
```


Read a file with pagination support.

```python
def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult:
```

**Parameters:**
- `path: str`
- `offset: int = 1`
- `limit: int = 500`

**Returns:** `ReadResult`

**Decorators:** `abstractmethod`


Write content to a file, creating directories as needed.

```python
def write_file(self, path: str, content: str) -> WriteResult:
```

**Parameters:**
- `path: str`
- `content: str`

**Returns:** `WriteResult`

**Decorators:** `abstractmethod`


Replace text in a file using fuzzy matching.

```python
def patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult:
```

**Parameters:**
- `path: str`
- `old_string: str`
- `new_string: str`
- `replace_all: bool = False`

**Returns:** `PatchResult`

**Decorators:** `abstractmethod`


Apply a V4A format patch.

```python
def patch_v4a(self, patch_content: str) -> PatchResult:
```

**Parameters:**
- `patch_content: str`

**Returns:** `PatchResult`

**Decorators:** `abstractmethod`


Search for content or files.

```python
def search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str = "."`
- `target: str = "content"`
- `file_glob: Optional[str] = None`
- `limit: int = 50`
- `offset: int = 0`
- `output_mode: str = "content"`
- `context: int = 0`

**Returns:** `SearchResult`

**Decorators:** `abstractmethod`

### 10. `ShellFileOperations` Class

File operations implemented via shell commands.

Works with ANY terminal backend that has execute(command, cwd) method.
This includes local, docker, singularity, ssh, modal, and daytona environments.

**Bases:** `FileOperations`

```python
class ShellFileOperations(FileOperations):
    """File operations implemented via shell commands."""
```


Initialize file operations with a terminal environment.

Args:
    terminal_env: Any object with execute(command, cwd) method.
                 Returns {"output": str, "returncode": int}
    cwd: Working directory (defaults to env's cwd or current directory)

```python
def __init__(self, terminal_env, cwd: str = None):
```

**Parameters:**
- `terminal_env`
- `cwd: str = None`


Execute command via terminal backend.

Args:
    stdin_data: If provided, piped to the process's stdin instead of
                embedding in the command string. Bypasses ARG_MAX.

```python
def _exec(self, command: str, cwd: str = None, timeout: int = None, stdin_data: str = None) -> ExecuteResult:
```

**Parameters:**
- `command: str`
- `cwd: str = None`
- `timeout: int = None`
- `stdin_data: str = None`

**Returns:** `ExecuteResult`


Check if a command exists in the environment (cached).

```python
def _has_command(self, cmd: str) -> bool:
```

**Parameters:**
- `cmd: str`

**Returns:** `bool`


Check if a file is likely binary.

Uses extension check (fast) + content analysis (fallback).

```python
def _is_likely_binary(self, path: str, content_sample: str = None) -> bool:
```

**Parameters:**
- `path: str`
- `content_sample: str = None`

**Returns:** `bool`


Check if file is an image we can return as base64.

```python
def _is_image(self, path: str) -> bool:
```

**Parameters:**
- `path: str`

**Returns:** `bool`


Add line numbers to content in LINE_NUM|CONTENT format.

```python
def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
```

**Parameters:**
- `content: str`
- `start_line: int = 1`

**Returns:** `str`


Expand shell-style paths like ~ and ~user to absolute paths.

This must be done BEFORE shell escaping, since ~ doesn't expand
inside single quotes.

```python
def _expand_path(self, path: str) -> str:
```

**Parameters:**
- `path: str`

**Returns:** `str`


Escape a string for safe use in shell commands.

```python
def _escape_shell_arg(self, arg: str) -> str:
```

**Parameters:**
- `arg: str`

**Returns:** `str`


Generate unified diff between old and new content.

```python
def _unified_diff(self, old_content: str, new_content: str, filename: str) -> str:
```

**Parameters:**
- `old_content: str`
- `new_content: str`
- `filename: str`

**Returns:** `str`


Read a file with pagination, binary detection, and line numbers.

Args:
    path: File path (absolute or relative to cwd)
    offset: Line number to start from (1-indexed, default 1)
    limit: Maximum lines to return (default 500, max 2000)

Returns:
    ReadResult with content, metadata, or error info

```python
def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult:
```

**Parameters:**
- `path: str`
- `offset: int = 1`
- `limit: int = 500`

**Returns:** `ReadResult`


Suggest similar files when the requested file is not found.

```python
def _suggest_similar_files(self, path: str) -> ReadResult:
```

**Parameters:**
- `path: str`

**Returns:** `ReadResult`


Write content to a file, creating parent directories as needed.

Pipes content through stdin to avoid OS ARG_MAX limits on large
files. The content never appears in the shell command string —
only the file path does.

Args:
    path: File path to write
    content: Content to write

Returns:
    WriteResult with bytes written or error

```python
def write_file(self, path: str, content: str) -> WriteResult:
```

**Parameters:**
- `path: str`
- `content: str`

**Returns:** `WriteResult`


Replace text in a file using fuzzy matching.

Args:
    path: File path to modify
    old_string: Text to find (must be unique unless replace_all=True)
    new_string: Replacement text
    replace_all: If True, replace all occurrences

Returns:
    PatchResult with diff and lint results

```python
def patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult:
```

**Parameters:**
- `path: str`
- `old_string: str`
- `new_string: str`
- `replace_all: bool = False`

**Returns:** `PatchResult`


Apply a V4A format patch.

V4A format:
    *** Begin Patch
    *** Update File: path/to/file.py
    @@ context hint @@
     context line
    -removed line
    +added line
    *** End Patch

Args:
    patch_content: V4A format patch string

Returns:
    PatchResult with changes made

```python
def patch_v4a(self, patch_content: str) -> PatchResult:
```

**Parameters:**
- `patch_content: str`

**Returns:** `PatchResult`


Run syntax check on a file after editing.

Args:
    path: File path to lint

Returns:
    LintResult with status and any errors

```python
def _check_lint(self, path: str) -> LintResult:
```

**Parameters:**
- `path: str`

**Returns:** `LintResult`


Search for content or files.

Args:
    pattern: Regex (for content) or glob pattern (for files)
    path: Directory/file to search (default: cwd)
    target: "content" (grep) or "files" (glob)
    file_glob: File pattern filter for content search (e.g., "*.py")
    limit: Max results (default 50)
    offset: Skip first N results
    output_mode: "content", "files_only", or "count"
    context: Lines of context around matches

Returns:
    SearchResult with matches or file list

```python
def search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str = "."`
- `target: str = "content"`
- `file_glob: Optional[str] = None`
- `limit: int = 50`
- `offset: int = 0`
- `output_mode: str = "content"`
- `context: int = 0`

**Returns:** `SearchResult`


Search for files by name pattern (glob-like).

```python
def _search_files(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str`
- `limit: int`
- `offset: int`

**Returns:** `SearchResult`


Search for files by name using ripgrep's --files mode.

rg --files respects .gitignore and excludes hidden directories by
default, and uses parallel directory traversal for ~200x speedup
over find on wide trees.

```python
def _search_files_rg(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str`
- `limit: int`
- `offset: int`

**Returns:** `SearchResult`


Search for content inside files (grep-like).

```python
def _search_content(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str`
- `file_glob: Optional[str]`
- `limit: int`
- `offset: int`
- `output_mode: str`
- `context: int`

**Returns:** `SearchResult`


Search using ripgrep.

```python
def _search_with_rg(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str`
- `file_glob: Optional[str]`
- `limit: int`
- `offset: int`
- `output_mode: str`
- `context: int`

**Returns:** `SearchResult`


Fallback search using grep.

```python
def _search_with_grep(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult:
```

**Parameters:**
- `pattern: str`
- `path: str`
- `file_glob: Optional[str]`
- `limit: int`
- `offset: int`
- `output_mode: str`
- `context: int`

**Returns:** `SearchResult`

### 11. Constants and Configuration

```python
_HOME = str(Path.home())
WRITE_DENIED_PATHS = ...  # 722 chars
WRITE_DENIED_PREFIXES = ...  # 379 chars
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}
LINTERS = ...  # 207 chars
MAX_LINES = 2000
MAX_LINE_LENGTH = 2000
MAX_FILE_SIZE = 50 * 1024
```

## Implementation Notes

### Node 1: Write Protection and Security

The library implements a write deny list to prevent modification of sensitive files. The `_is_write_denied(path: str) -> bool` function returns `True` for paths matching protected patterns:
- `~/.ssh/authorized_keys`
- `~/.ssh/id_rsa`
- `~/.netrc`
- `~/.aws/credentials`
- `~/.kube/config`

The function expands tilde (`~`) to the home directory using `_HOME = str(Path.home())` before checking deny patterns. The `write_file()` method checks this function and returns a `WriteResult` with an error message (containing "denied") if the path is protected.

### Node 2: Binary and Image File Detection

`_is_likely_binary(path: str, content_sample: str = None) -> bool` determines if a file is binary by:
- Checking file extension against known binary types (e.g., `.png`, `.db`)
- If no extension match, analyzing content sample for high ratio of non-printable characters

`_is_image(path: str) -> bool` returns `True` only for files with extensions in `IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}`.

### Node 3: Line Number Formatting

`_add_line_numbers(content: str, start_line: int = 1) -> str` formats output as `LINE_NUM|CONTENT` where:
- Line numbers are right-aligned in a 5-character field (e.g., `     1|`, `    50|`)
- Individual lines exceeding `MAX_LINE_LENGTH = 2000` are truncated with `[truncated]` appended
- The `start_line` parameter allows pagination offset (default 1)

### Node 4: Path Expansion and Shell Escaping

`_expand_path(path: str) -> str` expands shell-style paths including `~` and `~user` notation to absolute paths.

`_escape_shell_arg(arg: str) -> str` wraps arguments in single quotes for safe shell execution. Arguments containing single quotes are escaped with multiple quote characters (minimum 4 quote characters total for strings like `"it's"`).

### Node 5: Diff Generation

`_unified_diff(old_content: str, new_content: str, filename: str) -> str` generates unified diff format output containing:
- Lines prefixed with `-` for deletions
- Lines prefixed with `+` for additions
- The filename in the diff header

### Node 6: ReadResult Serialization

`ReadResult.to_dict()` omits fields with default/empty values:
- `None` values are omitted (e.g., `error`, `hint`, `base64_content`, `mime_type`, `dimensions`)
- Empty lists are omitted (e.g., `similar_files`)
- Non-empty or non-default values are always included, even if falsy (e.g., empty string `content=""` is preserved, `truncated=False` is included)

### Node 7: WriteResult Serialization

`WriteResult.to_dict()` omits `None` values for `error` and `warning` fields. The `bytes_written` and `dirs_created` fields are always included when set.

### Node 8: PatchResult Serialization

`PatchResult.to_dict()` includes:
- `success` field (boolean)
- `diff` string
- File lists: `files_modified`, `files_created`, `files_deleted`
- `lint` dict if present
- `error` if present
- When `error` is set, `success` defaults to `False`

### Node 9: SearchMatch and SearchResult Serialization

`SearchMatch` contains `path`, `line_number`, `content`, and `mtime` fields.

`SearchResult.to_dict()` behavior:
- Omits `matches` list if empty
- Omits `files` list if empty
- Omits `counts` dict if empty
- Always includes `total_count` (defaults to 0)
- Includes `truncated` flag when `True`
- Includes `error` if present

### Node 10: LintResult Serialization

`LintResult.to_dict()` maps status to a `"status"` key:
- `skipped=True` → `"status": "skipped"`
- `success=True` → `"status": "ok"`
- `success=False` → `"status": "error"`

Always includes `message` and `output` fields.

### Node 11: Search Path Validation

The `search()` method validates that the search path exists before proceeding. It uses `test -e <path>` to check existence. If the path does not exist (returncode 1), the method returns a `SearchResult` with an error message. This applies to both `target="content"` and `target="files"` modes.

### Node 12: Search Error Handling

When ripgrep (rg) returns exit code 2 (error condition), the search result includes an error message. Exit code 1 (no matches found) is treated as success with zero matches, not an error.

### Node 13: ShellFileOperations Initialization

`ShellFileOperations.__init__(terminal_env, cwd: str = None)` initializes with:
- A `terminal_env` object for command execution
- Optional `cwd` parameter; if not provided, attempts to read `terminal_env.cwd`
- Falls back to `"/"` if `terminal_env` has no `cwd` attribute

### Node 14: File Reading Constraints

`read_file(path: str, offset: int = 1, limit: int = 500)` respects:
- `MAX_LINES = 2000` total lines per file
- `MAX_FILE_SIZE = 50 * 1024` bytes (50 KB)
- `MAX_LINE_LENGTH = 2000` characters per line
- `offset` parameter for pagination (1-indexed line number)
- `limit` parameter for number of lines to return (default 500)
- Sets `truncated=True` in `ReadResult` when file exceeds limits

### Node 15: Command Execution Interface

`_exec(command: str, cwd: str = None, timeout: int = None, stdin_data: str = None) -> ExecuteResult` executes shell commands via the terminal backend and returns `ExecuteResult` with `stdout` and `exit_code` fields. The `cwd` parameter overrides the instance's default working directory.