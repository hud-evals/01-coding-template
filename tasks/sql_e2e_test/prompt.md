# sql-e2e-test

## Overview

- Project name: sql-e2e-test
- Total lines of code: 32
- Number of source modules: 1
- Classes: 0
- Module-level functions: 3
- Module 'rules' docstring: Rule priority logic with SQLite backing.

## Natural Language Instructions

Before you start:
- Create and edit the solution directly in `/home/ubuntu/workspace`.
- The hidden tests import these top-level module file(s): `rules.py`.
- Implement every symbol listed in `Required Tested Symbols`, including underscored/private helpers.
- Recreate any repo-internal helper behavior locally instead of trying to install private packages.

### Behavioral Requirements

1. Implement the function `init_db(db_path)`
   Initialize a SQLite DB by applying schema.sql from the repo root.
2. Implement the function `add_rule(conn, rule_id, start_date, end_date)`
3. Implement the function `priority_first_triggered(conn, date)`

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def init_db(db_path: str) -> sqlite3.Connection`
- `def add_rule(conn: sqlite3.Connection, rule_id: str, start_date: str, end_date: str) -> None`
- `def priority_first_triggered(conn: sqlite3.Connection, date: str) -> str | None`

## Runtime Files

The hidden tests open the following non-Python files at runtime. Paths are relative to the workspace root.

### Files already provided

These files are staged into the workspace automatically before the hidden tests run. You may read them, but do not need to re-create them.

- `/home/ubuntu/workspace/schema.sql`


## Environment Configuration

### Python Version

Python >=3.11

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `rules.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── rules.py
├── schema.sql (provided)
```

## API Usage Guide

### 1. Module Import

```python
from rules import (
    init_db,
    add_rule,
    priority_first_triggered,
    REPO_ROOT,
)
```

### 2. `init_db` Function

Initialize a SQLite DB by applying schema.sql from the repo root.

```python
def init_db(db_path: str) -> sqlite3.Connection:
```

**Parameters:**
- `db_path: str`

**Returns:** `sqlite3.Connection`

### 3. `add_rule` Function

```python
def add_rule(conn: sqlite3.Connection, rule_id: str, start_date: str, end_date: str) -> None:
```

**Parameters:**
- `conn: sqlite3.Connection`
- `rule_id: str`
- `start_date: str`
- `end_date: str`

**Returns:** `None`

### 4. `priority_first_triggered` Function

```python
def priority_first_triggered(conn: sqlite3.Connection, date: str) -> str | None:
```

**Parameters:**
- `conn: sqlite3.Connection`
- `date: str`

**Returns:** `str | None`

### 5. Constants and Configuration

```python
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
```

## Implementation Notes

The following behaviors are validated by the test suite:

### Note 1: test_in_memory_priority_first_triggered_wins
Tests symbols: `add_rule`, `init_db`, `priority_first_triggered`

```python
    def test_in_memory_priority_first_triggered_wins(self, tmp_path):
        db = str(tmp_path / "t.db")
        conn = init_db(db)
        add_rule(conn, "R1", "2026-01-01", "2026-12-31")
        add_rule(conn, "R2", "2026-06-01", "2026-06-30")
        assert priority_first_triggered(conn, "2026-06-15") == "R1"
```
