"""Tests for the paper secondary-metrics substrate reconciliation artifact (denominator completeness).

Every episode / session / realized-PnL event in these fixtures is produced by its REAL builder
(``run_paper_episode`` / ``build_paper_session_sequence`` / ``compute_paper_realized_pnl_event``), never a
hand-forged ``PaperEpisodeRunResult`` with the impossible ``realized_pnl_computed=True`` flag. Realized-PnL
reconciliation is therefore exercised exactly as it happens for a real paper episode: the runner leaves
``realized_pnl_computed`` False and the session sequence rejects any episode that sets it, so the artifact
binds realized PnL directly to the supplied event and the record's own ``realized_pnl``.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_core.validation import paper_secondary_metrics_substrate_reconciliation as recon_module
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
    run_paper_episode,
)
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_simulation_result_digest,
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
    build_flat_paper_position_state,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import (
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import build_paper_secondary_metrics_evidence
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliationError,
    PaperSecondaryMetricsSubstrateReconciliationStatus,
    PaperSecondaryMetricsSubstrateRecordInput,
    build_paper_secondary_metrics_substrate_reconciliation,
    paper_secondary_metrics_substrate_reconciliation_digest,
    paper_secondary_metrics_substrate_reconciliation_to_dict,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.secondary_metrics_policy import build_secondary_metrics_policy
from crypto_core.validation.trade_record_evidence import build_trade_record_evidence, trade_record_evidence_digest

_REASON_PREFIX = "paper_secondary_metrics_substrate_reconciliation:"
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


# --- Real-builder substrate scaffolding ---------------------------------------------------------------------


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


def _order_intent(side: PaperOrderSide, *, requested_units: str = "1", requested_notional: str = "100000"):
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
        requested_notional=requested_notional,
        requested_units=requested_units,
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


def _short_prior(*, signed: str = "-2", abs_units: str = "2", avg: str = "100"):
    return build_paper_position_state(
        position_state_id=_uid("pos"),
        market_symbol=_MARKET,
        side=PaperPositionStateSide.SHORT,
        signed_units=signed,
        abs_units=abs_units,
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-pos",
    )


def _flat_prior():
    return build_flat_paper_position_state(
        position_state_id=_uid("pos"), market_symbol=_MARKET, correlation_id="corr-pos"
    )


def _snapshot(reference_price: str, *, available_units: str | None = None):
    return build_paper_fill_market_snapshot(
        snapshot_id=_uid("snap"),
        market_symbol=_MARKET,
        reference_price=reference_price,
        available_units=available_units,
    )


def _fill_policy(*, allow_partial_fill: bool = False):
    return build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=allow_partial_fill
    )


def _mark(mark_price: str = "100"):
    return build_paper_mark_snapshot(
        mark_snapshot_id=_uid("mark"), market_symbol=_MARKET, mark_price=mark_price, correlation_id="corr-mark"
    )


def _run_episode(intent, prior, snapshot, fpolicy, mark, *, episode_id: str):
    ids: dict[str, object] = {
        "fill_simulation_id": _uid("fillsim"),
        "position_transition_id": _uid("trans"),
        "new_position_state_id": _uid("newpos"),
        "pnl_report_id": _uid("pnl"),
        "episode_run_id": episode_id,
        "correlation_id": _CORR,
    }
    episode = run_paper_episode(intent, prior, snapshot, fpolicy, mark, **ids)  # type: ignore[arg-type]
    # Re-run the identical (deterministic) fill so the realized event can bind the episode's own fill digest.
    fill_result = simulate_paper_fill(
        intent, snapshot, fpolicy, fill_simulation_id=ids["fill_simulation_id"], correlation_id=_CORR
    )
    return episode, fill_result, ids


def _record_from(episode_id: str, record_id: str, fill_result, *, event, policy_id: str = "policy-1"):
    filled = Decimal(fill_result.filled_units)
    unfilled = Decimal(fill_result.unfilled_units)
    is_filled = filled > 0
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
        realized_fill_price=_scale18(fill_result.fill_price) if is_filled else None,
        realized_pnl=_scale18(event.realized_pnl) if event is not None else "0.000000000000000000",
        decided_episode=True,
    )


def _closing_bundle(
    episode_id: str, record_id: str, *, reference_price: str, avg: str = "100", policy_id: str = "policy-1"
):
    """A real FILLED episode that BUYs to reduce a prior SHORT, realizing PnL, with a real realized event."""

    prior = _short_prior(avg=avg)
    intent = _order_intent(PaperOrderSide.BUY)
    snapshot = _snapshot(reference_price)
    episode, fill_result, ids = _run_episode(intent, prior, snapshot, _fill_policy(), _mark(), episode_id=episode_id)
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill_result,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=_CORR,
    )
    event = compute_paper_realized_pnl_event(
        prior, fill_result, transition, new_state, realized_pnl_event_id=_uid("rp"), correlation_id=_CORR
    )
    record = _record_from(episode_id, record_id, fill_result, event=event, policy_id=policy_id)
    return episode, fill_result, event, record


def _opening_bundle(episode_id: str, record_id: str, *, policy_id: str = "policy-1"):
    """A real FILLED opening episode (flat -> long); realizes nothing, so no realized event is supplied."""

    intent = _order_intent(PaperOrderSide.BUY)
    episode, fill_result, _ = _run_episode(
        intent, _flat_prior(), _snapshot("100"), _fill_policy(), _mark(), episode_id=episode_id
    )
    record = _record_from(episode_id, record_id, fill_result, event=None, policy_id=policy_id)
    return episode, fill_result, None, record


def _rejected_bundle(episode_id: str, record_id: str, *, policy_id: str = "policy-1"):
    """A real REJECTED (insufficient-liquidity) episode: zero fill, no realized fill price, no event."""

    intent = _order_intent(PaperOrderSide.BUY)
    episode, fill_result, _ = _run_episode(
        intent, _flat_prior(), _snapshot("100", available_units="0"), _fill_policy(), _mark(), episode_id=episode_id
    )
    record = _record_from(episode_id, record_id, fill_result, event=None, policy_id=policy_id)
    return episode, fill_result, None, record


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
    """A coherent win/loss/rejected 3-episode reconciliation fixture from real builders, mutable per test."""

    def __init__(self, bundles=None) -> None:
        self.policy = _policy()
        if bundles is None:
            bundles = [
                _closing_bundle("ep-0", "rec-0", reference_price="95"),  # BUY closes short @95 vs avg100 -> +5
                _closing_bundle("ep-1", "rec-1", reference_price="103"),  # BUY closes short @103 vs avg100 -> -3
                _rejected_bundle("ep-2", "rec-2"),
            ]
        self.bundles = list(bundles)
        self._sync()
        # Real, builder-valid session sequence over the real episodes (the digest-bound denominator ROOT).
        self.session = build_paper_session_sequence(
            [episode for (episode, _, _, _) in self.bundles], paper_session_id="ps-1", correlation_id=_CORR
        )

    def _sync(self) -> None:
        self.inputs = [
            PaperSecondaryMetricsSubstrateRecordInput(record, episode, fill_result, event)
            for (episode, fill_result, event, record) in self.bundles
        ]
        self.records = [record for (_, _, _, record) in self.bundles]
        self._rebuild_metrics()

    def _rebuild_metrics(self) -> None:
        self.metrics = build_paper_secondary_metrics_evidence(
            self.policy, self.records, evidence_id="sm4-1", correlation_id=_CORR
        )

    def rebuild_metrics_from_inputs(self) -> None:
        self.records = [item.record for item in self.inputs]
        self._rebuild_metrics()

    def build(self, **overrides):
        payload = {
            "reconciliation_id": "recon-1",
            "correlation_id": _CORR,
            "expected_policy_digest": self.policy.policy_digest,
            "expected_metrics_evidence_digest": self.metrics.evidence_digest,
            "expected_session_sequence_digest": self.session.paper_session_sequence_digest,
        }
        payload.update(overrides)
        return build_paper_secondary_metrics_substrate_reconciliation(
            self.policy, self.metrics, self.inputs, self.session, **payload
        )


def _reseal_record(record, **overrides):
    tampered = replace(record, **overrides)
    return replace(tampered, record_digest=trade_record_evidence_digest(tampered))


def _reseal_event(event, **overrides):
    tampered = replace(event, **overrides)
    return replace(tampered, realized_pnl_event_digest=paper_realized_pnl_event_digest(tampered))


# --- 1. Public API / happy path -----------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(recon_module.__all__) == {
        "PaperSecondaryMetricsSubstrateReconciliation",
        "PaperSecondaryMetricsSubstrateReconciliationError",
        "PaperSecondaryMetricsSubstrateReconciliationStatus",
        "PaperSecondaryMetricsSubstrateRecordInput",
        "build_paper_secondary_metrics_substrate_reconciliation",
        "paper_secondary_metrics_substrate_reconciliation_digest",
        "paper_secondary_metrics_substrate_reconciliation_to_dict",
    }


def test_episodes_are_builder_valid() -> None:
    # Guard against regressing to hand-forged substrate: every episode must reproduce its own public digest
    # and (per the runner/session contract) carry realized_pnl_computed=False, and the session must accept them.
    scenario = _Scenario()
    for item in scenario.inputs:
        assert item.episode_run.realized_pnl_computed is False
        assert paper_episode_run_result_digest(item.episode_run) == item.episode_run.episode_run_digest
    assert scenario.inputs[0].episode_run.status is PaperEpisodeRunStatus.COMPUTED
    assert scenario.inputs[2].episode_run.status is PaperEpisodeRunStatus.FILL_REJECTED
    assert scenario.session.episode_run_digests == tuple(
        item.episode_run.episode_run_digest for item in scenario.inputs
    )


def test_happy_win_loss_rejected_reconciled() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)

    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
    assert reconciliation.ready is True
    assert reconciliation.reason_codes == ()
    assert reconciliation.episode_count == 3
    assert reconciliation.filled_episode_count == 2
    assert reconciliation.rejected_or_unfilled_episode_count == 1
    assert reconciliation.positive_pnl_episode_count == 1
    assert reconciliation.negative_pnl_episode_count == 1
    assert reconciliation.zero_pnl_episode_count == 0
    assert len(reconciliation.reconciled_record_digests) == 3
    assert payload["reconciliation_digest"] == paper_secondary_metrics_substrate_reconciliation_digest(reconciliation)


def test_output_is_frozen() -> None:
    reconciliation = _Scenario().build()
    with pytest.raises(FrozenInstanceError):
        reconciliation.ready = False  # type: ignore[misc]


def test_serializer_matches_dataclass_fields() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)
    assert set(payload) == {field.name for field in fields(reconciliation)}
    assert payload["status"] == reconciliation.status.value


def test_deterministic_and_metadata_order_independent() -> None:
    scenario = _Scenario()
    first = scenario.build(metadata={"b": "2", "a": "1"})
    second = scenario.build(metadata={"a": "1", "b": "2"})
    assert first.reconciliation_digest == second.reconciliation_digest
    resealed = replace(first, reconciliation_digest="0" * 64)
    assert paper_secondary_metrics_substrate_reconciliation_digest(resealed) == first.reconciliation_digest


def test_structural_false_non_claim_flags() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)
    assert payload["paper_only"] is True
    assert payload["validation_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False


# --- 2. Completeness / bijection (dropped, extra, duplicate) -------------------------------------------------


def test_dropped_losing_record_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[0], scenario.inputs[2]]  # drop the loss; session still has all 3
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_dropped_rejected_unfilled_record_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[0], scenario.inputs[1]]  # drop the rejected episode
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_extra_record_without_episode_rejected() -> None:
    scenario = _Scenario()
    extra = _closing_bundle("ep-extra", "rec-extra", reference_price="98")
    scenario.inputs = [
        *scenario.inputs,
        PaperSecondaryMetricsSubstrateRecordInput(extra[3], extra[0], extra[1], extra[2]),
    ]
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_duplicate_record_episode_id_rejected() -> None:
    scenario = _Scenario()
    # A distinct real episode (different fill -> different digest) re-using episode id "ep-0"; its record's
    # episode_id matches its own run id, so the collision is a genuine duplicate episode id.
    dup = _closing_bundle("ep-0", "rec-dup", reference_price="96")
    scenario.inputs[2] = PaperSecondaryMetricsSubstrateRecordInput(dup[3], dup[0], dup[1], dup[2])
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("duplicate_record_episode_id") in reconciliation.reason_codes


def test_duplicate_substrate_episode_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[2] = scenario.inputs[0]  # same episode_run (same digest) twice
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("duplicate_substrate_episode") in reconciliation.reason_codes


def test_episode_order_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[1], scenario.inputs[0], scenario.inputs[2]]  # swap first two
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_order_mismatch") in reconciliation.reason_codes


# --- 3. Provenance / stale digests --------------------------------------------------------------------------


def test_stale_policy_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_policy_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("policy_digest_mismatch") in reconciliation.reason_codes


def test_stale_metrics_evidence_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_metrics_evidence_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("metrics_evidence_digest_mismatch") in reconciliation.reason_codes


def test_stale_session_sequence_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_session_sequence_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("session_sequence_digest_mismatch") in reconciliation.reason_codes


def test_stale_fill_result_digest_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_fill = replace(
        replace(win.fill_result, gross_notional="999"),
        result_digest=paper_fill_simulation_result_digest(replace(win.fill_result, gross_notional="999")),
    )
    scenario.inputs[0] = replace(win, fill_result=tampered_fill)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("fill_result_digest_mismatch") in reconciliation.reason_codes


def test_stale_realized_event_digest_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_event = replace(
        win.realized_pnl_event, realized_pnl_event_digest="0" * 64
    )  # carried digest not recomputed
    scenario.inputs[0] = replace(win, realized_pnl_event=tampered_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_digest_mismatch") in reconciliation.reason_codes


# --- 4. Record <-> substrate value / realized-event binding -------------------------------------------------


def test_resealed_record_quantity_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, filled_quantity="0.500000000000000000")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("filled_quantity_mismatch") in reconciliation.reason_codes


def test_resealed_record_realized_pnl_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, realized_pnl="9.000000000000000000")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_pnl_mismatch") in reconciliation.reason_codes


def test_losing_record_reconciles_with_matching_event() -> None:
    # The loss episode reconciles on its own only when its realized event binds and matches the record's PnL.
    scenario = _Scenario([_closing_bundle("ep-0", "rec-0", reference_price="103")])  # -3
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
    assert reconciliation.negative_pnl_episode_count == 1
    assert reconciliation.filled_episode_count == 1


def test_nonzero_pnl_filled_missing_event_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[1] = replace(scenario.inputs[1], realized_pnl_event=None)  # loss record still claims -3
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_required") in reconciliation.reason_codes


def test_supplied_event_pnl_mismatch_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    scenario.inputs[0] = replace(win, realized_pnl_event=_reseal_event(win.realized_pnl_event, realized_pnl="9"))
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_pnl_mismatch") in reconciliation.reason_codes


def test_supplied_event_binding_mismatch_rejected() -> None:
    scenario = _Scenario()
    # The loss episode's real event bound onto the win input: its fill/transition digests bind ep-1, not ep-0.
    win = scenario.inputs[0]
    scenario.inputs[0] = replace(win, realized_pnl_event=scenario.inputs[1].realized_pnl_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_binding_mismatch") in reconciliation.reason_codes


def test_supplied_event_resealed_fill_units_mismatch_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_event = _reseal_event(win.realized_pnl_event, filled_units="0.500000000000000000")
    scenario.inputs[0] = replace(win, realized_pnl_event=tampered_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_binding_mismatch") in reconciliation.reason_codes


def test_supplied_event_resealed_fill_price_mismatch_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_event = _reseal_event(win.realized_pnl_event, fill_price="96.000000000000000000")
    scenario.inputs[0] = replace(win, realized_pnl_event=tampered_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_binding_mismatch") in reconciliation.reason_codes


def test_zero_pnl_filled_without_event_reconciles() -> None:
    # A filled opening episode legitimately realizes nothing; the substrate cannot prove an event exists, so a
    # zero-PnL record with no event is a complete, reconciled episode (documented completeness boundary).
    scenario = _Scenario([_opening_bundle("ep-0", "rec-0")])
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
    assert reconciliation.zero_pnl_episode_count == 1
    assert reconciliation.filled_episode_count == 1


def test_filled_episode_missing_required_realized_event_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(scenario.inputs[0], realized_pnl_event=None)  # win record still claims +5
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_required") in reconciliation.reason_codes


def test_rejected_fill_carrying_realized_event_rejected() -> None:
    scenario = _Scenario()
    rejected = scenario.inputs[2]
    stray_event = scenario.inputs[0].realized_pnl_event  # a real event, but this episode is REJECTED
    scenario.inputs[2] = replace(rejected, realized_pnl_event=stray_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("unexpected_realized_event") in reconciliation.reason_codes


def test_rejected_fill_nonzero_pnl_rejected() -> None:
    scenario = _Scenario()
    tampered = _reseal_record(scenario.inputs[2].record, realized_pnl="4.000000000000000000")
    scenario.inputs[2] = replace(scenario.inputs[2], record=tampered)
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_pnl_mismatch") in reconciliation.reason_codes


def test_rejected_fill_record_claiming_fill_rejected() -> None:
    scenario = _Scenario()
    tampered = _reseal_record(
        scenario.inputs[2].record,
        filled_quantity="1.000000000000000000",
        realized_fill_price="100.000000000000000000",
    )
    scenario.inputs[2] = replace(scenario.inputs[2], record=tampered)
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("rejected_fill_record_mismatch") in reconciliation.reason_codes


def test_record_policy_id_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, policy_id="other-policy")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("record_policy_id_mismatch") in reconciliation.reason_codes


def test_record_episode_id_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, episode_id="not-the-episode")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("record_episode_id_mismatch") in reconciliation.reason_codes


def test_records_not_in_metrics_evidence_rejected() -> None:
    scenario = _Scenario()
    # Metrics evidence built over only the first two records; substrate supplies all three.
    scenario.metrics = build_paper_secondary_metrics_evidence(
        scenario.policy, scenario.records[:2], evidence_id="sm4-1", correlation_id=_CORR
    )
    reconciliation = scenario.build(expected_metrics_evidence_digest=scenario.metrics.evidence_digest)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("records_not_metrics_evidence") in reconciliation.reason_codes


# --- 5. Malformed input (raise) / scope ---------------------------------------------------------------------


def test_policy_wrong_type_raises() -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        build_paper_secondary_metrics_substrate_reconciliation(
            "policy",
            scenario.metrics,
            scenario.inputs,
            scenario.session,  # type: ignore[arg-type]
            reconciliation_id="r",
            correlation_id=_CORR,
            expected_policy_digest="a" * 64,
            expected_metrics_evidence_digest="a" * 64,
            expected_session_sequence_digest="a" * 64,
        )


def test_empty_inputs_raises() -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        build_paper_secondary_metrics_substrate_reconciliation(
            scenario.policy,
            scenario.metrics,
            [],
            scenario.session,
            reconciliation_id="r",
            correlation_id=_CORR,
            expected_policy_digest=scenario.policy.policy_digest,
            expected_metrics_evidence_digest=scenario.metrics.evidence_digest,
            expected_session_sequence_digest=scenario.session.paper_session_sequence_digest,
        )


def test_wrong_input_element_type_raises() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = "not-an-input"  # type: ignore[assignment]
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build()


@pytest.mark.parametrize("token", ["live-ready", "order_router", "deribit", "BIST-desk", "datetime.utcnow"])
def test_forbidden_metadata_token_raises(token: str) -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build(metadata={"source": token})


@pytest.mark.parametrize("bad", ["  ", "recon\t1"])
def test_malformed_reconciliation_id_raises(bad: str) -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build(reconciliation_id=bad)


# --- 6. Module purity ---------------------------------------------------------------------------------------


def test_source_has_no_forbidden_imports_or_calls() -> None:
    source = Path(recon_module.__file__).read_text(encoding="utf-8")
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
