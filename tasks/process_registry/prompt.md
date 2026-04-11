# process-registry

## Overview

**process-registry** is a lightweight Python library providing an in-memory registry for managed background processes. Comprising 990 lines of code organized in a single source module, the library implements 2 core classes and 1 module-level function to enable robust lifecycle management of spawned processes. The registry is designed to track processes initiated via terminal with `background=true`, offering a unified interface for monitoring, control, and data retrieval without external dependencies or persistent storage.

The library implements output buffering with a rolling 200KB window mechanism, allowing efficient capture and retrieval of process logs without unbounded memory consumption. Key operational capabilities include status polling to query process state, log retrieval for accessing buffered output, and blocking wait operations with interrupt support for synchronous process completion handling. Process termination is supported through explicit killing functionality, and the registry includes crash recovery mechanisms to maintain consistency when managed processes unexpectedly terminate.

This minimal, focused implementation targets scenarios requiring ephemeral process management within a single Python application instance, prioritizing simplicity and low overhead over distributed or persistent process tracking solutions.

# Natural Language Instructions for Rebuilding process-registry

## Implementation Constraints

- **Single module file**: All code lives in `/home/ubuntu/workspace/process_registry.py`
- **No external private packages**: Recreate all needed behavior locally
- **Exact signatures**: Use function/method signatures verbatim—do not rename parameters or change defaults
- **All symbols required**: Every class, method, function, and module-level constant listed must exist
- **Test imports**: Hidden tests import as `from process_registry import ...` or `import process_registry`
- **Thread-safe operations**: Use locks where indicated; manage background reader threads carefully
- **Checkpoint persistence**: Write/recover process metadata to/from JSON file at `CHECKPOINT_PATH`

---

## Natural Language Instructions

### Overview

You are rebuilding a **process registry library** that tracks spawned background processes in memory, buffers their output, and provides status polling, log retrieval, process killing, and crash recovery. The library must support both local subprocess spawning and remote environment-backed process execution.

### Behavioral Requirements

1. **ProcessSession dataclass**: Define a dataclass with all 20 fields exactly as specified (id, command, task_id, session_key, pid, process, env_ref, cwd, started_at, exited, exit_code, output_buffer, max_output_chars, detached, pid_scope, watcher_platform, watcher_chat_id, watcher_thread_id, watcher_interval, notify_on_complete, _lock, _reader_thread, _pty). The `_lock` field must be a `threading.Lock()` initialized in `__post_init__`. The `output_buffer` must support rolling-window behavior (max 200,000 characters by default).

2. **ProcessRegistry.__init__**: Initialize the registry with two internal dictionaries: `_running` (for active processes) and `_finished` (for exited processes). Initialize a threading lock `_lock` for thread-safe access. Set up any module-level constants (FINISHED_TTL_SECONDS=1800, MAX_PROCESSES=64, MAX_OUTPUT_CHARS=200000).

3. **ProcessRegistry._clean_shell_noise(text: str) -> str**: A static method that strips shell startup warnings (e.g., "WARNING: ..." lines) from the beginning of output text. Define `_SHELL_NOISE_SUBSTRINGS` as a class variable containing patterns to filter.

4. **ProcessRegistry._is_host_pid_alive(pid: Optional[int]) -> bool**: A static method that performs a best-effort liveness check on a host-visible PID. Return False if pid is None. Use `os.kill(pid, 0)` to test liveness (does not actually kill); catch `ProcessLookupError` to detect dead processes.

5. **ProcessRegistry._refresh_detached_session(session: Optional[ProcessSession]) -> Optional[ProcessSession]**: Update a recovered (detached) session when the underlying process has exited. Check if the process is still alive using `_is_host_pid_alive()`. If dead, move the session to `_finished`, set `exited=True`, and estimate `exit_code` (use 0 if unknown). Return the updated session or None if not found.

6. **ProcessRegistry._terminate_host_pid(pid: int) -> None**: A static method that terminates a host-visible PID without requiring the original process handle. Use `os.kill(pid, signal.SIGTERM)` first; if that fails, try `signal.SIGKILL`. Suppress exceptions gracefully.

