from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from crypto_core.audit import (
    DecisionEvidenceRef,
    DecisionLedgerRecord,
    DecisionLedgerStage,
    DecisionLedgerStatus,
    build_strategy_spec_decision_record,
    build_validation_decision_record,
    decision_ledger_digest,
    decision_ledger_record_from_dict,
    decision_ledger_record_to_dict,
)
from crypto_core.data.requirements import default_perp_data_requirement_registry
from crypto_core.service.evidence_store import EvidenceStore, decision_ledger_record_to_evidence_payload
from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation import LeakageBiasRepaintStatus, validate_strategy_data_requirements
from crypto_core.validation.leakage_bias_repaint import LeakageBiasRepaintResult


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "decision-ledger-store-s01",
        "strategy_version": "v1",
        "strategy_family": "microstructure",
        "edge_family": "order_flow_imbalance",
        "instrument_universe": ["BTCUSDT"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["binance_usdm", "bybit_usdt_perp"],
        "timeframe": "1m",
        "bar_definition": "ohlcv",
        "entry_conditions": ["ofi > 0.5"],
        "exit_conditions": ["ofi < 0.1"],
        "invalidation_conditions": ["spread > 20bps"],
        "risk_caps": {"max_leverage": 3.0, "max_notional": 1000},
        "data_requirements": {
            "order_book": {"required": True},
            "funding_rate": {"required": True},
            "mark_price": {"required": True},
            "liquidation": {"required": True},
        },
        "feature_requirements": {"ofi_window": 20},
        "latency_sensitivity": "high",
        "funding_sensitivity": "medium",
        "fee_model_requirement": "maker_taker",
        "slippage_model_requirement": "book_impact_v1",
        "expected_regime": "volatile",
        "failure_modes": ["feed_drop"],
        "kill_switch_triggers": ["dtl_breach"],
        "telemetry_fields": ["edge_score", "risk_state"],
        "promotion_requirements": ["wf_pass", "pbo_pass"],
    }


def _valid_spec() -> StrategySpec:
    result = validate_strategy_spec(_strategy_payload())
    assert result.accepted is True
    assert result.spec is not None
    return result.spec


def _evidence_ref() -> DecisionEvidenceRef:
    return DecisionEvidenceRef(source_type="validation_result", digest="a" * 64, source_id="validation-result-v1")


def _strategy_record() -> DecisionLedgerRecord:
    result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-store-001",
    )
    assert result.accepted is True
    assert result.record is not None
    return result.record


def _lbr_record() -> DecisionLedgerRecord:
    lbr_result = LeakageBiasRepaintResult(
        accepted=True,
        status=LeakageBiasRepaintStatus.PASS,
        rejection_reasons=(),
        needs_research_reasons=(),
    )
    result = build_validation_decision_record(
        DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
        lbr_result,
        strategy_id="decision-ledger-store-s01",
        strategy_digest="c" * 64,
        input_digest="d" * 64,
        correlation_id="corr-store-001",
        evidence_refs=(_evidence_ref(),),
    )
    assert result.accepted is True
    assert result.record is not None
    return result.record


def _pit_record() -> DecisionLedgerRecord:
    pit_result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry())
    result = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        pit_result,
        strategy_id="decision-ledger-store-s01",
        strategy_digest="c" * 64,
        input_digest="e" * 64,
        correlation_id="corr-store-001",
        evidence_refs=(_evidence_ref(),),
    )
    assert result.accepted is True
    assert result.record is not None
    return result.record


