"""Coding environment — tools for 0-to-1 development tasks.

The agent starts in a blank workspace, receives a long markdown prompt
describing a library/API to build from scratch, and is graded by running
tests from the original repository against its implementation.

Two scenarios are registered:

* ``coding-task`` — task artifacts (tests, golden, support) live on the
  image under ``/mcp_server/tasks``; ``task.py`` reads them from disk at
  grade time. Kept for backward compatibility with existing tasks.
* ``coding-task-v2`` — task artifacts are inlined into ``Task.args`` at
  sync time and staged by the scenario at grade time. Adding a new task
  only requires ``hud sync`` — no image rebuild.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from hud import Environment
from hud.tools.coding import BashTool, EditTool

logger = logging.getLogger(__name__)
SCENARIO_ENV_NAME = "ast-pilot"
SCENARIO_ID = f"{SCENARIO_ENV_NAME}:coding-task"
SCENARIO_ID_V2 = f"{SCENARIO_ENV_NAME}:coding-task-v2"

env = Environment(SCENARIO_ENV_NAME)

bash_tool = BashTool()
edit_tool = EditTool()

env.add_tool(bash_tool.mcp)
env.add_tool(edit_tool.mcp)


# ============================================================================
# Scenario Helpers
# ============================================================================

ValidateMode = Literal["baseline_fail", "golden_pass"]

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/home/ubuntu/workspace")


def make_prompt(description: str) -> str:
    """Format a task description into an agent prompt."""
    return (
        f"Your solution files belong in {WORKSPACE_DIR}.\n"
        "Your shell may start in a different current directory, so create/edit files in that workspace path explicitly.\n"
        "Use bash and editor tools to complete the following task:\n\n"
        f"{description}"
    )


# ============================================================================
# Scenario: coding-task
# ============================================================================


@env.scenario("coding-task", required_env_vars=["HUD_API_KEY", "HUD_ENV_NAME"])
async def coding_task(
    prompt: str,
    bash_checks: list[dict] | None = None,
    validate_mode: ValidateMode | None = None,
):
    """General coding task scenario.

    Sets up a blank workspace, presents the prompt, then grades using
    deterministic bash checks (typically: run tests from the original repo).

    Args:
        prompt: The task instruction shown to the agent.
        bash_checks: List of {"name": str, "command": str, "weight": float}
                     dicts for deterministic shell-based grading.
        validate_mode: Used by validation (baseline_fail / golden_pass).
    """
    from hud.native.graders import BashGrader, Grade
    from hud.tools.types import SubScore

    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    yield make_prompt(prompt)

    graders = []

    if bash_checks:
        for check in bash_checks:
            graders.append(
                BashGrader.grade(
                    name=check["name"],
                    weight=check.get("weight", 1.0),
                    command=check["command"],
                )
            )

    if not graders:
        graders.append(SubScore(name="no_graders_defined", value=0.0, weight=1.0))

    yield await Grade.gather(*graders)


# ============================================================================
# Scenario: coding-task-v2 (sync-only; all artifacts arrive in Task.args)
# ============================================================================

# Support files stage outside the workspace so an agent-created package
# cannot shadow a support package of the same name and break transitive
# imports from the hidden tests.
SUPPORT_STAGING_ROOT = Path("/opt/task_support")
REQUIREMENTS_DIR = Path("/tmp")

# TypeScript tasks mirror the original repo tree into this staging root so
# vitest can resolve relative imports, tsconfig paths, and find node_modules.
NODE_STAGING_ROOT = Path("/tmp/ast_pilot_ts_stage")
# node_modules is cached per content-hash of package.json+lockfile — a single
# install serves every task with the same dependency set across reruns.
NODE_MODULES_CACHE_ROOT = Path("/tmp/ast_pilot_node_modules")


def _stage_support(support: dict[str, str] | None) -> None:
    """Write each inlined support file to /opt/task_support/ and add to sys.path."""
    if not support:
        return
    if SUPPORT_STAGING_ROOT.exists():
        shutil.rmtree(SUPPORT_STAGING_ROOT)
    SUPPORT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    for rel, content in support.items():
        dst = SUPPORT_STAGING_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    root_str = str(SUPPORT_STAGING_ROOT)
    if root_str not in sys.path:
        sys.path.append(root_str)


def _write_requirements_file(hidden_requirements: str | None) -> Path | None:
    """Write hidden_requirements to /tmp so ``uv run --with-requirements`` can read it.

    Returns the path, or None when there are no requirements. uv's own cache
    handles resolution memoization — this function just needs the contents on
    disk under a content-hashed name so concurrent graders share one file.
    """
    if not hidden_requirements:
        return None
    digest = hashlib.sha256(hidden_requirements.encode("utf-8")).hexdigest()[:12]
    req_path = REQUIREMENTS_DIR / f"task_requirements_{digest}.txt"
    if not req_path.exists():
        req_path.write_text(hidden_requirements, encoding="utf-8")
    return req_path


def _stage_node_project(
    node_project: dict[str, Any] | None,
) -> tuple[Path | None, list[str], str]:
    """Materialize a TS project's static files into ``NODE_STAGING_ROOT/<slug>/``.

    Writes ``config_files`` + ``support_files`` at their repo-relative paths,
    pre-creates parent dirs for every ``source_files`` entry the agent is
    expected to produce, then lazily installs ``node_modules`` into a
    content-hashed cache (keyed by package.json + lockfile) and symlinks it
    into the staging tree. Running at scenario boot rather than in the grader
    bash avoids a startup race where two vitest graders concurrently re-seed
    the cache directory.

    Returns ``(staging_dir, source_files, node_modules_cache_dir)`` or
    ``(None, [], "")`` when the task is not a TS task.
    """
    if not node_project:
        return None, [], ""

    slug = node_project["slug"]
    staging = NODE_STAGING_ROOT / slug
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    config_files = node_project.get("config_files", {})
    for rel, content in config_files.items():
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")

    for rel, content in node_project.get("support_files", {}).items():
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")

    # Pre-create parent dirs for every source file the agent is expected to
    # produce — the grader bash command copies from WORKSPACE_DIR into these
    # paths with a no-clobber fallback, which silently no-ops if the parent
    # dir doesn't exist (cp errors go to /dev/null). Without this, vitest
    # reads the stale empty staging tree and fails with ERR_MODULE_NOT_FOUND.
    for rel in node_project.get("source_files", []):
        (staging / rel).parent.mkdir(parents=True, exist_ok=True)

    fingerprint = config_files.get("package.json", "") + config_files.get(
        "package-lock.json", ""
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
    cache_dir = NODE_MODULES_CACHE_ROOT / digest
    _ensure_node_modules_cache(cache_dir, config_files)
    # Symlink staging/node_modules -> cache/node_modules so vitest finds deps.
    staging_modules = staging / "node_modules"
    if staging_modules.is_symlink() or staging_modules.exists():
        if staging_modules.is_symlink() or staging_modules.is_file():
            staging_modules.unlink()
        else:
            shutil.rmtree(staging_modules)
    staging_modules.symlink_to(cache_dir / "node_modules")

    return staging, list(node_project.get("source_files", [])), str(cache_dir)


def _ensure_node_modules_cache(cache_dir: Path, config_files: dict[str, str]) -> None:
    """Install node_modules into ``cache_dir`` exactly once per content hash.

    Runs synchronously at scenario boot — single-caller path, no race with
    grader bash commands. ``.installed`` marker makes repeat calls idempotent,
    so the install cost is paid once per unique package.json + lockfile.
    """
    marker = cache_dir / ".installed"
    if marker.exists():
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "package.json").write_text(
        config_files.get("package.json", "{}"), encoding="utf-8"
    )
    lock = config_files.get("package-lock.json")
    if lock:
        (cache_dir / "package-lock.json").write_text(lock, encoding="utf-8")
    cmd = (
        "npm ci --ignore-scripts 2>/dev/null "
        "|| npm install --legacy-peer-deps --ignore-scripts"
    )
    subprocess.run(cmd, shell=True, cwd=str(cache_dir), check=True)
    marker.touch()


def _build_grader_command(
    grader: dict[str, Any],
    requirements_path: Path | None,
    node_staging: Path | None = None,
    node_source_files: list[str] | None = None,
    node_modules_cache: str = "",
) -> tuple[str, str, int, float]:
    """Translate one grader dict into (name, bash_command, timeout, weight).

    pytest-kind: writes the test content to /tmp and runs it via
    ``uv run --no-project --with pytest [--with-requirements …]`` — uv resolves
    and caches the requirement set per content-hash, no venv mutation.
    vitest-kind: writes the test into ``node_staging`` and runs
    ``npx vitest run <test_rel> --reporter=verbose`` after lazily installing
    ``node_modules`` into a content-hashed cache and symlinking it in.
    bash-kind: runs the provided command verbatim (escape hatch).
    """
    weight = float(grader.get("weight", 1.0))
    timeout = int(grader.get("timeout", 120))
    kind = grader.get("kind", "pytest")

    if kind == "pytest":
        test_name = grader["test_name"]
        test_path = Path("/tmp") / test_name
        test_path.write_text(grader["script"], encoding="utf-8")
        pythonpath = f"{WORKSPACE_DIR}:{SUPPORT_STAGING_ROOT}:$PYTHONPATH"
        uv_flags = "--no-project --with pytest"
        if requirements_path is not None:
            uv_flags += f" --with-requirements {requirements_path}"
        command = (
            f"cd {WORKSPACE_DIR} && "
            f"AST_PILOT_REPO_ROOT={WORKSPACE_DIR} "
            f"PYTHONPATH={pythonpath} "
            f"uv run {uv_flags} python -m pytest {test_path} -v"
        )
        return grader["name"], command, timeout, weight

    if kind == "vitest":
        if node_staging is None:
            raise ValueError(
                "vitest grader requires node_project to be set on the task"
            )
        test_rel = grader["test_rel"]
        test_path = node_staging / test_rel
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(grader["script"], encoding="utf-8")

        # Scenario setup already wrote config+support files, installed
        # node_modules into the content-hashed cache, symlinked it into
        # the staging tree, and pre-created source_files parent dirs. The
        # grader bash only needs to sync the agent's latest sources from
        # WORKSPACE_DIR and invoke vitest.
        del node_modules_cache  # used at scenario boot, not grader time
        source_cps: list[str] = []
        for rel in sorted(node_source_files or []):
            parent = str(Path(rel).parent)
            dst_dir = f"{node_staging}" if parent in ("", ".") else f"{node_staging}/{parent}"
            source_cps.append(
                f"(mkdir -p {dst_dir} && cp {WORKSPACE_DIR}/{Path(rel).name} {node_staging}/{rel} 2>/dev/null || true)"
            )
        parts = [*source_cps, f"cd {node_staging}",
                 f"npx vitest run {test_rel} --reporter=verbose"]
        return grader["name"], " && ".join(parts), timeout, weight

    if kind == "bash":
        return grader["name"], grader["command"], timeout, weight

    raise ValueError(f"Unknown grader kind: {kind!r}")


@env.scenario("coding-task-v2", required_env_vars=["HUD_API_KEY", "HUD_ENV_NAME"])
async def coding_task_v2(
    prompt: str,
    graders: list[dict[str, Any]] | None = None,
    support: dict[str, str] | None = None,
    hidden_requirements: str | None = None,
    node_project: dict[str, Any] | None = None,
):
    """Sync-only coding task scenario.

    All task artifacts (tests, support, hidden deps) arrive inside ``args`` —
    the Docker image holds only env.py + runtime. Staging layout:

      * support  -> /opt/task_support/  (appended to sys.path)
      * tests    -> /tmp/<test_name>    (written per-grader inside grading)
      * hidden_requirements -> /tmp/task_requirements_<hash>.txt, consumed by
                               ``uv run --with-requirements`` at grader time
      * node_project (TS only) -> /tmp/ast_pilot_ts_stage/<slug>/  (repo tree)
                               node_modules is lazily installed into a
                               content-hashed cache at grader time

    Golden pre-staging for ``hud eval integration_test`` happens via
    ``Task.validation`` (bash MCPToolCall with inlined base64 content) and
    fires before this scenario runs — not a scenario concern.

    Args:
        prompt: The task instruction shown to the agent.
        graders: List of grader dicts (see tasks/_helpers.pytest_grader /
                 tasks/_helpers.vitest_grader).
        support: {relative_path: utf-8 content} for repo-internal helper modules.
        hidden_requirements: Contents of requirements.hidden.txt (or "").
        node_project: TS bundle with keys ``slug``, ``config_files``,
                      ``support_files``, ``source_files`` (see
                      ``tasks/_helpers.load_node_project``).
    """
    from hud.native.graders import BashGrader, Grade
    from hud.tools.types import SubScore

    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    _stage_support(support)
    requirements_path = _write_requirements_file(hidden_requirements)
    node_staging, node_sources, node_cache = _stage_node_project(node_project)

    yield make_prompt(prompt)

    grader_list = graders or []
    if not grader_list:
        yield [SubScore(name="no_graders_defined", value=0.0, weight=1.0)]
        return

    total_weight = sum(float(g.get("weight", 1.0)) for g in grader_list) or 1.0
    jobs = []
    for g in grader_list:
        name, command, timeout, weight = _build_grader_command(
            g,
            requirements_path,
            node_staging=node_staging,
            node_source_files=node_sources,
            node_modules_cache=node_cache,
        )
        jobs.append(BashGrader.grade(
            name=name,
            weight=weight / total_weight,
            command=command,
            timeout_seconds=timeout,
        ))

    yield await Grade.gather(*jobs)


# ============================================================================
# Import task definitions (auto-discovers tasks/<name>/task.py)
# ============================================================================

import tasks  # noqa: E402, F401
