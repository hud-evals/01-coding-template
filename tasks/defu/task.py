"""Task: build defu (TypeScript) from scratch."""

from hud import Environment
from hud.eval.task import Task

from tasks._helpers import (
    golden_workspace_validation,
    load_node_project,
    load_prompt,
    load_support,
    resolve_env_name,
    vitest_grader,
)

SCENARIO_ID = "ast-pilot:coding-task-v2"

task = Task(
    env=Environment(resolve_env_name(__file__)),
    scenario=SCENARIO_ID,
    args={
        "prompt": load_prompt(__file__),
        "graders": [
            vitest_grader('test/defu.test.ts', task_file=__file__, weight=0.5),
            vitest_grader('test/utils.test.ts', task_file=__file__, weight=0.5),
        ],
        "support": load_support(__file__),
        "node_project": load_node_project(__file__),
    },
)
task.slug = 'defu'
task.validation = golden_workspace_validation(__file__)
