"""Coding environment — tools for 0-to-1 development tasks.

The agent starts in a blank workspace, receives a long markdown prompt
describing a library/API to build from scratch, and is graded by running
tests from the original repository against its implementation.

Two scenarios are registered:

* ``coding-task`` — task artifacts (tests, golden, support) live on the
  image under ``/mcp_server/tasks``; ``task.py`` reads them from disk at
  grade time. Kept for backward compatibility with existing tasks.
* ``coding-task-v2`` — task artifacts are inlined into ``Task.args`` at
  sync time and staged by the scenario at grade time. Adding a new task
  only requires ``hud sync`` — no image rebuild.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from hud import Environment
from hud.tools.coding import BashTool, EditTool

logger = logging.getLogger(__name__)
SCENARIO_ENV_NAME = "ast-pilot"
SCENARIO_ID = f"{SCENARIO_ENV_NAME}:coding-task"
SCENARIO_ID_V2 = f"{SCENARIO_ENV_NAME}:coding-task-v2"

env = Environment(SCENARIO_ENV_NAME)

bash_tool = BashTool()
edit_tool = EditTool()

env.add_tool(bash_tool.mcp)
env.add_tool(edit_tool.mcp)


# ============================================================================
# Scenario Helpers
# ============================================================================

ValidateMode = Literal["baseline_fail", "golden_pass"]

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/home/ubuntu/workspace")


def make_prompt(description: str) -> str:
    """Format a task description into an agent prompt."""
    return (
        f"Your solution files belong in {WORKSPACE_DIR}.\n"
        "Your shell may start in a different current directory, so create/edit files in that workspace path explicitly.\n"
        "Use bash and editor tools to complete the following task:\n\n"
        f"{description}"
    )


# ============================================================================
# Scenario: coding-task
# ============================================================================


@env.scenario("coding-task", required_env_vars=["HUD_API_KEY"])
async def coding_task(
    prompt: str,
    bash_checks: list[dict] | None = None,
    validate_mode: ValidateMode | None = None,
):
    """General coding task scenario.

    Sets up a blank workspace, presents the prompt, then grades using
    deterministic bash checks (typically: run tests from the original repo).

    Args:
        prompt: The task instruction shown to the agent.
        bash_checks: List of {"name": str, "command": str, "weight": float}
                     dicts for deterministic shell-based grading.
        validate_mode: Used by validation (baseline_fail / golden_pass).
    """
    from hud.native.graders import BashGrader, Grade
    from hud.tools.types import SubScore

    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    yield make_prompt(prompt)

    graders = []

    if bash_checks:
        for check in bash_checks:
            graders.append(
                BashGrader.grade(
                    name=check["name"],
                    weight=check.get("weight", 1.0),
                    command=check["command"],
                )
            )

    if not graders:
        graders.append(SubScore(name="no_graders_defined", value=0.0, weight=1.0))

    yield await Grade.gather(*graders)


# ============================================================================
# Scenario: coding-task-v2 (sync-only; all artifacts arrive in Task.args)
# ============================================================================

# Support files stage outside the workspace so an agent-created package
# cannot shadow a support package of the same name and break transitive
# imports from the hidden tests.
SUPPORT_STAGING_ROOT = Path("/opt/task_support")
REQUIREMENTS_MARKER_DIR = Path("/opt")


def _stage_support(support: dict[str, str] | None) -> None:
    """Write each inlined support file to /opt/task_support/ and add to sys.path."""
    if not support:
        return
    if SUPPORT_STAGING_ROOT.exists():
        shutil.rmtree(SUPPORT_STAGING_ROOT)
    SUPPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    for rel, content in support.items():
        dst = SUPPORT_STAGING_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    root_str = str(SUPPORT_STAGING_ROOT)
    if root_str not in sys.path:
        sys.path.append(root_str)


def _install_requirements(hidden_requirements: str | None) -> None:
    """Pip-install hidden deps, memoized by content hash to avoid reinstall churn."""
    if not hidden_requirements:
        return
    digest = hashlib.sha256(hidden_requirements.encode("utf-8")).hexdigest()[:12]
    marker = REQUIREMENTS_MARKER_DIR / f".req_installed_{digest}"
    if marker.exists():
        return
    req_path = REQUIREMENTS_MARKER_DIR / f"task_requirements_{digest}.txt"
    req_path.write_text(hidden_requirements, encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(req_path)],
        check=True,
    )
    marker.touch()


def _build_grader_command(grader: dict[str, Any]) -> tuple[str, str, int, float]:
    """Translate one grader dict into (name, bash_command, timeout, weight).

    pytest-kind: writes the test content to /tmp and runs pytest with PYTHONPATH
    covering workspace + support staging. bash-kind: runs the provided command
    verbatim (escape hatch for future non-pytest graders).
    """
    weight = float(grader.get("weight", 1.0))
    timeout = int(grader.get("timeout", 120))
    kind = grader.get("kind", "pytest")

    if kind == "pytest":
        test_name = grader["test_name"]
        test_path = Path("/tmp") / test_name
        test_path.write_text(grader["script"], encoding="utf-8")
        pythonpath = f"{WORKSPACE_DIR}:{SUPPORT_STAGING_ROOT}:$PYTHONPATH"
        command = (
            f"cd {WORKSPACE_DIR} && "
            f"AST_PILOT_REPO_ROOT={WORKSPACE_DIR} "
            f"PYTHONPATH={pythonpath} "
            f"{sys.executable} -m pytest {test_path} -v"
        )
        return grader["name"], command, timeout, weight

    if kind == "bash":
        return grader["name"], grader["command"], timeout, weight

    raise ValueError(f"Unknown grader kind: {kind!r}")


@env.scenario("coding-task-v2", required_env_vars=["HUD_API_KEY"])
async def coding_task_v2(
    prompt: str,
    graders: list[dict[str, Any]] | None = None,
    support: dict[str, str] | None = None,
    hidden_requirements: str | None = None,
):
    """Sync-only coding task scenario.

    All task artifacts (tests, support, hidden deps) arrive inside
    ``args`` — the Docker image holds only env.py + runtime. Staging layout:

      * support  -> /opt/task_support/  (appended to sys.path)
      * tests    -> /tmp/<test_name>    (written per-grader inside grading)
      * hidden_requirements -> pip-installed once, memoized by content hash

    Golden pre-staging for ``hud eval integration_test`` happens via
    ``Task.validation`` (bash MCPToolCall with inlined base64 content) and
    fires before this scenario runs — not a scenario concern.

    Args:
        prompt: The task instruction shown to the agent.
        graders: List of grader dicts (see tasks/_helpers.pytest_grader).
        support: {relative_path: utf-8 content} for repo-internal helper modules.
        hidden_requirements: Contents of requirements.hidden.txt (or "").
    """
    from hud.native.graders import BashGrader, Grade
    from hud.tools.types import SubScore

    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    _stage_support(support)
    _install_requirements(hidden_requirements)

    yield make_prompt(prompt)

    grader_list = graders or []
    if not grader_list:
        yield [SubScore(name="no_graders_defined", value=0.0, weight=1.0)]
        return

    total_weight = sum(float(g.get("weight", 1.0)) for g in grader_list) or 1.0
    jobs = []
    for g in grader_list:
        name, command, timeout, weight = _build_grader_command(g)
        jobs.append(BashGrader.grade(
            name=name,
            weight=weight / total_weight,
            command=command,
            timeout_seconds=timeout,
        ))

    yield await Grade.gather(*jobs)


# ============================================================================
# Import task definitions (auto-discovers tasks/<name>/task.py)
# ============================================================================

import tasks  # noqa: E402, F401
