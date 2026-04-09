from __future__ import annotations

import importlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def _load_build_support_module():
    path = Path(__file__).resolve().parents[1] / "build_support.py"
    spec = importlib.util.spec_from_file_location("build_support_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load build_support.py from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildSupportTests(unittest.TestCase):
    def test_stage_support_assets_hides_cross_task_target_source(self) -> None:
        build_support = _load_build_support_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_root = root / "tasks"
            support_root = root / "support"
            requirements_path = root / "requirements.hidden.txt"

            anthropic_task = tasks_root / "anthropic_adapter"
            context_task = tasks_root / "context_references"

            for task_dir in (anthropic_task, context_task):
                (task_dir / "support" / "agent").mkdir(parents=True, exist_ok=True)

            (anthropic_task / "task.py").write_text(
                "task.slug = 'anthropic-adapter'\n",
                encoding="utf-8",
            )
            (anthropic_task / "support" / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (anthropic_task / "support" / "agent" / "anthropic_adapter.py").write_text(
                '"""Shim for `agent.anthropic_adapter` used during hidden grading."""\n\n'
                "from anthropic_adapter import *\n",
                encoding="utf-8",
            )

            (context_task / "task.py").write_text(
                "task.slug = 'context-references'\n",
                encoding="utf-8",
            )
            (context_task / "support" / "agent" / "__init__.py").write_text("", encoding="utf-8")
            (context_task / "support" / "agent" / "anthropic_adapter.py").write_text(
                "SECRET_VALUE = 41\n",
                encoding="utf-8",
            )

            build_support.stage_support_assets(tasks_root, support_root, requirements_path)

            staged_source = support_root / "context_references" / "agent" / "anthropic_adapter.py"
            staged_text = staged_source.read_text(encoding="utf-8")
            self.assertNotIn("SECRET_VALUE = 41", staged_text)
            self.assertIn("spec_from_file_location", staged_text)

            hidden_files = list((support_root / "context_references" / ".ast_pilot_hidden").glob("*.pyc"))
            self.assertEqual(len(hidden_files), 1)
            self.assertTrue((support_root / "anthropic-adapter").is_symlink())

            importlib.invalidate_caches()
            sys.path.insert(0, str(support_root / "context_references"))
            sys.modules.pop("agent", None)
            sys.modules.pop("agent.anthropic_adapter", None)
            try:
                imported = importlib.import_module("agent.anthropic_adapter")
                self.assertEqual(imported.SECRET_VALUE, 41)
            finally:
                sys.path.pop(0)
                sys.modules.pop("agent", None)
                sys.modules.pop("agent.anthropic_adapter", None)


if __name__ == "__main__":
    unittest.main()
