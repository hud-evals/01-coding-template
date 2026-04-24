"""Task-build helpers — inline artifact content at task-import time.

Generated ``task.py`` files call these helpers to embed test, golden,
support and requirements content into ``Task.args`` (and the golden
staging commands into ``Task.validation``). ``hud sync`` then ships the
complete task definition as JSON — nothing task-specific needs to live
inside the Docker image.
"""

from __future__ import annotations

import base64
import shlex
from pathlib import Path

from hud.types import MCPToolCall


DEFAULT_WORKSPACE_DIR = "/home/ubuntu/workspace"


def load_prompt(task_file: str) -> str:
    """Read ``prompt.md`` from the directory containing *task_file*."""
    return (Path(task_file).parent / "prompt.md").read_text(encoding="utf-8")


def load_support(task_file: str) -> dict[str, str]:
    """Return ``{repo-relative-path: utf-8 content}`` for every file under ``support/``.

    Returns an empty dict if the directory does not exist. Walks recursively and
    sorts keys so the payload is stable across reruns (easier to diff / dedupe
    sync uploads).
    """
    return _walk_tree(Path(task_file).parent / "support")


def load_golden(task_file: str) -> dict[str, str]:
    """Same shape as :func:`load_support` but reads from ``golden/``.

    Consumed by :func:`golden_validation` to build the integration-test
    staging command; production runs never stage it.
    """
    return _walk_tree(Path(task_file).parent / "golden")


def load_requirements(task_file: str) -> str:
    """Read ``requirements.hidden.txt`` content; empty string if absent.

    The scenario pip-installs this once per grading process (memoized by
    content hash) before running any grader.
    """
    req = Path(task_file).parent / "requirements.hidden.txt"
    if not req.is_file():
        return ""
    return req.read_text(encoding="utf-8")


def pytest_grader(
    test_name: str,
    *,
    task_file: str,
    weight: float = 1.0,
    timeout: int = 120,
) -> dict:
    """Build a pytest grader dict from ``tests/<test_name>`` in the task dir.

    The test file content is read at task-import time and inlined into the
    returned dict, which goes into ``Task.args["graders"]``. The scenario
    writes the script to ``/tmp/<test_name>`` and runs pytest against it
    with ``PYTHONPATH`` including the staged support tree.
    """
    test_path = Path(task_file).parent / "tests" / test_name
    content = test_path.read_text(encoding="utf-8")
    return {
        "kind": "pytest",
        "name": test_path.stem,
        "test_name": test_name,
        "script": content,
        "weight": weight,
        "timeout": timeout,
    }


def golden_validation(
    task_file: str,
    *,
    workspace_dir: str = DEFAULT_WORKSPACE_DIR,
) -> list[MCPToolCall]:
    """Build the integration-test validation: a bash call that stages golden into the workspace.

    ``hud eval integration_test`` runs every :class:`MCPToolCall` in
    ``Task.validation`` against the live environment before graders fire.
    Each golden file is base64-encoded into the command so regex backslashes
    and UTF-8 payloads survive JSON → shell transport intact.

    Returns an empty list when the task has no golden/ directory, which
    tells the runner there is nothing to pre-stage.
    """
    golden = load_golden(task_file)
    if not golden:
        return []

    parts: list[str] = []
    for rel, content in sorted(golden.items()):
        dst = f"{workspace_dir.rstrip('/')}/{rel}"
        dst_dir = str(Path(dst).parent)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        parts.append(f"mkdir -p {shlex.quote(dst_dir)}")
        parts.append(f"echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(dst)}")

    command = " && ".join(parts)
    return [MCPToolCall(name="bash", arguments={"command": command})]


def _walk_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        result[rel] = path.read_text(encoding="utf-8")
    return result
