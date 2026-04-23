"""Shared LLM helper backed by the HUD inference gateway.

All LLM usage in ast-pilot goes through ``call_text_llm`` so that
tests can mock a single function and the auth / model wiring lives
in one place.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_client = None
_client_api_key: str | None = None

HUD_GATEWAY_BASE_URL = "https://inference.hud.ai/v1"
DEFAULT_MODEL = "claude-haiku-4-5"


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
        text = _extract_response_text(response)
    except Exception as exc:
        print(f"[warn] LLM call failed: {exc}")
        return None

    if text is None:
        return None

    if expect_json:
        text = _strip_markdown_fences(text)
        try:
            json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    return text


def _strip_markdown_fences(text: str) -> str:
    """Remove surrounding ```json fences some models insist on emitting."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].lstrip("`").strip().lower() in ("", "json"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _get_client():
    """Return a cached OpenAI-compatible client pointing at the HUD gateway."""
    global _client, _client_api_key

    _load_dotenv()

    hud_key = os.environ.get("HUD_API_KEY", "")
    if not hud_key:
        return None

    if _client is not None and _client_api_key == hud_key:
        return _client

    try:
        from openai import OpenAI

        _client = OpenAI(
            api_key=hud_key,
            base_url=HUD_GATEWAY_BASE_URL,
        )
        _client_api_key = hud_key
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

    for parent in (Path.cwd(), *Path.cwd().parents):
        env_file = parent / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                parsed = _parse_dotenv_line(line)
                if parsed is None:
                    continue
                key, value = parsed
                if key not in os.environ:
                    os.environ[key] = value
            break


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None

    key, _, raw_value = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    return key, _parse_dotenv_value(raw_value.strip())


def _parse_dotenv_value(raw_value: str) -> str:
    if not raw_value:
        return ""

    quote = raw_value[0]
    if quote in {'"', "'"}:
        value_chars: list[str] = []
        escaped = False
        for char in raw_value[1:]:
            if escaped:
                value_chars.append(char)
                escaped = False
                continue
            if quote == '"' and char == "\\":
                escaped = True
                continue
            if char == quote:
                return "".join(value_chars)
            value_chars.append(char)
        return raw_value[1:]

    return re.sub(r"\s+#.*$", "", raw_value).strip()


def _extract_response_text(response) -> str | None:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_extract_text_part(part) for part in content]
        text = "".join(part for part in parts if part)
        return text or None

    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    return None


def _extract_text_part(part) -> str | None:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        text = part.get("text")
        return text if isinstance(text, str) else None

    text = getattr(part, "text", None)
    return text if isinstance(text, str) else None


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _client, _client_api_key, _dotenv_loaded
    _client = None
    _client_api_key = None
    _dotenv_loaded = False
