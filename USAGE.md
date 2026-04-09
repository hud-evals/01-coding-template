# Using ast-pilot

`ast-pilot` turns a Python module and its pytest coverage into a 0-to-1 HUD coding task. The generated task gives an agent a long-form spec, an empty workspace, and hidden tests that grade the implementation.

The agent only sees the prompt. It does not see the hidden tests, the golden solution, or the hidden support tree used during validation.

## Current Repo Layout

Right now the workflow is split across two places:

- The repo root contains the generator: `src/ast_pilot/`, the generator tests, and this doc.
- `01-coding-template/` is the deployable HUD environment. It holds the actual task packages, the Docker image, and the `hud build` / `hud eval` / `hud deploy` flow.

That means you generate from the repo root, then validate and ship from `01-coding-template/`.

## Use The Template

If you are a vendor setting this up in a new repo, start from `01-coding-template/`.

That directory is the real HUD environment template. It contains:

- the Docker image definition
- the HUD scenario and MCP server entrypoint
- the task discovery logic
- the task packages that get built, validated, deployed, and synced

In this repo today, the generator still lives at the root and the deployable HUD environment lives under `01-coding-template/`. So the practical rule is:

- generate from the repo root
- ship from `01-coding-template/`

## Setup

Run this from the repo root:

```bash
uv sync
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and HUD_API_KEY
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

From the repo root:

```bash
source .env

uv run ast-pilot run path/to/your_module.py \
    --tests path/to/test_your_module.py \
    --name your-task-slug \
    --output output/your-task-slug
```

If you omit `--output`, the tool defaults to `output/<name>/`.

For real tasks, use the normal LLM-backed flow. It scans the source, renders `start.md`, validates the prompt against the extracted evidence, auto-fixes prompt mistakes when possible, and then packages the task bundle.

In practice, this gets you most of the way there. You usually get:

- the HUD-compatible task package structure
- a generated `task.py`
- hidden tests and golden validation files
- hidden support modules and hidden dependency manifests when they are needed

You should still review the output before shipping, especially for task difficulty, prompt clarity, and odd dependency edges.

### 2. Promote the generated task into `01-coding-template`

The generated task bundle lives under `output/<slug>/tasks/<slug>/`. The template repo uses an importable package directory name, so in practice you usually copy the slugged task folder into an underscored package directory.

Example:

```bash
rm -rf 01-coding-template/tasks/your_task_slug
cp -r output/your-task-slug/tasks/your-task-slug \
    01-coding-template/tasks/your_task_slug
```

For example, `anthropic-adapter` becomes `01-coding-template/tasks/anthropic_adapter`.

### 3. Build and validate before doing anything else

Validation happens from inside `01-coding-template/`:

```bash
cd 01-coding-template
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
hud deploy
hud sync tasks
```

What each command does:

- `hud deploy` creates or updates the HUD environment image
- `hud sync tasks` uploads the local task definitions to the HUD taskset

Important: `hud sync tasks` is not a universal replacement for `hud deploy`.

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

`ast-pilot run` produces a scratch output directory like this:

```text
output/your-task-slug/
├── evidence.json
├── start.md
└── tasks/
    └── your-task-slug/
        ├── __init__.py
        ├── prompt.md
        ├── task.py
        ├── tests/
        ├── golden/
        ├── support/
        └── requirements.hidden.txt
```

Here is what each piece is for:

- `evidence.json` is the raw AST extraction. It is useful for debugging, but it is not shipped to the agent.
- `start.md` is the generated task spec before it gets copied into the task package.
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
- pure Python modules are the safest path today
- modules that depend on native extensions, live services, databases, or app runtime state are not good task candidates
- `integration_test` proves the harness is sound, but it does not prove the task will be easy for a model
- `hud sync tasks` is not always enough after the first deploy; if hidden support, hidden dependencies, or shared environment files changed, you must run `hud deploy` again so the image actually contains those changes

If you want the highest reliability, prefer focused, self-contained modules with strong test coverage and minimal runtime coupling.

## LLM Mode vs `--no-llm`

Use LLM mode for real tasks.

`--no-llm` is only for fast structural checks when you want to test the pipeline without spending model calls. The deterministic prompt is accurate, but it reads like a technical dump and performs noticeably worse with real agents.

Dry-run example:

```bash
uv run ast-pilot run path/to/source.py \
    --tests path/to/tests.py \
    --name my-task \
    --no-llm \
    --output output/my-task
```

## Troubleshooting

### `ModuleNotFoundError` during `integration_test`

The usual causes are:

- a missing repo-internal helper in `support/`
- a missing hidden third-party dependency in `requirements.hidden.txt`
- a hidden test import that was not rewritten correctly for the workspace module name

Check the failing import first. That will usually tell you whether the problem is hidden support, a missing dependency, or a bad test rewrite.

### `Reward: 0.000` in `integration_test`

Treat this as a broken task harness, not a model failure.

Common causes:

- the golden source cannot import one of its hidden dependencies
- the hidden tests still refer to the original package path instead of the workspace module
- the task package was copied into the wrong directory name under `01-coding-template/tasks/`

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

After having successfully ran the tasks on hud, we have a beta feature that you should use called QA Agents. This is still in beta so take it with a grain of salt, but in our internal benchmarks we've seen a success rate of around 70%!

There are 4 different qa agents one can use right now on our platform in beta. For this specific template and use case, you should only use 2 of them:
    - Failure Mode Analysis agent -- this agent does a thorogh analysis on why the agent actually failed the task we have it, and where it went wrong during the full trace. This is crucial part for us since failure mode diversity is our most important goal here.
    - Reward Hacking agent -- this agent goes through the trace and catches agents that try to hack their way into getting a perfect score. This is extremely useful for isntances where, for example, and environment is not built well enough and the golden trace (the original codebase) is not secured and the agent can just copy it and get a score of 100%. We want to avoid this in 100% of our tasks and traces so running this agent is a must when a task is deemed good.

If you are calibrating difficulty more seriously, run multiple attempts and inspect the failures before deciding the task is ready to ship.

### The validator complains about something that looks correct

The validator checks prose against exact extracted facts. When it flags something suspicious, inspect the specific line and compare it with `evidence.json`. Some false positives do happen, but most real failures come from signatures, constants, or field names drifting in prose.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | required for LLM mode | Used for prompt generation and fixer calls |
| `HUD_API_KEY` | required for HUD commands | Used by `hud eval`, `hud deploy`, and sync |
| `AST_PILOT_MODEL` | `claude-haiku-4-5` | Model used for prose generation and fixer calls |
| `HUD_ENV_NAME` | `mario-claire` | Original local placeholder environment name. It is hardcoded into the template/task wiring and MUST be changed for your own deployment. || `CODING_GITHUB_TOKEN` | unset | Optional build secret for private repo clones in `Dockerfile.hud` |

## Short Version

If you only remember one path, remember this:

1. Generate with `uv run ast-pilot run ...`
2. Copy the task into `01-coding-template/tasks/...`
3. Run `hud build .`
4. Run `hud eval . integration_test --task-ids <slug> -y`
5. Only then run model evals or deploy
