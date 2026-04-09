# file-operations

## Overview

**file-operations** is a Python library comprising 1,082 lines of code organized into a single source module that provides unified file manipulation capabilities across heterogeneous execution environments. The library abstracts file operations—including read, write, patch, and search functionality—into a consistent interface that transparently works across multiple terminal backends: local shell execution, Docker containers, Singularity containers, SSH remote hosts, Modal cloud functions, and Daytona development environments. The architectural foundation leverages a key design principle: all file operations are expressible as shell commands, enabling the library to delegate execution to the underlying terminal backend's command execution layer rather than implementing environment-specific logic.

The module exports 9 classes and 2 module-level functions, providing both object-oriented and functional interfaces for file manipulation tasks. This structure allows developers to perform file operations without requiring knowledge of the specific execution environment, as the library transparently translates high-level file operation requests into appropriate shell commands for the active terminal backend. The single-module design maintains a cohesive API surface while encapsulating the complexity of multi-backend command generation and execution.

By standardizing file operations across diverse execution contexts—from local filesystems to containerized and remote environments—file-operations eliminates the need for environment-specific file handling code, reducing implementation complexity and improving portability across different deployment scenarios.

# Natural Language Instructions for Rebuilding file-operations

## Implementation Constraints

- **Single module file**: All code must live in `/home/ubuntu/workspace/file_operations.py`
- **No external private packages**: Recreate all needed behavior using standard library and common packages
- **Exact signatures**: Use the function/method signatures provided verbatim—do not rename parameters or change defaults
- **Dataclass design**: Use `@dataclass` decorator for all result types; implement `to_dict()` methods that omit None values and empty lists
- **Shell-based operations**: All file operations are implemented by executing shell commands via a `terminal_env` backend
- **Security checks**: Implement write denial for sensitive paths (`.ssh`, `.aws`, `.kube`, `.netrc`)

---

## Behavioral Requirements

### 1. Module-Level Constants and Functions

1. Define `IMAGE_EXTENSIONS` as a set containing `{'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}`.
2. Define `MAX_LINES = 2000` and `MAX_LINE_LENGTH = 2000` as module-level constants.
3. Define `MAX_FILE_SIZE = 50 * 1024` (50 KB) as the threshold for binary file detection.
4. Implement `_get_safe_write_root() -> Optional[str]` that returns the resolved path from the `HERMES_WRITE_SAFE_ROOT` environment variable, or `None` if unset.
5. Implement `_is_write_denied(path: str) -> bool` that:
   - Expands tilde (`~`) and `~user` paths to absolute paths using `os.path.expanduser()`
   - Returns `True` if the path matches any of these patterns (case-insensitive):
     - `~/.ssh/authorized_keys`
     - `~/.ssh/id_rsa`
     - `~/.netrc`
     - `~/.aws/*` (any file under `.aws/`)
     - `~/.kube/*` (any file under `.kube/`)
   - Returns `False` for all other paths
   - Uses `pathlib.Path` for path manipulation where appropriate

### 2. Result Dataclasses

6. Implement `ReadResult` as a dataclass with fields:
   - `content: str = ""`
   - `total_lines: int = 0`
   - `file_size: int = 0`
   - `truncated: bool = False`
   - `hint: Optional[str] = None`
   - `is_binary: bool = False`
   - `is_image: bool = False`
   - `base64_content: Optional[str] = None`
   - `mime_type: Optional[str] = None`
   - `dimensions: Optional[str] = None`
   - `error: Optional[str] = None`
   - `similar_files: List[str] = field(default_factory=list)`
   - Implement `to_dict(self) -> dict` that omits keys with `None` values and empty lists, but preserves empty strings and zero values

7. Implement `WriteResult` as a dataclass with fields:
   - `bytes_written: int = 0`
   - `dirs_created: bool = False`
   - `error: Optional[str] = None`
   - `warning: Optional[str] = None`
   - Implement `to_dict(self) -> dict` that omits keys with `None` values

8. Implement `PatchResult` as a dataclass with fields:
   - `success: bool = False`
   - `diff: str = ""`
   - `files_modified: List[str] = field(default_factory=list)`
   - `files_created: List[str] = field(default_factory=list)`
   - `files_deleted: List[str] = field(default_factory=list)`
   - `lint: Optional[Dict[str, Any]] = None`
   - `error: Optional[str] = None`
   - Implement `to_dict(self) -> dict` that omits keys with `None` values and empty lists

