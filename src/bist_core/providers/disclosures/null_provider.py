from __future__ import annotations

from typing import Sequence

from ..base import FailClosedError
from .base import DisclosureProvider, DisclosureRecord


class NullDisclosureProvider(DisclosureProvider):
    provider_name = "none"

    def recent(
        self,
        symbols: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[DisclosureRecord]:
        raise FailClosedError(
            "Disclosure provider is disabled (provider=none). Refusing to fabricate disclosures."
        )
