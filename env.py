"""Coding environment — tools for 0-to-1 development tasks.

The agent starts in a blank workspace, receives a long markdown prompt
describing a library/API to build from scratch, and is graded by running
tests from the original repository against its implementation.
"""

import logging
import os
from typing import Literal

from hud import Environment
from hud.tools.coding import BashTool, EditTool

logger = logging.getLogger(__name__)

def _require_env_name() -> str:
    env_name = os.environ.get("HUD_ENV_NAME", "").strip()
    if env_name:
        return env_name
    raise RuntimeError(
        "HUD_ENV_NAME is required. Set it in `.env` or your shell before running HUD commands."
    )


ENV_NAME = _require_env_name()

env = Environment(ENV_NAME)

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

    answer = yield make_prompt(prompt)

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
# Import task definitions (auto-discovers tasks/<name>/task.py)
# ============================================================================

import tasks  # noqa: E402, F401
