from __future__ import annotations

import os
import sys
from pathlib import Path


def apply_dotenv_defaults(env_file: Path) -> None:
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def is_hud_analysis_import() -> bool:
    return any(path.startswith("/opt/hud-analysis/") for path in sys.path)


def require_hud_env_name(
    env_file: Path | None = None,
    *,
    allow_analysis_placeholder: bool = False,
    error_message: str | None = None,
) -> str:
    if env_file is not None:
        apply_dotenv_defaults(env_file)

    env_name = os.environ.get("HUD_ENV_NAME", "").strip()
    if env_name:
        return env_name

    if allow_analysis_placeholder and is_hud_analysis_import():
        return "ast_pilot_analysis"

    raise RuntimeError(
        error_message
        or "HUD_ENV_NAME is required. Set it in `.env` or your shell before running HUD commands."
    )
