"""HUD task definition for TypeScript project."""

import json
import os
from pathlib import Path

from hud.eval.task import Task
from hud.types import MCPToolCall

if not os.environ.get('_HUD_DEV_CHILD'):
    from hud import Environment

    SCENARIO_ID = "ast-pilot:coding-task"
    TASK_DIR = Path(__file__).parent
    IMAGE_TASK_DIR = Path("/mcp_server/tasks") / TASK_DIR.name

    from task_bootstrap import require_hud_env_name

    ENV_NAME = require_hud_env_name(
        TASK_DIR.parents[1] / '.env',
        allow_analysis_placeholder=True,
        error_message="HUD_ENV_NAME is required. Set it before running this task.",
    )

    WORKSPACE_DIR = "/home/ubuntu/workspace"
    STAGING_DIR = '/tmp/ast_pilot_node_defu'
    NODE_MODULES_CACHE = '/tmp/ast_pilot_node_defu_modules'
    TESTS_DIR = TASK_DIR / 'tests'
    GOLDEN_DIR = TASK_DIR / 'golden'
    SUPPORT_DIR = TASK_DIR / 'support'
    CONFIG_DIR = TASK_DIR / 'config'
    BUNDLED_CONFIG_DIR = IMAGE_TASK_DIR / 'config'
    BUNDLED_SUPPORT_DIR = IMAGE_TASK_DIR / 'support'
    MANIFEST_PATH = TASK_DIR / 'node_bundle_manifest.json'

    env = Environment(ENV_NAME)
    env.connect_hub(ENV_NAME)

    def _load_manifest() -> dict:
        bundled = IMAGE_TASK_DIR / 'node_bundle_manifest.json'
        p = bundled if bundled.is_file() else MANIFEST_PATH
        return json.loads(p.read_text(encoding='utf-8'))

    def _prepare_hidden_runtime(test_rel: str) -> str:
        """Build a bash command that stages the mirrored repo tree."""
        manifest = _load_manifest()

        parts = []

        parts.append(
            f'CONFIG_SRC={BUNDLED_CONFIG_DIR}; '
            f'if [ ! -d $CONFIG_SRC ]; then CONFIG_SRC={CONFIG_DIR}; fi; '
            f'SUPPORT_SRC={BUNDLED_SUPPORT_DIR}; '
            f'if [ ! -d $SUPPORT_SRC ]; then SUPPORT_SRC={SUPPORT_DIR}; fi'
        )

        all_dirs = set()
        for section in ('source_files', 'test_files', 'support_files', 'config_files'):
            for rel in manifest.get(section, {}):
                parent = str(Path(rel).parent)
                if parent and parent != '.':
                    all_dirs.add(f'{STAGING_DIR}/{parent}')
        if all_dirs:
            parts.append(f'mkdir -p {" ".join(sorted(all_dirs))}')
        parts.append(f'mkdir -p {STAGING_DIR}')

        parts.append(
            f'if [ ! -f {NODE_MODULES_CACHE}/.installed ]; then '
            f'  mkdir -p {NODE_MODULES_CACHE} && '
            f'  cp $CONFIG_SRC/package.json {NODE_MODULES_CACHE}/ && '
            f'  cp $CONFIG_SRC/package-lock.json {NODE_MODULES_CACHE}/ 2>/dev/null; '
            f'  cp $CONFIG_SRC/.npmrc {NODE_MODULES_CACHE}/ 2>/dev/null; '
            f'  cd {NODE_MODULES_CACHE} && '
            f'  (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts) && '
            f'  touch {NODE_MODULES_CACHE}/.installed; '
            f'fi'
        )

        for rel in sorted(manifest.get('config_files', {})):
            name = Path(rel).name
            parts.append(f'cp $CONFIG_SRC/{name} {STAGING_DIR}/{rel} 2>/dev/null')

        parts.append(
            f'if [ -d {NODE_MODULES_CACHE}/node_modules ]; then '
            f'  ln -sfn {NODE_MODULES_CACHE}/node_modules {STAGING_DIR}/node_modules; '
            f'else '
            f'  cd {STAGING_DIR} && (npm ci --ignore-scripts 2>/dev/null || npm install --legacy-peer-deps --ignore-scripts); '
            f'fi'
        )

        for rel in sorted(manifest.get('source_files', {})):
            basename = Path(rel).name
            parts.append(f'cp {WORKSPACE_DIR}/{basename} {STAGING_DIR}/{rel} 2>/dev/null')

        for rel in sorted(manifest.get('support_files', {})):
            parts.append(f'cp $SUPPORT_SRC/{rel} {STAGING_DIR}/{rel} 2>/dev/null')

        return '; '.join(parts) + '; '

    def _inject_and_run(test_rel: str) -> str:
        """Build a bash command that writes a hidden test file and runs vitest."""
        content = (TESTS_DIR / test_rel).read_text()
        dest = f'{STAGING_DIR}/{test_rel}'
        return (
            f'{_prepare_hidden_runtime(test_rel)}'
            f"cat > {dest} << 'TESTEOF'\n"
            f'{content}\n'
            f'TESTEOF\n'
            f'cd {STAGING_DIR} && npx vitest run {test_rel} --reporter=verbose'
        )

    def _golden_setup(source_rel: str, dest: str) -> str:
        """Build a bash command that writes the golden solution to the workspace."""
        content = (GOLDEN_DIR / source_rel).read_text()
        return (
            f'mkdir -p {os.path.dirname(dest)}\n'
            f"cat > {dest} << 'GOLDENEOF'\n"
            f'{content}\n'
            f'GOLDENEOF'
        )

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
            {"name": 'test/defu.test.ts', "command": _inject_and_run('test/defu.test.ts'), "weight": 0.5},
            {"name": 'test/utils.test.ts', "command": _inject_and_run('test/utils.test.ts'), "weight": 0.5},
            ],
        },
    )
    task.slug = 'defu'

    task.validation = [
        MCPToolCall(name="bash", arguments={"command": _golden_setup('src/_utils.ts', '/home/ubuntu/workspace/_utils.ts')}),
        MCPToolCall(name="bash", arguments={"command": _golden_setup('src/defu.ts', '/home/ubuntu/workspace/defu.ts')}),
        MCPToolCall(name="bash", arguments={"command": _golden_setup('src/types.ts', '/home/ubuntu/workspace/types.ts')}),
    ]
