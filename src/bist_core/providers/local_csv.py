
from __future__ import annotations
from pathlib import Path
import csv
from typing import Dict, List

class LocalCSVProvider:
    """
    EOD snapshot.csv dosyasından (symbol, close) okuyan basit sağlayıcı.
    Varsayılan kök: data/eod/snapshots/YYYY-MM-DD/snapshot.csv
    """
    def __init__(self, base: Path | str = Path("data") / "eod" / "snapshots"):
        self.base = Path(base)

    def _file(self, date: str) -> Path:
        p = self.base / date / "snapshot.csv"
        if not p.exists():
            raise FileNotFoundError(f"snapshot not found: {p}")
        return p

    def symbols(self, date: str) -> list[str]:
        path = self._file(date)
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            return [row["symbol"] for row in rdr]

    def close_map(self, date: str) -> dict[str, float]:
        path = self._file(date)
        out: dict[str, float] = {}
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                sym = row["symbol"]
                c = row.get("close")
                out[sym] = float(c) if c not in (None, "") else float("nan")
        return out
