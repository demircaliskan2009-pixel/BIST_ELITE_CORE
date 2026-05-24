from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_hard_capped_paper_session import (
    DERIBIT_PAPER_SESSION_HARD_CAP,
    DeribitHardCappedPaperSessionRequest,
    run_deribit_hard_capped_paper_session,
)
from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_run_harness import DeribitPaperRunHarnessInputs
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs

ARTIFACT = Path("docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json")
PHASE40_ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_OPERATOR_PAPER_RUN_ARTIFACT_40B.json")
PHASE41_REPORT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_RUN_TELEMETRY_REPORT_41B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def _phase42_request(**overrides: object) -> DeribitHardCappedPaperSessionRequest:
    values = {
        "operator_id": "operator-phase42-offline-session",
        "session_id": "phase42-hard-capped-paper-session",
        "idempotency_key": "idem-phase42-hard-capped-paper-session",
        "simulation_only": True,
        "max_session_trades": 2,
    }
    values.update(overrides)
    return DeribitHardCappedPaperSessionRequest(**values)


def _trade_input(intent_id: str) -> DeribitPaperRunHarnessInputs:
    _, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id=intent_id,
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


def _phase42_trade_inputs(count: int = 2) -> tuple[DeribitPaperRunHarnessInputs, ...]:
    return tuple(_trade_input(f"phase42-session-trade-{index}") for index in range(1, count + 1))


def _run_phase42_session():
    return run_deribit_hard_capped_paper_session(_phase42_request(), _phase42_trade_inputs())


def test_phase42b_artifact_has_required_schema_and_source_refs() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE40_ARTIFACT.exists()
    assert PHASE41_REPORT.exists()
    assert artifact["schema_version"] == "deribit_hard_capped_paper_session_artifact.v1"
    assert artifact["phase"] == "42"
    assert artifact["source"] == "deribit_hard_capped_paper_session_v1"
    assert artifact["source_phase40_artifact"] == str(PHASE40_ARTIFACT).replace("\\", "/")
    assert artifact["source_phase41_telemetry_report"] == str(PHASE41_REPORT).replace("\\", "/")


def test_phase42b_artifact_matches_actual_session_output() -> None:
    result = _run_phase42_session()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase42b_artifact_records_hard_capped_multi_run_counts() -> None:
    artifact = _artifact()

    assert artifact["accepted"] is True
    assert artifact["session_id"] == "phase42-hard-capped-paper-session"
    assert artifact["operator_id"] == "operator-phase42-offline-session"
    assert artifact["hard_cap"] == DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert artifact["max_session_trades"] == 2
    assert artifact["trades_requested"] == 2
    assert artifact["trades_attempted"] == 2
    assert artifact["trades_filled"] == 2
    assert artifact["trades_rejected"] == 0
    assert artifact["ledger_mutated"] is True
    assert artifact["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1


def test_phase42b_artifact_final_ledger_summary_is_deterministic() -> None:
    after = _artifact()["after_ledger_summary"]

    assert after["symbol"] == "BTC-PERPETUAL"
    assert after["canonical_symbol"] == "BTC-PERP"
    assert after["cash_balance"] == 10_000.0
    assert after["position_qty"] == 1.0
    assert after["average_entry_price"] == 50_010.0
    assert after["applied_fill_count"] == 2
    assert after["applied_request_count"] == 3
    assert after["applied_idempotency_count"] == 3
