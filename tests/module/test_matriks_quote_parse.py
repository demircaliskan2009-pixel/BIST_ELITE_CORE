"""Matriks JSON price extraction (no network)."""

from __future__ import annotations

import pytest

from bist_core.data.matriks_provider import _extract_price_from_json, _quote_urls


def test_extract_last() -> None:
    assert _extract_price_from_json({"last": 42.5}) == 42.5


def test_extract_price_close() -> None:
    assert _extract_price_from_json({"price": 10.0}) == 10.0
    assert _extract_price_from_json({"close": 9.99}) == 9.99


def test_extract_nested_data_last() -> None:
    assert _extract_price_from_json({"data": {"last": 55.0}}) == 55.0


def test_extract_result_wrapper() -> None:
    assert _extract_price_from_json({"result": {"last": 12.34}}) == 12.34


def test_extract_rejects_zero() -> None:
    assert _extract_price_from_json({"last": 0}) is None


def test_quote_urls_prepends_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATRIKS_QUOTE_BASE_URL", "https://gw.example.com")
    urls = _quote_urls("asels")
    assert urls[0] == "https://gw.example.com/quote/ASELS"


def test_quote_urls_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATRIKS_QUOTE_BASE_URL", "https://api.matriksdata.com")
    urls = _quote_urls("THYAO")
    assert urls.count("https://api.matriksdata.com/quote/THYAO") == 1
