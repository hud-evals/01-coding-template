# Using ast-pilot

`ast-pilot` turns a Python module and its pytest coverage into a 0-to-1 HUD coding task. The generated task gives an agent a long-form spec, an empty workspace, and hidden tests that grade the implementation.

It covers the full path from source module to shippable HUD task.

The agent only sees the prompt. It does not see the hidden tests, the golden solution, or the hidden support tree used during validation.

## What This Directory Is

Treat this directory as the working root for this guide.

It contains both the task generator and the HUD environment that runs the generated tasks:

```text
.
├── src/ast_pilot/      # scanner, renderer, validator, and bundle generator
├── tasks/              # importable HUD task packages (`tasks/<pkg>/task.py`)
├── env.py              # HUD environment and `coding-task` scenario
├── build_support.py    # hidden support staging during image builds
├── scripts.py          # helper for syncing local tasks to a HUD taskset
├── Dockerfile.hud      # image definition used by `hud build` / `hud deploy`
└── USAGE.md            # this file
```

The mental model is simple:

- run `ast-pilot` to generate or update a task package in `tasks/<task_package>/`
- review the generated task package in `tasks/`
- build, validate, deploy, and sync from this directory

Open a shell in this directory and follow the commands below exactly as written.

## Setup

Run everything below from this directory:

```bash
uv sync
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and HUD_API_KEY
source .env
```

You only need `ANTHROPIC_API_KEY` for LLM-generated prose. You need `HUD_API_KEY` for `hud eval`, `hud deploy`, and task sync.

## What Makes a Good Source Module

Pick a source file that:

- is at least a few hundred lines of real logic, ideally around 1,000+ LOC
- already has solid pytest coverage
- has a clear API surface, even if some tested helpers are private
- does not depend on live services like databases, external APIs, or a running app server

Pure logic modules are still the easiest wins, but the current grader can also carry hidden repo-internal support modules when validation needs them.

## The Normal Workflow

### 1. Generate the task bundle

From this directory:

```bash
source .env

uv run ast-pilot run path/to/your_module.py \
    --tests path/to/test_your_module.py \
    --name your-task-slug
```

When you run this from this directory, the task package you will actually work with ends up in `tasks/your_task_slug/`.

For real tasks, use the normal LLM-backed flow. It scans the source, renders `start.md`, validates the prompt against the extracted evidence, auto-fixes prompt mistakes when possible, and then packages the task bundle.

If factual validation errors still remain after the auto-fix rounds, `ast-pilot run` stops before bundling so you do not accidentally ship a bad prompt.

In practice, this gets you most of the way there. You usually get:

- the HUD-compatible task package structure
- a generated `task.py`
- hidden tests and golden validation files
- hidden support modules and hidden dependency manifests when they are needed

You should still review the generated task package before shipping, especially for task difficulty, prompt clarity, and odd dependency edges.

If hidden tests depend on repo-internal modules that the generator cannot safely carry forward, generation now fails by default instead of silently inserting `skip` or `xfail` markers. If you intentionally want that downgraded behavior, set `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`.

### 2. Review the generated task in `tasks/`

The HUD task ID is still slug-shaped, for example `anthropic-adapter`, but the package directory under `tasks/` must be importable Python, so the on-disk folder uses underscores instead:

```text
tasks/anthropic_adapter/
```

That task package is the thing you build, validate, deploy, and sync.

### 3. Build and validate before doing anything else

Validation happens from this same directory:

```bash
hud build .
hud eval . integration_test --task-ids your-task-slug -y
```

This is the release gate. If `integration_test` does not return `Reward: 1.000`, the task is not sound yet and should not be deployed or synced.

If you want a broader sweep:

```bash
hud eval . integration_test --all -y
```

### 4. Run the task against an agent

Once the harness is sound, evaluate the real task difficulty:

```bash
hud eval . claude --task-ids your-task-slug -y --max-steps 30
```

This is a separate question from `integration_test`. A task can be perfectly valid and still be hard for the model.

### 5. Deploy and sync

After the task validates cleanly:

```bash
hud deploy .
uv run sync-tasks --taskset <taskset-name> --env <env-name>
```

What each command does:

- `hud deploy .` creates or updates the HUD environment image
- `uv run sync-tasks ...` uploads the local task definitions to the HUD taskset

Important: task sync is not a universal replacement for `hud deploy .`.

You still need to redeploy when you change anything that affects the environment image, including:

- `env.py`, `cli.py`, `Dockerfile.hud`, `pyproject.toml`, or `build_support.py`
- hidden support modules under `support/`
- hidden dependency manifests such as `requirements.hidden.txt`
- anything else that must exist inside the built image for validation to work

If you only changed task metadata or prompt content, sync may be enough. If you are unsure, run both.

The current template and generated tasks still default to `HUD_ENV_NAME=mario-claire` because that was the original local development environment name used while building this repo. That placeholder is hardcoded in `env.py`, generated `task.py`, and current build metadata, and you MUST change it for your own environment before reusing or shipping this template.

