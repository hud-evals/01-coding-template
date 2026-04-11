"""Shared LLM helper backed by the HUD inference gateway.

All LLM usage in ast-pilot goes through ``call_text_llm`` so that
tests can mock a single function and the auth / model wiring lives
in one place.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

_client = None

HUD_GATEWAY_BASE_URL = "https://inference.hud.ai/v1"
DEFAULT_MODEL = "claude-haiku-4-5"


@dataclass
class LLMResponse:
    text: str


def call_text_llm(
    prompt: str,
    *,
    max_tokens: int = 16384,
    expect_json: bool = False,
    temperature: float = 0,
) -> str | None:
    """Send a plain-text prompt and return the response text.

    Uses the HUD inference gateway via ``HUD_API_KEY``.

    When *expect_json* is True the response is validated as parseable
    JSON before being returned; a ``None`` return means the model
    produced invalid JSON.
    """
    client = _get_client()
    if client is None:
        return None

    model = os.environ.get("AST_PILOT_MODEL", DEFAULT_MODEL)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content
    except Exception as exc:
        print(f"[warn] LLM call failed: {exc}")
        return None

    if text and expect_json:
        try:
            json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    return text


def _get_client():
    """Return a cached OpenAI-compatible client pointing at the HUD gateway."""
    global _client
    if _client is not None:
        return _client

    _load_dotenv()

    hud_key = os.environ.get("HUD_API_KEY", "")
    if not hud_key:
        return None

    try:
        from openai import OpenAI

        _client = OpenAI(
            api_key=hud_key,
            base_url=HUD_GATEWAY_BASE_URL,
        )
        return _client
    except ImportError:
        print("[warn] openai package not installed; cannot use HUD gateway")
        return None


_dotenv_loaded = False


def _load_dotenv() -> None:
    """Load .env from the working directory or its parents if not already in env."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True

    if os.environ.get("HUD_API_KEY"):
        return

    from pathlib import Path

    for parent in (Path.cwd(), *Path.cwd().parents):
        env_file = parent / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value
            break


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _client, _dotenv_loaded
    _client = None
    _dotenv_loaded = False
