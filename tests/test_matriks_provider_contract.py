import pytest

from bist_core.providers.base import FailClosedError
from bist_core.providers.market_data.matriks_provider import MatriksMarketDataProvider


def test_matriks_provider_build_eod_request() -> None:
    provider = MatriksMarketDataProvider(
        api_key="secret-key",
        base_url="https://matriks.example.test/api",
        symbol_filter=["AKBNK"],
    )

    req = provider.build_eod_request(
        start_date="2026-01-01",
        end_date="2026-02-01",
        symbols=["thyao", "akbnk"],
    )

    assert req["provider_name"] == "matriks"
    assert req["ready"] is True
    assert req["base_url"] == "https://matriks.example.test/api"
    assert req["headers"]["X-API-Key"] == "***configured***"
    assert req["params"]["symbols"] == ["AKBNK", "THYAO"]


def test_matriks_provider_fails_closed_without_credentials() -> None:
    provider = MatriksMarketDataProvider(
        api_key=None,
        base_url=None,
        symbol_filter=["AKBNK"],
    )

    with pytest.raises(FailClosedError):
        provider.get_eod_range()
