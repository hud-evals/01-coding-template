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


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _client
    _client = None
