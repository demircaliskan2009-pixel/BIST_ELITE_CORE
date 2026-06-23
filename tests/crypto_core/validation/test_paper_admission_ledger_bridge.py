"""Tests for the paper admission ledger bridge — deterministic, paper-only, fail-closed append of a paper
evidence admission record (with proven record↔episode chain lineage) into the EXISTING ``EvidenceJournal``.

Covers the happy path, digest/provenance binding (no fake cross-contract equality), the STRONG record↔episode
chain lineage proof + its P2 regression, cross-artifact identity, status/safety/non-overclaim, raw/canonical
adversariality, forbidden-surface exclusion (alias-resistant), journal append/ledger semantics, and
non-overclaim. The happy path shares ONE realized-PnL event between the episode and the admitted manifest, so
``episode.realized_pnl_event_digest`` is a genuine member of ``manifest.source_event_digests``."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    evidence_journal_from_dict,
    evidence_journal_to_dict,
)
from crypto_core.audit.paper_trade_tick_journal_adapter import append_paper_trade_tick_to_evidence_journal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_admission_ledger_bridge as bridge_module
from crypto_core.validation.paper_admission_ledger_bridge import (
    PaperAdmissionLedgerBridgeError,
    PaperAdmissionLedgerBridgeStatus,
    append_paper_admission_record_to_evidence_journal,
    paper_admission_ledger_bridge_digest,
    paper_admission_ledger_bridge_to_dict,
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
from crypto_core.validation.paper_end_to_end_episode import (
    PaperEndToEndEpisodeStatus,
    build_paper_end_to_end_episode,
    paper_end_to_end_episode_digest,
)
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionStatus,
    build_paper_evidence_admission_record,
    paper_evidence_admission_record_digest,
)
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
    paper_session_realized_pnl_evidence_manifest_digest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

_HEX = "b" * 64
_SYMBOL = "BTC-PERPETUAL"
_CORR = "corr-ep"  # runtime correlation shared by the episode chain + the shared realized event
_REQ_CORR = "corr-req"
_RUN = "run-ep"
_EPISODE_ID = "e2e-1"
_UNSET = object()

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


# --------------------------------------------------------------------------------------------------
# Episode chain primitives (shared with the manifest's realized event)
# --------------------------------------------------------------------------------------------------


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


def _e_capacity(*, requested_units: str = "4", requested_notional: str = "200"):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    return evaluate_paper_capacity_gate(
        _make_draft(),
        cap_policy,
        requested_notional=requested_notional,
        requested_units=requested_units,
        correlation_id="corr-capacity",
    )


def _e_request(capacity, *, side: PaperOrderSide = PaperOrderSide.SELL):
    return build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=_SYMBOL,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id=_REQ_CORR,
    )


def _e_order_intent_from(capacity, request, *, intent_id: str = "intent-1"):
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id=intent_id, correlation_id="corr-intent")


def _e_bridge(**overrides):
    spec = _spec()
    capacity = _e_capacity()
    kwargs = {
        "expected_spec_digest": strategy_spec_digest(spec),
        "signal_id": "req-1",
        "run_id": _RUN,
        "correlation_id": _REQ_CORR,
        "market_symbol": _SYMBOL,
        "side": PaperOrderSide.SELL,
        "intent_type": PaperOrderIntentType.MARKET,
        "requested_units": capacity.requested_units,
        "requested_notional": capacity.requested_notional,
        "capacity_decision_digest": capacity.decision_digest,
        "limit_price": None,
    }
    kwargs.update(overrides)
    return build_strategy_signal_to_paper_intent(spec, **kwargs)


def _e_prior_long():
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


def _e_snapshot():
    return build_paper_fill_market_snapshot(
        snapshot_id="snap-1", market_symbol=_SYMBOL, reference_price="50", available_units=None
    )


def _e_policy():
    return build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )


def _e_mark():
    return build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol=_SYMBOL, mark_price="60", correlation_id="corr-mark"
    )


def _e_run(order_intent, prior):
    return run_paper_episode(
        order_intent,
        prior,
        _e_snapshot(),
        _e_policy(),
        _e_mark(),
        **_CHAIN_IDS,  # type: ignore[arg-type]
    )


def _realized_components(order_intent, prior):
    """Build the fill/transition/new-state/event the runner used (shared ids) — the SAME realized event the
    episode binds AND the manifest aggregates, so their digests are byte-identical (genuine lineage)."""
    fill = simulate_paper_fill(
        order_intent,
        _e_snapshot(),
        _e_policy(),
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


# --------------------------------------------------------------------------------------------------
# Manifest chain primitives (session provenance + realized-PnL rollup -> aggregate -> manifest)
# --------------------------------------------------------------------------------------------------


def _mr_intent(*, market_symbol: str = _SYMBOL):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(), cap_policy, requested_notional="100000", requested_units="10", correlation_id="corr-capacity"
    )
    request = build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=market_symbol,
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _mr_episode(suffix: str, *, market_symbol: str = _SYMBOL):
    intent = _mr_intent(market_symbol=market_symbol)
    prior = build_flat_paper_position_state(
        position_state_id=f"pos-{suffix}", market_symbol=market_symbol, correlation_id="corr-pos"
    )
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"snap-{suffix}", market_symbol=market_symbol, reference_price="50"
    )
    policy = build_paper_fill_policy(
        policy_id=f"fill-policy-{suffix}", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"mark-{suffix}", market_symbol=market_symbol, mark_price="60", correlation_id="corr-mark"
    )
    return run_paper_episode(
        intent,
        prior,
        snapshot,
        policy,
        mark,
        fill_simulation_id=f"fillsim-{suffix}",
        position_transition_id=f"trans-{suffix}",
        new_position_state_id=f"newpos-{suffix}",
        pnl_report_id=f"pnl-{suffix}",
        episode_run_id=f"ep-{suffix}",
        correlation_id="corr-ep",
    )


def _mr_prov(idx: str, *, market_symbol: str = _SYMBOL) -> PaperSessionSequenceProvenance:
    eps = [_mr_episode(idx, market_symbol=market_symbol)]
    session = build_paper_session_sequence(eps, paper_session_id=f"sess-{idx}", correlation_id=f"corr-sess-{idx}")
    return PaperSessionSequenceProvenance(session_sequence=session, episodes=tuple(eps))


def _mr_long(*, market_symbol: str = _SYMBOL, idn: str = "1"):
    return build_paper_position_state(
        position_state_id=f"rpos-{idn}",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="100",
        transition_count=0,
        correlation_id="corr-rpos",
    )


def _mr_fill(side: str, filled: str, price: str, *, market_symbol: str = _SYMBOL, idn: str = "1"):
    from decimal import Decimal, localcontext

    from crypto_core.validation.paper_fill_simulator import (
        PaperFillSimulationResult,
        PaperFillSimulationStatus,
        paper_fill_simulation_result_digest,
    )

    with localcontext() as ctx:
        ctx.prec = 400
        product = Decimal(filled) * Decimal(price)
    rendered = format(product, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    gross = "0" if rendered in {"", "-0"} else rendered
    base = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=PaperFillSimulationStatus.FILLED,
        fill_simulation_id=f"rfillsim-{idn}",
        intent_digest=_HEX,
        market_snapshot_digest=_HEX,
        fill_policy_digest=_HEX,
        market_symbol=market_symbol,
        side=side,
        intent_type="MARKET",
        fill_price=price,
        filled_units=filled,
        unfilled_units="0",
        gross_notional=gross,
        fee_amount="0",
        reason_codes=(),
        correlation_id="corr-rfill",
        metadata=(),
        result_digest="",
    )
    return replace(base, result_digest=paper_fill_simulation_result_digest(base))


def _foreign_rollup(event_id: str = "e1", *, market_symbol: str = _SYMBOL) -> PaperRealizedPnlRollupInput:
    """An INDEPENDENT realized event (different fill) -> its source-event digest differs from the episode's."""
    prior = _mr_long(idn=event_id, market_symbol=market_symbol)
    fill = _mr_fill("SELL", "4", "150", idn=event_id, market_symbol=market_symbol)
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=f"rtrans-{event_id}",
        new_position_state_id=f"rnewpos-{event_id}",
        correlation_id="corr-rapply",
    )
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id=event_id, correlation_id="corr-revt"
    )
    return PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )


