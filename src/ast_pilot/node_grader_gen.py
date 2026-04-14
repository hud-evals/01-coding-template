"""Generate HUD task bundles for TypeScript/Node projects.

Produces a task package that stages a temporary Node project at grading
time using a manifest-driven approach that preserves repo-relative paths,
bundles transitive local dependencies of hidden tests, and runs
``vitest run`` per test file.
"""

from __future__ import annotations

import os
from pathlib import Path

from .evidence import Evidence
from .node_bundle import NodeBundleManifest, audit_bare_imports, build_manifest
from .node_repo_support import detect_node_project
from .shared_utils import slug as _slug, write_text as _write

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
    support_dir = task_dir / "support"

    for d in (task_dir, tests_dir, golden_dir, config_dir, support_dir):
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

    ctx = detect_node_project(
        resolved_sources,
        require_lockfile=True,
        auto_generate_lockfile=True,
    )
    repo_root = ctx.root

    config_paths: list[Path] = []
    for name in ("package.json", "package-lock.json", ".npmrc"):
        candidate = repo_root / name
        if candidate.exists():
            config_paths.append(candidate)
    if ctx.tsconfig_path and ctx.tsconfig_path.exists():
        config_paths.append(ctx.tsconfig_path)
    if ctx.vitest_config_path and ctx.vitest_config_path.exists():
        config_paths.append(ctx.vitest_config_path)

    manifest = build_manifest(
        slug=slug,
        repo_root=repo_root,
        source_paths=resolved_sources,
        test_paths=resolved_tests,
        config_paths=config_paths,
    )

    dep_issues = audit_bare_imports(manifest, ctx.package_json)
    if dep_issues:
        issues_str = "\n".join(f"  - {i}" for i in dep_issues)
        raise ValueError(
            f"Hidden test dependency audit failed:\n{issues_str}\n"
            "All bare imports used by hidden tests must be declared in package.json."
        )

    for rel, content in manifest.source_files.items():
        dest = golden_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/golden/{rel}"] = content

    for rel, content in manifest.test_files.items():
        dest = tests_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/tests/{rel}"] = content

    for rel, content in manifest.support_files.items():
        dest = support_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write(dest, content)
        files[f"tasks/{slug}/support/{rel}"] = content

    for rel, content in manifest.config_files.items():
        name = Path(rel).name
        _write(config_dir / name, content)
        files[f"tasks/{slug}/config/{name}"] = content

    manifest_json = manifest.to_json()
    _write(task_dir / "node_bundle_manifest.json", manifest_json)
    files[f"tasks/{slug}/node_bundle_manifest.json"] = manifest_json

    test_rel_paths = sorted(manifest.test_files.keys())
    golden_rel_paths = sorted(manifest.source_files.keys())

    task_py = _generate_task_py(
        ev=ev,
        slug=slug,
        test_files=test_rel_paths,
        golden_files=golden_rel_paths,
    )
    _write(task_dir / "task.py", task_py)
    files[f"tasks/{slug}/task.py"] = task_py

    return files


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
        basename = Path(golden_file).name
        dest = f"{WORKSPACE_DIR}/{basename}"
        validation_items.append(
            f'        MCPToolCall(name="bash", arguments={{"command": _golden_setup({golden_file!r}, {dest!r})}}),',
        )

    lines = [
        '"""HUD task definition for TypeScript project."""',
        "",
        "import json",
        "import os",
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
        "    TESTS_DIR = TASK_DIR / 'tests'",
        "    GOLDEN_DIR = TASK_DIR / 'golden'",
        "    SUPPORT_DIR = TASK_DIR / 'support'",
        "    CONFIG_DIR = TASK_DIR / 'config'",
        "    BUNDLED_CONFIG_DIR = IMAGE_TASK_DIR / 'config'",
        "    BUNDLED_SUPPORT_DIR = IMAGE_TASK_DIR / 'support'",
        "    MANIFEST_PATH = TASK_DIR / 'node_bundle_manifest.json'",
        "",
        "    env = Environment(ENV_NAME)",
        "    env.connect_hub(ENV_NAME)",
        "",
        "    def _load_manifest() -> dict:",
        "        bundled = IMAGE_TASK_DIR / 'node_bundle_manifest.json'",
        "        p = bundled if bundled.is_file() else MANIFEST_PATH",
        "        return json.loads(p.read_text(encoding='utf-8'))",
        "",
        "    def _prepare_hidden_runtime(test_rel: str) -> str:",
        '        """Build a bash command that stages the mirrored repo tree."""',
        "        manifest = _load_manifest()",
        "",
        "        parts = []",
        "",
        "        parts.append(",
        "            f'CONFIG_SRC={BUNDLED_CONFIG_DIR}; '",
        "            f'if [ ! -d $CONFIG_SRC ]; then CONFIG_SRC={CONFIG_DIR}; fi; '",
        "            f'SUPPORT_SRC={BUNDLED_SUPPORT_DIR}; '",
        "            f'if [ ! -d $SUPPORT_SRC ]; then SUPPORT_SRC={SUPPORT_DIR}; fi'",
        "        )",
        "",
        "        all_dirs = set()",
        "        for section in ('source_files', 'test_files', 'support_files', 'config_files'):",
        "            for rel in manifest.get(section, {}):",
        "                parent = str(Path(rel).parent)",
        "                if parent and parent != '.':",
        "                    all_dirs.add(f'{STAGING_DIR}/{parent}')",
        "        if all_dirs:",
        "            parts.append(f'mkdir -p {\" \".join(sorted(all_dirs))}')",
        "        parts.append(f'mkdir -p {STAGING_DIR}')",
        "",
        "        parts.append(",
        "            f'if [ ! -f {NODE_MODULES_CACHE}/.installed ]; then '",
        "            f'  mkdir -p {NODE_MODULES_CACHE} && '",
        "            f'  cp $CONFIG_SRC/package.json {NODE_MODULES_CACHE}/ && '",
        "            f'  cp $CONFIG_SRC/package-lock.json {NODE_MODULES_CACHE}/ 2>/dev/null; '",
        "            f'  cp $CONFIG_SRC/.npmrc {NODE_MODULES_CACHE}/ 2>/dev/null; '",
        "            f'  cd {NODE_MODULES_CACHE} && '",
        "            f'  (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts) && '",
        "            f'  touch {NODE_MODULES_CACHE}/.installed; '",
        "            f'fi'",
        "        )",
        "",
        "        for rel in sorted(manifest.get('config_files', {})):",
        "            name = Path(rel).name",
        "            parts.append(f'cp $CONFIG_SRC/{name} {STAGING_DIR}/{rel} 2>/dev/null')",
        "",
        "        parts.append(",
        "            f'if [ -d {NODE_MODULES_CACHE}/node_modules ]; then '",
        "            f'  ln -sfn {NODE_MODULES_CACHE}/node_modules {STAGING_DIR}/node_modules; '",
        "            f'else '",
        "            f'  cd {STAGING_DIR} && (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts); '",
        "            f'fi'",
        "        )",
        "",
        "        for rel in sorted(manifest.get('source_files', {})):",
        "            basename = Path(rel).name",
        "            parts.append(f'cp {WORKSPACE_DIR}/{basename} {STAGING_DIR}/{rel} 2>/dev/null')",
        "",
        "        for rel in sorted(manifest.get('support_files', {})):",
        "            parts.append(f'cp $SUPPORT_SRC/{rel} {STAGING_DIR}/{rel} 2>/dev/null')",
        "",
        "        return '; '.join(parts) + '; '",
        "",
        "    def _inject_and_run(test_rel: str) -> str:",
        '        """Build a bash command that writes a hidden test file and runs vitest."""',
        "        content = (TESTS_DIR / test_rel).read_text()",
        "        dest = f'{STAGING_DIR}/{test_rel}'",
        "        return (",
        "            f'{_prepare_hidden_runtime(test_rel)}'",
        "            f\"cat > {dest} << 'TESTEOF'\\n\"",
        "            f'{content}\\n'",
        "            f'TESTEOF\\n'",
        "            f'cd {STAGING_DIR} && npx vitest run {test_rel} --reporter=verbose'",
        "        )",
        "",
        "    def _golden_setup(source_rel: str, dest: str) -> str:",
        '        """Build a bash command that writes the golden solution to the workspace."""',
        "        content = (GOLDEN_DIR / source_rel).read_text()",
        "        return (",
        "            f'mkdir -p {os.path.dirname(dest)}\\n'",
        "            f\"cat > {dest} << 'GOLDENEOF'\\n\"",
        "            f'{content}\\n'",
        "            f'GOLDENEOF'",
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
        output_root / "prompt.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")

    return f"# {project_name}\n\nImplement the TypeScript library described below.\n"
