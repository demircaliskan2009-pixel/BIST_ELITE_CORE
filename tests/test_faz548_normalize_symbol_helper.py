"""FAZ548: Symbol normalization shared helper — uppercase, trim; deterministic. Test-first."""

from __future__ import annotations


from bist_core.symbol import normalize_symbol


def test_faz548_normalize_symbol_helper() -> None:
    """Uppercase and trim; lowercase input -> uppercase output."""
    assert normalize_symbol("  aaa  ") == "AAA"
    assert normalize_symbol("bbb") == "BBB"
    assert normalize_symbol("  Xyz  ") == "XYZ"


def test_faz548_normalize_symbol_deterministic() -> None:
    """Same input -> same output (deterministic)."""
    inp = "  thyao  "
    assert normalize_symbol(inp) == normalize_symbol(inp)
    assert normalize_symbol(inp) == "THYAO"


def test_faz548_normalize_symbol_edge_empty() -> None:
    """Empty/whitespace -> empty string (no crash)."""
    assert normalize_symbol("") == ""
    assert normalize_symbol("   ") == ""


def test_faz548_normalize_symbol_edge_mixed_case() -> None:
    """Mixed case -> uppercase."""
    assert normalize_symbol("ThYaO") == "THYAO"


def test_faz548_normalize_symbol_edge_dot_e_suffix() -> None:
    """BIST .E suffix stripped for consistency."""
    assert normalize_symbol("THYAO.E") == "THYAO"
    assert normalize_symbol("  thyao.e  ") == "THYAO"
