# ast-pilot coding template

A HUD environment for 0-to-1 coding tasks: the agent starts in a blank workspace, reads a long markdown prompt describing a library to build from scratch, and is graded by running hidden tests against its implementation. The agent never sees the tests, the golden solution, or any support files.

This repo is **both a HUD environment** (the `env.py` + `Dockerfile.hud` you deploy) **and a generator** (`ast-pilot`) that turns real source modules into task packages the environment can run. The two sections below mirror that split — read the HUD section first; the generator is a shortcut that lives on top of it.

---

## Part 1 — How this repo works as a HUD environment

A HUD environment is a Docker image that exposes one or more **scenarios**. A scenario is an async function decorated with `@env.scenario` in `env.py`; it accepts an `args` dict (the task payload) and yields a prompt followed by grading results. The platform runs the container, pipes the agent's messages through it, and scores the result.

There are two commands that talk to the HUD platform from this repo:

- **`hud deploy .`** builds the Docker image from `Dockerfile.hud`, pushes it to HUD's registry, and registers the scenarios declared in `env.py`. Re-run it whenever **the container-side code** changes: `env.py`, `Dockerfile.hud`, or `pyproject.toml`.
- **`hud sync tasks`** discovers the `Task` objects defined under `tasks/<name>/task.py` and uploads their JSON payloads (`scenario`, `args`, `validation`) to the platform. Nothing Docker-related happens here — it's a plain HTTP round-trip.

After a task is synced, you invoke it with `hud eval <taskset> <agent> --task-ids <slug>`. Two agents matter for authoring:

- `integration_test` — pre-stages the golden solution (via `Task.validation`) and then runs the graders. Must return **Reward 1.0** for a task to be considered shippable.
- `claude` / `opus` / any real model — runs the actual agent loop against the prompt.

### Setup

```bash
uv sync
export HUD_API_KEY=...   # required: platform + LLM inference gateway auth
hud deploy .             # builds the image, pushes it, registers the scenarios
                         # .hud/config.json is written here, recording the env name
```

| Variable | Default | What it does |
| --- | --- | --- |
| `HUD_API_KEY` | required | Auth for HUD platform + LLM inference gateway |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model for the generator's prompt / alignment passes |
| `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS` | unset | `1` to downgrade unsupported test imports instead of failing |
| `AST_PILOT_ALLOW_ALIGNMENT_UNAVAILABLE` | unset | `1` to promote even when the alignment reviewer never returned parseable JSON. Coverage will be unknown — only set during a known LLM provider outage. Equivalent to `--allow-alignment-unavailable`. |
| `CODING_GITHUB_TOKEN` | unset | Build secret for private-repo clones in `Dockerfile.hud` |

The deployed environment name lives in `.hud/config.json` (`registryName`) and is picked up automatically by the generator + sync flow — no `.env` or `HUD_ENV_NAME` export needed.

After the first deploy, you'll see both scenarios registered: `ast-pilot:coding-task-v2` (the one every new task uses) and `ast-pilot:coding-task` (legacy, kept for backward compatibility with image-baked tasks).

### The sync-only loop

Once the environment is deployed, shipping a new task is a pure `hud sync` round-trip — no Docker involved. A minimal task is a directory with a `task.py` that constructs a `Task` object:

```python
# tasks/my_task/task.py
from hud import Environment
from hud.eval.task import Task
from hud.types import MCPToolCall

from tasks._helpers import resolve_env_name  # reads .hud/config.json at the repo root

task = Task(
    env=Environment(resolve_env_name(__file__)),
    scenario="ast-pilot:coding-task-v2",
    args={
        "prompt": "Build a function named add(a, b) that returns a + b...",
        "graders": [
            {
                "kind": "pytest",
                "name": "test_add",
                "test_name": "test_add.py",
                "script": "from add import add\ndef test_add(): assert add(2,3) == 5\n",
                "weight": 1.0,
                "timeout": 60,
            },
        ],
        "support": {},               # {path: content} staged to /opt/task_support/
        "hidden_requirements": "",   # contents of requirements.hidden.txt
    },
)
task.slug = "my-task"
# Pre-stage the golden solution for `hud eval integration_test`:
task.validation = [
    MCPToolCall(
        name="bash",
        arguments={"command": "mkdir -p /home/ubuntu/workspace && echo 'def add(a,b): return a+b' > /home/ubuntu/workspace/add.py"},
    ),
]
```

