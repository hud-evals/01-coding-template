"""Task: build hermes_retry from scratch."""

import os
import hashlib
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

    WORKSPACE_DIR = "/home/ubuntu/workspace"
    REPO_ROOT_ENV = "AST_PILOT_REPO_ROOT"

    TESTS_DIR = TASK_DIR / "tests"
    GOLDEN_DIR = TASK_DIR / "golden"
    IMAGE_TASK_DIR = Path("/mcp_server/tasks") / TASK_DIR.name
    LEGACY_SUPPORT_DIR = Path('/opt/ast_pilot_support') / TASK_DIR.name
    BUNDLED_SUPPORT_DIR = IMAGE_TASK_DIR / "support"
    RUNTIME_ROOT = Path("/tmp/ast_pilot_task_runtime") / TASK_DIR.name
    LOCAL_HIDDEN_REQUIREMENTS = TASK_DIR / "requirements.hidden.txt"
    BUNDLED_HIDDEN_REQUIREMENTS = IMAGE_TASK_DIR / "requirements.hidden.txt"
    BUNDLED_ASSETS = []

    def _support_source_dir() -> Path | None:
        if LEGACY_SUPPORT_DIR.is_dir():
            return LEGACY_SUPPORT_DIR
        return BUNDLED_SUPPORT_DIR

    def _requirements_marker() -> Path:
        digest = "none"
        if LOCAL_HIDDEN_REQUIREMENTS.is_file():
            digest = hashlib.sha256(LOCAL_HIDDEN_REQUIREMENTS.read_bytes()).hexdigest()[:12]
        return RUNTIME_ROOT / f".requirements-{digest}.ok"

    def _prepare_hidden_runtime(test_file: str, runtime_support_dir: Path) -> str:
        """Build a bash command that exposes hidden support/runtime deps for grading."""
        support_source = _support_source_dir()
        requirements_marker = _requirements_marker()
        return (
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "import shutil\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            f"support_source = Path({str(support_source)!r})\n"
            f"runtime_support_dir = Path({str(runtime_support_dir)!r})\n"
            f"hidden_requirements = Path({str(BUNDLED_HIDDEN_REQUIREMENTS)!r})\n"
            f"requirements_marker = Path({str(requirements_marker)!r})\n"
            f"requirements_lock = Path({str(requirements_marker.parent / (requirements_marker.name + '.lock'))!r})\n"
            "if support_source.is_dir():\n"
            "    if runtime_support_dir.exists():\n"
            "        shutil.rmtree(runtime_support_dir)\n"
            "    runtime_support_dir.parent.mkdir(parents=True, exist_ok=True)\n"
            "    shutil.copytree(support_source, runtime_support_dir)\n"
            "if hidden_requirements.is_file() and not requirements_marker.exists():\n"
            "    while True:\n"
            "        try:\n"
            "            requirements_lock.mkdir(parents=True, exist_ok=False)\n"
            "            break\n"
            "        except FileExistsError:\n"
            "            if requirements_marker.exists():\n"
            "                break\n"
            "            time.sleep(0.1)\n"
            "    if not requirements_marker.exists():\n"
            "        try:\n"
            "            subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(hidden_requirements)], check=True)\n"
            "            requirements_marker.parent.mkdir(parents=True, exist_ok=True)\n"
            "            requirements_marker.write_text('ok', encoding='utf-8')\n"
            "        finally:\n"
            "            if requirements_lock.exists():\n"
            "                requirements_lock.rmdir()\n"
            "PY\n"
        )

    def _stage_runtime_assets(source_dir: Path | None) -> str:
        """Copy bundled non-code assets into the workspace (no-clobber)."""
        if not BUNDLED_ASSETS or source_dir is None:
            return ""
        parts: list[str] = []
        for rel in BUNDLED_ASSETS:
            src = f"{source_dir}/{rel}"
            dst = f"{WORKSPACE_DIR}/{rel}"
            dst_dir = os.path.dirname(dst) or "/"
            parts.append(f"mkdir -p '{dst_dir}'")
            parts.append(f"cp -n '{src}' '{dst}' 2>/dev/null || true")
        return "; ".join(parts) + "; "

    def _inject_and_run(test_file: str, workdir: str = "/home/ubuntu/workspace") -> str:
        """Build a bash command that writes a test file and runs pytest."""
        content = (TESTS_DIR / test_file).read_text()
        runtime_support_dir = RUNTIME_ROOT / Path(test_file).stem / "support"
        prepare = ""
        stage_assets = ""
        pythonpath = '/home/ubuntu/workspace:$PYTHONPATH'
        return (
            f"{prepare}"
            f"{stage_assets}"
            f"cat > /tmp/{test_file} << 'TESTEOF'\n"
            f"{content}\n"
            f"TESTEOF\n"
            f"cd {workdir} && AST_PILOT_REPO_ROOT={workdir} PYTHONPATH={pythonpath} python -m pytest /tmp/{test_file} -v"
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
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": 'test_retry_utils',
                    "command": _inject_and_run('test_retry_utils.py'),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = 'hermes-retry'

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('agent/retry_utils.py', '/home/ubuntu/workspace/agent/retry_utils.py'),
            },
        ),
    ]
