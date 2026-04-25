"""Simple word-count utility."""

from __future__ import annotations

WHITESPACE = " \t\n\r\f\v"


def count_words(text: str) -> int:
    """Return the number of whitespace-delimited tokens in *text*."""
    if text is None:
        return 0
    return len([tok for tok in text.split() if tok])


def unique_words(text: str) -> set[str]:
    """Return the set of unique case-folded words in *text*."""
    return {tok.casefold() for tok in text.split() if tok}
