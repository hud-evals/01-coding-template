"""Task: build multi tenant system from scratch."""

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

    def _inject_and_run(test_file: str, test_func: str = "", workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file and runs pytest."""
        content = (TESTS_DIR / test_file).read_text(encoding="utf-8")
        pythonpath = '/home/ubuntu/workspace:$PYTHONPATH'
        target = f"/tmp/{test_file}{'::' + test_func if test_func else ''}"
        return (
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && PYTHONPATH={pythonpath} python -m pytest {target} -v"
        )

    def _golden_setup(source_file: str, dest: str) -> str:
        """Build a bash command that writes the golden solution to the workspace."""
        content = (GOLDEN_DIR / source_file).read_text(encoding="utf-8")
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
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "lsm_flushing", "command": _inject_and_run('test_multi_tenant_system.py', 'TestVectorDBEnterprise::test_lsm_flushing_and_persistence'), "weight": 1.0},
                {"name": "compaction", "command": _inject_and_run('test_multi_tenant_system.py', 'TestVectorDBEnterprise::test_compaction_consistency'), "weight": 1.0},
                {"name": "lsh_efficiency", "command": _inject_and_run('test_multi_tenant_system.py', 'TestVectorDBEnterprise::test_lsh_banding_efficiency'), "weight": 1.0},
                {"name": "isolation", "command": _inject_and_run('test_multi_tenant_system.py', 'TestVectorDBEnterprise::test_isolation_enforcement'), "weight": 1.0},
                {"name": "lru_cache", "command": _inject_and_run('test_multi_tenant_system.py', 'TestVectorDBEnterprise::test_lru_cache_behavior'), "weight": 1.0},
            ],
        },
    )
    task.slug = 'multi-tenant-system'
    task.columns = {
        "Name": "Multi-Tenant Enterprise VectorDB",
        "Difficulty": "Hard",
        "Category": "Data Pipeline",
        "Failure modes": "Agent often fails LSM-tree flushing by not persisting memtable to SSTables on disk. Compaction logic frequently merges segments incorrectly losing data. LSH banding parameters are miscalculated leading to poor recall. Tenant isolation broken when shared index leaks cross-tenant vectors. LRU cache eviction order wrong."
    }
    task.metadata = {
        "name": "Multi-Tenant Enterprise VectorDB",
        "description": "LSM-Tree RAG vector store from scratch in pure Python.",
        "difficulty": "Hard"
    }


    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup(
                    'multi_tenant_rag_system.py',
                    '/home/ubuntu/workspace/multi_tenant_rag_system.py',
                ),
            },
        ),
    ]
