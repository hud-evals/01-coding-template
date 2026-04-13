"""Generate HUD task bundles for TypeScript/Node projects.

Produces a task package that stages a temporary Node project at grading
time, copies hidden tests and golden files into it, runs ``npm ci`` once,
then executes ``vitest run`` per test file.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .evidence import Evidence
from .node_repo_support import detect_node_project

WORKSPACE_DIR = "/home/ubuntu/workspace"


def generate_graders(
    ev: Evidence,
    output_dir: str | Path,
    prompt_md: str | None = None,
    source_paths: list[str | Path] | None = None,
    test_paths: list[str | Path] | None = None,
) -> dict[str, str]:
    """Generate a complete TypeScript task bundle under *output_dir*."""

    output_dir = Path(output_dir)
    slug = _slug(ev.project_name)
    task_dir = output_dir / "tasks" / slug
    tests_dir = task_dir / "tests"
    golden_dir = task_dir / "golden"
    config_dir = task_dir / "config"

    for d in (task_dir, tests_dir, golden_dir, config_dir):
        d.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    init_content = ""
    _write(task_dir / "__init__.py", init_content)
    files[f"tasks/{slug}/__init__.py"] = init_content

    prompt_content = _load_prompt(output_dir, ev.project_name, prompt_md=prompt_md)
    _write(task_dir / "prompt.md", prompt_content)
    files[f"tasks/{slug}/prompt.md"] = prompt_content

    resolved_sources = [Path(p) for p in (source_paths or [mod.path for mod in ev.source_files])]
    resolved_tests = [Path(p) for p in (test_paths or [])]

    for src in resolved_sources:
        if src.exists():
            content = src.read_text(encoding="utf-8")
            dest = golden_dir / src.name
            _write(dest, content)
            files[f"tasks/{slug}/golden/{src.name}"] = content

    for test_file in resolved_tests:
        if test_file.exists():
            content = test_file.read_text(encoding="utf-8")
            dest = tests_dir / test_file.name
            _write(dest, content)
            files[f"tasks/{slug}/tests/{test_file.name}"] = content

    ctx = detect_node_project(resolved_sources)
    _copy_config_files(ctx, config_dir, files, slug)

    test_file_names = sorted(p.name for p in tests_dir.glob("*.ts"))
    if not test_file_names:
        test_file_names = sorted(p.name for p in tests_dir.glob("*test*"))

    golden_file_names = sorted(p.name for p in golden_dir.iterdir() if p.is_file())

    task_py = _generate_task_py(
        ev=ev,
        slug=slug,
        test_files=test_file_names,
        golden_files=golden_file_names,
    )
    _write(task_dir / "task.py", task_py)
    files[f"tasks/{slug}/task.py"] = task_py

    return files


def _copy_config_files(ctx, config_dir: Path, files: dict[str, str], slug: str) -> None:
    """Copy Node project config files into the task bundle."""
    root = ctx.root

    for name in ("package.json", "package-lock.json"):
        src = root / name
        if src.exists():
            content = src.read_text(encoding="utf-8")
            _write(config_dir / name, content)
            files[f"tasks/{slug}/config/{name}"] = content

    if ctx.tsconfig_path and ctx.tsconfig_path.exists():
        content = ctx.tsconfig_path.read_text(encoding="utf-8")
        _write(config_dir / ctx.tsconfig_path.name, content)
        files[f"tasks/{slug}/config/{ctx.tsconfig_path.name}"] = content

    if ctx.vitest_config_path and ctx.vitest_config_path.exists():
        content = ctx.vitest_config_path.read_text(encoding="utf-8")
        _write(config_dir / ctx.vitest_config_path.name, content)
        files[f"tasks/{slug}/config/{ctx.vitest_config_path.name}"] = content


def _generate_task_py(
    ev: Evidence,
    slug: str,
    test_files: list[str],
    golden_files: list[str],
) -> str:
    """Generate the task.py content for a TypeScript task."""

    weight_per_check = round(1.0 / max(len(test_files), 1), 4)

    checks_items = []
    for test_file in test_files:
        checks_items.append(
            f'            {{"name": {test_file!r}, "command": _inject_and_run({test_file!r}), "weight": {weight_per_check}}},'
        )

    validation_items = []
    for golden_file in golden_files:
        dest = f"{WORKSPACE_DIR}/{golden_file}"
        validation_items.append(
            f'        MCPToolCall(name="bash", arguments={{"command": _golden_setup({golden_file!r}, {dest!r})}}),',
        )

    lines = [
        '"""HUD task definition for TypeScript project."""',
        "",
        "import os",
        "import subprocess",
        "import time",
        "from pathlib import Path",
        "",
        "from hud.eval.task import Task",
        "from hud.types import MCPToolCall",
        "",
        "if not os.environ.get('_HUD_DEV_CHILD'):",
        "    from hud import Environment",
        "",
        '    SCENARIO_ID = "ast-pilot:coding-task"',
        "    TASK_DIR = Path(__file__).parent",
        '    IMAGE_TASK_DIR = Path("/mcp_server/tasks") / TASK_DIR.name',
        "",
        "    from task_bootstrap import require_hud_env_name",
        "",
        "    ENV_NAME = require_hud_env_name(",
        "        TASK_DIR.parents[1] / '.env',",
        "        allow_analysis_placeholder=True,",
        '        error_message="HUD_ENV_NAME is required. Set it before running this task.",',
        "    )",
        "",
        f'    WORKSPACE_DIR = "{WORKSPACE_DIR}"',
        f"    STAGING_DIR = '/tmp/ast_pilot_node_{slug}'",
        f"    NODE_MODULES_CACHE = '/tmp/ast_pilot_node_{slug}_modules'",
        "    INSTALL_MARKER = Path(f'{NODE_MODULES_CACHE}/.installed')",
        "    TESTS_DIR = TASK_DIR / 'tests'",
        "    GOLDEN_DIR = TASK_DIR / 'golden'",
        "    CONFIG_DIR = TASK_DIR / 'config'",
        "    BUNDLED_CONFIG_DIR = IMAGE_TASK_DIR / 'config'",
        "",
        "    env = Environment(ENV_NAME)",
        "    env.connect_hub(ENV_NAME)",
        "",
        "    def _prepare_hidden_runtime() -> str:",
        '        """Build a bash command that sets up the Node project once, then reuses it.',
        "",
        "        Uses shell-level path resolution so it works both inside the",
        "        Docker image (BUNDLED_CONFIG_DIR) and locally (CONFIG_DIR).",
        '        """',
        "        return (",
        '            f"CONFIG_SRC={BUNDLED_CONFIG_DIR}; "',
        '            f"if [ ! -d $CONFIG_SRC ]; then CONFIG_SRC={CONFIG_DIR}; fi; "',
        '            f"if [ ! -f {NODE_MODULES_CACHE}/.installed ]; then "',
        '            f"  mkdir -p {NODE_MODULES_CACHE} && "',
        '            f"  cp $CONFIG_SRC/package.json {NODE_MODULES_CACHE}/ && "',
        '            f"  cp $CONFIG_SRC/package-lock.json {NODE_MODULES_CACHE}/ 2>/dev/null; "',
        '            f"  cd {NODE_MODULES_CACHE} && "',
        '            f"  (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts) && "',
        '            f"  touch {NODE_MODULES_CACHE}/.installed; "',
        '            f"fi; "',
        '            f"mkdir -p {STAGING_DIR}/src {STAGING_DIR}/tests && "',
        '            f"cp $CONFIG_SRC/package.json {STAGING_DIR}/ && "',
        '            f"cp $CONFIG_SRC/package-lock.json {STAGING_DIR}/ 2>/dev/null; "',
        '            f"cp $CONFIG_SRC/tsconfig*.json {STAGING_DIR}/ 2>/dev/null; "',
        '            f"cp $CONFIG_SRC/vitest*.* {STAGING_DIR}/ 2>/dev/null; "',
        '            f"cp $CONFIG_SRC/vite*.* {STAGING_DIR}/ 2>/dev/null; "',
        '            f"if [ -d {NODE_MODULES_CACHE}/node_modules ]; then "',
        '            f"  ln -sfn {NODE_MODULES_CACHE}/node_modules {STAGING_DIR}/node_modules; "',
        '            f"else "',
        '            f"  cd {STAGING_DIR} && (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts); "',
        '            f"fi; "',
        '            f"cp {WORKSPACE_DIR}/*.ts {STAGING_DIR}/src/ 2>/dev/null; "',
        '            f"cp {WORKSPACE_DIR}/*.mts {STAGING_DIR}/src/ 2>/dev/null; "',
        '            f"cp {WORKSPACE_DIR}/*.ts {STAGING_DIR}/tests/ 2>/dev/null; "',
        '            f"cp {WORKSPACE_DIR}/*.mts {STAGING_DIR}/tests/ 2>/dev/null; "',
        "        )",
        "",
        "    def _inject_and_run(test_file: str) -> str:",
        '        """Build a bash command that writes a test file and runs vitest."""',
        "        content = (TESTS_DIR / test_file).read_text()",
        "        return (",
        '            f"{_prepare_hidden_runtime()}"',
        '            f"cat > {STAGING_DIR}/tests/{test_file} << \'TESTEOF\'\\n"',
        '            f"{content}\\n"',
        '            f"TESTEOF\\n"',
        '            f"cd {STAGING_DIR} && npx vitest run tests/{test_file} --reporter=verbose"',
        "        )",
        "",
        "    def _golden_setup(source_file: str, dest: str) -> str:",
        '        """Build a bash command that writes the golden solution to the workspace."""',
        "        content = (GOLDEN_DIR / source_file).read_text()",
        "        return (",
        '            f"mkdir -p {os.path.dirname(dest)}\\n"',
        '            f"cat > {dest} << \'GOLDENEOF\'\\n"',
        '            f"{content}\\n"',
        '            f"GOLDENEOF"',
        "        )",
        "",
        "    task = Task(",
        "        env=env,",
        "        scenario=SCENARIO_ID,",
        "        args={",
        '            "prompt": (TASK_DIR / "prompt.md").read_text(),',
        '            "bash_checks": [',
    ]
    lines.extend(checks_items)
    lines += [
        "            ],",
        "        },",
        "    )",
        f"    task.slug = {slug!r}",
        "",
        "    task.validation = [",
    ]
    lines.extend(validation_items)
    lines += [
        "    ]",
        "",
    ]
    return "\n".join(lines)


def _load_prompt(output_root: Path, project_name: str, prompt_md: str | None = None) -> str:
    if prompt_md:
        return prompt_md

    candidates = [
        output_root / "start.md",
        output_root / "prompt.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")

    return f"# {project_name}\n\nImplement the TypeScript library described below.\n"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
