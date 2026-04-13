"""Language dispatch: route CLI operations to the correct backend."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_LANGUAGES = ("python", "typescript")

TS_SOURCE_EXTENSIONS = frozenset({".ts", ".mts", ".cts"})
PY_SOURCE_EXTENSIONS = frozenset({".py"})


def infer_language(source_paths: list[str | Path]) -> str:
    """Infer the language from file extensions.

    Returns ``"typescript"`` when all source files are ``.ts`` / ``.mts`` / ``.cts``,
    ``"python"`` otherwise.
    """
    if not source_paths:
        return "python"

    extensions = {Path(p).suffix.lower() for p in source_paths}
    if extensions and extensions <= TS_SOURCE_EXTENSIONS:
        return "typescript"
    return "python"


def validate_language(language: str) -> str:
    """Normalise and validate a language string."""
    language = language.strip().lower()
    aliases = {"ts": "typescript", "py": "python", "js": "javascript", "javascript": "javascript"}
    language = aliases.get(language, language)

    if language == "javascript":
        raise SystemExit("JavaScript support is not yet available. Use --language typescript for .ts files.")

    if language not in SUPPORTED_LANGUAGES:
        raise SystemExit(
            f"Unsupported language: {language!r}. Supported: {', '.join(SUPPORTED_LANGUAGES)}"
        )
    return language