Ship it:

```bash
hud sync tasks -y                                               # uploads Task.args + Task.validation
hud eval <env-name> integration_test --task-ids my-task -y # golden must score 1.0
hud eval <env-name> claude --task-ids my-task -y --max-steps 30
```

Change any of the args, the prompt, a grader, or the golden-staging command → re-run `hud sync`. No redeploy.

### When `hud deploy` is required

Container-side edits only:

- `env.py` — scenario body (staging directories, pytest / vitest invocation, new scenario args)
- `Dockerfile.hud` — runtime image (OS packages, Python / Node versions)
- `pyproject.toml` — Python runtime dependencies

Everything else — task content, helper modules under `tasks/_helpers/`, the `src/ast_pilot/` generator — lives on the host and flows through `hud sync`.

### The whole authoring loop is two commands

Once `hud deploy` has registered the scenarios (a one-time thing), **every new or edited task ships in exactly two steps**:

1. **Create or edit the task** — add a `tasks/<name>/task.py` (or touch the prompt, tests, golden, support, requirements for an existing one).
2. **`hud sync tasks -y`** — upload the payload. Seconds. No image build, no registry push.

Then one more command verifies the harness actually works:

```bash
hud eval <env-name> integration_test --task-ids my-task -y
```

The `integration_test` agent pre-stages the golden solution (via `Task.validation`), runs every grader, and expects **Reward 1.0**. If it scores lower, your golden doesn't pass your own hidden tests — the task isn't ready. If it scores 1.0, the grading harness is sound and you can run it against real agents the same way (`claude`, `opus`, …).

That's it. Task iteration is now a pure host-side → HTTP round-trip loop. The Docker image only gets involved again if you change `env.py`, the Dockerfile, or runtime dependencies.

### Scenario reference

`ast-pilot:coding-task-v2` (the default) accepts:

| Arg | Type | What the scenario does |
| --- | --- | --- |
| `prompt` | `str` | Prepended with workspace instructions and shown to the agent |
| `graders` | `list[dict]` | Three kinds: `{"kind": "pytest", "test_name", "script", "name", "weight", "timeout"}` runs a Python test under `uv run --with-requirements`; `{"kind": "vitest", "test_rel", "script", "name", "weight", "timeout"}` runs a TS test from the staged node project tree; `{"kind": "bash", "command", "name", "weight", "timeout"}` runs a raw shell check |
| `support` | `dict[str, str]` | Written verbatim to `/opt/task_support/<path>`; root is appended to `sys.path`. Lives outside the workspace so agent-created packages can't shadow support packages of the same name. |
| `hidden_requirements` | `str` | Contents of a pip `requirements.txt`; consumed per-grader by `uv run --with-requirements` — uv caches resolution by content hash, no venv mutation. |
| `node_project` | `dict` (TS tasks only) | `{"slug", "config_files", "support_files", "source_files"}` — scenario mirrors the repo tree at `/tmp/ast_pilot_ts_stage/<slug>/`, installs `node_modules` into a content-hashed cache once, then per-grader copies agent sources from the workspace and runs `npx vitest run <test_rel>`. |

`Task.validation` on the task object is orthogonal to `args` — it's a list of `MCPToolCall`s that `hud eval integration_test` executes in order before graders run. Perfect for pre-staging a golden solution with a base64-encoded bash write. Verified end-to-end against `hud-python`'s `EvalContext` → `IntegrationTestRunner`.

---

## Part 2 — The ast-pilot generator

Writing `task.py` by hand for a real library — enumerating every symbol, inlining the hidden tests, inlining the golden, bundling repo-internal support modules, writing an accurate prompt — is tedious and error-prone. `ast-pilot` automates it. You point it at a source module and its tests; it emits the whole task package (prompt, tests, golden, support, `task.py`) ready to `hud sync`.

Combined with Part 1, the daily loop becomes three commands:

```bash
# 1. Generate the task from a source module + tests
uv run ast-pilot run path/to/module.py \
    --tests path/to/test_module.py \
    --name my-task

# 2. Upload to the platform (seconds, no image involved)
hud sync tasks -y

# 3. Validate — golden must score 1.0
hud eval <env-name> integration_test --task-ids my-task -y
```

