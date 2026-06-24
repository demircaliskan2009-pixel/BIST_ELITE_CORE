"""Tests for the deterministic paper replay harness — proves an original vs replay ``PaperGovernorDecision``
are digest-identical at every public contract boundary, fail-closed on any discrepancy.

Genuine artifacts are built end-to-end through the merged paper chain (episode + admitted manifest + record →
ledger bridge → governor decision) so the harness is exercised against real ``decide_paper_governor`` output,
not hand-rolled stand-ins; adversarial variants are derived by ``replace(...)`` + reseal of those genuine
artifacts. Covers happy MATCHED, boundary MISMATCHED, untrusted-input REJECTED, cross-id, canonical/adversarial,
forbidden-surface exclusion (alias-resistant AST), and non-overclaim."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import deterministic_paper_replay_harness as harness_module
from crypto_core.validation.deterministic_paper_replay_harness import (
    DeterministicPaperReplayHarnessError,
    DeterministicPaperReplayHarnessStatus,
    deterministic_paper_replay_harness_result_digest,
    deterministic_paper_replay_harness_result_to_dict,
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
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot as _build_paper_mark_snapshot
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
    return _build_paper_mark_snapshot(
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
    mark = _build_paper_mark_snapshot(
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


def _reseal(decision):
    """Reseal a (tampered) decision's self-digest so its public digest re-proves but content changed."""
    return replace(decision, decision_digest=paper_governor_decision_digest(decision))


def _verify(original, replay, **overrides):
    kwargs = {
        "expected_original_digest": original.decision_digest,
        "expected_replay_digest": replay.decision_digest,
        "run_id": _RUN,
        "episode_id": _EPISODE_ID,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return verify_deterministic_paper_replay(original, replay, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy replay MATCHED
# --------------------------------------------------------------------------------------------------


def test_identical_replay_matches() -> None:
    original = _real_decision()
    replay = _real_decision()
    # A genuine deterministic replay reproduces the exact same decision digest.
    assert original.decision_digest == replay.decision_digest
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.MATCHED
    assert result.matched is True
    assert result.ready is True
    assert result.reason_codes == ()
    assert result.run_id == _RUN
    assert result.episode_id == _EPISODE_ID
    assert result.correlation_id == _CORR
    assert result.market_symbol == _SYMBOL
    assert result.original_decision_digest == original.decision_digest
    assert result.replay_decision_digest == replay.decision_digest
    assert _is_hex64(result.replay_result_digest)
    assert result.compared_boundaries == harness_module._COMPARED_BOUNDARIES
    assert len(result.compared_boundaries) > 0


def test_result_digest_deterministic_and_recomputes() -> None:
    original = _real_decision()
    replay = _real_decision()
    a = _verify(original, replay)
    b = _verify(original, replay)
    assert a.replay_result_digest == b.replay_result_digest
    assert deterministic_paper_replay_harness_result_digest(a) == a.replay_result_digest
    assert deterministic_paper_replay_harness_result_to_dict(a)["replay_result_digest"] == a.replay_result_digest


def test_changed_bound_field_changes_result_digest() -> None:
    original = _real_decision()
    replay = _real_decision()
    base = _verify(original, replay)
    other = _verify(original, replay, metadata={"note": "second"})
    assert base.replay_result_digest != other.replay_result_digest


def test_matched_boundary_values_mirrored() -> None:
    original = _real_decision()
    replay = _real_decision()
    result = _verify(original, replay)
    assert result.original_ledger_bridge_digest == original.ledger_bridge_digest
    assert result.original_episode_digest == original.episode_digest
    assert result.original_manifest_digest == original.manifest_digest
    assert result.original_realized_pnl_event_digest == original.realized_pnl_event_digest
    assert result.original_policy_digest == original.policy_digest
    assert result.original_realized_pnl_total == original.realized_pnl_total
    assert result.original_closed_units_total == original.closed_units_total
    assert result.original_computed_event_count == original.computed_event_count
    assert result.original_source_event_digest_count == original.source_event_digest_count
    assert result.original_verdict == original.decision.value


# --------------------------------------------------------------------------------------------------
# 2. Boundary MISMATCHED (both trusted, replay differs)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("episode_digest", "b" * 64, "episode_digest_mismatch"),
        ("ledger_bridge_digest", "b" * 64, "ledger_bridge_digest_mismatch"),
        ("manifest_digest", "b" * 64, "manifest_digest_mismatch"),
        ("realized_pnl_event_digest", "b" * 64, "realized_pnl_event_digest_mismatch"),
        ("policy_digest", "b" * 64, "policy_digest_mismatch"),
        ("realized_pnl_total", "-300", "realized_pnl_total_mismatch"),
        ("closed_units_total", "9", "closed_units_total_mismatch"),
        ("source_event_digest_count", 7, "source_event_digest_count_mismatch"),
    ],
)
def test_boundary_mismatch_fails_closed(field: str, value: object, reason: str) -> None:
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), **{field: value}))
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.MISMATCHED
    assert result.matched is False
    assert result.ready is False
    assert any(reason in code for code in result.reason_codes)
    # The top-level decision digest also necessarily differs when an embedded bound field changed.
    assert any("decision_digest_mismatch" in code for code in result.reason_codes)


