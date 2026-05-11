"""Phase 20H — Stage5 Runtime Evidence Persistence / Operator Attestation Store.

Tests:
    - Stage5RuntimeEvidenceRecord serialization roundtrip
    - stage5_runtime_evidence_record_from_dict fail-closed validation
    - build_stage5_gate_from_runtime_evidence_record behavior
    - JSON safety
    - Deterministic replay invariant
    - No credential/env/network keys ever required
"""

from __future__ import annotations

import json

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20h"
_SLEEVE_ID = "sleeve-20h"
_RECORD_ID = "record-20h-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approval(*, approved: bool = True) -> portfolio.Stage5OperatorApprovalEvidence:
    return portfolio.Stage5OperatorApprovalEvidence(
        approved=approved,
        approver_id="ops-lead-20h",
        approved_at_ns=90 * _DAY_NS,
        approval_reference="approval-ticket-20h",
        rejection_reasons=(),
    )


def _credentials(*, valid: bool = True) -> portfolio.Stage5CredentialAttestationEvidence:
    return portfolio.Stage5CredentialAttestationEvidence(
        live_api_credentials_valid=valid,
        attested_by="security-lead-20h",
        attested_at_ns=91 * _DAY_NS,
        attestation_reference="credential-attestation-20h",
        rejection_reasons=(),
    )


def _risk(*, governance_clear: bool = True, kill_switch_clear: bool = True) -> portfolio.Stage5RiskGovernanceEvidence:
    return portfolio.Stage5RiskGovernanceEvidence(
        risk_governance_clear=governance_clear,
        kill_switch_clear=kill_switch_clear,
        ehs_at_entry=0.80,
        max_drawdown_bps=None,
        attested_at_ns=92 * _DAY_NS,
        rejection_reasons=(),
    )


def _canary(*, tier: float = 10.0, weeks: int = 0) -> portfolio.Stage5CanaryTierEvidence:
    return portfolio.Stage5CanaryTierEvidence(
        allocation_tier_pct=tier,
        weeks_at_tier=weeks,
        canary_observation_count=20,
        canary_pnl_non_negative=True,
        canary_drawdown_within_limit=True,
        canary_slippage_within_limit=True,
        canary_incidents=0,
        as_of_ns=100 * _DAY_NS,
        rejection_reasons=(),
    )


def _bundle(**overrides: object) -> portfolio.Stage5RuntimeEvidenceBundle:
    values: dict[str, object] = {
        "edge_id": _EDGE_ID,
        "as_of_ns": 100 * _DAY_NS,
        "operator_approval": _approval(),
        "credential_attestation": _credentials(),
        "risk_governance": _risk(),
        "canary_tier": _canary(),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceBundle(**values)  # type: ignore[arg-type]


def _record(**overrides: object) -> portfolio.Stage5RuntimeEvidenceRecord:
    values: dict[str, object] = {
        "record_id": _RECORD_ID,
        "sleeve_id": _SLEEVE_ID,
        "edge_id": _EDGE_ID,
        "evidence_bundle": _bundle(),
        "created_at_ns": 100 * _DAY_NS,
        "source": "operator_attestation",
        "schema_version": 1,
        "notes": (),
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceRecord(**values)  # type: ignore[arg-type]


def _baseline() -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20h",
        edge_id=_EDGE_ID,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(*, passed: bool = True) -> validation.Stage4PaperSummary:
    if passed:
        return validation.Stage4PaperSummary(
            paper_id="paper-20h",
            edge_id=_EDGE_ID,
            started_at_ns=1,
            stopped_at_ns=31 * _DAY_NS + 1,
            paper_sharpe=1.2,
            paper_hit_rate=0.58,
            paper_slippage_bps=4.5,
            paper_fill_rate=0.97,
            paper_trade_count=42,
        )
    else:
        # Below all thresholds → comparison fails
        return validation.Stage4PaperSummary(
            paper_id="paper-20h-fail",
            edge_id=_EDGE_ID,
            started_at_ns=1,
            stopped_at_ns=31 * _DAY_NS + 1,
            paper_sharpe=0.1,
            paper_hit_rate=0.30,
            paper_slippage_bps=20.0,
            paper_fill_rate=0.50,
            paper_trade_count=1,
        )


def _stage4_pass() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary(passed=True))


def _stage4_fail() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary(passed=False))


# ---------------------------------------------------------------------------
# Test 1 — Roundtrip preserves all fields
# ---------------------------------------------------------------------------


def test_record_to_dict_from_dict_roundtrip():
    """to_dict → from_dict roundtrip must preserve all fields exactly."""
    rec = _record(notes=("note-a", "note-b"))
    d = portfolio.stage5_runtime_evidence_record_to_dict(rec)
    restored = portfolio.stage5_runtime_evidence_record_from_dict(d)
    assert restored.record_id == rec.record_id
    assert restored.sleeve_id == rec.sleeve_id
    assert restored.edge_id == rec.edge_id
    assert restored.created_at_ns == rec.created_at_ns
    assert restored.source == rec.source
    assert restored.schema_version == rec.schema_version
    assert restored.notes == rec.notes
    assert restored.evidence_bundle == rec.evidence_bundle


