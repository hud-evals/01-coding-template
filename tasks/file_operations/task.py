"""Task: build file-operations from scratch."""

import os
from pathlib import Path

from hud.eval.task import Task
from hud.types import MCPToolCall
from task_bootstrap import require_hud_env_name

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    SCENARIO_ID = "ast-pilot:coding-task"

    TASK_DIR = Path(__file__).parent
    ENV_NAME = require_hud_env_name(
        TASK_DIR.parents[1] / ".env",
        error_message="HUD_ENV_NAME is required. Set it before running this task.",
    )
    env = Environment(ENV_NAME)
    env.connect_hub(ENV_NAME)

    TESTS_DIR = TASK_DIR / "tests"
    GOLDEN_DIR = TASK_DIR / "golden"
    SUPPORT_DIR = Path('/opt/ast_pilot_support') / TASK_DIR.name

    def _inject_and_run(test_file: str, workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file and runs pytest."""
        content = (TESTS_DIR / test_file).read_text()
        pythonpath = f"/home/ubuntu/workspace:{SUPPORT_DIR}:$PYTHONPATH"
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && PYTHONPATH={pythonpath} python -m pytest /tmp/{test_file} -v"
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
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": 'test_file_operations',
                    "command": _inject_and_run('test_file_operations.py'),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = 'file-operations'

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('binary_extensions.py', '/home/ubuntu/workspace/binary_extensions.py'),
            },
        ),
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('file_operations.py', '/home/ubuntu/workspace/file_operations.py'),
            },
        ),
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('hermes_constants.py', '/home/ubuntu/workspace/hermes_constants.py'),
            },
        ),
    ]
