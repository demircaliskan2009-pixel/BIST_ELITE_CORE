from __future__ import annotations

from typing import Sequence

from ..base import FailClosedError
from .base import DisclosureProvider, DisclosureRecord


class DeferredDisclosureProvider(DisclosureProvider):
    def __init__(self, provider_name: str, reason: str | None = None) -> None:
        self.provider_name = provider_name
        self.reason = reason or "Disclosure provider wiring is not complete yet."

    def recent(
        self,
        symbols: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[DisclosureRecord]:
        raise FailClosedError(
            f"Disclosure provider {self.provider_name!r} is not ready. {self.reason}"
        )