7. **ProcessRegistry.spawn_local(command: str, cwd: str = None, task_id: str = "", session_key: str = "", env_vars: dict = None, use_pty: bool = False) -> ProcessSession**: Spawn a background process locally using `subprocess.Popen`. Create a new `ProcessSession` with a unique `id` (e.g., "proc_<uuid>"), set `pid_scope="host"`, and `detached=False`. Strip blocked environment variables (e.g., HERMES_*, GATEWAY_*) from the spawned process's environment. If `use_pty=True`, use `pty.openpty()` to create a pseudo-terminal; otherwise use pipes. Start a background reader thread (`_reader_loop` or `_pty_reader_loop`) to capture output. Add the session to `_running`. Return the session.

8. **ProcessRegistry.spawn_via_env(env: Any, command: str, cwd: str = None, task_id: str = "", session_key: str = "", timeout: int = 10) -> ProcessSession**: Spawn a process through a non-local environment backend (e.g., sandbox). Create a `ProcessSession` with `pid_scope="sandbox"`, `env_ref=env`, and `detached=False`. Call `env.run_background(command, cwd=cwd, timeout=timeout)` to get a log file path and PID file path. Start a background poller thread (`_env_poller_loop`) to monitor the log file. Add the session to `_running`. Return the session.

9. **ProcessRegistry._reader_loop(session: ProcessSession)**: A background thread function that reads stdout from a local `Popen` process line-by-line. Append each line to `session.output_buffer` (respecting the rolling-window max size). When EOF is reached, call `_move_to_finished(session)` with the process's exit code.

10. **ProcessRegistry._env_poller_loop(session: ProcessSession, env: Any, log_path: str, pid_path: str)**: A background thread function that polls a sandbox log file for non-local backends. Periodically read new lines from the log file and append to `session.output_buffer`. Check the PID file to detect when the process exits. When done, call `_move_to_finished(session)`.

11. **ProcessRegistry._pty_reader_loop(session: ProcessSession)**: A background thread function that reads output from a PTY process. Similar to `_reader_loop` but reads from the PTY file descriptor instead of `process.stdout`.

12. **ProcessRegistry._move_to_finished(session: ProcessSession)**: Move a session from `_running` to `_finished`. Set `session.exited=True`. Record the exit code. Stop the reader thread if running. Call `_prune_if_needed()` to enforce the MAX_PROCESSES limit.

13. **ProcessRegistry.get(session_id: str) -> Optional[ProcessSession]**: Retrieve a session by ID from either `_running` or `_finished`. Return None if not found. Thread-safe (acquire `_lock`).

14. **ProcessRegistry.poll(session_id: str) -> dict**: Check the status of a process and return new output since the last poll. Return a dict with keys: `status` ("running", "exited", or "not_found"), `command`, `pid`, `output_preview` (first 500 chars of output), `exit_code` (if exited), and other metadata. If the session is detached and recovered, call `_refresh_detached_session()` to update its status.

15. **ProcessRegistry.read_log(session_id: str, offset: int = 0, limit: int = 200) -> dict**: Read the full output log with optional pagination by lines. Split `session.output_buffer` by newlines. If `offset` and `limit` are provided, return only those lines. Return a dict with keys: `status`, `total_lines`, `showing` (description of which lines), `output` (the log text), and `session_id`.

16. **ProcessRegistry.wait(session_id: str, timeout: int = None) -> dict**: Block until a process exits, timeout occurs, or an interrupt is received. Poll the session status in a loop with a small sleep interval (e.g., 0.1 seconds). If timeout is exceeded, return a dict with `status="timeout"` and a `timeout_note`. Otherwise, return the final status dict (like `poll()`).

17. **ProcessRegistry.kill_process(session_id: str) -> dict**: Kill a background process. If the session is not found, return `{"status": "not_found"}`. If already exited, return `{"status": "already_exited"}`. If running and local, call `process.terminate()` or `process.kill()`. If detached (recovered), use `_terminate_host_pid(session.pid)`. Return a dict with `status="killed"` and the session metadata.

18. **ProcessRegistry.write_stdin(session_id: str, data: str) -> dict**: Send raw data to a running process's stdin without appending a newline. Acquire the session's `_lock`, write to `process.stdin`, and flush. Return a dict with `status` and any error message.

19. **ProcessRegistry.submit_stdin(session_id: str, data: str = "") -> dict**: Send data + newline to a running process's stdin (like pressing Enter). Call `write_stdin()` with `data + "\n"`. Return the result dict.

