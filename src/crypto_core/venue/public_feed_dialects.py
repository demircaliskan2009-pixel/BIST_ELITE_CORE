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
_DERIBIT_LEGACY_DIALECT_ID = "deribit:l2_orderbook:placeholder"
_DERIBIT_VERIFIED_DIALECT_ID = "deribit:l2_orderbook:book_instrument_interval"
_DIALECT_ALIASES = {
    _DERIBIT_LEGACY_DIALECT_ID: _DERIBIT_VERIFIED_DIALECT_ID,
}


_PUBLIC_FEED_DIALECTS: tuple[PublicFeedDialectSpec, ...] = (
    PublicFeedDialectSpec(
        dialect_id=_DERIBIT_VERIFIED_DIALECT_ID,
        venue_id=VenueId.DERIBIT,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        instrument_type=InstrumentType.INVERSE_PERP,
        verification_status=FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS,
        official_doc_refs=(
            "DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md#proof-ready-technical-rows",
            "DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md#proof_ready_not_approved-15",
            "DERIBIT_POLICY_DECISION_AUDIT_26AM.md#operator-approved-policy-values",
            "DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md#row-classifications",
            "DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md#5-expected-validator-outcome-after-phase-26aw-patch",
        ),
        requires_rest_snapshot=False,
        supports_delta_stream=True,
        supports_checksum=False,
        sequence_model=FeedSequenceModel.SNAPSHOT_DELTA_RANGE,
        checksum_model=FeedChecksumModel.NONE,
        requires_heartbeat=True,
        requires_ping_pong=False,
        supports_resync=True,
        max_gap_tolerance=0,
        max_staleness_ns=2_000_000_000,
        max_receive_lag_ns=1_000_000_000,
        enabled_for_connector=False,
        rejection_reasons=(),
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
    canonical_id = _DIALECT_ALIASES.get(dialect_id, dialect_id)
    for spec in all_public_feed_dialects():
        if spec.dialect_id == canonical_id:
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
