"""Tests for textkit.counter."""
import sys
sys.path.insert(0, "/home/ubuntu/workspace")

from textkit.counter import count_words, unique_words, WHITESPACE


def test_count_words_simple() -> None:
    assert count_words("hello world") == 2


def test_count_words_empty() -> None:
    assert count_words("") == 0


def test_count_words_whitespace_only() -> None:
    assert count_words("   \t\n  ") == 0


def test_count_words_none() -> None:
    assert count_words(None) == 0


def test_unique_words_casefolds() -> None:
    assert unique_words("Hello HELLO hello") == {"hello"}


def test_unique_words_empty() -> None:
    assert unique_words("") == set()


def test_whitespace_constant_has_expected_chars() -> None:
    assert " " in WHITESPACE
    assert "\t" in WHITESPACE
    assert "\n" in WHITESPACE