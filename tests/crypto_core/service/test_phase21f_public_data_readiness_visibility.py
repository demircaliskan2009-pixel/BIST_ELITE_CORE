from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace

from crypto_core.data.public_data_readiness import PublicDataReadinessSnapshot
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.service.artifact_export import (
    EscalationStage,
    OperatorDecisionPack,
    decision_pack_from_dict,
    decision_pack_missing_evidence,
    decision_pack_to_dict,
    export_operator_decision_pack,
    load_operator_decision_pack,
)
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.service_orchestrator import ServiceOrchestrator
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, VenueId


def test_no_public_data_snapshots_is_fail_closed_in_operator_status():
    payload = _orchestrator().combined_status_dict()

    assert payload["public_data_ready"] is False
    assert payload["public_data_ready_symbols"] == []
    assert payload["public_data_readiness_blockers"] == ["public_data:readiness_snapshot_missing"]
    assert payload["public_data_readiness_snapshot_count"] == 0


def test_accepted_public_data_snapshot_surfaces_ready_symbol():
    snapshot = _accepted_snapshot(symbol="BTCUSDT")
    operator_snapshot = _orchestrator().apply_public_data_readiness_snapshot(snapshot)

    assert operator_snapshot.public_data_ready is True
    assert operator_snapshot.public_data_ready_symbols == ("binance_usdm:BTCUSDT:l2_orderbook",)
    assert operator_snapshot.public_data_readiness_blockers == ()
    assert operator_snapshot.public_data_readiness_snapshot_count == 1


def test_rejected_public_data_snapshot_surfaces_blockers_json_safe():
    orch = _orchestrator()
    orch.apply_public_data_readiness_snapshot(
        _rejected_snapshot(rejection_reasons=("public_feed:unhealthy", "public_data:order_book_not_ready"))
    )

    payload = orch.combined_status_dict()

    assert payload["public_data_ready"] is False
    assert payload["public_data_readiness_blockers"] == [
        "public_feed:unhealthy",
        "public_data:order_book_not_ready",
    ]
    assert json.dumps(payload)


def test_mixed_public_data_snapshots_fail_pack_level_readiness_with_deterministic_ordering():
    orch = _orchestrator()
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))
    orch.apply_public_data_readiness_snapshot(
        _rejected_snapshot(symbol="BTCUSDT", rejection_reasons=("public_feed:stale",))
    )

    payload = orch.combined_status_dict()

    assert payload["public_data_ready"] is False
    assert payload["public_data_ready_symbols"] == ["binance_usdm:ETHUSDT:l2_orderbook"]
    assert payload["public_data_readiness_blockers"] == ["public_feed:stale"]
    assert payload["public_data_readiness_snapshot_count"] == 2


def test_public_data_readiness_snapshot_upsert_is_deterministic_by_venue_symbol_feed():
    orch = _orchestrator()
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="BTCUSDT"))
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))

    payload = orch.combined_status_dict()

    assert payload["public_data_ready"] is True
    assert payload["public_data_ready_symbols"] == [
        "binance_usdm:BTCUSDT:l2_orderbook",
        "binance_usdm:ETHUSDT:l2_orderbook",
    ]
    assert payload["public_data_readiness_snapshot_count"] == 2


def test_public_data_readiness_rejects_malformed_snapshot():
    try:
        _orchestrator().apply_public_data_readiness_snapshot(object())  # type: ignore[arg-type]
    except ValueError as exc:
        assert "PublicDataReadinessSnapshot" in str(exc)
    else:
        raise AssertionError("expected malformed snapshot to fail closed")


