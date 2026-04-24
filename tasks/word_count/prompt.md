# word-count

## Overview

**word-count** is a lightweight Python utility library designed to provide simple word-counting functionality. The project consists of a single source module (`counter`) containing 17 lines of code organized around two module-level functions. With zero class definitions, the library adopts a functional programming approach, exposing its capabilities through direct function calls rather than object-oriented abstractions. This minimal architecture makes word-count suitable for integration into larger applications or as a standalone utility for basic text analysis tasks.

The `counter` module serves as the sole interface for word-counting operations, as indicated by its docstring: "Simple word-count utility." The module exposes exactly two functions at the module level, each designed to handle specific aspects of word counting. The compact codebase of 17 lines reflects a focused implementation that prioritizes simplicity and efficiency without unnecessary abstraction layers or feature bloat.

This library is intended for developers seeking a straightforward, dependency-light solution for word-counting operations in Python projects. The functional design and minimal footprint make it easy to understand, maintain, and integrate into existing codebases without introducing significant overhead.

## Natural Language Instructions

### Implementation Constraints
- Create the file at `/home/ubuntu/workspace/textkit/counter.py`
- Create the directory `/home/ubuntu/workspace/textkit/` if it does not exist
- The module must be importable as `from textkit.counter import count_words, unique_words, WHITESPACE`
- Do not use external dependencies beyond Python's standard library
- The total implementation should be approximately 17 lines of code
- Preserve exact function signatures and parameter names as specified

### Behavioral Requirements

1. **Module docstring**: The `textkit.counter` module must have the docstring `"Simple word-count utility."`

2. **WHITESPACE constant**: Define a module-level constant named `WHITESPACE` with the exact value `" \t\n\r\f\v"` (space, tab, newline, carriage return, form feed, vertical tab). This constant must be importable and must contain at least the characters space (`" "`), tab (`"\t"`), and newline (`"\n"`).

3. **count_words function signature**: Implement a function with signature `def count_words(text: str) -> int:` that returns an integer.

4. **count_words docstring**: The function must have the docstring `"Return the number of whitespace-delimited tokens in *text*."`

5. **count_words behavior with normal input**: When called with a string containing words separated by whitespace (e.g., `"hello world"`), the function must return the count of whitespace-delimited tokens. For `"hello world"`, it must return `2`.

6. **count_words behavior with empty string**: When called with an empty string `""`, the function must return `0`.

7. **count_words behavior with whitespace-only input**: When called with a string containing only whitespace characters (e.g., `"   \t\n  "`), the function must return `0`.

8. **count_words behavior with None input**: When called with `None` as the argument, the function must return `0` (not raise an exception).

9. **unique_words function signature**: Implement a function with signature `def unique_words(text: str) -> set[str]:` that returns a set of strings.

10. **unique_words docstring**: The function must have the docstring `"Return the set of unique case-folded words in *text*."`

11. **unique_words case-folding behavior**: When called with a string containing the same word in different cases (e.g., `"Hello HELLO hello"`), the function must return a set containing only one element: the case-folded (lowercased) version of the word. For `"Hello HELLO hello"`, it must return `{"hello"}`.

12. **unique_words behavior with empty string**: When called with an empty string `""`, the function must return an empty set `set()`.

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

### Node 1: count_words function behavior

The `count_words(text: str) -> int` function returns the number of whitespace-delimited tokens in the input text.

- When given `"hello world"`, returns `2`.
- When given an empty string `""`, returns `0`.
- When given only whitespace characters (e.g., `"   \t\n  "`), returns `0`.
- When given `None` as input, returns `0` (the function handles `None` gracefully rather than raising an exception).

Whitespace delimiters are defined by the `WHITESPACE` constant.

### Node 2: unique_words function behavior

The `unique_words(text: str) -> set[str]` function returns a set of unique case-folded words in the input text.

- Case-folding is applied: when given `"Hello HELLO hello"`, all three variants are normalized to the same case and the function returns `{"hello"}` (a set containing a single element).
- When given an empty string `""`, returns an empty set `set()`.

### Node 3: WHITESPACE constant definition

The `WHITESPACE` constant is defined as `" \t\n\r\f\v"` and contains the following characters:
- Space: `" "`
- Tab: `"\t"`
- Newline: `"\n"`
- Carriage return: `"\r"`
- Form feed: `"\f"`
- Vertical tab: `"\v"`

These characters are used as delimiters for tokenizing text in the `count_words` function.