from __future__ import annotations

from typing import Protocol
from pathlib import Path


class InstrumentsProvider(Protocol):
    def pull(self, day: str, outdir: Path, **kwargs) -> Path:
        """Pull instruments for day into outdir and return JSONL path."""
        raise NotImplementedError
