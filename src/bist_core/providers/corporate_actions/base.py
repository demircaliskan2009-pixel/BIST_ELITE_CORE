from __future__ import annotations

from pathlib import Path
from typing import Protocol


class CorporateActionsProvider(Protocol):
    def pull(self, day: str, outdir: Path, **kwargs) -> Path:
        """Pull corporate actions into outdir and return JSONL path."""
        raise NotImplementedError
