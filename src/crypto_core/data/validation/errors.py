"""Validation error taxonomy.

Fail-closed contract: every validation failure raises ValidationError.
No silent corrections. No auto-repair. No partial acceptance.

PRD reference: §4.2 (sequence validation, CRC32), §4.3 (trade dedup), §4.4 (halt conditions).
"""

from __future__ import annotations

from enum import Enum


class ValidationErrorCode(str, Enum):
    """Taxonomy of all data validation failures.

    Sequence integrity:
      SEQ_GAP          — gap detected in stream sequence numbers
      DUPLICATE_EVENT  — same sequence number or trade_id seen twice
      OUT_OF_ORDER     — event arrived with sequence < last seen

    Temporal:
      STALE_DATA       — last event timestamp exceeds stale threshold (PRD §4.2: >10s)
      CLOCK_DRIFT      — event timestamp deviates excessively from wall clock

    Order book:
      BOOK_CRC_MISMATCH  — CRC32 checksum from exchange does not match local computation
      BOOK_CROSSED       — best_bid >= best_ask after applying update
      BOOK_INCONSISTENCY — book state is logically impossible (negative qty, etc.)
      BOOK_NO_SNAPSHOT   — delta received before initial snapshot was applied

    Field validation:
      MISSING_FIELD    — required field absent or None
      INVALID_PRICE    — price <= 0 (impossible for a real trade/level)
      INVALID_QTY      — qty < 0 (negative quantity is invalid)
      INVALID_SYMBOL   — symbol not in registered active universe
    """

    # Sequence integrity
    SEQ_GAP = "SEQ_GAP"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    OUT_OF_ORDER = "OUT_OF_ORDER"

    # Temporal
    STALE_DATA = "STALE_DATA"
    CLOCK_DRIFT = "CLOCK_DRIFT"

    # Order book
    BOOK_CRC_MISMATCH = "BOOK_CRC_MISMATCH"
    BOOK_CROSSED = "BOOK_CROSSED"
    BOOK_INCONSISTENCY = "BOOK_INCONSISTENCY"
    BOOK_NO_SNAPSHOT = "BOOK_NO_SNAPSHOT"

    # Field validation
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_QTY = "INVALID_QTY"
    INVALID_SYMBOL = "INVALID_SYMBOL"


class ValidationError(Exception):
    """Raised by DataValidator on any validation failure.

    Fail-closed: all failures raise this exception.
    Never silently corrected or swallowed.

    Attributes:
        code:    ValidationErrorCode classifying the failure.
        context: dict of structured evidence for the audit log.
    """

    def __init__(
        self,
        code: ValidationErrorCode,
        message: str,
        context: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.context: dict[str, object] = context or {}
        super().__init__(f"[{code.value}] {message}")

    def __repr__(self) -> str:  # pragma: no cover
        return f"ValidationError(code={self.code}, context={self.context}, msg={self})"
