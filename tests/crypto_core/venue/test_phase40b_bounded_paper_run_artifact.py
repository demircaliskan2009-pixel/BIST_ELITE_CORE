from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_run_harness import (
    DeribitPaperRunHarnessInputs,
    DeribitPaperRunOperatorRequest,
    run_deribit_bounded_paper_run_harness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs

ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_OPERATOR_PAPER_RUN_ARTIFACT_40B.json")
PHASE38_PROOF = Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json")
PHASE39_AUDIT = Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_AUDIT_REPORT_39B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def _phase40_request() -> DeribitPaperRunOperatorRequest:
    return DeribitPaperRunOperatorRequest(
        operator_id="operator-phase40-offline-harness",
        run_id="phase40-bounded-paper-run",
        idempotency_key="idem-phase40-bounded-paper-run",
        simulation_only=True,
    )


def _phase40_inputs() -> DeribitPaperRunHarnessInputs:
    _, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase40-bounded-paper-run",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    return DeribitPaperRunHarnessInputs(
        intent=intent,
        decision=decision,
        fill_request=fill_request,
        frame=frame,
        ledger_state=ledger,
    )


def _run_phase40_harness():
    return run_deribit_bounded_paper_run_harness(_phase40_request(), _phase40_inputs())


def test_phase40b_artifact_has_required_schema_and_source_refs() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE38_PROOF.exists()
    assert PHASE39_AUDIT.exists()
    assert artifact["schema_version"] == "deribit_bounded_operator_paper_run_artifact.v1"
    assert artifact["phase"] == "40"
    assert artifact["source"] == "deribit_paper_run_harness_v1"
    assert artifact["source_phase38_proof_artifact"] == str(PHASE38_PROOF).replace("\\", "/")
    assert artifact["source_phase39_audit_report"] == str(PHASE39_AUDIT).replace("\\", "/")


def test_phase40b_artifact_matches_actual_harness_output() -> None:
    result = _run_phase40_harness()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase40b_artifact_records_one_bounded_paper_trade() -> None:
    artifact = _artifact()

    assert artifact["accepted"] is True
    assert artifact["run_id"] == "phase40-bounded-paper-run"
    assert artifact["operator_id"] == "operator-phase40-offline-harness"
    assert artifact["simulation_only"] is True
    assert artifact["max_trades"] == 1
    assert artifact["trade_count_attempted"] == 1
    assert artifact["trade_count_accepted"] == 1
    assert artifact["fill_count"] == 1
    assert artifact["ledger_mutation_count"] == 1
    assert artifact["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1


def test_phase40b_artifact_embeds_expected_safety_invariants() -> None:
    invariants = _artifact()["safety_invariants"]
    assert isinstance(invariants, dict)

    for flag in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
        "no_ci_live_network_dependency",
    ):
        assert invariants[flag] is True
