"""FAZ112: Market data provider registry — pluggable, external feed integration, static dummy for tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.market_data import resolve_provider
from bist_core.market_data.base import MarketDataProvider
from bist_core.market_data.registry import (
    STATIC_DUMMY_CLOSE_MAP,
    STATIC_DUMMY_SYMBOLS,
    StaticDummyMarketDataProvider,
    get_market_data_provider,
    list_market_data_providers,
    register_market_data_provider,
    static_dummy_factory,
    _clear_registry_for_tests,
)


def test_register_and_resolve_dummy_provider(tmp_path: Path) -> None:
    """Pluggable registry: register and resolve by key."""
    register_market_data_provider("dummy", static_dummy_factory)
    try:
        provider = resolve_provider(name="dummy", snapshot_root=tmp_path)
        assert isinstance(provider, StaticDummyMarketDataProvider)
        assert provider.symbols("2025-01-01") == STATIC_DUMMY_SYMBOLS
        assert provider.close_map("2025-01-01") == STATIC_DUMMY_CLOSE_MAP
        ok, msg = provider.validate("2025-01-01")
        assert ok is True
        assert msg == "ok"
    finally:
        _clear_registry_for_tests()


def test_static_dummy_returns_static_data() -> None:
    """Dummy provider returns static dummy data for test purposes."""
    provider = StaticDummyMarketDataProvider()
    assert provider.symbols("any-day") == ["DUMMY_A", "DUMMY_B"]
    assert provider.close_map("any-day") == {"DUMMY_A": 100.0, "DUMMY_B": 200.0}
    ok, msg = provider.validate("any-day")
    assert ok is True
    assert msg == "ok"


def test_dummy_provider_implements_interface() -> None:
    """Static dummy conforms to MarketDataProvider (common interface)."""
    provider = StaticDummyMarketDataProvider()
    assert isinstance(provider, MarketDataProvider)


def test_unknown_provider_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown market_data provider: unknown_xyz"):
        resolve_provider(name="unknown_xyz", snapshot_root=Path("/tmp"))


def test_register_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        register_market_data_provider("  ", static_dummy_factory)
    with pytest.raises(ValueError, match="cannot be empty"):
        register_market_data_provider("", static_dummy_factory)


def test_get_market_data_provider_normalized() -> None:
    register_market_data_provider("Dummy", static_dummy_factory)
    try:
        assert get_market_data_provider("dummy") is static_dummy_factory
        assert get_market_data_provider("  DUMMY  ") is static_dummy_factory
        assert get_market_data_provider("unknown_xyz") is None
    finally:
        _clear_registry_for_tests()


def test_retrieve_by_key_and_verify_interface() -> None:
    """Retrieval by string key returns a factory that produces a provider implementing MarketDataProvider."""
    register_market_data_provider("dummy", static_dummy_factory)
    try:
        factory = get_market_data_provider("dummy")
        assert factory is not None
        provider = factory(snapshot_root=None)
        assert isinstance(provider, MarketDataProvider)
        assert provider.symbols("2025-01-01") == STATIC_DUMMY_SYMBOLS
    finally:
        _clear_registry_for_tests()


def test_list_market_data_providers() -> None:
    """Pluggable registration is visible via list of keys."""
    _clear_registry_for_tests()
    try:
        assert list_market_data_providers() == []
        register_market_data_provider("alpha", static_dummy_factory)
        register_market_data_provider("beta", static_dummy_factory)
        assert list_market_data_providers() == ["alpha", "beta"]
    finally:
        _clear_registry_for_tests()


def test_local_eod_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """local_eod resolution is unchanged (still requires snapshot_root or env)."""
    monkeypatch.delenv("BIST_CORE_SNAPSHOT_DIR", raising=False)
    with pytest.raises(ValueError, match="local_eod requires snapshot_root"):
        resolve_provider(name="local_eod", snapshot_root=None)
