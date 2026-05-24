from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import (
    DeribitPaperTradeGateResult,
    DeribitPaperTradeOperatorTrigger,
    deribit_paper_trade_gate_audit_record_to_dict,
    run_deribit_paper_trade_gate,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs

PROOF = Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json")


def _proof() -> dict[str, object]:
    return json.loads(PROOF.read_text(encoding="utf-8"))


def _phase38_trade_result() -> DeribitPaperTradeGateResult:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-first-paper-trade-smoke",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    trigger = DeribitPaperTradeOperatorTrigger(
        operator_id="operator-phase38-offline-smoke",
        run_id=trigger.run_id,
        idempotency_key=trigger.idempotency_key,
        simulation_only=True,
    )
    return run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)


def _audit_record_hash(result: DeribitPaperTradeGateResult) -> str:
    payload = deribit_paper_trade_gate_audit_record_to_dict(result.audit_record)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_phase38b_proof_artifact_has_required_schema_and_scope() -> None:
    proof = _proof()

    assert proof["schema_version"] == "deribit_first_paper_trade_smoke_proof.v1"
    assert proof["phase"] == "38"
    assert proof["source"] == "deterministic_offline_phase37_gate_fixture"
    assert proof["simulation_only"] is True
    assert proof["live_enabled"] is False
    assert proof["shadow_enabled"] is False
    assert proof["auto_loop_enabled"] is False
    assert proof["venue"] == "deribit"
    assert proof["instrument"] == "BTC-PERPETUAL"
    assert proof["canonical_symbol"] == "BTC-PERP"


def test_phase38b_proof_artifact_matches_actual_phase37_gate_output() -> None:
    proof = _proof()
    result = _phase38_trade_result()

    assert proof["run_id"] == result.run_id
    assert proof["fill_status"] == "FILLED"
    assert proof["ledger_mutated"] is result.ledger_mutated
    assert proof["reason_code"] == result.reason_code
    assert proof["fill_id"] == result.fill_id
    assert proof["application_id"] == result.audit_record.audit_id
    assert (
        proof["before_ledger_summary"]
        == deribit_paper_trade_gate_audit_record_to_dict(result.audit_record)["before_ledger_summary"]
    )
    assert (
        proof["after_ledger_summary"]
        == deribit_paper_trade_gate_audit_record_to_dict(result.audit_record)["after_ledger_summary"]
    )
    assert proof["audit_record"] == deribit_paper_trade_gate_audit_record_to_dict(result.audit_record)
    assert proof["audit_record_sha256"] == _audit_record_hash(result)


def test_phase38b_proof_artifact_records_current_readiness_state() -> None:
    proof = _proof()
    readiness = evaluate_deribit_manual_review_readiness()

    assert proof["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
    assert proof["validator_state_summary"] == {
        "accepted": readiness.accepted,
        "evidence_review_complete": readiness.evidence_review_complete,
        "ready_for_engineering_patch": readiness.ready_for_engineering_patch,
        "connector_enablement_ready": readiness.connector_enablement_ready,
        "pending_rows": len(readiness.pending_rows),
        "deferred_rows": list(readiness.deferred_rows),
        "rejection_reasons": list(readiness.rejection_reasons),
        "b1_b5_status": readiness.b1_b5_status,
    }


def test_phase38b_proof_artifact_safety_invariants_are_explicit() -> None:
    proof = _proof()
    invariants = proof["safety_invariants"]

    assert invariants == {
        "no_private_api": True,
        "no_credentials": True,
        "no_exchange_orders": True,
        "no_execution_adapter": True,
        "no_order_routing": True,
        "no_strategy_alpha": True,
        "no_scheduler": True,
        "no_automatic_paper_loop": True,
        "no_shadow": True,
        "no_live": True,
        "no_ci_live_network_dependency": True,
    }
