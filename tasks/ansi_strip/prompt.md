# ansi-strip

## Overview

- Project name: ansi-strip
- Total lines of code: 44
- Number of source modules: 1
- Classes: 0
- Module-level functions: 1
- Module 'ansi_strip' docstring: Strip ANSI escape sequences from subprocess output.

Used by terminal_tool, code_execution_tool, and process_registry to clean
command output before returning it to the model.  This prevents ANSI codes
from entering the model's context — which is the root cause of models
copying escape sequences int

## Natural Language Instructions

Before you start:
- Create and edit the solution under `/home/ubuntu/workspace` at the exact workspace-relative paths below.
- Workspace-relative paths for hidden-test imports: `tools/ansi_strip.py`.
- Implement every symbol listed in `Required Tested Symbols`, including underscored/private helpers.
- Recreate any repo-internal helper behavior locally instead of trying to install private packages.

### Behavioral Requirements

1. Implement the function `strip_ansi(text)`
   Remove ANSI escape sequences from text.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def strip_ansi(text: str) -> str`
- `_ANSI_ESCAPE_RE`
- `_HAS_ESCAPE`

## Environment Configuration

### Python Version

Python 3.12

### Workspace

- Put the implementation under `/home/ubuntu/workspace` at the exact workspace-relative paths listed below.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution from: `tools/ansi_strip.py`. A file at `pkg/mod.py` must resolve as `from pkg.mod import ...`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.


## Project Directory Structure

```
workspace/
├── pyproject.toml
└── tools/
    └── ansi_strip.py
```

## API Usage Guide

### 1. Module Import

```python
from tools.ansi_strip import (
    strip_ansi,
)
```

### 2. `strip_ansi` Function

Remove ANSI escape sequences from text.

Returns the input unchanged (fast path) when no ESC or C1 bytes are
present.  Safe to call on any string — clean text passes through
with negligible overhead.

```python
def strip_ansi(text: str) -> str:
```

**Parameters:**
- `text: str`

**Returns:** `str`

### 3. Constants and Configuration

```python
_ANSI_ESCAPE_RE = ...  # 664 chars
_HAS_ESCAPE = re.compile(r"[\x1b\x80-\x9f]")
```

## Implementation Notes

The following behaviors are validated by the test suite:

### Note 1: test_strip_ansi_removes_color_codes
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_removes_color_codes() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"
```

### Note 2: test_strip_ansi_preserves_plain_text
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_preserves_plain_text() -> None:
    assert strip_ansi("hello world") == "hello world"
```

### Note 3: test_strip_ansi_handles_none
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_handles_none() -> None:
    assert strip_ansi(None) is None
```

### Note 4: test_strip_ansi_preserves_unicode
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_preserves_unicode() -> None:
    assert strip_ansi("héllo — 世界\x1b[1mbold\x1b[0m") == "héllo — 世界bold"
```

### Note 5: test_strip_ansi_removes_osc_sequences
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_removes_osc_sequences() -> None:
    # OSC with BEL terminator
    assert strip_ansi("\x1b]0;window title\x07after") == "after"
    # OSC with ST terminator
    assert strip_ansi("\x1b]0;title\x1b\\after") == "after"
```

### Note 6: test_strip_ansi_private_mode_csi
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_private_mode_csi() -> None:
    # Private-mode ? prefix
    assert strip_ansi("\x1b[?25l" + "visible" + "\x1b[?25h") == "visible"
```

### Note 7: test_strip_ansi_csi_intermediate_bytes
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_csi_intermediate_bytes() -> None:
    # CSI with intermediate byte
    assert strip_ansi("before\x1b[1 @after") == "beforeafter"
```

### Note 8: test_has_escape_pattern_matches_only_escape_bytes
Tests symbols: `_HAS_ESCAPE`

```python
def test_has_escape_pattern_matches_only_escape_bytes() -> None:
    assert _HAS_ESCAPE.search("\x1b[0m") is not None
    assert _HAS_ESCAPE.search("plain text") is None
```

### Note 9: test_ansi_escape_re_is_compiled
Tests symbols: `_ANSI_ESCAPE_RE`

```python
def test_ansi_escape_re_is_compiled() -> None:
    import re
    assert isinstance(_ANSI_ESCAPE_RE, re.Pattern)
```

### Note 10: test_strip_ansi_empty_string
Tests symbols: `strip_ansi`

```python
def test_strip_ansi_empty_string() -> None:
    assert strip_ansi("") == ""
```
