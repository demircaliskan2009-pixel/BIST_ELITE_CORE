from __future__ import annotations

from pathlib import Path
from typing import Protocol


class InstrumentsProvider(Protocol):
    def pull(self, day: str, outdir: Path, **kwargs) -> Path:
        """Pull instruments for day into outdir and return JSONL path."""
        raise NotImplementedError
