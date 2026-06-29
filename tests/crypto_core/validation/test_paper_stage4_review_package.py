"""Tests for the paper Stage-4 review package (§10.4.5) — deterministic, paper-only, fail-closed, digest-bound,
review-only evidence dossier over the merged §10.4 chain.

A single genuine same-chain set is built end-to-end (metrics summary → injected time window → comparator bridge +
return methodology → daily return series → 30-day gate decision), all sharing ONE time window over a real
CANDIDATE metrics summary; adversarial variants are derived by ``replace(...)`` + reseal. Covers phase-scope/no
comparator execution, the happy READY dossier, exact consumed-type boundaries, digest/provenance, consumed-artifact
safety, review-only semantics, suspicious-token rejection, 30-day gate integration, and alias-resistant
forbidden-surface AST."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation import paper_stage4_review_package as package_module
from crypto_core.validation.deterministic_paper_replay_harness import verify_deterministic_paper_replay
from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecisionStatus,
    build_paper_30day_evidence_gate_decision,
    paper_30day_evidence_gate_decision_digest,
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
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    build_paper_daily_return_series_evidence,
    paper_daily_return_series_evidence_digest,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
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
from crypto_core.validation.paper_return_series_methodology import (
    build_paper_return_series_methodology,
    paper_return_series_methodology_digest,
)
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
from crypto_core.validation.paper_stage4_review_package import (
    PaperStage4ReviewPackageError,
    PaperStage4ReviewPackageStatus,
    build_paper_stage4_review_package,
    paper_stage4_review_package_digest,
    paper_stage4_review_package_to_dict,
)
from crypto_core.validation.paper_vs_backtest_comparator_bridge import (
    build_paper_vs_backtest_comparator_bridge,
    paper_vs_backtest_comparator_bridge_digest,
)
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

_SYMBOL = "BTC-PERPETUAL"
_CORR = "corr-ep"
_REQ_CORR = "corr-req"
_RUN = "run-ep"
_EPISODE_ID = "e2e-1"
_POLICY_ID = "gov-policy-1"
_AGG_ID = "agg-1"
_METHOD_ID = "method-1"
_DAY_NS = 86_400_000_000_000

_CHAIN_IDS: dict[str, object] = {
    "fill_simulation_id": "fillsim-1",
    "position_transition_id": "trans-1",
    "new_position_state_id": "newpos-1",
    "pnl_report_id": "pnl-1",
    "episode_run_id": "ep-run-1",
    "correlation_id": _CORR,
}


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


# -------------------------------------------------------------------------------------------------
# Genuine merged metrics-summary chain (mirrors test_paper_deterministic_time_window_adapter fixtures)
# -------------------------------------------------------------------------------------------------


def _make_draft() -> PaperAllocatorIntentDraft:
    fields_payload: dict[str, object] = {
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
    draft = PaperAllocatorIntentDraft(**fields_payload, draft_digest="")  # type: ignore[arg-type]
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


def _gov_policy():
    return build_paper_governor_policy(
        policy_id=_POLICY_ID,
        min_computed_event_count=1,
        max_abs_realized_pnl="1000",
        review_abs_realized_pnl="500",
        max_closed_units="100",
    )


def _summary():
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
        expected_session_aggregate_digest=agg.aggregate_digest,
        expected_evidence_manifest_digest=manifest.manifest_digest,
        expected_readiness_decision_digest=readiness.readiness_decision_digest,
        run_id=_RUN,
        aggregate_id=agg.aggregate_id,
        correlation_id=_CORR,
    )


def _methodology():
    return build_paper_return_series_methodology(
        methodology_id=_METHOD_ID,
        correlation_id=_CORR,
        mtm_policy_id="mtm-policy-1",
        fee_policy_id="fee-policy-1",
        funding_policy_id="funding-policy-1",
        mark_policy_id="mark-policy-1",
        exposure_policy_id="exposure-policy-1",
        liquidation_policy_id="liquidation-policy-1",
        risk_free_policy_id="risk-free-policy-1",
    )


def _bucket(day: int) -> PaperDailyReturnBucket:
    seed = PaperDailyReturnBucket(
        bucket_id=f"bucket-{day + 1}",
        bucket_start_ns=day * _DAY_NS,
        bucket_end_ns=(day + 1) * _DAY_NS,
        normalized_index_start="1",
        normalized_index_end="1",
        bucket_digest="",
    )
    return replace(seed, bucket_digest=series_module._bucket_digest(seed))  # noqa: SLF001


def _buckets(days: int = 30) -> tuple[PaperDailyReturnBucket, ...]:
    return tuple(_bucket(day) for day in range(days))


class _Chain:
    """A genuine same-chain set of the six merged §10.4 artifacts sharing one time window."""

    def __init__(self, *, days: int = 30) -> None:
        self.summary = _summary()
        self.window = build_paper_deterministic_time_window_evidence(
            self.summary,
            expected_metrics_summary_digest=self.summary.summary_digest,
            started_at_ns=0,
            stopped_at_ns=days * _DAY_NS,
            window_id="window-1",
            methodology_id=_METHOD_ID,
            run_id=_RUN,
            aggregate_id=_AGG_ID,
            correlation_id=_CORR,
            sample_observation_count=days,
        )
        self.bridge = build_paper_vs_backtest_comparator_bridge(
            self.window,
            expected_time_window_digest=self.window.time_window_digest,
            bridge_id="bridge-1",
            paper_id="paper-1",
            correlation_id=_CORR,
        )
        self.methodology = _methodology()
        self.series = build_paper_daily_return_series_evidence(
            self.methodology,
            self.window,
            expected_methodology_digest=self.methodology.methodology_digest,
            expected_time_window_digest=self.window.time_window_digest,
            series_id="series-1",
            correlation_id=_CORR,
            daily_buckets=_buckets(days),
        )
        self.gate = build_paper_30day_evidence_gate_decision(
            self.series,
            expected_series_digest=self.series.series_digest,
            gate_id="gate-1",
            correlation_id=_CORR,
        )


def _chain(*, days: int = 30) -> _Chain:
    return _Chain(days=days)


def _pkg(chain: _Chain | None = None, **overrides):
    chain = chain if chain is not None else _chain()
    payload: dict[str, object] = {
        "metrics_summary": chain.summary,
        "time_window_evidence": chain.window,
        "comparator_bridge_evidence": chain.bridge,
        "return_series_methodology": chain.methodology,
        "daily_return_series_evidence": chain.series,
        "thirty_day_gate_decision": chain.gate,
        "expected_metrics_summary_digest": chain.summary.summary_digest,
        "expected_time_window_digest": chain.window.time_window_digest,
        "expected_comparator_bridge_digest": chain.bridge.bridge_digest,
        "expected_return_series_methodology_digest": chain.methodology.methodology_digest,
        "expected_daily_return_series_digest": chain.series.series_digest,
        "expected_thirty_day_gate_decision_digest": chain.gate.decision_digest,
        "review_package_id": "review-1",
        "paper_id": "paper-1",
        "correlation_id": _CORR,
        "metadata": {"purpose": "paper stage4 review"},
    }
    payload.update(overrides)
    return build_paper_stage4_review_package(
        payload.pop("metrics_summary"),
        payload.pop("time_window_evidence"),
        payload.pop("comparator_bridge_evidence"),
        payload.pop("return_series_methodology"),
        payload.pop("daily_return_series_evidence"),
        payload.pop("thirty_day_gate_decision"),
        **payload,
    )


@pytest.fixture(scope="module")
def chain() -> _Chain:
    return _chain()


# -------------------------------------------------------------------------------------------------
# 1. Phase scope / no comparator execution
# -------------------------------------------------------------------------------------------------


def test_ready_package_does_not_invoke_comparator(chain: _Chain) -> None:
    result = _pkg(chain)
    assert result.stage4_comparator_invoked is False
    assert result.comparison_ready is False
    assert result.comparator_stage4_comparator_invoked is False
    assert result.comparator_comparison_ready is False


def test_module_does_not_execute_comparator_or_build_stage4_summary() -> None:
    source = Path(package_module.__file__).read_text(encoding="utf-8")
    assert "compare_stage4(" not in source
    assert "Stage4PaperSummary(" not in source


# -------------------------------------------------------------------------------------------------
# 2. Happy review-package path
# -------------------------------------------------------------------------------------------------


def test_ready_review_package(chain: _Chain) -> None:
    result = _pkg(chain)
    assert result.status is PaperStage4ReviewPackageStatus.READY
    assert result.ready is True
    assert result.reason_codes == ()
    assert result.market_symbol == _SYMBOL
    # review-only / operator-review semantics
    assert result.review_only is True
    assert result.stage4_review_package is True
    assert result.operator_review_required is True
    assert result.operator_review_complete is False
    assert result.approval_granted is False
    # evidence-chain consumption flags
    for flag in (
        result.metrics_summary_consumed,
        result.time_window_evidence_consumed,
        result.comparator_bridge_consumed,
        result.return_series_methodology_consumed,
        result.daily_return_series_evidence_consumed,
        result.thirty_day_gate_consumed,
        result.evidence_chain_consumed,
    ):
        assert flag is True
    assert result.paper_stage4_readiness_decision_consumed is False
    # bound consumed digests
    assert result.metrics_summary_digest == chain.summary.summary_digest
    assert result.time_window_digest == chain.window.time_window_digest
    assert result.comparator_bridge_digest == chain.bridge.bridge_digest
    assert result.return_series_methodology_digest == chain.methodology.methodology_digest
    assert result.daily_return_series_digest == chain.series.series_digest
    assert result.thirty_day_gate_decision_digest == chain.gate.decision_digest
    assert result.thirty_day_gate_satisfied is True
    assert result.review_findings == package_module._READY_FINDINGS  # noqa: SLF001
    assert _is_hex64(result.review_package_digest)


def test_review_findings_sorted_unique(chain: _Chain) -> None:
    result = _pkg(chain)
    assert list(result.review_findings) == sorted(set(result.review_findings))


# -------------------------------------------------------------------------------------------------
# 3. Exact consumed-artifact type boundaries
# -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "match"),
    [
        ("metrics_summary", "metrics_summary_malformed"),
        ("time_window_evidence", "time_window_evidence_malformed"),
        ("comparator_bridge_evidence", "comparator_bridge_evidence_malformed"),
        ("return_series_methodology", "return_series_methodology_malformed"),
        ("daily_return_series_evidence", "daily_return_series_evidence_malformed"),
        ("thirty_day_gate_decision", "thirty_day_gate_decision_malformed"),
    ],
)
def test_wrong_consumed_artifact_type_raises(chain: _Chain, field_name: str, match: str) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match=match):
        _pkg(chain, **{field_name: object()})


# -------------------------------------------------------------------------------------------------
# 4. Digest / provenance
# -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "match"),
    [
        ("expected_metrics_summary_digest", "metrics_summary_digest_mismatch"),
        ("expected_time_window_digest", "time_window_digest_mismatch"),
        ("expected_comparator_bridge_digest", "comparator_bridge_digest_mismatch"),
        ("expected_return_series_methodology_digest", "return_series_methodology_digest_mismatch"),
        ("expected_daily_return_series_digest", "daily_return_series_digest_mismatch"),
        ("expected_thirty_day_gate_decision_digest", "thirty_day_gate_decision_digest_mismatch"),
    ],
)
def test_wrong_expected_digest_rejects(chain: _Chain, field_name: str, match: str) -> None:
    result = _pkg(chain, **{field_name: "a" * 64})
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any(match in code for code in result.reason_codes)


def test_forged_artifact_self_digest_rejects(chain: _Chain) -> None:
    forged = replace(chain.summary, summary_digest="0" * 64)  # tampered WITHOUT reseal
    result = _pkg(chain, metrics_summary=forged, expected_metrics_summary_digest="0" * 64)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("metrics_summary_digest_mismatch" in code for code in result.reason_codes)


def test_package_digest_deterministic_and_recomputes(chain: _Chain) -> None:
    a = _pkg(chain)
    b = _pkg(chain)
    assert a.review_package_digest == b.review_package_digest
    assert paper_stage4_review_package_digest(a) == a.review_package_digest
    assert paper_stage4_review_package_to_dict(a)["review_package_digest"] == a.review_package_digest


def test_self_digest_excluded_and_only_self_digest_excluded(chain: _Chain) -> None:
    result = _pkg(chain)
    payload = paper_stage4_review_package_to_dict(result)
    assert set(payload) == {field.name for field in fields(result)}
    resealed = replace(result, review_package_digest="0" * 64)
    assert paper_stage4_review_package_digest(resealed) == result.review_package_digest


@pytest.mark.parametrize(
    "override",
    [
        {"review_package_id": "review-2"},
        {"paper_id": "paper-2"},
        {"metadata": {"purpose": "other"}},
    ],
)
def test_changed_bound_field_changes_digest(chain: _Chain, override: dict[str, object]) -> None:
    base = _pkg(chain)
    other = _pkg(chain, **override)
    assert base.review_package_digest != other.review_package_digest


def test_changed_chain_changes_package_digest() -> None:
    base = _pkg(_chain(days=30))
    other = _pkg(_chain(days=31))
    assert base.review_package_digest != other.review_package_digest


def test_inputs_not_mutated(chain: _Chain) -> None:
    before = chain.gate.decision_digest
    metadata = {"purpose": "paper stage4 review"}
    _pkg(chain, metadata=metadata)
    assert chain.gate.decision_digest == before
    assert metadata == {"purpose": "paper stage4 review"}


# -------------------------------------------------------------------------------------------------
# 5. Consumed-artifact safety
# -------------------------------------------------------------------------------------------------


def test_unsafe_metrics_summary_rejects(chain: _Chain) -> None:
    forged = replace(chain.summary, prdv4_stage4_complete=True)
    forged = replace(forged, summary_digest=paper_session_metrics_summary_digest(forged))
    result = _pkg(chain, metrics_summary=forged, expected_metrics_summary_digest=forged.summary_digest)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("metrics_summary_unsafe_flags" in code for code in result.reason_codes)


def test_unsafe_time_window_rejects(chain: _Chain) -> None:
    forged = replace(chain.window, sharpe_computed=True)
    forged = replace(forged, time_window_digest=paper_deterministic_time_window_evidence_digest(forged))
    result = _pkg(chain, time_window_evidence=forged, expected_time_window_digest=forged.time_window_digest)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("time_window_unsafe_flags" in code for code in result.reason_codes)


def test_comparator_bridge_comparison_ready_rejects(chain: _Chain) -> None:
    forged = replace(chain.bridge, comparison_ready=True)
    forged = replace(forged, bridge_digest=paper_vs_backtest_comparator_bridge_digest(forged))
    result = _pkg(chain, comparator_bridge_evidence=forged, expected_comparator_bridge_digest=forged.bridge_digest)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("comparator_bridge_unsafe_flags" in code for code in result.reason_codes)


def test_comparator_bridge_stage4_invoked_rejects(chain: _Chain) -> None:
    forged = replace(chain.bridge, stage4_comparator_invoked=True)
    forged = replace(forged, bridge_digest=paper_vs_backtest_comparator_bridge_digest(forged))
    result = _pkg(chain, comparator_bridge_evidence=forged, expected_comparator_bridge_digest=forged.bridge_digest)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("comparator_bridge_unsafe_flags" in code for code in result.reason_codes)


def test_unsafe_daily_return_series_rejects(chain: _Chain) -> None:
    forged = replace(chain.series, sharpe_computed=True)
    forged = replace(forged, series_digest=paper_daily_return_series_evidence_digest(forged))
    result = _pkg(chain, daily_return_series_evidence=forged, expected_daily_return_series_digest=forged.series_digest)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("daily_return_series_unsafe_flags" in code for code in result.reason_codes)


def test_unsafe_methodology_rejects(chain: _Chain) -> None:
    forged = replace(chain.methodology, profitability_proven=True)
    forged = replace(forged, methodology_digest=paper_return_series_methodology_digest(forged))
    result = _pkg(
        chain,
        return_series_methodology=forged,
        expected_return_series_methodology_digest=forged.methodology_digest,
    )
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("return_series_methodology_unsafe_flags" in code for code in result.reason_codes)


# -------------------------------------------------------------------------------------------------
# 6. Review-only semantics
# -------------------------------------------------------------------------------------------------


def test_assembled_is_not_approval(chain: _Chain) -> None:
    result = _pkg(chain)
    payload = paper_stage4_review_package_to_dict(result)
    assert payload["operator_review_required"] is True
    assert payload["operator_review_complete"] is False
    assert payload["approval_granted"] is False
    assert payload["prdv4_stage4_complete"] is False
    assert payload["comparison_ready"] is False


def test_operator_approval_has_no_builder_param(chain: _Chain) -> None:
    with pytest.raises(TypeError):
        _pkg(chain, approval_granted=True)  # not a builder parameter


# -------------------------------------------------------------------------------------------------
# 7. Suspicious token / metadata rejection
# -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["live_order", "bist", "scheduler", "capital", "readiness", "approved", "trade"])
def test_scope_violation_in_review_package_id_raises(chain: _Chain, token: str) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="scope_violation"):
        _pkg(chain, review_package_id=f"review-{token}")


@pytest.mark.parametrize("field_name", ["paper_id", "correlation_id"])
def test_scope_violation_in_other_ids_raises(chain: _Chain, field_name: str) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="scope_violation"):
        _pkg(chain, **{field_name: "service-token"})


@pytest.mark.parametrize("token", ["wall_clock", "datetime.now", "perf_counter"])
def test_clock_token_raises(chain: _Chain, token: str) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="clock_token_forbidden"):
        _pkg(chain, review_package_id=f"review-{token}")


def test_scope_violation_in_metadata_raises(chain: _Chain) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="scope_violation"):
        _pkg(chain, metadata={"note": "approved for live"})


def test_str_subclass_id_raises(chain: _Chain) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="review_package_id_invalid"):
        _pkg(chain, review_package_id=_LiarStr("review-1"))


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(chain: _Chain, bad_metadata: object) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="metadata_malformed"):
        _pkg(chain, metadata=bad_metadata)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63])
def test_malformed_expected_digest_raises(chain: _Chain, bad: str) -> None:
    with pytest.raises(PaperStage4ReviewPackageError, match="expected_metrics_summary_digest_invalid"):
        _pkg(chain, expected_metrics_summary_digest=bad)


# -------------------------------------------------------------------------------------------------
# 8. 30-day gate integration
# -------------------------------------------------------------------------------------------------


def test_binds_gate_used_window_fields(chain: _Chain) -> None:
    result = _pkg(chain)
    assert result.thirty_day_gate_minimum_bucket_count == 30
    assert result.thirty_day_gate_bucket_count == 30
    assert result.thirty_day_gate_daily_return_count == 30
    assert result.thirty_day_gate_used_bucket_count == 30
    assert result.thirty_day_gate_used_first_bucket_id == "bucket-1"
    assert result.thirty_day_gate_used_last_bucket_id == "bucket-30"
    assert result.thirty_day_gate_used_first_bucket_start_ns == 0
    assert result.thirty_day_gate_used_last_bucket_end_ns == 30 * _DAY_NS
    assert result.daily_return_series_bucket_count == 30
    assert result.daily_return_series_return_count == 30


def test_longer_window_still_satisfies_and_binds_total_counts() -> None:
    result = _pkg(_chain(days=31))
    assert result.status is PaperStage4ReviewPackageStatus.READY
    assert result.thirty_day_gate_satisfied is True
    assert result.thirty_day_gate_bucket_count == 31
    assert result.thirty_day_gate_used_bucket_count == 30  # decision over the first 30


def test_does_not_reinterpret_gate_as_readiness(chain: _Chain) -> None:
    result = _pkg(chain)
    assert result.thirty_day_gate_satisfied is True
    assert result.prdv4_stage4_complete is False
    assert result.live_ready is False
    assert result.shadow_ready is False
    assert result.deribit_ready is False
    assert result.profitability_proven is False
    assert result.edge_proven is False


def test_gate_not_satisfied_rejects(chain: _Chain) -> None:
    forged = replace(chain.gate, thirty_day_gate_satisfied=False)
    forged = replace(forged, decision_digest=paper_30day_evidence_gate_decision_digest(forged))
    result = _pkg(
        chain, thirty_day_gate_decision=forged, expected_thirty_day_gate_decision_digest=forged.decision_digest
    )
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("thirty_day_gate_not_satisfied" in code for code in result.reason_codes)


def test_rejected_gate_decision_rejects(chain: _Chain) -> None:
    forged = replace(chain.gate, status=PaperThirtyDayEvidenceGateDecisionStatus.REJECTED, ready=False)
    forged = replace(forged, decision_digest=paper_30day_evidence_gate_decision_digest(forged))
    result = _pkg(
        chain, thirty_day_gate_decision=forged, expected_thirty_day_gate_decision_digest=forged.decision_digest
    )
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("thirty_day_gate_unsafe_flags" in code for code in result.reason_codes)


def test_cross_chain_mismatch_rejects() -> None:
    # A gate from a DIFFERENT chain (different series) must not bind into this chain.
    chain_a = _chain()
    chain_b = _chain(days=31)
    result = _pkg(
        chain_a,
        thirty_day_gate_decision=chain_b.gate,
        expected_thirty_day_gate_decision_digest=chain_b.gate.decision_digest,
    )
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert any("gate_series_chain_mismatch" in code for code in result.reason_codes)


# -------------------------------------------------------------------------------------------------
# 9. Forbidden surface (alias-resistant AST) + non-overclaim
# -------------------------------------------------------------------------------------------------


def test_module_purity_no_impure_imports() -> None:
    tree = ast.parse(Path(package_module.__file__).read_text(encoding="utf-8"))
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
    source = Path(package_module.__file__).read_text(encoding="utf-8")
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
        assert "stage4_comparator" not in module, module
        assert "deribit" not in module, module
        assert "bist" not in module, module
    assert "compare_stage4" not in imported_names
    assert "Stage4PaperSummary" not in imported_names
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
    assert set(package_module.__all__) == {
        "PaperStage4ReviewPackage",
        "PaperStage4ReviewPackageError",
        "PaperStage4ReviewPackageStatus",
        "build_paper_stage4_review_package",
        "paper_stage4_review_package_digest",
        "paper_stage4_review_package_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "approve", "compare", "sharpe")
    for name in package_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


def test_result_frozen(chain: _Chain) -> None:
    result = _pkg(chain)
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


def test_reason_codes_sorted_stable(chain: _Chain) -> None:
    result = _pkg(chain, expected_metrics_summary_digest="a" * 64, expected_time_window_digest="b" * 64)
    assert result.status is PaperStage4ReviewPackageStatus.REJECTED
    assert list(result.reason_codes) == sorted(set(result.reason_codes))
    assert len(result.reason_codes) >= 2


def test_non_overclaim_flags(chain: _Chain) -> None:
    payload = paper_stage4_review_package_to_dict(_pkg(chain))
    for flag in (
        "operator_review_complete",
        "approval_granted",
        "comparison_ready",
        "stage4_comparator_invoked",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "deribit_ready",
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
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
        "sharpe_computed",
        "paper_sharpe_computed",
        "annualized_sharpe_computed",
        "return_series_constructed",
        "paper_stage4_readiness_decision_consumed",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True
    assert payload["stage4_review_package"] is True
    assert payload["review_only"] is True
    assert payload["operator_review_required"] is True
