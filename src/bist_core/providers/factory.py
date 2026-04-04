from __future__ import annotations

from .config import ProviderConfig
from .disclosures.kap_provider import KapDisclosureProvider
from .disclosures.null_provider import NullDisclosureProvider
from .market_data.datastore_file_provider import DatastoreFileMarketDataProvider
from .market_data.finnet_provider import FinnetMarketDataProvider
from .market_data.matriks_provider import MatriksMarketDataProvider
from .market_data.null_provider import NullMarketDataProvider


def build_market_data_provider(config: ProviderConfig):
    config.validate(must_exist=False)

    if config.market_data_provider == "none":
        return NullMarketDataProvider()

    if config.market_data_provider == "datastore_file":
        return DatastoreFileMarketDataProvider(config.datastore_path())

    if config.market_data_provider == "finnet":
        return FinnetMarketDataProvider(
            api_key=config.finnet_api_key,
            base_url=config.finnet_base_url,
            symbol_filter=list(config.finnet_symbol_filter),
        )

    if config.market_data_provider == "matriks":
        return MatriksMarketDataProvider(
            api_key=config.matriks_api_key,
            base_url=config.matriks_base_url,
            symbol_filter=list(config.matriks_symbol_filter),
        )

    return NullMarketDataProvider()


def build_disclosures_provider(config: ProviderConfig):
    config.validate(must_exist=False)

    if config.disclosures_provider == "none":
        return NullDisclosureProvider()

    if config.disclosures_provider == "kap":
        return KapDisclosureProvider(
            api_key=config.kap_api_key,
            base_url=config.kap_base_url,
            company_filter=list(config.kap_company_filter),
            topic_filter=list(config.kap_topic_filter),
        )

    return NullDisclosureProvider()