9. Implement `SearchMatch` as a dataclass with fields:
   - `path: str`
   - `line_number: int = 0`
   - `content: str = ""`
   - `mtime: float = 0.0`

10. Implement `SearchResult` as a dataclass with fields:
    - `matches: List[SearchMatch] = field(default_factory=list)`
    - `files: List[str] = field(default_factory=list)`
    - `counts: Dict[str, int] = field(default_factory=dict)`
    - `total_count: int = 0`
    - `truncated: bool = False`
    - `error: Optional[str] = None`
    - Implement `to_dict(self) -> dict` that:
      - Omits `matches` key if the list is empty
      - Omits `files` key if the list is empty
      - Omits `counts` key if the dict is empty
      - Omits `error` key if `None`
      - Always includes `total_count` and `truncated`
      - Converts each `SearchMatch` in `matches` to a dict

11. Implement `LintResult` as a dataclass with fields:
    - `success: bool = False`
    - `skipped: bool = False`
    - `output: str = ""`
    - `message: str = ""`
    - Implement `to_dict(self) -> dict` that:
      - Maps `success=True` to `"status": "ok"`
      - Maps `skipped=True` to `"status": "skipped"`
      - Maps `success=False` to `"status": "error"`
      - Always includes `output` and `message` fields

12. Implement `ExecuteResult` as a dataclass with fields:
    - `stdout: str`
    - `exit_code: int`

### 3. FileOperations Abstract Base Class

13. Implement `FileOperations` as an abstract base class with abstract methods:
    - `read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult`
    - `write_file(self, path: str, content: str) -> WriteResult`
    - `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult`
    - `patch_v4a(self, patch_content: str) -> PatchResult`
    - `search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult`

### 4. ShellFileOperations Implementation

14. Implement `ShellFileOperations(FileOperations)` with `__init__(self, terminal_env, cwd: str = None)` that:
    - Stores `terminal_env` as an instance variable
    - Sets `self.cwd` to the provided `cwd` parameter, or falls back to `terminal_env.cwd` if available, or `"/"` if neither is provided
    - Initializes a command cache (dict) for `_has_command()` results

15. Implement `_exec(self, command: str, cwd: str = None, timeout: int = None, stdin_data: str = None) -> ExecuteResult` that:
    - Calls `terminal_env.execute(command, cwd=cwd, timeout=timeout, stdin_data=stdin_data)`
    - Extracts `stdout` and `exit_code` (or `returncode`) from the result
    - Returns an `ExecuteResult` object

16. Implement `_has_command(self, cmd: str) -> bool` that:
    - Caches results in an instance dict to avoid repeated checks
    - Uses `command -v <cmd>` to check if a command exists
    - Returns `True` if exit code is 0, `False` otherwise

17. Implement `_is_likely_binary(self, path: str, content_sample: str = None) -> bool` that:
    - Returns `True` if the file extension is in a known binary set (`.pyc`, `.so`, `.o`, `.a`, `.exe`, `.dll`, `.db`, `.sqlite`, `.zip`, `.tar`, `.gz`, `.jpg`, `.png`, `.gif`, `.pdf`, `.bin`, `.dat`)
    - If `content_sample` is provided, analyzes the content:
      - Counts non-printable characters (bytes < 32 or > 126, excluding common whitespace like `\n`, `\r`, `\t`)
      - Returns `True` if the ratio of non-printable chars exceeds 30%
    - Returns `False` by default

18. Implement `_is_image(self, path: str) -> bool` that:
    - Returns `True` if the file extension (lowercased) is in `IMAGE_EXTENSIONS`
    - Returns `False` otherwise

19. Implement `_add_line_numbers(self, content: str, start_line: int = 1) -> str` that:
    - Splits content by newlines
    - For each line, prepends a right-aligned line number (6 characters wide) followed by `|`
    - Truncates lines longer than `MAX_LINE_LENGTH` and appends `[truncated]`
    - Returns the formatted content as a single string with newlines preserved

20. Implement `_expand_path(self, path: str) -> str` that:
    - Expands `~` and `~user` using `os.path.expanduser()`
    - Expands environment variables using `os.path.expandvars()`
    - Returns the expanded path

21. Implement `_escape_shell_arg(self, arg: str) -> str` that:
    - Wraps the argument in single quotes
    - Escapes any single quotes within the argument by replacing `'` with `'\''`
    - Returns the safely escaped string

