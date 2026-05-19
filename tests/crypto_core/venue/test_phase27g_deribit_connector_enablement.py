"""Phase 27G Deribit public dialect enablement tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    evaluate_public_feed_dialect_gate,
)
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = REPO_ROOT / "src" / "crypto_core" / "venue" / "public_feed_dialects.py"


def _deribit_spec():
    specs = dialects_for_venue(VenueId.DERIBIT)
    assert len(specs) == 1
    return specs[0]


def test_phase27g_deribit_verified_public_dialect_enabled_for_connector() -> None:
    spec = _deribit_spec()
    gate = evaluate_public_feed_dialect_gate(spec)

    assert spec.dialect_id == "deribit:l2_orderbook:book_instrument_interval"
    assert spec.enabled_for_connector is True
    assert spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    assert gate.accepted is True
    assert gate.connector_allowed is True
    assert gate.rejection_reasons == ()


def test_phase27g_only_deribit_public_dialect_is_connector_ready() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"


def test_phase27g_verified_fields_unchanged_except_enabled_flag() -> None:
    spec = _deribit_spec()

    assert spec.supports_delta_stream is True
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.requires_heartbeat is True
    assert spec.supports_resync is True
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase27g_registry_adds_no_private_or_order_runtime_surface() -> None:
    source = REGISTRY.read_text(encoding="utf-8").lower()
    for forbidden in (
        "api_key",
        "api_secret",
        "private_api",
        "place_order",
        "cancel_order",
        "deposit",
        "withdraw",
        "executionmode.live",
        "paper",
        "shadow",
    ):
        assert forbidden not in source
