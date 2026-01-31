"""
FAZ58: Local EOD market data provider — reads snapshots from snapshot_root.
Paths: snapshot_root/<day>/snapshot.csv or snapshot_root/<day>.csv.
Deterministic: symbols and close_map keys sorted by symbol.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional


def _snapshot_path(base: Path, day: str) -> Optional[Path]:
    """Return path to snapshot for day (snapshot.csv or day.csv), or None if missing."""
    p1 = base / day / "snapshot.csv"
    if p1.is_file():
        return p1
    p2 = base / (day + ".csv")
    if p2.is_file():
        return p2
    return None


class LocalEODProvider:
    """Read EOD snapshots from snapshot_root. Deterministic symbols and close_map order."""

    def __init__(self, snapshot_root: Path | str) -> None:
        self._root = Path(snapshot_root)
        self._raw_path: Optional[Path] = None
        self._raw_sha256: Optional[str] = None

    def _path(self, day: str) -> Path:
        p = _snapshot_path(self._root, day)
        if p is None:
            raise FileNotFoundError(
                f"No snapshot for day {day}: expected {self._root / day / 'snapshot.csv'} or {self._root / (day + '.csv')}"
            )
        return p

    def symbols(self, day: str) -> List[str]:
        path = self._path(day)
        self._set_raw_path(path)
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            syms = [row.get("symbol", "").strip() for row in rdr if row.get("symbol")]
        return sorted(set(syms))

    def close_map(self, day: str) -> Dict[str, float]:
        path = self._path(day)
        self._set_raw_path(path)
        out: Dict[str, float] = {}
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                sym = (row.get("symbol") or "").strip()
                if not sym:
                    continue
                c = row.get("close")
                try:
                    out[sym] = float(c) if c not in (None, "") else float("nan")
                except (TypeError, ValueError):
                    out[sym] = float("nan")
        return dict(sorted(out.items()))

    def validate(self, day: str) -> tuple[bool, str]:
        p = _snapshot_path(self._root, day)
        if p is None:
            return False, f"no snapshot for day {day}"
        try:
            syms = self.symbols(day)
            if not syms:
                return False, "snapshot empty or no symbol column"
            return True, "ok"
        except Exception as e:
            return False, str(e)

    @property
    def raw_path(self) -> Optional[Path]:
        """Path to last read snapshot (for provenance). Set after symbols/close_map/validate."""
        return self._raw_path

    @property
    def raw_sha256(self) -> Optional[str]:
        """SHA256 of last read snapshot (optional)."""
        return self._raw_sha256

    def _set_raw_path(self, path: Path) -> None:
        self._raw_path = path
        try:
            from bist_core.services import snapshot_integrity
            self._raw_sha256 = snapshot_integrity.compute_sha256(path)
        except Exception:
            self._raw_sha256 = None