22. Implement `_unified_diff(self, old_content: str, new_content: str, filename: str) -> str` that:
    - Uses `difflib.unified_diff()` to generate a unified diff
    - Includes the filename in the diff header
    - Returns the diff as a string

23. Implement `read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult` that:
    - Expands the path using `_expand_path()`
    - Checks if the file exists; if not, calls `_suggest_similar_files()` and returns that result
    - Reads the file content using shell commands (e.g., `cat`)
    - Detects if the file is binary using `_is_likely_binary()`
    - If binary and an image, encodes as base64 and sets `base64_content` and `mime_type`
    - Counts total lines in the file
    - Implements pagination: returns lines from `offset` to `offset + limit`
    - Sets `truncated=True` if there are more lines beyond the limit
    - Adds line numbers to the returned content using `_add_line_numbers()`
    - Returns a `ReadResult` with all fields populated

24. Implement `_suggest_similar_files(self, path: str) -> ReadResult` that:
    - Uses `find` or similar to locate files with similar names in the same directory
    - Returns a `ReadResult` with `error` set and `similar_files` populated
    - Limits suggestions to a reasonable number (e.g., 5)

25. Implement `write_file(self, path: str, content: str) -> WriteResult` that:
    - Checks if the path is write-denied using `_is_write_denied()`; if so, returns an error
    - Expands the path using `_expand_path()`
    - Creates parent directories as needed using `mkdir -p`
    - Writes the content to the file using shell commands (e.g., `cat > file`)
    - Returns a `WriteResult` with `bytes_written` set to the length of the content and `dirs_created` indicating if directories were created

26. Implement `patch_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> PatchResult` that:
    - Reads the current file content
    - Performs fuzzy string matching to find the `old_string` in the content (allowing for minor whitespace differences)
    - Replaces the first occurrence (or all occurrences if `replace_all=True`)
    - Generates a unified diff using `_unified_diff()`
    - Writes the new content back to the file
    - Runs `_check_lint()` on the file after modification
    - Returns a `PatchResult` with `success=True`, the diff, and lint results

27. Implement `patch_v4a(self, patch_content: str) -> PatchResult` that:
    - Parses the V4A format patch (a specific unified diff format)
    - Extracts the filename and hunks from the patch
    - Applies the hunks to the file using fuzzy matching
    - Returns a `PatchResult` with success status and any errors

28. Implement `_check_lint(self, path: str) -> LintResult` that:
    - Detects the file type by extension
    - Runs an appropriate linter (e.g., `python -m py_compile` for `.py`, `node --check` for `.js`)
    - Returns a `LintResult` with `success=True` if no errors, or `success=False` with error output
    - Returns `skipped=True` if no linter is available for the file type

29. Implement `search(self, pattern: str, path: str = ".", target: str = "content", file_glob: Optional[str] = None, limit: int = 50, offset: int = 0, output_mode: str = "content", context: int = 0) -> SearchResult` that:
    - Validates that the `path` exists; if not, returns an error
    - Dispatches to `_search_files()` if `target == "files"`, otherwise to `_search_content()`
    - Handles `limit` and `offset` for pagination
    - Returns a `SearchResult` with matches, file list, counts, and truncation status

30. Implement `_search_files(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult` that:
    - Searches for files matching the glob pattern using `find` or `rg --files`
    - Returns a `SearchResult` with the `files` list populated

31. Implement `_search_files_rg(self, pattern: str, path: str, limit: int, offset: int) -> SearchResult` that:
    - Uses `ripgrep` (rg) with `--files` mode to search for files
    - Applies the glob pattern if provided
    - Returns a `SearchResult` with the `files` list

