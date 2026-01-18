from __future__ import annotations

from pathlib import Path

from bist_core.providers.instruments.base import InstrumentsProvider
from bist_core.services import instrumentstore


class OfflineFileInstrumentsProvider(InstrumentsProvider):
    name = "offline_file"

    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path

    def pull(self, day: str, outdir: Path, **kwargs) -> Path:
        records, _ = instrumentstore.parse_instruments(
            self.input_path, source=self.name
        )
        deduped = instrumentstore.dedupe_instruments(records)
        out_path = outdir / "instruments.jsonl"
        instrumentstore.atomic_write_jsonl(out_path, deduped)
        return out_path
