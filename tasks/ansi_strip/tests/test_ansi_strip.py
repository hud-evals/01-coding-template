"""Tests for tools.ansi_strip."""
import sys
sys.path.insert(0, "/home/ubuntu/workspace")

import pytest

from tools.ansi_strip import strip_ansi, _ANSI_ESCAPE_RE, _HAS_ESCAPE


def test_strip_ansi_removes_color_codes() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"


def test_strip_ansi_preserves_plain_text() -> None:
    assert strip_ansi("hello world") == "hello world"


def test_strip_ansi_handles_none() -> None:
    assert strip_ansi(None) is None


def test_strip_ansi_preserves_unicode() -> None:
    assert strip_ansi("héllo — 世界\x1b[1mbold\x1b[0m") == "héllo — 世界bold"


def test_strip_ansi_removes_osc_sequences() -> None:
    # OSC with BEL terminator
    assert strip_ansi("\x1b]0;window title\x07after") == "after"
    # OSC with ST terminator
    assert strip_ansi("\x1b]0;title\x1b\\after") == "after"


def test_strip_ansi_private_mode_csi() -> None:
    # Private-mode ? prefix
    assert strip_ansi("\x1b[?25l" + "visible" + "\x1b[?25h") == "visible"


def test_strip_ansi_csi_intermediate_bytes() -> None:
    # CSI with intermediate byte
    assert strip_ansi("before\x1b[1 @after") == "beforeafter"


def test_has_escape_pattern_matches_only_escape_bytes() -> None:
    assert _HAS_ESCAPE.search("\x1b[0m") is not None
    assert _HAS_ESCAPE.search("plain text") is None


def test_ansi_escape_re_is_compiled() -> None:
    import re
    assert isinstance(_ANSI_ESCAPE_RE, re.Pattern)


def test_strip_ansi_empty_string() -> None:
    assert strip_ansi("") == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])