"""Strategy plugin interface — deterministic signal generation."""

from __future__ import annotations

from typing import Any


class BaseStrategy:
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


__all__ = ["BaseStrategy"]