# ---------------------------------------------------------------------------
# Test 2 — from_dict rejects non-dict
# ---------------------------------------------------------------------------


def test_record_from_dict_rejects_non_dict():
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict("not_a_dict")


def test_record_from_dict_rejects_list():
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict([])


# ---------------------------------------------------------------------------
# Test 3 — from_dict rejects missing/empty record_id
# ---------------------------------------------------------------------------


def test_record_from_dict_rejects_missing_record_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    del d["record_id"]
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


def test_record_from_dict_rejects_empty_record_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["record_id"] = ""
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 4 — rejects missing/empty sleeve_id
# ---------------------------------------------------------------------------


def test_record_from_dict_rejects_missing_sleeve_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    del d["sleeve_id"]
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


def test_record_from_dict_rejects_empty_sleeve_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["sleeve_id"] = ""
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 5 — rejects missing/empty edge_id
# ---------------------------------------------------------------------------


def test_record_from_dict_rejects_missing_edge_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    del d["edge_id"]
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


def test_record_from_dict_rejects_empty_edge_id():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["edge_id"] = ""
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 6 — rejects invalid created_at_ns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [0, -1, -1000, "not_int", None, 0.0])
def test_record_from_dict_rejects_invalid_created_at_ns(bad_value):
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["created_at_ns"] = bad_value
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 7 — rejects invalid schema_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_version", [0, -1, "v1", None, 0.5])
def test_record_from_dict_rejects_invalid_schema_version(bad_version):
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["schema_version"] = bad_version
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 8 — rejects invalid notes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_notes", ["not_a_list", [1, 2, 3], [None], ["ok", 42]])
def test_record_from_dict_rejects_invalid_notes(bad_notes):
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["notes"] = bad_notes
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 9 — rejects malformed evidence_bundle
# ---------------------------------------------------------------------------


def test_record_from_dict_rejects_missing_evidence_bundle():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    del d["evidence_bundle"]
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


def test_record_from_dict_rejects_non_dict_evidence_bundle():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["evidence_bundle"] = "not_a_dict"
    with pytest.raises(portfolio.SleevePortfolioCorruptError):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


def test_record_from_dict_rejects_incomplete_evidence_bundle():
    d = portfolio.stage5_runtime_evidence_record_to_dict(_record())
    d["evidence_bundle"] = {"edge_id": _EDGE_ID}  # Missing required sub-fields
    # bundle deserializer raises SleevePortfolioValidationError (ValueError) for missing int fields
    with pytest.raises((portfolio.SleevePortfolioCorruptError, ValueError)):
        portfolio.stage5_runtime_evidence_record_from_dict(d)


# ---------------------------------------------------------------------------
# Test 10 — build gate from valid record returns passing gate
# ---------------------------------------------------------------------------


