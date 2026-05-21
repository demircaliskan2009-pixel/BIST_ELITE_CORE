from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.contracts import (
    OrderBookDelta,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicFeedType,
    PublicMarketDataEvent,
    VenueContractError,
    VenueId,
)
from crypto_core.venue.deribit_public_feed_adapter import (
    DERIBIT_PUBLIC_BOOK_CHANNEL,
    DERIBIT_PUBLIC_BOOK_DIALECT_ID,
    DeribitPublicBookObservation,
    DeribitPublicFeedParseResult,
    deribit_public_book_observation_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from crypto_core.venue.registry import VenueRegistryError, get_instrument_spec

DERIBIT_MARKETEVENT_NORMALIZER_ID = "deribit_public_book_marketevent_normalizer_v1"

_SUPPORTED_EVENT_TYPES = frozenset({"snapshot", "change", "delta", "unspecified"})


@dataclass(frozen=True)
class DeribitMarketEventNormalizationResult:
    accepted: bool
    market_event: PublicMarketDataEvent | None
    order_book_snapshot: OrderBookSnapshot | None
    order_book_delta: OrderBookDelta | None
    rejection_reasons: tuple[str, ...]


def normalize_deribit_public_book_parse_result(
    parse_result: DeribitPublicFeedParseResult,
    *,
    prior_change_id: int | None = None,
) -> DeribitMarketEventNormalizationResult:
    if not isinstance(parse_result, DeribitPublicFeedParseResult):
        return _rejected(("deribit_marketevent:parse_result_malformed",))
    if parse_result.accepted is not True or parse_result.observation is None:
        return _rejected(("deribit_marketevent:pre_normalization_not_accepted", *parse_result.rejection_reasons))
    return normalize_deribit_public_book_observation(parse_result.observation, prior_change_id=prior_change_id)


def normalize_deribit_public_book_observation(
    observation: DeribitPublicBookObservation,
    *,
    prior_change_id: int | None = None,
) -> DeribitMarketEventNormalizationResult:
    reasons = list(_observation_rejection_reasons(observation, prior_change_id=prior_change_id))
    if reasons:
        return _rejected(reasons)

    assert isinstance(observation, DeribitPublicBookObservation)
    instrument = get_instrument_spec(VenueId.DERIBIT, observation.instrument_name)
    event = PublicMarketDataEvent(
        venue_id=VenueId.DERIBIT,
        symbol=instrument.symbol,
        canonical_symbol=instrument.canonical_symbol,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        event_time_ns=observation.event_time_ns,
        receive_time_ns=observation.received_at_ns,
        sequence_id=observation.change_id,
        payload_hash=_observation_hash(observation),
        raw_payload_ref=_raw_payload_ref(observation),
        normalized=True,
    )

    book_result = _book_contract_for_observation(observation, instrument.canonical_symbol)
    if book_result.rejection_reasons:
        return _rejected(book_result.rejection_reasons)

    return DeribitMarketEventNormalizationResult(
        accepted=True,
        market_event=event,
        order_book_snapshot=book_result.snapshot,
        order_book_delta=book_result.delta,
        rejection_reasons=(),
    )


@dataclass(frozen=True)
class _BookContractResult:
    snapshot: OrderBookSnapshot | None
    delta: OrderBookDelta | None
    rejection_reasons: tuple[str, ...]


def _observation_rejection_reasons(
    observation: object,
    *,
    prior_change_id: int | None,
) -> tuple[str, ...]:
    if not isinstance(observation, DeribitPublicBookObservation):
        return ("deribit_marketevent:observation_malformed",)

    reasons: list[str] = []
    spec = _ready_deribit_dialect()
    if spec is None:
        reasons.append("deribit_marketevent:dialect_not_ready")
    elif spec.dialect_id != observation.dialect_id:
        reasons.append("deribit_marketevent:dialect_mismatch")

    if observation.adapter_id == "":
        reasons.append("deribit_marketevent:adapter_missing")
    if observation.venue_id is not VenueId.DERIBIT:
        reasons.append("deribit_marketevent:venue_mismatch")
    if observation.feed_type is not PublicFeedType.L2_ORDERBOOK:
        reasons.append("deribit_marketevent:feed_type_mismatch")
    if observation.channel != DERIBIT_PUBLIC_BOOK_CHANNEL:
        reasons.append("deribit_marketevent:channel_mismatch")
    if not _non_empty(observation.instrument_name):
        reasons.append("deribit_marketevent:instrument_missing")
    else:
        try:
            get_instrument_spec(VenueId.DERIBIT, observation.instrument_name)
        except VenueRegistryError:
            reasons.append("deribit_marketevent:instrument_unknown")
    if observation.event_type not in _SUPPORTED_EVENT_TYPES:
        reasons.append("deribit_marketevent:event_type_unsupported")
    if not _positive_int(observation.event_time_ns) or not _positive_int(observation.received_at_ns):
        reasons.append("deribit_marketevent:timestamp_invalid")
    elif observation.received_at_ns < observation.event_time_ns:
        reasons.append("deribit_marketevent:received_before_event")
    if not _non_negative_int(observation.change_id):
        reasons.append("deribit_marketevent:change_id_invalid")
    if observation.prev_change_id is not None and not _non_negative_int(observation.prev_change_id):
        reasons.append("deribit_marketevent:prev_change_id_invalid")
    if not _non_negative_int(observation.receive_lag_ns):
        reasons.append("deribit_marketevent:receive_lag_invalid")
    elif _positive_int(observation.event_time_ns) and _positive_int(observation.received_at_ns):
        computed_lag_ns = observation.received_at_ns - observation.event_time_ns
        if observation.receive_lag_ns != computed_lag_ns:
            reasons.append("deribit_marketevent:receive_lag_mismatch")
        if spec is not None:
            if computed_lag_ns > spec.max_receive_lag_ns:
                reasons.append("deribit_marketevent:receive_lag_breach")
            if computed_lag_ns > spec.max_staleness_ns:
                reasons.append("deribit_marketevent:stale_event")
    if prior_change_id is not None:
        if not _non_negative_int(prior_change_id):
            reasons.append("deribit_marketevent:prior_change_id_invalid")
        elif observation.prev_change_id is None:
            reasons.append("deribit_marketevent:sequence_gap_unresolved")
        elif observation.prev_change_id != prior_change_id:
            reasons.append("deribit_marketevent:sequence_gap_detected")
    if spec is not None:
        if spec.supports_checksum is not False or spec.checksum_model is not FeedChecksumModel.NONE:
            reasons.append("deribit_marketevent:checksum_policy_mismatch")
        if spec.sequence_model is not FeedSequenceModel.SNAPSHOT_DELTA_RANGE:
            reasons.append("deribit_marketevent:sequence_policy_mismatch")
        if spec.max_gap_tolerance != 0:
            reasons.append("deribit_marketevent:gap_policy_not_fail_closed")
    if not observation.bids or not observation.asks:
        reasons.append("deribit_marketevent:book_side_missing")
    if any(level.price <= 0.0 or level.amount < 0.0 for level in observation.bids + observation.asks):
        reasons.append("deribit_marketevent:book_level_malformed")
    if (
        observation.bids
        and observation.asks
        and max(level.price for level in observation.bids) >= min(level.price for level in observation.asks)
    ):
        reasons.append("deribit_marketevent:book_crossed")
    if observation.normalized is not False:
        reasons.append("deribit_marketevent:already_normalized")
    return tuple(dict.fromkeys(reasons))


def _book_contract_for_observation(
    observation: DeribitPublicBookObservation,
    canonical_symbol: str,
) -> _BookContractResult:
    try:
        levels_bids = tuple(OrderBookLevel(price=level.price, quantity=level.amount) for level in observation.bids)
        levels_asks = tuple(OrderBookLevel(price=level.price, quantity=level.amount) for level in observation.asks)
        if observation.event_type == "snapshot":
            return _BookContractResult(
                snapshot=OrderBookSnapshot(
                    venue_id=VenueId.DERIBIT,
                    symbol=observation.instrument_name,
                    canonical_symbol=canonical_symbol,
                    event_time_ns=observation.event_time_ns,
                    receive_time_ns=observation.received_at_ns,
                    sequence_id=observation.change_id,
                    bids=levels_bids,
                    asks=levels_asks,
                    checksum=None,
                    depth=min(len(levels_bids), len(levels_asks)),
                    source=DERIBIT_MARKETEVENT_NORMALIZER_ID,
                ),
                delta=None,
                rejection_reasons=(),
            )
        if observation.event_type in {"change", "delta"}:
            if observation.prev_change_id is None:
                return _BookContractResult(
                    snapshot=None,
                    delta=None,
                    rejection_reasons=("deribit_marketevent:sequence_gap_unresolved",),
                )
            return _BookContractResult(
                snapshot=None,
                delta=OrderBookDelta(
                    venue_id=VenueId.DERIBIT,
                    symbol=observation.instrument_name,
                    canonical_symbol=canonical_symbol,
                    event_time_ns=observation.event_time_ns,
                    receive_time_ns=observation.received_at_ns,
                    first_update_id=observation.prev_change_id + 1,
                    final_update_id=observation.change_id,
                    prev_update_id=observation.prev_change_id,
                    bid_updates=levels_bids,
                    ask_updates=levels_asks,
                    checksum=None,
                    source=DERIBIT_MARKETEVENT_NORMALIZER_ID,
                ),
                rejection_reasons=(),
            )
    except VenueContractError:
        return _BookContractResult(
            snapshot=None,
            delta=None,
            rejection_reasons=("deribit_marketevent:book_contract_invalid",),
        )
    return _BookContractResult(snapshot=None, delta=None, rejection_reasons=())


def _ready_deribit_dialect():
    ready = tuple(spec for spec in connector_ready_dialects() if spec.dialect_id == DERIBIT_PUBLIC_BOOK_DIALECT_ID)
    if len(ready) != 1:
        return None
    return ready[0]


def _observation_hash(observation: DeribitPublicBookObservation) -> str:
    payload = json.dumps(
        deribit_public_book_observation_to_dict(observation),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _raw_payload_ref(observation: DeribitPublicBookObservation) -> str:
    return (
        f"deribit-public-book:{observation.instrument_name}:"
        f"{observation.change_id}:{observation.event_time_ns}:{observation.event_type}"
    )


def _rejected(reasons: tuple[str, ...] | list[str]) -> DeribitMarketEventNormalizationResult:
    return DeribitMarketEventNormalizationResult(
        accepted=False,
        market_event=None,
        order_book_snapshot=None,
        order_book_delta=None,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = [
    "DERIBIT_MARKETEVENT_NORMALIZER_ID",
    "DeribitMarketEventNormalizationResult",
    "normalize_deribit_public_book_observation",
    "normalize_deribit_public_book_parse_result",
]
