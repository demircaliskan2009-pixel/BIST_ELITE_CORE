"""FAZ118-HOTFIX-TRNUM: Turkish number format parsing (30.000 -> 30000, 30,5 -> 30.5)."""
from __future__ import annotations

import pytest

from bist_core.cli.main import _parse_tr_number


def test_parse_tr_number_30_000() -> None:
    """30.000 (binlik) -> 30000."""
    assert _parse_tr_number("30.000") == 30000.0


def test_parse_tr_number_2_000() -> None:
    """2.000 (binlik) -> 2000."""
    assert _parse_tr_number("2.000") == 2000.0


def test_parse_tr_number_30_5() -> None:
    """30,5 (ondalık) -> 30.5."""
    assert _parse_tr_number("30,5") == 30.5


def test_parse_tr_number_1250000() -> None:
    """1250000 (ayırıcısız) -> 1250000."""
    assert _parse_tr_number("1250000") == 1250000.0


def test_parse_tr_number_1_250_000() -> None:
    """1.250.000 (binlik) -> 1250000."""
    assert _parse_tr_number("1.250.000") == 1250000.0


def test_parse_tr_number_1_250_000_75() -> None:
    """1.250.000,75 (binlik + ondalık) -> 1250000.75."""
    assert _parse_tr_number("1.250.000,75") == 1250000.75


def test_parse_tr_number_40_000_tl() -> None:
    """40.000Tl -> 40000."""
    assert _parse_tr_number("40.000Tl") == 40000.0


def test_parse_tr_number_10_000_tl() -> None:
    """10.000TL -> 10000."""
    assert _parse_tr_number("10.000TL") == 10000.0


def test_parse_tr_number_40_000_tl_spaces() -> None:
    """40 000 TL -> 40000."""
    assert _parse_tr_number("40 000 TL") == 40000.0


def test_parse_tr_number_try_symbol() -> None:
    """₺1.250.000,75 -> 1250000.75."""
    assert _parse_tr_number("₺1.250.000,75") == 1250000.75


def test_parse_tr_number_empty() -> None:
    """Boş veya None -> None."""
    assert _parse_tr_number("") is None
    assert _parse_tr_number("   ") is None
