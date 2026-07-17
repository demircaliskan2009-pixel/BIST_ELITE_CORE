"""Tests for the SM-5 paper-vs-backtest methodology-v2 snapshot bridge."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.paper_vs_backtest_methodology_v2 as methodology_v2_module
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
    PaperSecondaryMetricsEnforcementPrecondition,
    PaperSecondaryMetricsEnforcementPreconditionStatus,
    build_paper_secondary_metrics_enforcement_precondition,
    paper_secondary_metrics_enforcement_precondition_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    build_paper_secondary_metrics_evidence,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliation,
    PaperSecondaryMetricsSubstrateRecordInput,
    build_paper_secondary_metrics_substrate_reconciliation,
    paper_secondary_metrics_substrate_reconciliation_digest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    build_paper_vs_backtest_methodology,
    paper_vs_backtest_methodology_digest,
)
from crypto_core.validation.paper_vs_backtest_methodology_v2 import (
    PaperVsBacktestMethodologyV2,
    PaperVsBacktestMethodologyV2Error,
    PaperVsBacktestMethodologyV2Status,
    build_paper_vs_backtest_methodology_v2,
    paper_vs_backtest_methodology_v2_digest,
    paper_vs_backtest_methodology_v2_to_dict,
)
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    build_secondary_metrics_policy,
    secondary_metrics_policy_digest,
)
from crypto_core.validation.trade_record_evidence import build_trade_record_evidence

_REASON_PREFIX = "paper_vs_backtest_methodology_v2:"
_MARKET = "BTC-PERPETUAL"
_CORR = "corr-1"

_EXPECTED_FIELD_ORDER = (
    "schema_version",
    "methodology_version",
    "status",
    "ready",
    "methodology_id",
    "correlation_id",
    "predecessor_methodology_id",
    "secondary_metrics_policy_id",
    "secondary_metrics_enforcement_precondition_id",
    "market_symbol",
    "expected_predecessor_methodology_digest",
    "verified_predecessor_methodology_digest",
    "expected_secondary_metrics_policy_digest",
    "verified_secondary_metrics_policy_digest",
    "expected_secondary_metrics_enforcement_precondition_digest",
    "verified_secondary_metrics_enforcement_precondition_digest",
    "comparison_basis",
    "enforced_guardrail_policy",
    "secondary_guardrail_policy",
    "sharpe_retention_ratio",
    "min_duration_days",
    "risk_free_policy_id",
    "annualization_factor",
    "annualization_policy",
    "stddev_policy",
    "decimal_policy",
    "decimal_scale",
    "decimal_rounding",
    "decimal_internal_precision",
    "hit_rate_guardrail_policy",
    "fill_rate_guardrail_policy",
    "slippage_guardrail_policy",
    "drawdown_guardrail_policy",
    "hit_rate_definition",
    "fill_rate_definition",
    "slippage_definition",
    "hit_rate_operator",
    "fill_rate_operator",
    "slippage_operator",
    "expected_fill_model_reference",
    "expected_fill_model_parameters_digest",
    "secondary_metrics_decimal_policy",
    "secondary_metrics_decimal_scale",
    "secondary_metrics_decimal_rounding",
    "fraction_intermediates_required",
    "approved_hit_rate_floor",
    "approved_fill_rate_floor",
    "approved_slippage_ceiling_bps",
    "approved_min_decided_episode_count",
    "approval_reference",
    "approval_digest",
    "thresholds_approved",
    "hit_rate_floor_enforced",
    "fill_rate_floor_enforced",
    "slippage_ceiling_enforced",
    "reason_codes",
    "metadata",
    "methodology_digest",
    "paper_only",
    "methodology_snapshot",
    "policy_declared",
    "predecessor_methodology_consumed",
    "secondary_metrics_policy_consumed",
    "secondary_metrics_enforcement_precondition_consumed",
    "secondary_metrics_enforced",
    "drawdown_ceiling_enforced",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "comparison_performed",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "edge_identity_proven",
    "production_execution",
    "real_orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)

_ALWAYS_FALSE_FLAGS = (
    "secondary_metrics_enforced",
    "drawdown_ceiling_enforced",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "comparison_performed",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "edge_identity_proven",
    "production_execution",
    "real_orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)

_uid_counter = [0]


def _uid(prefix: str) -> str:
    _uid_counter[0] += 1
    return f"{prefix}-{_uid_counter[0]}"


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _scale18(value: object) -> str:
    from decimal import Decimal

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
    from decimal import Decimal

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


def _policy(**overrides) -> SecondaryMetricsPolicy:
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


def _predecessor(**overrides) -> PaperVsBacktestMethodology:
    payload = {
        "methodology_id": "meth-v1-1",
        "correlation_id": _CORR,
        "sharpe_retention_ratio": "0.500000000000000000",
        "min_duration_days": 30,
        "risk_free_policy_id": "constant_zero_daily_review_only.v1",
    }
    payload.update(overrides)
    return build_paper_vs_backtest_methodology(**payload)  # type: ignore[arg-type]


def _build_precondition(
    policy: SecondaryMetricsPolicy,
    metrics: PaperSecondaryMetricsEvidence,
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
) -> PaperSecondaryMetricsEnforcementPrecondition:
    return build_paper_secondary_metrics_enforcement_precondition(
        policy,
        metrics,
        reconciliation,
        precondition_id="precondition-1",
        correlation_id=_CORR,
        expected_policy_digest=policy.policy_digest,
        expected_metrics_evidence_digest=metrics.evidence_digest,
        expected_reconciliation_digest=reconciliation.reconciliation_digest,
    )


class _Chain:
    """Builds a complete READY anchor chain: predecessor v1 + policy + SM-4 + reconciliation + precondition."""

    def __init__(self) -> None:
        self.predecessor = _predecessor()
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
        self.precondition = _build_precondition(self.policy, self.metrics, self.reconciliation)


def _build_v2(
    chain: _Chain,
    *,
    predecessor=None,
    policy=None,
    precondition=None,
    **overrides,
) -> PaperVsBacktestMethodologyV2:
    predecessor = chain.predecessor if predecessor is None else predecessor
    policy = chain.policy if policy is None else policy
    precondition = chain.precondition if precondition is None else precondition
    payload: dict[str, object] = {
        "methodology_id": "sm5-1",
        "correlation_id": _CORR,
        "expected_predecessor_methodology_digest": (
            predecessor.methodology_digest if type(predecessor) is PaperVsBacktestMethodology else "0" * 64
        ),
        "expected_secondary_metrics_policy_digest": (
            policy.policy_digest if type(policy) is SecondaryMetricsPolicy else "0" * 64
        ),
        "expected_secondary_metrics_enforcement_precondition_digest": (
            precondition.precondition_digest
            if type(precondition) is PaperSecondaryMetricsEnforcementPrecondition
            else "0" * 64
        ),
    }
    payload.update(overrides)
    return build_paper_vs_backtest_methodology_v2(
        predecessor,
        policy,
        precondition,
        **payload,  # type: ignore[arg-type]
    )


def _reseal_predecessor(predecessor: PaperVsBacktestMethodology, **overrides) -> PaperVsBacktestMethodology:
    seed = replace(predecessor, **overrides)  # type: ignore[arg-type]
    return replace(seed, methodology_digest=paper_vs_backtest_methodology_digest(seed))


def _reseal_policy(policy: SecondaryMetricsPolicy, **overrides) -> SecondaryMetricsPolicy:
    seed = replace(policy, **overrides)  # type: ignore[arg-type]
    return replace(seed, policy_digest=secondary_metrics_policy_digest(seed))


def _reseal_metrics(metrics: PaperSecondaryMetricsEvidence, **overrides) -> PaperSecondaryMetricsEvidence:
    seed = replace(metrics, **overrides)  # type: ignore[arg-type]
    return replace(seed, evidence_digest=paper_secondary_metrics_evidence_digest(seed))


def _reseal_reconciliation(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation, **overrides
) -> PaperSecondaryMetricsSubstrateReconciliation:
    seed = replace(reconciliation, **overrides)  # type: ignore[arg-type]
    return replace(seed, reconciliation_digest=paper_secondary_metrics_substrate_reconciliation_digest(seed))


def _reseal_precondition(
    precondition: PaperSecondaryMetricsEnforcementPrecondition, **overrides
) -> PaperSecondaryMetricsEnforcementPrecondition:
    seed = replace(precondition, **overrides)  # type: ignore[arg-type]
    return replace(seed, precondition_digest=paper_secondary_metrics_enforcement_precondition_digest(seed))


# --------------------------------------------------------------------------------------------------
# Public contract and determinism
# --------------------------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert methodology_v2_module.__all__ == [
        "PaperVsBacktestMethodologyV2",
        "PaperVsBacktestMethodologyV2Error",
        "PaperVsBacktestMethodologyV2Status",
        "build_paper_vs_backtest_methodology_v2",
        "paper_vs_backtest_methodology_v2_digest",
        "paper_vs_backtest_methodology_v2_to_dict",
    ]
    assert [status.value for status in PaperVsBacktestMethodologyV2Status] == [
        "METHODOLOGY_READY",
        "METHODOLOGY_REJECTED",
    ]


def test_dataclass_field_order_exact() -> None:
    names = tuple(field.name for field in fields(PaperVsBacktestMethodologyV2))
    assert names == _EXPECTED_FIELD_ORDER
    assert len(names) == 98


def test_ready_contract_exact() -> None:
    result = _build_v2(_Chain())
    payload = paper_vs_backtest_methodology_v2_to_dict(result)

    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY
    assert result.ready is True
    assert result.reason_codes == ()
    assert result.schema_version == "paper-vs-backtest-methodology.v2"
    assert result.methodology_version == "paper-vs-backtest-methodology.v2"
    assert result.market_symbol == _MARKET
    assert result.secondary_guardrail_policy.endswith(".v2")
    assert result.hit_rate_operator == ">="
    assert result.fill_rate_operator == ">="
    assert result.slippage_operator == "<="
    assert result.approved_hit_rate_floor == "0.500000000000000000"
    assert result.approved_fill_rate_floor == "0.900000000000000000"
    assert result.approved_slippage_ceiling_bps == "25.000000000000000000"
    assert result.approved_min_decided_episode_count == 1
    assert result.thresholds_approved is True
    assert result.verified_predecessor_methodology_digest != ""
    assert result.verified_secondary_metrics_policy_digest != ""
    assert result.verified_secondary_metrics_enforcement_precondition_digest != ""
    assert payload["methodology_digest"] == paper_vs_backtest_methodology_v2_digest(result)


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _build_v2(_Chain()).ready = False  # type: ignore[misc]


def test_metadata_order_does_not_change_digest() -> None:
    chain = _Chain()
    first = _build_v2(chain, metadata={"b": "2", "a": "1"})
    second = _build_v2(chain, metadata={"a": "1", "b": "2"})
    changed = _build_v2(chain, metadata={"a": "1", "b": "3"})

    assert first.methodology_digest == second.methodology_digest
    assert changed.methodology_digest != first.methodology_digest


def test_serializer_is_fields_complete_and_excludes_only_self_digest() -> None:
    result = _build_v2(_Chain(), metadata={"b": "2", "a": "1"})
    payload = paper_vs_backtest_methodology_v2_to_dict(result)
    resealed = replace(result, methodology_digest="0" * 64)

    assert set(payload) == {field.name for field in fields(result)}
    assert payload["status"] == result.status.value
    assert payload["metadata"] == [["a", "1"], ["b", "2"]]
    assert payload["reason_codes"] == list(result.reason_codes)
    assert paper_vs_backtest_methodology_v2_digest(result) == result.methodology_digest
    assert paper_vs_backtest_methodology_v2_digest(resealed) == result.methodology_digest


def test_digest_is_deterministic() -> None:
    chain = _Chain()
    first = _build_v2(chain)
    second = _build_v2(chain)
    assert first.methodology_digest == second.methodology_digest
    assert first.methodology_digest == paper_vs_backtest_methodology_v2_digest(first)


# --------------------------------------------------------------------------------------------------
# Three-anchor digest triple reproof
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("anchor", ["predecessor", "policy", "precondition"])
@pytest.mark.parametrize("mode", ["stale_expected", "tampered_carried", "resealed"])
def test_anchor_digest_triple_mismatch_rejected(anchor: str, mode: str) -> None:
    chain = _Chain()
    expected_reason = {
        "predecessor": _rc("predecessor_methodology_digest_mismatch"),
        "policy": _rc("secondary_metrics_policy_digest_mismatch"),
        "precondition": _rc("secondary_metrics_enforcement_precondition_digest_mismatch"),
    }[anchor]
    verified_field = {
        "predecessor": "verified_predecessor_methodology_digest",
        "policy": "verified_secondary_metrics_policy_digest",
        "precondition": "verified_secondary_metrics_enforcement_precondition_digest",
    }[anchor]

    kwargs: dict[str, object] = {}
    if mode == "stale_expected":
        expected_arg = {
            "predecessor": "expected_predecessor_methodology_digest",
            "policy": "expected_secondary_metrics_policy_digest",
            "precondition": "expected_secondary_metrics_enforcement_precondition_digest",
        }[anchor]
        kwargs[expected_arg] = "c" * 64
        result = _build_v2(chain, **kwargs)
    elif mode == "tampered_carried":
        if anchor == "predecessor":
            kwargs["predecessor"] = replace(chain.predecessor, methodology_id="tampered-x")
        elif anchor == "policy":
            kwargs["policy"] = replace(chain.policy, policy_id="policy-1")  # digest unchanged, reseal below
            kwargs["policy"] = replace(chain.policy, approval_reference="tampered-x")
        else:
            kwargs["precondition"] = replace(chain.precondition, precondition_id="tampered-x")
        result = _build_v2(chain, **kwargs)
    else:  # resealed
        if anchor == "predecessor":
            resealed = _reseal_predecessor(chain.predecessor, methodology_id="resealed-x")
            result = _build_v2(
                chain,
                predecessor=resealed,
                expected_predecessor_methodology_digest=chain.predecessor.methodology_digest,
            )
        elif anchor == "policy":
            resealed = _reseal_policy(chain.policy, approval_reference="resealed-x")
            result = _build_v2(
                chain,
                policy=resealed,
                expected_secondary_metrics_policy_digest=chain.policy.policy_digest,
            )
        else:
            resealed = _reseal_precondition(chain.precondition, precondition_id="resealed-x")
            result = _build_v2(
                chain,
                precondition=resealed,
                expected_secondary_metrics_enforcement_precondition_digest=chain.precondition.precondition_digest,
            )

    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert expected_reason in result.reason_codes
    assert getattr(result, verified_field) == ""


# --------------------------------------------------------------------------------------------------
# Predecessor anchor
# --------------------------------------------------------------------------------------------------


def test_v1_v2_predecessor_substitution_raises() -> None:
    chain = _Chain()
    v2 = _build_v2(chain)
    with pytest.raises(PaperVsBacktestMethodologyV2Error, match=_rc("predecessor_methodology_malformed")):
        build_paper_vs_backtest_methodology_v2(
            v2,  # type: ignore[arg-type]
            chain.policy,
            chain.precondition,
            expected_predecessor_methodology_digest="a" * 64,
            expected_secondary_metrics_policy_digest=chain.policy.policy_digest,
            expected_secondary_metrics_enforcement_precondition_digest=chain.precondition.precondition_digest,
            methodology_id="sm5-1",
            correlation_id=_CORR,
        )


@pytest.mark.parametrize(
    "overrides,expected_reason",
    [
        ({"sharpe_retention_ratio": "0.400000000000000000"}, "predecessor_methodology_contract_mismatch"),
        ({"min_duration_days": 45}, "predecessor_methodology_contract_mismatch"),
        ({"enforced_guardrail_policy": "tampered.v1"}, "predecessor_methodology_contract_mismatch"),
        ({"hit_rate_floor_enforced": True}, "unsafe_flags"),
        ({"edge_proven": True}, "unsafe_flags"),
        ({"comparison_ready": True}, "unsafe_flags"),
    ],
)
def test_predecessor_governance_and_safe_flag_mutations_rejected(overrides, expected_reason) -> None:
    chain = _Chain()
    tampered = _reseal_predecessor(chain.predecessor, **overrides)
    result = _build_v2(
        chain,
        predecessor=tampered,
        expected_predecessor_methodology_digest=tampered.methodology_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc(expected_reason) in result.reason_codes


def test_predecessor_not_ready_rejected() -> None:
    chain = _Chain()
    tampered = _reseal_predecessor(
        chain.predecessor,
        ready=False,
        reason_codes=("paper_vs_backtest_methodology:test_rejected",),
    )
    result = _build_v2(
        chain,
        predecessor=tampered,
        expected_predecessor_methodology_digest=tampered.methodology_digest,
    )
    assert _rc("predecessor_methodology_not_ready") in result.reason_codes


# --------------------------------------------------------------------------------------------------
# Policy anchor
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,expected_reason",
    [
        ({"hit_rate_definition": "tampered.v1"}, "secondary_metrics_policy_contract_mismatch"),
        ({"expected_fill_model_reference": "tampered.v1"}, "secondary_metrics_policy_contract_mismatch"),
        ({"decimal_policy": "tampered.v1"}, "secondary_metrics_policy_contract_mismatch"),
        ({"fraction_intermediates_required": False}, "secondary_metrics_policy_contract_mismatch"),
        ({"approval_digest": "z" * 64}, "secondary_metrics_policy_contract_mismatch"),
        ({"approved_hit_rate_floor": "1.500000000000000000"}, "secondary_metrics_policy_contract_mismatch"),
        ({"edge_proven": True}, "unsafe_flags"),
        ({"comparator_invoked": True}, "unsafe_flags"),
    ],
)
def test_policy_definition_fill_model_decimal_fraction_approval_threshold_and_safe_flag_mutations_rejected(
    overrides, expected_reason
) -> None:
    chain = _Chain()
    tampered = _reseal_policy(chain.policy, **overrides)
    result = _build_v2(
        chain,
        policy=tampered,
        expected_secondary_metrics_policy_digest=tampered.policy_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc(expected_reason) in result.reason_codes


def test_policy_precondition_id_digest_and_correlation_substitution_rejected() -> None:
    chain = _Chain()

    id_mismatch = _reseal_precondition(chain.precondition, policy_id="policy-other")
    result = _build_v2(
        chain,
        precondition=id_mismatch,
        expected_secondary_metrics_enforcement_precondition_digest=id_mismatch.precondition_digest,
    )
    assert _rc("policy_binding_mismatch") in result.reason_codes

    digest_mismatch = _reseal_precondition(chain.precondition, policy_digest="d" * 64)
    result = _build_v2(
        chain,
        precondition=digest_mismatch,
        expected_secondary_metrics_enforcement_precondition_digest=digest_mismatch.precondition_digest,
    )
    assert _rc("policy_binding_mismatch") in result.reason_codes

    corr_mismatch = _reseal_precondition(chain.precondition, correlation_id="corr-other")
    result = _build_v2(
        chain,
        precondition=corr_mismatch,
        expected_secondary_metrics_enforcement_precondition_digest=corr_mismatch.precondition_digest,
    )
    assert _rc("correlation_id_mismatch") in result.reason_codes


# --------------------------------------------------------------------------------------------------
# Precondition anchor
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,expected_reason",
    [
        ({"schema_version": "tampered.v1"}, "secondary_metrics_enforcement_precondition_contract_mismatch"),
        ({"metrics_evidence_digest": "not-hex"}, "secondary_metrics_enforcement_precondition_contract_mismatch"),
        ({"stage4_complete": True}, "unsafe_flags"),
        ({"sm5_enabled": True}, "unsafe_flags"),
    ],
)
def test_precondition_schema_status_reason_nested_digest_and_safe_flag_mutations_rejected(
    overrides, expected_reason
) -> None:
    chain = _Chain()
    tampered = _reseal_precondition(chain.precondition, **overrides)
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=tampered.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc(expected_reason) in result.reason_codes


def test_precondition_not_ready_rejected() -> None:
    chain = _Chain()
    tampered = _reseal_precondition(
        chain.precondition,
        status=PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_REJECTED,
        ready=False,
        reason_codes=("paper_secondary_metrics_enforcement_precondition:test_rejected",),
    )
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=tampered.precondition_digest,
    )
    assert _rc("secondary_metrics_enforcement_precondition_not_ready") in result.reason_codes


# --------------------------------------------------------------------------------------------------
# Threshold echo / pass coherence / record-set coherence
# --------------------------------------------------------------------------------------------------


def test_threshold_echo_and_pass_computed_value_incoherence_rejected() -> None:
    chain = _Chain()

    echo_mismatch = _reseal_precondition(chain.precondition, approved_hit_rate_floor="0.400000000000000000")
    result = _build_v2(
        chain,
        precondition=echo_mismatch,
        expected_secondary_metrics_enforcement_precondition_digest=echo_mismatch.precondition_digest,
    )
    assert _rc("threshold_snapshot_mismatch") in result.reason_codes

    pass_incoherent = _reseal_precondition(chain.precondition, hit_rate_passed=False)
    result = _build_v2(
        chain,
        precondition=pass_incoherent,
        expected_secondary_metrics_enforcement_precondition_digest=pass_incoherent.precondition_digest,
    )
    assert _rc("threshold_pass_incoherent") in result.reason_codes


def test_none_slippage_preserves_current_sm5_precondition_semantics() -> None:
    chain = _Chain()
    metrics = _reseal_metrics(chain.metrics, average_slippage_bps=None)
    reconciliation = _reseal_reconciliation(
        chain.reconciliation, verified_metrics_evidence_digest=metrics.evidence_digest
    )
    precondition = _build_precondition(chain.policy, metrics, reconciliation)
    assert precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
    assert precondition.computed_slippage_bps is None

    result = _build_v2(chain, precondition=precondition)
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY
    assert result.slippage_ceiling_enforced is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"record_digests": ("z" * 64,)},
        {"metrics_record_count": 99},
        {"reconciled_record_count": 99},
        {"reconciled_episode_count": 99},
    ],
)
def test_record_digest_container_hex_order_duplicate_and_count_incoherence_rejected(overrides) -> None:
    chain = _Chain()
    tampered = _reseal_precondition(chain.precondition, **overrides)
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=tampered.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc("record_set_incoherent") in result.reason_codes


def test_non_tuple_record_digest_container_rejects_without_crash() -> None:
    # A non-tuple record-digest container leaves the precondition self-digest stale (the anchor digest
    # reproof cannot iterate it), so BOTH the digest reproof and the record-set coherence fail closed.
    chain = _Chain()
    tampered = replace(chain.precondition, record_digests=None)  # type: ignore[arg-type]
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=chain.precondition.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc("record_set_incoherent") in result.reason_codes
    assert _rc("secondary_metrics_enforcement_precondition_digest_mismatch") in result.reason_codes


def test_record_digest_unsorted_and_duplicate_rejected() -> None:
    chain = _Chain()
    ordered = chain.precondition.record_digests
    assert len(ordered) == 2

    unsorted = _reseal_precondition(chain.precondition, record_digests=tuple(reversed(ordered)))
    result = _build_v2(
        chain,
        precondition=unsorted,
        expected_secondary_metrics_enforcement_precondition_digest=unsorted.precondition_digest,
    )
    assert _rc("record_set_incoherent") in result.reason_codes

    duplicate = _reseal_precondition(
        chain.precondition,
        record_digests=(ordered[0], ordered[0]),
    )
    result = _build_v2(
        chain,
        precondition=duplicate,
        expected_secondary_metrics_enforcement_precondition_digest=duplicate.precondition_digest,
    )
    assert _rc("record_set_incoherent") in result.reason_codes


def test_decided_count_may_be_less_than_record_count_but_cannot_exceed_it() -> None:
    chain = _Chain()

    fewer_decided = _reseal_precondition(chain.precondition, computed_decided_episode_count=1)
    result = _build_v2(
        chain,
        precondition=fewer_decided,
        expected_secondary_metrics_enforcement_precondition_digest=fewer_decided.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY

    too_many_decided = _reseal_precondition(chain.precondition, computed_decided_episode_count=3)
    result = _build_v2(
        chain,
        precondition=too_many_decided,
        expected_secondary_metrics_enforcement_precondition_digest=too_many_decided.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc("record_set_incoherent") in result.reason_codes


# --------------------------------------------------------------------------------------------------
# Enforcement / no-overclaim flags
# --------------------------------------------------------------------------------------------------


def test_ready_and_rejected_enforcement_flags_exact() -> None:
    chain = _Chain()

    ready = _build_v2(chain)
    assert ready.hit_rate_floor_enforced is True
    assert ready.fill_rate_floor_enforced is True
    assert ready.slippage_ceiling_enforced is True
    assert ready.predecessor_methodology_consumed is True
    assert ready.secondary_metrics_policy_consumed is True
    assert ready.secondary_metrics_enforcement_precondition_consumed is True
    assert ready.paper_only is True
    assert ready.methodology_snapshot is True
    assert ready.policy_declared is True

    rejected = _build_v2(chain, expected_secondary_metrics_policy_digest="c" * 64)
    assert rejected.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert rejected.hit_rate_floor_enforced is False
    assert rejected.fill_rate_floor_enforced is False
    assert rejected.slippage_ceiling_enforced is False
    assert rejected.predecessor_methodology_consumed is False
    assert rejected.secondary_metrics_policy_consumed is False
    assert rejected.secondary_metrics_enforcement_precondition_consumed is False
    # Structural declaration flags stay True on both paths.
    assert rejected.paper_only is True
    assert rejected.methodology_snapshot is True
    assert rejected.policy_declared is True


def test_secondary_metrics_enforced_always_false() -> None:
    chain = _Chain()
    ready = _build_v2(chain)
    rejected = _build_v2(chain, expected_secondary_metrics_policy_digest="c" * 64)
    assert ready.secondary_metrics_enforced is False
    assert rejected.secondary_metrics_enforced is False


def test_all_nonclaim_flags_always_false() -> None:
    chain = _Chain()
    ready = paper_vs_backtest_methodology_v2_to_dict(_build_v2(chain))
    rejected = paper_vs_backtest_methodology_v2_to_dict(
        _build_v2(chain, expected_secondary_metrics_policy_digest="c" * 64)
    )
    for flag in _ALWAYS_FALSE_FLAGS:
        assert ready[flag] is False, flag
        assert rejected[flag] is False, flag


# --------------------------------------------------------------------------------------------------
# RAISE vs REJECTED boundary and scope
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"methodology_id": ""}, "methodology_id_malformed"),
        ({"methodology_id": " leading"}, "methodology_id_malformed"),
        ({"correlation_id": ""}, "correlation_id_malformed"),
        ({"expected_predecessor_methodology_digest": "z" * 64}, "expected_predecessor_methodology_digest_malformed"),
        ({"expected_secondary_metrics_policy_digest": "short"}, "expected_secondary_metrics_policy_digest_malformed"),
        (
            {"expected_secondary_metrics_enforcement_precondition_digest": "Z" * 64},
            "expected_secondary_metrics_enforcement_precondition_digest_malformed",
        ),
        ({"metadata": {"k": "\n"}}, "metadata_malformed"),
    ],
)
def test_malformed_caller_input_raises_but_untrusted_anchor_rejects(overrides, match) -> None:
    chain = _Chain()
    with pytest.raises(PaperVsBacktestMethodologyV2Error, match=_rc(match)):
        _build_v2(chain, **overrides)

    # An untrusted anchor (stale expected digest) never raises: it fails closed to REJECTED.
    rejected = _build_v2(chain, expected_predecessor_methodology_digest="c" * 64)
    assert rejected.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED


@pytest.mark.parametrize(
    "token,match",
    [
        ("BIST", "bist_token_forbidden"),
        ("borsa istanbul", "bist_token_forbidden"),
        ("live_order", "scope_violation"),
        ("connector_ready", "scope_violation"),
        ("wall_clock", "clock_token_forbidden"),
    ],
)
def test_caller_scope_bist_clock_raises(token, match) -> None:
    chain = _Chain()
    with pytest.raises(PaperVsBacktestMethodologyV2Error, match=_rc(match)):
        _build_v2(chain, metadata={"note": token})


def test_anchor_carried_scope_reseal_rejects() -> None:
    chain = _Chain()
    tampered = _reseal_precondition(chain.precondition, precondition_id="deribit_ready_bridge")
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=tampered.precondition_digest,
    )
    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc("anchor_scope_violation") in result.reason_codes


# --------------------------------------------------------------------------------------------------
# Boundary: builder signature, comparator, and forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_builder_signature_has_no_governance_operator_sm4_or_reconciliation_argument() -> None:
    signature = inspect.signature(build_paper_vs_backtest_methodology_v2)
    names = tuple(signature.parameters)
    assert names == (
        "predecessor_methodology",
        "secondary_metrics_policy",
        "enforcement_precondition",
        "expected_predecessor_methodology_digest",
        "expected_secondary_metrics_policy_digest",
        "expected_secondary_metrics_enforcement_precondition_digest",
        "methodology_id",
        "correlation_id",
        "metadata",
    )
    forbidden_fragments = (
        "approved_",
        "operator",
        "threshold",
        "hit_rate",
        "fill_rate",
        "slippage",
        "sm4",
        "evidence",
        "reconciliation",
        "comparator",
        "baseline",
        "readiness",
    )
    for name in names:
        assert not any(fragment in name for fragment in forbidden_fragments), name


def test_compare_stage4_echo_cannot_satisfy_methodology_v2() -> None:
    result = _build_v2(_Chain())
    # Even a READY methodology-v2 never claims comparison or comparator invocation.
    assert result.comparison_ready is False
    assert result.paper_vs_backtest_comparison_ready is False
    assert result.comparison_performed is False
    assert result.stage4_comparator_invoked is False
    assert result.stage4_completion_decided is False
    assert result.prdv4_stage4_complete is False

    # The comparator surface may appear only inside the defensive scope-guard regex (as a BLOCKED token),
    # never as an import or a call. Prove that structurally rather than by raw substring.
    source = Path(methodology_v2_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    comparator_surfaces = {"compare_stage4", "Stage4PaperSummary", "Stage4BacktestBaseline"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in comparator_surfaces, function.id
            if isinstance(function, ast.Attribute):
                assert function.attr not in comparator_surfaces, function.attr
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
            for name in imported:
                assert not any(surface in name for surface in comparator_surfaces), name
                assert "stage4_comparator" not in name, name
                assert "paper_stage4_comparison_evidence" not in name, name


def test_ast_forbids_comparator_sm4_reconciliation_filesystem_network_clock_random_subprocess_runtime_private_order_live_and_capital_surfaces() -> (
    None
):
    source = Path(methodology_v2_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "os",
        "io",
        "pathlib",
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "ssl",
        "requests",
        "urllib",
        "http",
        "threading",
        "asyncio",
        "subprocess",
        "sqlite3",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
        "crypto_core.validation.paper_stage4_comparison_evidence",
        "crypto_core.validation.paper_stage4_comparison_evidence_v2",
        "crypto_core.validation.paper_stage4_completion_decision_v2",
        "crypto_core.validation.paper_secondary_metrics_evidence",
        "crypto_core.validation.paper_secondary_metrics_substrate_reconciliation",
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
        "system",
        "getenv",
        "eval",
        "exec",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                ), alias.name
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            ), node.module
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names, function.id
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names, function.attr


# --------------------------------------------------------------------------------------------------
# Anchor-carried metadata scope scan (PR #334 review repair)
# --------------------------------------------------------------------------------------------------


def _resealed_chain_with_anchor_metadata(chain: _Chain, anchor: str, metadata: tuple[tuple[str, str], ...]):
    """Build a fully coherent digest-valid chain where exactly one anchor carries the given metadata.

    Every reseal recomputes the anchor's public self-digest and rebinds every downstream digest reference
    (policy digest into the precondition), so all three digest triples pass and the metadata content is the
    ONLY difference from a READY chain. Returns the v2 build result.
    """

    if anchor == "predecessor":
        tampered = _reseal_predecessor(chain.predecessor, metadata=metadata)
        return _build_v2(
            chain,
            predecessor=tampered,
            expected_predecessor_methodology_digest=tampered.methodology_digest,
        )
    if anchor == "policy":
        tampered_policy = _reseal_policy(chain.policy, metadata=metadata)
        rebound_precondition = _reseal_precondition(chain.precondition, policy_digest=tampered_policy.policy_digest)
        return _build_v2(
            chain,
            policy=tampered_policy,
            precondition=rebound_precondition,
            expected_secondary_metrics_policy_digest=tampered_policy.policy_digest,
            expected_secondary_metrics_enforcement_precondition_digest=rebound_precondition.precondition_digest,
        )
    tampered = _reseal_precondition(chain.precondition, metadata=metadata)
    return _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=tampered.precondition_digest,
    )


@pytest.mark.parametrize("position", ["key", "value"])
@pytest.mark.parametrize(
    "token",
    ["bist_authority", "deribit_ready", "datetime.now"],
    ids=["bist", "scope", "clock"],
)
@pytest.mark.parametrize("anchor", ["predecessor", "policy", "precondition"])
def test_anchor_metadata_bist_scope_clock_key_and_value_rejected(anchor: str, token: str, position: str) -> None:
    """The exact review exploit: a coherent resealed anchor smuggling forbidden metadata must fail closed.

    ``reason_codes`` is asserted to be EXACTLY the anchor-scope reason, which simultaneously proves that all
    three digest triples passed (a digest mismatch is NOT why the attack is rejected) and that pre-repair —
    without the metadata scan — this chain would have reached METHODOLOGY_READY.
    """

    chain = _Chain()
    metadata = ((token, "x"),) if position == "key" else (("note", token),)
    result = _resealed_chain_with_anchor_metadata(chain, anchor, metadata)

    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert result.ready is False
    assert result.reason_codes == (_rc("anchor_scope_violation"),)
    # Digest triples passed before scope rejection: every verified digest is populated.
    assert result.verified_predecessor_methodology_digest != ""
    assert result.verified_secondary_metrics_policy_digest != ""
    assert result.verified_secondary_metrics_enforcement_precondition_digest != ""
    assert result.predecessor_methodology_consumed is False
    assert result.secondary_metrics_policy_consumed is False
    assert result.secondary_metrics_enforcement_precondition_consumed is False
    assert result.hit_rate_floor_enforced is False
    assert result.fill_rate_floor_enforced is False
    assert result.slippage_ceiling_enforced is False
    assert result.secondary_metrics_enforced is False
    payload = paper_vs_backtest_methodology_v2_to_dict(result)
    for flag in _ALWAYS_FALSE_FLAGS:
        assert payload[flag] is False, flag


def test_safe_resealed_anchor_metadata_still_ready() -> None:
    # Control experiment: the identical reseal construction with SAFE metadata in all three anchors still
    # reaches METHODOLOGY_READY — the attack matrix above is rejected for its tokens, not its mechanism.
    chain = _Chain()
    safe = (("note", "governance snapshot"),)
    predecessor = _reseal_predecessor(chain.predecessor, metadata=safe)
    policy = _reseal_policy(chain.policy, metadata=safe)
    precondition = _reseal_precondition(chain.precondition, metadata=safe, policy_digest=policy.policy_digest)
    result = _build_v2(
        chain,
        predecessor=predecessor,
        policy=policy,
        precondition=precondition,
        expected_predecessor_methodology_digest=predecessor.methodology_digest,
        expected_secondary_metrics_policy_digest=policy.policy_digest,
        expected_secondary_metrics_enforcement_precondition_digest=precondition.precondition_digest,
    )

    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY
    assert result.ready is True
    assert result.reason_codes == ()
    assert result.hit_rate_floor_enforced is True
    assert result.fill_rate_floor_enforced is True
    assert result.slippage_ceiling_enforced is True
    assert result.secondary_metrics_enforced is False


@pytest.mark.parametrize("position", ["key", "value"])
@pytest.mark.parametrize(
    "token,match",
    [
        ("bist_authority", "bist_token_forbidden"),
        ("deribit_ready", "scope_violation"),
        ("datetime.now", "clock_token_forbidden"),
    ],
    ids=["bist", "scope", "clock"],
)
def test_caller_metadata_with_attack_tokens_still_raises(token: str, match: str, position: str) -> None:
    # The caller-owned boundary is unchanged by the repair: the same tokens RAISE when caller-supplied.
    chain = _Chain()
    metadata = {token: "x"} if position == "key" else {"note": token}
    with pytest.raises(PaperVsBacktestMethodologyV2Error, match=_rc(match)):
        _build_v2(chain, metadata=metadata)


def test_malformed_anchor_metadata_container_rejects_without_crash() -> None:
    # A non-tuple anchor metadata container must not crash the scan; the anchor already fails its digest
    # reproof (the serializer cannot iterate the container), so the chain fails closed to REJECTED.
    chain = _Chain()
    tampered = replace(chain.precondition, metadata=None)  # type: ignore[arg-type]
    result = _build_v2(
        chain,
        precondition=tampered,
        expected_secondary_metrics_enforcement_precondition_digest=chain.precondition.precondition_digest,
    )

    assert result.status is PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    assert _rc("secondary_metrics_enforcement_precondition_digest_mismatch") in result.reason_codes
