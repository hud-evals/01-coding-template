# ast-pilot coding template

Generate 0-to-1 coding tasks from Python or TypeScript source modules and run them on the [HUD platform](https://hud.ai).

The agent starts in a blank workspace, gets a long markdown prompt describing a library to build from scratch, and is graded by running hidden tests against its implementation. The agent never sees the tests, the golden solution, or any support files.

## Setup

```bash
uv sync
cp .env.example .env   # fill in HUD_API_KEY and HUD_ENV_NAME
source .env
```

| Variable | Default | What it does |
| --- | --- | --- |
| `HUD_API_KEY` | required | Auth for LLM calls (HUD inference gateway) and HUD commands |
| `HUD_ENV_NAME` | required | Deployed HUD environment name used by tasks, sync, and eval |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model for prose generation, fixer, and alignment review |
| `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS` | unset | Set to `1` to downgrade unsupported test imports instead of failing |
| `CODING_GITHUB_TOKEN` | unset | Build secret for private repo clones in `Dockerfile.hud` |

`.env` is intentionally excluded from the Docker image. The deployed environment must not depend on it.

## Generating a task

Pick a source module with a few hundred lines of real logic, solid test coverage, a clear API surface, and no live-service dependencies. Then:

```bash
# Python
uv run ast-pilot run path/to/module.py \
    --tests path/to/test_module.py \
    --name my-task

# TypeScript
uv run ast-pilot run path/to/repo/src/*.ts \
    --tests path/to/repo/test/*.test.ts \
    --name my-ts-task
```

Language is auto-inferred from file extensions, or set explicitly with `--language typescript`.

This runs the full pipeline:

1. Scans source and tests into an evidence store
2. Renders `prompt.md` (LLM prose grounded in exact extracted signatures)
3. Validates the prompt against source evidence — refuses to proceed on factual errors
4. Fixes validation issues (up to 3 rounds)
5. Generates the task package (hidden tests, golden solution, support files, `task.py`)
6. Runs prompt-grader alignment (deterministic gap analysis + parallel LLM review of each hidden test file)
7. Auto-fixes safe mismatches, hard-stops on contradictions
8. Promotes the result into `tasks/my_task/`

Use `--no-llm` for fast structural smoke tests. Use `--no-alignment-autofix` to skip the alignment pass.

If hidden tests depend on repo-internal modules the generator can't carry, generation fails by default. Set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1` to downgrade instead.

## Task package structure

```text
tasks/my_task/                     # Python
├── __init__.py
├── task.py                        # HUD wiring, grading commands, golden validation
├── prompt.md                      # what the agent sees
├── tests/                         # hidden pytest files
├── golden/                        # golden source for validation
├── support/                       # hidden repo-internal helpers
└── requirements.hidden.txt        # hidden pip dependencies

tasks/my_ts_task/                  # TypeScript
├── __init__.py
├── task.py
├── prompt.md
├── node_bundle_manifest.json      # manifest-driven staging config
├── tests/                         # hidden test files (repo-relative paths)
├── golden/                        # golden source files (repo-relative paths)
├── support/                       # transitive fixtures and data files
└── config/                        # package.json, lockfile, tsconfig, vitest config
```

Generated `task.py` files hardcode the scenario ID `ast-pilot:coding-task`, load `HUD_ENV_NAME` via `task_bootstrap.py`, and connect to the deployed environment. Grading uses `BashGrader` — each check runs a shell command, exit 0 = pass.

For TypeScript, the grader mirrors the repo tree in a temp directory at grading time, copies agent workspace files in by basename, stages hidden tests at their original paths, and runs `npx vitest run`. The agent never needs to run `npm install`.

### Runtime assets and `REPO_ROOT`

Non-Python files referenced by source or tests via `open(...)`, `sqlite3.connect(...)`, `Path(...) / "..."`, etc. (`.sql`, `.yaml`, `.json`, `.toml`, configs) are auto-detected. Files that exist in the source repo are bundled into `support/` and staged into the workspace before each check. References the scanner cannot resolve to a file on disk are surfaced in `prompt.md` under `Runtime Files → Files you must create` so the agent knows to produce them.

Tests that derive paths from `__file__` — `REPO_ROOT = os.path.dirname(os.path.abspath(__file__))` and friends (`HERE`, `BASE_DIR`, `ROOT_DIR`, `PROJECT_ROOT`) — are rewritten at generation time to read `AST_PILOT_REPO_ROOT` (set to `/home/ubuntu/workspace` at grading time). Without this, tests staged at `/tmp/test_x.py` would resolve sibling files against `/tmp` instead of the agent's workspace.

Detection only activates when the source tree has a repo-root marker (`pyproject.toml` or `package.json`); bare directories are skipped. Both behaviors require the tests to be present at scan time — if you copy hidden tests into `tasks/<name>/tests/` after regen, the rewrite and asset detection won't fire.

## Deploy and validate

```bash
hud build .                                        # build local image
hud deploy . -n "$HUD_ENV_NAME"                    # push to HUD platform
hud eval . integration_test --task-ids my-task -y  # validate the harness
hud eval . claude --task-ids my-task -y --max-steps 30  # run with a real agent
hud sync tasks <taskset-name>                      # upload task definitions
```

**`integration_test`** is the release gate. It checks that the golden solution passes all hidden tests from a blank workspace. A task is not ready until this returns `Reward: 1.000`.

**`hud sync`** uploads prompt + grading commands to the platform. It does not upload the raw files under `tasks/` — those live inside the Docker image from `hud deploy`. After regenerating a task, you need both deploy and sync.

Redeploy whenever you change `env.py`, `Dockerfile.hud`, `pyproject.toml`, `task_bootstrap.py`, support modules, or hidden dependencies.

## TypeScript support

**Supported:** `.ts` source files, single-package repos (npm/pnpm/yarn), vitest.

**Not supported yet:** `.js` input, Jest, `node:test`, monorepo workspaces, tsconfig path aliases, React/TSX/browser stacks.

The runtime image includes Node.js 20+. Runtime file references (`fs.readFileSync(__dirname + '/file.json')`) are detected and bundled, but exotic patterns may be missed.

## Directory layout

```text
01-coding-template/
├── src/ast_pilot/       # scanner, renderer, validator, fixer, alignment, task generator
├── tasks/               # generated task packages
├── env.py               # HUD environment + shared coding scenario
├── cli.py               # MCP server entry point
├── task_bootstrap.py    # local .env loading for generated tasks
├── build_support.py     # hidden support staging during builds
├── Dockerfile.hud       # Ubuntu + Python + Node 20
└── pyproject.toml       # hud-python >= 0.5.35
```

## Troubleshooting

**`HUD_ENV_NAME is required`** — Put `HUD_ENV_NAME=<name>` in `.env` and run `source .env`.

**`ModuleNotFoundError` during integration_test** — Usually a missing helper in `support/`, a missing dependency in `requirements.hidden.txt`, or a bad import rewrite. Check the failing import first.

**Generation fails on unsupported internal modules** — Expected. Pick a simpler source module, trim the test surface, or set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`.

**integration_test shows stale behavior** — The platform is running an old image. Run `hud build . && hud deploy . -n "$HUD_ENV_NAME"` then re-eval.

**integration_test passes but agent scores are low** — The harness is fine; the prompt or task difficulty needs work. Check that all tested symbols are mentioned, implementation notes reflect real test behavior, and the module isn't too broad for the target model.

**Validator flags something that looks correct** — It checks prose against exact extracted facts. Most real failures are signature drift, wrong constants, or renamed fields. Some false positives happen.

## Calibration

A valid task is not necessarily a solvable task. Good heuristics:

- Smaller libraries are easier, but don't go so small it becomes a toy
- Keep the API surface focused and hidden-dependency complexity low
- Prefer one coherent module over a feature spread across half a repo
- Always run real agent evals after integration_test passes

```bash
hud eval . claude --task-ids my-task -y --max-steps 30
```

Run multiple attempts and inspect failures before shipping.
