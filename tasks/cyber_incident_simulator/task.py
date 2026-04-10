"""Task: Cyber Incident Simulator."""

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
        content = (GOLDEN_DIR / "soc_simulator.py").read_text(encoding="utf-8")
        return (
            f"cat > /home/ubuntu/workspace/soc_simulator.py << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "ingester_parsing", "command": _inject_and_run("test_ingestion.py", "test_parse_valid_logs"), "weight": 1.0},
                {"name": "brute_force_detection", "command": _inject_and_run("test_correlation.py", "test_detect_brute_force"), "weight": 1.0},
                {"name": "brute_force_timeout", "command": _inject_and_run("test_correlation.py", "test_brute_force_out_of_window"), "weight": 1.0},
                {"name": "lateral_movement", "command": _inject_and_run("test_correlation.py", "test_lateral_movement"), "weight": 1.0},
                {"name": "blast_radius_bfs", "command": _inject_and_run("test_containment.py", "test_blast_radius"), "weight": 1.0},
                {"name": "graph_isolation", "command": _inject_and_run("test_containment.py", "test_isolation_plan_success"), "weight": 1.0},
                {"name": "graph_fragmentation_defense", "command": _inject_and_run("test_containment.py", "test_isolation_causes_fragmentation"), "weight": 1.0},
                {"name": "report_structure", "command": _inject_and_run("test_reporting.py", "test_report_generation"), "weight": 1.0},
                {"name": "report_empty", "command": _inject_and_run("test_reporting.py", "test_empty_report"), "weight": 1.0},
            ]
        }
    )

    task.slug = "cyber-incident-simulator"
    task.columns = {
        "Name": "Autonomous SOC Simulator",
        "Difficulty": "Extreme",
        "Category": "Security Engineering",
        "Failure modes": "Does not enforce sliding window on Brute Force precisely. Graph fragmentation check is O(N^3) instead of simple BFS dropping the execution time. Incorrect parsing of ISO datetimes in standard python."
    }
    task.metadata = {
        "name": "Autonomous SOC Simulator",
        "description": "SOC backend engine evaluating stateful threat patterns and network graph isolation.",
        "difficulty": "Extreme"
    }

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
