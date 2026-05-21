from __future__ import annotations

import math
from dataclasses import dataclass, replace

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.contracts import (
    OrderBookDelta,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicFeedHealth,
    PublicFeedType,
    PublicMarketDataEvent,
    VenueId,
)
from crypto_core.venue.deribit_marketevent_normalizer import (
    DERIBIT_MARKETEVENT_NORMALIZER_ID,
    DeribitMarketEventNormalizationResult,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from crypto_core.venue.registry import (
    VenueRegistryError,
    ensure_instrument_usable_for_downstream,
    ensure_public_feed_usable_for_downstream,
    get_instrument_spec,
)

DERIBIT_PUBLIC_DATA_QUALITY_GATE_ID = "deribit_public_data_quality_gate_v1"

_RAW_PAYLOAD_PREFIX = "deribit-public-book:"
_SNAPSHOT_EVENT_TYPE = "snapshot"
_DELTA_EVENT_TYPES = frozenset({"change", "delta"})
_PRIVATE_OR_EXECUTION_MARKERS = frozenset(
    {
        "account",
        "auth",
        "balance",
        "buy",
        "credential",
        "order_id",
        "paper",
        "position",
        "private",
        "sell",
        "shadow",
        "signature",
        "submit",
        "token",
        "withdraw",
    }
)


@dataclass(frozen=True)
class DeribitPublicDataQualityResult:
    accepted: bool
    public_feed_health: PublicFeedHealth | None
    market_event: PublicMarketDataEvent | None
    order_book_snapshot: OrderBookSnapshot | None
    order_book_delta: OrderBookDelta | None
    rejection_reasons: tuple[str, ...]


def evaluate_deribit_normalized_book_quality(
    normalization_result: object,
    *,
    prior_sequence_id: int | None = None,
) -> DeribitPublicDataQualityResult:
    if not isinstance(normalization_result, DeribitMarketEventNormalizationResult):
        return _rejected(("deribit_public_data_quality:normalization_result_malformed",))
    if normalization_result.accepted is not True or normalization_result.market_event is None:
        return _rejected(
            (
                "deribit_public_data_quality:normalization_not_accepted",
                *normalization_result.rejection_reasons,
            )
        )
    return evaluate_deribit_public_data_quality(
        normalization_result.market_event,
        order_book_snapshot=normalization_result.order_book_snapshot,
        order_book_delta=normalization_result.order_book_delta,
        prior_sequence_id=prior_sequence_id,
    )


def evaluate_deribit_public_data_quality(
    market_event: object,
    *,
    order_book_snapshot: object | None = None,
    order_book_delta: object | None = None,
    prior_sequence_id: int | None = None,
) -> DeribitPublicDataQualityResult:
    reasons: list[str] = []
    spec = _ready_deribit_dialect()
    if spec is None:
        reasons.append("deribit_public_data_quality:dialect_not_ready")

    if not isinstance(market_event, PublicMarketDataEvent):
        return _rejected((*reasons, "deribit_public_data_quality:market_event_malformed"))

    _validate_market_event(market_event, reasons)
    _validate_event_identity(market_event, reasons)
    _validate_event_timing(market_event, spec, reasons)
    _validate_dialect_policy(spec, reasons)

    if order_book_snapshot is not None and order_book_delta is not None:
        reasons.append("deribit_public_data_quality:book_contract_ambiguous")
    elif order_book_snapshot is None and order_book_delta is None:
        reasons.append("deribit_public_data_quality:book_contract_missing")
    elif order_book_snapshot is not None:
        _validate_snapshot_contract(order_book_snapshot, market_event, reasons)
    else:
        _validate_delta_contract(order_book_delta, market_event, prior_sequence_id, reasons)

    health = _public_feed_health(market_event, reasons)
    if health is not None and not reasons:
        try:
            ensure_public_feed_usable_for_downstream(health)
        except VenueRegistryError as exc:
            reasons.extend(str(exc).split(";"))
            health = replace(
                health,
                healthy=False,
                rejection_reasons=tuple(dict.fromkeys((*health.rejection_reasons, *str(exc).split(";")))),
            )

    if reasons:
        if health is not None:
            health = replace(
                health,
                healthy=False,
                stale=health.stale or "deribit_public_data_quality:stale_event" in reasons,
                gap_detected=health.gap_detected or "deribit_public_data_quality:sequence_gap_detected" in reasons,
                resync_required=(
                    health.resync_required
                    or "deribit_public_data_quality:sequence_gap_detected" in reasons
                    or "deribit_public_data_quality:sequence_gap_unresolved" in reasons
                ),
                rejection_reasons=tuple(dict.fromkeys((*health.rejection_reasons, *reasons))),
            )
        return DeribitPublicDataQualityResult(
            accepted=False,
            public_feed_health=health,
            market_event=market_event,
            order_book_snapshot=order_book_snapshot if isinstance(order_book_snapshot, OrderBookSnapshot) else None,
            order_book_delta=order_book_delta if isinstance(order_book_delta, OrderBookDelta) else None,
            rejection_reasons=tuple(dict.fromkeys(reasons)),
        )

    assert health is not None
    return DeribitPublicDataQualityResult(
        accepted=True,
        public_feed_health=health,
        market_event=market_event,
        order_book_snapshot=order_book_snapshot if isinstance(order_book_snapshot, OrderBookSnapshot) else None,
        order_book_delta=order_book_delta if isinstance(order_book_delta, OrderBookDelta) else None,
        rejection_reasons=(),
    )


def _validate_market_event(event: PublicMarketDataEvent, reasons: list[str]) -> None:
    if event.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_public_data_quality:venue_mismatch")
    if event.feed_type is not PublicFeedType.L2_ORDERBOOK:
        reasons.append("deribit_public_data_quality:feed_type_mismatch")
    if event.normalized is not True:
        reasons.append("deribit_public_data_quality:not_normalized")
    if not isinstance(event.event_time_ns, int) or isinstance(event.event_time_ns, bool) or event.event_time_ns <= 0:
        reasons.append("deribit_public_data_quality:timestamp_invalid")
    if (
        not isinstance(event.receive_time_ns, int)
        or isinstance(event.receive_time_ns, bool)
        or event.receive_time_ns <= 0
    ):
        reasons.append("deribit_public_data_quality:timestamp_invalid")
    if (
        isinstance(event.event_time_ns, int)
        and isinstance(event.receive_time_ns, int)
        and not isinstance(event.event_time_ns, bool)
        and not isinstance(event.receive_time_ns, bool)
        and event.receive_time_ns < event.event_time_ns
    ):
        reasons.append("deribit_public_data_quality:received_before_event")
    if not isinstance(event.sequence_id, int) or isinstance(event.sequence_id, bool) or event.sequence_id < 0:
        reasons.append("deribit_public_data_quality:sequence_id_invalid")
    if not isinstance(event.raw_payload_ref, str) or not event.raw_payload_ref.startswith(_RAW_PAYLOAD_PREFIX):
        reasons.append("deribit_public_data_quality:raw_payload_ref_invalid")
    if _contains_private_or_execution_marker(event.raw_payload_ref):
        reasons.append("deribit_public_data_quality:private_or_execution_contamination")


def _validate_event_identity(event: PublicMarketDataEvent, reasons: list[str]) -> None:
    try:
        instrument = ensure_instrument_usable_for_downstream(get_instrument_spec(VenueId.DERIBIT, event.symbol))
    except VenueRegistryError:
        reasons.append("deribit_public_data_quality:instrument_unknown")
        return
    if instrument.canonical_symbol != event.canonical_symbol:
        reasons.append("deribit_public_data_quality:canonical_symbol_mismatch")


def _validate_event_timing(market_event: PublicMarketDataEvent, spec: object, reasons: list[str]) -> None:
    if spec is None:
        return
    receive_lag_ns = market_event.receive_time_ns - market_event.event_time_ns
    if receive_lag_ns > spec.max_receive_lag_ns:
        reasons.append("deribit_public_data_quality:receive_lag_breach")
    if receive_lag_ns > spec.max_staleness_ns:
        reasons.append("deribit_public_data_quality:stale_event")


def _validate_dialect_policy(spec: object, reasons: list[str]) -> None:
    if spec is None:
        return
    if spec.supports_checksum is not False or spec.checksum_model is not FeedChecksumModel.NONE:
        reasons.append("deribit_public_data_quality:checksum_policy_mismatch")
    if spec.sequence_model is not FeedSequenceModel.SNAPSHOT_DELTA_RANGE:
        reasons.append("deribit_public_data_quality:sequence_policy_mismatch")
    if spec.max_gap_tolerance != 0:
        reasons.append("deribit_public_data_quality:gap_policy_not_fail_closed")


def _validate_snapshot_contract(snapshot: object, event: PublicMarketDataEvent, reasons: list[str]) -> None:
    if not isinstance(snapshot, OrderBookSnapshot):
        reasons.append("deribit_public_data_quality:order_book_snapshot_malformed")
        return
    _validate_book_header(snapshot, event, reasons)
    if snapshot.checksum is not None:
        reasons.append("deribit_public_data_quality:checksum_unsupported")
    if _raw_payload_event_type(event.raw_payload_ref) != _SNAPSHOT_EVENT_TYPE:
        reasons.append("deribit_public_data_quality:event_contract_mismatch")
    if snapshot.depth <= 0 or snapshot.depth > min(len(snapshot.bids), len(snapshot.asks)):
        reasons.append("deribit_public_data_quality:snapshot_depth_invalid")
    if not snapshot.bids or not snapshot.asks:
        reasons.append("deribit_public_data_quality:book_side_missing")
    bids_valid = _validate_levels(snapshot.bids, require_positive_quantity=True, reasons=reasons)
    asks_valid = _validate_levels(snapshot.asks, require_positive_quantity=True, reasons=reasons)
    if bids_valid and asks_valid and _best_bid(snapshot.bids) >= _best_ask(snapshot.asks):
        reasons.append("deribit_public_data_quality:book_crossed")


def _validate_delta_contract(
    delta: object,
    event: PublicMarketDataEvent,
    prior_sequence_id: int | None,
    reasons: list[str],
) -> None:
    if not isinstance(delta, OrderBookDelta):
        reasons.append("deribit_public_data_quality:order_book_delta_malformed")
        return
    _validate_book_header(delta, event, reasons)
    if delta.checksum is not None:
        reasons.append("deribit_public_data_quality:checksum_unsupported")
    if _raw_payload_event_type(event.raw_payload_ref) not in _DELTA_EVENT_TYPES:
        reasons.append("deribit_public_data_quality:event_contract_mismatch")
    if not delta.bid_updates and not delta.ask_updates:
        reasons.append("deribit_public_data_quality:book_side_missing")
    bids_valid = _validate_levels(delta.bid_updates, require_positive_quantity=False, reasons=reasons)
    asks_valid = _validate_levels(delta.ask_updates, require_positive_quantity=False, reasons=reasons)
    if delta.first_update_id != delta.prev_update_id + 1:
        reasons.append("deribit_public_data_quality:sequence_range_invalid")
    if delta.final_update_id != event.sequence_id:
        reasons.append("deribit_public_data_quality:sequence_id_mismatch")
    if prior_sequence_id is not None:
        if not isinstance(prior_sequence_id, int) or isinstance(prior_sequence_id, bool) or prior_sequence_id < 0:
            reasons.append("deribit_public_data_quality:prior_sequence_id_invalid")
        elif delta.prev_update_id != prior_sequence_id:
            reasons.append("deribit_public_data_quality:sequence_gap_detected")
        elif delta.first_update_id != prior_sequence_id + 1:
            reasons.append("deribit_public_data_quality:sequence_gap_unresolved")
    if (
        bids_valid
        and asks_valid
        and delta.bid_updates
        and delta.ask_updates
        and _best_bid(delta.bid_updates) >= _best_ask(delta.ask_updates)
    ):
        reasons.append("deribit_public_data_quality:book_crossed")


def _validate_book_header(book: object, event: PublicMarketDataEvent, reasons: list[str]) -> None:
    if getattr(book, "venue_id", None) is not VenueId.DERIBIT:
        reasons.append("deribit_public_data_quality:book_venue_mismatch")
    if getattr(book, "symbol", None) != event.symbol:
        reasons.append("deribit_public_data_quality:book_symbol_mismatch")
    if getattr(book, "canonical_symbol", None) != event.canonical_symbol:
        reasons.append("deribit_public_data_quality:book_canonical_symbol_mismatch")
    if getattr(book, "event_time_ns", None) != event.event_time_ns:
        reasons.append("deribit_public_data_quality:book_event_time_mismatch")
    if getattr(book, "receive_time_ns", None) != event.receive_time_ns:
        reasons.append("deribit_public_data_quality:book_receive_time_mismatch")
    if _contains_private_or_execution_marker(getattr(book, "source", None)):
        reasons.append("deribit_public_data_quality:private_or_execution_contamination")
    if getattr(book, "source", None) != DERIBIT_MARKETEVENT_NORMALIZER_ID:
        reasons.append("deribit_public_data_quality:book_source_mismatch")


def _validate_levels(
    levels: object,
    *,
    require_positive_quantity: bool,
    reasons: list[str],
) -> bool:
    if not isinstance(levels, (tuple, list)):
        reasons.append("deribit_public_data_quality:book_level_malformed")
        return False
    for level in levels:
        if not isinstance(level, OrderBookLevel):
            reasons.append("deribit_public_data_quality:book_level_malformed")
            return False
        if not math.isfinite(level.price) or level.price <= 0.0:
            reasons.append("deribit_public_data_quality:book_level_invalid")
        if not math.isfinite(level.quantity) or level.quantity < 0.0:
            reasons.append("deribit_public_data_quality:book_level_invalid")
        if require_positive_quantity and level.quantity <= 0.0:
            reasons.append("deribit_public_data_quality:book_level_invalid")
    return True


def _public_feed_health(
    market_event: PublicMarketDataEvent,
    reasons: list[str],
) -> PublicFeedHealth | None:
    if (
        not isinstance(market_event.event_time_ns, int)
        or isinstance(market_event.event_time_ns, bool)
        or market_event.event_time_ns <= 0
        or not isinstance(market_event.receive_time_ns, int)
        or isinstance(market_event.receive_time_ns, bool)
        or market_event.receive_time_ns <= 0
    ):
        return None
    unique_reasons = tuple(dict.fromkeys(reasons))
    return PublicFeedHealth(
        venue_id=VenueId.DERIBIT,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        symbol=market_event.symbol,
        healthy=unique_reasons == (),
        stale="deribit_public_data_quality:stale_event" in unique_reasons,
        last_event_time_ns=market_event.event_time_ns,
        last_receive_time_ns=market_event.receive_time_ns,
        gap_detected="deribit_public_data_quality:sequence_gap_detected" in unique_reasons,
        resync_required=(
            "deribit_public_data_quality:sequence_gap_detected" in unique_reasons
            or "deribit_public_data_quality:sequence_gap_unresolved" in unique_reasons
        ),
        rejection_reasons=unique_reasons,
    )


def _ready_deribit_dialect():
    ready = tuple(spec for spec in connector_ready_dialects() if spec.venue_id is VenueId.DERIBIT)
    if len(ready) != 1:
        return None
    return ready[0]


def _best_bid(levels: tuple[OrderBookLevel, ...] | list[OrderBookLevel]) -> float:
    return max(level.price for level in levels)


def _best_ask(levels: tuple[OrderBookLevel, ...] | list[OrderBookLevel]) -> float:
    return min(level.price for level in levels)


def _raw_payload_event_type(raw_payload_ref: str | None) -> str | None:
    if not isinstance(raw_payload_ref, str) or not raw_payload_ref.startswith(_RAW_PAYLOAD_PREFIX):
        return None
    _, _, event_type = raw_payload_ref.rpartition(":")
    return event_type or None


def _contains_private_or_execution_marker(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _PRIVATE_OR_EXECUTION_MARKERS)


def _rejected(reasons: tuple[str, ...] | list[str]) -> DeribitPublicDataQualityResult:
    return DeribitPublicDataQualityResult(
        accepted=False,
        public_feed_health=None,
        market_event=None,
        order_book_snapshot=None,
        order_book_delta=None,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "DERIBIT_PUBLIC_DATA_QUALITY_GATE_ID",
    "DeribitPublicDataQualityResult",
    "evaluate_deribit_normalized_book_quality",
    "evaluate_deribit_public_data_quality",
]