def test_genuine_verdict_difference_mismatches() -> None:
    # Two genuine decisions over the SAME bridge but different policies -> different verdict + policy digest.
    original = _real_decision(policy=_policy())  # ALLOW
    replay = _real_decision(policy=_policy(review_abs_realized_pnl="100"))  # REVIEW_REQUIRED
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.MISMATCHED
    assert any("verdict_mismatch" in code for code in result.reason_codes)
    assert any("policy_digest_mismatch" in code for code in result.reason_codes)


def test_expected_replay_anchor_mismatch_rejects() -> None:
    original = _real_decision()
    replay = _real_decision()
    result = _verify(original, replay, expected_replay_digest="a" * 64)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("replay_decision_digest_mismatch" in code for code in result.reason_codes)


def test_expected_original_anchor_mismatch_rejects() -> None:
    original = _real_decision()
    replay = _real_decision()
    result = _verify(original, replay, expected_original_digest="a" * 64)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("original_decision_digest_mismatch" in code for code in result.reason_codes)


def test_forged_replay_self_digest_rejects() -> None:
    original = _real_decision()
    replay = replace(_real_decision(), decision_digest="0" * 64)  # tampered WITHOUT reseal
    result = _verify(original, replay, expected_replay_digest="0" * 64)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("replay_decision_digest_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 3. Status / safety (untrusted consumed decision -> REJECTED, no partial match)
# --------------------------------------------------------------------------------------------------


def test_rejected_original_decision_rejects() -> None:
    # A genuine REJECTED governor decision (wrong bridge anchor) is untrusted input.
    rejected = _real_decision(expected_ledger_bridge_digest="a" * 64)
    replay = _real_decision()
    result = _verify(rejected, replay, expected_original_digest=rejected.decision_digest)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert result.matched is False
    assert any("original_decision_not_decided" in code for code in result.reason_codes)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("order_routed", "replay_decision_unsafe_flags"),
        ("execution_authorized", "replay_decision_unsafe_flags"),
        ("live_api_called", "replay_decision_unsafe_flags"),
        ("scheduler_enabled", "replay_decision_unsafe_flags"),
        ("prdv4_stage4_complete", "replay_decision_unsafe_flags"),
        ("live_ready", "replay_decision_unsafe_flags"),
        ("production_execution", "replay_decision_unsafe_flags"),
    ],
)
def test_unsafe_or_overclaim_flag_rejects(field: str, reason: str) -> None:
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), **{field: True}))
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert result.matched is False
    assert any(reason in code for code in result.reason_codes)


def test_lineage_unproven_rejects() -> None:
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), source_event_digest_count=0))
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("replay_decision_lineage_unproven" in code for code in result.reason_codes)


def test_no_partial_match_under_unsafe_input() -> None:
    original = _reseal(replace(_real_decision(), order_routed=True))
    replay = _real_decision()
    result = _verify(original, replay, expected_original_digest=original.decision_digest)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert result.matched is False
    assert result.ready is False


# --------------------------------------------------------------------------------------------------
# 4. Cross-id consistency
# --------------------------------------------------------------------------------------------------


def test_run_id_mismatch_rejects() -> None:
    result = _verify(_real_decision(), _real_decision(), run_id="other-run")
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("original_run_id_mismatch" in code for code in result.reason_codes)
    assert any("replay_run_id_mismatch" in code for code in result.reason_codes)


