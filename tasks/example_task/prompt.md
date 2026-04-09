# Task: Build a CLI Calculator

Create a Python calculator module at `/home/ubuntu/workspace/calc.py`.

## Requirements

### Module: `calc.py`

Implement the following functions:

1. **`add(a, b)`** — Returns `a + b`
2. **`sub(a, b)`** — Returns `a - b`
3. **`mul(a, b)`** — Returns `a * b`
4. **`div(a, b)`** — Returns `a / b`. Must raise `ZeroDivisionError` when `b == 0`.

5. **`evaluate(expr: str) -> float`** — Parses a string expression like `"3 + 4"` (space-separated: `<number> <operator> <number>`) and returns the numeric result using the functions above. Supported operators: `+`, `-`, `*`, `/`.

### CLI interface

When run as `python calc.py 3 + 4`, the program should print the result to stdout (e.g. `7.0`).

## Constraints

- Pure Python, no external dependencies.
- The file must be importable as a module (`from calc import add, evaluate`).
