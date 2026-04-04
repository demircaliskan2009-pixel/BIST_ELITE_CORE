import pytest

from bist_core.providers.base import FailClosedError
from bist_core.providers.config import ProviderConfig
from bist_core.providers.factory import build_disclosures_provider, build_market_data_provider


def test_none_market_data_provider_fails_closed() -> None:
    cfg = ProviderConfig(
        market_data_provider="none",
        disclosures_provider="none",
        datastore_normalized_csv="dummy.csv",
    )
    provider = build_market_data_provider(cfg)
    with pytest.raises(FailClosedError):
        provider.latest_trading_day()


def test_deferred_market_data_provider_fails_closed() -> None:
    cfg = ProviderConfig(
        market_data_provider="finnet",
        disclosures_provider="none",
        datastore_normalized_csv="dummy.csv",
    )
    provider = build_market_data_provider(cfg)
    with pytest.raises(FailClosedError):
        provider.latest_trading_day()


def test_deferred_disclosure_provider_fails_closed() -> None:
    cfg = ProviderConfig(
        market_data_provider="datastore_file",
        disclosures_provider="kap",
        datastore_normalized_csv="dummy.csv",
    )
    provider = build_disclosures_provider(cfg)
    with pytest.raises(FailClosedError):
        provider.recent(symbols=["AKBNK"], limit=10)
