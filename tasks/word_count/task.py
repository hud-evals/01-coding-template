"""Task: build word-count from scratch."""

from hud import Environment
from hud.eval.task import Task

from tasks._helpers import (
    golden_validation,
    load_prompt,
    load_requirements,
    load_support,
    pytest_grader,
    resolve_env_name,
)

SCENARIO_ID = "ast-pilot:coding-task-v2"

task = Task(
    env=Environment(resolve_env_name(__file__)),
    scenario=SCENARIO_ID,
    args={
        "prompt": load_prompt(__file__),
        "graders": [
            pytest_grader('test_counter.py', task_file=__file__, weight=1.0),
        ],
        "support": load_support(__file__),
        "hidden_requirements": load_requirements(__file__),
    },
)
task.slug = 'word-count'
task.validation = golden_validation(__file__)
