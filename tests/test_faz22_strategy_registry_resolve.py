from __future__ import annotations

import pytest

from bist_core.strategies.registry import resolve_strategy


def test_strategy_registry_resolve() -> None:
    assert resolve_strategy("equal_weight").name == "equal_weight"
    assert resolve_strategy("top_n_by_signal").name == "top_n_by_signal"
    assert resolve_strategy("deny_all").name == "deny_all"
    with pytest.raises(ValueError):
        resolve_strategy("unknown_strategy")
