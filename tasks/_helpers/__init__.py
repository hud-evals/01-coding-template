"""Task-build helpers — inline artifact content at task-import time.

Generated ``task.py`` files call these helpers to embed test, golden,
support and requirements content into ``Task.args`` (and the golden
staging commands into ``Task.validation``). ``hud sync`` then ships the
complete task definition as JSON — nothing task-specific needs to live
inside the Docker image.
"""

from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path

from hud.types import MCPToolCall


DEFAULT_WORKSPACE_DIR = "/home/ubuntu/workspace"


def resolve_env_name(task_file: str) -> str:
    """Return the deployed HUD environment name that this task targets.

    Read from ``.hud/config.json`` at the repo root — the same file ``hud deploy``
    and ``hud sync env`` maintain. Raising here is intentional: a task with no
    target environment cannot sync, so surfacing the misconfiguration at
    task-import time beats failing cryptically inside ``hud sync``.
    """
    repo_root = Path(task_file).resolve().parents[2]
    config_path = repo_root / ".hud" / "config.json"
    if not config_path.is_file():
        raise RuntimeError(
            f"Cannot resolve HUD environment for task at {task_file}: "
            f"{config_path} is missing. Run `hud deploy` or `hud sync env <name>` "
            "first — that writes the link between this directory and its deployed env."
        )
    data = json.loads(config_path.read_text(encoding="utf-8"))
    name = data.get("registryName")
    if not name:
        raise RuntimeError(
            f"{config_path} is missing 'registryName'. Re-run `hud deploy` "
            "to refresh the environment binding."
        )
    return str(name)


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


def vitest_grader(
    test_rel: str,
    *,
    task_file: str,
    weight: float = 1.0,
    timeout: int = 180,
) -> dict:
    """Build a vitest grader dict from ``tests/<test_rel>`` in the task dir.

    ``test_rel`` is the repo-relative path the test had in the source repo
    (e.g. ``test/defu.test.ts``) — the scenario writes the test into the
    staging tree at that exact location so vitest resolves imports the same
    way it did in the original project.
    """
    test_path = Path(task_file).parent / "tests" / test_rel
    content = test_path.read_text(encoding="utf-8")
    return {
        "kind": "vitest",
        "name": test_rel,
        "test_rel": test_rel,
        "script": content,
        "weight": weight,
        "timeout": timeout,
    }


def load_node_project(task_file: str) -> dict | None:
    """Read ``node_bundle_manifest.json`` and inline config/support files.

    Returns the dict the scenario expects as its ``node_project`` arg:

    * ``slug``: scenario-provided staging directory key
    * ``config_files``: ``{rel_path: content}`` for ``package.json``,
      ``package-lock.json``, ``tsconfig.json``, ``vitest.config.ts``, etc.
    * ``support_files``: ``{rel_path: content}`` for hidden helpers referenced
      by tests (e.g. fixture modules)
    * ``source_files``: list of repo-relative paths the agent is expected to
      produce in the workspace (scenario copies basename from ``WORKSPACE_DIR``
      into staging at grader time)

    Returns ``None`` when the task has no manifest (i.e. it's a Python task).
    """
    task_dir = Path(task_file).parent
    manifest_path = task_dir / "node_bundle_manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "slug": manifest["slug"],
        "config_files": manifest.get("config_files", {}),
        "support_files": manifest.get("support_files", {}),
        "source_files": sorted(manifest.get("source_files", {}).keys()),
    }


def golden_workspace_validation(
    task_file: str,
    *,
    workspace_dir: str = DEFAULT_WORKSPACE_DIR,
) -> list[MCPToolCall]:
    """TS-task variant of :func:`golden_validation`.

    The original repo tree lives under ``golden/`` at repo-relative paths
    (``src/index.ts`` etc.) but the agent writes basenames into
    ``WORKSPACE_DIR``. ``hud eval integration_test`` stages each golden file
    into ``WORKSPACE_DIR/<basename>`` so the grader bash command can copy it
    back into the right staging position.
    """
    golden = load_golden(task_file)
    if not golden:
        return []

    parts: list[str] = []
    for rel, content in sorted(golden.items()):
        basename = Path(rel).name
        dst = f"{workspace_dir.rstrip('/')}/{basename}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        parts.append(f"mkdir -p {shlex.quote(workspace_dir)}")
        parts.append(f"echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(dst)}")

    command = " && ".join(parts)
    return [MCPToolCall(name="bash", arguments={"command": command})]


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
