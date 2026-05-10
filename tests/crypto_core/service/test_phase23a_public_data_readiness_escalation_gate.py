from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from crypto_core.data.public_data_readiness import PublicDataReadinessSnapshot
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
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
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_missing_public_data_readiness_snapshot_creates_blocker():
    payload = _orchestrator_with_review().combined_status_dict()

    assert payload["public_data_ready"] is False
    assert payload["public_data_readiness_blockers"] == ["public_data:readiness_snapshot_missing"]
    assert payload["public_data_readiness_snapshot_count"] == 0


def test_missing_public_data_snapshot_prevents_higher_escalation():
    decision = _decision(_pack(public_data_readiness_blockers=("public_data:readiness_snapshot_missing",)))

    assert decision.escalation_stage == EscalationStage.PAPER_ONLY
    assert decision.escalation_stage not in {
        EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE,
        EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE,
    }
    assert "public_data:readiness_snapshot_missing" in decision.blocking_reasons


def test_missing_snapshot_appears_in_why_not_higher_surface():
    decision = _decision(_pack(public_data_readiness_blockers=("public_data:readiness_snapshot_missing",)))

    assert "public_data:readiness_snapshot_missing" in decision.why_not_higher
    assert "public_data_readiness" in decision.revalidation_required
    assert "public_data:readiness_snapshot_missing" in decision.missing_evidence


def test_missing_snapshot_appears_in_decision_pack_missing_evidence_summary():
    pack = _orchestrator_with_review().decision_pack()
    missing = decision_pack_missing_evidence(pack)

    assert missing["public_data_ready"] is False
    assert missing["public_data_readiness_blockers"] == ["public_data:readiness_snapshot_missing"]
    assert missing["details"]["public_data_readiness_blockers"] == ["public_data:readiness_snapshot_missing"]
    assert "public_data:readiness_snapshot_missing" in pack.why_not_promotable


def test_rejected_public_data_snapshot_propagates_blockers():
    orch = _orchestrator_with_review(readiness_level="tiny_cap_live")
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(rejection_reasons=("public_feed:stale",)))

    pack = orch.decision_pack()
    decision = orch.escalation_decision()

    assert pack.public_data_ready is False
    assert pack.public_data_readiness_blockers == ("public_feed:stale",)
    assert "public_feed:stale" in decision.blocking_reasons
    assert "public_feed:stale" in decision.why_not_higher


def test_rejected_public_data_snapshot_prevents_higher_escalation():
    decision = _decision(
        _pack(
            public_data_ready=False,
            public_data_readiness_blockers=("public_feed:stale",),
            public_data_readiness_snapshot_count=1,
        )
    )

    assert decision.escalation_stage == EscalationStage.PAPER_ONLY
    assert decision.escalation_stage != EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_accepted_public_data_readiness_preserves_previous_escalation_behavior():
    decision = _decision(
        _pack(
            public_data_ready=True,
            public_data_ready_symbols=("binance_usdm:BTCUSDT:l2_orderbook",),
            public_data_readiness_blockers=(),
            public_data_readiness_snapshot_count=1,
        )
    )

    assert decision.escalation_stage == EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE
    assert decision.blocking_reasons == ()


def test_mixed_snapshots_any_rejected_snapshot_blocks_pack_readiness():
    orch = _orchestrator_with_review(readiness_level="tiny_cap_live")
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))
    orch.apply_public_data_readiness_snapshot(
        _rejected_snapshot(symbol="BTCUSDT", rejection_reasons=("public_feed:stale",))
    )

    pack = orch.decision_pack()
    decision = orch.escalation_decision()

    assert pack.public_data_ready is False
    assert pack.public_data_ready_symbols == ("binance_usdm:ETHUSDT:l2_orderbook",)
    assert pack.public_data_readiness_blockers == ("public_feed:stale",)
    assert decision.escalation_stage == EscalationStage.PAPER_ONLY


