from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts


class ScriptsTests(unittest.TestCase):
    def test_required_env_name_returns_hud_env_name(self) -> None:
        with patch.dict(os.environ, {"HUD_ENV_NAME": "release-env"}, clear=False):
            self.assertEqual(scripts._required_env_name(), "release-env")

    def test_required_env_name_exits_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                with self.assertRaises(SystemExit) as ctx:
                    scripts._required_env_name()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("HUD_ENV_NAME is required", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
