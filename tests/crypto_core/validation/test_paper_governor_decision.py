"""Tests for the paper governor decision — deterministic, paper-only, fail-closed governance verdict over a
READY ``PaperAdmissionLedgerBridge`` against a static, digest-bound ``PaperGovernorPolicy`` snapshot.

Covers the happy ALLOW path, deterministic REVIEW/BLOCK policy paths, digest/provenance binding (no fake
cross-contract equality), cross-artifact identity, status/safety/non-overclaim, raw/canonical adversariality,
forbidden-surface exclusion (alias-resistant), and non-overclaim. A genuine READY bridge is built end-to-end
(episode + admitted manifest + record → append) so the governor decides over a real, proven paper chain."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_governor_decision as governor_module
from crypto_core.validation.paper_admission_ledger_bridge import (
    PaperAdmissionLedgerBridgeStatus,
    append_paper_admission_record_to_evidence_journal,
    paper_admission_ledger_bridge_digest,
)
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_end_to_end_episode import build_paper_end_to_end_episode
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_evidence_admission_record import build_paper_evidence_admission_record
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_governor_decision import (
    PaperGovernorDecisionError,
    PaperGovernorDecisionStatus,
    PaperGovernorPolicy,
    PaperGovernorPolicyError,
    PaperGovernorVerdict,
    build_paper_governor_policy,
    decide_paper_governor,
    paper_governor_decision_digest,
    paper_governor_decision_to_dict,
    paper_governor_policy_digest,
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
    build_flat_paper_position_state,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_realized_pnl_rollup import PaperRealizedPnlRollupInput
from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregateInput,
    build_paper_session_realized_pnl_aggregate,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
)
from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    build_paper_session_realized_pnl_evidence_manifest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

_SYMBOL = "BTC-PERPETUAL"
_CORR = "corr-ep"
_REQ_CORR = "corr-req"
_RUN = "run-ep"
_EPISODE_ID = "e2e-1"
_POLICY_ID = "gov-policy-1"

_CHAIN_IDS: dict[str, object] = {
    "fill_simulation_id": "fillsim-1",
    "position_transition_id": "trans-1",
    "new_position_state_id": "newpos-1",
    "pnl_report_id": "pnl-1",
    "episode_run_id": "ep-run-1",
    "correlation_id": _CORR,
}


class _LiarStr(str):
    """A ``str`` subclass that lies about equality (defeated only by exact ``type(x) is str`` checks)."""

    def __eq__(self, other: object) -> bool:  # noqa: D401 - test double
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _make_draft() -> PaperAllocatorIntentDraft:
    fields: dict[str, object] = {
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
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _spec() -> StrategySpec:
    payload = {
        "schema_version": "strategy-spec.v1",
        "strategy_id": "alpha-funding-carry",
        "strategy_version": "1.0.0",
        "strategy_family": "carry",
        "edge_family": "funding_basis_carry",
        "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["perp_linear"],
        "timeframe": "1h",
        "bar_definition": "time_1h",
        "entry_conditions": ["funding_positive"],
        "exit_conditions": ["funding_neutral"],
        "invalidation_conditions": ["regime_break"],
        "risk_caps": {"max_leverage": 2.0},
        "data_requirements": {"funding_rate": "1h"},
        "feature_requirements": {"funding_zscore": "rolling"},
        "latency_sensitivity": "low",
        "funding_sensitivity": "high",
        "fee_model_requirement": "taker_10bps",
        "slippage_model_requirement": "depth_aware",
        "expected_regime": "ranging",
        "failure_modes": ["funding_flip"],
        "kill_switch_triggers": ["max_dd"],
        "telemetry_fields": ["funding"],
        "promotion_requirements": ["walk_forward"],
    }
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _capacity():
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    return evaluate_paper_capacity_gate(
        _make_draft(), cap_policy, requested_notional="200", requested_units="4", correlation_id="corr-capacity"
    )


def _request(capacity):
    return build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=_SYMBOL,
        side=PaperOrderSide.SELL,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id=_REQ_CORR,
    )


def _order_intent_from(capacity, request):
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _bridge_signal():
    spec = _spec()
    capacity = _capacity()
    return build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=strategy_spec_digest(spec),
        signal_id="req-1",
        run_id=_RUN,
        correlation_id=_REQ_CORR,
        market_symbol=_SYMBOL,
        side=PaperOrderSide.SELL,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units=capacity.requested_units,
        requested_notional=capacity.requested_notional,
        capacity_decision_digest=capacity.decision_digest,
        limit_price=None,
    )


def _prior_long():
    return build_paper_position_state(
        position_state_id="pos-1",
        market_symbol=_SYMBOL,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="100",
        transition_count=0,
        correlation_id="corr-pos",
    )


def _snapshot():
    return build_paper_fill_market_snapshot(
        snapshot_id="snap-1", market_symbol=_SYMBOL, reference_price="50", available_units=None
    )


def _policy_fill():
    return build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )


def _mark():
    return build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol=_SYMBOL, mark_price="60", correlation_id="corr-mark"
    )


def _realized_components(order_intent, prior):
    fill = simulate_paper_fill(
        order_intent,
        _snapshot(),
        _policy_fill(),
        fill_simulation_id=_CHAIN_IDS["fill_simulation_id"],  # type: ignore[arg-type]
        correlation_id=_CORR,
    )
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=_CHAIN_IDS["position_transition_id"],  # type: ignore[arg-type]
        new_position_state_id=_CHAIN_IDS["new_position_state_id"],  # type: ignore[arg-type]
        correlation_id=_CORR,
    )
    assert new_state is not None
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id="rpnl-1", correlation_id=_CORR
    )
    return fill, transition, new_state, event


def _mr_episode():
    intent = _order_intent_from(_capacity(), _request(_capacity()))
    prior = build_flat_paper_position_state(position_state_id="pos-m", market_symbol=_SYMBOL, correlation_id="corr-pos")
    snapshot = build_paper_fill_market_snapshot(snapshot_id="snap-m", market_symbol=_SYMBOL, reference_price="50")
    policy = build_paper_fill_policy(
        policy_id="fill-policy-m", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id="mark-m", market_symbol=_SYMBOL, mark_price="60", correlation_id="corr-mark"
    )
    return run_paper_episode(
        intent,
        prior,
        snapshot,
        policy,
        mark,
        fill_simulation_id="fillsim-m",
        position_transition_id="trans-m",
        new_position_state_id="newpos-m",
        pnl_report_id="pnl-m",
        episode_run_id="ep-m",
        correlation_id="corr-ep",
    )


def _mr_prov() -> PaperSessionSequenceProvenance:
    eps = [_mr_episode()]
    session = build_paper_session_sequence(eps, paper_session_id="sess-1", correlation_id="corr-sess-1")
    return PaperSessionSequenceProvenance(session_sequence=session, episodes=tuple(eps))


def _aligned():
    capacity = _capacity()
    order_intent = _order_intent_from(capacity, _request(capacity))
    bridge_signal = _bridge_signal()
    prior = _prior_long()
    episode_run = run_paper_episode(order_intent, prior, _snapshot(), _policy_fill(), _mark(), **_CHAIN_IDS)  # type: ignore[arg-type]
    fill, transition, new_state, event = _realized_components(order_intent, prior)
    episode = build_paper_end_to_end_episode(
        bridge_signal,
        order_intent,
        episode_run,
        event,
        expected_bridge_digest=bridge_signal.bridge_digest,
        expected_order_intent_digest=order_intent.intent_digest,
        expected_episode_run_digest=episode_run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    rollup = PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )
    prov = _mr_prov()
    sbridge = build_paper_session_realized_pnl_bridge(
        prov, (rollup,), bridge_id="bridge-1", correlation_id="corr-bridge"
    )
    agg = build_paper_session_realized_pnl_aggregate(
        [PaperSessionRealizedPnlAggregateInput(bridge=sbridge, session_input=prov, rollup_entries=(rollup,))],
        aggregate_id="agg-1",
        correlation_id="corr-agg",
    )
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=agg.aggregate_digest, correlation_id="corr-manifest"
    )
    record = build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id=_CORR
    )
    return record, manifest, episode


def _ready_bridge():
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = append_paper_admission_record_to_evidence_journal(
        journal,
        record,
        episode,
        manifest,
        expected_admission_digest=record.admission_digest,
        expected_episode_digest=episode.episode_digest,
        expected_prior_journal_head_digest=journal.head_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.READY
    # The aligned chain produces realized_pnl=-200, closed_units=4, computed_event_count=1.
    assert bridge.realized_pnl_total == "-200"
    assert bridge.closed_units_total == "4"
    assert bridge.computed_event_count == 1
    return bridge


def _policy(
    *,
    policy_id: str = _POLICY_ID,
    min_computed_event_count: int = 1,
    max_abs_realized_pnl: str = "1000",
    review_abs_realized_pnl: str = "500",
    max_closed_units: str = "100",
    metadata=None,
) -> PaperGovernorPolicy:
    return build_paper_governor_policy(
        policy_id=policy_id,
        min_computed_event_count=min_computed_event_count,
        max_abs_realized_pnl=max_abs_realized_pnl,
        review_abs_realized_pnl=review_abs_realized_pnl,
        max_closed_units=max_closed_units,
        metadata=metadata,
    )


def _decide(bridge=None, policy=None, **overrides):
    bridge = bridge if bridge is not None else _ready_bridge()
    policy = policy if policy is not None else _policy()
    kwargs = {
        "expected_ledger_bridge_digest": bridge.ledger_digest,
        "episode_id": _EPISODE_ID,
        "run_id": _RUN,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return decide_paper_governor(bridge, policy, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy path / ALLOW
# --------------------------------------------------------------------------------------------------


def test_valid_inputs_allow_paper() -> None:
    bridge = _ready_bridge()
    decision = _decide(bridge=bridge)
    assert decision.status is PaperGovernorDecisionStatus.DECIDED
    assert decision.decided is True
    assert decision.decision is PaperGovernorVerdict.ALLOW_PAPER
    assert decision.allowed is True
    assert decision.reason_codes == ()
    assert decision.run_id == _RUN
    assert decision.episode_id == _EPISODE_ID
    assert decision.correlation_id == _CORR
    assert decision.market_symbol == _SYMBOL
    assert _is_hex64(decision.decision_digest)


def test_all_consumed_digests_bound() -> None:
    bridge = _ready_bridge()
    policy = _policy()
    decision = _decide(bridge=bridge, policy=policy)
    assert decision.ledger_bridge_digest == bridge.ledger_digest
    assert decision.expected_ledger_bridge_digest == bridge.ledger_digest
    assert decision.policy_digest == policy.policy_digest
    assert decision.policy_id == policy.policy_id
    assert decision.episode_digest == bridge.episode_digest
    assert decision.manifest_digest == bridge.manifest_digest
    assert decision.realized_pnl_event_digest == bridge.realized_pnl_event_digest
    assert decision.realized_pnl_total == bridge.realized_pnl_total
    assert decision.closed_units_total == bridge.closed_units_total
    assert decision.ledger_bridge_status == "READY"


def test_decision_digest_deterministic_and_recomputes() -> None:
    a = _decide()
    b = _decide()
    assert a.decision_digest == b.decision_digest
    assert paper_governor_decision_digest(a) == a.decision_digest
    assert paper_governor_decision_to_dict(a)["decision_digest"] == a.decision_digest


def test_changed_bound_field_changes_decision_digest() -> None:
    base = _decide()
    other = _decide(metadata={"note": "second"})
    assert base.decision_digest != other.decision_digest


def test_policy_digest_recomputes() -> None:
    policy = _policy()
    assert paper_governor_policy_digest(policy) == policy.policy_digest


# --------------------------------------------------------------------------------------------------
# 2. Governor decision semantics (deterministic ALLOW / REVIEW / BLOCK)
# --------------------------------------------------------------------------------------------------


def test_review_required_soft_realized_pnl_boundary() -> None:
    # abs(realized)=200 > review(100) but <= block(1000) -> REVIEW_REQUIRED.
    decision = _decide(policy=_policy(review_abs_realized_pnl="100", max_abs_realized_pnl="1000"))
    assert decision.status is PaperGovernorDecisionStatus.DECIDED
    assert decision.decision is PaperGovernorVerdict.REVIEW_REQUIRED
    assert decision.allowed is False
    assert any("realized_pnl_exceeds_review_threshold" in r for r in decision.reason_codes)


def test_block_paper_realized_pnl_exceeds_block_threshold() -> None:
    # abs(realized)=200 > block(100) -> BLOCK_PAPER (decided).
    decision = _decide(policy=_policy(review_abs_realized_pnl="50", max_abs_realized_pnl="100"))
    assert decision.status is PaperGovernorDecisionStatus.DECIDED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert decision.allowed is False
    assert any("realized_pnl_exceeds_block_threshold" in r for r in decision.reason_codes)


def test_block_paper_closed_units_exceeds_max() -> None:
    decision = _decide(policy=_policy(max_closed_units="2"))
    assert decision.status is PaperGovernorDecisionStatus.DECIDED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert any("closed_units_exceeds_max" in r for r in decision.reason_codes)


def test_block_paper_insufficient_computed_events() -> None:
    decision = _decide(policy=_policy(min_computed_event_count=2))
    assert decision.status is PaperGovernorDecisionStatus.DECIDED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert any("insufficient_computed_events" in r for r in decision.reason_codes)


def test_reason_codes_sorted_stable() -> None:
    decision = _decide(
        policy=_policy(
            min_computed_event_count=2, max_closed_units="2", max_abs_realized_pnl="100", review_abs_realized_pnl="50"
        )
    )
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert list(decision.reason_codes) == sorted(set(decision.reason_codes))


def test_policy_snapshot_is_serializer_visible_and_digest_bound() -> None:
    policy = _policy()
    decision = _decide(policy=policy)
    payload = paper_governor_decision_to_dict(decision)
    assert payload["policy_digest"] == policy.policy_digest
    assert payload["policy_id"] == policy.policy_id


# --------------------------------------------------------------------------------------------------
# 3. Digest / provenance
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_ledger_bridge_digest_rejects() -> None:
    decision = _decide(expected_ledger_bridge_digest="a" * 64)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert any("ledger_bridge_digest_mismatch" in r for r in decision.reason_codes)


def test_forged_ledger_bridge_self_digest_rejects() -> None:
    bridge = replace(_ready_bridge(), ledger_digest="0" * 64)
    decision = _decide(bridge=bridge, expected_ledger_bridge_digest="0" * 64)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_digest_mismatch" in r for r in decision.reason_codes)


def test_tampered_policy_digest_rejects() -> None:
    bridge = _ready_bridge()
    tampered = replace(_policy(), max_abs_realized_pnl="5")  # changes thresholds, stale policy_digest
    decision = _decide(bridge=bridge, policy=tampered)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("policy_digest_mismatch" in r for r in decision.reason_codes)


def test_stale_self_digest_without_expected_anchor_rejects() -> None:
    # Genuine self-digest paired with a WRONG expected anchor is rejected.
    decision = _decide(expected_ledger_bridge_digest="c" * 64)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_digest_mismatch" in r for r in decision.reason_codes)


# --------------------------------------------------------------------------------------------------
# 4. Cross-artifact consistency
# --------------------------------------------------------------------------------------------------


def test_episode_id_mismatch_rejects() -> None:
    decision = _decide(episode_id="other-episode")
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("episode_id_mismatch" in r for r in decision.reason_codes)


def test_run_id_mismatch_rejects() -> None:
    decision = _decide(run_id="other-run")
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("run_id_mismatch" in r for r in decision.reason_codes)


def test_correlation_id_mismatch_rejects() -> None:
    decision = _decide(correlation_id="corr-other")
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("correlation_id_mismatch" in r for r in decision.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Status / safety
# --------------------------------------------------------------------------------------------------


def test_ledger_bridge_not_ready_rejects() -> None:
    tampered = replace(_ready_bridge(), status=PaperAdmissionLedgerBridgeStatus.REJECTED, ready=False)
    sealed = replace(tampered, ledger_digest=paper_admission_ledger_bridge_digest(tampered))
    decision = _decide(bridge=sealed, expected_ledger_bridge_digest=sealed.ledger_digest)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert any("ledger_bridge_not_ready" in r for r in decision.reason_codes)


def test_ledger_bridge_not_appended_rejects() -> None:
    tampered = replace(_ready_bridge(), appended=False)
    sealed = replace(tampered, ledger_digest=paper_admission_ledger_bridge_digest(tampered))
    decision = _decide(bridge=sealed, expected_ledger_bridge_digest=sealed.ledger_digest)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_not_appended" in r for r in decision.reason_codes)


def test_ledger_bridge_lineage_unproven_rejects() -> None:
    tampered = replace(_ready_bridge(), source_event_digest_count=0)
    sealed = replace(tampered, ledger_digest=paper_admission_ledger_bridge_digest(tampered))
    decision = _decide(bridge=sealed, expected_ledger_bridge_digest=sealed.ledger_digest)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_lineage_unproven" in r for r in decision.reason_codes)


def test_resealed_unsafe_ledger_bridge_flag_rejects() -> None:
    tampered = replace(_ready_bridge(), order_routed=True)
    sealed = replace(tampered, ledger_digest=paper_admission_ledger_bridge_digest(tampered))
    decision = _decide(bridge=sealed, expected_ledger_bridge_digest=sealed.ledger_digest)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_unsafe_flags" in r for r in decision.reason_codes)


def test_resealed_overclaim_ledger_bridge_flag_rejects() -> None:
    tampered = replace(_ready_bridge(), prdv4_stage4_complete=True)
    sealed = replace(tampered, ledger_digest=paper_admission_ledger_bridge_digest(tampered))
    decision = _decide(bridge=sealed, expected_ledger_bridge_digest=sealed.ledger_digest)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_unsafe_flags" in r for r in decision.reason_codes)


def test_non_overclaim_flags_false_and_bound() -> None:
    payload = paper_governor_decision_to_dict(_decide())
    for flag in (
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "profitability_proven",
        "edge_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "order_routed",
        "execution_authorized",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True


# --------------------------------------------------------------------------------------------------
# 6. Raw / canonical adversariality
# --------------------------------------------------------------------------------------------------


def test_str_subclass_correlation_id_raises() -> None:
    with pytest.raises(PaperGovernorDecisionError, match="correlation_id_invalid"):
        _decide(correlation_id=_LiarStr("corr-ep"))


def test_equality_liar_ledger_digest_cannot_bypass() -> None:
    bridge = replace(_ready_bridge(), ledger_digest=_LiarStr(_ready_bridge().ledger_digest))
    decision = _decide(bridge=bridge, expected_ledger_bridge_digest="a" * 64)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_digest_mismatch" in r for r in decision.reason_codes)


def test_bridge_digest_serializer_error_rejected_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_artifact: object) -> str:
        raise RuntimeError("digest exploded")

    monkeypatch.setattr(governor_module, "paper_admission_ledger_bridge_digest", boom)
    decision = _decide()
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert any("ledger_bridge_malformed" in r for r in decision.reason_codes)


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    with pytest.raises(PaperGovernorDecisionError, match="metadata_malformed"):
        _decide(metadata=bad_metadata)


@pytest.mark.parametrize("correlation_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(correlation_id: str) -> None:
    with pytest.raises(PaperGovernorDecisionError, match="scope_violation"):
        _decide(correlation_id=correlation_id)


# --------------------------------------------------------------------------------------------------
# 7. Fail-closed: call-level input
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_ledger_bridge_raises() -> None:
    with pytest.raises(PaperGovernorDecisionError, match="ledger_bridge_malformed"):
        decide_paper_governor(
            {"not": "a-bridge"},  # type: ignore[arg-type]
            _policy(),
            expected_ledger_bridge_digest="a" * 64,
            episode_id=_EPISODE_ID,
            run_id=_RUN,
            correlation_id=_CORR,
        )


def test_wrong_typed_policy_raises() -> None:
    with pytest.raises(PaperGovernorDecisionError, match="policy_malformed"):
        decide_paper_governor(
            _ready_bridge(),
            {"not": "a-policy"},  # type: ignore[arg-type]
            expected_ledger_bridge_digest="a" * 64,
            episode_id=_EPISODE_ID,
            run_id=_RUN,
            correlation_id=_CORR,
        )


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_ledger_bridge_digest_raises(bad: str) -> None:
    with pytest.raises(PaperGovernorDecisionError, match="expected_ledger_bridge_digest_invalid"):
        _decide(expected_ledger_bridge_digest=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_episode_id_raises(bad: str) -> None:
    with pytest.raises(PaperGovernorDecisionError, match="episode_id_invalid"):
        _decide(episode_id=bad)


# --------------------------------------------------------------------------------------------------
# 8. Policy builder validation
# --------------------------------------------------------------------------------------------------


def test_policy_review_threshold_exceeds_block_raises() -> None:
    with pytest.raises(PaperGovernorPolicyError, match="review_threshold_exceeds_block_threshold"):
        _policy(review_abs_realized_pnl="2000", max_abs_realized_pnl="1000")


@pytest.mark.parametrize("bad", ["-1", "1.", ".5", "00", "1e5", "NaN", ""])
def test_policy_malformed_threshold_raises(bad: str) -> None:
    with pytest.raises(PaperGovernorPolicyError, match="max_abs_realized_pnl_invalid"):
        _policy(max_abs_realized_pnl=bad)


def test_policy_negative_min_event_count_raises() -> None:
    with pytest.raises(PaperGovernorPolicyError, match="min_computed_event_count_invalid"):
        _policy(min_computed_event_count=-1)


def test_policy_scope_violation_raises() -> None:
    with pytest.raises(PaperGovernorPolicyError, match="scope_violation"):
        _policy(policy_id="live_order")


# --------------------------------------------------------------------------------------------------
# 8b. P2 regression — policy threshold invariants re-proved at the DECISION boundary
# (a malformed-but-resealed policy whose digest re-proves must still fail closed; no false ALLOW)
# --------------------------------------------------------------------------------------------------


def _resealed_policy(**overrides) -> PaperGovernorPolicy:
    """Manually construct a malformed policy and reseal its self-digest (bypassing the builder's invariants),
    so ``paper_governor_policy_digest`` re-proves but the threshold invariants are violated."""
    tampered = replace(_policy(), **overrides)
    return replace(tampered, policy_digest=paper_governor_policy_digest(tampered))


def test_resealed_review_exceeds_block_threshold_rejects_at_boundary() -> None:
    # Exact connector false-ALLOW class: review(2000) > block(1000), bridge abs(realized)=200. The digest
    # re-proves, but the decision boundary re-checks invariants -> REJECTED + BLOCK_PAPER (never ALLOW).
    policy = _resealed_policy(max_abs_realized_pnl="1000", review_abs_realized_pnl="2000")
    assert paper_governor_policy_digest(policy) == policy.policy_digest  # digest re-proves
    decision = _decide(policy=policy)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert decision.allowed is False
    assert decision.decision is not PaperGovernorVerdict.ALLOW_PAPER
    assert any("policy_thresholds_malformed" in r for r in decision.reason_codes)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_abs_realized_pnl": "-1"},
        {"review_abs_realized_pnl": "-1"},
        {"max_closed_units": "-1"},
        {"min_computed_event_count": -1},
    ],
)
def test_resealed_invalid_threshold_rejects_at_boundary(overrides: dict[str, object]) -> None:
    policy = _resealed_policy(**overrides)
    assert paper_governor_policy_digest(policy) == policy.policy_digest  # digest re-proves
    decision = _decide(policy=policy)
    assert decision.status is PaperGovernorDecisionStatus.REJECTED
    assert decision.decision is PaperGovernorVerdict.BLOCK_PAPER
    assert decision.allowed is False
    assert any("policy_thresholds_malformed" in r for r in decision.reason_codes)


def test_boundary_reproof_independent_of_builder() -> None:
    # The builder still rejects malformed thresholds up front, AND the decision boundary independently rejects
    # a resealed artifact that bypassed the builder — defense in depth, no trust of builder invariants.
    with pytest.raises(PaperGovernorPolicyError):
        _policy(review_abs_realized_pnl="2000", max_abs_realized_pnl="1000")
    resealed = _resealed_policy(max_abs_realized_pnl="1000", review_abs_realized_pnl="2000")
    assert _decide(policy=resealed).status is PaperGovernorDecisionStatus.REJECTED


# --------------------------------------------------------------------------------------------------
# 9. Immutability / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_output_frozen() -> None:
    decision = _decide()
    with pytest.raises(FrozenInstanceError):
        decision.allowed = True  # type: ignore[misc]


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(governor_module.__file__).read_text(encoding="utf-8"))
    top_level: set[str] = set()
    crypto_submodules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
            parts = node.module.split(".")
            if parts[0] == "crypto_core" and len(parts) > 1:
                crypto_submodules.add(parts[1])
    impure = {
        "os",
        "sys",
        "io",
        "pathlib",
        "time",
        "datetime",
        "threading",
        "asyncio",
        "multiprocessing",
        "socket",
        "subprocess",
        "random",
        "secrets",
        "uuid",
        "requests",
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules <= {"validation"}


def test_no_forbidden_module_imports() -> None:
    tree = ast.parse(Path(governor_module.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        assert "service" not in module.split("."), module
        assert "execution" not in module.split("."), module
        assert "venue" not in module.split("."), module
        assert "runtime" not in module.split("."), module
        assert "readiness" not in module, module
        assert "paper_adapter" not in module, module
        assert "paper_live_service" not in module, module
        assert "paper_shadow_session_controller" not in module, module


def test_public_api_exact() -> None:
    assert set(governor_module.__all__) == {
        "PaperGovernorDecision",
        "PaperGovernorDecisionError",
        "PaperGovernorDecisionStatus",
        "PaperGovernorPolicy",
        "PaperGovernorPolicyError",
        "PaperGovernorVerdict",
        "build_paper_governor_policy",
        "decide_paper_governor",
        "paper_governor_decision_digest",
        "paper_governor_decision_to_dict",
        "paper_governor_policy_digest",
        "paper_governor_policy_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "place_order", "venue", "live")
    for name in governor_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name
