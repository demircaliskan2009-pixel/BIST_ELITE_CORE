"""FAZ109: Network kill-switch — BIST_CORE_ALLOW_NETWORK default false; vendor_api and kap_html guarded."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bist_core.providers.events.kap_html import KapHtmlEventsProvider
from bist_core.providers.vendor_api import VendorAPIConfig, VendorAPIProvider


def test_faz109_vendor_api_raises_when_network_disabled() -> None:
    """With env cleared, VendorAPIProvider.symbols(day) must raise; session.get must not be called (counter==0)."""
    get_counter = 0

    class FakeSession:
        def get(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal get_counter
            get_counter += 1
            return MagicMock(raise_for_status=MagicMock(), json=lambda: [])

    env_allow = os.environ.pop("BIST_CORE_ALLOW_NETWORK", None)
    try:
        get_counter = 0
        provider = VendorAPIProvider(
            cfg=VendorAPIConfig(eod_endpoint="http://fake", kap_endpoint=None, api_key=None),
            session=FakeSession(),
        )
        with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
            provider.symbols("2099-01-01")
        assert get_counter == 0
    finally:
        if env_allow is not None:
            os.environ["BIST_CORE_ALLOW_NETWORK"] = env_allow


def test_faz109_kap_html_raises_on_cache_miss_when_network_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With env cleared and empty cache, fetch_events_for_day must raise; urlopen must not be called."""
    import urllib.request

    urlopen_called = False

    def fail_if_urlopen(*args: Any, **kwargs: Any) -> None:
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen must not be called")

    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_urlopen)
    provider = KapHtmlEventsProvider(raw_dir=tmp_path, cache_only=False)
    with pytest.raises(RuntimeError, match="KAP_CACHE_MISS_NETWORK_DISABLED"):
        provider.fetch_events_for_day("2099-01-01")
    assert not urlopen_called