def test_build_gate_from_valid_record_returns_passing_gate():
    """Valid record with passing Stage4 result must produce a passing gate (Phase 20J: Stage4 required)."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_pass(),
    )
    assert gate.passed is True
    assert gate.edge_id == _EDGE_ID
    assert len(gate.rejection_reasons) == 0


# ---------------------------------------------------------------------------
# Test 11 — build gate with failed operator approval returns failed gate with stable reason
# ---------------------------------------------------------------------------


def test_build_gate_failed_operator_approval_returns_failed_gate():
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    assert gate.passed is False
    assert "stage5:operator_approval_missing" in gate.rejection_reasons


def test_build_gate_failed_operator_approval_reason_is_stable():
    """Same input → same rejection reason code deterministically."""
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    gate1 = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    gate2 = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    assert gate1.rejection_reasons == gate2.rejection_reasons


# ---------------------------------------------------------------------------
# Test 12 — build gate defaults as_of_ns from record.created_at_ns
# ---------------------------------------------------------------------------


def test_build_gate_defaults_as_of_ns_from_record():
    rec = _record(created_at_ns=55 * _DAY_NS)
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    assert gate.as_of_ns == 55 * _DAY_NS


# ---------------------------------------------------------------------------
# Test 13 — build gate uses supplied as_of_ns override
# ---------------------------------------------------------------------------


def test_build_gate_uses_supplied_as_of_ns_override():
    rec = _record(created_at_ns=55 * _DAY_NS)
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        as_of_ns=99 * _DAY_NS,
    )
    assert gate.as_of_ns == 99 * _DAY_NS


# ---------------------------------------------------------------------------
# Test 14 — build gate with failed Stage4 result returns failed Stage5 gate
# ---------------------------------------------------------------------------


def test_build_gate_with_failed_stage4_returns_failed_gate():
    rec = _record()
    failed_s4 = _stage4_fail()
    assert not failed_s4.passed
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=failed_s4,
    )
    assert gate.passed is False
    assert gate.stage4_passed is False
    assert "stage5:stage4_not_passed" in gate.rejection_reasons


def test_build_gate_with_passed_stage4_does_not_add_stage4_rejection():
    rec = _record()
    passed_s4 = _stage4_pass()
    assert passed_s4.passed
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=passed_s4,
    )
    assert gate.passed is True
    assert "stage5:stage4_not_passed" not in gate.rejection_reasons


def test_build_gate_no_stage4_result_forces_failure():
    """stage4_comparison_result=None → gate must fail with stable 'stage5:stage4_comparison_missing' reason.

    Phase 20J invariant: Stage5 runtime evidence cannot become live-ready without a
    matched, passing Stage4 comparison.  A missing Stage4 result is treated as a
    blocker, not a neutral condition.
    """
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,
    )
    assert gate.passed is False
    assert gate.stage4_passed is False
    assert "stage5:stage4_comparison_missing" in gate.rejection_reasons


# ---------------------------------------------------------------------------
# Test 15 — JSON dumps works for record dict and gate dict
# ---------------------------------------------------------------------------


def test_record_dict_is_json_serializable():
    rec = _record(notes=("note-1",))
    d = portfolio.stage5_runtime_evidence_record_to_dict(rec)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    assert _RECORD_ID in serialized


def test_gate_dict_from_record_is_json_serializable():
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    gate_d = portfolio.stage5_live_readiness_gate_to_dict(gate)
    serialized = json.dumps(gate_d)
    assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# Test 16 — Deterministic replay: same record/input → same gate dict
# ---------------------------------------------------------------------------


def test_build_gate_deterministic_replay_same_output():
    rec = _record()
    gate1 = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    gate2 = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    assert portfolio.stage5_live_readiness_gate_to_dict(gate1) == portfolio.stage5_live_readiness_gate_to_dict(gate2)


def test_record_roundtrip_deterministic():
    rec = _record()
    d1 = portfolio.stage5_runtime_evidence_record_to_dict(rec)
    d2 = portfolio.stage5_runtime_evidence_record_to_dict(portfolio.stage5_runtime_evidence_record_from_dict(d1))
    assert d1 == d2


# ---------------------------------------------------------------------------
# Test 17 — No credential/env/network/client keys are read or required
# ---------------------------------------------------------------------------


def test_build_gate_no_env_or_network_required():
    """build_stage5_gate_from_runtime_evidence_record must not raise even if all
    env vars are absent.  Since it is pure/deterministic, this always holds; we
    confirm by verifying that the function returns without touching os.environ.
    """
    import os

    original_environ = dict(os.environ)
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    # os.environ must not have changed
    assert dict(os.environ) == original_environ
    assert gate is not None


def test_record_dict_contains_no_credential_keys():
    """The serialized dict must not contain any credential or network keys."""
    forbidden = {"api_key", "secret", "token", "client", "network_client", "password", "private_key", "credentials"}
    rec = _record()
    d = portfolio.stage5_runtime_evidence_record_to_dict(rec)

    def _all_keys(obj: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                keys |= _all_keys(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                keys |= _all_keys(item)
        return keys

    found = _all_keys(d) & forbidden
    assert not found, f"Forbidden keys found in record dict: {found}"


# ---------------------------------------------------------------------------
# Test 18 — edge_id from record overrides bundle edge_id
# ---------------------------------------------------------------------------


def test_build_gate_uses_record_edge_id_not_bundle_edge_id():
    """The gate edge_id must come from record.edge_id, not the bundle field."""
    # Build a bundle with a different edge_id than the record
    mismatched_bundle = _bundle(edge_id="bundle-edge-different")
    # Wrap it in a record with the authoritative edge_id
    rec = portfolio.Stage5RuntimeEvidenceRecord(
        record_id=_RECORD_ID,
        sleeve_id=_SLEEVE_ID,
        edge_id=_EDGE_ID,  # This is the authoritative one
        evidence_bundle=mismatched_bundle,
        created_at_ns=100 * _DAY_NS,
    )
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(rec, allocation_tier_pct=10.0, weeks_at_tier=0)
    assert gate.edge_id == _EDGE_ID


# ---------------------------------------------------------------------------
# Test 19 — Stage5RuntimeEvidenceRecord is frozen (immutable)
# ---------------------------------------------------------------------------


def test_stage5_runtime_evidence_record_is_frozen():
    rec = _record()
    with pytest.raises((AttributeError, TypeError)):
        rec.record_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 20 — Default field values are correct
# ---------------------------------------------------------------------------


def test_stage5_runtime_evidence_record_default_source():
    rec = portfolio.Stage5RuntimeEvidenceRecord(
        record_id=_RECORD_ID,
        sleeve_id=_SLEEVE_ID,
        edge_id=_EDGE_ID,
        evidence_bundle=_bundle(),
        created_at_ns=100 * _DAY_NS,
    )
    assert rec.source == "operator_attestation"
    assert rec.schema_version == 1
    assert rec.notes == ()
