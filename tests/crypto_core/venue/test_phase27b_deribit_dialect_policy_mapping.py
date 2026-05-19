"""Phase 27B Deribit dialect policy mapping tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import dialects_for_venue

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_AUDIT = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_POLICY_DECISION_AUDIT_26AM.md"
STATIC_VERIFICATION = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md"


def _spec():
    return dialects_for_venue(VenueId.DERIBIT)[0]


def test_phase27b_checksum_policy_maps_to_no_checksum_support() -> None:
    policy = POLICY_AUDIT.read_text(encoding="utf-8")
    spec = _spec()
    assert "NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE" in policy
    assert "DO_NOT_SET_SUPPORTS_CHECKSUM_TRUE_IN_THIS_PHASE" in policy
    assert spec.supports_checksum is False
    assert spec.checksum_model.value == "none"


def test_phase27b_liveness_and_budget_policy_values_map_to_registry() -> None:
    policy = POLICY_AUDIT.read_text(encoding="utf-8")
    spec = _spec()
    assert "PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000" in policy
    assert "MAX_STALENESS_MS_2000" in policy
    assert "MAX_RECEIVE_LAG_MS_1000" in policy
    assert spec.requires_heartbeat is True
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase27b_official_and_policy_refs_are_present() -> None:
    spec = _spec()
    refs = set(spec.official_doc_refs)
    assert "DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md#proof-ready-technical-rows" in refs
    assert "DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md#proof_ready_not_approved-15" in refs
    assert "DERIBIT_POLICY_DECISION_AUDIT_26AM.md#operator-approved-policy-values" in refs
    assert "DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md#row-classifications" in refs
    assert (
        "DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md#5-expected-validator-outcome-after-phase-26aw-patch"
        in refs
    )


def test_phase27b_static_verification_doc_records_conservative_sequence_limitation() -> None:
    text = STATIC_VERIFICATION.read_text(encoding="utf-8")
    assert "`SNAPSHOT_DELTA_RANGE`" in text
    assert "Exact Deribit `prev_change_id == previous change_id` has no dedicated enum" in text
    assert "`max_gap_tolerance`" in text
    assert "`0`" in text
