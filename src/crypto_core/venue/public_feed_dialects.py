from __future__ import annotations

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
    public_feed_dialect_connector_ready,
)
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId


class VenuePublicFeedDialectRegistryError(ValueError):
    """Raised when a static public-feed dialect lookup fails closed."""


_UNVERIFIED_REASON = ("public_feed_dialect:unverified",)


_PUBLIC_FEED_DIALECTS: tuple[PublicFeedDialectSpec, ...] = (
    PublicFeedDialectSpec(
        dialect_id="deribit:l2_orderbook:placeholder",
        venue_id=VenueId.DERIBIT,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.INVERSE_PERP,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
    PublicFeedDialectSpec(
        dialect_id="binance_usdm:l2_orderbook:placeholder",
        venue_id=VenueId.BINANCE_USDM,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.USDT_PERP,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
    PublicFeedDialectSpec(
        dialect_id="bybit_usdt_perp:l2_orderbook:placeholder",
        venue_id=VenueId.BYBIT_USDT_PERP,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.USDT_PERP,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
    PublicFeedDialectSpec(
        dialect_id="okx_swap:l2_orderbook:placeholder",
        venue_id=VenueId.OKX_SWAP,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.USDT_PERP,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
    PublicFeedDialectSpec(
        dialect_id="kraken_futures:l2_orderbook:placeholder",
        venue_id=VenueId.KRAKEN_FUTURES,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.USDT_PERP,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
    PublicFeedDialectSpec(
        dialect_id="coinbase_derivatives:l2_orderbook:placeholder",
        venue_id=VenueId.COINBASE_DERIVATIVES,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.DATED_FUTURES,
        verification_status=FeedDialectVerificationStatus.UNVERIFIED,
        official_doc_refs=(),
        requires_rest_snapshot=False,
        supports_delta_stream=False,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.UNKNOWN,
        checksum_model=FeedChecksumModel.UNKNOWN,
        requires_heartbeat=False,
        requires_ping_pong=False,
        supports_resync=False,
        max_gap_tolerance=0,
        max_staleness_ns=1,
        max_receive_lag_ns=1,
        enabled_for_connector=False,
        rejection_reasons=_UNVERIFIED_REASON,
    ),
)


def all_public_feed_dialects() -> tuple[PublicFeedDialectSpec, ...]:
    return tuple(sorted(_PUBLIC_FEED_DIALECTS, key=lambda spec: spec.dialect_id))


def get_public_feed_dialect(dialect_id: str) -> PublicFeedDialectSpec:
    if not isinstance(dialect_id, str) or not dialect_id:
        raise VenuePublicFeedDialectRegistryError("dialect_id must be non-empty")
    for spec in all_public_feed_dialects():
        if spec.dialect_id == dialect_id:
            return spec
    raise VenuePublicFeedDialectRegistryError(f"unknown public feed dialect: {dialect_id}")


def dialects_for_venue(venue_id: VenueId | str) -> tuple[PublicFeedDialectSpec, ...]:
    venue = _coerce_venue_id(venue_id)
    if venue is None:
        return ()
    return tuple(spec for spec in all_public_feed_dialects() if spec.venue_id is venue)


def connector_ready_dialects() -> tuple[PublicFeedDialectSpec, ...]:
    return tuple(spec for spec in all_public_feed_dialects() if public_feed_dialect_connector_ready(spec))


def _coerce_venue_id(value: VenueId | str) -> VenueId | None:
    if isinstance(value, VenueId):
        return value
    if isinstance(value, str):
        try:
            return VenueId(value)
        except ValueError:
            return None
    return None


__all__ = [
    "VenuePublicFeedDialectRegistryError",
    "all_public_feed_dialects",
    "connector_ready_dialects",
    "dialects_for_venue",
    "get_public_feed_dialect",
]
