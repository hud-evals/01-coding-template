"""CLI scripts for managing tasks."""

import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, parse, request

PROJECT_ROOT = str(Path(__file__).parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _collect_tasks():
    """Discover all Task objects from tasks/ subpackages."""
    import tasks as tasks_pkg

    raw_tasks = getattr(tasks_pkg, "tasks", {})
    task_ids = getattr(tasks_pkg, "task_ids", {})
    if not raw_tasks:
        print("No Task objects found in tasks/ subpackages.")
        sys.exit(1)
    return dict(raw_tasks), dict(task_ids)


def _load_env() -> dict[str, str]:
    env_file = Path(__file__).parent / ".env"
    env: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def _api_json(method: str, *, api_url: str, api_key: str, path: str,
              payload: dict | list | None = None) -> Any:
    url = f"{api_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {api_key}"}
    body: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()

    req = request.Request(url, headers=headers, data=body, method=method.upper())
    try:
        with request.urlopen(req) as resp:  # noqa: S310
            raw = resp.read()
            return json.loads(raw.decode()) if raw else None
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method.upper()} {path} failed ({e.code}): {detail}") from e


def sync_tasks():
    """Sync local task definitions to a HUD platform taskset.

    Usage: uv run sync-tasks --taskset <name> --env <env-name>
    """
    import argparse

    parser = argparse.ArgumentParser(description="Sync local tasks to a HUD taskset")
    parser.add_argument("--taskset", required=True, help="Taskset name on the platform")
    parser.add_argument("--env", dest="env_name", required=True, help="Deployed environment name")
    args = parser.parse_args()

    from hud.settings import settings as hud_settings

    api_key = hud_settings.api_key
    if not api_key:
        print("HUD_API_KEY is required. Set via `hud set HUD_API_KEY=...`")
        sys.exit(1)
    api_url = hud_settings.hud_api_url

    tasks_by_name, task_ids = _collect_tasks()

    upload_tasks = []
    for task_name, task in tasks_by_name.items():
        scenario_name = getattr(task, "scenario", None)
        if not scenario_name:
            print(f"Task '{task_name}' has no scenario")
            sys.exit(1)

        task_env = getattr(task, "env", None)
        env_class_name = getattr(task_env, "name", None) if task_env else None
        if env_class_name and ":" not in scenario_name:
            scenario_name = f"{env_class_name}:{scenario_name}"

        task_slug = task_ids.get(task_name)
        if not task_slug:
            print(f"Task '{task_name}' has no slug. Set task.slug in task.py.")
            sys.exit(1)

        args_dict = getattr(task, "args", None) or {}
        validation = getattr(task, "validation", None)
        validation_list = None
        if validation:
            validation_list = [{"name": v.name, "arguments": v.arguments or {}} for v in validation]

        entry: dict[str, Any] = {
            "slug": task_slug,
            "env": {"name": args.env_name},
            "scenario": scenario_name,
            "args": args_dict,
        }
        if validation_list is not None:
            entry["validation"] = validation_list

        upload_tasks.append(entry)
        print(f"  {task_name} -> {task_slug} ({scenario_name})")

    print(f"\nUploading {len(upload_tasks)} task(s) to taskset '{args.taskset}' on env '{args.env_name}'...")

    result = _api_json(
        "POST",
        api_url=api_url,
        api_key=api_key,
        path="/tasks/upload",
        payload={"name": args.taskset, "tasks": upload_tasks},
    )

    print(f"Done. Response: {json.dumps(result, indent=2)}")