20. **ProcessRegistry.list_sessions(task_id: str = None) -> list**: List all running and recently-finished processes. Return a list of dicts, each with keys: `session_id`, `command`, `status` ("running" or "exited"), `pid`, `task_id`, `output_preview`, `exit_code` (if exited), `started_at`. If `task_id` is provided, filter to only sessions with that task_id.

21. **ProcessRegistry.has_active_processes(task_id: str) -> bool**: Check if there are active (running, not exited) processes for a given task_id. Return True if at least one session in `_running` matches the task_id.

22. **ProcessRegistry.has_active_for_session(session_key: str) -> bool**: Check if there are active processes for a gateway session key. Return True if at least one session in `_running` has `session_key` matching the argument.

23. **ProcessRegistry.kill_all(task_id: str = None) -> int**: Kill all running processes, optionally filtered by task_id. Return the count of processes killed. Iterate over `_running`, call `kill_process()` for each matching session, and move them to `_finished`.

24. **ProcessRegistry._prune_if_needed()**: Remove oldest finished sessions if the total count (running + finished) exceeds MAX_PROCESSES. First, remove any finished sessions older than FINISHED_TTL_SECONDS. Then, if still over the limit, remove the oldest finished sessions by `started_at` timestamp until the count is under MAX_PROCESSES. Must hold `_lock` when called.

25. **ProcessRegistry._write_checkpoint()**: Write running process metadata to a checkpoint JSON file atomically. For each session in `_running`, serialize: `session_id`, `command`, `pid`, `task_id`, `session_key`, `cwd`, `pid_scope`, `watcher_platform`, `watcher_chat_id`, `watcher_thread_id`, `watcher_interval`, `notify_on_complete`. Write to a temporary file first, then rename to `CHECKPOINT_PATH` to ensure atomicity.

26. **ProcessRegistry.recover_from_checkpoint() -> int**: On gateway startup, probe PIDs from the checkpoint file to recover detached processes. Read `CHECKPOINT_PATH` (return 0 if missing). For each entry, check if the PID is still alive using `_is_host_pid_alive()`. If alive, create a new `ProcessSession` with `detached=True`, `pid_scope="host"`, and add to `_running`. If the session has watcher metadata and `watcher_interval > 0`, enqueue a watcher task (e.g., via a task queue). Skip entries with `pid_scope="sandbox"` (they cannot be recovered). Return the count of recovered sessions.

27. **_handle_process(args, **kw) -> str**: A module-level function that acts as a JSON-RPC-like handler for process registry operations. Parse `args` as a dict with an `action` key. Supported actions: `"list"` (call `list_sessions()`), `"poll"` (call `poll(session_id)`), `"read_log"` (call `read_log(session_id, offset, limit)`), `"wait"` (call `wait(session_id, timeout)`), `"kill"` (call `kill_process(session_id)`), `"write_stdin"` (call `write_stdin(session_id, data)`), `"submit_stdin"` (call `submit_stdin(session_id, data)`). Return a JSON string with the result or an error message.

28. **Module-level constants**: Define `FINISHED_TTL_SECONDS = 1800`, `MAX_PROCESSES = 64`, `MAX_OUTPUT_CHARS = 200_000`, and `CHECKPOINT_PATH = get_hermes_home() / "processes.json"` (or a similar path). Implement or import `get_hermes_home()` to return the Hermes home directory.

29. **String literals**: Use the exact string keys listed in the requirements (e.g., 'action', 'command', 'status', 'output', 'pid', 'session_id', etc.) consistently throughout the module for dict keys and data fields.

30. **Thread safety**: All public methods that access `_running` or `_finished` must acquire `_lock` before reading/writing. Use context managers (`with self._lock:`) to ensure locks are released even if exceptions occur.

31. **Output buffering**: Implement a rolling-window buffer for `output_buffer` that never exceeds `max_output_chars` (default 200,000). When appending new output, if the buffer would exceed the limit, discard the oldest lines first.

32. **Error handling**: Return informative error dicts (with `status` and optional `note` or `error` keys) for all failure cases (not found, already exited, timeout, etc.). Do not raise exceptions from public methods; instead, return error dicts.

33. **PTY support**: When `use_pty=True` in `spawn_local()`, use `pty.openpty()` to create a pseudo-terminal pair. Set the slave side to raw mode and connect it to the subprocess. Read from the master side in `_pty_reader_loop()`.