def _manifest_from_rollup(rollup: PaperRealizedPnlRollupInput, *, market_symbol: str = _SYMBOL):
    prov = _mr_prov("1", market_symbol=market_symbol)
    sbridge = build_paper_session_realized_pnl_bridge(
        prov, (rollup,), bridge_id="bridge-1", correlation_id="corr-bridge"
    )
    agg = build_paper_session_realized_pnl_aggregate(
        [PaperSessionRealizedPnlAggregateInput(bridge=sbridge, session_input=prov, rollup_entries=(rollup,))],
        aggregate_id="agg-1",
        correlation_id="corr-agg",
    )
    return build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=agg.aggregate_digest, correlation_id="corr-manifest"
    )


def _record_from_manifest(manifest, *, correlation_id: str = _CORR, metadata=None):
    return build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id=correlation_id, metadata=metadata
    )


def _foreign_manifest(*, market_symbol: str = _SYMBOL):
    return _manifest_from_rollup(_foreign_rollup(market_symbol=market_symbol), market_symbol=market_symbol)


# --------------------------------------------------------------------------------------------------
# Aligned (record, manifest, episode) — shared realized event proves record↔episode lineage
# --------------------------------------------------------------------------------------------------


def _aligned():
    capacity = _e_capacity()
    order_intent = _e_order_intent_from(capacity, _e_request(capacity))
    bridge = _e_bridge()
    prior = _e_prior_long()
    episode_run = _e_run(order_intent, prior)
    fill, transition, new_state, event = _realized_components(order_intent, prior)

    episode = build_paper_end_to_end_episode(
        bridge,
        order_intent,
        episode_run,
        event,
        expected_bridge_digest=bridge.bridge_digest,
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
    manifest = _manifest_from_rollup(rollup)
    record = _record_from_manifest(manifest)
    return record, manifest, episode


def _append(
    journal: EvidenceJournal,
    *,
    record=None,
    manifest=None,
    episode=None,
    expected_admission_digest=None,
    expected_episode_digest=None,
    expected_prior_journal_head_digest=_UNSET,
    episode_id: str = _EPISODE_ID,
    run_id: str = _RUN,
    correlation_id: str = _CORR,
    metadata=None,
):
    if record is None and manifest is None and episode is None:
        record, manifest, episode = _aligned()
    if expected_prior_journal_head_digest is _UNSET:
        expected_prior_journal_head_digest = journal.head_digest
    return append_paper_admission_record_to_evidence_journal(
        journal,
        record,
        episode,
        manifest,
        expected_admission_digest=expected_admission_digest
        if expected_admission_digest is not None
        else record.admission_digest,
        expected_episode_digest=expected_episode_digest
        if expected_episode_digest is not None
        else episode.episode_digest,
        expected_prior_journal_head_digest=expected_prior_journal_head_digest,
        episode_id=episode_id,
        run_id=run_id,
        correlation_id=correlation_id,
        metadata=metadata,
    )


# --------------------------------------------------------------------------------------------------
# 1. Happy path
# --------------------------------------------------------------------------------------------------


def test_valid_inputs_ready_and_appends_one_entry() -> None:
    record, manifest, episode = _aligned()
    assert record.status is PaperEvidenceAdmissionStatus.ADMITTED
    assert episode.status is PaperEndToEndEpisodeStatus.READY
    # The shared realized event digest is genuinely a member of the admitted manifest's source events.
    assert episode.realized_pnl_event_digest in manifest.source_event_digests
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.READY
    assert bridge.ready is True
    assert bridge.appended is True
    assert bridge.rejection_reasons == ()
    assert bridge.entry_type == "PAPER_EVIDENCE_ADMISSION_RECORD"
    assert bridge.source_event_digest_count == 1
    assert _is_hex64(bridge.ledger_digest)
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True
    assert journal.snapshot()[0].entry_type is EvidenceArtifactType.PAPER_EVIDENCE_ADMISSION_RECORD


def test_all_consumed_digests_are_bound() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode)
    assert bridge.admission_digest == record.admission_digest
    assert bridge.manifest_digest == record.manifest_digest == manifest.manifest_digest
    assert bridge.aggregate_digest == record.aggregate_digest == manifest.aggregate_digest
    assert bridge.episode_digest == episode.episode_digest
    assert bridge.realized_pnl_event_digest == episode.realized_pnl_event_digest
    assert bridge.realized_pnl_event_digest in manifest.source_event_digests
    assert bridge.manifest_status == "READY"


