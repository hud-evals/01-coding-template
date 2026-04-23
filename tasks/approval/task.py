"""Task: build approval from scratch."""

import base64
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

    def _stage_hidden_support(runtime_support_dir: Path) -> str:
        """Copy hidden support modules into a writable runtime directory."""
        support_source = _support_source_dir()
        return (
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "import shutil\n"
            f"support_source = Path({str(support_source)!r})\n"
            f"runtime_support_dir = Path({str(runtime_support_dir)!r})\n"
            "if support_source.is_dir():\n"
            "    if runtime_support_dir.exists():\n"
            "        shutil.rmtree(runtime_support_dir)\n"
            "    runtime_support_dir.parent.mkdir(parents=True, exist_ok=True)\n"
            "    shutil.copytree(support_source, runtime_support_dir)\n"
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
        """Build a bash command that writes a test file and runs pytest via uv run.

        File content is base64-encoded so regex backslash escapes can't be mangled
        by any intermediate shell or transport layer.
        """
        content = (TESTS_DIR / test_file).read_text()
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        runtime_support_dir = RUNTIME_ROOT / Path(test_file).stem / "support"
        stage_support = _stage_hidden_support(runtime_support_dir)
        stage_assets = ""
        pythonpath = f"{WORKSPACE_DIR}:{runtime_support_dir}:$PYTHONPATH"
        uv_cmd = "uv run --no-project --with pytest " f"--with-requirements {BUNDLED_HIDDEN_REQUIREMENTS} " "python -m pytest"
        return (
            f"{stage_support}"
            f"{stage_assets}"
            f"echo '{encoded}' | base64 -d > /tmp/{test_file}\n"
            f"cd {workdir} && AST_PILOT_REPO_ROOT={workdir} PYTHONPATH={pythonpath} "
            f"{uv_cmd} /tmp/{test_file} -v"
        )

    def _golden_setup(source_file: str, dest: str) -> str:
        """Build a bash command that writes the golden solution to the workspace.

        Same base64 treatment as _inject_and_run: immune to backslash-escape
        corruption anywhere in the shell/transport chain.
        """
        content = (GOLDEN_DIR / source_file).read_text()
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        return (
            f"mkdir -p {os.path.dirname(dest)}\n"
            f"echo '{encoded}' | base64 -d > {dest}"
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": 'test_approval',
                    "command": _inject_and_run('test_approval.py'),
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = 'approval'

    task.validation = [
        MCPToolCall(
            name="bash",
            arguments={
                "command": _golden_setup('tools/approval.py', '/home/ubuntu/workspace/tools/approval.py'),
            },
        ),
    ]
