"""Task: Lock-Free Concurrent HashMap."""

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
    GOLDEN_DIR = TASK_DIR / "golden/lockfree_hashmap"

    def _inject_and_run(test_file: str, test_func: str = "") -> str:
        """
        Build a bash command that writes a test file to /tmp and runs pytest.
        Using the proven pattern from multi-tenant-system and quantum-swarm.
        """
        content = (TESTS_DIR / test_file).read_text(encoding="utf-8")
        # Ensure we can find 'lockfree' no matter how the agent nests it
        pythonpath = '/home/ubuntu/workspace:/home/ubuntu/workspace/lockfree_hashmap:$PYTHONPATH'
        target = f"/tmp/{test_file}{'::' + test_func if test_func else ''}"
        
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd /home/ubuntu/workspace && PYTHONPATH={pythonpath} python -m pytest {target} -v"
        )

    def _golden_setup() -> str:
        """Build a bash command that writes the full golden solution layout."""
        cmd = "mkdir -p /home/ubuntu/workspace/lockfree_hashmap/lockfree\n"
        files = {
            "lockfree/__init__.py": "lockfree/__init__.py",
            "lockfree/atomic.py": "lockfree/atomic.py",
            "lockfree/hashmap.py": "lockfree/hashmap.py",
            "lockfree/node.py": "lockfree/node.py",
            "lockfree/utils.py": "lockfree/utils.py",
            "README.md": "README.md",
            "requirements.txt": "requirements.txt"
        }
        for dest, src in files.items():
            content = (GOLDEN_DIR / src).read_text(encoding="utf-8")
            cmd += f"cat << 'GOLDENEOF' > /home/ubuntu/workspace/lockfree_hashmap/{dest}\n{content}\nGOLDENEOF\n"
        return cmd

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "atomic_integer_basic", "command": _inject_and_run("test_atomic.py", "test_atomic_integer_basic"), "weight": 1.0},
                {"name": "atomic_integer_cas", "command": _inject_and_run("test_atomic.py", "test_atomic_integer_cas"), "weight": 1.0},
                {"name": "atomic_reference_basic", "command": _inject_and_run("test_atomic.py", "test_atomic_reference_basic"), "weight": 1.0},
                {"name": "atomic_concurrent_increment", "command": _inject_and_run("test_atomic.py", "test_atomic_concurrent_increment"), "weight": 1.0},
                {"name": "basic_put_get", "command": _inject_and_run("test_basic.py", "test_put_and_get"), "weight": 1.0},
                {"name": "basic_delete", "command": _inject_and_run("test_basic.py", "test_delete"), "weight": 1.0},
                {"name": "basic_contains_dunder", "command": _inject_and_run("test_basic.py", "test_contains_and_dunder"), "weight": 1.0},
                {"name": "basic_keys_values_items", "command": _inject_and_run("test_basic.py", "test_keys_values_items"), "weight": 1.0},
                {"name": "basic_clear", "command": _inject_and_run("test_basic.py", "test_clear"), "weight": 1.0},
                {"name": "concurrent_put_no_lost", "command": _inject_and_run("test_concurrent.py", "test_concurrent_put_no_lost_writes"), "weight": 1.0},
                {"name": "concurrent_mixed", "command": _inject_and_run("test_concurrent.py", "test_concurrent_mixed_operations"), "weight": 1.0},
                {"name": "concurrent_same_key", "command": _inject_and_run("test_concurrent.py", "test_concurrent_same_key_updates"), "weight": 1.0},
                {"name": "concurrent_delete_reinsert", "command": _inject_and_run("test_concurrent.py", "test_concurrent_delete_and_reinsert"), "weight": 1.0},
                {"name": "no_locks_in_source", "command": _inject_and_run("test_concurrent.py", "test_no_locks_in_source"), "weight": 1.0},
                {"name": "resize_triggered", "command": _inject_and_run("test_resize.py", "test_resize_triggered"), "weight": 1.0},
                {"name": "concurrent_resize", "command": _inject_and_run("test_resize.py", "test_concurrent_resize"), "weight": 1.0}
            ]
        }
    )

    task.slug = "lockfree-concurrent-hashmap"
    task.columns = {
        "Name": "Lock-Free Concurrent HashMap",
        "Difficulty": "Extreme",
        "Category": "Systems Engineering",
        "Failure modes": "Agent uses threading.Lock instead of true lock-free CAS operations. AtomicInteger increment not truly atomic without CAS retry loop. Resize logic causes lost writes when concurrent put happens during table copy. Agent often forgets to implement __contains__ and __len__ dunder methods. No-locks-in-source check fails because agent imports Lock."
    }
    task.metadata = {
        "name": "Lock-Free Concurrent HashMap",
        "description": "Lock-free open-addressing hashmap with real CAS via ctypes.",
        "difficulty": "Extreme"
    }

    # Validation uses the golden solution set up via bash
    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
