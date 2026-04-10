"""Task: Cybersecurity Threat Hunter."""
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

    # Note: Using the exact same pattern as medical_chatbot
    task = Task(
        env=env,
        scenario="coding-task",
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": "test_imports",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_imports",
                    "weight": 1.0,
                },
                {
                    "name": "test_bloom_filter",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_bloom_filter",
                    "weight": 1.0,
                },
                {
                    "name": "test_entropy_calc",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_entropy_calc",
                    "weight": 1.0,
                },
                {
                    "name": "test_log_parser",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_log_parser",
                    "weight": 1.0,
                },
                {
                    "name": "test_faiss_config",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_faiss_config",
                    "weight": 1.0,
                },
                {
                    "name": "test_llm_config",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_llm_config",
                    "weight": 1.0,
                },
                {
                    "name": "test_analysis_pipeline",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_analysis_pipeline",
                    "weight": 1.0,
                },
                {
                    "name": "test_mitigation_content",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_mitigation_content",
                    "weight": 1.0,
                },
                {
                    "name": "test_internal_handlers",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_internal_handlers",
                    "weight": 1.0,
                },
                {
                    "name": "test_top_level_entry",
                    "command": _inject_and_run("test_threat_hunter.py") + " -k test_top_level_entry",
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = "cyber-threat-hunter"

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup("threat_hunter.py", "/home/ubuntu/workspace/threat_hunter.py"),
            },
        ),
    ]