def test_appended_payload_binds_lineage_event_digest() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    _append(journal, record=record, manifest=manifest, episode=episode)
    payload = journal.snapshot()[0].payload
    assert payload["realized_pnl_event_digest"] == episode.realized_pnl_event_digest
    assert payload["manifest_digest"] == manifest.manifest_digest
    assert payload["source_event_digest_count"] == 1


def test_ledger_digest_deterministic_and_recomputes() -> None:
    r1, m1, e1 = _aligned()
    r2, m2, e2 = _aligned()
    a = _append(EvidenceJournal(), record=r1, manifest=m1, episode=e1)
    b = _append(EvidenceJournal(), record=r2, manifest=m2, episode=e2)
    assert a.ledger_digest == b.ledger_digest
    assert paper_admission_ledger_bridge_digest(a) == a.ledger_digest
    assert paper_admission_ledger_bridge_to_dict(a)["ledger_digest"] == a.ledger_digest


def test_changed_bound_field_changes_ledger_digest() -> None:
    r, m, e = _aligned()
    base = _append(EvidenceJournal(), record=r, manifest=m, episode=e)
    other = _append(EvidenceJournal(), record=r, manifest=m, episode=e, metadata={"note": "second"})
    assert base.ledger_digest != other.ledger_digest


# --------------------------------------------------------------------------------------------------
# 2. P2 regression — strong record↔episode chain lineage
# --------------------------------------------------------------------------------------------------


