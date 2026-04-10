"""Task: Software Bug Bounty Fixer."""

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
        content = (GOLDEN_DIR / "secure_api.py").read_text(encoding="utf-8")
        return (
            f"cat > /home/ubuntu/workspace/secure_api.py << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "sqli_basic", "command": _inject_and_run("test_sqli.py", "test_sqli_protection"), "weight": 1.0},
                {"name": "sqli_union", "command": _inject_and_run("test_sqli.py", "test_sqli_union_attack"), "weight": 1.0},
                {"name": "sqli_stacked", "command": _inject_and_run("test_sqli.py", "test_sqli_stacked_queries"), "weight": 1.0},
                {"name": "login_wrong_pass", "command": _inject_and_run("test_sqli.py", "test_login_wrong_password"), "weight": 1.0},
                {"name": "xss_script", "command": _inject_and_run("test_xss.py", "test_xss_protection"), "weight": 1.0},
                {"name": "xss_img_onerror", "command": _inject_and_run("test_xss.py", "test_xss_img_onerror"), "weight": 1.0},
                {"name": "xss_event_handler", "command": _inject_and_run("test_xss.py", "test_xss_event_handler"), "weight": 1.0},
                {"name": "xss_normal_text", "command": _inject_and_run("test_xss.py", "test_comment_normal_text"), "weight": 1.0},
                {"name": "logic_positive", "command": _inject_and_run("test_logic.py", "test_logic_positive"), "weight": 1.0},
                {"name": "logic_insufficient_funds", "command": _inject_and_run("test_logic.py", "test_logic_insufficient_funds"), "weight": 1.0},
                {"name": "logic_negative_qty", "command": _inject_and_run("test_logic.py", "test_logic_negative_quantity"), "weight": 1.0},
                {"name": "logic_zero_qty", "command": _inject_and_run("test_logic.py", "test_logic_zero_quantity"), "weight": 1.0},
                {"name": "logic_insufficient_stock", "command": _inject_and_run("test_logic.py", "test_logic_insufficient_stock"), "weight": 1.0},
                {"name": "logic_no_product", "command": _inject_and_run("test_logic.py", "test_logic_nonexistent_product"), "weight": 1.0},
                {"name": "logic_stock_decrement", "command": _inject_and_run("test_logic.py", "test_logic_stock_decrements"), "weight": 1.0},
                {"name": "idor_basic", "command": _inject_and_run("test_idor.py", "test_idor_protection"), "weight": 1.0},
                {"name": "idor_nonexistent", "command": _inject_and_run("test_idor.py", "test_idor_nonexistent_user"), "weight": 1.0},
                {"name": "idor_fields", "command": _inject_and_run("test_idor.py", "test_idor_returns_correct_fields"), "weight": 1.0},
            ]
        }
    )

    task.slug = "bug-bounty-fixer"
    task.columns = {
        "Name": "Bug Bounty Code Fixer",
        "Difficulty": "Extreme",
        "Category": "Cybersecurity",
        "Failure modes": "Agents failing to correctly escape XSS tags, or missing the edge-cases on the logic negative integer bypass check."
    }
    task.metadata = {
        "name": "Software Bug Bounty Hunter & Fixer",
        "description": "Locate and patch critical vulnerabilities across an e-commerce python backend.",
        "difficulty": "Extreme"
    }

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