32. Implement `_search_content(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Dispatches to `_search_with_rg()` if ripgrep is available, otherwise to `_search_with_grep()`
    - Handles `output_mode` (e.g., "content", "count")
    - Applies `context` lines before/after matches
    - Returns a `SearchResult` with matches and counts

33. Implement `_search_with_rg(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Constructs a ripgrep command with appropriate flags
    - Handles exit codes: 0 (matches found), 1 (no matches), 2 (error)
    - Parses the output to extract file paths, line numbers, and content
    - Returns a `SearchResult` with matches and metadata

34. Implement `_search_with_grep(self, pattern: str, path: str, file_glob: Optional[str], limit: int, offset: int, output_mode: str, context: int) -> SearchResult` that:
    - Constructs a grep command as a fallback when ripgrep is unavailable
    - Parses the output to extract file paths, line numbers, and content
    - Returns a `SearchResult` with matches and metadata

---

## Implementation Notes

- **Imports**: Use `dataclasses`, `abc`, `os`, `pathlib`, `difflib`, `re`, `base64`, `mimetypes`, and standard library modules.
- **Terminal Backend**: The `terminal_env` parameter is expected to have an `execute(command, cwd=None, timeout=None, stdin_data=None)` method that returns a dict with `stdout` and `returncode` (or `exit_code`) keys.
- **Error Handling**: All methods should gracefully handle missing files, permission errors, and command failures by returning appropriate result objects with error messages.
- **Fuzzy Matching**: For `patch_replace()`, implement fuzzy matching by normalizing whitespace and allowing minor variations in the old string.
- **Pagination**: Implement offset/limit correctly so that `offset=0` means the first item, and results are properly truncated when exceeding the limit.

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

Python 3.10

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

`_escape_shell_arg(arg: str) -> str` wraps arguments in single quotes for safe shell execution. Arguments containing single quotes are escaped with multiple quote characters (minimum 4 total quotes for `"it's"`).

### Node 5: Unified Diff Generation

`_unified_diff(old_content: str, new_content: str, filename: str) -> str` generates standard unified diff format showing:
- Lines prefixed with `-` for deletions
- Lines prefixed with `+` for additions
- The filename in the diff header

### Node 6: ReadResult Serialization

`ReadResult.to_dict()` omits fields with default/empty values:
- `None` values are excluded from the dict
- Empty lists (e.g., `similar_files=[]`) are excluded
- Non-empty or non-default values are always included
- Empty string content (`content=""`) is preserved in the dict
- Fields included when non-default: `content`, `total_lines`, `file_size`, `truncated`, `hint`, `is_binary`, `is_image`, `base64_content`, `mime_type`, `dimensions`, `error`, `similar_files`

### Node 7: WriteResult Serialization

`WriteResult.to_dict()` includes:
- `bytes_written` (always included)
- `dirs_created` (always included)
- `error` and `warning` only if not `None`

### Node 8: PatchResult Serialization

`PatchResult.to_dict()` includes:
- `success` (always included; defaults to `False` if error is set)
- `diff`, `files_modified`, `files_created`, `files_deleted` (always included)
- `lint` (included if present)
- `error` (included if present)

### Node 9: SearchResult Serialization

`SearchResult.to_dict()` behavior:
- `total_count` always included
- `matches` list omitted if empty
- `files` list included when populated (file search mode)
- `counts` dict included when populated (count mode)
- `truncated` flag included when `True`
- `error` included if present
- `SearchMatch` objects in matches are converted to dicts with fields: `path`, `line_number`, `content`, `mtime`

### Node 10: LintResult Serialization

`LintResult.to_dict()` maps status field:
- `success=True` → `"status": "ok"`
- `success=False` → `"status": "error"`
- `skipped=True` → `"status": "skipped"`
- Always includes `output` and `message` fields

### Node 11: Search Path Validation

The `search()` method validates that the search path exists before proceeding. If the path does not exist (detected via `test -e` shell command returning exit code 1), the method returns a `SearchResult` with an error. This validation applies to both `target="content"` and `target="files"` modes.

### Node 12: Search Tool Error Handling

When using ripgrep (`rg`) for search:
- Exit code 0: matches found
- Exit code 1: no matches found (not an error)
- Exit code 2: actual error condition (reported in `SearchResult.error`)

### Node 13: ShellFileOperations Initialization

`ShellFileOperations.__init__(terminal_env, cwd: str = None)` sets the working directory:
- Uses provided `cwd` parameter if given
- Falls back to `terminal_env.cwd` if available
- Falls back to `"/"` if neither is available

### Node 14: File Size and Line Limits

Constants define read limits:
- `MAX_FILE_SIZE = 50 * 1024` (50 KB) - files larger than this are truncated
- `MAX_LINES = 2000` - maximum lines returned in a single read
- `MAX_LINE_LENGTH = 2000` - individual lines longer than this are truncated with `[truncated]` marker

The `read_file(path: str, offset: int = 1, limit: int = 500)` method supports pagination with `offset` (starting line, 1-indexed) and `limit` (number of lines to return, default 500).

### Node 15: ExecuteResult Structure

`ExecuteResult` contains:
- `stdout: str` - command output
- `exit_code: int` - process exit code

The `_exec(command: str, cwd: str = None, timeout: int = None, stdin_data: str = None) -> ExecuteResult` method executes shell commands with optional working directory, timeout, and stdin input.