def test_p2_foreign_chain_lineage_unproven_rejects() -> None:
    # A digest-valid ADMITTED record from a DIFFERENT realized-PnL chain + a digest-valid READY episode that
    # share market_symbol / correlation_id / caller episode_id+run_id MUST NOT bind: the episode's realized
    # event digest is absent from the foreign manifest's source events -> lineage unproven, fail closed.
    _, _, episode = _aligned()
    foreign_manifest = _foreign_manifest()
    foreign_record = _record_from_manifest(foreign_manifest, correlation_id=_CORR)
    assert foreign_record.status is PaperEvidenceAdmissionStatus.ADMITTED
    assert foreign_record.market_symbol == episode.market_symbol == _SYMBOL
    assert episode.realized_pnl_event_digest not in foreign_manifest.source_event_digests
    journal = EvidenceJournal()
    bridge = _append(journal, record=foreign_record, manifest=foreign_manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert bridge.ready is False
    assert any("record_episode_lineage_unproven" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0
    assert journal.head_digest is None


def test_str_subclass_episode_event_digest_cannot_bypass_lineage() -> None:
    record, manifest, episode = _aligned()
    liar_episode = replace(episode, realized_pnl_event_digest=_LiarStr(episode.realized_pnl_event_digest))
    sealed = replace(liar_episode, episode_digest=paper_end_to_end_episode_digest(liar_episode))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=record, manifest=manifest, episode=sealed, expected_episode_digest=sealed.episode_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("record_episode_lineage_unproven" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


# --------------------------------------------------------------------------------------------------
# 3. Manifest binding / digest provenance
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_admission_digest_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, expected_admission_digest="a" * 64)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_wrong_expected_episode_digest_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, expected_episode_digest="a" * 64)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_forged_admission_self_digest_rejects() -> None:
    record, manifest, episode = _aligned()
    forged = replace(record, admission_digest="0" * 64)
    journal = EvidenceJournal()
    bridge = _append(journal, record=forged, manifest=manifest, episode=episode, expected_admission_digest="0" * 64)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_foreign_manifest_digest_mismatch_rejects() -> None:
    # A self-consistent manifest that is NOT the one the record admitted -> manifest_digest_mismatch.
    record, _, episode = _aligned()
    foreign_manifest = _foreign_manifest()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=foreign_manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("manifest_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_forged_manifest_self_digest_rejects() -> None:
    record, manifest, episode = _aligned()
    forged_manifest = replace(manifest, manifest_digest="0" * 64)
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=forged_manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("manifest_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_aggregate_binding_mismatch_rejects() -> None:
    record, manifest, episode = _aligned()
    tampered = replace(manifest, aggregate_digest="0" * 64)
    sealed = replace(tampered, manifest_digest=paper_session_realized_pnl_evidence_manifest_digest(tampered))
    # Rebuild the record so the manifest self-digest re-proves against record.manifest_digest, isolating the
    # aggregate binding check.
    rebuilt = replace(record, manifest_digest=sealed.manifest_digest)
    rebuilt = replace(rebuilt, admission_digest=paper_evidence_admission_record_digest(rebuilt))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=rebuilt, manifest=sealed, episode=episode, expected_admission_digest=rebuilt.admission_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("aggregate_binding_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_wrong_prior_journal_head_digest_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=record, manifest=manifest, episode=episode, expected_prior_journal_head_digest="b" * 64
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("prior_journal_head_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


# --------------------------------------------------------------------------------------------------
# 4. Cross-artifact identity
# --------------------------------------------------------------------------------------------------


def test_episode_id_mismatch_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, episode_id="other-episode")
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_id_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_run_id_mismatch_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, run_id="other-run")
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("run_id_mismatch" in r for r in bridge.rejection_reasons)


def test_caller_correlation_mismatch_rejects() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, correlation_id="corr-other")
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_correlation_mismatch" in r for r in bridge.rejection_reasons)
    assert any("admission_correlation_mismatch" in r for r in bridge.rejection_reasons)


def test_admission_record_correlation_mismatch_rejects() -> None:
    record, manifest, episode = _aligned()
    other_record = _record_from_manifest(manifest, correlation_id="corr-adm-other")
    journal = EvidenceJournal()
    bridge = _append(journal, record=other_record, manifest=manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_correlation_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_market_symbol_mismatch_rejects() -> None:
    _, _, episode = _aligned()
    eth_manifest = _foreign_manifest(market_symbol="ETH-PERPETUAL")
    eth_record = _record_from_manifest(eth_manifest, correlation_id=_CORR)
    assert eth_record.status is PaperEvidenceAdmissionStatus.ADMITTED
    journal = EvidenceJournal()
    bridge = _append(journal, record=eth_record, manifest=eth_manifest, episode=episode)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("symbol_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


# --------------------------------------------------------------------------------------------------
# 5. Status / safety
# --------------------------------------------------------------------------------------------------


def test_admission_not_admitted_rejects() -> None:
    _, manifest, episode = _aligned()
    rejected = build_paper_evidence_admission_record(manifest, expected_manifest_digest="a" * 64, correlation_id=_CORR)
    assert rejected.status is PaperEvidenceAdmissionStatus.REJECTED
    journal = EvidenceJournal()
    bridge = _append(
        journal,
        record=rejected,
        manifest=manifest,
        episode=episode,
        expected_admission_digest=rejected.admission_digest,
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_not_admitted" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_episode_not_ready_rejects() -> None:
    record, manifest, _ = _aligned()
    capacity = _e_capacity()
    order_intent = _e_order_intent_from(capacity, _e_request(capacity))
    bridge_artifact = _e_bridge()
    prior = _e_prior_long()
    episode_run = _e_run(order_intent, prior)
    _, _, _, event = _realized_components(order_intent, prior)
    rejected_episode = build_paper_end_to_end_episode(
        bridge_artifact,
        order_intent,
        episode_run,
        event,
        expected_bridge_digest="d" * 64,  # wrong anchor -> REJECTED episode
        expected_order_intent_digest=order_intent.intent_digest,
        expected_episode_run_digest=episode_run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=_EPISODE_ID,
        run_id=_RUN,
        correlation_id=_CORR,
    )
    assert rejected_episode.status is PaperEndToEndEpisodeStatus.REJECTED
    journal = EvidenceJournal()
    bridge = _append(
        journal,
        record=record,
        manifest=manifest,
        episode=rejected_episode,
        expected_episode_digest=rejected_episode.episode_digest,
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_not_ready" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_resealed_unsafe_admission_flag_rejects() -> None:
    record, manifest, episode = _aligned()
    tampered = replace(record, order_routed=True)
    sealed = replace(tampered, admission_digest=paper_evidence_admission_record_digest(tampered))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=sealed, manifest=manifest, episode=episode, expected_admission_digest=sealed.admission_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_unsafe_flags" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_resealed_unsafe_manifest_flag_rejects() -> None:
    record, manifest, episode = _aligned()
    tampered = replace(manifest, order_routed=True)
    sealed = replace(tampered, manifest_digest=paper_session_realized_pnl_evidence_manifest_digest(tampered))
    rebuilt = replace(record, manifest_digest=sealed.manifest_digest)
    rebuilt = replace(rebuilt, admission_digest=paper_evidence_admission_record_digest(rebuilt))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=rebuilt, manifest=sealed, episode=episode, expected_admission_digest=rebuilt.admission_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("manifest_unsafe_flags" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_resealed_unsafe_episode_flag_rejects() -> None:
    record, manifest, episode = _aligned()
    tampered = replace(episode, live_api_called=True)
    sealed = replace(tampered, episode_digest=paper_end_to_end_episode_digest(tampered))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=record, manifest=manifest, episode=sealed, expected_episode_digest=sealed.episode_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_unsafe_flags" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_resealed_overclaim_episode_flag_rejects() -> None:
    record, manifest, episode = _aligned()
    tampered = replace(episode, prdv4_stage4_complete=True)
    sealed = replace(tampered, episode_digest=paper_end_to_end_episode_digest(tampered))
    journal = EvidenceJournal()
    bridge = _append(
        journal, record=record, manifest=manifest, episode=sealed, expected_episode_digest=sealed.episode_digest
    )
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("episode_unsafe_flags" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_non_overclaim_flags_false_and_bound() -> None:
    payload = paper_admission_ledger_bridge_to_dict(_append(EvidenceJournal()))
    for flag in (
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "profitability_proven",
        "edge_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "order_routed",
    ):
        assert payload[flag] is False
    assert payload["paper_only"] is True


# --------------------------------------------------------------------------------------------------
# 6. Raw / canonical adversariality
# --------------------------------------------------------------------------------------------------


def test_str_subclass_correlation_id_raises() -> None:
    journal = EvidenceJournal()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="correlation_id_invalid"):
        _append(journal, correlation_id=_LiarStr("corr-ep"))


def test_equality_liar_admission_digest_cannot_bypass() -> None:
    record, manifest, episode = _aligned()
    liar = replace(record, admission_digest=_LiarStr(record.admission_digest))
    journal = EvidenceJournal()
    bridge = _append(journal, record=liar, manifest=manifest, episode=episode, expected_admission_digest="a" * 64)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_digest_mismatch" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_admission_serializer_error_rejected_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_artifact: object) -> str:
        raise RuntimeError("digest exploded")

    monkeypatch.setattr(bridge_module, "paper_evidence_admission_record_digest", boom)
    journal = EvidenceJournal()
    bridge = _append(journal)
    assert bridge.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("admission_malformed" in r for r in bridge.rejection_reasons)
    assert journal.entry_count == 0


def test_appended_payload_has_no_forbidden_token_keys() -> None:
    journal = EvidenceJournal()
    _append(journal)
    payload = journal.snapshot()[0].payload
    banned = ("order", "scheduler", "auto_loop", "live", "shadow", "connector_ready", "credential")
    for key in payload:
        lowered = key.lower()
        assert all(token not in lowered for token in banned), key


@pytest.mark.parametrize("bad_metadata", [{"k": 5}, {5: "v"}, ["not", "a", "map"]])
def test_malformed_metadata_raises(bad_metadata: object) -> None:
    journal = EvidenceJournal()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="metadata_malformed"):
        _append(journal, metadata=bad_metadata)


@pytest.mark.parametrize("correlation_id", ["live_order", "bist", "scheduler", "place_order"])
def test_scope_violation_in_ids_raises(correlation_id: str) -> None:
    journal = EvidenceJournal()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="scope_violation"):
        _append(journal, correlation_id=correlation_id)


# --------------------------------------------------------------------------------------------------
# 7. Fail-closed: call-level input
# --------------------------------------------------------------------------------------------------


def _call(journal, record, episode, manifest, **overrides):
    kwargs = {
        "expected_admission_digest": "a" * 64,
        "expected_episode_digest": "a" * 64,
        "expected_prior_journal_head_digest": None,
        "episode_id": _EPISODE_ID,
        "run_id": _RUN,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return append_paper_admission_record_to_evidence_journal(journal, record, episode, manifest, **kwargs)


def test_wrong_typed_journal_raises() -> None:
    record, manifest, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="journal_malformed"):
        _call("not-a-journal", record, episode, manifest)  # type: ignore[arg-type]


def test_wrong_typed_record_raises() -> None:
    _, manifest, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="record_malformed"):
        _call(EvidenceJournal(), {"not": "a-record"}, episode, manifest)  # type: ignore[arg-type]


def test_wrong_typed_episode_raises() -> None:
    record, manifest, _ = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="episode_malformed"):
        _call(EvidenceJournal(), record, {"not": "an-episode"}, manifest)  # type: ignore[arg-type]


def test_wrong_typed_manifest_raises() -> None:
    record, _, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="manifest_malformed"):
        _call(EvidenceJournal(), record, episode, {"not": "a-manifest"})  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65])
