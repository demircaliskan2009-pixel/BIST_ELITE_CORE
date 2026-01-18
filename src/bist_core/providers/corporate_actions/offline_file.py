from __future__ import annotations

from pathlib import Path

from bist_core.providers.corporate_actions.base import CorporateActionsProvider
from bist_core.services import castore


class OfflineFileCorporateActionsProvider(CorporateActionsProvider):
    name = "offline_file"

    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path

    def pull(self, day: str, outdir: Path, **kwargs) -> Path:
        records, _ = castore.parse_actions(self.input_path)
        deduped = castore.dedupe_actions(records)
        out_path = outdir / "actions.jsonl"
        castore.atomic_write_jsonl(out_path, deduped)
        return out_path
