"""Fuzzy match task — build a multi-strategy fuzzy find-and-replace module.

Based on a real standalone module from an existing repository.
Demonstrates the full task pattern with:
- prompt.md describing the module to build
- tests/ from the original repo (injected at runtime)
- golden/ containing the original source (used for validation)
"""

import os
from pathlib import Path

from hud.eval.task import Task
from hud.types import MCPToolCall

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    ENV_NAME = os.environ.get("HUD_ENV_NAME", "01-coding-reinis")

    env = Environment("coding")
    env.connect_hub(ENV_NAME)

    TASK_DIR = Path(__file__).parent
    TESTS_DIR = TASK_DIR / "tests"
    GOLDEN_DIR = TASK_DIR / "golden"

    def _inject_and_run(test_file: str, workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file to /tmp and runs it."""
        content = (TESTS_DIR / test_file).read_text()
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && python -m pytest /tmp/{test_file} -v"
        )

    def _golden_setup(source_file: str, dest: str) -> str:
        """Build a bash command that writes the golden solution to the workspace."""
        content = (GOLDEN_DIR / source_file).read_text()
        return (
            f"mkdir -p {os.path.dirname(dest)}\n"
            f"cat > {dest} << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario="coding-task",
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": "tests_pass",
                    "command": _inject_and_run("test_fuzzy_match.py"),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = "fuzzy-match"

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup(
                    "fuzzy_match.py",
                    "/home/ubuntu/workspace/fuzzy_match.py",
                ),
            },
        ),
    ]
