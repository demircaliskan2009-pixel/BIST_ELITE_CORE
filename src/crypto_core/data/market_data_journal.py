from __future__ import annotations

from dataclasses import dataclass

from crypto_core.venue.contracts import PublicFeedType, PublicMarketDataEvent, VenueId


class PublicMarketDataJournalError(ValueError):
    """Raised when public market-data journal payloads are malformed."""


@dataclass(frozen=True)
class PublicMarketDataJournalEntry:
    entry_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    event_time_ns: int
    receive_time_ns: int
    sequence_id: int
    payload_hash: str
    payload_ref: str | None
    event_kind: str
    normalized: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_entry_shape(self)


@dataclass(frozen=True)
class PublicMarketDataReplayCursor:
    journal_id: str
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    last_sequence_id: int
    last_event_time_ns: int
    entry_count: int
    healthy: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_cursor_shape(self)


@dataclass(frozen=True)
class PublicMarketDataReplayResult:
    applied: bool
    cursor: PublicMarketDataReplayCursor | None
    rejection_reasons: tuple[str, ...]
    gap_detected: bool
    stale_detected: bool
    resync_required: bool

    def __post_init__(self) -> None:
        if not isinstance(self.applied, bool):
            raise PublicMarketDataJournalError("applied must be a boolean")
        if self.cursor is not None and not isinstance(self.cursor, PublicMarketDataReplayCursor):
            raise PublicMarketDataJournalError("cursor must be PublicMarketDataReplayCursor or None")
        _string_tuple(self.rejection_reasons, "rejection_reasons")
        if not isinstance(self.gap_detected, bool):
            raise PublicMarketDataJournalError("gap_detected must be a boolean")
        if not isinstance(self.stale_detected, bool):
            raise PublicMarketDataJournalError("stale_detected must be a boolean")
        if not isinstance(self.resync_required, bool):
            raise PublicMarketDataJournalError("resync_required must be a boolean")


def build_journal_entry_from_public_event(
    event: PublicMarketDataEvent,
    *,
    entry_id: str,
) -> PublicMarketDataJournalEntry:
    if not isinstance(event, PublicMarketDataEvent):
        raise PublicMarketDataJournalError("event must be PublicMarketDataEvent")
    return PublicMarketDataJournalEntry(
        entry_id=_non_empty_string(entry_id, "entry_id"),
        venue_id=event.venue_id,
        symbol=event.symbol,
        canonical_symbol=event.canonical_symbol,
        feed_type=event.feed_type,
        event_time_ns=event.event_time_ns,
        receive_time_ns=event.receive_time_ns,
        sequence_id=event.sequence_id,
        payload_hash=event.payload_hash,
        payload_ref=event.raw_payload_ref,
        event_kind=event.feed_type.value,
        normalized=event.normalized,
        rejection_reasons=(),
    )


def replay_journal_entries(
    entries: tuple[PublicMarketDataJournalEntry, ...],
    *,
    max_staleness_ns: int | None = None,
) -> PublicMarketDataReplayResult:
    if not isinstance(entries, tuple) or not entries:
        return _rejected(("market_data_journal:entries_empty",))
    if max_staleness_ns is not None and (
        not isinstance(max_staleness_ns, int) or isinstance(max_staleness_ns, bool) or max_staleness_ns <= 0
    ):
        return _rejected(("market_data_journal:max_staleness_invalid",))

    reasons: list[str] = []
    entry_ids: set[str] = set()
    sequence_ids: set[int] = set()
    first = entries[0]
    if not isinstance(first, PublicMarketDataJournalEntry):
        return _rejected(("market_data_journal:entry_malformed",))

    previous_sequence_id: int | None = None
    previous_event_time_ns: int | None = None
    stale_detected = False
    for entry in entries:
        if not isinstance(entry, PublicMarketDataJournalEntry):
            reasons.append("market_data_journal:entry_malformed")
            continue
        reasons.extend(_entry_rejection_reasons(entry))
        if entry.venue_id != first.venue_id:
            reasons.append("market_data_journal:venue_mismatch")
        if entry.symbol != first.symbol or entry.canonical_symbol != first.canonical_symbol:
            reasons.append("market_data_journal:symbol_mismatch")
        if entry.feed_type != first.feed_type:
            reasons.append("market_data_journal:feed_type_mismatch")
        if entry.entry_id in entry_ids:
            reasons.append("market_data_journal:duplicate_entry_id")
        entry_ids.add(entry.entry_id)
        if entry.sequence_id in sequence_ids:
            reasons.append("market_data_journal:duplicate_sequence_id")
        sequence_ids.add(entry.sequence_id)
        if previous_sequence_id is not None and entry.sequence_id <= previous_sequence_id:
            reasons.append("market_data_journal:sequence_not_monotonic")
        if previous_event_time_ns is not None and entry.event_time_ns <= previous_event_time_ns:
            reasons.append("market_data_journal:event_time_not_monotonic")
        if max_staleness_ns is not None and entry.receive_time_ns - entry.event_time_ns > max_staleness_ns:
            stale_detected = True
            reasons.append("market_data_journal:stale_entry")
        previous_sequence_id = entry.sequence_id
        previous_event_time_ns = entry.event_time_ns

    normalized_reasons = tuple(dict.fromkeys(reasons))
    if normalized_reasons:
        return _rejected(
            normalized_reasons,
            gap_detected=any(reason in _GAP_REASONS for reason in normalized_reasons),
            stale_detected=stale_detected or "market_data_journal:event_time_not_monotonic" in normalized_reasons,
            resync_required=True,
        )

    last = entries[-1]
    cursor = PublicMarketDataReplayCursor(
        journal_id=_journal_id(entries),
        venue_id=first.venue_id,
        symbol=first.symbol,
        canonical_symbol=first.canonical_symbol,
        last_sequence_id=last.sequence_id,
        last_event_time_ns=last.event_time_ns,
        entry_count=len(entries),
        healthy=True,
        rejection_reasons=(),
    )
    return PublicMarketDataReplayResult(
        applied=True,
        cursor=cursor,
        rejection_reasons=(),
        gap_detected=False,
        stale_detected=False,
        resync_required=False,
    )


