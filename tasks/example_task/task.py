"""Example task — build a small CLI calculator from scratch.

Demonstrates the 0-to-1 task pattern:
1. Agent gets a long markdown prompt (prompt.md) describing what to build
2. Agent works in a blank workspace using bash + editor
3. Grading injects hidden tests at runtime and runs them against the agent's code
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

    def _inject_and_run(test_file: str, workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file to /tmp and runs it."""
        content = (TESTS_DIR / test_file).read_text()
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && python -m pytest /tmp/{test_file} -v"
        )

    task = Task(
        env=env,
        scenario="coding-task",
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": "tests_pass",
                    "command": _inject_and_run("test_calc.py"),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = "example-calc"

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": (
                    "mkdir -p /home/ubuntu/workspace && cd /home/ubuntu/workspace"
                    " && cat > calc.py << 'PYEOF'\n"
                    "import sys\n"
                    "\n"
                    "def add(a, b): return a + b\n"
                    "def sub(a, b): return a - b\n"
                    "def mul(a, b): return a * b\n"
                    "def div(a, b):\n"
                    "    if b == 0: raise ZeroDivisionError('division by zero')\n"
                    "    return a / b\n"
                    "\n"
                    "OPS = {'+': add, '-': sub, '*': mul, '/': div}\n"
                    "\n"
                    "def evaluate(expr):\n"
                    "    parts = expr.split()\n"
                    "    a, op, b = float(parts[0]), parts[1], float(parts[2])\n"
                    "    return OPS[op](a, b)\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    print(evaluate(' '.join(sys.argv[1:])))\n"
                    "PYEOF"
                )
            },
        ),
    ]