def test_public_data_readiness_metadata_flows_to_decision_pack_export_load(tmp_path):
    orch = _orchestrator_with_review()
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot())
    pack = orch.decision_pack()

    assert pack.public_data_ready is True
    assert pack.public_data_ready_symbols == ("binance_usdm:BTCUSDT:l2_orderbook",)
    assert pack.public_data_readiness_blockers == ()

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    result = export_operator_decision_pack(pack=pack, evidence_store=store)
    assert result.success is True
    loaded = load_operator_decision_pack(evidence_store=store)
    assert loaded.public_data_ready is True
    assert loaded.public_data_ready_symbols == ("binance_usdm:BTCUSDT:l2_orderbook",)


def test_public_data_readiness_blockers_flow_to_decision_pack_missing_evidence():
    orch = _orchestrator_with_review()
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(rejection_reasons=("public_feed:stale",)))
    pack = orch.decision_pack()

    payload = decision_pack_to_dict(pack)
    missing = decision_pack_missing_evidence(pack)

    assert payload["public_data_ready"] is False
    assert payload["public_data_readiness_blockers"] == ["public_feed:stale"]
    assert missing["public_data_ready"] is False
    assert missing["public_data_readiness_blockers"] == ["public_feed:stale"]
    assert missing["details"]["public_data_readiness_blockers"] == ["public_feed:stale"]
    assert json.dumps(payload)


def test_old_decision_pack_payload_missing_public_data_fields_defaults_fail_closed():
    payload = decision_pack_to_dict(_pack(public_data_ready=True, public_data_ready_symbols=("x",)))
    for field_name in (
        "public_data_ready",
        "public_data_ready_symbols",
        "public_data_readiness_blockers",
        "public_data_readiness_snapshot_count",
    ):
        del payload[field_name]

    restored = decision_pack_from_dict(payload)

    assert restored.public_data_ready is False
    assert restored.public_data_ready_symbols == ()
    assert restored.public_data_readiness_blockers == ("public_data:readiness_snapshot_missing",)
    assert restored.public_data_readiness_snapshot_count == 0


def test_public_data_ready_true_with_blockers_loads_fail_closed():
    payload = decision_pack_to_dict(
        _pack(
            public_data_ready=True,
            public_data_ready_symbols=("binance_usdm:BTCUSDT:l2_orderbook",),
            public_data_readiness_blockers=("public_feed:stale",),
            public_data_readiness_snapshot_count=1,
        )
    )

    restored = decision_pack_from_dict(payload)

    assert restored.public_data_ready is False
    assert restored.public_data_readiness_blockers == ("public_feed:stale",)


def test_public_data_metadata_does_not_change_escalation_behavior():
    pack = _pack(
        readiness_level="tiny_cap_live",
        stage5_live_ready=True,
        stage5_live_readiness_blockers=(),
        public_data_ready=False,
        public_data_readiness_blockers=("public_feed:stale",),
    )

    decision = _orchestrator()._build_escalation_decision(pack)

    assert decision.escalation_stage == EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_public_data_readiness_does_not_enable_live_execution():
    orch = _orchestrator()
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot())
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert orch.operator_snapshot().trading_enabled is False
    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _orchestrator() -> ServiceOrchestrator:
    return ServiceOrchestrator(service=_Service(), readiness_level="paper_live")


def _orchestrator_with_review() -> ServiceOrchestrator:
    orchestrator = _orchestrator()
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


class _Service:
    def status(self):
        session = SimpleNamespace(current_cycle_time_ns=1_000, start_time_ns=1)
        runtime = SimpleNamespace(session_status=session)
        return SimpleNamespace(
            service_mode="paper",
            trading_enabled=False,
            blocked_reason=None,
            execution_intelligence=None,
            runtime_status=runtime,
            watchdog=None,
        )


@dataclass(frozen=True)
class _ReviewSnapshot:
    updated_at_ns: int = 303
    provisional_verdict: str = "promote"
    provisional_summary: str = "Promotion review supports candidate."
    campaign_ids: tuple[str, ...] = ("campaign-1",)
    campaign_count: int = 1
    ext_regime_quality: str = "supportive"
    ext_regime_governance: dict = field(default_factory=dict)
    verdict_distribution: dict = field(default_factory=dict)
    execution_sufficiency: dict = field(default_factory=dict)
    symbol_breadth: dict = field(default_factory=dict)
    insufficient_evidence: tuple[str, ...] = ()
    is_ready_to_finalize: bool = True


