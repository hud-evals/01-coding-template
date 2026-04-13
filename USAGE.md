# Using ast-pilot

`ast-pilot` turns a Python module plus pytest coverage into a 0-to-1 HUD coding task. It generates:

- an agent-facing prompt
- hidden tests
- golden validation steps
- hidden support files and hidden pip requirements when needed
- the `task.py` wiring needed to run the task on HUD

It covers the full path from source module to shippable HUD task.

The agent only sees `prompt.md`. It does not see the hidden tests, the golden solution, the hidden support tree, or `requirements.hidden.txt`.

## What This Directory Is

Treat `01-coding-template/` as the working root.

This directory contains both:

- the generator under `src/ast_pilot/`
- the deployable HUD environment under `env.py`, `cli.py`, `Dockerfile.hud`, and `tasks/`

```text
.
├── src/ast_pilot/      # scanner, renderer, validator, fixer, alignment checker, and task generator
├── tasks/              # generated HUD task packages (`tasks/<pkg>/task.py`)
├── env.py              # HUD environment and shared coding scenario
├── task_bootstrap.py   # local .env loading for generated tasks
├── build_support.py    # hidden support staging during image builds
├── Dockerfile.hud      # image definition used by `hud build` / `hud deploy`
└── USAGE.md            # this file
```

The mental model is simple:

- run `ast-pilot` here
- generated tasks land directly in `tasks/<task_package>/`
- review the generated task package in `tasks/`
- build, deploy, validate, and sync from this directory

Normal usage is tasks-first. The final artifact goes straight into `tasks/` in the happy path.

## Setup

Run everything below from this directory:

```bash
uv sync
cp .env.example .env
# Fill in HUD_API_KEY and HUD_ENV_NAME
source .env
```

What the important variables do:

- `HUD_API_KEY`: auth for LLM calls (via HUD inference gateway) and HUD commands (`hud build`, `hud deploy`, `hud eval`)
- `HUD_ENV_NAME`: the deployed HUD environment name your generated tasks connect to

Important: `.env` is intentionally excluded from the Docker image. Local task import and sync can read `HUD_ENV_NAME` from `.env`, but the deployed environment itself must not depend on `.env` being present inside the image.

## What Makes a Good Source Module

Pick a source file that:

- is at least a few hundred lines of real logic, ideally around 1,000+ LOC
- already has solid pytest coverage
- has a clear API surface, even if some tested helpers are private
- does not depend on live services like databases, external APIs, or a running app server

Pure logic modules are still the easiest wins, but the current generator can also carry hidden repo-internal support modules when validation needs them.

## End-to-End Workflow

### 1. Generate the task package

From this directory:

```bash
uv run ast-pilot run path/to/your_module.py \
    --tests path/to/test_your_module.py \
    --name your-task-slug
```

This command does the whole authoring pipeline:

1. scans the source and tests
2. renders `start.md`
3. validates the prose against exact extracted evidence
4. runs up to three fixer rounds when LLM mode is enabled
5. generates the HUD task package
6. runs a prompt-grader alignment pass (deterministic gap analysis + LLM review)
7. auto-fixes safe prompt mismatches, hard-stops on contradictions
8. promotes the generated task directly into `tasks/your_task_slug/`

If unresolved factual validation errors remain, generation stops before bundling. That is intentional: the tool now refuses to ship a prompt that drifted away from the code.

For real tasks, use normal LLM mode. `--no-llm` is only for fast structural smoke tests.