Then run it with a real agent: `hud eval <env-name> claude --task-ids my-task -y --max-steps 30`.

### What `ast-pilot run` does

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

Pipeline:

1. Scans source and tests into an evidence store
2. Renders `prompt.md` (LLM prose grounded in exact extracted signatures)
3. Validates the prompt against source evidence — refuses to proceed on factual errors
4. Fixes validation issues (up to 3 rounds)
5. Emits the task package — hidden tests, golden, support, `task.py` — ready to sync
6. Runs prompt-grader alignment (deterministic gap analysis + parallel LLM review of each hidden test file)
7. Auto-fixes safe mismatches, hard-stops on contradictions
8. Promotes the result into `tasks/my_task/`

Flags:

- `--no-llm` — skip prose generation for fast structural smoke tests
- `--no-alignment-autofix` — skip the alignment pass
- `--allow-alignment-unavailable` — promote even when the reviewer never returned parseable JSON (LLM outage escape hatch; equivalent to `AST_PILOT_ALLOW_ALIGNMENT_UNAVAILABLE=1`)
- `--plain` (or `AST_PILOT_PLAIN=1`) — disable the rich TUI (CI-friendly)

Failure modes the generator hard-fails on by default (with explicit escape hatches):

- Hidden tests depending on repo-internal modules the generator can't carry → set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1` to downgrade them to `pytest.mark.skip`.
- Hidden tests using `Path(__file__).parents[N]` to walk above the test directory → same env var. These resolve to `/tmp` at grading time, not the agent workspace.
- Alignment reviewer returning no parseable response on every retry → set `AST_PILOT_ALLOW_ALIGNMENT_UNAVAILABLE=1` (or pass `--allow-alignment-unavailable`). Use only when the LLM provider is degraded; the resulting task ships with unknown coverage.

For TypeScript projects the generator additionally requires a usable Node project at the import root: `package.json`, vitest as the test runner, no monorepo workspaces, no path aliases, no unresolved local vitest setupFiles. Missing `package-lock.json` is auto-generated for you in a temp dir — the source repo is never modified.

### Generated task package