def _raw_lines(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class _TrackingLock:
    def __init__(self) -> None:
        self.held = False

    def __enter__(self) -> "_TrackingLock":
        assert self.held is False
        self.held = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.held = False
        return False


def test_valid_strategy_spec_decision_record_appends_to_evidence_store(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    record = _strategy_record()

    result = store.append_decision_ledger_record(record)

    assert result.success is True
    loaded = store.load_evidence()
    assert len(loaded) == 1
    assert loaded[0]["evidence_type"] == "audit_record"
    assert loaded[0]["timestamp_ns"] == 0
    assert loaded[0]["data"]["payload_type"] == "decision_ledger_record"
    assert loaded[0]["data"]["stage"] == DecisionLedgerStage.STRATEGY_SPEC.value


def test_valid_lbr_and_pit_decision_records_append_with_evidence_refs(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    lbr_result = store.append_decision_ledger_record(_lbr_record())
    pit_result = store.append_decision_ledger_record(_pit_record())

    assert lbr_result.success is True
    assert pit_result.success is True
    records = store.load_evidence()
    assert records[0]["data"]["stage"] == DecisionLedgerStage.LEAKAGE_BIAS_REPAINT.value
    assert records[1]["data"]["stage"] == DecisionLedgerStage.PIT_PARITY.value
    assert records[0]["data"]["evidence_refs"]
    assert records[1]["data"]["evidence_refs"]


def test_invalid_decision_record_does_not_append(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    invalid = replace(
        _strategy_record(),
        accepted=True,
        rejection_reasons=("decision_ledger:test_rejection",),
    )

    result = store.append_decision_ledger_record(invalid)

    assert result.success is False
    assert "accepted_with_rejection_reasons" in (result.error or "")
    assert not store.evidence_log_path.exists()


def test_malformed_mapping_does_not_append(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    result = store.append_decision_ledger_record({"not": "a decision ledger record"})

    assert result.success is False
    assert result.error
    assert not store.evidence_log_path.exists()


def test_bist_leakage_record_rejects(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    payload = decision_ledger_record_to_dict(_strategy_record())
    payload["metadata"] = {"source": "Matriks"}

    result = store.append_decision_ledger_record(payload)

    assert result.success is False
    assert "decision_ledger:bist_scope_leakage" in (result.error or "")
    assert not store.evidence_log_path.exists()


def test_forbidden_live_private_order_scheduler_metadata_rejects(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    payload = decision_ledger_record_to_dict(_strategy_record())
    payload["metadata"] = {
        "scheduler": "enabled",
        "private_api": "x",
        "order_router": "v1",
        "auto_loop": True,
        "shadow_live_execution": False,
        "credentials": "bad",
        "live": "bad",
    }

    result = store.append_decision_ledger_record(payload)

    assert result.success is False
    assert "decision_ledger:forbidden_field_scheduler" in (result.error or "")
    assert "decision_ledger:forbidden_field_private_api" in (result.error or "")
    assert not store.evidence_log_path.exists()


def test_duplicate_append_is_explicitly_rejected(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    record = _strategy_record()

    first = store.append_decision_ledger_record(record)
    second = store.append_decision_ledger_record(record)

    assert first.success is True
    assert second.success is False
    assert "Duplicate decision ledger evidence digest" in (second.error or "")
    assert store.evidence_line_count() == 1


def test_duplicate_digest_check_runs_inside_append_lock(tmp_path: Path, monkeypatch) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    tracking_lock = _TrackingLock()
    monkeypatch.setattr(store, "_lock", tracking_lock)
    original_exists = store._decision_ledger_digest_exists
    checked = False

    def wrapped_exists(evidence_digest: object) -> bool:
        nonlocal checked
        checked = True
        assert tracking_lock.held is True
        return original_exists(evidence_digest)

    monkeypatch.setattr(store, "_decision_ledger_digest_exists", wrapped_exists)

    result = store.append_decision_ledger_record(_strategy_record())

    assert result.success is True
    assert checked is True


def test_payload_digest_equals_decision_ledger_digest(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    record = _strategy_record()

    result = store.append_decision_ledger_record(record)

    assert result.success is True
    loaded = store.load_evidence()
    assert loaded[0]["data"]["evidence_digest"] == decision_ledger_digest(record)


def test_stored_payload_round_trips_through_decision_ledger_from_dict(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    record = _strategy_record()

    result = store.append_decision_ledger_record(record)

    assert result.success is True
    loaded = store.load_evidence()
    ledger_payload = loaded[0]["data"]["decision_ledger_record"]
    ledger_result = decision_ledger_record_from_dict(ledger_payload)
    assert ledger_result.accepted is True
    assert ledger_result.record is not None
    assert decision_ledger_digest(ledger_result.record) == decision_ledger_digest(record)


def test_no_runtime_timestamp_is_added_to_decision_ledger_payload(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    result = store.append_decision_ledger_record(_strategy_record())

    assert result.success is True
    raw = _raw_lines(store.evidence_log_path)
    assert raw[0]["timestamp_ns"] == 0
    data = raw[0]["data"]
    assert "timestamp_ns" not in data
    assert "created_at" not in data
    assert "wall_clock" not in data


def test_evidence_payload_helper_uses_canonical_record_payload() -> None:
    record = _strategy_record()

    payload = decision_ledger_record_to_evidence_payload(record)

    assert payload["decision_ledger_record"] == decision_ledger_record_to_dict(record)
    assert payload["evidence_digest"] == decision_ledger_digest(record)
    assert payload["status"] == DecisionLedgerStatus.ACCEPTED.value
