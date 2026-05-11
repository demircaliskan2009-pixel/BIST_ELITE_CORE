"""Durable portfolio / position state persistence — Phase 6E.

Atomic JSON snapshot of PositionTracker internal state.
Written on demand (e.g. after each fill applied to the tracker).
Read on startup bootstrap to restore position and PnL state.

Schema v1::

    {
        "schema_version": "1",
        "snapshot_ns": 1234567890,
        "nav_usd": 10000.0,
        "daily_realized_pnl": 50.0,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "exchange": "binance",
                "side": "long",
                "quantity": 0.01,
                "avg_entry_price": 50000.0,
                "mark_price": 50100.0,
                "leverage": 1.0,
                "realized_pnl": 0.0,
                "liquidation_price": null
            }
        ]
    }

Invariants:
  - Fail closed: any missing required field → PortfolioRestoreError.
  - No silent schema coercion.
  - No fake broker reconciliation.
  - Atomic write via temp-file rename (prevents half-written snapshots).
  - Thread safety: NOT guaranteed — single-threaded pipeline use only.

PRD reference: §1.26 Margin, §1.28 Kelly.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"

# Required top-level fields in a portfolio snapshot
_REQUIRED_FIELDS = frozenset({"schema_version", "snapshot_ns", "nav_usd", "daily_realized_pnl", "positions"})
# Required fields for each position entry
_REQUIRED_POSITION_FIELDS = frozenset(
    {"symbol", "exchange", "side", "quantity", "avg_entry_price", "mark_price", "leverage", "realized_pnl"}
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PortfolioRestoreError(RuntimeError):
    """Raised when a persisted portfolio snapshot is malformed.

    Fail-closed: any corruption or missing field → STOP restore.
    """


# ---------------------------------------------------------------------------
# PortfolioStateStore
# ---------------------------------------------------------------------------


class PortfolioStateStore:
    """Atomic JSON snapshot store for PortfolioTracker state.

    Usage::

        store = PortfolioStateStore(path=Path("runtime/portfolio_state.json"))
        store.save(tracker.to_persistence_dict(snapshot_ns=time.time_ns()))

        # On startup:
        raw = store.load()  # returns dict or raises PortfolioRestoreError
        tracker = PositionTracker.restore_from_dict(raw)

    Invariants:
      - save() is atomic: writes to a temp file then renames.
      - load() raises PortfolioRestoreError on any schema violation.
      - Not thread-safe — use from single pipeline thread only.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, snapshot: dict) -> None:
        """Atomically write the portfolio snapshot to disk.

        Args:
            snapshot: dict produced by PositionTracker.to_persistence_dict().

        The write is atomic: data goes to a .tmp file first, then renamed.
        This prevents partial writes from corrupting the snapshot.
        """
        tmp_path = self._path.with_suffix(".tmp")
        content = json.dumps(snapshot, indent=2, default=str)
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(content)
        # Atomic rename — works on the same filesystem
        os.replace(tmp_path, self._path)

    def load(self) -> dict:
        """Load and validate the portfolio snapshot.

        Returns:
            The validated snapshot dict (ready for PositionTracker.restore_from_dict).

        Raises:
            PortfolioRestoreError: if the file does not exist, is malformed,
                                   or fails schema validation (fail-closed).
        """
        if not self._path.exists():
            raise PortfolioRestoreError(f"Portfolio snapshot not found at {self._path} — no prior state to restore")

        try:
            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise PortfolioRestoreError(f"Portfolio snapshot JSON decode error at {self._path}: {exc}") from exc

        _validate_snapshot(raw)
        return raw

    def exists(self) -> bool:
        """True when a snapshot file exists at this store's path."""
        return self._path.exists()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_snapshot(d: object) -> None:
    """Fail-closed schema validation for a portfolio snapshot."""
    if not isinstance(d, dict):
        raise PortfolioRestoreError(f"Portfolio snapshot must be a dict, got {type(d).__name__!r}")

    missing_top = _REQUIRED_FIELDS - set(d)
    if missing_top:
        raise PortfolioRestoreError(f"Portfolio snapshot missing required fields: {sorted(missing_top)!r}")

    version = d.get("schema_version")
    if version != _SCHEMA_VERSION:
        raise PortfolioRestoreError(
            f"Portfolio snapshot has unknown schema_version={version!r} (expected {_SCHEMA_VERSION!r})"
        )

    # Validate positions array
    positions = d.get("positions")
    if not isinstance(positions, list):
        raise PortfolioRestoreError(f"Portfolio snapshot 'positions' must be a list, got {type(positions).__name__!r}")

    for idx, pos in enumerate(positions):
        if not isinstance(pos, dict):
            raise PortfolioRestoreError(
                f"Portfolio snapshot positions[{idx}] must be a dict, got {type(pos).__name__!r}"
            )
        missing_pos = _REQUIRED_POSITION_FIELDS - set(pos)
        if missing_pos:
            raise PortfolioRestoreError(f"Portfolio snapshot positions[{idx}] missing fields: {sorted(missing_pos)!r}")

    # Validate numeric fields
    try:
        float(d["nav_usd"])
        float(d["daily_realized_pnl"])
        int(d["snapshot_ns"])
    except (TypeError, ValueError) as exc:
        raise PortfolioRestoreError(f"Portfolio snapshot contains non-numeric value: {exc}") from exc

    nav = float(d["nav_usd"])
    if nav <= 0.0:
        raise PortfolioRestoreError(f"Portfolio snapshot nav_usd must be positive; got {nav}")