34. **Environment variable filtering**: When spawning a local process, strip environment variables that start with `HERMES_`, `GATEWAY_`, or other blocked prefixes. Always set `PYTHONUNBUFFERED=1` for Python subprocesses to ensure unbuffered output.

35. **Detached process recovery**: Sessions recovered from the checkpoint file are marked `detached=True` and `pid_scope="host"`. They do not have a live `process` handle, so use `_is_host_pid_alive()` and `_terminate_host_pid()` for status checks and termination. Periodically refresh their status via `_refresh_detached_session()`.

## Required Tested Symbols

The hidden tests import every symbol listed here. Implement all of them, including underscored/private helpers.

- `def ProcessRegistry.spawn_local(self, command: str, cwd: str = None, task_id: str = "", session_key: str = "", env_vars: dict = None, use_pty: bool = False) -> ProcessSession`
- `def ProcessRegistry.get(self, session_id: str) -> Optional[ProcessSession]`
- `def ProcessRegistry.poll(self, session_id: str) -> dict`
- `def ProcessRegistry.read_log(self, session_id: str, offset: int = 0, limit: int = 200) -> dict`
- `def ProcessRegistry.wait(self, session_id: str, timeout: int = None) -> dict`
- `def ProcessRegistry.kill_process(self, session_id: str) -> dict`
- `def ProcessRegistry.list_sessions(self, task_id: str = None) -> list`
- `def ProcessRegistry.has_active_processes(self, task_id: str) -> bool`
- `def ProcessRegistry.has_active_for_session(self, session_key: str) -> bool`
- `def ProcessRegistry._prune_if_needed(self)`
- `def ProcessRegistry._write_checkpoint(self)`
- `def ProcessRegistry.recover_from_checkpoint(self) -> int`
- `def _handle_process(args, **kw)`
- `FINISHED_TTL_SECONDS`
- `MAX_PROCESSES`

## Environment Configuration

### Python Version

Python >=3.11

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Your shell may start in a different current directory, so `cd` into the workspace or use paths that write there explicitly.
- Hidden tests import the solution as top-level module file(s): `process_registry.py`.

### External Dependencies

No third-party runtime dependencies were detected from the source file.

### Internal Helpers (implement locally)

These names came from repo-internal modules. Do NOT try to `pip install` them.

- `hermes_cli.config`: repo-private filesystem/path helpers; the original code imported `get_hermes_home` from `hermes_cli.config`. Recreate the needed behavior locally.
- `tools.ansi_strip`: repo-private helper module; the original code imported `strip_ansi` from `tools.ansi_strip`. Recreate the needed behavior locally.
- `tools.environments.local`: repo-private helper module; the original code imported `_find_shell`, `_sanitize_subprocess_env` from `tools.environments.local`. Recreate the needed behavior locally.
- `tools.registry`: repo-private helper module; the original code imported `registry`, `tool_error` from `tools.registry`. Recreate the needed behavior locally.
- `tools.terminal_tool`: repo-private helper module; the original code imported `_interrupt_event` from `tools.terminal_tool`. Recreate the needed behavior locally.
- `utils`: repo-private helper module; the original code imported `atomic_json_write` from `utils`. Recreate the needed behavior locally.


## Project Directory Structure

```
workspace/
├── pyproject.toml
├── process_registry.py
```

## API Usage Guide

### 1. Module Import

```python
from process_registry import (
    ProcessSession,
    ProcessRegistry,
    CHECKPOINT_PATH,
    MAX_OUTPUT_CHARS,
    FINISHED_TTL_SECONDS,
    MAX_PROCESSES,
    PROCESS_SCHEMA,
)
```

### 2. `ProcessSession` Class

A tracked background process with output buffering.

```python
class ProcessSession():
    """A tracked background process with output buffering."""
```

**Class Variables:**
- `id: str`
- `command: str`
- `task_id: str`
- `session_key: str`
- `pid: Optional[int]`
- `process: Optional[subprocess.Popen]`
- `env_ref: Any`
- `cwd: Optional[str]`
- `started_at: float`
- `exited: bool`
- `exit_code: Optional[int]`
- `output_buffer: str`
- `max_output_chars: int`
- `detached: bool`
- `pid_scope: str`
- `watcher_platform: str`
- `watcher_chat_id: str`
- `watcher_thread_id: str`
- `watcher_interval: int`
- `notify_on_complete: bool`
- `_lock: threading.Lock`
- `_reader_thread: Optional[threading.Thread]`
- `_pty: Any`