def test_public_data_ready_symbols_and_blockers_are_deterministically_ordered():
    orch = _orchestrator()
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(symbol="SOLUSDT", rejection_reasons=("z_blocker",)))
    orch.apply_public_data_readiness_snapshot(_accepted_snapshot(symbol="BTCUSDT"))
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(symbol="ADAUSDT", rejection_reasons=("a_blocker",)))

    payload = orch.combined_status_dict()

    assert payload["public_data_ready_symbols"] == [
        "binance_usdm:BTCUSDT:l2_orderbook",
        "binance_usdm:ETHUSDT:l2_orderbook",
    ]
    assert payload["public_data_readiness_blockers"] == ["a_blocker", "z_blocker"]


def test_json_export_load_roundtrip_preserves_public_data_readiness_blockers(tmp_path):
    orch = _orchestrator_with_review()
    orch.apply_public_data_readiness_snapshot(_rejected_snapshot(rejection_reasons=("public_feed:stale",)))
    pack = orch.decision_pack()
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())

    result = export_operator_decision_pack(pack=pack, evidence_store=store)
    loaded = load_operator_decision_pack(evidence_store=store)

    assert result.success is True
    assert loaded.public_data_ready is False
    assert loaded.public_data_readiness_blockers == ("public_feed:stale",)
    assert json.dumps(decision_pack_to_dict(loaded))


def test_old_payload_without_public_data_fields_fails_closed():
    payload = decision_pack_to_dict(
        _pack(
            public_data_ready=True,
            public_data_ready_symbols=("binance_usdm:BTCUSDT:l2_orderbook",),
            public_data_readiness_snapshot_count=1,
        )
    )
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
    assert restored.public_data_readiness_blockers == ()
    assert restored.public_data_readiness_snapshot_count == 0


def test_stage5_live_ready_logic_remains_unchanged_when_public_data_is_ready():
    not_ready = _decision(
        _pack(stage5_live_ready=False, public_data_ready=True, public_data_readiness_snapshot_count=1)
    )
    ready = _decision(_pack(stage5_live_ready=True, public_data_ready=True, public_data_readiness_snapshot_count=1))

    assert not_ready.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
    assert ready.escalation_stage == EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_lifecycle_and_execution_live_modes_remain_rejected():
    lifecycle = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(
        _execution_request()
    )
    execution = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert lifecycle.approved is False
    assert lifecycle.rejection_reason == RejectionReason.LIVE_NOT_ENABLED
    assert execution.allowed is False
    assert execution.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_no_network_connector_client_imports_introduced():
    forbidden_imports = {"requests", "httpx", "aiohttp", "websocket", "urllib"}
    for path in (
        Path("src/crypto_core/service/service_orchestrator.py"),
        Path("src/crypto_core/service/artifact_export.py"),
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert forbidden_imports.isdisjoint(imports)


def test_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == ()


def test_deribit_public_connector_readiness_remains_blocked():
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def _orchestrator(*, readiness_level: str = "paper_live") -> ServiceOrchestrator:
    return ServiceOrchestrator(service=_Service(), readiness_level=readiness_level)


def _orchestrator_with_review(*, readiness_level: str = "paper_live") -> ServiceOrchestrator:
    orchestrator = _orchestrator(readiness_level=readiness_level)
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _decision(pack: OperatorDecisionPack):
    return _orchestrator()._build_escalation_decision(pack)


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
    review_id = "review-23a"
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
    readiness_level: str = "tiny_cap_live",
    stage5_live_ready: bool = True,
    stage5_live_readiness_blockers: tuple[str, ...] = (),
    public_data_ready: bool = False,
    public_data_ready_symbols: tuple[str, ...] = (),
    public_data_readiness_blockers: tuple[str, ...] = (),
    public_data_readiness_snapshot_count: int = 0,
) -> OperatorDecisionPack:
    return OperatorDecisionPack(
        artifact_time_ns=1,
        review_id="review-23a",
        review_timestamp_ns=1,
        review_status="active",
        promotion_verdict="promote",
        operator_disposition="promotable",
        decision_summary="phase23a decision pack",
        readiness_level=readiness_level,
        readiness_is_supportive=True,
        criteria_summary={"readiness": {"available": True}},
        pass_criteria=("promotion_review_supported",),
        stage5_live_ready=stage5_live_ready,
        stage5_live_ready_sleeve_ids=("sleeve-23a",) if stage5_live_ready else (),
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
