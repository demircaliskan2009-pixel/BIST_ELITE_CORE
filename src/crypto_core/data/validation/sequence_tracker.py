"""Per-stream sequence number tracker.

Stateful tracker that enforces monotonically increasing, gap-free sequences.
One tracker instance is shared across all streams via stream_key namespacing.

Determinism: all state is (stream_key → last_seen_sequence_no).
Same event sequence → identical state transitions.

PRD reference: §4.2 (sequence validation), §4.3 (trade gap detection).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from crypto_core.data.validation.errors import ValidationError, ValidationErrorCode


@dataclass
class SequenceTracker:
    """Tracks per-stream sequence numbers and enforces gap-free ordering.

    Stream keys are namespaced strings in the form:
      "{exchange}:{symbol}:{stream_type}"
      e.g. "binance:BTCUSDT:trade"

    Invariants enforced:
    - No gaps (sequence_no must equal last + 1)
    - No duplicates (sequence_no must not equal last)
    - No out-of-order (sequence_no must not be < last)

    All violations raise ValidationError — no silent acceptance.
    """

    _last: Dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def advance(self, stream_key: str, sequence_no: int) -> None:
        """Record the next sequence number for the stream.

        First call for a stream_key initialises the tracker (no gap check on first event).

        Raises:
            ValidationError(DUPLICATE_EVENT)  — sequence_no == last seen
            ValidationError(OUT_OF_ORDER)     — sequence_no < last seen
            ValidationError(SEQ_GAP)          — sequence_no > last seen + 1
        """
        if stream_key not in self._last:
            self._last[stream_key] = sequence_no
            return

        last = self._last[stream_key]

        if sequence_no == last:
            raise ValidationError(
                ValidationErrorCode.DUPLICATE_EVENT,
                f"Duplicate sequence {sequence_no} on stream '{stream_key}'",
                {"stream_key": stream_key, "sequence_no": sequence_no, "last": last},
            )

        if sequence_no < last:
            raise ValidationError(
                ValidationErrorCode.OUT_OF_ORDER,
                f"Out-of-order sequence {sequence_no} < last {last} on stream '{stream_key}'",
                {"stream_key": stream_key, "sequence_no": sequence_no, "last": last},
            )

        if sequence_no > last + 1:
            raise ValidationError(
                ValidationErrorCode.SEQ_GAP,
                f"Sequence gap on stream '{stream_key}': expected {last + 1}, got {sequence_no}",
                {
                    "stream_key": stream_key,
                    "expected": last + 1,
                    "actual": sequence_no,
                    "gap_size": sequence_no - last - 1,
                },
            )

        self._last[stream_key] = sequence_no

    def reset(self, stream_key: str) -> None:
        """Reset tracker for a stream.

        Called on reconnect / re-snapshot so the first post-recovery event
        is accepted without a gap check.
        """
        self._last.pop(stream_key, None)

    def last_seen(self, stream_key: str) -> Optional[int]:
        """Returns last accepted sequence number, or None if stream is unknown."""
        return self._last.get(stream_key)

    def known_streams(self) -> frozenset:
        """Returns set of all currently tracked stream keys."""
        return frozenset(self._last.keys())