### 3. `ProcessRegistry` Class

In-memory registry of running and finished background processes.

Thread-safe. Accessed from:
  - Executor threads (terminal_tool, process tool handlers)
  - Gateway asyncio loop (watcher tasks, session reset checks)
  - Cleanup thread (sandbox reaping coordination)

```python
class ProcessRegistry():
    """In-memory registry of running and finished background processes."""
```

**Class Variables:**
- `_SHELL_NOISE_SUBSTRINGS`


```python
def __init__(self):
```


Strip shell startup warnings from the beginning of output.

```python
def _clean_shell_noise(text: str) -> str:
```

**Parameters:**
- `text: str`

**Returns:** `str`

**Decorators:** `staticmethod`


Best-effort liveness check for host-visible PIDs.

```python
def _is_host_pid_alive(pid: Optional[int]) -> bool:
```

**Parameters:**
- `pid: Optional[int]`

**Returns:** `bool`

**Decorators:** `staticmethod`


Update recovered host-PID sessions when the underlying process has exited.

```python
def _refresh_detached_session(self, session: Optional[ProcessSession]) -> Optional[ProcessSession]:
```

**Parameters:**
- `session: Optional[ProcessSession]`

**Returns:** `Optional[ProcessSession]`


Terminate a host-visible PID without requiring the original process handle.

```python
def _terminate_host_pid(pid: int) -> None:
```

**Parameters:**
- `pid: int`

**Returns:** `None`

**Decorators:** `staticmethod`


Spawn a background process locally.

Only for TERMINAL_ENV=local. Other backends use spawn_via_env().

Args:
    use_pty: If True, use a pseudo-terminal via ptyprocess for interactive
             CLI tools (Codex, Claude Code, Python REPL). Falls back to
             subprocess.Popen if ptyprocess is not installed.

```python
def spawn_local(self, command: str, cwd: str = None, task_id: str = "", session_key: str = "", env_vars: dict = None, use_pty: bool = False) -> ProcessSession:
```

**Parameters:**
- `command: str`
- `cwd: str = None`
- `task_id: str = ""`
- `session_key: str = ""`
- `env_vars: dict = None`
- `use_pty: bool = False`

**Returns:** `ProcessSession`


Spawn a background process through a non-local environment backend.

For Docker/Singularity/Modal/Daytona/SSH: runs the command inside the sandbox
using the environment's execute() interface. We wrap the command to
capture the in-sandbox PID and redirect output to a log file inside
the sandbox, then poll the log via subsequent execute() calls.

This is less capable than local spawn (no live stdout pipe, no stdin),
but it ensures the command runs in the correct sandbox context.

```python
def spawn_via_env(self, env: Any, command: str, cwd: str = None, task_id: str = "", session_key: str = "", timeout: int = 10) -> ProcessSession:
```

**Parameters:**
- `env: Any`
- `command: str`
- `cwd: str = None`
- `task_id: str = ""`
- `session_key: str = ""`
- `timeout: int = 10`

**Returns:** `ProcessSession`


Background thread: read stdout from a local Popen process.

```python
def _reader_loop(self, session: ProcessSession):
```

**Parameters:**
- `session: ProcessSession`


Background thread: poll a sandbox log file for non-local backends.

```python
def _env_poller_loop(self, session: ProcessSession, env: Any, log_path: str, pid_path: str):
```

**Parameters:**
- `session: ProcessSession`
- `env: Any`
- `log_path: str`
- `pid_path: str`


Background thread: read output from a PTY process.

```python
def _pty_reader_loop(self, session: ProcessSession):
```

**Parameters:**
- `session: ProcessSession`


Move a session from running to finished.

```python
def _move_to_finished(self, session: ProcessSession):
```

**Parameters:**
- `session: ProcessSession`


Get a session by ID (running or finished).

```python
def get(self, session_id: str) -> Optional[ProcessSession]:
```

**Parameters:**
- `session_id: str`

**Returns:** `Optional[ProcessSession]`


Check status and get new output for a background process.

```python
def poll(self, session_id: str) -> dict:
```

**Parameters:**
- `session_id: str`

**Returns:** `dict`


Read the full output log with optional pagination by lines.

```python
def read_log(self, session_id: str, offset: int = 0, limit: int = 200) -> dict:
```