For larger-scale usage patterns, see the HUD docs:
[Running at Scale](https://docs.hud.ai/building/running-at-scale)

## What Gets Generated

`ast-pilot run` creates a task package like this under `tasks/`:

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

Here is what each piece is for:

- `prompt.md` is the agent-facing version of that spec.
- `task.py` wires the task into the HUD environment, injects the hidden tests, and defines the golden validation steps.
- `tests/` contains the hidden pytest files used for grading.
- `golden/` contains the original source files used by `hud eval . integration_test`.
- `support/` contains hidden repo-internal helper modules and packages needed only for grading.
- `requirements.hidden.txt` lists hidden pip dependencies that need to be installed into the image for grading.

The hidden tests are injected at runtime. They are not copied into the agent's workspace. The hidden support tree is staged into the image for validation, not exposed as normal agent workspace files.

## Why `integration_test` Matters

`hud eval . integration_test` is the authoritative check that the task harness is correct. It verifies that:

- the golden solution can be injected into the blank workspace
- the hidden tests run successfully against that golden solution
- the hidden support modules and hidden dependencies are staged correctly
- the task wiring in `task.py` is sound

If this step fails, the task setup is broken. Fix the harness first. Do not diagnose agent behavior until this passes.

## Known Limitations

The generator is in good shape, but it is not magic. The current boundaries are:

- repo-internal dependency resolution works in many cases, but deep or unusual import graphs can still need manual cleanup
- common `src/` layouts are handled more reliably now, but unusual packaging setups can still need manual cleanup
- pure Python modules are the safest path today
- modules that depend on native extensions, live services, databases, or app runtime state are not good task candidates
- `integration_test` proves the harness is sound, but it does not prove the task will be easy for a model
- syncing tasks is not always enough after the first deploy; if hidden support, hidden dependencies, or shared environment files changed, you must run `hud deploy .` again so the image actually contains those changes

If you want the highest reliability, prefer focused, self-contained modules with strong test coverage and minimal runtime coupling.

## LLM Mode vs `--no-llm`

Use LLM mode for real tasks.

`--no-llm` is only for fast structural checks when you want to test the pipeline without spending model calls. The deterministic prompt is accurate, but it reads like a technical dump and performs noticeably worse with real agents.

Dry-run example:

```bash
uv run ast-pilot run path/to/source.py \
    --tests path/to/tests.py \
    --name my-task \
    --no-llm
```

## Troubleshooting

### `ModuleNotFoundError` during `integration_test`

The usual causes are:

- a missing repo-internal helper in `support/`
- a missing hidden third-party dependency in `requirements.hidden.txt`
- a hidden test import that was not rewritten correctly for the workspace module name

Check the failing import first. That will usually tell you whether the problem is hidden support, a missing dependency, or a bad test rewrite.

### Generation fails because hidden tests reference unsupported internal modules

The generator now fails by default when hidden tests depend on repo-internal modules that it cannot safely bundle for grading. That is intentional: silently downgrading those tests with `skip` or `xfail` makes the task look sounder than it really is.

Your options are:

- pick a simpler source module with fewer hidden test dependencies
- manually reduce the hidden test surface so the unsupported imports go away
- only if you intentionally accept downgraded coverage, rerun with `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS=1`

### `Reward: 0.000` in `integration_test`

Treat this as a broken task harness, not a model failure.

Common causes:

- the golden source cannot import one of its hidden dependencies
- the hidden tests still refer to the original package path instead of the workspace module
- the task package was copied into the wrong directory name under `tasks/`

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

After you have successfully run tasks on HUD, we have a beta feature you should use called QA Agents. This is still in beta, so take it with a grain of salt, but in our internal benchmarks we have seen a success rate of around 70%.

There are 4 different QA agents in beta on the platform right now. For this specific template and use case, you should only use 2 of them:

- Failure Mode Analysis agent: this agent does a thorough analysis of why the model failed the task and where it went wrong across the full trace. This is a crucial part of the workflow because failure mode diversity is one of the most important goals here.
- Reward Hacking agent: this agent goes through the trace and catches models that try to hack their way into getting a perfect score. This is especially useful in instances where, for example, an environment is not built securely enough and the model can access or copy the golden trace to get a score of 100%. We want to avoid this in 100% of our tasks and traces, so running this agent is a must once a task is deemed good.

If you are calibrating difficulty more seriously, run multiple attempts and inspect the failures before deciding the task is ready to ship.

### The validator complains about something that looks correct

The validator checks prose against exact extracted facts. When it flags something suspicious, inspect the specific line and compare it with `evidence.json`. Some false positives do happen, but most real failures come from signatures, constants, or field names drifting in prose.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | required for LLM mode | Used for prompt generation and fixer calls |
| `HUD_API_KEY` | required for HUD commands | Used by `hud eval`, `hud deploy`, and sync |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model used for prose generation and fixer calls |
| `AST_PILOT_ALLOW_UNSUPPORTED_TEST_REFS` | unset | If set to `1`, allows the generator to downgrade unsupported hidden-test imports with `skip` or `xfail` instead of failing generation. |
| `HUD_ENV_NAME` | `mario-claire` | Original local placeholder environment name. It is hardcoded into the template and task wiring and MUST be changed for your own deployment. |
| `CODING_GITHUB_TOKEN` | unset | Optional build secret for private repo clones in `Dockerfile.hud` |

## Short Version

If you only remember one path, remember this:

1. Generate with `uv run ast-pilot run ...`
2. Copy the task into `tasks/...`
3. Run `hud build .`
4. Run `hud eval . integration_test --task-ids <slug> -y`
5. Only then run model evals or deploy