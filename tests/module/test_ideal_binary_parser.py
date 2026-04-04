"""ideal_binary_parser — public API smoke (no legacy parse_ideal_file alias)."""

from __future__ import annotations

from bist_core.data.ideal_binary_parser import parse_ideal_binary


def test_parse_ideal_binary_is_callable() -> None:
    assert callable(parse_ideal_binary)
