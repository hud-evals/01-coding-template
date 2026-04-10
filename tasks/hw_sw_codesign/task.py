"""Task: Hardware-Software Co-Design Collective."""

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
        content = (GOLDEN_DIR / "codesign_engine.py").read_text(encoding="utf-8")
        return (
            f"cat > /home/ubuntu/workspace/codesign_engine.py << 'GOLDENEOF'\n"
            f"{content}\n"
            f"GOLDENEOF"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(encoding="utf-8"),
            "bash_checks": [
                {"name": "isa_add_count", "command": _inject_and_run("test_architecture.py", "test_isa_add_and_count"), "weight": 1.0},
                {"name": "isa_avg_power", "command": _inject_and_run("test_architecture.py", "test_isa_avg_power"), "weight": 1.0},
                {"name": "risc_arch", "command": _inject_and_run("test_architecture.py", "test_risc_architecture"), "weight": 1.0},
                {"name": "neuro_arch", "command": _inject_and_run("test_architecture.py", "test_neuromorphic_architecture"), "weight": 1.0},
                {"name": "compare_arch", "command": _inject_and_run("test_architecture.py", "test_compare_architectures"), "weight": 1.0},
                {"name": "validate_valid", "command": _inject_and_run("test_compiler.py", "test_validate_valid_program"), "weight": 1.0},
                {"name": "validate_invalid", "command": _inject_and_run("test_compiler.py", "test_validate_invalid_opcode"), "weight": 1.0},
                {"name": "dead_code_elim", "command": _inject_and_run("test_compiler.py", "test_dead_code_elimination"), "weight": 1.0},
                {"name": "strength_reduce", "command": _inject_and_run("test_compiler.py", "test_strength_reduction"), "weight": 1.0},
                {"name": "full_optimize", "command": _inject_and_run("test_compiler.py", "test_full_optimize"), "weight": 1.0},
                {"name": "sim_add", "command": _inject_and_run("test_simulator.py", "test_simple_add_simulation"), "weight": 1.0},
                {"name": "sim_mul_div", "command": _inject_and_run("test_simulator.py", "test_mul_div_simulation"), "weight": 1.0},
                {"name": "sim_energy", "command": _inject_and_run("test_simulator.py", "test_energy_tracking"), "weight": 1.0},
                {"name": "sim_div_zero", "command": _inject_and_run("test_simulator.py", "test_div_by_zero"), "weight": 1.0},
                {"name": "bench_grade", "command": _inject_and_run("test_benchmark_fab.py", "test_benchmark_grading"), "weight": 1.0},
                {"name": "fab_estimate", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_estimate"), "weight": 1.0},
                {"name": "fab_invalid_node", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_invalid_node"), "weight": 1.0},
                {"name": "fab_recommend", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_recommendation"), "weight": 1.0},
                {"name": "fab_no_budget", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_no_budget"), "weight": 1.0},
                {"name": "bus_threadsafe", "command": _inject_and_run("test_orchestrator.py", "test_message_bus_thread_safety"), "weight": 1.0},
                {"name": "orch_risc", "command": _inject_and_run("test_orchestrator.py", "test_orchestrator_risc_pipeline"), "weight": 1.0},
                {"name": "orch_no_prog", "command": _inject_and_run("test_orchestrator.py", "test_orchestrator_no_program"), "weight": 1.0},
                {"name": "sim_branch_beq", "command": _inject_and_run("test_simulator.py", "test_branch_beq"), "weight": 1.0},
                {"name": "sim_store_load", "command": _inject_and_run("test_simulator.py", "test_store_load_memory"), "weight": 1.0},
                {"name": "sim_timeout", "command": _inject_and_run("test_simulator.py", "test_max_cycles_timeout"), "weight": 1.0},
                {"name": "bench_grade_f", "command": _inject_and_run("test_benchmark_fab.py", "test_benchmark_grade_f"), "weight": 1.0},
                {"name": "fab_exact_transistors", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_exact_transistor_count"), "weight": 1.0},
                {"name": "fab_7nm_vs_28nm", "command": _inject_and_run("test_benchmark_fab.py", "test_fabrication_7nm_vs_28nm"), "weight": 1.0},
            ]
        }
    )

    task.slug = "hw-sw-codesign"
    task.columns = {
        "Name": "HW-SW Co-Design Collective",
        "Difficulty": "Extreme",
        "Category": "Hardware Engineering",
        "Failure modes": "Incorrect ISA instruction counts, simulator register resolution bugs, strength reduction operand mapping errors, fabrication transistor math, thread-safety race conditions."
    }
    task.metadata = {
        "name": "Hardware-Software Co-Design Collective",
        "description": "Multi-agent system bridging chip architecture design, compiler optimization, CPU simulation, and fabrication analysis.",
        "difficulty": "Extreme"
    }

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={"command": _golden_setup()},
        ),
    ]
