from __future__ import annotations

import datetime as dt

import pytest

from bist_core.services import advisor as advisor_mod


def test_safe_date_accepts_iso_string() -> None:
    got = advisor_mod._safe_date("2026-03-14")
    assert str(got) == "2026-03-14"


def test_safe_date_accepts_datetime_instance() -> None:
    got = advisor_mod._safe_date(dt.datetime(2026, 3, 14, 12, 30, 0))
    assert str(got) == "2026-03-14"


def test_safe_date_rejects_blank_string() -> None:
    with pytest.raises(ValueError):
        advisor_mod._safe_date("")


def test_build_advice_for_symbol_no_longer_raises_nameerror_on_date_coercion() -> None:
    day = "2026-03-14"
    for symbol in ["ASELS", "AKBNK", "GARAN"]:
        try:
            advisor_mod.build_advice_for_symbol(symbol=symbol, date=day)
        except NameError as exc:
            raise AssertionError(f"unexpected NameError: {exc}") from exc
        except Exception:
            pass


def test_public_chat_entrypoint_no_longer_reports_safe_date_nameerror() -> None:
    got = advisor_mod.build_chat_response_for_text(
        "scan top 2",
        "2026-03-14",
        known_symbols=["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"],
        scan_universe=["ASELS", "AKBNK", "GARAN"],
    )
    err_values = list((got.get("advisor_errors") or {}).values())
    assert "NameError" not in err_values
