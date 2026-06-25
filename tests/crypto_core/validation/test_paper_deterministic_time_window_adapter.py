"""Tests for the paper deterministic time-window adapter (§10.4.2) — deterministic, paper-only, fail-closed
INJECTED nanosecond window evidence over a ``PaperSessionMetricsSummary``.

A genuine summary is built end-to-end through the merged paper chain (aggregate + manifest + §7.7 readiness →
metrics summary); adversarial variants are derived by ``replace(...)`` + reseal. Covers the duplicate-precheck/
non-duplication, the happy READY+eligible path, summary digest/provenance, summary invariants, injected-int
timestamp validation, suspicious clock-token rejection, determinism/canonicality, forbidden-surface exclusion
(alias-resistant AST + no stage4_comparator), and non-overclaim."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_deterministic_time_window_adapter as window_module
from crypto_core.validation.deterministic_paper_replay_harness import verify_deterministic_paper_replay
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
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidenceError,
    PaperDeterministicTimeWindowEvidenceStatus,
    build_paper_deterministic_time_window_evidence,
    paper_deterministic_time_window_evidence_digest,
    paper_deterministic_time_window_evidence_to_dict,
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
    build_paper_governor_policy,
    decide_paper_governor,
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
from crypto_core.validation.paper_session_metrics_summary import (
    paper_session_metrics_summary_digest,
    summarize_paper_session_metrics,
)
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
from crypto_core.validation.paper_stage4_readiness_decision import decide_paper_stage4_readiness
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

_SYMBOL = "BTC-PERPETUAL"
_CORR = "corr-ep"
_REQ_CORR = "corr-req"
_RUN = "run-ep"
_EPISODE_ID = "e2e-1"
_POLICY_ID = "gov-policy-1"
_AGG_ID = "agg-1"

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


class _IntSub(int):
    """An ``int`` subclass (rejected by exact ``type(x) is int`` timestamp checks)."""


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
    agg_input = PaperSessionRealizedPnlAggregateInput(bridge=sbridge, session_input=prov, rollup_entries=(rollup,))
    agg = build_paper_session_realized_pnl_aggregate([agg_input], aggregate_id=_AGG_ID, correlation_id="corr-agg")
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=agg.aggregate_digest, correlation_id="corr-manifest"
    )
    record = build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id=_CORR
    )
    return record, manifest, episode, agg


def _ready_bridge_from(record, manifest, episode):
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


def _gov_policy(
    *,
    max_abs_realized_pnl: str = "1000",
    review_abs_realized_pnl: str = "500",
    max_closed_units: str = "100",
):
    return build_paper_governor_policy(
        policy_id=_POLICY_ID,
        min_computed_event_count=1,
        max_abs_realized_pnl=max_abs_realized_pnl,
        review_abs_realized_pnl=review_abs_realized_pnl,
        max_closed_units=max_closed_units,
    )


def _summary(policy=None):
    """A genuine ``PaperSessionMetricsSummary`` over one deterministic paper chain (default verdict CANDIDATE)."""
    record, manifest, episode, agg = _aligned()
    bridge = _ready_bridge_from(record, manifest, episode)
    policy = policy if policy is not None else _gov_policy()
    governor = decide_paper_governor(
        bridge,
        policy,
        expected_ledger_bridge_digest=bridge.ledger_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    replay = verify_deterministic_paper_replay(
        governor,
        governor,
        expected_original_digest=governor.decision_digest,
        expected_replay_digest=governor.decision_digest,
        run_id=_RUN,
        episode_id=_EPISODE_ID,
        correlation_id=_CORR,
    )
    readiness = decide_paper_stage4_readiness(
        replay,
        governor,
        expected_replay_result_digest=replay.replay_result_digest,
        expected_governor_decision_digest=governor.decision_digest,
        run_id=_RUN,
        episode_id=_EPISODE_ID,
        correlation_id=_CORR,
    )
    return summarize_paper_session_metrics(
        agg,
        manifest,
        readiness,
        expected_session_aggregate_digest=agg.aggregate_digest,
        expected_evidence_manifest_digest=manifest.manifest_digest,
        expected_readiness_decision_digest=readiness.readiness_decision_digest,
        run_id=_RUN,
        aggregate_id=agg.aggregate_id,
        correlation_id=_CORR,
    )


def _reseal_summary(summary):
    return replace(summary, summary_digest=paper_session_metrics_summary_digest(summary))


def _build(summary, **overrides):
    kwargs = {
        "expected_metrics_summary_digest": summary.summary_digest,
        "started_at_ns": 1_000,
        "stopped_at_ns": 2_000,
        "window_id": "window-1",
        "methodology_id": "paper-window-method-1",
        "run_id": _RUN,
        "aggregate_id": _AGG_ID,
        "correlation_id": _CORR,
        "sample_observation_count": 3,
    }
    kwargs.update(overrides)
    return build_paper_deterministic_time_window_evidence(summary, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy path + non-duplication
# --------------------------------------------------------------------------------------------------


def test_ready_eligible_window() -> None:
    summary = _summary()
    result = _build(summary)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    assert result.ready is True
    assert result.sample_eligible is True
    assert result.reason_codes == ()
    assert result.timestamp_policy == "injected_deterministic_ns.v1"
    assert result.started_at_ns == 1_000
    assert result.stopped_at_ns == 2_000
    assert result.window_duration_ns == 1_000
    assert result.sample_observation_count == 3
    # Consumes the summary (re-proven + bound); copies its gross/count fields by value (no recomputation).
    assert result.metrics_summary_digest == summary.summary_digest
    assert result.expected_metrics_summary_digest == summary.summary_digest
    assert result.summary_ready is True
    assert result.summary_readiness_verdict == "PAPER_STAGE4_CANDIDATE"
    assert result.session_bridge_count == summary.session_bridge_count
    assert result.event_count == summary.event_count
    assert result.closed_units_total == summary.closed_units_total
    assert result.realized_pnl_total == summary.realized_pnl_total
    assert result.abs_realized_pnl_total == summary.abs_realized_pnl_total
    assert result.market_symbol == _SYMBOL
    assert _is_hex64(result.time_window_digest)


def test_window_duration_is_integer_ns() -> None:
    result = _build(_summary(), started_at_ns=5_000_000_000, stopped_at_ns=5_000_000_777)
    assert type(result.window_duration_ns) is int
    assert result.window_duration_ns == 777


def test_evidence_digest_deterministic_and_recomputes() -> None:
    summary = _summary()
    a = _build(summary)
    b = _build(summary)
    assert a.time_window_digest == b.time_window_digest
    assert paper_deterministic_time_window_evidence_digest(a) == a.time_window_digest
    assert paper_deterministic_time_window_evidence_to_dict(a)["time_window_digest"] == a.time_window_digest


@pytest.mark.parametrize(
    "override",
    [
        {"window_id": "window-2"},
        {"methodology_id": "paper-window-method-2"},
        {"started_at_ns": 1_001},
        {"stopped_at_ns": 2_001},
        {"sample_observation_count": 4},
        {"metadata": {"note": "x"}},
    ],
)
def test_changed_bound_field_changes_digest(override: dict[str, object]) -> None:
    summary = _summary()
    base = _build(summary)
    other = _build(summary, **override)
    assert base.time_window_digest != other.time_window_digest


def test_review_summary_ready_but_not_eligible() -> None:
    summary = _summary(policy=_gov_policy(review_abs_realized_pnl="100"))  # verdict REVIEW, summary.ready False
    result = _build(summary)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    assert result.ready is True
    assert result.sample_eligible is False
    assert result.summary_ready is False
    assert result.summary_readiness_verdict == "PAPER_REVIEW_REQUIRED"
    assert any("window_not_sample_eligible" in code for code in result.reason_codes)


def test_zero_duration_ready_but_not_eligible() -> None:
    result = _build(_summary(), started_at_ns=1_000, stopped_at_ns=1_000)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    assert result.window_duration_ns == 0
    assert result.sample_eligible is False
    assert any("window_not_sample_eligible" in code for code in result.reason_codes)


def test_zero_observations_not_eligible() -> None:
    result = _build(_summary(), sample_observation_count=0)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    assert result.sample_eligible is False


# --------------------------------------------------------------------------------------------------
# 2. Summary digest / provenance
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_summary_digest_rejects() -> None:
    result = _build(_summary(), expected_metrics_summary_digest="a" * 64)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("metrics_summary_digest_mismatch" in code for code in result.reason_codes)


def test_forged_summary_self_digest_rejects() -> None:
    summary = _summary()
    forged = replace(summary, summary_digest="0" * 64)  # tampered WITHOUT reseal
    result = _build(forged, expected_metrics_summary_digest="0" * 64)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("metrics_summary_digest_mismatch" in code for code in result.reason_codes)


def test_input_summary_not_mutated() -> None:
    summary = _summary()
    before = summary.summary_digest
    _build(summary)
    assert summary.summary_digest == before


# --------------------------------------------------------------------------------------------------
# 3. Summary safety / invariants
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_summary_raises() -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="metrics_summary_malformed"):
        build_paper_deterministic_time_window_evidence(
            {"not": "a-summary"},  # type: ignore[arg-type]
            expected_metrics_summary_digest="a" * 64,
            started_at_ns=1,
            stopped_at_ns=2,
            window_id="window-1",
            methodology_id="m-1",
            run_id=_RUN,
            aggregate_id=_AGG_ID,
            correlation_id=_CORR,
        )


def test_rejected_summary_rejects() -> None:
    rejected = summarize_or_rejected()
    result = _build(rejected, expected_metrics_summary_digest=rejected.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_not_ready" in code for code in result.reason_codes)


def summarize_or_rejected():
    # A genuine REJECTED metrics summary (wrong aggregate anchor) — still digest-sealed.
    record, manifest, episode, agg = _aligned()
    bridge = _ready_bridge_from(record, manifest, episode)
    governor = decide_paper_governor(
        bridge,
        _gov_policy(),
        expected_ledger_bridge_digest=bridge.ledger_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    replay = verify_deterministic_paper_replay(
        governor,
        governor,
        expected_original_digest=governor.decision_digest,
        expected_replay_digest=governor.decision_digest,
        run_id=_RUN,
        episode_id=_EPISODE_ID,
        correlation_id=_CORR,
    )
    readiness = decide_paper_stage4_readiness(
        replay,
        governor,
        expected_replay_result_digest=replay.replay_result_digest,
        expected_governor_decision_digest=governor.decision_digest,
        run_id=_RUN,
        episode_id=_EPISODE_ID,
        correlation_id=_CORR,
    )
    return summarize_paper_session_metrics(
        agg,
        manifest,
        readiness,
        expected_session_aggregate_digest="a" * 64,  # wrong anchor -> REJECTED summary
        expected_evidence_manifest_digest=manifest.manifest_digest,
        expected_readiness_decision_digest=readiness.readiness_decision_digest,
        run_id=_RUN,
        aggregate_id=agg.aggregate_id,
        correlation_id=_CORR,
    )


def test_unsafe_summary_flag_rejects() -> None:
    summary = _reseal_summary(replace(_summary(), prdv4_stage4_complete=True))
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_unsafe_flags" in code for code in result.reason_codes)


def test_sharpe_overclaim_summary_flag_rejects() -> None:
    summary = _reseal_summary(replace(_summary(), sharpe_computed=True))
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_unsafe_flags" in code for code in result.reason_codes)


def test_summary_ready_verdict_inconsistent_rejects() -> None:
    summary = _reseal_summary(replace(_summary(), ready=False))  # CANDIDATE but ready False
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_ready_verdict_inconsistent" in code for code in result.reason_codes)


def test_incoherent_counts_reject() -> None:
    summary = _reseal_summary(replace(_summary(), computed_event_count=999))  # > event_count
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_counts_invalid" in code for code in result.reason_codes)


def test_negative_count_rejects() -> None:
    summary = _reseal_summary(replace(_summary(), episode_count_total=-1))
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_counts_invalid" in code for code in result.reason_codes)


def test_abs_realized_mismatch_rejects() -> None:
    summary = _reseal_summary(replace(_summary(), abs_realized_pnl_total="999"))
    result = _build(summary, expected_metrics_summary_digest=summary.summary_digest)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("summary_abs_mismatch" in code for code in result.reason_codes)


def test_run_id_mismatch_rejects() -> None:
    result = _build(_summary(), run_id="other-run")
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("run_id_mismatch" in code for code in result.reason_codes)


def test_aggregate_id_mismatch_rejects() -> None:
    result = _build(_summary(), aggregate_id="other-agg")
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("aggregate_id_mismatch" in code for code in result.reason_codes)


def test_correlation_id_mismatch_rejects() -> None:
    result = _build(_summary(), correlation_id="corr-other")
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("correlation_id_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 4. Injected-int timestamp validation
# --------------------------------------------------------------------------------------------------


def test_start_after_stop_rejects() -> None:
    result = _build(_summary(), started_at_ns=2_000, stopped_at_ns=1_000)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("window_order_invalid" in code for code in result.reason_codes)


def test_negative_start_rejects() -> None:
    result = _build(_summary(), started_at_ns=-1, stopped_at_ns=1_000)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("started_at_ns_negative" in code for code in result.reason_codes)


def test_negative_stop_rejects() -> None:
    result = _build(_summary(), started_at_ns=0, stopped_at_ns=-5)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("stopped_at_ns_negative" in code for code in result.reason_codes)


@pytest.mark.parametrize("bad", [True, 1.0, "1000", _IntSub(1_000)])
def test_non_exact_int_start_raises(bad: object) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="started_at_ns_invalid"):
        _build(_summary(), started_at_ns=bad)


@pytest.mark.parametrize("bad", [True, 2.0, "2000", _IntSub(2_000)])
def test_non_exact_int_stop_raises(bad: object) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="stopped_at_ns_invalid"):
        _build(_summary(), stopped_at_ns=bad)


@pytest.mark.parametrize("bad", [True, 3.0, "3"])
def test_non_exact_int_observation_count_raises(bad: object) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="sample_observation_count_invalid"):
        _build(_summary(), sample_observation_count=bad)


def test_negative_observation_count_rejects() -> None:
    result = _build(_summary(), sample_observation_count=-1)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert any("sample_observation_count_negative" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Suspicious clock-token rejection
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "wall_clock",
        "datetime.now",
        "time.time_ns",
        "perf_counter",
        "utcnow",
        "server_time",
        "exchange_time",
        "real_time",
        "clock",
    ],
)
def test_clock_token_in_window_id_raises(token: str) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="clock_token_forbidden"):
        _build(_summary(), window_id=f"window-{token}")


def test_clock_token_in_methodology_id_raises() -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="clock_token_forbidden"):
        _build(_summary(), methodology_id="datetime.now-method")


def test_clock_token_in_metadata_key_raises() -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="clock_token_forbidden"):
        _build(_summary(), metadata={"server_time": "x"})


def test_clock_token_in_metadata_value_raises() -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="clock_token_forbidden"):
        _build(_summary(), metadata={"note": "captured via perf_counter"})


# --------------------------------------------------------------------------------------------------
# 6. Canonical / adversarial / determinism
# --------------------------------------------------------------------------------------------------


def test_str_subclass_window_id_raises() -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="window_id_invalid"):
        _build(_summary(), window_id=_LiarStr("window-1"))


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="metadata_malformed"):
        _build(_summary(), metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_digest_raises(bad: str) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="expected_metrics_summary_digest_invalid"):
        _build(_summary(), expected_metrics_summary_digest=bad)


@pytest.mark.parametrize("scope_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(scope_id: str) -> None:
    with pytest.raises(PaperDeterministicTimeWindowEvidenceError, match="scope_violation"):
        _build(_summary(), methodology_id=scope_id)


def test_result_frozen() -> None:
    result = _build(_summary())
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


def test_reason_codes_sorted_stable() -> None:
    result = _build(_summary(), run_id="other-run", started_at_ns=2_000, stopped_at_ns=1_000)
    assert result.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


# --------------------------------------------------------------------------------------------------
# 7. Time-free boundary / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_no_time_or_sharpe_derived_fields() -> None:
    payload = paper_deterministic_time_window_evidence_to_dict(_build(_summary()))
    # Injected integer ns is present; measured/derived time-series fields are NOT.
    assert payload["started_at_ns"] == 1_000
    assert payload["window_duration_ns"] == 1_000
    assert payload["real_wall_clock_used"] is False
    assert payload["timestamp_origin_proven"] is False
    for forbidden_key in (
        "session_duration_days",
        "duration_days",
        "paper_sharpe",
        "sharpe",
        "annualized_return",
        "return_series",
    ):
        assert forbidden_key not in payload


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(window_module.__file__).read_text(encoding="utf-8"))
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
        "duckdb",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules <= {"validation"}


def test_no_forbidden_module_or_clock_symbols() -> None:
    source = Path(window_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
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
        assert "readiness" not in module.split("."), module
        assert "paper_adapter" not in module, module
        assert "stage4_comparator" not in module, module
        assert "deribit" not in module, module
        assert "bist" not in module, module
    # No stage4-comparator coupling and no real-clock CALLS anywhere in the source. Use call-style patterns so
    # neither the module's own forbidden-token string literals (scope guard) nor its docstring prose naming the
    # excluded symbols false-positive; the AST import loop above already proves stage4_comparator is not imported.
    for banned_symbol in (
        "Stage4PaperSummary(",
        "compare_stage4(",
        "perf_counter(",
        "monotonic(",
        "time.time(",
        "time.time_ns(",
        "datetime.now(",
        "datetime.utcnow(",
    ):
        assert banned_symbol not in source, banned_symbol


def test_public_api_exact() -> None:
    assert set(window_module.__all__) == {
        "PaperDeterministicTimeWindowEvidence",
        "PaperDeterministicTimeWindowEvidenceError",
        "PaperDeterministicTimeWindowEvidenceStatus",
        "build_paper_deterministic_time_window_evidence",
        "paper_deterministic_time_window_evidence_digest",
        "paper_deterministic_time_window_evidence_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "venue", "sharpe", "wallclock")
    for name in window_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# --------------------------------------------------------------------------------------------------
# 8. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags() -> None:
    payload = paper_deterministic_time_window_evidence_to_dict(_build(_summary()))
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
        "sharpe_computed",
        "return_series_computed",
        "thirty_day_gate_satisfied",
        "stage4_comparator_invoked",
        "real_wall_clock_used",
        "timestamp_origin_proven",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True
    assert payload["injected_deterministic_time_window"] is True
