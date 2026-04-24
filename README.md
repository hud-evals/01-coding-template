# ast-pilot coding template

Generate 0-to-1 coding tasks from Python or TypeScript source modules and run them on the [HUD platform](https://hud.ai).

The agent starts in a blank workspace, gets a long markdown prompt describing a library to build from scratch, and is graded by running hidden tests against its implementation. The agent never sees the tests, the golden solution, or any support files.

---

## The loop — zero to shipped task in about a minute

After the one-time environment setup below, every new task follows a three-command loop. **No Docker rebuild. No `hud deploy`.** Task content (prompt, hidden tests, golden solution, support modules, hidden deps) rides inside `Task.args`; `hud sync` uploads them directly to the platform.

```bash
# 1. Generate the task from a source module + tests
uv run ast-pilot run path/to/module.py \
    --tests path/to/test_module.py \
    --name my-task

# 2. Upload to the platform (seconds, no image involved)
hud sync tasks -y

# 3. Validate the harness — golden solution must score 1.0
hud eval "$HUD_ENV_NAME" integration_test --task-ids my-task -y
```

That's it. The task is live on the platform and you can now run it against a real agent:

```bash
hud eval "$HUD_ENV_NAME" claude --task-ids my-task -y --max-steps 30
```

Iterate on any task by editing its source / tests / prompt and re-running **steps 1-3**. Shipping a fleet of tasks? Same three commands per task, or `hud sync tasks -y` once to push all locally-staged tasks.

The only time you need `hud deploy` is the initial environment setup — or when you change the scenario itself, the runtime image, or Python dependencies. See [When you need `hud deploy`](#when-you-need-hud-deploy) below.

---

## One-time environment setup

```bash
uv sync
cp .env.example .env   # fill in HUD_API_KEY and HUD_ENV_NAME
source .env
hud deploy .           # builds the runtime image + registers the scenarios
```

| Variable | Default | What it does |
| --- | --- | --- |
| `HUD_API_KEY` | required | Auth for HUD platform and LLM inference gateway |
| `HUD_ENV_NAME` | required | Deployed HUD environment name used by tasks, sync, and eval |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model for prompt generation, fixer, and alignment review |
| `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS` | unset | Set to `1` to downgrade unsupported test imports instead of failing |
| `CODING_GITHUB_TOKEN` | unset | Build secret for private repo clones in `Dockerfile.hud` |

`.env` is excluded from the Docker image. Runtime env vars are injected by the HUD platform when the container starts.

After `hud deploy` completes you'll see both scenarios registered — `ast-pilot:coding-task-v2` (the sync-only scenario used by all newly-generated tasks) and `ast-pilot:coding-task` (kept for backward compatibility with legacy image-baked tasks).

## When you need `hud deploy`

You re-deploy only when you change the container-side code:

- `env.py` — scenario body, staging directories, pytest invocation
- `Dockerfile.hud` — runtime image (OS packages, node version)
- `pyproject.toml` — Python runtime dependencies
- `task_bootstrap.py` — host-side `.env` loading for generated tasks

Everything else — task content, generator templates, helpers under `tasks/_helpers/`, `src/ast_pilot/*` — is host-side. Changes propagate through `ast-pilot run` + `hud sync` alone.

---

## Generating a task

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

The pipeline runs:

1. Scans source and tests into an evidence store
2. Renders `prompt.md` (LLM prose grounded in exact extracted signatures)
3. Validates the prompt against source evidence — refuses to proceed on factual errors
4. Fixes validation issues (up to 3 rounds)
5. Generates the task package (hidden tests, golden solution, support files, `task.py`)
6. Runs prompt-grader alignment (deterministic gap analysis + parallel LLM review of each hidden test file)
7. Auto-fixes safe mismatches, hard-stops on contradictions
8. Promotes the result into `tasks/my_task/`

Flags:

- `--no-llm` — skip the LLM prose step for fast structural smoke tests
- `--no-alignment-autofix` — skip the alignment pass
- `--plain` (or `AST_PILOT_PLAIN=1`) — disable the rich TUI and emit uncoloured output (CI-friendly)

If hidden tests depend on repo-internal modules the generator can't carry, generation fails by default. Set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1` to downgrade instead.

## Task package structure

```text
tasks/my_task/                     # Python
├── __init__.py
├── task.py                        # thin wrapper: load_* helpers + pytest_grader + golden_validation
├── prompt.md                      # what the agent sees
├── tests/                         # hidden pytest files
├── golden/                        # golden source at repo-relative paths (e.g. golden/agent/retry_utils.py)
├── support/                       # hidden repo-internal helpers (namespace-package safe)
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

A newly-generated `task.py` is a ~25-line wrapper that calls helpers from `tasks/_helpers/` to inline prompt / support / tests / hidden requirements into `Task.args`, and emits a single base64-inlined bash `MCPToolCall` into `Task.validation` to stage the golden solution when `hud eval integration_test` runs. Nothing task-specific lives in the Docker image.

### Runtime assets and `REPO_ROOT`

Non-Python files referenced by source or tests via `open(...)`, `sqlite3.connect(...)`, `Path(...) / "..."`, etc. (`.sql`, `.yaml`, `.json`, `.toml`, configs) are auto-detected. Files that exist in the source repo are bundled into `support/` and staged before each check. References the scanner cannot resolve to a file on disk are surfaced in `prompt.md` under `Runtime Files → Files you must create` so the agent knows to produce them.

Tests that derive paths from `__file__` — `REPO_ROOT = os.path.dirname(os.path.abspath(__file__))` and friends (`HERE`, `BASE_DIR`, `ROOT_DIR`, `PROJECT_ROOT`) — are rewritten at generation time to read `AST_PILOT_REPO_ROOT` (set to `/home/ubuntu/workspace` at grading time). Without this, tests staged at `/tmp/test_x.py` would resolve sibling files against `/tmp` instead of the agent's workspace.

Detection only activates when the source tree has a repo-root marker (`pyproject.toml` or `package.json`); bare directories are skipped. Both behaviors require the tests to be present at scan time — if you copy hidden tests into `tasks/<name>/tests/` after regen, the rewrite and asset detection won't fire.

Inline `Path(__file__).parents[N]` inside function bodies is **not** rewritten — the rewriter only handles module-level anchor assignments (`REPO_ROOT = ...`). Tests that use `Path(__file__).resolve().parents[N]` to reach *sibling* modules are detected at generation time and surfaced as a `[warn]` on stderr. At grading time these resolve against `/tmp/` and the referenced files won't exist. Fix by trimming the test to the target module's own surface, or bundle the sibling module into `support/` and set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1` if needed.

### Nested package support

Source files inside a repo-internal package (e.g. `hermes-agent/agent/retry_utils.py`) preserve their nested path end-to-end. The agent is told to create the solution at `agent/retry_utils.py` under the workspace, the golden lives at `golden/agent/retry_utils.py`, and hidden tests keep their original `from agent.retry_utils import …` imports — no flat-basename rewrite.

Packages that contain a workspace target ship without an `__init__.py` under `support/`. Python then treats the package as a PEP 420 namespace package, so the agent's workspace write and any hidden sibling helpers (e.g. `support/agent/other_helper.py`) merge onto one import root at grading time. Single-file scans with the source at the repo root still use the flat workspace layout.

### Alignment literal checks

The alignment pass extracts every literal in the hidden tests' `assert <LIT> in result`, `assert <LIT> not in result`, and `assert x == <LIT>` assertions (and their TS `toContain` / `toBe` equivalents) and hands them to the reviewer with a required per-literal simulation schema. Any literal that the prompt's rules would not produce verbatim is auto-converted into a blocking `direct_contradiction` fix — the reviewer cannot rationalize these away.

---

## Architecture: how sync-only works

`env.py` registers two scenarios:

- **`ast-pilot:coding-task-v2`** — the default for newly-generated tasks. Accepts `prompt`, `graders`, `support`, `hidden_requirements` in args. The scenario stages `support` into `/opt/task_support/` (outside `WORKSPACE_DIR`, appended to `sys.path` — prevents agent-created packages from shadowing support packages of the same name), writes each grader's test script to `/tmp/` just before running pytest, and pip-installs `hidden_requirements` once per grading process (memoized by content hash). Golden pre-staging flows through `Task.validation`.
- **`ast-pilot:coding-task`** — legacy, kept for image-baked tasks. Reads `/mcp_server/tasks/<slug>/` at grade time. Do not use for new tasks.

The `hud sync` path, verified end-to-end against `hud-python`:

- `tasks/<name>/task.py` imports `tasks._helpers` and calls `load_prompt`, `load_support`, `load_requirements`, `pytest_grader`, `golden_validation` at host-side import time.
- Each helper reads files next to `task.py` and returns JSON-serializable content.
- `hud sync tasks` POSTs `{env, scenario, args, validation, ...}` to `/tasks/upload`. `Task.validation` (a list of `MCPToolCall`) rides along as part of the same payload.
- At eval time, `EvalContext` pulls `task.validation` and hands it to `IntegrationTestRunner` (for `hud eval ... integration_test`) or makes it available to whichever agent class you've configured.

Because the scenario body never opens `/mcp_server/tasks/`, you can evolve tests, goldens, weights, and support trees freely — `hud sync` is the only round-trip.

## Directory layout

```text
01-coding-template/
├── src/ast_pilot/       # scanner, renderer, validator, fixer, alignment, task generator
├── tasks/               # generated task packages
│   └── _helpers/        # load_*, pytest_grader, golden_validation — host-side inliners
├── env.py               # HUD environment + two scenarios
├── cli.py               # MCP server entry point
├── task_bootstrap.py    # local .env loading for generated tasks
├── build_support.py     # hidden support staging for the legacy scenario
├── Dockerfile.hud       # Ubuntu + Python + Node 20 runtime
└── pyproject.toml       # hud-python >= 0.5.35
```

## Troubleshooting

**`HUD_ENV_NAME is required`** — Put `HUD_ENV_NAME=<name>` in `.env` and run `source .env`.

**`ModuleNotFoundError` during integration_test** — Usually a missing helper in `support/`, a missing dependency in `requirements.hidden.txt`, or a bad import rewrite. Check the failing import first.

**Generation fails on unsupported internal modules** — Expected. Pick a simpler source module, trim the test surface, or set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`.

**Integration test shows stale behavior after I edited a task** — Did you run `hud sync tasks -y` after regenerating? Task content only reaches the platform via sync. If you only edited the generator or helpers, regenerate the affected tasks first.

**Integration test shows stale behavior after I edited `env.py`** — Scenario changes require `hud deploy .` to rebuild the image. Sync is not enough for scenario-level changes.

**Integration test passes but real-agent scores are low** — The harness is fine; the prompt or task difficulty needs work. Check that all tested symbols are mentioned, implementation notes reflect real test behavior, and the module isn't too broad for the target model.

**Validator flags something that looks correct** — It checks prose against exact extracted facts. Most real failures are signature drift, wrong constants, or renamed fields. Some false positives happen.

## TypeScript support

**Supported:** `.ts` source files, single-package repos (npm/pnpm/yarn), vitest.

**Not supported yet:** `.js` input, Jest, `node:test`, monorepo workspaces, tsconfig path aliases, React/TSX/browser stacks. The TS generator currently emits the legacy `ast-pilot:coding-task` template — v2 sync-only parity is on the roadmap.

The runtime image includes Node.js 20+. Runtime file references (`fs.readFileSync(__dirname + '/file.json')`) are detected and bundled, but exotic patterns may be missed.

## Calibration

A valid task is not necessarily a solvable task. Good heuristics:

- Smaller libraries are easier, but don't go so small it becomes a toy
- Keep the API surface focused and hidden-dependency complexity low
- Prefer one coherent module over a feature spread across half a repo
- Always run real-agent evals after integration_test passes

```bash
hud eval "$HUD_ENV_NAME" claude --task-ids my-task -y --max-steps 30
```

Run multiple attempts and inspect failures before shipping.