def replay_cursor_ready(cursor: PublicMarketDataReplayCursor | None) -> bool:
    if not isinstance(cursor, PublicMarketDataReplayCursor):
        return False
    return cursor.healthy is True and cursor.rejection_reasons == ()


def public_market_data_journal_entry_to_dict(entry: PublicMarketDataJournalEntry) -> dict[str, object]:
    return {
        "entry_id": entry.entry_id,
        "venue_id": entry.venue_id.value,
        "symbol": entry.symbol,
        "canonical_symbol": entry.canonical_symbol,
        "feed_type": entry.feed_type.value,
        "event_time_ns": entry.event_time_ns,
        "receive_time_ns": entry.receive_time_ns,
        "sequence_id": entry.sequence_id,
        "payload_hash": entry.payload_hash,
        "payload_ref": entry.payload_ref,
        "event_kind": entry.event_kind,
        "normalized": entry.normalized,
        "rejection_reasons": list(entry.rejection_reasons),
    }


def public_market_data_journal_entry_from_dict(data: object) -> PublicMarketDataJournalEntry:
    if not isinstance(data, dict):
        raise PublicMarketDataJournalError("journal entry payload must be a mapping")
    return PublicMarketDataJournalEntry(
        entry_id=_non_empty_string(data.get("entry_id"), "entry_id"),
        venue_id=_venue_id(data.get("venue_id")),
        symbol=_non_empty_string(data.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(data.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_feed_type(data.get("feed_type")),
        event_time_ns=_positive_int(data.get("event_time_ns"), "event_time_ns"),
        receive_time_ns=_positive_int(data.get("receive_time_ns"), "receive_time_ns"),
        sequence_id=_non_negative_int(data.get("sequence_id"), "sequence_id"),
        payload_hash=_non_empty_string(data.get("payload_hash"), "payload_hash"),
        payload_ref=_optional_string(data.get("payload_ref"), "payload_ref"),
        event_kind=_non_empty_string(data.get("event_kind"), "event_kind"),
        normalized=_bool(data.get("normalized"), "normalized"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_market_data_replay_cursor_to_dict(cursor: PublicMarketDataReplayCursor) -> dict[str, object]:
    return {
        "journal_id": cursor.journal_id,
        "venue_id": cursor.venue_id.value,
        "symbol": cursor.symbol,
        "canonical_symbol": cursor.canonical_symbol,
        "last_sequence_id": cursor.last_sequence_id,
        "last_event_time_ns": cursor.last_event_time_ns,
        "entry_count": cursor.entry_count,
        "healthy": cursor.healthy,
        "rejection_reasons": list(cursor.rejection_reasons),
    }


def public_market_data_replay_cursor_from_dict(data: object) -> PublicMarketDataReplayCursor:
    if not isinstance(data, dict):
        raise PublicMarketDataJournalError("replay cursor payload must be a mapping")
    return PublicMarketDataReplayCursor(
        journal_id=_non_empty_string(data.get("journal_id"), "journal_id"),
        venue_id=_venue_id(data.get("venue_id")),
        symbol=_non_empty_string(data.get("symbol"), "symbol"),
        canonical_symbol=_non_empty_string(data.get("canonical_symbol"), "canonical_symbol"),
        last_sequence_id=_non_negative_int(data.get("last_sequence_id"), "last_sequence_id"),
        last_event_time_ns=_positive_int(data.get("last_event_time_ns"), "last_event_time_ns"),
        entry_count=_positive_int(data.get("entry_count"), "entry_count"),
        healthy=_bool(data.get("healthy"), "healthy"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons", ()), "rejection_reasons"),
    )


_GAP_REASONS = frozenset(
    {
        "market_data_journal:sequence_not_monotonic",
        "market_data_journal:duplicate_sequence_id",
    }
)


def _entry_rejection_reasons(entry: PublicMarketDataJournalEntry) -> tuple[str, ...]:
    reasons: list[str] = []
    if entry.receive_time_ns < entry.event_time_ns:
        reasons.append("market_data_journal:receive_before_event")
    if not entry.normalized:
        reasons.append("market_data_journal:not_normalized")
    reasons.extend(entry.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def _validate_entry_shape(entry: PublicMarketDataJournalEntry) -> None:
    _non_empty_string(entry.entry_id, "entry_id")
    if not isinstance(entry.venue_id, VenueId):
        raise PublicMarketDataJournalError("venue_id is malformed")
    _non_empty_string(entry.symbol, "symbol")
    _non_empty_string(entry.canonical_symbol, "canonical_symbol")
    if not isinstance(entry.feed_type, PublicFeedType):
        raise PublicMarketDataJournalError("feed_type is malformed")
    _positive_int(entry.event_time_ns, "event_time_ns")
    _positive_int(entry.receive_time_ns, "receive_time_ns")
    if entry.receive_time_ns < entry.event_time_ns:
        raise PublicMarketDataJournalError("receive_time_ns cannot precede event_time_ns")
    _non_negative_int(entry.sequence_id, "sequence_id")
    _non_empty_string(entry.payload_hash, "payload_hash")
    _optional_string(entry.payload_ref, "payload_ref")
    _non_empty_string(entry.event_kind, "event_kind")
    _bool(entry.normalized, "normalized")
    _string_tuple(entry.rejection_reasons, "rejection_reasons")


def _validate_cursor_shape(cursor: PublicMarketDataReplayCursor) -> None:
    _non_empty_string(cursor.journal_id, "journal_id")
    if not isinstance(cursor.venue_id, VenueId):
        raise PublicMarketDataJournalError("venue_id is malformed")
    _non_empty_string(cursor.symbol, "symbol")
    _non_empty_string(cursor.canonical_symbol, "canonical_symbol")
    _non_negative_int(cursor.last_sequence_id, "last_sequence_id")
    _positive_int(cursor.last_event_time_ns, "last_event_time_ns")
    _positive_int(cursor.entry_count, "entry_count")
    _bool(cursor.healthy, "healthy")
    _string_tuple(cursor.rejection_reasons, "rejection_reasons")


def _rejected(
    reasons: tuple[str, ...],
    *,
    gap_detected: bool = False,
    stale_detected: bool = False,
    resync_required: bool = False,
) -> PublicMarketDataReplayResult:
    return PublicMarketDataReplayResult(
        applied=False,
        cursor=None,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        gap_detected=gap_detected,
        stale_detected=stale_detected,
        resync_required=resync_required,
    )


def _journal_id(entries: tuple[PublicMarketDataJournalEntry, ...]) -> str:
    first = entries[0]
    last = entries[-1]
    return (
        f"{first.venue_id.value}:{first.feed_type.value}:"
        f"{first.symbol}:{first.sequence_id}:{last.sequence_id}:{len(entries)}"
    )


def _venue_id(value: object) -> VenueId:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError as exc:
            raise PublicMarketDataJournalError("venue_id is unsupported") from exc
    raise PublicMarketDataJournalError("venue_id is malformed")


def _feed_type(value: object) -> PublicFeedType:
    if isinstance(value, PublicFeedType):
        return value
    if isinstance(value, str):
        try:
            return PublicFeedType(value)
        except ValueError as exc:
            raise PublicMarketDataJournalError("feed_type is unsupported") from exc
    raise PublicMarketDataJournalError("feed_type is malformed")


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicMarketDataJournalError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PublicMarketDataJournalError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PublicMarketDataJournalError(f"{field_name} must be a non-negative integer")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicMarketDataJournalError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise PublicMarketDataJournalError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PublicMarketDataJournalError(f"{field_name} must contain non-empty strings")
    return result


__all__ = [
    "PublicMarketDataJournalEntry",
    "PublicMarketDataJournalError",
    "PublicMarketDataReplayCursor",
    "PublicMarketDataReplayResult",
    "build_journal_entry_from_public_event",
    "public_market_data_journal_entry_from_dict",
    "public_market_data_journal_entry_to_dict",
    "public_market_data_replay_cursor_from_dict",
    "public_market_data_replay_cursor_to_dict",
    "replay_cursor_ready",
    "replay_journal_entries",
]
