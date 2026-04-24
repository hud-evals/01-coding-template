"""Task: build ansi-strip from scratch."""

import os
from pathlib import Path

from hud.eval.task import Task
from task_bootstrap import require_hud_env_name

from tasks._helpers import (
    golden_validation,
    load_prompt,
    load_requirements,
    load_support,
    pytest_grader,
)

if not os.environ.get("_HUD_DEV_CHILD"):
    from hud import Environment

    SCENARIO_ID = "ast-pilot:coding-task-v2"

    TASK_DIR = Path(__file__).parent
    ENV_NAME = require_hud_env_name(
        TASK_DIR.parents[1] / ".env",
        error_message="HUD_ENV_NAME is required. Set it before running this task.",
    )
    env = Environment(ENV_NAME)
    env.connect_hub(ENV_NAME)

    task = Task(
        env=env,
        scenario=SCENARIO_ID,
        args={
            "prompt": load_prompt(__file__),
            "graders": [
                pytest_grader('test_ansi_strip.py', task_file=__file__, weight=1.0),
            ],
            "support": load_support(__file__),
            "hidden_requirements": load_requirements(__file__),
        },
    )
    task.slug = 'ansi-strip'
    task.validation = golden_validation(__file__)
