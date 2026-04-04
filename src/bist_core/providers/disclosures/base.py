from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DisclosureRecord:
    provider_name: str
    disclosure_id: str
    symbol: str | None
    title: str
    published_at: str
    url: str | None = None
    category: str | None = None


class DisclosureProvider(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    def recent(
        self,
        symbols: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[DisclosureRecord]:
        raise NotImplementedError
