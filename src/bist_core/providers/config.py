from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .base import ProviderConfigError

MARKET_DATA_PROVIDERS = {"none", "datastore_file", "finnet", "matriks", "bist"}
DISCLOSURE_PROVIDERS = {"none", "kap"}


def _clean(value: str | None, default: str | None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return default if text == "" else text


def _split_csv(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    parts = [x.strip().upper() for x in str(value).split(",")]
    return tuple(x for x in parts if x)


@dataclass(frozen=True)
class ProviderConfig:
    market_data_provider: str = "datastore_file"
    disclosures_provider: str = "none"
    datastore_normalized_csv: str | None = None

    kap_api_key: str | None = None
    kap_base_url: str | None = None
    kap_company_filter: tuple[str, ...] = ()
    kap_topic_filter: tuple[str, ...] = ()

    finnet_api_key: str | None = None
    finnet_base_url: str | None = None
    finnet_symbol_filter: tuple[str, ...] = ()

    matriks_api_key: str | None = None
    matriks_base_url: str | None = None
    matriks_symbol_filter: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ProviderConfig":
        source = os.environ if env is None else env
        return cls(
            market_data_provider=str(_clean(source.get("BIST_MARKET_DATA_PROVIDER"), "datastore_file")).lower(),
            disclosures_provider=str(_clean(source.get("BIST_DISCLOSURES_PROVIDER"), "none")).lower(),
            datastore_normalized_csv=_clean(source.get("BIST_DATASTORE_NORMALIZED_CSV"), None),
            kap_api_key=_clean(source.get("BIST_KAP_API_KEY"), None),
            kap_base_url=_clean(source.get("BIST_KAP_BASE_URL"), None),
            kap_company_filter=_split_csv(source.get("BIST_KAP_COMPANY_FILTER")),
            kap_topic_filter=_split_csv(source.get("BIST_KAP_TOPIC_FILTER")),
            finnet_api_key=_clean(source.get("BIST_FINNET_API_KEY"), None),
            finnet_base_url=_clean(source.get("BIST_FINNET_BASE_URL"), None),
            finnet_symbol_filter=_split_csv(source.get("BIST_FINNET_SYMBOL_FILTER")),
            matriks_api_key=_clean(source.get("BIST_MATRIKS_API_KEY"), None),
            matriks_base_url=_clean(source.get("BIST_MATRIKS_BASE_URL"), None),
            matriks_symbol_filter=_split_csv(source.get("BIST_MATRIKS_SYMBOL_FILTER")),
        )

    def datastore_path(self) -> Path | None:
        if not self.datastore_normalized_csv:
            return None
        return Path(self.datastore_normalized_csv).expanduser().resolve()

    def validate(self, must_exist: bool = False) -> "ProviderConfig":
        if self.market_data_provider not in MARKET_DATA_PROVIDERS:
            raise ProviderConfigError(
                f"Unknown market data provider: {self.market_data_provider!r}. "
                f"Allowed={sorted(MARKET_DATA_PROVIDERS)}"
            )

        if self.disclosures_provider not in DISCLOSURE_PROVIDERS:
            raise ProviderConfigError(
                f"Unknown disclosures provider: {self.disclosures_provider!r}. "
                f"Allowed={sorted(DISCLOSURE_PROVIDERS)}"
            )

        if self.market_data_provider == "datastore_file":
            if not self.datastore_normalized_csv:
                raise ProviderConfigError(
                    "BIST_DATASTORE_NORMALIZED_CSV is required when "
                    "BIST_MARKET_DATA_PROVIDER=datastore_file"
                )
            if must_exist and not self.datastore_path().exists():
                raise ProviderConfigError(
                    f"Configured datastore csv does not exist: {self.datastore_path()}"
                )

        return self
