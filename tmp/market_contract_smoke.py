from bist_core.providers.config import ProviderConfig
from bist_core.providers.factory import build_market_data_provider

for provider_name in ("finnet", "matriks"):
    env = {
        "BIST_MARKET_DATA_PROVIDER": provider_name,
        "BIST_DISCLOSURES_PROVIDER": "none",
        "BIST_DATASTORE_NORMALIZED_CSV": "dummy.csv",
        f"BIST_{provider_name.upper()}_SYMBOL_FILTER": "AKBNK,THYAO",
    }
    cfg = ProviderConfig.from_env(env)
    provider = build_market_data_provider(cfg)
    req = provider.build_eod_request(start_date="2026-01-01", end_date="2026-02-01")
    print(provider_name, req)