def test_episode_id_mismatch_rejects() -> None:
    result = _verify(_real_decision(), _real_decision(), episode_id="other-episode")
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("episode_id_mismatch" in code for code in result.reason_codes)


def test_correlation_id_mismatch_rejects() -> None:
    result = _verify(_real_decision(), _real_decision(), correlation_id="corr-other")
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("correlation_id_mismatch" in code for code in result.reason_codes)


def test_replay_side_id_divergence_rejects() -> None:
    # Original carries the caller ids; replay was resealed with a different run id -> replay side fails.
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), run_id="run-divergent"))
    result = _verify(original, replay, expected_replay_digest=replay.decision_digest)
    assert result.status is DeterministicPaperReplayHarnessStatus.REJECTED
    assert any("replay_run_id_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Canonical / adversarial
# --------------------------------------------------------------------------------------------------


def test_str_subclass_correlation_id_raises() -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="correlation_id_invalid"):
        _verify(_real_decision(), _real_decision(), correlation_id=_LiarStr("corr-ep"))


def test_equality_liar_boundary_field_cannot_mask_mismatch() -> None:
    # A str-subclass liar in a bound digest normalizes to "" at the boundary, so it can never appear equal.
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), episode_digest=_LiarStr("b" * 64)))
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.MISMATCHED
    assert result.matched is False
    assert any("episode_digest_mismatch" in code for code in result.reason_codes)


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="metadata_malformed"):
        _verify(_real_decision(), _real_decision(), metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_digest_raises(bad: str) -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="expected_original_digest_invalid"):
        _verify(_real_decision(), _real_decision(), expected_original_digest=bad)


def test_wrong_typed_original_raises() -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="original_malformed"):
        verify_deterministic_paper_replay(
            {"not": "a-decision"},  # type: ignore[arg-type]
            _real_decision(),
            expected_original_digest="a" * 64,
            expected_replay_digest="a" * 64,
            run_id=_RUN,
            episode_id=_EPISODE_ID,
            correlation_id=_CORR,
        )


def test_wrong_typed_replay_raises() -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="replay_malformed"):
        verify_deterministic_paper_replay(
            _real_decision(),
            {"not": "a-decision"},  # type: ignore[arg-type]
            expected_original_digest="a" * 64,
            expected_replay_digest="a" * 64,
            run_id=_RUN,
            episode_id=_EPISODE_ID,
            correlation_id=_CORR,
        )


@pytest.mark.parametrize("scope_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(scope_id: str) -> None:
    with pytest.raises(DeterministicPaperReplayHarnessError, match="scope_violation"):
        _verify(_real_decision(), _real_decision(), correlation_id=scope_id)


def test_inputs_not_mutated() -> None:
    original = _real_decision()
    replay = _real_decision()
    original_digest_before = original.decision_digest
    replay_digest_before = replay.decision_digest
    _verify(original, replay)
    assert original.decision_digest == original_digest_before
    assert replay.decision_digest == replay_digest_before


def test_result_frozen() -> None:
    result = _verify(_real_decision(), _real_decision())
    with pytest.raises(FrozenInstanceError):
        result.matched = True  # type: ignore[misc]


def test_reason_codes_sorted_stable() -> None:
    original = _real_decision()
    replay = _reseal(replace(_real_decision(), episode_digest="b" * 64, manifest_digest="c" * 64))
    result = _verify(original, replay)
    assert result.status is DeterministicPaperReplayHarnessStatus.MISMATCHED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


# --------------------------------------------------------------------------------------------------
# 6. Immutability / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(harness_module.__file__).read_text(encoding="utf-8"))
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
    tree = ast.parse(Path(harness_module.__file__).read_text(encoding="utf-8"))
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
        assert "deribit" not in module, module
        assert "bist" not in module, module


def test_public_api_exact() -> None:
    assert set(harness_module.__all__) == {
        "DeterministicPaperReplayHarnessError",
        "DeterministicPaperReplayHarnessResult",
        "DeterministicPaperReplayHarnessStatus",
        "deterministic_paper_replay_harness_result_digest",
        "deterministic_paper_replay_harness_result_to_dict",
        "verify_deterministic_paper_replay",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "place_order", "venue", "live")
    for name in harness_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# --------------------------------------------------------------------------------------------------
# 7. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags_false_and_bound() -> None:
    payload = deterministic_paper_replay_harness_result_to_dict(_verify(_real_decision(), _real_decision()))
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
