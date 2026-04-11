# 01-coding-template

Coding environment template for 0-to-1 development tasks on the [HUD platform](https://hud.ai).

The agent starts in a blank workspace, receives a long markdown prompt describing a library/API to build from scratch, and is graded by running hidden tests against its implementation.

For the end-to-end vendor workflow, task generation process, validation rules, deployment guidance, and calibration advice, start with `USAGE.md`.

## Quick Start

```bash
uv sync
cp .env.example .env  # add your HUD_API_KEY and HUD_ENV_NAME
source .env

hud build .
hud deploy . -n "$HUD_ENV_NAME"
hud eval . integration_test --all -y
hud eval . claude --all -y --max-steps 30
```

## Creating a Task

Each task is a self-contained package under `tasks/<name>/`:

```
tasks/my_task/
├── __init__.py      # from .task import *
├── task.py          # Task definition (prompt, grading, validation)
├── prompt.md        # Long markdown instructions for the agent
└── tests/           # Hidden test files used for grading
    └── test_*.py
```

### task.py

```python
import os
from pathlib import Path
from hud.eval.task import Task
from hud.types import MCPToolCall
from task_bootstrap import require_hud_env_name

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    SCENARIO_ID = "ast-pilot:coding-task"
    TASK_DIR = Path(__file__).parent
    ENV_NAME = require_hud_env_name(TASK_DIR.parents[1] / ".env")

    env = Environment(ENV_NAME)
    env.connect_hub(ENV_NAME)

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": (TASK_DIR / "prompt.md").read_text(),
            "bash_checks": [
                {
                    "name": "tests_pass",
                    "command": "...generated pytest command...",
                    "weight": 1.0,
                },
            ],
        },
    )
    task.slug = "my-task-slug"

    # Golden solution for validation (baseline_fail / golden_pass)
    task.validation = [
        MCPToolCall(name="bash", arguments={"command": "...golden solution commands..."}),
    ]
```

### prompt.md

Long markdown file describing the full library/API the agent should build — the project architecture, all functions, APIs, data structures, etc.

### Grading

Grading uses `BashGrader` from the HUD SDK. Each `bash_check` runs a shell command; exit code 0 = pass, non-zero = fail.

The typical pattern: carry hidden tests inside `tasks/<name>/tests/`, then let the generated `task.py` inject and run them during grading.

### Validation

`task.validation` defines MCPToolCall steps that produce the golden solution. Used by `hud eval . integration_test --all -y` to verify:
- **golden_pass**: apply the golden solution, then run graders — should score 1.0
- **baseline_fail**: run graders on the blank workspace — should score 0.0

For this template's hub-connected tasks, `integration_test` should be treated as validation against the deployed HUD environment, not just the last local image you built.

## Using Private Repos

For tasks based on private repositories, pass a GitHub token at build time:

```bash
export CODING_GITHUB_TOKEN=ghp_...
hud build . --build-arg REPO_URL=https://github.com/org/repo \
            --secret id=CODING_GITHUB_TOKEN,env=CODING_GITHUB_TOKEN
```

The repo is cloned to `/home/root/golden` (invisible to the agent). Use it for extracting tests or as the validation golden solution.

## Structure

```
01-coding-template/
├── env.py           # Environment: SDK tools, shared ast-pilot scenario
├── cli.py           # MCP server entry point
├── task_bootstrap.py # Local .env loading for generated tasks
├── grading/         # SDK grader re-exports
├── tasks/
│   ├── __init__.py  # Auto-discovery
│   └── example_task/
│       ├── task.py
│       ├── prompt.md
│       └── tests/
├── Dockerfile.hud   # Container (Ubuntu + Python, no desktop)
└── pyproject.toml   # hud-python>=0.5.35
```

## Commands

```bash
hud build .                                    # Build and sanity-check the local image
hud deploy . -n "$HUD_ENV_NAME"                # Deploy/update the HUD environment
hud eval . integration_test --all -y           # Validate tasks against the deployed env
hud eval . claude --all -y --max-steps 30      # Run all tasks with Claude
hud sync tasks <taskset-name>                  # Sync tasks to a taskset
```
