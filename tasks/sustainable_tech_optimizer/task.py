"""Task: Sustainable Tech Optimizer Network."""

import os
from pathlib import Path
from task_bootstrap import require_hud_env_name

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment
    from hud.eval.task import Task
    from hud.types import MCPToolCall

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

    def _inject_and_run(test_file: str, test_func: str = "") -> str:
        content = (TESTS_DIR / test_file).read_text(encoding="utf-8")
        pythonpath = '/home/ubuntu/workspace:$PYTHONPATH'
        target = f"/tmp/{test_file}{'::' + test_func if test_func else ''}"
        
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd /home/ubuntu/workspace && PYTHONPATH={pythonpath} python -m pytest {target} -v"
        )

    def _golden_setup() -> str:
        content = (GOLDEN_DIR / "green_optimizer.py").read_text(encoding="utf-8")
        return (
            f"cat > /home/ubuntu/workspace/green_optimizer.py << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "forecaster_math", "command": _inject_and_run("test_forecaster.py", "test_forecast_renewable_out"), "weight": 1.0},
                {"name": "intensity_ratio", "command": _inject_and_run("test_forecaster.py", "test_calculate_effective_intensity"), "weight": 1.0},
                {"name": "allocator_success", "command": _inject_and_run("test_allocator.py", "test_allocation_success"), "weight": 1.0},
                {"name": "allocator_failure", "command": _inject_and_run("test_allocator.py", "test_allocation_failure"), "weight": 1.0},
                {"name": "carbon_audit", "command": _inject_and_run("test_auditor.py", "test_carbon_auditor_epoch"), "weight": 1.0},
                {"name": "sla_negotiation", "command": _inject_and_run("test_negotiator.py", "test_negotiator_sla_filtering"), "weight": 1.0},
                {"name": "batch_processing", "command": _inject_and_run("test_negotiator.py", "test_process_workload_batch"), "weight": 1.0},
            ]
        }
    )

    task.slug = "sustainable-tech-optimizer"
    task.columns = {
        "Name": "Sustainable Tech Optimizer",
        "Difficulty": "Extreme",
        "Category": "Systems Heuristics",
        "Failure modes": "Sorting latency/flag mismatch, failing to predict capacity bounds tracking, incorrectly summing emissions instead of specific epoch deltas."
    }
    task.metadata = {
        "name": "Sustainable Tech Optimizer Network",
        "description": "Multi-objective resource allocation for green energy computing architectures.",
        "difficulty": "Extreme"
    }

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
