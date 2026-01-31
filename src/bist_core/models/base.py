"""
FAZ62: Model plugin interface. predict(features) -> scores.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class ModelPlugin(Protocol):
    """Plugin interface: predict(features) -> scores (same order as features)."""

    def predict(self, features: List[Dict[str, Any]]) -> List[float]:
        """
        Return one score per feature row; order must match features.
        features: list of dicts (e.g. [{"symbol": "A", "close": 10.0}, ...]).
        """
        ...
