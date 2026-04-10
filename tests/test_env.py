from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ENV_PATH = Path(__file__).resolve().parents[1] / "env.py"


class _FakeEnvironment:
    def __init__(self, name: str):
        self.name = name
        self.tools = []

    def add_tool(self, tool) -> None:
        self.tools.append(tool)

    def scenario(self, *_args, **_kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeTool:
    def __init__(self) -> None:
        self.mcp = object()


def _load_env_module(
    env_vars: dict[str, str],
    extra_sys_path: list[str] | None = None,
    dotenv_text: str | None = None,
):
    module_name = "_ast_pilot_env_test"

    fake_hud = types.ModuleType("hud")
    fake_hud.__path__ = []
    fake_hud.Environment = _FakeEnvironment

    fake_hud_tools = types.ModuleType("hud.tools")
    fake_hud_tools.__path__ = []

    fake_hud_tools_coding = types.ModuleType("hud.tools.coding")
    fake_hud_tools_coding.BashTool = _FakeTool
    fake_hud_tools_coding.EditTool = _FakeTool

    fake_tasks = types.ModuleType("tasks")

    spec = importlib.util.spec_from_file_location(module_name, ENV_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None

    old_sys_path = list(sys.path)
    sys.path = list(extra_sys_path or []) + old_sys_path
    dotenv_path = ENV_PATH.with_name(".env")
    original_is_file = Path.is_file
    original_read_text = Path.read_text

    def fake_is_file(path: Path) -> bool:
        if path == dotenv_path:
            return dotenv_text is not None
        return original_is_file(path)

    def fake_read_text(path: Path, *args, **kwargs) -> str:
        if dotenv_text is not None and path == dotenv_path:
            return dotenv_text
        return original_read_text(path, *args, **kwargs)

    try:
        with (
            patch.dict(os.environ, env_vars, clear=True),
            patch.object(Path, "is_file", fake_is_file),
            patch.object(Path, "read_text", fake_read_text),
            patch.dict(
                sys.modules,
                {
                    "hud": fake_hud,
                    "hud.tools": fake_hud_tools,
                    "hud.tools.coding": fake_hud_tools_coding,
                    "tasks": fake_tasks,
                },
                clear=False,
            ),
        ):
            sys.modules.pop(module_name, None)
            spec.loader.exec_module(module)
            return module
    finally:
        sys.path = old_sys_path


class EnvTests(unittest.TestCase):
    def test_uses_stable_internal_environment_name(self) -> None:
        module = _load_env_module({})
        self.assertEqual(module.env.name, "ast-pilot")

    def test_internal_environment_name_does_not_depend_on_hud_env_name(self) -> None:
        module = _load_env_module({"HUD_ENV_NAME": "release-env"})
        self.assertEqual(module.env.name, "ast-pilot")

    def test_internal_environment_name_does_not_depend_on_dotenv(self) -> None:
        module = _load_env_module({}, dotenv_text="HUD_ENV_NAME=dotenv-env\n")
        self.assertEqual(module.env.name, "ast-pilot")

    def test_scenario_id_uses_stable_prefix(self) -> None:
        module = _load_env_module({})
        self.assertEqual(module.SCENARIO_ID, "ast-pilot:coding-task")


if __name__ == "__main__":
    unittest.main()
