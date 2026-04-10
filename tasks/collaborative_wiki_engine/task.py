"""Task: Collaborative Markdown Wiki Engine."""

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

    def _inject_and_run(test_file: str, test_func: str = "") -> str:
        """
        Build a bash command that writes a test file to /tmp and runs pytest.
        Proven pattern from quantum-circuit-swarm and multi-tenant-system.
        """
        content = (TESTS_DIR / test_file).read_text(encoding="utf-8")
        
        # Standard PYTHONPATH: strictly the root workspace.
        pythonpath = '/home/ubuntu/workspace:$PYTHONPATH'
        target = f"/tmp/{test_file}{'::' + test_func if test_func else ''}"
        
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd /home/ubuntu/workspace && PYTHONPATH={pythonpath} python -m pytest {target} -v"
        )

    def _golden_setup() -> str:
        """Build a bash command that writes the full golden solution layout directly to the root."""
        content = (GOLDEN_DIR / "wiki_engine.py").read_text(encoding="utf-8")
        return (
            f"cat > /home/ubuntu/workspace/wiki_engine.py << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "version_creation", "command": _inject_and_run("test_versioning.py", "test_page_creation"), "weight": 1.0},
                {"name": "version_updates", "command": _inject_and_run("test_versioning.py", "test_page_updates"), "weight": 1.0},
                {"name": "version_history", "command": _inject_and_run("test_versioning.py", "test_revision_history"), "weight": 1.0},
                {"name": "version_conflict", "command": _inject_and_run("test_versioning.py", "test_conflict_detection"), "weight": 1.0},
                {"name": "search_basic", "command": _inject_and_run("test_search.py", "test_basic_search"), "weight": 1.0},
                {"name": "search_ranking", "command": _inject_and_run("test_search.py", "test_ranking_by_frequency"), "weight": 1.0},
                {"name": "search_persistence", "command": _inject_and_run("test_search.py", "test_index_updates_on_save"), "weight": 1.0},
                {"name": "concurrency_race", "command": _inject_and_run("test_concurrency.py", "test_concurrent_updates"), "weight": 1.0},
                {"name": "concurrency_massive", "command": _inject_and_run("test_concurrency.py", "test_massive_history_concurrency"), "weight": 1.0},
                {"name": "parser_headings", "command": _inject_and_run("test_parser.py", "test_heading_parsing"), "weight": 1.0},
                {"name": "parser_lists", "command": _inject_and_run("test_parser.py", "test_list_parsing"), "weight": 1.0},
                {"name": "parser_mixed", "command": _inject_and_run("test_parser.py", "test_mixed_content"), "weight": 1.0},
            ]
        }
    )

    task.slug = "wiki-engine-system"
    task.columns = {
        "Name": "Collaborative Wiki Engine",
        "Difficulty": "Extreme",
        "Category": "Knowledge Systems",
        "Failure modes": "Agent splits code into multiple files causing import errors that crash all tests. Optimistic locking not implemented with proper thread locks so concurrent updates cause race conditions. Search index not updated after page edits so stale results returned. Markdown parser fails on nested inline elements like bold inside links."
    }
    task.metadata = {
        "name": "Collaborative Wiki Engine",
        "description": "Version-controlled searchable wiki with optimistic locking.",
        "difficulty": "Extreme"
    }

    # Validation uses the golden solution set up via bash
    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