Also important: if hidden tests depend on repo-internal modules that the generator cannot safely carry forward, generation now fails by default instead of silently inserting `skip` or `xfail`. If you intentionally want the old downgraded behavior, set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`.

### 2. Review the generated task package

The on-disk folder must be valid Python, so the package directory uses underscores:

```text
tasks/your_task_slug/
├── __init__.py
├── prompt.md
├── task.py
├── tests/
├── golden/
├── support/
└── requirements.hidden.txt
```

The task slug itself stays hyphenated, for example `your-task-slug`.

Generated `task.py` files now do three important things out of the box:

- they hardcode the stable scenario ID `ast-pilot:coding-task`
- they load `HUD_ENV_NAME` locally through `task_bootstrap.py`
- they connect to the deployed HUD environment named by `HUD_ENV_NAME`

That hardcoded scenario split is intentional. The scenario inside the environment stays stable, while the actual deployed HUD environment name remains configurable.

### 3. Build the local image

```bash
hud build .
```

This is your local image sanity check. It catches build failures, packaging problems, and missing runtime files before you touch the platform.

But `hud build .` only updates your local image. It does not change the deployed HUD environment that hub-connected tasks use.

### 4. Deploy the environment used by the tasks

```bash
hud deploy . -n "$HUD_ENV_NAME"
```

This updates the real HUD environment that generated tasks connect to.

Safe rule: after you regenerate a task and before you trust a platform-side `integration_test`, deploy first.

You definitely need to redeploy when you changed anything that affects the environment image, including:

- `env.py`, `task_bootstrap.py`, `cli.py`, `Dockerfile.hud`, `pyproject.toml`, or `build_support.py`
- hidden support modules under `tasks/<task>/support/`
- hidden dependency manifests such as `requirements.hidden.txt`
- any generated task content that must exist inside the image for grading to work

### 5. Run the release-gate validation

```bash
hud eval . integration_test --task-ids your-task-slug -y
```

This is the release gate. A task is not ready until this returns `Reward: 1.000`.

If you want a full sweep:

```bash
hud eval . integration_test --all -y
```

In plain English, `integration_test` checks that:

- the task can start from a blank workspace
- the golden solution can be injected correctly
- the hidden tests pass against the golden solution
- hidden support files and hidden pip dependencies are staged correctly
- the generic `ast-pilot:coding-task` scenario and the generated `task.py` wiring agree with each other

For this template, that validation is against the HUD environment the task connects to. That is why stale deploys can make `integration_test` keep failing even after local code changed.

### 6. Run real agent evals

Once the harness is sound, test actual difficulty:

```bash
hud eval . claude --task-ids your-task-slug -y --max-steps 30
```

This answers a different question from `integration_test`. A task can be perfectly valid and still be too hard, too vague, or too annoying for the model.

### 7. Sync tasks to a taskset

```bash
hud sync tasks <taskset-name>
```

This uploads your local task definitions to a HUD taskset.

Task sync is not a replacement for deploy:

- `hud deploy . -n "$HUD_ENV_NAME"` updates the environment image
- `hud sync tasks <taskset-name>` updates task definitions on the platform

If you are not sure whether a change needs both, the safe answer is yes.

For larger-scale usage patterns, see the HUD docs:
[Running at Scale](https://docs.hud.ai/building/running-at-scale)

## What The Main Commands Actually Do

These four commands were the big source of confusion during development, so here is the layman version:

- `hud build .`: build and sanity-check the image locally
- `hud deploy . -n "$HUD_ENV_NAME"`: push the current environment image to the HUD platform
- `hud eval . integration_test ...`: validate the task harness against the environment the task connects to
- `hud sync tasks <taskset-name>`: upload task definitions to a HUD taskset

The practical consequence is:

- if you changed only local authoring files and want a quick local sanity check, `hud build .` is useful
- if you changed shared runtime wiring or anything that must live inside the deployed image, you must `hud deploy` before trusting platform eval results

## What Gets Generated

Normal tasks-first usage leaves the final task package under `tasks/`. Intermediate evidence and prompt artifacts are generated during the run and cleaned up automatically after a successful promotion.

Here is what each generated file is for:

- `prompt.md`: the agent-facing task description
- `task.py`: wires the task into HUD, injects hidden tests, stages hidden runtime support, and defines golden validation
- `tests/`: hidden pytest files used for grading
- `golden/`: original source files used to build the golden validation path
- `support/`: hidden repo-internal helper modules and packages needed only for grading
- `requirements.hidden.txt`: hidden pip dependencies needed only for grading

The hidden tests are injected at runtime. They are not copied into the agent's normal workspace.

## Why The Scenario Is Hardcoded

Generated tasks now hardcode:

```python
SCENARIO_ID = "ast-pilot:coding-task"
```

This happens out of the box in the generator. You do not need to patch it by hand for new tasks.

That split exists for a reason:

- the environment exports one stable shared scenario, `ast-pilot:coding-task`
- `HUD_ENV_NAME` chooses which deployed HUD environment to talk to
- keeping those two concepts separate prevents deployed images from crashing just because `.env` is not baked into the image

## Known Limitations

The generator is in good shape, but it is not magic. The current boundaries are:

- repo-internal dependency resolution works in many cases, but deep or unusual import graphs can still need manual cleanup
- common `src/` layouts are handled more reliably now, but unusual packaging setups can still need manual cleanup
- pure Python modules are the safest path today
- modules that depend on native extensions, live services, databases, or app runtime state are not good task candidates
- `integration_test` proves the harness is sound, but it does not prove the task will be easy for a model

If you want the highest reliability, prefer focused, self-contained modules with strong test coverage and minimal runtime coupling.

## Troubleshooting

### `HUD_ENV_NAME is required`

For local commands, the fix is simple:

- put `HUD_ENV_NAME=<your-deployed-env-name>` in `.env`
- run `source .env` before HUD commands

Generated tasks and `hud sync tasks` both expect that variable locally.

The deployed environment itself should not depend on `.env` existing inside the image.

### `ModuleNotFoundError` during `integration_test`

The usual causes are:

- a missing repo-internal helper in `support/`
- a missing hidden third-party dependency in `requirements.hidden.txt`
- a hidden test import that was not rewritten correctly for the workspace module name

Check the failing import first. It will usually tell you whether the problem is hidden support, a missing dependency, or a bad test rewrite.

### Generation fails because hidden tests reference unsupported internal modules

That is now expected behavior. The generator fails by default rather than silently weakening the test suite.

Your options are:

- pick a simpler source module with fewer hidden test dependencies
- manually reduce the hidden test surface so the unsupported imports go away
- only if you intentionally accept downgraded coverage, rerun with `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`

### `integration_test` still shows old behavior after you fixed the code

That usually means the platform is still running an older deployed image.

Run:

```bash
hud build .
hud deploy . -n "$HUD_ENV_NAME"
hud eval . integration_test --task-ids your-task-slug -y
```

### `integration_test` passes but agent pass rate is poor

That usually means the harness is fine and the prompt or task difficulty needs work. Look at:

- whether the prompt clearly calls out all tested symbols, including private helpers
- whether the implementation notes describe the real behavior the tests care about
- whether the module is simply too broad or too dependency-heavy for the target model

## Task Calibration

If you want a task to be solvable by real agents, calibration matters as much as harness correctness.

Good heuristics:

- smaller libraries are usually easier, because the agent has less code to write
- but do not go so small that the task stops being meaningful or becomes a toy
- keep the API surface focused
- keep hidden dependency complexity low
- prefer one coherent module over a feature that spreads across half the repo

Always run real QA agent evals after `integration_test` passes. A task can be perfectly valid and still be too hard, too ambiguous, or too annoying for the target model.

The simplest QA loop is:

```bash
hud eval . claude --task-ids your-task-slug -y --max-steps 30
```

If you are calibrating difficulty more seriously, run multiple attempts and inspect the failures before deciding the task is ready to ship.

### The validator complains about something that looks correct

The validator checks prose against exact extracted facts. When it flags something suspicious, inspect the specific line and compare it with the extracted evidence. Some false positives do happen, but most real failures come from signatures, constants, or field names drifting in prose.

## Prompt-Grader Alignment

After generating the task bundle, `ast-pilot` runs an automatic LLM-only alignment pass that compares the final `prompt.md` against the final hidden test files.

Safe mismatches (e.g. prompt underspecifies an output format that the grader requires) are automatically corrected in the prompt. Fundamentally inconsistent tasks (e.g. prompt says raise an exception but grader expects a return value) cause the CLI to exit non-zero before promotion.

After every auto-fix the prompt is re-validated against the original source evidence to prevent the LLM from "fixing" the prompt into something factually wrong.

This pass is enabled by default when LLM mode is active. To disable it:

```bash
uv run ast-pilot run ... --no-alignment-autofix
```

To control the maximum number of alignment fix rounds (default 2):

```bash
uv run ast-pilot run ... --alignment-max-rounds 3
```

When `--no-llm` is passed, the alignment pass is skipped automatically.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HUD_API_KEY` | required for LLM mode | Used for LLM calls via the HUD inference gateway and for HUD commands |
| `HUD_ENV_NAME` | required | Deployed HUD environment name used by local task import, generated tasks, and sync |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model used for prose generation, fixer calls, and alignment review |
| `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS` | unset | If set to `1`, allows the generator to downgrade unsupported hidden-test imports with `skip` or `xfail` instead of failing generation |
| `CODING_GITHUB_TOKEN` | unset | Optional build secret for private repo clones in `Dockerfile.hud` |

