"""Tests for the validation-only secondary-metrics enforcement precondition bridge."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

import crypto_core.validation.paper_secondary_metrics_enforcement_precondition as precondition_module
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_secondary_metrics_enforcement_precondition import (
    PaperSecondaryMetricsEnforcementPreconditionError,
    PaperSecondaryMetricsEnforcementPreconditionStatus,
    build_paper_secondary_metrics_enforcement_precondition,
    paper_secondary_metrics_enforcement_precondition_digest,
    paper_secondary_metrics_enforcement_precondition_to_dict,
)
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    PaperSecondaryMetricsEvidenceStatus,
    build_paper_secondary_metrics_evidence,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliation,
    PaperSecondaryMetricsSubstrateReconciliationStatus,
    PaperSecondaryMetricsSubstrateRecordInput,
    build_paper_secondary_metrics_substrate_reconciliation,
    paper_secondary_metrics_substrate_reconciliation_digest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    build_secondary_metrics_policy,
    secondary_metrics_policy_digest,
)
from crypto_core.validation.trade_record_evidence import (
    build_trade_record_evidence,
)

_REASON_PREFIX = "paper_secondary_metrics_enforcement_precondition:"
_MARKET = "BTC-PERPETUAL"
_CORR = "corr-1"

_STRUCTURAL_FALSE_FLAGS = (
    "live_ready",
    "shadow_ready",
    "connector_ready",
    "orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "stage4_complete",
    "sm5_enabled",
    "sm6_enabled",
)

_uid_counter = [0]


def _uid(prefix: str) -> str:
    _uid_counter[0] += 1
    return f"{prefix}-{_uid_counter[0]}"


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _scale18(value: object) -> str:
    return format(Decimal(str(value)).quantize(Decimal("1E-18")), "f")


def _make_draft() -> PaperAllocatorIntentDraft:
    fields_map: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": "a" * 64,
        "promotion_readiness_journal_entry_digest": "a" * 64,
        "promotion_readiness_payload_digest": "a" * 64,
        "promotion_candidate_journal_entry_digest": "a" * 64,
        "decision_journal_entry_digest": "a" * 64,
        "decision_journal_payload_digest": "a" * 64,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields_map, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _order_intent(side: PaperOrderSide):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(),
        cap_policy,
        requested_notional="100000",
        requested_units="1",
        correlation_id="corr-capacity",
    )
    request = build_paper_order_intent_request(
        request_id=_uid("req"),
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=_MARKET,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id=_uid("intent"), correlation_id="corr-intent")


def _short_prior(*, avg: str = "100"):
    return build_paper_position_state(
        position_state_id=_uid("pos"),
        market_symbol=_MARKET,
        side=PaperPositionStateSide.SHORT,
        signed_units="-2",
        abs_units="2",
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-pos",
    )


def _snapshot(reference_price: str):
    return build_paper_fill_market_snapshot(
        snapshot_id=_uid("snap"),
        market_symbol=_MARKET,
        reference_price=reference_price,
    )


def _fill_policy():
    return build_paper_fill_policy(
        policy_id="fill-policy-1",
        slippage_bps="0",
        fee_rate_bps="0",
        allow_partial_fill=False,
    )


def _mark():
    return build_paper_mark_snapshot(
        mark_snapshot_id=_uid("mark"),
        market_symbol=_MARKET,
        mark_price="100",
        correlation_id="corr-mark",
    )


def _run_episode(intent, prior, snapshot, *, episode_id: str):
    ids: dict[str, object] = {
        "fill_simulation_id": _uid("fillsim"),
        "position_transition_id": _uid("trans"),
        "new_position_state_id": _uid("newpos"),
        "pnl_report_id": _uid("pnl"),
        "episode_run_id": episode_id,
        "correlation_id": _CORR,
    }
    episode = run_paper_episode(intent, prior, snapshot, _fill_policy(), _mark(), **ids)  # type: ignore[arg-type]
    fill_result = simulate_paper_fill(
        intent,
        snapshot,
        _fill_policy(),
        fill_simulation_id=ids["fill_simulation_id"],
        correlation_id=_CORR,
    )
    return episode, fill_result, ids


def _record_from(episode_id: str, record_id: str, fill_result, *, event, policy_id: str = "policy-1"):
    filled = Decimal(fill_result.filled_units)
    unfilled = Decimal(fill_result.unfilled_units)
    return build_trade_record_evidence(
        record_id=record_id,
        correlation_id=_CORR,
        sleeve_id="sleeve-1",
        policy_id=policy_id,
        episode_id=episode_id,
        strategy_id="strategy-1",
        decision_id=_uid("decision"),
        intended_quantity=_scale18(filled + unfilled),
        filled_quantity=_scale18(filled),
        expected_fill_price="100.000000000000000000",
        realized_fill_price=_scale18(fill_result.fill_price),
        realized_pnl=_scale18(event.realized_pnl),
        decided_episode=True,
    )


def _closing_bundle(episode_id: str, record_id: str, *, reference_price: str, policy_id: str = "policy-1"):
    prior = _short_prior()
    intent = _order_intent(PaperOrderSide.BUY)
    snapshot = _snapshot(reference_price)
    episode, fill_result, ids = _run_episode(intent, prior, snapshot, episode_id=episode_id)
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill_result,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=_CORR,
    )
    event = compute_paper_realized_pnl_event(
        prior,
        fill_result,
        transition,
        new_state,
        realized_pnl_event_id=_uid("rp"),
        correlation_id=_CORR,
    )
    record = _record_from(episode_id, record_id, fill_result, event=event, policy_id=policy_id)
    return episode, fill_result, event, record


def _policy(**overrides):
    payload = {
        "policy_id": "policy-1",
        "correlation_id": _CORR,
        "expected_fill_model_parameters_digest": "a" * 64,
        "approved_hit_rate_floor": "0.500000000000000000",
        "approved_fill_rate_floor": "0.900000000000000000",
        "approved_slippage_ceiling_bps": "25.000000000000000000",
        "approved_min_decided_episode_count": 1,
        "approval_reference": "gov-sm2-1",
        "approval_digest": "b" * 64,
        "thresholds_approved": True,
    }
    payload.update(overrides)
    return build_secondary_metrics_policy(**payload)  # type: ignore[arg-type]


class _Scenario:
    def __init__(self) -> None:
        self.policy = _policy()
        self.bundles = [
            _closing_bundle("ep-0", "rec-0", reference_price="95"),
            _closing_bundle("ep-1", "rec-1", reference_price="96"),
        ]
        self.inputs = [
            PaperSecondaryMetricsSubstrateRecordInput(record, episode, fill_result, event)
            for (episode, fill_result, event, record) in self.bundles
        ]
        self.records = [record for (_, _, _, record) in self.bundles]
        self.metrics = build_paper_secondary_metrics_evidence(
            self.policy,
            self.records,
            evidence_id="sm4-1",
            correlation_id=_CORR,
        )
        assert self.metrics.status is PaperSecondaryMetricsEvidenceStatus.METRICS_READY
        self.session = build_paper_session_sequence(
            [episode for (episode, _, _, _) in self.bundles],
            paper_session_id="ps-1",
            correlation_id=_CORR,
        )
        self.reconciliation = build_paper_secondary_metrics_substrate_reconciliation(
            self.policy,
            self.metrics,
            self.inputs,
            self.session,
            reconciliation_id="recon-1",
            correlation_id=_CORR,
            expected_policy_digest=self.policy.policy_digest,
            expected_metrics_evidence_digest=self.metrics.evidence_digest,
            expected_session_sequence_digest=self.session.paper_session_sequence_digest,
        )
        assert self.reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED

    def build(
        self,
        *,
        policy: SecondaryMetricsPolicy | None = None,
        metrics: PaperSecondaryMetricsEvidence | None = None,
        reconciliation: PaperSecondaryMetricsSubstrateReconciliation | None = None,
        **overrides: object,
    ):
        policy = self.policy if policy is None else policy
        metrics = self.metrics if metrics is None else metrics
        reconciliation = self.reconciliation if reconciliation is None else reconciliation
        payload: dict[str, object] = {
            "precondition_id": "precondition-1",
            "correlation_id": _CORR,
            "expected_policy_digest": policy.policy_digest,
            "expected_metrics_evidence_digest": metrics.evidence_digest,
            "expected_reconciliation_digest": reconciliation.reconciliation_digest,
        }
        payload.update(overrides)
        return build_paper_secondary_metrics_enforcement_precondition(
            policy,
            metrics,
            reconciliation,
            **payload,
        )


def _reseal_policy(policy: SecondaryMetricsPolicy, **overrides: object) -> SecondaryMetricsPolicy:
    seed = replace(policy, **overrides)  # type: ignore[arg-type]
    return replace(seed, policy_digest=secondary_metrics_policy_digest(seed))


def _reseal_metrics(
    evidence: PaperSecondaryMetricsEvidence,
    **overrides: object,
) -> PaperSecondaryMetricsEvidence:
    seed = replace(evidence, **overrides)  # type: ignore[arg-type]
    return replace(seed, evidence_digest=paper_secondary_metrics_evidence_digest(seed))


def _reseal_reconciliation(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
    **overrides: object,
) -> PaperSecondaryMetricsSubstrateReconciliation:
    seed = replace(reconciliation, **overrides)  # type: ignore[arg-type]
    return replace(seed, reconciliation_digest=paper_secondary_metrics_substrate_reconciliation_digest(seed))


def _bind_reconciliation_to_metrics(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
    metrics: PaperSecondaryMetricsEvidence,
) -> PaperSecondaryMetricsSubstrateReconciliation:
    return _reseal_reconciliation(reconciliation, verified_metrics_evidence_digest=metrics.evidence_digest)


def test_public_api_exact() -> None:
    assert set(precondition_module.__all__) == {
        "PaperSecondaryMetricsEnforcementPrecondition",
        "PaperSecondaryMetricsEnforcementPreconditionError",
        "PaperSecondaryMetricsEnforcementPreconditionStatus",
        "build_paper_secondary_metrics_enforcement_precondition",
        "paper_secondary_metrics_enforcement_precondition_digest",
        "paper_secondary_metrics_enforcement_precondition_to_dict",
    }


def test_happy_path_precondition_ready() -> None:
    scenario = _Scenario()
    precondition = scenario.build()
    payload = paper_secondary_metrics_enforcement_precondition_to_dict(precondition)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
    assert precondition.ready is True
    assert precondition.reason_codes == ()
    assert precondition.policy_digest == scenario.policy.policy_digest
    assert precondition.metrics_evidence_digest == scenario.metrics.evidence_digest
    assert precondition.reconciliation_digest == scenario.reconciliation.reconciliation_digest
    assert precondition.hit_rate_passed is True
    assert precondition.fill_rate_passed is True
    assert precondition.slippage_passed is True
    assert precondition.min_decided_episode_count_passed is True
    assert precondition.record_digests == scenario.metrics.record_digests
    assert payload["precondition_digest"] == paper_secondary_metrics_enforcement_precondition_digest(precondition)


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _Scenario().build().ready = False  # type: ignore[misc]


def test_serializer_matches_dataclass_fields_and_digest_excludes_self() -> None:
    precondition = _Scenario().build(metadata={"b": "2", "a": "1"})
    payload = paper_secondary_metrics_enforcement_precondition_to_dict(precondition)
    resealed = replace(precondition, precondition_digest="0" * 64)

    assert set(payload) == {field.name for field in fields(precondition)}
    assert payload["status"] == precondition.status.value
    assert payload["metadata"] == [["a", "1"], ["b", "2"]]
    assert paper_secondary_metrics_enforcement_precondition_digest(precondition) == precondition.precondition_digest
    assert paper_secondary_metrics_enforcement_precondition_digest(resealed) == precondition.precondition_digest


def test_deterministic_and_metadata_order_independent() -> None:
    scenario = _Scenario()
    first = scenario.build(metadata={"b": "2", "a": "1"})
    second = scenario.build(metadata={"a": "1", "b": "2"})
    changed = scenario.build(metadata={"a": "1", "b": "3"})

    assert first.precondition_digest == second.precondition_digest
    assert changed.precondition_digest != first.precondition_digest


def test_stale_policy_digest_rejects() -> None:
    precondition = _Scenario().build(expected_policy_digest="c" * 64)
    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("policy_digest_mismatch") in precondition.reason_codes


def test_stale_metrics_evidence_digest_rejects() -> None:
    precondition = _Scenario().build(expected_metrics_evidence_digest="c" * 64)
    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("metrics_evidence_digest_mismatch") in precondition.reason_codes


def test_stale_reconciliation_digest_rejects() -> None:
    precondition = _Scenario().build(expected_reconciliation_digest="c" * 64)
    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("reconciliation_digest_mismatch") in precondition.reason_codes


def test_policy_not_ready_rejects() -> None:
    scenario = _Scenario()
    rejected = _policy(thresholds_approved=False)
    precondition = scenario.build(policy=rejected)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("policy_not_ready") in precondition.reason_codes


def test_metrics_evidence_not_ready_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(
        scenario.metrics,
        status=PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED,
        ready=False,
        reason_codes=("paper_secondary_metrics_evidence:test_rejected",),
    )
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("metrics_evidence_not_ready") in precondition.reason_codes


def test_reconciliation_not_ready_rejects() -> None:
    scenario = _Scenario()
    reconciliation = _reseal_reconciliation(
        scenario.reconciliation,
        status=PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED,
        ready=False,
        reason_codes=("paper_secondary_metrics_substrate_reconciliation:test_rejected",),
    )
    precondition = scenario.build(reconciliation=reconciliation)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert _rc("reconciliation_not_ready") in precondition.reason_codes


def test_metrics_evidence_policy_mismatch_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, verified_policy_digest="c" * 64)
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("metrics_evidence_policy_mismatch") in precondition.reason_codes


def test_reconciliation_policy_mismatch_rejects() -> None:
    scenario = _Scenario()
    reconciliation = _reseal_reconciliation(scenario.reconciliation, verified_policy_digest="c" * 64)
    precondition = scenario.build(reconciliation=reconciliation)

    assert _rc("reconciliation_policy_mismatch") in precondition.reason_codes


def test_reconciliation_metrics_evidence_mismatch_rejects() -> None:
    scenario = _Scenario()
    reconciliation = _reseal_reconciliation(scenario.reconciliation, verified_metrics_evidence_digest="c" * 64)
    precondition = scenario.build(reconciliation=reconciliation)

    assert _rc("reconciliation_metrics_evidence_mismatch") in precondition.reason_codes


def test_record_set_count_mismatch_rejects() -> None:
    scenario = _Scenario()
    reconciliation = _reseal_reconciliation(
        scenario.reconciliation,
        reconciled_record_digests=scenario.reconciliation.reconciled_record_digests[:1],
    )
    precondition = scenario.build(reconciliation=reconciliation)

    assert _rc("record_set_mismatch") in precondition.reason_codes


def test_malformed_reconciliation_record_digest_container_rejects_without_crash() -> None:
    scenario = _Scenario()
    reconciliation = replace(
        scenario.reconciliation,
        reconciled_record_digests=None,  # type: ignore[arg-type]
    )
    precondition = scenario.build(reconciliation=reconciliation)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert precondition.reconciled_record_count == 0
    assert _rc("reconciliation_digest_mismatch") in precondition.reason_codes
    assert _rc("record_set_mismatch") in precondition.reason_codes


def test_hit_rate_floor_failure_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, hit_rate="0.000000000000000000")
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("hit_rate_floor_not_met") in precondition.reason_codes
    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_fill_rate_floor_failure_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, fill_rate_by_quantity="0.500000000000000000")
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("fill_rate_floor_not_met") in precondition.reason_codes
    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_slippage_ceiling_failure_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, average_slippage_bps="30.000000000000000000")
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("slippage_ceiling_exceeded") in precondition.reason_codes
    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_malformed_slippage_rejects_without_crash() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, average_slippage_bps="0.5")
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED
    assert precondition.computed_slippage_bps == "0.5"
    assert precondition.slippage_passed is False
    assert _rc("slippage_ceiling_exceeded") in precondition.reason_codes
    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_min_decided_episode_count_failure_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, decided_episode_count=0)
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("min_decided_episode_count_not_met") in precondition.reason_codes
    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_threshold_snapshot_mismatch_rejects() -> None:
    scenario = _Scenario()
    metrics = _reseal_metrics(scenario.metrics, approved_hit_rate_floor="0.400000000000000000")
    reconciliation = _bind_reconciliation_to_metrics(scenario.reconciliation, metrics)
    precondition = scenario.build(metrics=metrics, reconciliation=reconciliation)

    assert _rc("threshold_snapshot_mismatch") in precondition.reason_codes


def test_structural_non_claim_flags_are_fixed() -> None:
    precondition = _Scenario().build()
    payload = paper_secondary_metrics_enforcement_precondition_to_dict(precondition)

    assert payload["paper_only"] is True
    assert payload["validation_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False


def test_consumed_artifact_unsafe_flag_rejects() -> None:
    scenario = _Scenario()
    reconciliation = _reseal_reconciliation(scenario.reconciliation, stage4_complete=True)
    precondition = scenario.build(reconciliation=reconciliation)

    assert _rc("unsafe_flags") in precondition.reason_codes


@pytest.mark.parametrize("token", ["BIST", "KAP", "Matriks", "Borsa", "live", "stage4_complete", "sm5_enabled"])
def test_forbidden_metadata_or_id_token_raises(token: str) -> None:
    with pytest.raises(PaperSecondaryMetricsEnforcementPreconditionError):
        _Scenario().build(metadata={"token": token})


def test_wrong_type_artifact_raises() -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsEnforcementPreconditionError, match=_rc("policy_malformed")):
        build_paper_secondary_metrics_enforcement_precondition(
            object(),  # type: ignore[arg-type]
            scenario.metrics,
            scenario.reconciliation,
            precondition_id="precondition-1",
            correlation_id=_CORR,
            expected_policy_digest=scenario.policy.policy_digest,
            expected_metrics_evidence_digest=scenario.metrics.evidence_digest,
            expected_reconciliation_digest=scenario.reconciliation.reconciliation_digest,
        )


def test_no_comparator_runtime_or_sm5_sm6_imports_or_calls() -> None:
    source = Path(precondition_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "requests",
        "urllib",
        "threading",
        "asyncio",
        "subprocess",
        "os",
        "pathlib",
        "sqlite3",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
        "crypto_core.validation.paper_vs_backtest_methodology_v2",
        "crypto_core.validation.paper_stage4_comparison_evidence_v2",
    )
    forbidden_call_names = {
        "open",
        "float",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "compare_stage4",
        "Stage4PaperSummary",
        "Stage4BacktestBaseline",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == m or alias.name.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == m or node.module.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names


def test_structural_false_defaults_never_enable_sm5_sm6_or_stage4_completion() -> None:
    field_defaults = {
        field.name: field.default for field in fields(precondition_module.PaperSecondaryMetricsEnforcementPrecondition)
    }
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert field_defaults[flag] is False, flag
    assert field_defaults["paper_only"] is True
    assert field_defaults["validation_only"] is True
