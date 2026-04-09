"""Task: build context-references from scratch."""

import os
from pathlib import Path

from hud.eval.task import Task
from hud.types import MCPToolCall

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    ENV_NAME = os.environ.get("HUD_ENV_NAME", "mario-claire")

    env = Environment("mario-claire")
    env.connect_hub(ENV_NAME)

    TASK_DIR = Path(__file__).parent
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
        scenario="coding-task",
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": 'test_context_references',
                    "command": _inject_and_run('test_context_references.py'),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = 'context-references'

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('context_references.py', '/home/ubuntu/workspace/context_references.py'),
            },
        ),
    ]