**Parameters:**
- `session_id: str`
- `offset: int = 0`
- `limit: int = 200`

**Returns:** `dict`


Block until a process exits, timeout, or interrupt.

Args:
    session_id: The process to wait for.
    timeout: Max seconds to block. Falls back to TERMINAL_TIMEOUT config.

Returns:
    dict with status ("exited", "timeout", "interrupted", "not_found")
    and output snapshot.

```python
def wait(self, session_id: str, timeout: int = None) -> dict:
```

**Parameters:**
- `session_id: str`
- `timeout: int = None`

**Returns:** `dict`


Kill a background process.

```python
def kill_process(self, session_id: str) -> dict:
```

**Parameters:**
- `session_id: str`

**Returns:** `dict`


Send raw data to a running process's stdin (no newline appended).

```python
def write_stdin(self, session_id: str, data: str) -> dict:
```

**Parameters:**
- `session_id: str`
- `data: str`

**Returns:** `dict`


Send data + newline to a running process's stdin (like pressing Enter).

```python
def submit_stdin(self, session_id: str, data: str = "") -> dict:
```

**Parameters:**
- `session_id: str`
- `data: str = ""`

**Returns:** `dict`


List all running and recently-finished processes.

```python
def list_sessions(self, task_id: str = None) -> list:
```

**Parameters:**
- `task_id: str = None`

**Returns:** `list`


Check if there are active (running) processes for a task_id.

```python
def has_active_processes(self, task_id: str) -> bool:
```

**Parameters:**
- `task_id: str`

**Returns:** `bool`


Check if there are active processes for a gateway session key.

```python
def has_active_for_session(self, session_key: str) -> bool:
```

**Parameters:**
- `session_key: str`

**Returns:** `bool`


Kill all running processes, optionally filtered by task_id. Returns count killed.

```python
def kill_all(self, task_id: str = None) -> int:
```

**Parameters:**
- `task_id: str = None`

**Returns:** `int`


Remove oldest finished sessions if over MAX_PROCESSES. Must hold _lock.

```python
def _prune_if_needed(self):
```


Write running process metadata to checkpoint file atomically.

```python
def _write_checkpoint(self):
```


On gateway startup, probe PIDs from checkpoint file.

Returns the number of processes recovered as detached.

```python
def recover_from_checkpoint(self) -> int:
```

**Returns:** `int`

### 4. Constants and Configuration

```python
_IS_WINDOWS = platform.system() == "Windows"
CHECKPOINT_PATH = get_hermes_home() / "processes.json"
MAX_OUTPUT_CHARS = 200_000
FINISHED_TTL_SECONDS = 1800
MAX_PROCESSES = 64
PROCESS_SCHEMA = ...  # 1705 chars
```

## Implementation Notes

### Node 1: ProcessSession Data Structure
- `ProcessSession` is a dataclass representing a single tracked background process
- Contains process metadata: `id`, `command`, `task_id`, `session_key`, `pid`, `cwd`, `started_at`
- Tracks execution state: `exited` (boolean), `exit_code` (Optional[int])
- Maintains output in `output_buffer` (string) with a `max_output_chars` limit (default 200_000)
- Includes threading primitives: `_lock` (threading.Lock), `_reader_thread` (Optional[threading.Thread])
- Supports PTY mode via `_pty` field
- Tracks detached processes: `detached` (boolean), `pid_scope` (string)
- Includes watcher metadata for notifications: `watcher_platform`, `watcher_chat_id`, `watcher_thread_id`, `watcher_interval`, `notify_on_complete`
- Stores optional subprocess handle: `process` (Optional[subprocess.Popen])

### Node 2: ProcessRegistry Core Structure
- Maintains two internal dictionaries: `_running` (active processes) and `_finished` (exited processes)
- Uses threading lock `_lock` for thread-safe access to internal state
- Implements shell noise filtering via `_clean_shell_noise()` to strip startup warnings from output
- Provides liveness checking via `_is_host_pid_alive()` for best-effort PID validation

### Node 3: Process Spawning
- `spawn_local()` spawns processes directly using subprocess.Popen with optional PTY support
  - Accepts: `command`, `cwd`, `task_id`, `session_key`, `env_vars` dict, `use_pty` boolean
  - Strips blocked environment variables from background process environment
  - Returns a `ProcessSession` object
  - Launches background reader thread (`_reader_loop` or `_pty_reader_loop`)