```text
tasks/my_task/                     # Python
├── __init__.py
├── task.py                        # thin wrapper: calls load_* helpers + pytest_grader + golden_validation
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

The generated `task.py` is a ~25-line wrapper that calls helpers from `tasks/_helpers/` — `load_prompt`, `load_support`, `load_requirements`, `pytest_grader`, `golden_validation` — to inline file contents into `Task.args` / `Task.validation` at task-import time. `hud sync` then POSTs the whole payload to the platform; nothing task-specific reaches the Docker image.

### Runtime assets and `REPO_ROOT`

Non-Python files referenced by source or tests via `open(...)`, `sqlite3.connect(...)`, `Path(...) / "..."`, etc. (`.sql`, `.yaml`, `.json`, `.toml`, configs) are auto-detected. Files that exist in the source repo are bundled into `support/`; references the scanner cannot resolve are surfaced in `prompt.md` under `Runtime Files → Files you must create`.

Tests that derive paths from `__file__` — `REPO_ROOT = os.path.dirname(os.path.abspath(__file__))` and friends (`HERE`, `BASE_DIR`, `ROOT_DIR`, `PROJECT_ROOT`) — are rewritten at generation time to read `AST_PILOT_REPO_ROOT` (set to `/home/ubuntu/workspace` at grading time). Without this, tests staged at `/tmp/test_x.py` would resolve sibling files against `/tmp` instead of the agent's workspace.

Detection only activates when the source tree has a repo-root marker (`pyproject.toml` or `package.json`); bare directories are skipped. Inline `Path(__file__).parents[N]` inside function bodies is **not** rewritten — only module-level anchor assignments are.

### Nested package support

Source files inside a repo-internal package (e.g. `hermes-agent/agent/retry_utils.py`) preserve their nested path end-to-end. The agent is told to create the solution at `agent/retry_utils.py` under the workspace, the golden lives at `golden/agent/retry_utils.py`, and hidden tests keep their original `from agent.retry_utils import …` imports — no flat-basename rewrite.

Packages that contain a workspace target ship without an `__init__.py` under `support/`, so Python treats them as PEP 420 namespace packages — the agent's workspace write and any hidden sibling helpers merge onto one import root at grading time.

### Alignment literal checks

The alignment pass extracts every literal in the hidden tests' `assert <LIT> in result`, `assert <LIT> not in result`, and `assert x == <LIT>` assertions (and their TS `toContain` / `toBe` equivalents) and hands them to the reviewer with a required per-literal simulation schema. Any literal that the prompt's rules would not produce verbatim is auto-converted into a blocking `direct_contradiction` fix.

### TypeScript support

**Supported:** `.ts` source, single-package repos (npm/pnpm/yarn), vitest. The TS generator emits v2 sync-only `task.py` files, same as the Python generator — `hud sync` ships them with no image rebuild.
**Not supported yet:** `.js` input, Jest, `node:test`, monorepo workspaces, tsconfig path aliases, React/TSX/browser stacks.

---

## Directory layout

```text
01-coding-template/
├── src/ast_pilot/       # scanner, renderer, validator, fixer, alignment, task generator
├── tasks/               # generated task packages
│   └── _helpers/        # load_*, pytest_grader, vitest_grader, golden_validation — host-side inliners
├── env.py               # HUD environment + two scenarios (v1 legacy, v2 sync-only)
├── cli.py               # MCP server entry point
├── .hud/config.json     # written by `hud deploy`; records registryName for this env
├── Dockerfile.hud       # Ubuntu + Python + Node 20 runtime
└── pyproject.toml       # hud-python >= 0.5.35
```

## Troubleshooting

**`Cannot resolve HUD environment` at sync time** — `.hud/config.json` is missing. Run `hud deploy` (or `hud sync env <name>`) once to write it.

**`ModuleNotFoundError` during integration_test** — Usually a missing helper in `support/`, a missing dependency in `requirements.hidden.txt`, or a bad import rewrite. Check the failing import first.

**`integration_test` returns `Reward: 0.000` and the trace shows a `KeyError`/`AttributeError` from an unset env var or undefined fixture** — Your test relies on a `conftest.py` autouse fixture (common in repos that isolate `$HOME`-style state, monkeypatch env vars, or reset plugin singletons per test). The generator does **not** bundle `conftest.py` today, so those fixtures don't activate at grading time. Two workarounds: pick a test file that doesn't depend on autouse fixtures (run `pytest --fixtures path/to/test.py` to see what it pulls in), or inline the fixture body into the test itself before regenerating — whatever is literally in the test file gets bundled verbatim.

**Generation fails on unsupported internal modules** — Expected. Pick a simpler source module, trim the test surface, or set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`.

**Generation aborts with `alignment unavailable`** — The LLM reviewer returned nothing parseable on every retry; the generator refuses to ship a task with unknown coverage. Retry once the provider recovers, or pass `--allow-alignment-unavailable` if you need to ship anyway (the generated task will sync but reviewers should manually audit the prompt).

**TypeScript generation refuses with unsupported reasons** — The repo isn't compatible with v0 TS mode (monorepo workspaces, non-vitest runner, path aliases, unresolved vitest setupFiles). Either split out the package you care about into a single-package layout, or fix the offending config. Missing `package-lock.json` is the only one that auto-resolves (in a temp dir — your repo is left alone).

**integration_test shows stale behavior after editing a task** — Did you run `hud sync tasks -y`? Task content only reaches the platform via sync. If you only edited the generator or helpers, regenerate the affected tasks first.

**integration_test shows stale behavior after editing `env.py`** — Scenario changes require `hud deploy .` to rebuild the image. Sync alone is not enough.

**integration_test passes but real-agent scores are low** — The harness is fine; the prompt or task difficulty needs work. Check that all tested symbols are mentioned, implementation notes reflect real test behavior, and the module isn't too broad for the target model.

**Validator flags something that looks correct** — It checks prose against exact extracted facts. Most real failures are signature drift, wrong constants, or renamed fields. Some false positives happen.

## Calibration

A valid task is not necessarily a solvable task. Good heuristics:

- Smaller libraries are easier, but don't go so small it becomes a toy
- Keep the API surface focused and hidden-dependency complexity low
- Prefer one coherent module over a feature spread across half a repo
- Always run real-agent evals after integration_test passes

```bash
hud eval <env-name> claude --task-ids my-task -y --max-steps 30
```

Run multiple attempts and inspect failures before shipping.
