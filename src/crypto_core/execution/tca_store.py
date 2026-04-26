"""TCA + attribution persistence — Phase 9B.

Append-only JSONL store for TCARecord and TradeAttribution objects.
Follows the same pattern as ExecutionStateStore: one JSON per line,
fail-closed on any corruption, deterministic restore.

Design invariants:
  - Append-only: never mutate or delete existing records.
  - Fail-closed: any malformed line → raise TCAStoreCorruptError.
  - No silent data coercion on read.
  - Thread safety: NOT guaranteed — single-threaded pipeline use only.
  - Path management: caller provides valid path.

PRD reference: §7 Execution Engine, §1.14 TCA.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from crypto_core.execution.attribution import TradeAttribution, attribution_from_dict, attribution_to_dict
from crypto_core.execution.tca import TCARecord, tca_record_from_dict, tca_record_to_dict

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"
_TCA_RECORD_TYPE = "tca_record"
_ATTRIBUTION_RECORD_TYPE = "attribution_record"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TCAStoreCorruptError(RuntimeError):
    """Raised when a persisted TCA/attribution record is malformed.

    Fail-closed: any corruption → STOP, do not silently skip.
    """


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCAStoreStats:
    """Statistics about the TCA store contents."""

    tca_record_count: int
    attribution_record_count: int
    unknown_record_count: int
    total_lines: int


@dataclass
class RestoredTCAState:
    """Result of loading persisted TCA / attribution records.

    tca_records: all restored TCARecord objects.
    attribution_records: all restored TradeAttribution objects.
    stats: counts per record type.
    """

    tca_records: list[TCARecord] = field(default_factory=list)
    attribution_records: list[TradeAttribution] = field(default_factory=list)
    stats: TCAStoreStats = field(
        default_factory=lambda: TCAStoreStats(0, 0, 0, 0),
    )


# ---------------------------------------------------------------------------
# TCAStore
# ---------------------------------------------------------------------------


class TCAStore:
    """Append-only JSONL store for TCA records and attribution records.

    Usage::

        store = TCAStore(path=Path("runtime/tca_log.jsonl"))
        store.append_tca(tca_record)
        store.append_attribution(attribution_record)

        # On startup / audit:
        state = store.load()
        print(f"Loaded {state.stats.tca_record_count} TCA records")

    Invariants:
      - One JSONL record per line.
      - Append-only; never mutates existing lines.
      - load() fails closed on any malformed line.
      - Not thread-safe — use from single pipeline thread only.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append_tca(self, record: TCARecord) -> None:
        """Append a TCA record to the store."""
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "record_type": _TCA_RECORD_TYPE,
            "payload": tca_record_to_dict(record),
        }
        self._append_line(envelope)

    def append_attribution(self, record: TradeAttribution) -> None:
        """Append an attribution record to the store."""
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "record_type": _ATTRIBUTION_RECORD_TYPE,
            "payload": attribution_to_dict(record),
        }
        self._append_line(envelope)

    def load(self) -> RestoredTCAState:
        """Load all persisted records.

        Raises TCAStoreCorruptError on any malformed line (fail-closed).
        Returns empty state if file does not exist.
        """
        if not self._path.exists():
            return RestoredTCAState()

        tca_records: list[TCARecord] = []
        attribution_records: list[TradeAttribution] = []
        unknown_count = 0
        total_lines = 0

        with self._path.open("r", encoding="utf-8") as f:
            for line_num, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                total_lines += 1

                try:
                    d = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TCAStoreCorruptError(f"Line {line_num}: invalid JSON: {exc}") from exc

                record_type = d.get("record_type")
                payload = d.get("payload")

                if payload is None:
                    raise TCAStoreCorruptError(f"Line {line_num}: missing payload field")

                if record_type == _TCA_RECORD_TYPE:
                    try:
                        tca_records.append(tca_record_from_dict(payload))
                    except (ValueError, KeyError, TypeError) as exc:
                        raise TCAStoreCorruptError(f"Line {line_num}: malformed TCA record: {exc}") from exc
                elif record_type == _ATTRIBUTION_RECORD_TYPE:
                    try:
                        attribution_records.append(attribution_from_dict(payload))
                    except (ValueError, KeyError, TypeError) as exc:
                        raise TCAStoreCorruptError(f"Line {line_num}: malformed attribution record: {exc}") from exc
                else:
                    unknown_count += 1
                    logger.warning(
                        "TCAStore line %d: unknown record_type=%r",
                        line_num,
                        record_type,
                    )

        stats = TCAStoreStats(
            tca_record_count=len(tca_records),
            attribution_record_count=len(attribution_records),
            unknown_record_count=unknown_count,
            total_lines=total_lines,
        )

        return RestoredTCAState(
            tca_records=tca_records,
            attribution_records=attribution_records,
            stats=stats,
        )

    def line_count(self) -> int:
        """Return total non-empty lines in the store file."""
        if not self._path.exists():
            return 0
        count = 0
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def _append_line(self, envelope: dict) -> None:
        """Write one JSON line to the JSONL file."""
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, separators=(",", ":")) + "\n")