class _ReviewStatus:
    value = "active"


class _Review:
    campaign_count = 1
    final_report = None
    review_id = "review-21f"
    status = _ReviewStatus()
    is_finalized = False

    def current_snapshot(self) -> _ReviewSnapshot:
        return _ReviewSnapshot()

    def get_promotion_reason_summary(self) -> dict:
        return {
            "pass_reasons": ("promotion_review_supported",),
            "warning_reasons": (),
            "fail_reasons": (),
            "insufficient_reasons": (),
            "pass_count": 1,
            "warning_count": 0,
            "fail_count": 0,
            "insufficient_count": 0,
        }

    def get_missing_evidence(self) -> dict:
        return {
            "insufficient_criteria": [],
            "warning_criteria": [],
            "fail_criteria": [],
            "message": "Review evidence sufficient.",
        }


def _accepted_snapshot(
    *,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
) -> PublicDataReadinessSnapshot:
    return PublicDataReadinessSnapshot(
        venue_id=VenueId.BINANCE_USDM,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        order_book_ready=True,
        replay_ready=True,
        feed_gate_ready=True,
        accepted_for_paper=True,
        rejection_reasons=(),
        last_sequence_id=10,
        last_event_time_ns=1_000,
        last_receive_time_ns=1_001,
    )


def _rejected_snapshot(
    *,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
    rejection_reasons: tuple[str, ...] = ("public_feed:unhealthy",),
) -> PublicDataReadinessSnapshot:
    return PublicDataReadinessSnapshot(
        venue_id=VenueId.BINANCE_USDM,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        order_book_ready=False,
        replay_ready=True,
        feed_gate_ready=False,
        accepted_for_paper=False,
        rejection_reasons=rejection_reasons,
        last_sequence_id=10,
        last_event_time_ns=1_000,
        last_receive_time_ns=1_001,
    )


def _pack(
    *,
    readiness_level: str = "paper_live",
    stage5_live_ready: bool = False,
    stage5_live_readiness_blockers: tuple[str, ...] = (),
    public_data_ready: bool = False,
    public_data_ready_symbols: tuple[str, ...] = (),
    public_data_readiness_blockers: tuple[str, ...] = (),
    public_data_readiness_snapshot_count: int = 0,
) -> OperatorDecisionPack:
    return OperatorDecisionPack(
        artifact_time_ns=1,
        review_id="review-21f",
        review_timestamp_ns=1,
        review_status="active",
        promotion_verdict="promote",
        operator_disposition="promotable",
        decision_summary="phase21f decision pack",
        readiness_level=readiness_level,
        readiness_is_supportive=True,
        criteria_summary={"readiness": {"available": True}},
        pass_criteria=("promotion_review_supported",),
        stage5_live_ready=stage5_live_ready,
        stage5_live_ready_sleeve_ids=("sleeve-21f",) if stage5_live_ready else (),
        stage5_live_readiness_blockers=stage5_live_readiness_blockers,
        public_data_ready=public_data_ready,
        public_data_ready_symbols=public_data_ready_symbols,
        public_data_readiness_blockers=public_data_readiness_blockers,
        public_data_readiness_snapshot_count=public_data_readiness_snapshot_count,
        external_regime_quality="supportive",
        external_regime_evidence_available=True,
        external_regime_evidence_sufficient=True,
        external_regime_summary="External regime supportive.",
        reason_codes={"pass_count": 1, "warning_count": 0, "fail_count": 0, "insufficient_count": 0},
    )


def _edge_signal() -> EdgeSignal:
    return EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )


def _execution_request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=_edge_signal(),
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
