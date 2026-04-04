import pytest

from bist_core.providers.base import FailClosedError
from bist_core.providers.disclosures.kap_provider import KapDisclosureProvider


def test_kap_provider_build_recent_request() -> None:
    provider = KapDisclosureProvider(
        api_key="secret-key",
        base_url="https://kap.example.test/api",
        company_filter=["AKBNK"],
        topic_filter=["GENEL"],
    )

    req = provider.build_recent_request(symbols=["thyao", "akbnk"], limit=500)

    assert req["provider_name"] == "kap"
    assert req["ready"] is True
    assert req["base_url"] == "https://kap.example.test/api"
    assert req["headers"]["X-API-Key"] == "***configured***"
    assert req["params"]["limit"] == 250
    assert req["params"]["symbols"] == ["AKBNK", "THYAO"]
    assert req["params"]["topics"] == ["GENEL"]


def test_kap_provider_recent_fails_closed_without_credentials() -> None:
    provider = KapDisclosureProvider(
        api_key=None,
        base_url=None,
        company_filter=["AKBNK"],
        topic_filter=["GENEL"],
    )

    with pytest.raises(FailClosedError):
        provider.recent(limit=1)
