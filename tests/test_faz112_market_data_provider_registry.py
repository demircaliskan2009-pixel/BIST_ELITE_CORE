"""FAZ112: Market data provider registry — register custom vendors without touching core."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from bist_core.market_data import resolve_provider
from bist_core.market_data.base import MarketDataProvider
from bist_core.market_data.registry import (
    get_market_data_provider,
    register_market_data_provider,
    _clear_registry_for_tests,
)


class DummyMarketDataProvider:
    """Minimal MarketDataProvider for tests."""

    def symbols(self, day: str) -> List[str]:
        return []

    def close_map(self, day: str) -> Dict[str, float]:
        return {}

    def validate(self, day: str) -> tuple[bool, str]:
        return (True, "ok")


def _dummy_factory(
    *,
    snapshot_root: Optional[Path] = None,
    **kwargs: Any,
) -> MarketDataProvider:
    return DummyMarketDataProvider()


def test_register_and_resolve_dummy_provider(tmp_path: Path) -> None:
    register_market_data_provider("dummy", _dummy_factory)
    try:
        provider = resolve_provider(name="dummy", snapshot_root=tmp_path)
        assert isinstance(provider, DummyMarketDataProvider)
        assert provider.symbols("2025-01-01") == []
        assert provider.close_map("2025-01-01") == {}
        ok, msg = provider.validate("2025-01-01")
        assert ok is True
        assert msg == "ok"
    finally:
        _clear_registry_for_tests()


def test_unknown_provider_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown market_data provider: unknown_xyz"):
        resolve_provider(name="unknown_xyz", snapshot_root=Path("/tmp"))


def test_register_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        register_market_data_provider("  ", _dummy_factory)
    with pytest.raises(ValueError, match="cannot be empty"):
        register_market_data_provider("", _dummy_factory)


def test_get_market_data_provider_normalized() -> None:
    register_market_data_provider("Dummy", _dummy_factory)
    try:
        assert get_market_data_provider("dummy") is _dummy_factory
        assert get_market_data_provider("  DUMMY  ") is _dummy_factory
        assert get_market_data_provider("unknown_xyz") is None
    finally:
        _clear_registry_for_tests()


def test_local_eod_unchanged() -> None:
    """local_eod resolution is unchanged (still requires snapshot_root or env)."""
    with pytest.raises(ValueError, match="local_eod requires snapshot_root"):
        resolve_provider(name="local_eod", snapshot_root=None)
