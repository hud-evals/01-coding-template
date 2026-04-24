# word-count

## Overview

- Project name: word-count
- Total lines of code: 17
- Number of source modules: 1
- Classes: 0
- Module-level functions: 2
- Module 'counter' docstring: Simple word-count utility.

## Natural Language Instructions

Before you start:
- Create and edit the solution under `/home/ubuntu/workspace` at the exact workspace-relative paths below.
- Workspace-relative paths for hidden-test imports: `textkit/counter.py`.
- Implement every symbol listed in `Required Tested Symbols`, including underscored/private helpers.
- Recreate any repo-internal helper behavior locally instead of trying to install private packages.

### Behavioral Requirements

1. Implement the function `count_words(text)`
   Return the number of whitespace-delimited tokens in *text*.
2. Implement the function `unique_words(text)`
   Return the set of unique case-folded words in *text*.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def count_words(text: str) -> int`
- `def unique_words(text: str) -> set[str]`
- `WHITESPACE`

## Environment Configuration

### Python Version

Python 3.12

### Workspace

- Put the implementation under `/home/ubuntu/workspace` at the exact workspace-relative paths listed below.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution from: `textkit/counter.py`. A file at `pkg/mod.py` must resolve as `from pkg.mod import ...`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.


## Project Directory Structure

```
workspace/
├── pyproject.toml
└── textkit/
    └── counter.py
```

## API Usage Guide

### 1. Module Import

```python
from textkit.counter import (
    count_words,
    unique_words,
    WHITESPACE,
)
```

### 2. `count_words` Function

Return the number of whitespace-delimited tokens in *text*.

```python
def count_words(text: str) -> int:
```

**Parameters:**
- `text: str`

**Returns:** `int`

### 3. `unique_words` Function

Return the set of unique case-folded words in *text*.

```python
def unique_words(text: str) -> set[str]:
```

**Parameters:**
- `text: str`

**Returns:** `set[str]`

### 4. Constants and Configuration

```python
WHITESPACE = " \t\n\r\f\v"
```

## Implementation Notes

The following behaviors are validated by the test suite:

### Note 1: test_count_words_simple
Tests symbols: `count_words`

```python
def test_count_words_simple() -> None:
    assert count_words("hello world") == 2
```

### Note 2: test_count_words_empty
Tests symbols: `count_words`

```python
def test_count_words_empty() -> None:
    assert count_words("") == 0
```

### Note 3: test_count_words_whitespace_only
Tests symbols: `count_words`

```python
def test_count_words_whitespace_only() -> None:
    assert count_words("   \t\n  ") == 0
```

### Note 4: test_count_words_none
Tests symbols: `count_words`

```python
def test_count_words_none() -> None:
    assert count_words(None) == 0
```

### Note 5: test_unique_words_casefolds
Tests symbols: `unique_words`

```python
def test_unique_words_casefolds() -> None:
    assert unique_words("Hello HELLO hello") == {"hello"}
```

### Note 6: test_unique_words_empty
Tests symbols: `unique_words`

```python
def test_unique_words_empty() -> None:
    assert unique_words("") == set()
```

### Note 7: test_whitespace_constant_has_expected_chars
Tests symbols: `WHITESPACE`

```python
def test_whitespace_constant_has_expected_chars() -> None:
    assert " " in WHITESPACE
    assert "\t" in WHITESPACE
    assert "\n" in WHITESPACE
```