def test_malformed_expected_admission_digest_raises(bad: str) -> None:
    record, manifest, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="expected_admission_digest_invalid"):
        _call(EvidenceJournal(), record, episode, manifest, expected_admission_digest=bad)


def test_malformed_prior_head_anchor_raises() -> None:
    record, manifest, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="expected_prior_journal_head_digest_invalid"):
        _call(
            EvidenceJournal(),
            record,
            episode,
            manifest,
            expected_admission_digest=record.admission_digest,
            expected_episode_digest=episode.episode_digest,
            expected_prior_journal_head_digest="not-hex",
        )


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_episode_id_raises(bad: str) -> None:
    record, manifest, episode = _aligned()
    with pytest.raises(PaperAdmissionLedgerBridgeError, match="episode_id_invalid"):
        _call(EvidenceJournal(), record, episode, manifest, episode_id=bad)


# --------------------------------------------------------------------------------------------------
# 8. Journal append / ledger semantics
# --------------------------------------------------------------------------------------------------


def test_rejection_leaves_journal_unchanged() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    bridge = _append(journal, record=record, manifest=manifest, episode=episode, expected_admission_digest="a" * 64)
    assert bridge.appended is False
    assert bridge.resulting_journal_entry_count == 0
    assert bridge.resulting_journal_head_digest is None
    assert journal.entry_count == 0
    assert journal.head_digest is None


