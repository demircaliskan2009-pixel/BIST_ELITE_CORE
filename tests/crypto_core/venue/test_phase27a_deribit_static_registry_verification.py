"""Phase 27A Deribit static registry verification tests."""

from __future__ import annotations

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    public_feed_dialect_rejection_reasons,
)
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import (
    connector_ready_dialects,
    dialects_for_venue,
    get_public_feed_dialect,
)


def _deribit_spec():
    specs = dialects_for_venue(VenueId.DERIBIT)
    assert len(specs) == 1
    return specs[0]


def test_phase27a_evidence_review_complete_before_static_registry_assumption() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert len(result.pending_rows) == 0
    assert result.deferred_rows == ("policy_review:separate_connector_enablement",)


def test_phase27a_deribit_dialect_is_verified_from_official_docs() -> None:
    spec = _deribit_spec()
    assert spec.dialect_id == "deribit:l2_orderbook:book_instrument_interval"
    assert spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    assert public_feed_dialect_rejection_reasons(spec) == ()
    assert len(spec.official_doc_refs) >= 5


def test_phase27a_legacy_placeholder_alias_resolves_to_verified_spec() -> None:
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")
    assert spec.dialect_id == "deribit:l2_orderbook:book_instrument_interval"
    assert spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS


def test_phase27a_static_fields_are_fail_closed() -> None:
    spec = _deribit_spec()
    assert spec.supports_delta_stream is True
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.max_gap_tolerance == 0
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()
