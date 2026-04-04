"""FAZ405: KAP empty cache no crash — empty dir returns empty/error, no exception."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.providers.events.kap_html import KapHtmlEventsProvider


def test_faz405_kap_empty_cache_no_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty cache dir -> no exception; returns CacheMiss marker."""
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")
    assert not any(tmp_path.iterdir()), "tmp_path should be empty"
    provider = KapHtmlEventsProvider(raw_dir=tmp_path, cache_only=True)
    result = provider.fetch_events_for_day("2099-01-01")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].get("error_marker") == "ProviderError:CacheMiss"


def test_faz405_kap_empty_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty cache dir -> deterministic; same day same result."""
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")
    provider = KapHtmlEventsProvider(raw_dir=tmp_path, cache_only=True)
    r1 = provider.fetch_events_for_day("2099-01-02")
    r2 = provider.fetch_events_for_day("2099-01-02")
    assert r1 == r2
    assert r1[0]["error_marker"] == "ProviderError:CacheMiss"