def test_duplicate_append_fails_closed_journal_unchanged() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    first = _append(journal, record=record, manifest=manifest, episode=episode)
    assert first.ready is True
    head_after_first = journal.head_digest
    second = _append(journal, record=record, manifest=manifest, episode=episode)
    assert second.status is PaperAdmissionLedgerBridgeStatus.REJECTED
    assert any("journal_append_rejected" in r for r in second.rejection_reasons)
    assert journal.entry_count == 1
    assert journal.head_digest == head_after_first


def test_append_to_non_empty_journal_chains() -> None:
    record, manifest, episode = _aligned()
    journal = EvidenceJournal()
    tick = build_paper_trade_tick(
        tick_id="tick-1",
        action="BUY",
        intent_type="LIMIT",
        instrument_id="BTC-USD",
        quantity="1.5",
        strategy_id="momentum-1",
        run_plan_id="run-1",
        upstream_report_digest="f" * 64,
        correlation_id="corr-seed",
        limit_price="20000.5",
    )
    append_paper_trade_tick_to_evidence_journal(journal, tick, correlation_id="corr:seed")
    prior_head = journal.head_digest
    bridge = _append(
        journal, record=record, manifest=manifest, episode=episode, expected_prior_journal_head_digest=prior_head
    )
    assert bridge.ready is True
    assert bridge.prior_journal_entry_count == 1
    assert bridge.prior_journal_head_digest == prior_head
    assert bridge.resulting_journal_entry_count == 2
    assert journal.entry_count == 2
    assert journal.verify_chain().accepted is True


