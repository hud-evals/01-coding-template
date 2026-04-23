"""Small shared helpers used across ast-pilot backends."""

from __future__ import annotations

from pathlib import Path


def slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


def pkg_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_required_symbols_text(items: list[str]) -> str:
    if not items:
        return "- No explicit tested symbols were extracted."
    return "\n".join(f"- {item}" for item in items)


def primary_module_name(target_files: list[str], project_name: str) -> str:
    """Dotted module name for the first workspace target.

    Converts workspace-relative paths back into import-style module names
    (``agent/retry_utils.py`` → ``agent.retry_utils``) so the prompt can
    show accurate ``from pkg.mod import …`` snippets for nested layouts.
    """
    if target_files:
        rel = target_files[0]
        without_suffix = rel[:-3] if rel.endswith(".py") else rel
        return without_suffix.replace("/", ".")
    return pkg_name(project_name)
