"""Task: build medical-chatbot from scratch."""

import os
from pathlib import Path

from hud.eval.task import Task
from hud.types import MCPToolCall

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    ENV_NAME = os.environ.get("HUD_ENV_NAME", "ast-pilot-task-env")

    env = Environment("ast-pilot-task-env")
    env.connect_hub(ENV_NAME)

    TASK_DIR = Path(__file__).parent
    TESTS_DIR = TASK_DIR / "tests"
    GOLDEN_DIR = TASK_DIR / "golden"

    def _inject_and_run(test_file: str, workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file and runs pytest."""
        content = (TESTS_DIR / test_file).read_text()
        pythonpath = f"{workdir}:$PYTHONPATH"
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && PYTHONPATH={pythonpath} python3 -m pytest /tmp/{test_file} -v"
        )

    def _golden_setup(source_file: str, dest: str) -> str:
        """Build a bash command that writes the golden solution to the workspace."""
        content = (GOLDEN_DIR / source_file).read_text()
        return (
            f"mkdir -p $(dirname {dest})\n"
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
                    "name": 'test_imports',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_imports",
                    "weight": 1.0,
                },
                {
                    "name": 'test_env_vars',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_env_vars",
                    "weight": 1.0,
                },
                {
                    "name": 'test_faiss_init',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_faiss_init",
                    "weight": 1.0,
                },
                {
                    "name": 'test_llm_setup',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_llm_setup",
                    "weight": 1.0,
                },
                {
                    "name": 'test_prompt_persona',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_prompt_persona",
                    "weight": 1.0,
                },
                {
                    "name": 'test_query_execution',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_query_execution",
                    "weight": 1.0,
                },
                {
                    "name": 'test_rag_integrity',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_rag_integrity",
                    "weight": 1.0,
                },
                {
                    "name": 'test_response_formatting',
                    "command": _inject_and_run('test_medical_chatbot.py') + " -k test_response_formatting",
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = 'medical-chatbot'

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('chatbot.py', '/home/ubuntu/workspace/chatbot.py'),
            },
        ),
    ]