## Experimental TypeScript Support

`ast-pilot` includes experimental support for generating HUD tasks from TypeScript source modules.

### Supported Matrix

- TypeScript source files (`.ts`)
- `npm` with committed `package-lock.json`
- Single-package repos only
- Vitest test runner only

### Not Supported (Yet)

- JavaScript (`.js`) input files
- Jest or `node:test`
- Monorepo workspaces
- `pnpm` or `yarn`
- `tsconfig.json` path aliases
- React / TSX / browser stacks

### Usage

```bash
uv run ast-pilot run path/to/module.ts \
    --tests path/to/module.test.ts \
    --name my-ts-task
```

The language is auto-inferred from `.ts` file extensions. You can also be explicit:

```bash
uv run ast-pilot run path/to/module.ts \
    --tests path/to/module.test.ts \
    --name my-ts-task \
    --language typescript
```

The generated task bundle uses `npm ci` + `vitest run` for grading instead of `pip install` + `pytest`.

### Known Limitations

- Post-bundle alignment auto-fix is not yet TypeScript-aware. The TS path runs deterministic validation only.
- Hidden test support/rewriting is simpler than the Python backend. TS v0 copies test files as-is.
- The runtime image must include Node.js 20+. The Dockerfile has been updated accordingly.

## Short Version

If you only remember one path, remember this:

1. Generate with `uv run ast-pilot run ...`
2. Run `hud build .`
3. Run `hud deploy . -n "$HUD_ENV_NAME"`
4. Run `hud eval . integration_test --task-ids <slug> -y`
5. Run real model evals
6. Sync with `hud sync tasks <taskset-name>`
