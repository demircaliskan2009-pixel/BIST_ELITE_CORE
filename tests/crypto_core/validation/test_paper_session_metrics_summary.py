"""Tests for the paper session metrics summary (§10.4.1) — deterministic, paper-only, TIME-FREE summary that
binds an existing ``PaperSessionRealizedPnlAggregate`` (via its admitted evidence manifest) to its §7.7
``PaperStage4ReadinessDecision`` verdict.

Genuine artifacts are built end-to-end through the merged paper chain (the same realized event flows into both
the session aggregate/manifest and the governor→replay→readiness verdict, so the strong aggregate↔manifest↔
readiness binding is real); adversarial variants are derived by ``replace(...)`` + reseal. Covers the
duplicate-precheck added value, candidate/review/block context paths, digest/provenance, STRONG same-admitted-
chain binding (foreign-aggregate membership-only regression), the readiness ready/verdict invariant, cross-id,
status/safety, the time-free boundary, canonical/adversarial, forbidden-surface exclusion (AST), non-overclaim."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_session_metrics_summary as summary_module
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
    PaperSessionMetricsSummaryError,
    PaperSessionMetricsSummaryStatus,
    paper_session_metrics_summary_digest,
    paper_session_metrics_summary_to_dict,
    summarize_paper_session_metrics,
)
from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregateInput,
    PaperSessionRealizedPnlAggregateStatus,
    build_paper_session_realized_pnl_aggregate,
    paper_session_realized_pnl_aggregate_digest,
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
    decide_paper_stage4_readiness,
    paper_stage4_readiness_decision_digest,
)
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
    return record, manifest, episode, agg, agg_input


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


def _policy(
    *,
    min_computed_event_count: int = 1,
    max_abs_realized_pnl: str = "1000",
    review_abs_realized_pnl: str = "500",
    max_closed_units: str = "100",
):
    return build_paper_governor_policy(
        policy_id=_POLICY_ID,
        min_computed_event_count=min_computed_event_count,
        max_abs_realized_pnl=max_abs_realized_pnl,
        review_abs_realized_pnl=review_abs_realized_pnl,
        max_closed_units=max_closed_units,
    )


def _full_chain(policy=None):
    """Build one genuine deterministic paper chain → (aggregate, manifest, readiness, aggregate_input)."""
    record, manifest, episode, agg, agg_input = _aligned()
    bridge = _ready_bridge_from(record, manifest, episode)
    policy = policy if policy is not None else _policy()
    governor = decide_paper_governor(
        bridge,
        policy,
        expected_ledger_bridge_digest=bridge.ledger_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    # A deterministic replay of the same decision is digest-identical -> MATCHED.
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
    return agg, manifest, readiness, agg_input


def _chain_inputs(policy=None):
    agg, manifest, readiness, _ = _full_chain(policy)
    return agg, manifest, readiness


def _reseal_aggregate(aggregate):
    return replace(aggregate, aggregate_digest=paper_session_realized_pnl_aggregate_digest(aggregate))


def _reseal_readiness(readiness):
    return replace(readiness, readiness_decision_digest=paper_stage4_readiness_decision_digest(readiness))


def _summarize(aggregate, manifest, readiness, **overrides):
    kwargs = {
        "expected_session_aggregate_digest": aggregate.aggregate_digest,
        "expected_evidence_manifest_digest": manifest.manifest_digest,
        "expected_readiness_decision_digest": readiness.readiness_decision_digest,
        "run_id": _RUN,
        "aggregate_id": aggregate.aggregate_id,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return summarize_paper_session_metrics(aggregate, manifest, readiness, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Duplicate-precheck added value + happy candidate path
# --------------------------------------------------------------------------------------------------


def test_candidate_ready_and_adds_value_over_aggregate() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness)
    assert result.status is PaperSessionMetricsSummaryStatus.READY
    assert result.ready is True
    assert result.reason_codes == ()
    # Reuses aggregate digest + binds the manifest + the §7.7 readiness digest/verdict (NOT in the aggregate).
    assert result.session_aggregate_digest == aggregate.aggregate_digest
    assert result.evidence_manifest_digest == manifest.manifest_digest
    assert result.readiness_decision_digest == readiness.readiness_decision_digest
    assert result.readiness_verdict == "PAPER_STAGE4_CANDIDATE"
    assert result.readiness_status == "DECIDED"
    # Time-free gross/count metrics mirrored from the aggregate (not recomputed).
    assert result.session_bridge_count == aggregate.session_bridge_count
    assert result.event_count == aggregate.event_count
    assert result.computed_event_count == aggregate.computed_event_count
    assert result.closed_units_total == aggregate.closed_units_total
    assert result.realized_pnl_total == aggregate.realized_pnl_total
    assert result.source_event_digest_count == len(aggregate.source_event_digests)
    assert result.realized_pnl_event_digest == readiness.realized_pnl_event_digest
    assert _is_hex64(result.summary_digest)


def test_abs_realized_total_is_magnitude_of_gross() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness)
    # The aligned chain produces realized_pnl=-200; abs magnitude is 200 (only derived metric).
    assert result.realized_pnl_total == "-200"
    assert result.abs_realized_pnl_total == "200"


def test_summary_digest_deterministic_and_recomputes() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    a = _summarize(aggregate, manifest, readiness)
    b = _summarize(aggregate, manifest, readiness)
    assert a.summary_digest == b.summary_digest
    assert paper_session_metrics_summary_digest(a) == a.summary_digest
    assert paper_session_metrics_summary_to_dict(a)["summary_digest"] == a.summary_digest


def test_changed_bound_field_changes_summary_digest() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    base = _summarize(aggregate, manifest, readiness)
    other = _summarize(aggregate, manifest, readiness, metadata={"note": "second"})
    assert base.summary_digest != other.summary_digest


# --------------------------------------------------------------------------------------------------
# 2. Readiness context paths (no upgrade)
# --------------------------------------------------------------------------------------------------


def test_review_required_summarized_not_ready() -> None:
    aggregate, manifest, readiness = _chain_inputs(policy=_policy(review_abs_realized_pnl="100"))
    result = _summarize(aggregate, manifest, readiness)
    assert result.status is PaperSessionMetricsSummaryStatus.READY
    assert result.ready is False
    assert result.readiness_verdict == "PAPER_REVIEW_REQUIRED"
    assert any("readiness_review_required" in code for code in result.reason_codes)


def test_blocked_summarized_not_ready() -> None:
    aggregate, manifest, readiness = _chain_inputs(
        policy=_policy(review_abs_realized_pnl="50", max_abs_realized_pnl="100")
    )
    result = _summarize(aggregate, manifest, readiness)
    assert result.status is PaperSessionMetricsSummaryStatus.READY
    assert result.ready is False
    assert result.readiness_verdict == "PAPER_BLOCKED"
    assert any("readiness_blocked" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 3. Digest / provenance
# --------------------------------------------------------------------------------------------------


def test_wrong_aggregate_anchor_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, expected_session_aggregate_digest="a" * 64)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("session_aggregate_digest_mismatch" in code for code in result.reason_codes)


def test_wrong_manifest_anchor_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, expected_evidence_manifest_digest="a" * 64)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("evidence_manifest_digest_mismatch" in code for code in result.reason_codes)


def test_wrong_readiness_anchor_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, expected_readiness_decision_digest="a" * 64)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_decision_digest_mismatch" in code for code in result.reason_codes)


def test_forged_aggregate_self_digest_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    forged = replace(aggregate, aggregate_digest="0" * 64)  # tampered WITHOUT reseal
    result = _summarize(forged, manifest, readiness, expected_session_aggregate_digest="0" * 64)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("session_aggregate_digest_mismatch" in code for code in result.reason_codes)


def test_forged_readiness_self_digest_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    forged = replace(readiness, readiness_decision_digest="0" * 64)  # tampered WITHOUT reseal
    result = _summarize(aggregate, manifest, forged, expected_readiness_decision_digest="0" * 64)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_decision_digest_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 4. STRONG same-admitted-chain binding (P1 repair) — membership alone is insufficient
# --------------------------------------------------------------------------------------------------


def test_foreign_aggregate_with_same_event_rejects() -> None:
    # A DIFFERENT but fully valid aggregate built from the same input bundle (so it CONTAINS the same realized
    # event → event membership passes) is NOT the aggregate the manifest admitted (different aggregate digest).
    aggregate, manifest, readiness, agg_input = _full_chain()
    foreign = build_paper_session_realized_pnl_aggregate(
        [agg_input], aggregate_id="agg-foreign", correlation_id="corr-agg"
    )
    assert foreign.aggregate_digest != aggregate.aggregate_digest
    # Event membership alone WOULD have passed (the foreign aggregate contains the same realized event).
    assert readiness.realized_pnl_event_digest in foreign.source_event_digests
    result = _summarize(
        foreign,
        manifest,
        readiness,
        expected_session_aggregate_digest=foreign.aggregate_digest,
        aggregate_id="agg-foreign",
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert result.ready is False
    assert any("readiness_aggregate_chain_mismatch" in code for code in result.reason_codes)


def test_readiness_manifest_chain_mismatch_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_readiness(replace(readiness, manifest_digest="c" * 64))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_manifest_chain_mismatch" in code for code in result.reason_codes)


def test_realized_event_not_in_aggregate_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_readiness(replace(readiness, realized_pnl_event_digest="b" * 64))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("realized_pnl_event_not_in_aggregate" in code for code in result.reason_codes)


def test_market_symbol_mismatch_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_readiness(replace(readiness, market_symbol="ETH-PERPETUAL"))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("market_symbol_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Readiness ready/verdict invariant (P2 repair)
# --------------------------------------------------------------------------------------------------


def test_candidate_ready_false_inconsistent_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()  # CANDIDATE, ready True
    tampered = _reseal_readiness(replace(readiness, ready=False))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert result.ready is False
    assert any("readiness_ready_verdict_inconsistent" in code for code in result.reason_codes)


def test_review_ready_true_inconsistent_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs(policy=_policy(review_abs_realized_pnl="100"))  # REVIEW, ready False
    tampered = _reseal_readiness(replace(readiness, ready=True))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_ready_verdict_inconsistent" in code for code in result.reason_codes)


def test_blocked_ready_true_inconsistent_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs(
        policy=_policy(review_abs_realized_pnl="50", max_abs_realized_pnl="100")
    )  # BLOCK, ready False
    tampered = _reseal_readiness(replace(readiness, ready=True))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_ready_verdict_inconsistent" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 6. Cross-id
# --------------------------------------------------------------------------------------------------


def test_run_id_mismatch_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, run_id="other-run")
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_run_id_mismatch" in code for code in result.reason_codes)


def test_aggregate_id_mismatch_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, aggregate_id="other-agg")
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("aggregate_id_mismatch" in code for code in result.reason_codes)


def test_correlation_id_mismatch_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, correlation_id="corr-other")
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("readiness_correlation_id_mismatch" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 7. Status / safety (untrusted -> REJECTED, no partial READY)
# --------------------------------------------------------------------------------------------------


def test_aggregate_not_computed_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_aggregate(replace(aggregate, status=PaperSessionRealizedPnlAggregateStatus.REJECTED))
    result = _summarize(tampered, manifest, readiness, expected_session_aggregate_digest=tampered.aggregate_digest)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("session_aggregate_not_computed" in code for code in result.reason_codes)


def test_unsafe_aggregate_flag_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_aggregate(replace(aggregate, order_routed=True))
    result = _summarize(tampered, manifest, readiness, expected_session_aggregate_digest=tampered.aggregate_digest)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("session_aggregate_unsafe_flags" in code for code in result.reason_codes)


def test_negative_count_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_aggregate(replace(aggregate, episode_count_total=-1))
    result = _summarize(tampered, manifest, readiness, expected_session_aggregate_digest=tampered.aggregate_digest)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("episode_count_total_invalid" in code for code in result.reason_codes)


def test_unsafe_readiness_flag_rejects() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_readiness(replace(readiness, prdv4_stage4_complete=True))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert result.ready is False
    assert any("readiness_decision_unsafe_flags" in code for code in result.reason_codes)


def test_no_partial_ready_under_unsafe_input() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_aggregate(replace(aggregate, live_api_called=True))
    result = _summarize(tampered, manifest, readiness, expected_session_aggregate_digest=tampered.aggregate_digest)
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert result.ready is False


# --------------------------------------------------------------------------------------------------
# 8. Time-free boundary
# --------------------------------------------------------------------------------------------------


def test_time_free_flags_false_and_no_time_fields() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    payload = paper_session_metrics_summary_to_dict(_summarize(aggregate, manifest, readiness))
    assert payload["sharpe_computed"] is False
    assert payload["return_series_computed"] is False
    assert payload["thirty_day_gate_satisfied"] is False
    # No wall-clock / time-series fields are present at all.
    for forbidden_key in ("started_at_ns", "stopped_at_ns", "session_duration_days", "sharpe", "paper_sharpe"):
        assert forbidden_key not in payload


# --------------------------------------------------------------------------------------------------
# 9. Canonical / adversarial
# --------------------------------------------------------------------------------------------------


def test_str_subclass_correlation_id_raises() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="correlation_id_invalid"):
        _summarize(aggregate, manifest, readiness, correlation_id=_LiarStr("corr-ep"))


def test_equality_liar_event_digest_cannot_bypass() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    tampered = _reseal_readiness(replace(readiness, realized_pnl_event_digest=_LiarStr("b" * 64)))
    result = _summarize(
        aggregate, manifest, tampered, expected_readiness_decision_digest=tampered.readiness_decision_digest
    )
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert any("realized_pnl_event_not_in_aggregate" in code for code in result.reason_codes)


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    aggregate, manifest, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="metadata_malformed"):
        _summarize(aggregate, manifest, readiness, metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_digest_raises(bad: str) -> None:
    aggregate, manifest, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="expected_session_aggregate_digest_invalid"):
        _summarize(aggregate, manifest, readiness, expected_session_aggregate_digest=bad)


def test_wrong_typed_aggregate_raises() -> None:
    _, manifest, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="session_aggregate_malformed"):
        summarize_paper_session_metrics(
            {"not": "an-aggregate"},  # type: ignore[arg-type]
            manifest,
            readiness,
            expected_session_aggregate_digest="a" * 64,
            expected_evidence_manifest_digest="a" * 64,
            expected_readiness_decision_digest="a" * 64,
            run_id=_RUN,
            aggregate_id=_AGG_ID,
            correlation_id=_CORR,
        )


def test_wrong_typed_manifest_raises() -> None:
    aggregate, _, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="evidence_manifest_malformed"):
        summarize_paper_session_metrics(
            aggregate,
            {"not": "a-manifest"},  # type: ignore[arg-type]
            readiness,
            expected_session_aggregate_digest="a" * 64,
            expected_evidence_manifest_digest="a" * 64,
            expected_readiness_decision_digest="a" * 64,
            run_id=_RUN,
            aggregate_id=_AGG_ID,
            correlation_id=_CORR,
        )


def test_wrong_typed_readiness_raises() -> None:
    aggregate, manifest, _ = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="readiness_decision_malformed"):
        summarize_paper_session_metrics(
            aggregate,
            manifest,
            {"not": "a-readiness"},  # type: ignore[arg-type]
            expected_session_aggregate_digest="a" * 64,
            expected_evidence_manifest_digest="a" * 64,
            expected_readiness_decision_digest="a" * 64,
            run_id=_RUN,
            aggregate_id=_AGG_ID,
            correlation_id=_CORR,
        )


@pytest.mark.parametrize("scope_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(scope_id: str) -> None:
    aggregate, manifest, readiness = _chain_inputs()
    with pytest.raises(PaperSessionMetricsSummaryError, match="scope_violation"):
        _summarize(aggregate, manifest, readiness, correlation_id=scope_id)


def test_inputs_not_mutated() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    aggregate_digest_before = aggregate.aggregate_digest
    manifest_digest_before = manifest.manifest_digest
    readiness_digest_before = readiness.readiness_decision_digest
    _summarize(aggregate, manifest, readiness)
    assert aggregate.aggregate_digest == aggregate_digest_before
    assert manifest.manifest_digest == manifest_digest_before
    assert readiness.readiness_decision_digest == readiness_digest_before


def test_result_frozen() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness)
    with pytest.raises(FrozenInstanceError):
        result.ready = True  # type: ignore[misc]


def test_reason_codes_sorted_stable() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    result = _summarize(aggregate, manifest, readiness, run_id="other-run", aggregate_id="other-agg")
    assert result.status is PaperSessionMetricsSummaryStatus.REJECTED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


# --------------------------------------------------------------------------------------------------
# 10. Immutability / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(summary_module.__file__).read_text(encoding="utf-8"))
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
    tree = ast.parse(Path(summary_module.__file__).read_text(encoding="utf-8"))
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
        assert "paper_live_service" not in module, module
        assert "paper_shadow_session_controller" not in module, module
        assert "deribit" not in module, module
        assert "bist" not in module, module


def test_public_api_exact() -> None:
    assert set(summary_module.__all__) == {
        "PaperSessionMetricsSummary",
        "PaperSessionMetricsSummaryError",
        "PaperSessionMetricsSummaryStatus",
        "paper_session_metrics_summary_digest",
        "paper_session_metrics_summary_to_dict",
        "summarize_paper_session_metrics",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "place_order", "venue", "sharpe")
    for name in summary_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# --------------------------------------------------------------------------------------------------
# 11. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags_false_and_bound() -> None:
    aggregate, manifest, readiness = _chain_inputs()
    payload = paper_session_metrics_summary_to_dict(_summarize(aggregate, manifest, readiness))
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
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True
