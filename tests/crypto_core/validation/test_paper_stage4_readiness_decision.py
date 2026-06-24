"""Tests for the paper Stage-4 readiness decision — deterministic, paper-only, fail-closed verdict over a
``DeterministicPaperReplayHarnessResult`` (§7.6) + ``PaperGovernorDecision`` (§7.5).

Genuine artifacts are built end-to-end through the merged paper chain (episode + admitted manifest + record →
ledger bridge → governor decision → replay harness) so the readiness decision is exercised against real
artifacts; adversarial variants are derived by ``replace(...)`` + reseal. Covers candidate/review/block paths,
replay mismatch, digest/provenance, same-chain binding, cross-id, status/safety, canonical/adversarial,
forbidden-surface exclusion (alias-resistant AST), and non-overclaim."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_stage4_readiness_decision as readiness_module
from crypto_core.validation.deterministic_paper_replay_harness import (
    deterministic_paper_replay_harness_result_digest,
    verify_deterministic_paper_replay,
)
from crypto_core.validation.paper_admission_ledger_bridge import (
    PaperAdmissionLedgerBridgeStatus,
    append_paper_admission_record_to_evidence_journal,
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
    PaperGovernorPolicy,
    build_paper_governor_policy,
    decide_paper_governor,
    paper_governor_decision_digest,
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
from crypto_core.validation.paper_stage4_readiness_decision import (
    PaperStage4ReadinessDecisionError,
    PaperStage4ReadinessStatus,
    PaperStage4ReadinessVerdict,
    decide_paper_stage4_readiness,
    paper_stage4_readiness_decision_digest,
    paper_stage4_readiness_decision_to_dict,
)
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


def _real_decision(*, policy=None, bridge=None, **overrides):
    """A genuine ``PaperGovernorDecision`` from ``decide_paper_governor`` over a real READY bridge."""
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


def _reseal_governor(decision):
    return replace(decision, decision_digest=paper_governor_decision_digest(decision))


def _replay(original, replay, **overrides):
    """A genuine ``DeterministicPaperReplayHarnessResult`` over an original/replay governor-decision pair."""
    kwargs = {
        "expected_original_digest": original.decision_digest,
        "expected_replay_digest": replay.decision_digest,
        "run_id": _RUN,
        "episode_id": _EPISODE_ID,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return verify_deterministic_paper_replay(original, replay, **kwargs)


def _reseal_replay(result):
    return replace(result, replay_result_digest=deterministic_paper_replay_harness_result_digest(result))


def _candidate_inputs(policy=None):
    """Return (replay_result MATCHED, governor) sharing the same deterministic paper chain."""
    policy = policy if policy is not None else _policy()
    governor = _real_decision(policy=policy)
    replay_side = _real_decision(policy=policy)
    replay_result = _replay(governor, replay_side)
    return replay_result, governor


def _decide_readiness(replay_result, governor, **overrides):
    kwargs = {
        "expected_replay_result_digest": replay_result.replay_result_digest,
        "expected_governor_decision_digest": governor.decision_digest,
        "run_id": _RUN,
        "episode_id": _EPISODE_ID,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return decide_paper_stage4_readiness(replay_result, governor, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy candidate path
# --------------------------------------------------------------------------------------------------


def test_candidate_path() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor)
    assert result.status is PaperStage4ReadinessStatus.DECIDED
    assert result.decided is True
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_STAGE4_CANDIDATE
    assert result.ready is True
    assert result.reason_codes == ()
    assert result.run_id == _RUN
    assert result.episode_id == _EPISODE_ID
    assert result.correlation_id == _CORR
    assert result.market_symbol == _SYMBOL
    assert result.replay_result_digest == replay_result.replay_result_digest
    assert result.governor_decision_digest == governor.decision_digest
    assert result.episode_digest == governor.episode_digest
    assert result.policy_digest == governor.policy_digest
    assert result.replay_status == "MATCHED"
    assert result.governor_verdict == "ALLOW_PAPER"
    assert _is_hex64(result.readiness_decision_digest)


def test_decision_digest_deterministic_and_recomputes() -> None:
    replay_result, governor = _candidate_inputs()
    a = _decide_readiness(replay_result, governor)
    b = _decide_readiness(replay_result, governor)
    assert a.readiness_decision_digest == b.readiness_decision_digest
    assert paper_stage4_readiness_decision_digest(a) == a.readiness_decision_digest
    assert paper_stage4_readiness_decision_to_dict(a)["readiness_decision_digest"] == a.readiness_decision_digest


def test_changed_bound_field_changes_decision_digest() -> None:
    replay_result, governor = _candidate_inputs()
    base = _decide_readiness(replay_result, governor)
    other = _decide_readiness(replay_result, governor, metadata={"note": "second"})
    assert base.readiness_decision_digest != other.readiness_decision_digest


# --------------------------------------------------------------------------------------------------
# 2. Review / block paths
# --------------------------------------------------------------------------------------------------


def test_review_path() -> None:
    # abs(realized)=200 > review(100) but <= block(1000) -> governor REVIEW_REQUIRED.
    replay_result, governor = _candidate_inputs(policy=_policy(review_abs_realized_pnl="100"))
    result = _decide_readiness(replay_result, governor)
    assert result.status is PaperStage4ReadinessStatus.DECIDED
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_REVIEW_REQUIRED
    assert result.ready is False
    assert any("governor_review_required" in code for code in result.reason_codes)


def test_block_path_governor_block() -> None:
    # abs(realized)=200 > block(100) -> governor BLOCK_PAPER.
    replay_result, governor = _candidate_inputs(
        policy=_policy(review_abs_realized_pnl="50", max_abs_realized_pnl="100")
    )
    result = _decide_readiness(replay_result, governor)
    assert result.status is PaperStage4ReadinessStatus.DECIDED
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_BLOCKED
    assert result.ready is False
    assert any("governor_block_paper" in code for code in result.reason_codes)


def test_replay_mismatch_blocks() -> None:
    governor = _real_decision()
    mismatched_side = _reseal_governor(replace(_real_decision(), episode_digest="b" * 64))
    replay_result = _replay(governor, mismatched_side, expected_replay_digest=mismatched_side.decision_digest)
    result = _decide_readiness(replay_result, governor)
    assert result.status is PaperStage4ReadinessStatus.DECIDED
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_BLOCKED
    assert result.ready is False
    assert any("replay_not_matched" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 3. Digest / provenance / same-chain binding
# --------------------------------------------------------------------------------------------------


def test_wrong_replay_anchor_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, expected_replay_result_digest="a" * 64)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_BLOCKED
    assert any("replay_result_digest_mismatch" in code for code in result.reason_codes)


def test_wrong_governor_anchor_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, expected_governor_decision_digest="a" * 64)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("governor_decision_digest_mismatch" in code for code in result.reason_codes)


def test_forged_replay_self_digest_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    forged = replace(replay_result, replay_result_digest="0" * 64)  # tampered WITHOUT reseal
    result = _decide_readiness(forged, governor, expected_replay_result_digest="0" * 64)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_result_digest_mismatch" in code for code in result.reason_codes)


def test_forged_governor_self_digest_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    forged = replace(governor, decision_digest="0" * 64)  # tampered WITHOUT reseal
    result = _decide_readiness(replay_result, forged, expected_governor_decision_digest="0" * 64)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("governor_decision_digest_mismatch" in code for code in result.reason_codes)


def test_replay_governor_chain_mismatch_rejects() -> None:
    # Replay built over one chain; governor is a genuine decision from a DIFFERENT policy (different digest).
    replay_result, _ = _candidate_inputs()
    other_governor = _real_decision(policy=_policy(max_closed_units="50"))
    result = _decide_readiness(
        replay_result, other_governor, expected_governor_decision_digest=other_governor.decision_digest
    )
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_governor_decision_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 4. Cross-id
# --------------------------------------------------------------------------------------------------


def test_run_id_mismatch_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, run_id="other-run")
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_run_id_mismatch" in code for code in result.reason_codes)
    assert any("governor_run_id_mismatch" in code for code in result.reason_codes)


def test_episode_id_mismatch_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, episode_id="other-episode")
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("episode_id_mismatch" in code for code in result.reason_codes)


def test_correlation_id_mismatch_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, correlation_id="corr-other")
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("correlation_id_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Status / safety (untrusted input -> REJECTED, no partial candidate)
# --------------------------------------------------------------------------------------------------


def test_replay_self_rejected_not_trusted() -> None:
    governor = _real_decision()
    rejected_replay = _replay(governor, _real_decision(), expected_original_digest="a" * 64)
    result = _decide_readiness(
        rejected_replay, governor, expected_replay_result_digest=rejected_replay.replay_result_digest
    )
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_result_not_trusted" in code for code in result.reason_codes)


def test_replay_inconsistent_flags_reject() -> None:
    replay_result, governor = _candidate_inputs()
    inconsistent = _reseal_replay(replace(replay_result, ready=False))  # status MATCHED but ready False
    result = _decide_readiness(inconsistent, governor, expected_replay_result_digest=inconsistent.replay_result_digest)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_result_inconsistent" in code for code in result.reason_codes)


def test_unsafe_replay_flag_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    unsafe = _reseal_replay(replace(replay_result, order_routed=True))
    result = _decide_readiness(unsafe, governor, expected_replay_result_digest=unsafe.replay_result_digest)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert result.ready is False
    assert any("replay_result_unsafe_flags" in code for code in result.reason_codes)


def test_overclaim_replay_flag_rejects() -> None:
    replay_result, governor = _candidate_inputs()
    overclaim = _reseal_replay(replace(replay_result, prdv4_stage4_complete=True))
    result = _decide_readiness(overclaim, governor, expected_replay_result_digest=overclaim.replay_result_digest)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_result_unsafe_flags" in code for code in result.reason_codes)


def test_governor_not_decided_rejects() -> None:
    replay_result, _ = _candidate_inputs()
    rejected_governor = _real_decision(expected_ledger_bridge_digest="a" * 64)
    result = _decide_readiness(
        replay_result, rejected_governor, expected_governor_decision_digest=rejected_governor.decision_digest
    )
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("governor_decision_not_decided" in code for code in result.reason_codes)


def test_unsafe_governor_flag_rejects() -> None:
    replay_result, _ = _candidate_inputs()
    unsafe_governor = _reseal_governor(replace(_real_decision(), order_routed=True))
    result = _decide_readiness(
        replay_result, unsafe_governor, expected_governor_decision_digest=unsafe_governor.decision_digest
    )
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("governor_decision_unsafe_flags" in code for code in result.reason_codes)


def test_no_partial_candidate_under_unsafe_input() -> None:
    replay_result, governor = _candidate_inputs()
    unsafe = _reseal_replay(replace(replay_result, live_api_called=True))
    result = _decide_readiness(unsafe, governor, expected_replay_result_digest=unsafe.replay_result_digest)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert result.ready is False
    assert result.verdict is PaperStage4ReadinessVerdict.PAPER_BLOCKED


# --------------------------------------------------------------------------------------------------
# 6. Canonical / adversarial
# --------------------------------------------------------------------------------------------------


def test_str_subclass_correlation_id_raises() -> None:
    replay_result, governor = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="correlation_id_invalid"):
        _decide_readiness(replay_result, governor, correlation_id=_LiarStr("corr-ep"))


def test_equality_liar_chain_field_cannot_bypass() -> None:
    replay_result, governor = _candidate_inputs()
    liar = _reseal_replay(replace(replay_result, original_episode_digest=_LiarStr("b" * 64)))
    result = _decide_readiness(liar, governor, expected_replay_result_digest=liar.replay_result_digest)
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert any("replay_governor_episode_digest_mismatch" in code for code in result.reason_codes)


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    replay_result, governor = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="metadata_malformed"):
        _decide_readiness(replay_result, governor, metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_digest_raises(bad: str) -> None:
    replay_result, governor = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="expected_replay_result_digest_invalid"):
        _decide_readiness(replay_result, governor, expected_replay_result_digest=bad)


def test_wrong_typed_replay_raises() -> None:
    _, governor = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="replay_result_malformed"):
        decide_paper_stage4_readiness(
            {"not": "a-replay"},  # type: ignore[arg-type]
            governor,
            expected_replay_result_digest="a" * 64,
            expected_governor_decision_digest="a" * 64,
            run_id=_RUN,
            episode_id=_EPISODE_ID,
            correlation_id=_CORR,
        )


def test_wrong_typed_governor_raises() -> None:
    replay_result, _ = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="governor_decision_malformed"):
        decide_paper_stage4_readiness(
            replay_result,
            {"not": "a-governor"},  # type: ignore[arg-type]
            expected_replay_result_digest="a" * 64,
            expected_governor_decision_digest="a" * 64,
            run_id=_RUN,
            episode_id=_EPISODE_ID,
            correlation_id=_CORR,
        )


@pytest.mark.parametrize("scope_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(scope_id: str) -> None:
    replay_result, governor = _candidate_inputs()
    with pytest.raises(PaperStage4ReadinessDecisionError, match="scope_violation"):
        _decide_readiness(replay_result, governor, correlation_id=scope_id)


def test_inputs_not_mutated() -> None:
    replay_result, governor = _candidate_inputs()
    replay_digest_before = replay_result.replay_result_digest
    governor_digest_before = governor.decision_digest
    _decide_readiness(replay_result, governor)
    assert replay_result.replay_result_digest == replay_digest_before
    assert governor.decision_digest == governor_digest_before


def test_result_frozen() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor)
    with pytest.raises(FrozenInstanceError):
        result.ready = True  # type: ignore[misc]


def test_reason_codes_sorted_stable() -> None:
    replay_result, governor = _candidate_inputs()
    result = _decide_readiness(replay_result, governor, run_id="other-run", episode_id="other-episode")
    assert result.status is PaperStage4ReadinessStatus.REJECTED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


# --------------------------------------------------------------------------------------------------
# 7. Immutability / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(readiness_module.__file__).read_text(encoding="utf-8"))
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
        "httpx",
        "aiohttp",
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules <= {"validation"}


def test_no_forbidden_module_imports() -> None:
    tree = ast.parse(Path(readiness_module.__file__).read_text(encoding="utf-8"))
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
        assert "service" not in module, module
        assert "paper_adapter" not in module, module
        assert "paper_live_service" not in module, module
        assert "paper_shadow_session_controller" not in module, module
        assert "deribit" not in module, module
        assert "bist" not in module, module


def test_public_api_exact() -> None:
    assert set(readiness_module.__all__) == {
        "PaperStage4ReadinessDecision",
        "PaperStage4ReadinessDecisionError",
        "PaperStage4ReadinessStatus",
        "PaperStage4ReadinessVerdict",
        "decide_paper_stage4_readiness",
        "paper_stage4_readiness_decision_digest",
        "paper_stage4_readiness_decision_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "place_order", "venue")
    for name in readiness_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# --------------------------------------------------------------------------------------------------
# 8. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags_false_and_bound() -> None:
    replay_result, governor = _candidate_inputs()
    payload = paper_stage4_readiness_decision_to_dict(_decide_readiness(replay_result, governor))
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
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "deribit_ready",
        "operational_readiness",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True
