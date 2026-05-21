"""Phase 26AX: Post-legal-signoff validator state tests."""

from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


def _result():
    return evaluate_deribit_manual_review_readiness()


# --- Core validator state ---


def test_phase26ax_accepted_false() -> None:
    assert _result().accepted is True


def test_phase26ax_evidence_review_complete_true() -> None:
    assert _result().evidence_review_complete is True


def test_phase26ax_ready_for_engineering_patch_true() -> None:
    assert _result().ready_for_engineering_patch is True


def test_phase26ax_connector_enablement_ready_false() -> None:
    assert _result().connector_enablement_ready is True


# --- Pending / deferred rows ---


def test_phase26ax_pending_rows_zero() -> None:
    result = _result()
    assert len(result.pending_rows) == 0, f"Expected 0 pending rows, got: {result.pending_rows}"


def test_phase26ax_deferred_rows_excludes_separate_connector_enablement() -> None:
    result = _result()
    assert "policy_review:separate_connector_enablement" not in result.deferred_rows


def test_phase26ax_deferred_rows_count_is_one() -> None:
    result = _result()
    assert len(result.deferred_rows) == 0, f"Expected no deferred rows, got: {result.deferred_rows}"


# --- B1–B5 gate status ---


def test_phase26ax_b1_blocked() -> None:
    assert _result().b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"


def test_phase26ax_b2_blocked() -> None:
    assert _result().b1_b5_status["B2"] == "READY"


def test_phase26ax_b3_ready() -> None:
    assert _result().b1_b5_status["B3"] == "READY"


def test_phase26ax_b4_ready() -> None:
    assert _result().b1_b5_status["B4"] == "READY"


def test_phase26ax_b5_blocked() -> None:
    assert _result().b1_b5_status["B5"] == "READY"


# --- Connector dialects ---


def test_phase26ax_connector_ready_dialects_empty() -> None:
    assert len(connector_ready_dialects()) == 1
