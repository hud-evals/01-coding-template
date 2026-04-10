"""Task: build quantum circuit designer swarm from scratch."""

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
        content = (GOLDEN_DIR / source_file).read_text()
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
                {"name": "complex_arithmetic", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_complex_arithmetic'), "weight": 1.0},
                {"name": "matrix_tensor_product", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_matrix_tensor_product'), "weight": 1.0},
                {"name": "hadamard_superposition", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_hadamard_superposition'), "weight": 1.0},
                {"name": "bell_state", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_bell_state'), "weight": 1.0},
                {"name": "unitarity", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_unitarity'), "weight": 1.0},
                {"name": "serialization_roundtrip", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_serialization_roundtrip'), "weight": 1.0},
                {"name": "swarm_ghz_circuit", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_swarm_ghz_circuit'), "weight": 1.0},
                {"name": "evolver_improves_fitness", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_evolver_improves_fitness'), "weight": 1.0},
                {"name": "message_bus_threadsafe", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_message_bus_threadsafe'), "weight": 1.0},
                {"name": "circuit_dag_depth", "command": _inject_and_run('test_quantum_swarm.py', 'TestQuantumSwarmEnterprise::test_circuit_dag_depth'), "weight": 1.0},
            ],
        },
    )
    task.slug = 'quantum-circuit-swarm'
    task.columns = {
        "Name": "Quantum Circuit Designer Swarm",
        "Difficulty": "Extreme",
        "Category": "Multi-Agent System",
        "Failure modes": "Agent struggles with tensor product math (Kronecker product). Often implements matrix multiplication instead of element-wise tensor expansion. Genetic algorithm evolver frequently has fitness function bugs. DAG depth calculation often wrong due to incorrect topological sort."
    }
    task.metadata = {
        "name": "Quantum Circuit Designer Swarm",
        "description": "Enterprise-grade quantum swarm with genetically optimized circuits.",
        "difficulty": "Extreme"
    }


    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup(
                    'quantum_swarm.py',
                    '/home/ubuntu/workspace/quantum_swarm.py',
                ),
            },
        ),
    ]
