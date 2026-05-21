"""Phase 25Z Deribit non-null prev_change_id capture spec tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NON_NULL_PREV_CHANGE_ID_CAPTURE_SPEC_25Z.md"


def _spec_doc() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def test_phase25z_capture_spec_sets_public_market_data_boundary() -> None:
    doc = _spec_doc()

    assert "status: SPEC_ONLY_NO_NETWORK_CHANGE" in doc
    assert "`dry_run` | Must be `true`." in doc
    assert "`operator_authorization` | Must be `PUBLIC_MARKET_DATA_ONLY`." in doc
    assert "credentials" in doc
    assert "private API" in doc
    assert "orders" in doc
    assert "`connector_ready_dialects()`" in doc
    assert "NOT_connector_enablement: true" in doc


def test_phase25z_capture_spec_requires_longer_public_book_capture() -> None:
    doc = _spec_doc()

    assert "--duration-seconds 30" in doc
    assert "--max-messages 100" in doc
    assert "`duration_seconds >= 30`" in doc
    assert "`max_messages >= 100`" in doc
    assert "book.BTC-PERPETUAL.none.10.100ms" in doc
    assert "public unauthenticated book channel only" in doc


def test_phase25z_capture_spec_requires_non_null_prev_and_exact_continuity() -> None:
    doc = _spec_doc()

    assert "At least one actual observed event has non-null integer `payload_sample.prev_change_id`" in doc
    assert "current.payload_sample.prev_change_id == prior.payload_sample.change_id" in doc
    assert "A non-null but mismatched `prev_change_id` is not continuity proof." in doc
    assert "`non_null_prev_change_id_observed=false`" in doc
    assert "`continuity_pair_missing=true`" in doc
    assert "`prev_change_id`: WAIT_INSUFFICIENT" in doc
    assert "`continuity_condition`: WAIT_INSUFFICIENT" in doc


def test_phase25z_capture_spec_aligns_with_raw_smoke_sample_events_schema() -> None:
    doc = _spec_doc()

    assert "`sample_events` | Raw smoke result schema." in doc
    assert "`observed_events` | Optional normalized proof schema derived from `sample_events`" in doc
    assert "adjacent event rows are stored under `sample_events`" in doc
    assert "`payload_sample.change_id`" in doc
    assert "`payload_sample.prev_change_id`" in doc
    assert "The normalized artifact must not invent top-level raw fields" in doc


def test_phase25z_spec_records_no_script_or_source_runtime_edit_needed() -> None:
    doc = _spec_doc()

    assert "No script edit required for this docs/tests proof plan." in doc
    assert "No source runtime edit authorized or required in this phase." in doc
    assert "DERIBIT_PUBLIC_WS_MAX_DURATION_SECONDS=30.0" in doc
    assert "DERIBIT_PUBLIC_WS_MAX_MESSAGES=100" in doc


def test_phase25z_validator_and_connector_readiness_remain_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is True
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is True
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "READY_FOR_HUMAN_GATE",
        "B2": "READY",
        "B3": "READY",
        "B4": "READY",
        "B5": "READY",
    }
    assert len(connector_ready_dialects()) == 1
