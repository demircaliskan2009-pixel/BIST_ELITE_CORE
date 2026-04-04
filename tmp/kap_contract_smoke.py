from bist_core.providers.config import ProviderConfig
from bist_core.providers.factory import build_disclosures_provider

env = {
    "BIST_MARKET_DATA_PROVIDER": "datastore_file",
    "BIST_DATASTORE_NORMALIZED_CSV": "dummy.csv",
    "BIST_DISCLOSURES_PROVIDER": "kap",
    "BIST_KAP_COMPANY_FILTER": "AKBNK,THYAO",
    "BIST_KAP_TOPIC_FILTER": "GENEL,KAR PAYI",
}
cfg = ProviderConfig.from_env(env)
provider = build_disclosures_provider(cfg)
req = provider.build_recent_request(limit=25)
print(req)