- `spawn_via_env()` spawns through non-local environment backends (sandboxes)
  - Accepts: `env` object, `command`, `cwd`, `task_id`, `session_key`, `timeout` (default 10)
  - Launches `_env_poller_loop` background thread to poll sandbox log files

### Node 4: Output Reading and Buffering
- `_reader_loop()` runs in background thread for local Popen processes, reads stdout continuously
- `_pty_reader_loop()` runs in background thread for PTY-based processes
- `_env_poller_loop()` polls sandbox log files and pid files for non-local backends
- All readers append to `output_buffer` up to `max_output_chars` limit (200_000)
- Output is thread-safe via `_lock` on the session

### Node 5: Session Lifecycle Management
- `_move_to_finished()` transitions a session from `_running` to `_finished` when process exits
- Finished sessions are retained for `FINISHED_TTL_SECONDS` (1800 seconds / 30 minutes)
- `_refresh_detached_session()` updates recovered host-PID sessions when underlying process exits
- `_prune_if_needed()` removes expired finished sessions and oldest sessions when count exceeds `MAX_PROCESSES` (64)

### Node 6: Query Operations
- `get(session_id)` returns a `ProcessSession` from either `_running` or `_finished`, or None if not found
- `poll(session_id)` returns dict with keys: `status` ("running", "exited", or "not_found"), `output_preview`, `command`, `exit_code` (if exited)
- `read_log(session_id, offset=0, limit=200)` returns dict with full output log, paginated by lines
  - Returns: `status`, `total_lines`, `showing` (description), `lines` (list)
  - Default limit is 200 lines; offset and limit control pagination
- `list_sessions(task_id=None)` returns list of dicts for all sessions (running + finished)
  - Each entry contains: `session_id`, `command`, `status`, `pid`, `output_preview`
  - Optional filtering by `task_id`
- `has_active_processes(task_id)` returns boolean; checks only `_running` dict
- `has_active_for_session(session_key)` returns boolean; checks only `_running` dict for matching `session_key`

### Node 7: Process Control Operations
- `kill_process(session_id)` terminates a running process
  - Returns dict with `status`: "killed", "already_exited", or "not_found"
  - For detached sessions, uses `_terminate_host_pid()` with host-visible PID
  - For normal sessions, calls `process.terminate()` or `process.kill()`
- `kill_all(task_id=None)` kills all running processes, optionally filtered by `task_id`
  - Returns count of processes killed
- `write_stdin(session_id, data)` sends raw data to process stdin (no newline)
- `submit_stdin(session_id, data="")` sends data + newline to process stdin

### Node 8: Checkpoint and Recovery
- `_write_checkpoint()` writes metadata of all `_running` sessions to `CHECKPOINT_PATH` (get_hermes_home() / "processes.json") as JSON
  - Includes: `session_id`, `command`, `pid`, `task_id`, `session_key`, `cwd`, `pid_scope`, `detached`, `watcher_platform`, `watcher_chat_id`, `watcher_thread_id`, `watcher_interval`, `notify_on_complete`
  - Write is atomic
- `recover_from_checkpoint()` on gateway startup probes PIDs from checkpoint file
  - Returns count of recovered sessions
  - Skips entries with `pid_scope` == "sandbox" (non-local backends)
  - For live PIDs (verified via `_is_host_pid_alive()`), creates detached `ProcessSession` objects and adds to `_running`
  - Enqueues watcher tasks if `watcher_interval` > 0 and watcher metadata is present
  - Skips entries with dead PIDs or missing `watcher_interval`

### Node 9: Platform-Specific Behavior
- `_IS_WINDOWS` flag (platform.system() == "Windows") controls platform-specific logic
- `_terminate_host_pid(pid)` terminates a host-visible PID without original process handle
- Detached sessions use `pid_scope` field to track scope ("host" or "sandbox")
- `watcher_platform` field stores platform type (e.g., "telegram") for notifications

### Node 10: Handler Function
- `_handle_process(args, **kw)` is the entry point for external callers
  - Accepts dict with `action` key: "list", "poll", "spawn", "kill", "wait", "write_stdin", "submit_stdin", etc.
  - Returns JSON string with result
  - Returns error dict if required fields missing or action unknown
  - "list" action returns dict with "processes" key