def test_journal_serialization_round_trip() -> None:
    journal = EvidenceJournal()
    _append(journal)
    data = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=journal.entry_count, expected_head_digest=journal.head_digest
    )
    assert loaded.entry_count == 1
    assert loaded.verify_chain().accepted is True
    assert loaded.snapshot()[0].entry_type is EvidenceArtifactType.PAPER_EVIDENCE_ADMISSION_RECORD


# --------------------------------------------------------------------------------------------------
# 9. Immutability / forbidden surfaces
# --------------------------------------------------------------------------------------------------


def test_output_frozen() -> None:
    bridge = _append(EvidenceJournal())
    with pytest.raises(FrozenInstanceError):
        bridge.ready = False  # type: ignore[misc]


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
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules.isdisjoint(
        {
            "service",
            "connector",
            "runtime",
            "venue",
            "execution",
            "orchestrator",
            "session",
            "temporal",
            "data",
            "portfolio",
        }
    )
    assert crypto_submodules <= {"audit", "validation", "strategy"}


def test_no_forbidden_module_imports() -> None:
    tree = ast.parse(Path(bridge_module.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = (
        "crypto_core.service.readiness",
        "crypto_core.service",
        "crypto_core.execution.paper_adapter",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
    )
    for module in imported:
        assert module not in forbidden, module
        assert "paper_live_service" not in module, module
        assert "paper_shadow_session_controller" not in module, module
        assert "readiness" not in module, module


def test_journals_under_own_artifact_type() -> None:
    source = Path(bridge_module.__file__).read_text(encoding="utf-8")
    assert "EvidenceArtifactType.PAPER_EVIDENCE_ADMISSION_RECORD" in source
    assert "PAPER_TRADE_TICK" not in source
    assert "PAPER_REPLAY_RESULT_REPORT" not in source


def test_public_api_exact() -> None:
    assert set(bridge_module.__all__) == {
        "PaperAdmissionLedgerBridge",
        "PaperAdmissionLedgerBridgeError",
        "PaperAdmissionLedgerBridgeStatus",
        "append_paper_admission_record_to_evidence_journal",
        "paper_admission_ledger_bridge_digest",
        "paper_admission_ledger_bridge_to_dict",
    }
    banned = ("execute", "route", "router", "send", "submit", "schedule", "place_order", "venue", "live")
    for name in bridge_module.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name
