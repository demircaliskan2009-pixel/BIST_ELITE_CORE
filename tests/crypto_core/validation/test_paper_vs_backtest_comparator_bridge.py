"""Tests for the paper-vs-backtest comparator bridge (§10.4.3) — deterministic, paper-only, fail-closed
BRIDGE-READINESS evidence over a ``PaperDeterministicTimeWindowEvidence`` (§10.4.2).

A genuine time-window evidence is built end-to-end through the merged paper chain (aggregate + manifest + §7.7
readiness → metrics summary → injected time window); adversarial variants are derived by ``replace(...)`` +
reseal. Covers duplicate-precheck/non-comparator-execution, the happy BLOCKED bridge path, window digest/
provenance, window invariant re-proof, the missing comparator inputs, the optional backtest baseline, suspicious
token rejection, forbidden-surface exclusion (alias-resistant AST: no comparator EXECUTION, no
``Stage4PaperSummary`` construction), and non-overclaim."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_vs_backtest_comparator_bridge as bridge_module
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
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    build_paper_deterministic_time_window_evidence,
    paper_deterministic_time_window_evidence_digest,
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
from crypto_core.validation.paper_session_metrics_summary import summarize_paper_session_metrics
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
from crypto_core.validation.paper_vs_backtest_comparator_bridge import (
    PaperVsBacktestComparatorBridgeError,
    PaperVsBacktestComparatorBridgeStatus,
    build_paper_vs_backtest_comparator_bridge,
    paper_vs_backtest_comparator_bridge_digest,
    paper_vs_backtest_comparator_bridge_to_dict,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    build_stage4_backtest_baseline,
    stage4_backtest_baseline_to_dict,
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

_MISSING_V1 = (
    "paper_sharpe",
    "paper_edge_id",
    "paper_return_series",
    "paper_vs_backtest_methodology",
    "thirty_day_gate",
)


class _LiarStr(str):
    """A ``str`` subclass that lies about equality (defeated only by exact ``type(x) is str`` checks)."""

    def __eq__(self, other: object) -> bool:  # noqa: D401 - test double
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _WindowSubclass(PaperDeterministicTimeWindowEvidence):
    """Should be rejected by exact artifact type checks."""


class _BaselineSubclass(Stage4BacktestBaseline):
    """Should be rejected by exact artifact type checks."""


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


# --------------------------------------------------------------------------------------------------
# Genuine end-to-end chain (mirrors the merged §10.4.2 time-window adapter fixtures)
# --------------------------------------------------------------------------------------------------


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


def _window(summary=None, **overrides):
    summary = summary if summary is not None else _summary()
    kwargs: dict[str, object] = {
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
    return build_paper_deterministic_time_window_evidence(summary, **kwargs)  # type: ignore[arg-type]


def _reseal_window(window):
    return replace(window, time_window_digest=paper_deterministic_time_window_evidence_digest(window))


def _build_bridge(window=None, **overrides):
    window = window if window is not None else _window()
    kwargs: dict[str, object] = {
        "expected_time_window_digest": window.time_window_digest,
        "bridge_id": "bridge-1",
        "paper_id": "paper-1",
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_vs_backtest_comparator_bridge(window, **kwargs)


def _baseline(**overrides) -> Stage4BacktestBaseline:
    kwargs: dict[str, object] = {
        "baseline_id": "baseline-1",
        "edge_id": "edge-alpha",
        "as_of_ns": 1_700_000_000_000_000_000,
        "backtest_sharpe": 1.5,
        "backtest_hit_rate": 0.55,
    }
    kwargs.update(overrides)
    return build_stage4_backtest_baseline(**kwargs)  # type: ignore[arg-type]


def _baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    canonical = json.dumps(
        stage4_backtest_baseline_to_dict(baseline),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# 1. Phase scope / no comparator execution
# --------------------------------------------------------------------------------------------------


def test_ready_bridge_does_not_invoke_comparator() -> None:
    result = _build_bridge()
    assert result.stage4_comparator_invoked is False
    assert result.comparison_ready is False
    assert result.paper_vs_backtest_comparison_ready is False


def test_module_does_not_construct_stage4_paper_summary() -> None:
    source = Path(bridge_module.__file__).read_text(encoding="utf-8")
    # The comparator is never executed and no paper summary is ever constructed in the missing-input path.
    assert "Stage4PaperSummary(" not in source
    assert "compare_stage4(" not in source


# --------------------------------------------------------------------------------------------------
# 2. Happy BLOCKED bridge path
# --------------------------------------------------------------------------------------------------


def test_ready_blocked_bridge() -> None:
    window = _window()
    result = _build_bridge(window)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.READY
    assert result.ready is True
    assert result.comparison_ready is False
    assert result.stage4_comparator_invoked is False
    assert result.edge_id_unproven is True
    assert result.backtest_baseline_present is False
    # Window provenance carried + bound.
    assert result.time_window_digest == window.time_window_digest
    assert result.expected_time_window_digest == window.time_window_digest
    assert result.metrics_summary_digest == window.metrics_summary_digest
    assert result.market_symbol == _SYMBOL
    assert result.sample_eligible is True
    assert result.started_at_ns == 1_000
    assert result.stopped_at_ns == 2_000
    assert result.window_duration_ns == 1_000
    # Missing paper-side comparator inputs enumerated; baseline absent so it is missing too.
    for token in (*_MISSING_V1, "backtest_baseline"):
        assert token in result.missing_comparator_inputs
    assert "paper_sample_eligibility" not in result.missing_comparator_inputs  # eligible window
    assert any("comparison_not_ready_missing_inputs" in code for code in result.reason_codes)
    assert _is_hex64(result.bridge_digest)


def test_missing_inputs_sorted_unique() -> None:
    result = _build_bridge()
    assert list(result.missing_comparator_inputs) == sorted(set(result.missing_comparator_inputs))


# --------------------------------------------------------------------------------------------------
# 3. Window digest / provenance
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_window_digest_rejects() -> None:
    result = _build_bridge(_window(), expected_time_window_digest="a" * 64)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_digest_mismatch" in code for code in result.reason_codes)


def test_forged_window_self_digest_rejects() -> None:
    window = _window()
    forged = replace(window, time_window_digest="0" * 64)  # tampered WITHOUT reseal
    result = _build_bridge(forged, expected_time_window_digest="0" * 64)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_digest_mismatch" in code for code in result.reason_codes)


def test_input_window_not_mutated() -> None:
    window = _window()
    before = window.time_window_digest
    _build_bridge(window)
    assert window.time_window_digest == before


def test_bridge_digest_deterministic_and_recomputes() -> None:
    window = _window()
    a = _build_bridge(window)
    b = _build_bridge(window)
    assert a.bridge_digest == b.bridge_digest
    assert paper_vs_backtest_comparator_bridge_digest(a) == a.bridge_digest
    assert paper_vs_backtest_comparator_bridge_to_dict(a)["bridge_digest"] == a.bridge_digest


@pytest.mark.parametrize(
    "override",
    [
        {"bridge_id": "bridge-2"},
        {"paper_id": "paper-2"},
        {"correlation_id": "corr-other"},
        {"metadata": {"note": "x"}},
    ],
)
def test_changed_bound_field_changes_digest(override: dict[str, object]) -> None:
    window = _window()
    base = _build_bridge(window)
    other = _build_bridge(window, **override)
    assert base.bridge_digest != other.bridge_digest


def test_changed_window_changes_bridge_digest() -> None:
    base = _build_bridge(_window())
    other_window = _window(sample_observation_count=7)
    other = _build_bridge(other_window)
    assert base.time_window_digest != other.time_window_digest
    assert base.bridge_digest != other.bridge_digest


def test_baseline_presence_changes_digest() -> None:
    window = _window()
    no_baseline = _build_bridge(window)
    baseline = _baseline()
    with_baseline = _build_bridge(
        window,
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=_baseline_digest(baseline),
        baseline_id="baseline-1",
    )
    assert no_baseline.bridge_digest != with_baseline.bridge_digest


# --------------------------------------------------------------------------------------------------
# 4. Time-window invariant re-proof
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_window_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="time_window_evidence_malformed"):
        build_paper_vs_backtest_comparator_bridge(
            {"not": "a-window"},  # type: ignore[arg-type]
            expected_time_window_digest="a" * 64,
            bridge_id="bridge-1",
            paper_id="paper-1",
            correlation_id=_CORR,
        )


def test_window_subclass_raises() -> None:
    window = _window()
    subclass_window = _WindowSubclass(
        **{field.name: getattr(window, field.name) for field in fields(PaperDeterministicTimeWindowEvidence)}
    )
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="time_window_evidence_malformed"):
        _build_bridge(subclass_window, expected_time_window_digest=subclass_window.time_window_digest)


def test_window_unsafe_flags_reject() -> None:
    window = _reseal_window(replace(_window(), prdv4_stage4_complete=True))
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_unsafe_flags" in code for code in result.reason_codes)


def test_window_sharpe_overclaim_rejects() -> None:
    window = _reseal_window(replace(_window(), sharpe_computed=True))
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_unsafe_flags" in code for code in result.reason_codes)


def test_rejected_window_blocks_as_not_ready() -> None:
    # A genuine REJECTED time window (wrong summary anchor) is still digest-sealed; the bridge must refuse it.
    window = _window(expected_metrics_summary_digest="a" * 64)
    assert window.status is PaperDeterministicTimeWindowEvidenceStatus.REJECTED
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_not_ready" in code for code in result.reason_codes)


def test_sample_eligible_false_blocks_comparison() -> None:
    window = _window(_summary(policy=_gov_policy(review_abs_realized_pnl="100")))  # REVIEW -> not eligible
    assert window.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    assert window.sample_eligible is False
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.READY
    assert result.comparison_ready is False
    assert result.sample_eligible is False
    assert "paper_sample_eligibility" in result.missing_comparator_inputs
    assert any("time_window_not_sample_eligible" in code for code in result.reason_codes)


@pytest.mark.parametrize(
    "overrides",
    [
        {"sample_observation_count": 0},
        {"stopped_at_ns": 1_000, "window_duration_ns": 0},
        {
            "event_count": 0,
            "computed_event_count": 0,
            "no_realized_event_count": 0,
            "source_event_digest_count": 0,
        },
    ],
)
def test_resealed_sample_eligible_without_positive_evidence_rejects(overrides: dict[str, object]) -> None:
    window = _reseal_window(replace(_window(), sample_eligible=True, **overrides))
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_sample_eligibility_inconsistent" in code for code in result.reason_codes)


def test_window_counts_incoherent_rejects() -> None:
    window = _reseal_window(replace(_window(), event_count=99))  # 99 != computed + no_realized
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_counts_incoherent" in code for code in result.reason_codes)


def test_window_timestamps_invalid_rejects() -> None:
    window = _reseal_window(replace(_window(), window_duration_ns=999))  # != stopped - started (1000)
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_timestamps_invalid" in code for code in result.reason_codes)


def test_window_ready_inconsistent_rejects() -> None:
    window = _reseal_window(replace(_window(), ready=False))  # READY status but ready False
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("time_window_ready_inconsistent" in code for code in result.reason_codes)


# --------------------------------------------------------------------------------------------------
# 5. Missing comparator inputs
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("missing_token", list(_MISSING_V1))
def test_required_paper_input_missing_blocks(missing_token: str) -> None:
    result = _build_bridge()
    assert missing_token in result.missing_comparator_inputs
    assert result.comparison_ready is False
    assert result.stage4_comparator_invoked is False


def test_comparison_never_ready_even_with_baseline() -> None:
    baseline = _baseline()
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=_baseline_digest(baseline),
        baseline_id="baseline-1",
    )
    assert result.status is PaperVsBacktestComparatorBridgeStatus.READY
    assert result.comparison_ready is False
    # A supplied baseline removes the baseline gap but the paper side is still missing.
    assert "backtest_baseline" not in result.missing_comparator_inputs
    assert "paper_edge_id" in result.missing_comparator_inputs


# --------------------------------------------------------------------------------------------------
# 6. Optional backtest baseline
# --------------------------------------------------------------------------------------------------


def test_baseline_bound_and_present() -> None:
    baseline = _baseline()
    digest = _baseline_digest(baseline)
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=digest,
        baseline_id="baseline-1",
    )
    assert result.status is PaperVsBacktestComparatorBridgeStatus.READY
    assert result.backtest_baseline_present is True
    assert result.backtest_baseline_digest == digest
    assert result.expected_backtest_baseline_digest == digest
    assert result.baseline_id == "baseline-1"


def test_baseline_digest_is_deterministic() -> None:
    baseline = _baseline()
    assert _baseline_digest(baseline) == _baseline_digest(_baseline())


def test_baseline_digest_mismatch_rejects() -> None:
    baseline = _baseline()
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest="a" * 64,
        baseline_id="baseline-1",
    )
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("backtest_baseline_digest_mismatch" in code for code in result.reason_codes)


def test_malformed_baseline_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="backtest_baseline_malformed"):
        _build_bridge(
            _window(),
            backtest_baseline={"not": "a-baseline"},  # type: ignore[arg-type]
            expected_backtest_baseline_digest="a" * 64,
        )


def test_baseline_subclass_raises() -> None:
    baseline = _BaselineSubclass(
        baseline_id="baseline-1",
        edge_id="edge-alpha",
        as_of_ns=1_700_000_000_000_000_000,
        backtest_sharpe=1.5,
        backtest_hit_rate=0.55,
    )
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="backtest_baseline_malformed"):
        _build_bridge(
            _window(),
            backtest_baseline=baseline,
            expected_backtest_baseline_digest=_baseline_digest(baseline),
            baseline_id="baseline-1",
        )


def test_invalid_baseline_fields_reject() -> None:
    baseline = _baseline(backtest_sharpe=0.0)  # non-positive Sharpe -> not well-formed
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=_baseline_digest(baseline),
        baseline_id="baseline-1",
    )
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("backtest_baseline_invalid" in code for code in result.reason_codes)


def test_baseline_id_mismatch_rejects() -> None:
    baseline = _baseline()
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=_baseline_digest(baseline),
        baseline_id="other-baseline",
    )
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert any("baseline_id_mismatch" in code for code in result.reason_codes)


def test_baseline_digest_without_baseline_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="expected_backtest_baseline_digest_unexpected"):
        _build_bridge(_window(), expected_backtest_baseline_digest="a" * 64)


def test_baseline_digest_required_when_baseline_present() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="expected_backtest_baseline_digest_invalid"):
        _build_bridge(_window(), backtest_baseline=_baseline(), expected_backtest_baseline_digest=None)


def test_edge_never_proven_even_with_baseline() -> None:
    baseline = _baseline()
    result = _build_bridge(
        _window(),
        backtest_baseline=baseline,
        expected_backtest_baseline_digest=_baseline_digest(baseline),
        baseline_id="baseline-1",
        edge_id="edge-alpha",
    )
    assert result.edge_id_unproven is True
    assert result.edge_proven is False
    assert "paper_edge_id" in result.missing_comparator_inputs


# --------------------------------------------------------------------------------------------------
# 7. Suspicious token rejection
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scope_token", ["live_order", "bist", "scheduler", "place_order", "capital", "readiness"])
def test_scope_violation_in_bridge_id_raises(scope_token: str) -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="scope_violation"):
        _build_bridge(_window(), bridge_id=f"bridge-{scope_token}")


@pytest.mark.parametrize("field", ["paper_id", "baseline_id", "edge_id"])
def test_scope_violation_in_other_ids_raises(field: str) -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="scope_violation"):
        _build_bridge(_window(), **{field: "service-token"})


def test_scope_violation_in_metadata_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="scope_violation"):
        _build_bridge(_window(), metadata={"note": "real_money balance"})


@pytest.mark.parametrize("token", ["wall_clock", "datetime.now", "perf_counter", "server_time", "clock"])
def test_clock_token_in_bridge_id_raises(token: str) -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="clock_token_forbidden"):
        _build_bridge(_window(), bridge_id=f"bridge-{token}")


def test_clock_token_in_metadata_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="clock_token_forbidden"):
        _build_bridge(_window(), metadata={"note": "captured via perf_counter"})


def test_str_subclass_bridge_id_raises() -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="bridge_id_invalid"):
        _build_bridge(_window(), bridge_id=_LiarStr("bridge-1"))


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="metadata_malformed"):
        _build_bridge(_window(), metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_window_digest_raises(bad: str) -> None:
    with pytest.raises(PaperVsBacktestComparatorBridgeError, match="expected_time_window_digest_invalid"):
        _build_bridge(_window(), expected_time_window_digest=bad)


# --------------------------------------------------------------------------------------------------
# 8. Forbidden surfaces (alias-resistant AST)
# --------------------------------------------------------------------------------------------------


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(bridge_module.__file__).read_text(encoding="utf-8"))
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


def test_no_forbidden_module_or_comparator_execution() -> None:
    source = Path(bridge_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
            imported_names.extend(alias.name for alias in node.names)
    for module in imported_modules:
        parts = module.split(".")
        assert "service" not in parts, module
        assert "execution" not in parts, module
        assert "venue" not in parts, module
        assert "runtime" not in parts, module
        assert "readiness" not in parts, module
        assert "paper_adapter" not in module, module
        assert "deribit" not in module, module
        assert "bist" not in module, module
    # The baseline DATA TYPE + its serializer may be imported from stage4_comparator, but never the comparator
    # entrypoint or the paper-summary constructor.
    assert "compare_stage4" not in imported_names
    assert "Stage4PaperSummary" not in imported_names
    # No comparator EXECUTION and no real-clock CALLS anywhere in the source (call-style patterns so the module's
    # own forbidden-token string literals and docstring prose naming excluded symbols do not false-positive).
    for banned_symbol in (
        "compare_stage4(",
        "Stage4PaperSummary(",
        "perf_counter(",
        "monotonic(",
        "time.time(",
        "time.time_ns(",
        "datetime.now(",
        "datetime.utcnow(",
    ):
        assert banned_symbol not in source, banned_symbol


def test_public_api_exact() -> None:
    assert set(bridge_module.__all__) == {
        "PaperVsBacktestComparatorBridgeEvidence",
        "PaperVsBacktestComparatorBridgeError",
        "PaperVsBacktestComparatorBridgeStatus",
        "build_paper_vs_backtest_comparator_bridge",
        "paper_vs_backtest_comparator_bridge_digest",
        "paper_vs_backtest_comparator_bridge_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "venue", "compare", "wallclock")
    for name in bridge_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


def test_result_frozen() -> None:
    result = _build_bridge()
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


def test_reason_codes_sorted_stable() -> None:
    window = _reseal_window(replace(_window(), event_count=99, window_duration_ns=999))
    result = _build_bridge(window, expected_time_window_digest=window.time_window_digest)
    assert result.status is PaperVsBacktestComparatorBridgeStatus.REJECTED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


# --------------------------------------------------------------------------------------------------
# 9. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags() -> None:
    payload = paper_vs_backtest_comparator_bridge_to_dict(_build_bridge())
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
        "paper_vs_backtest_comparison_ready",
        "comparison_ready",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True
    assert payload["bridge_readiness_evidence"] is True
    assert payload["edge_id_unproven"] is True
