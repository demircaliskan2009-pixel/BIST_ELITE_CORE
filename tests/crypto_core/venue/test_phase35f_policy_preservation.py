from __future__ import annotations

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.deribit_paper_fill_model import DeribitPaperFillRequest
from crypto_core.venue.deribit_paper_order_intent import DeribitPaperPreFillRiskPolicy
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


def test_phase35f_connector_ready_dialect_policy_is_preserved() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    spec = ready[0]
    assert spec.venue_id is VenueId.DERIBIT
    assert spec.feed_type is PublicFeedType.L2_ORDERBOOK
    assert spec.enabled_for_connector is True
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase35f_fill_model_bridge_remains_request_only() -> None:
    annotations = DeribitPaperFillRequest.__dataclass_fields__

    assert set(annotations) == {
        "request_id",
        "side",
        "style",
        "quantity",
        "limit_price",
        "simulation_only",
    }


def test_phase35f_default_risk_policy_is_bounded_and_no_ledger_requirement_is_faked() -> None:
    policy = DeribitPaperPreFillRiskPolicy()

    assert policy.max_order_qty == 1.0
    assert policy.max_order_notional == 50_000.0
    assert policy.require_accounting_state is False
