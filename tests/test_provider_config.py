from pathlib import Path

import pytest

from bist_core.providers.base import ProviderConfigError
from bist_core.providers.config import ProviderConfig


def test_provider_config_from_env_defaults() -> None:
    cfg = ProviderConfig.from_env({})
    assert cfg.market_data_provider == "datastore_file"
    assert cfg.disclosures_provider == "none"


def test_provider_config_requires_csv_for_datastore() -> None:
    cfg = ProviderConfig(
        market_data_provider="datastore_file",
        disclosures_provider="none",
        datastore_normalized_csv=None,
    )
    with pytest.raises(ProviderConfigError):
        cfg.validate()


def test_provider_config_accepts_declared_values(tmp_path: Path) -> None:
    csv_path = tmp_path / "normalized.csv"
    csv_path.write_text("date,symbol,open,high,low,close,volume,turnover_tl\n", encoding="utf-8")

    cfg = ProviderConfig(
        market_data_provider="datastore_file",
        disclosures_provider="kap",
        datastore_normalized_csv=str(csv_path),
    )
    validated = cfg.validate(must_exist=True)
    assert validated.datastore_path() == csv_path.resolve()


def test_provider_config_parses_kap_filters() -> None:
    cfg = ProviderConfig.from_env(
        {
            "BIST_MARKET_DATA_PROVIDER": "datastore_file",
            "BIST_DATASTORE_NORMALIZED_CSV": "dummy.csv",
            "BIST_DISCLOSURES_PROVIDER": "kap",
            "BIST_KAP_COMPANY_FILTER": "akbnk, thyao ,, sise",
            "BIST_KAP_TOPIC_FILTER": "genel, kar payi",
        }
    )
    assert cfg.kap_company_filter == ("AKBNK", "THYAO", "SISE")
    assert cfg.kap_topic_filter == ("GENEL", "KAR PAYI")
