"""Tests for the paper session realized-PnL evidence manifest — deterministic, paper-only, gross-only,
consumer/cross-check over a provenance-bound realized-PnL aggregate with an independent expected digest."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_session_realized_pnl_evidence_manifest
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
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_simulation_result_digest,
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
    paper_session_realized_pnl_aggregate_digest,
    paper_session_realized_pnl_aggregate_to_dict,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
)
from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    PaperSessionRealizedPnlEvidenceManifestError,
    PaperSessionRealizedPnlEvidenceManifestStatus,
    build_paper_session_realized_pnl_evidence_manifest,
    paper_session_realized_pnl_evidence_manifest_digest,
    paper_session_realized_pnl_evidence_manifest_to_dict,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence

_HEX = "b" * 64
_AGG_DIGEST_FN = (
    "crypto_core.validation.paper_session_realized_pnl_aggregate.paper_session_realized_pnl_aggregate_digest"
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _reseal(aggregate):
    """Recompute the aggregate self-digest after an in-place tamper (resealed, self-consistent)."""
    return replace(aggregate, aggregate_digest=paper_session_realized_pnl_aggregate_digest(aggregate))


# --------------------------------------------------------------------------------------------------
# Session-sequence fixtures (mirror test_paper_session_realized_pnl_aggregate.py)
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


def _intent(*, market_symbol: str = "BTC-PERPETUAL"):
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


def _episode(suffix: str, *, market_symbol: str = "BTC-PERPETUAL"):
    intent = _intent(market_symbol=market_symbol)
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


def _episode_list(suffixes=("1",), *, market_symbol: str = "BTC-PERPETUAL"):
    return [_episode(s, market_symbol=market_symbol) for s in suffixes]


def _session_result(episodes, *, paper_session_id: str, correlation_id: str):
    return build_paper_session_sequence(episodes, paper_session_id=paper_session_id, correlation_id=correlation_id)


def _prov_for(idx: str, *, market_symbol: str = "BTC-PERPETUAL") -> PaperSessionSequenceProvenance:
    eps = _episode_list((idx,), market_symbol=market_symbol)
    session = _session_result(eps, paper_session_id=f"sess-{idx}", correlation_id=f"corr-sess-{idx}")
    return PaperSessionSequenceProvenance(session_sequence=session, episodes=tuple(eps))


# --------------------------------------------------------------------------------------------------
# Realized-PnL provenance-bundle fixtures
# --------------------------------------------------------------------------------------------------


def _exact_gross(filled_units: str, fill_price: str) -> str:
    with localcontext() as ctx:
        ctx.prec = 400
        product = Decimal(filled_units) * Decimal(fill_price)
    rendered = format(product, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _long(*, avg: str = "100", market_symbol: str = "BTC-PERPETUAL", idn: str = "1"):
    return build_paper_position_state(
        position_state_id=f"rpos-{idn}",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-rpos",
    )


def _rflat(*, market_symbol: str = "BTC-PERPETUAL", idn: str = "1"):
    return build_flat_paper_position_state(
        position_state_id=f"rpos-{idn}", market_symbol=market_symbol, correlation_id="corr-rpos"
    )


def _fill(
    side: str, filled: str, price: str, *, market_symbol: str = "BTC-PERPETUAL", idn: str = "1"
) -> PaperFillSimulationResult:
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
        gross_notional=_exact_gross(filled, price),
        fee_amount="0",
        reason_codes=(),
        correlation_id="corr-rfill",
        metadata=(),
        result_digest="",
    )
    return replace(base, result_digest=paper_fill_simulation_result_digest(base))


def _bundle(
    event_id: str,
    *,
    prior_side: str = "LONG",
    avg: str = "100",
    price: str = "150",
    filled: str = "4",
    market_symbol: str = "BTC-PERPETUAL",
) -> PaperRealizedPnlRollupInput:
    if prior_side == "LONG":
        prior = _long(avg=avg, market_symbol=market_symbol, idn=event_id)
        fill = _fill("SELL", filled, price, market_symbol=market_symbol, idn=event_id)
    else:  # FLAT — open from flat (NO_REALIZED_PNL)
        prior = _rflat(market_symbol=market_symbol, idn=event_id)
        fill = _fill("BUY", filled, price, market_symbol=market_symbol, idn=event_id)
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


def _no_realized(event_id: str, **kwargs: object) -> PaperRealizedPnlRollupInput:
    return _bundle(event_id, prior_side="FLAT", filled="10", price="100", **kwargs)  # type: ignore[arg-type]


def _entry_from(prov, *, bridge_id: str, bundles, bridge_correlation: str = "corr-bridge"):
    ents = tuple(bundles)
    bridge = build_paper_session_realized_pnl_bridge(prov, ents, bridge_id=bridge_id, correlation_id=bridge_correlation)
    return PaperSessionRealizedPnlAggregateInput(bridge=bridge, session_input=prov, rollup_entries=ents)


def _entry(idx: str = "1", *, bridge_id: str | None = None, bundles=None, market_symbol: str = "BTC-PERPETUAL"):
    prov = _prov_for(idx, market_symbol=market_symbol)
    ents = tuple(bundles) if bundles is not None else (_bundle(f"e{idx}", market_symbol=market_symbol),)
    return _entry_from(prov, bridge_id=bridge_id or f"bridge-{idx}", bundles=ents)


def _aggregate(entries=None, **overrides):
    base: dict[str, object] = {"aggregate_id": "agg-1", "correlation_id": "corr-agg"}
    base.update(overrides)
    ents = entries if entries is not None else [_entry("1")]
    return build_paper_session_realized_pnl_aggregate(ents, **base)  # type: ignore[arg-type]


def _manifest(aggregate=None, *, expected=None, correlation_id: str = "corr-manifest", metadata=None):
    agg = aggregate if aggregate is not None else _aggregate([_entry("1")])
    digest = expected if expected is not None else agg.aggregate_digest
    return build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=digest, correlation_id=correlation_id, metadata=metadata
    )


# --------------------------------------------------------------------------------------------------
# Output-contract sets
# --------------------------------------------------------------------------------------------------

_EXPECTED_KEYS = {
    "schema_version",
    "status",
    "ready",
    "aggregate_id",
    "aggregate_digest",
    "expected_aggregate_digest",
    "market_symbol",
    "session_bridge_count",
    "session_sequence_digests",
    "bridge_digests",
    "rollup_digests",
    "source_event_digests",
    "fill_simulation_result_digests",
    "position_transition_digests",
    "episode_count_total",
    "event_count",
    "computed_event_count",
    "no_realized_event_count",
    "closed_units_total",
    "realized_pnl_total",
    "rejection_reasons",
    "insufficient_evidence_reasons",
    "correlation_id",
    "metadata",
    "manifest_digest",
    "paper_only",
    "gross_only",
    "fees_included",
    "unrealized_pnl_included",
    "total_pnl_computed",
    "equity_or_capital_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
}

_FORBIDDEN_VALUE_KEYS = {
    "unrealized_pnl",
    "unrealized_pnl_total",
    "total_pnl",
    "equity",
    "equity_total",
    "capital",
    "capital_total",
    "capital_balance",
    "margin",
    "balance",
    "fee_amount",
    "fees",
    "order_id",
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
}

_SAFE_FALSE_FLAGS = (
    "fees_included",
    "unrealized_pnl_included",
    "total_pnl_computed",
    "equity_or_capital_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
)


# --------------------------------------------------------------------------------------------------
# Happy path / READY
# --------------------------------------------------------------------------------------------------


def test_ready_manifest_happy_path() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.ready is True
    assert manifest.rejection_reasons == ()
    assert manifest.insufficient_evidence_reasons == ()
    assert manifest.aggregate_id == agg.aggregate_id
    assert manifest.aggregate_digest == agg.aggregate_digest
    assert manifest.market_symbol == "BTC-PERPETUAL"
    assert manifest.session_bridge_count == 1
    assert manifest.event_count == 1
    assert manifest.computed_event_count == 1
    assert manifest.no_realized_event_count == 0
    assert manifest.realized_pnl_total == "200"
    assert manifest.closed_units_total == "4"
    assert manifest.bridge_digests == agg.bridge_digests
    assert manifest.session_sequence_digests == agg.session_sequence_digests
    assert manifest.rollup_digests == agg.rollup_digests
    assert manifest.source_event_digests == agg.source_event_digests
    assert manifest.fill_simulation_result_digests == agg.fill_simulation_result_digests
    assert manifest.position_transition_digests == agg.position_transition_digests
    assert manifest.gross_only is True
    assert _is_hex64(manifest.manifest_digest)


def test_two_bridge_aggregate_manifest_ready() -> None:
    agg = _aggregate([_entry("1"), _entry("2")])
    manifest = _manifest(agg)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.session_bridge_count == 2
    assert manifest.event_count == 2
    assert manifest.realized_pnl_total == "400"
    assert len(manifest.bridge_digests) == 2


def test_insufficient_evidence_when_no_computed_events() -> None:
    agg = _aggregate([_entry("1", bundles=(_no_realized("n1"),))])
    manifest = _manifest(agg)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.INSUFFICIENT_EVIDENCE
    assert manifest.ready is False
    assert any("no_computed_realized_events" in r for r in manifest.insufficient_evidence_reasons)
    assert manifest.rejection_reasons == ()
    assert manifest.computed_event_count == 0
    assert manifest.realized_pnl_total == "0"


# --------------------------------------------------------------------------------------------------
# Determinism / digest binding
# --------------------------------------------------------------------------------------------------


def test_manifest_digest_deterministic_and_recomputes() -> None:
    agg = _aggregate([_entry("1")])
    m1 = _manifest(agg, correlation_id="corr-manifest")
    m2 = _manifest(agg, correlation_id="corr-manifest")
    assert m1.manifest_digest == m2.manifest_digest
    assert paper_session_realized_pnl_evidence_manifest_digest(m1) == m1.manifest_digest
    assert paper_session_realized_pnl_evidence_manifest_to_dict(m1)["manifest_digest"] == m1.manifest_digest


def test_correlation_id_changes_manifest_digest() -> None:
    agg = _aggregate([_entry("1")])
    a = _manifest(agg, correlation_id="corr-a")
    b = _manifest(agg, correlation_id="corr-b")
    assert a.manifest_digest != b.manifest_digest


def test_metadata_canonicalized_deterministic() -> None:
    agg = _aggregate([_entry("1")])
    a = _manifest(agg, correlation_id="c", metadata={"z": "1", "a": "2"})
    b = _manifest(agg, correlation_id="c", metadata={"a": "2", "z": "1"})
    assert a.metadata == (("a", "2"), ("z", "1"))  # sorted, order-independent
    assert a.manifest_digest == b.manifest_digest


# --------------------------------------------------------------------------------------------------
# Single-snapshot / no-double-read (Codex P1)
# --------------------------------------------------------------------------------------------------


def test_aggregate_serializer_called_exactly_once_no_toctou(monkeypatch: pytest.MonkeyPatch) -> None:
    # The builder must serialize the aggregate EXACTLY once; a stateful serializer whose 2nd call diverges
    # (binds aaaa... while a re-read would cover bbbb...) cannot create a divergence window.
    agg = _aggregate([_entry("1")])
    genuine = paper_session_realized_pnl_aggregate_to_dict(agg)  # captured before patching (no counter bump)
    divergent = dict(genuine)
    divergent["aggregate_digest"] = "b" * 64
    divergent["bridge_digests"] = ["b" * 64]
    calls = {"n": 0}

    def fake_to_dict(aggregate):
        calls["n"] += 1
        return genuine if calls["n"] == 1 else divergent

    monkeypatch.setattr(
        paper_session_realized_pnl_evidence_manifest, "paper_session_realized_pnl_aggregate_to_dict", fake_to_dict
    )
    manifest = _manifest(agg)
    assert calls["n"] == 1  # serialized exactly once -> no TOCTOU window
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.bridge_digests == agg.bridge_digests  # bound from the single genuine snapshot


def test_builder_does_not_call_public_aggregate_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    # The builder must recompute the aggregate digest from its single snapshot, never via a second read of
    # the aggregate through the PUBLIC digest helper.
    agg = _aggregate([_entry("1")])
    expected = agg.aggregate_digest

    def boom(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("manifest builder must not call paper_session_realized_pnl_aggregate_digest")

    monkeypatch.setattr(_AGG_DIGEST_FN, boom)
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=expected, correlation_id="c"
    )
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY


# --------------------------------------------------------------------------------------------------
# Independent expected aggregate digest (Codex P1/P2)
# --------------------------------------------------------------------------------------------------


def test_expected_digest_required_keyword() -> None:
    agg = _aggregate([_entry("1")])
    with pytest.raises(TypeError):
        build_paper_session_realized_pnl_evidence_manifest(agg, correlation_id="c")  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65, 5, None])
def test_malformed_expected_digest_raises(bad: object) -> None:
    agg = _aggregate([_entry("1")])
    with pytest.raises(PaperSessionRealizedPnlEvidenceManifestError, match="expected_aggregate_digest_invalid"):
        build_paper_session_realized_pnl_evidence_manifest(
            agg,
            expected_aggregate_digest=bad,
            correlation_id="c",  # type: ignore[arg-type]
        )


def test_correct_expected_digest_ready() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg, expected=agg.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY


def test_wrong_expected_digest_rejected() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg, expected="a" * 64)  # well-formed but not the aggregate's digest
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("expected_aggregate_digest_mismatch" in r for r in manifest.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Fail-closed: aggregate digest re-proof
# --------------------------------------------------------------------------------------------------


def test_forged_aggregate_digest_rejected() -> None:
    agg = _aggregate([_entry("1")])
    genuine = agg.aggregate_digest
    forged = replace(agg, aggregate_digest="d" * 64)  # canonical hex64 but not the real digest
    manifest = _manifest(forged, expected=genuine)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_digest_mismatch" in r for r in manifest.rejection_reasons)


def test_invalid_shape_aggregate_digest_rejected() -> None:
    agg = _aggregate([_entry("1")])
    genuine = agg.aggregate_digest
    forged = replace(agg, aggregate_digest="not-a-digest")
    manifest = _manifest(forged, expected=genuine)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_digest_invalid" in r for r in manifest.rejection_reasons)


def test_tampered_aggregate_payload_unsealed_rejected() -> None:
    # Tamper a material field WITHOUT recomputing the aggregate digest -> snapshot recompute mismatch.
    agg = _aggregate([_entry("1")])
    genuine = agg.aggregate_digest
    tampered = replace(agg, realized_pnl_total="999")
    manifest = _manifest(tampered, expected=genuine)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_digest_mismatch" in r for r in manifest.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Fail-closed: resealed economic tamper caught by the ORIGINAL expected digest (Codex P1/P2 boundary)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("realized_pnl_total", "999"),
        ("closed_units_total", "999"),
        ("market_symbol", "ETH-PERPETUAL"),
        ("session_bridge_count", 5),
    ],
)
def test_resealed_economic_tamper_rejected_with_original_expected(field: str, value: object) -> None:
    # A resealed (self-consistent) tamper is caught because the caller holds the GENUINE expected digest:
    # reseal changes the aggregate digest, so expected != recomputed.
    agg = _aggregate([_entry("1")])
    genuine = agg.aggregate_digest
    tampered = _reseal(replace(agg, **{field: value}))
    assert paper_session_realized_pnl_aggregate_digest(tampered) == tampered.aggregate_digest  # self-consistent
    manifest = _manifest(tampered, expected=genuine)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("expected_aggregate_digest_mismatch" in r for r in manifest.rejection_reasons)


def test_trust_boundary_coherent_tamper_with_matching_expected_is_recorded() -> None:
    # Trust-boundary clarity: if the caller's expected digest matches a fully self-consistent (resealed)
    # aggregate, the manifest records it on the caller's authority. The manifest is NOT, by itself, an
    # independent tamper-proof of the aggregate's economics — the expected digest is the trust anchor.
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, realized_pnl_total="999"))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.realized_pnl_total == "999"


# --------------------------------------------------------------------------------------------------
# Fail-closed: chain/count cross-checks (resealed + matching expected to reach the invariant)
# --------------------------------------------------------------------------------------------------


def test_resealed_bridge_count_inconsistency_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, session_bridge_count=99))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("bridge_count_mismatch" in r for r in manifest.rejection_reasons)


def test_resealed_event_chain_count_mismatch_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, source_event_digests=()))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("event_count_mismatch" in r for r in manifest.rejection_reasons)


def test_resealed_event_count_incoherent_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, computed_event_count=5))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("event_count_incoherent" in r for r in manifest.rejection_reasons)


def test_resealed_malformed_digest_chain_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, bridge_digests=("not-hex",)))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("digest_chain_malformed" in r for r in manifest.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Fail-closed: malformed totals (resealed + matching expected to reach the totals invariant)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "not-a-decimal", "", "1e5", "00", "-0"])
def test_resealed_malformed_realized_total_rejected(value: str) -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, realized_pnl_total=value))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("realized_pnl_total_malformed" in r for r in manifest.rejection_reasons)


@pytest.mark.parametrize("value", ["-1", "NaN", "not-a-decimal", ""])
def test_resealed_invalid_closed_units_rejected(value: str) -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, closed_units_total=value))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("closed_units_total_invalid" in r for r in manifest.rejection_reasons)


def test_canonical_zero_total_preserved() -> None:
    e1 = _entry("1", bundles=(_bundle("g1", price="150"),))  # +200
    e2 = _entry("2", bundles=(_bundle("l1", price="50"),))  # -200
    agg = _aggregate([e1, e2])
    manifest = _manifest(agg)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.realized_pnl_total == "0"
    assert manifest.closed_units_total == "8"


# --------------------------------------------------------------------------------------------------
# Fail-closed: aggregate invariants (resealed + matching expected to reach the invariant)
# --------------------------------------------------------------------------------------------------


def test_forged_aggregate_schema_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, schema_version="forged-schema.v1"))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_schema_invalid" in r for r in manifest.rejection_reasons)


def test_empty_aggregate_id_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, aggregate_id=""))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_id_or_symbol_invalid" in r for r in manifest.rejection_reasons)


def test_aggregate_not_computed_flag_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, aggregate_computed=False))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_not_computed" in r for r in manifest.rejection_reasons)


def test_aggregate_safety_flag_true_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, order_routed=True))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_safety_violation" in r for r in manifest.rejection_reasons)


def test_internal_aggregate_correlation_scope_leak_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, correlation_id="live_order"))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_scope_violation" in r for r in manifest.rejection_reasons)


def test_internal_aggregate_metadata_scope_leak_rejected() -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, metadata=(("note", "scheduler"),)))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_scope_violation" in r for r in manifest.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Fail-closed: forged-but-self-consistent aggregate INTERNAL scope/structure bypass (Codex re-audit P1/P2)
# A resealed aggregate matching its own (caller-supplied) expected digest passes the triple-digest binding;
# the manifest must still STRUCTURALLY re-prove + scope-guard the aggregate's internal correlation_id /
# metadata / reason_codes from the single snapshot, so a non-string id, nested/non-string metadata, or
# non-empty reason_codes cannot smuggle a forbidden token (or otherwise diverge) into a READY manifest.
# --------------------------------------------------------------------------------------------------


# Malformed aggregate metadata/reason_codes now fail closed in the AGGREGATE serializer itself (see
# test_paper_session_realized_pnl_aggregate.py). The manifest captures the aggregate snapshot via that public
# serializer EXACTLY once, so a malformed aggregate can no longer be serialized: snapshot capture fails and
# the manifest records REJECTED (aggregate_payload_invalid) — never READY. A non-resealed malformed aggregate
# paired with a syntactically valid arbitrary expected digest exercises exactly that end state.


@pytest.mark.parametrize(
    "bad_metadata",
    [
        {"li": "scheduler"},  # dict -> a blind list(...) would lose the value and collide ('li' -> ['l','i'])
        ("ab",),  # one-dimensional
        (("nested", {"x": "scheduler"}),),  # nested dict value (forbidden token would be hidden)
        (("nested", ["scheduler"]),),  # nested list value
        (("k", 5),),  # non-string value
        ((5, "v"),),  # non-string key
        (("k",),),  # malformed pair length (short)
        (("k", "v", "x"),),  # malformed pair length (long)
        (("k", "v"), ("k", "w")),  # duplicate key
    ],
)
def test_malformed_aggregate_metadata_cannot_ready(bad_metadata: object) -> None:
    agg = replace(_aggregate([_entry("1")]), metadata=bad_metadata)
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest="a" * 64, correlation_id="c"
    )
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert manifest.ready is False
    assert any("aggregate_payload_invalid" in r for r in manifest.rejection_reasons)


def test_hidden_metadata_value_cannot_collapse_into_ready() -> None:
    # Two different hidden dict values must never produce a READY manifest (and cannot collide on a digest):
    # the serializer raises before a snapshot/digest exists, so both map fail-closed to REJECTED.
    base = _aggregate([_entry("1")])
    for hidden in ({"li": "scheduler"}, {"li": "safe"}):
        agg = replace(base, metadata=hidden)
        manifest = build_paper_session_realized_pnl_evidence_manifest(
            agg, expected_aggregate_digest="a" * 64, correlation_id="c"
        )
        assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
        assert manifest.ready is False


@pytest.mark.parametrize("bad_correlation", [{"x": "scheduler"}, ["live_order"], 5])
def test_non_string_internal_correlation_rejected(bad_correlation: object) -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, correlation_id=bad_correlation))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_correlation_id_invalid" in r for r in manifest.rejection_reasons)


@pytest.mark.parametrize("blank", ["", "   "])
def test_empty_internal_correlation_rejected(blank: str) -> None:
    agg = _aggregate([_entry("1")])
    tampered = _reseal(replace(agg, correlation_id=blank))
    manifest = _manifest(tampered, expected=tampered.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert any("aggregate_correlation_id_invalid" in r for r in manifest.rejection_reasons)


@pytest.mark.parametrize("codes", ["", {}, set(), ("scheduler",), ("live_order",), ("some_reason",), ("a", "b")])
def test_malformed_aggregate_reason_codes_cannot_ready(codes: object) -> None:
    # Lossy empty containers ("" / {} / set()) and ANY non-empty reason_codes now fail closed in the aggregate
    # serializer (a COMPUTED aggregate carries reason_codes == ()), so the manifest cannot capture a snapshot
    # and records REJECTED — never READY — whether or not a forbidden token is present.
    agg = replace(_aggregate([_entry("1")]), reason_codes=codes)
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest="a" * 64, correlation_id="c"
    )
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert manifest.ready is False
    assert any("aggregate_payload_invalid" in r for r in manifest.rejection_reasons)


def test_baseline_empty_internal_reason_codes_ready() -> None:
    agg = _aggregate([_entry("1")])
    assert agg.reason_codes == ()  # COMPUTED aggregate contract
    manifest = _manifest(agg)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY


# --------------------------------------------------------------------------------------------------
# Expected aggregate digest output binding (Codex re-audit P2)
# --------------------------------------------------------------------------------------------------


def test_expected_digest_recorded_on_ready_manifest() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg, expected=agg.aggregate_digest)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    assert manifest.expected_aggregate_digest == agg.aggregate_digest
    payload = paper_session_realized_pnl_evidence_manifest_to_dict(manifest)
    assert payload["expected_aggregate_digest"] == agg.aggregate_digest


def test_two_wrong_expected_digests_produce_distinct_manifests() -> None:
    # Before the fix, expected_aggregate_digest was not bound, so two different WRONG anchors produced
    # identical REJECTED manifests/digests. They must now differ in payload AND manifest digest.
    agg = _aggregate([_entry("1")])
    a = _manifest(agg, expected="a" * 64)
    b = _manifest(agg, expected="c" * 64)
    assert a.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    assert b.status is PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    pa = paper_session_realized_pnl_evidence_manifest_to_dict(a)
    pb = paper_session_realized_pnl_evidence_manifest_to_dict(b)
    assert pa["expected_aggregate_digest"] == "a" * 64
    assert pb["expected_aggregate_digest"] == "c" * 64
    assert pa != pb
    assert a.manifest_digest != b.manifest_digest


# --------------------------------------------------------------------------------------------------
# Source regression: the builder must never import/call the PUBLIC aggregate digest helper (single-snapshot)
# --------------------------------------------------------------------------------------------------


def test_source_does_not_import_or_call_public_aggregate_digest() -> None:
    # A future refactor must not reintroduce a direct import/alias OR call of the PUBLIC aggregate digest
    # helper: invoking it would re-serialize the aggregate a SECOND time, reopening the snapshot/digest
    # TOCTOU the builder closes by recomputing the digest from its single captured snapshot. (A docstring
    # mention is fine — this checks AST imports/calls, not raw text.)
    source = Path(paper_session_realized_pnl_evidence_manifest.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = "paper_session_realized_pnl_aggregate_digest"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert all(alias.name != helper for alias in node.names), f"must not import {helper}"
        elif isinstance(node, ast.Import):
            assert all(not alias.name.endswith(helper) for alias in node.names), f"must not import {helper}"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != helper, f"must not call {helper}"
            elif isinstance(func, ast.Attribute):
                assert func.attr != helper, f"must not call {helper}"


# --------------------------------------------------------------------------------------------------
# Fail-closed: call-level input
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, {"not": "an-aggregate"}, 5, "x"])
def test_wrong_typed_aggregate_raises(bad: object) -> None:
    with pytest.raises(PaperSessionRealizedPnlEvidenceManifestError, match="aggregate_malformed"):
        build_paper_session_realized_pnl_evidence_manifest(
            bad,  # type: ignore[arg-type]
            expected_aggregate_digest="0" * 64,
            correlation_id="c",
        )


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_correlation_id_raises(bad: str) -> None:
    agg = _aggregate([_entry("1")])
    with pytest.raises(PaperSessionRealizedPnlEvidenceManifestError, match="correlation_id_invalid"):
        _manifest(agg, correlation_id=bad)


def test_malformed_metadata_raises() -> None:
    agg = _aggregate([_entry("1")])
    with pytest.raises(PaperSessionRealizedPnlEvidenceManifestError, match="metadata_malformed"):
        _manifest(agg, metadata={"k": 5})  # type: ignore[dict-item]


@pytest.mark.parametrize(
    "correlation_id,metadata",
    [
        ("live_order", None),
        ("bist", None),
        ("scheduler", None),
        ("c", {"note": "place_order"}),
    ],
)
def test_scope_violation_in_inputs_raises(correlation_id: str, metadata: object) -> None:
    agg = _aggregate([_entry("1")])
    with pytest.raises(PaperSessionRealizedPnlEvidenceManifestError, match="scope_violation"):
        _manifest(agg, correlation_id=correlation_id, metadata=metadata)


def test_safe_market_data_terms_allowed() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg, correlation_id="c", metadata={"src": "order_book"})
    assert manifest.metadata == (("src", "order_book"),)
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY


# --------------------------------------------------------------------------------------------------
# Exact totals
# --------------------------------------------------------------------------------------------------


def test_market_symbol_and_totals_copied_exactly() -> None:
    agg = _aggregate([_entry("1")])
    manifest = _manifest(agg)
    assert manifest.market_symbol == agg.market_symbol
    assert manifest.realized_pnl_total == agg.realized_pnl_total
    assert manifest.closed_units_total == agg.closed_units_total


def test_high_scale_totals_preserved() -> None:
    avg = "0." + "0" * 99 + "1"
    e1 = _entry("1", bundles=(_bundle("h1", avg=avg, price="1"),))
    e2 = _entry("2", bundles=(_bundle("h2", avg=avg, price="1"),))
    agg = _aggregate([e1, e2])
    manifest = _manifest(agg)
    assert manifest.realized_pnl_total == "7." + "9" * 99 + "2"
    assert manifest.realized_pnl_total == agg.realized_pnl_total
    assert "e" not in manifest.realized_pnl_total.lower()


# --------------------------------------------------------------------------------------------------
# Immutability / no-leak / no-mutation
# --------------------------------------------------------------------------------------------------


def test_output_frozen() -> None:
    manifest = _manifest()
    with pytest.raises(FrozenInstanceError):
        manifest.realized_pnl_total = "1"  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    agg = _aggregate([_entry("1")])
    digest_before = agg.aggregate_digest
    payload_before = paper_session_realized_pnl_aggregate_digest(agg)
    totals_before = (agg.realized_pnl_total, agg.closed_units_total)
    chains_before = (agg.bridge_digests, agg.source_event_digests)
    _manifest(agg, metadata={"k": "v"})
    assert agg.aggregate_digest == digest_before
    assert paper_session_realized_pnl_aggregate_digest(agg) == payload_before
    assert (agg.realized_pnl_total, agg.closed_units_total) == totals_before
    assert (agg.bridge_digests, agg.source_event_digests) == chains_before


def test_dict_keys_and_safe_flags_no_forbidden_value_fields() -> None:
    payload = paper_session_realized_pnl_evidence_manifest_to_dict(_manifest())
    assert set(payload) == _EXPECTED_KEYS
    assert payload["paper_only"] is True
    assert payload["gross_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert _FORBIDDEN_VALUE_KEYS.isdisjoint(payload.keys())


def test_serializer_identity_values_are_exact_primitives() -> None:
    payload = paper_session_realized_pnl_evidence_manifest_to_dict(_manifest())
    for digest in payload["source_event_digests"]:
        assert type(digest) is str
    for digest in payload["fill_simulation_result_digests"]:
        assert type(digest) is str
    assert type(payload["realized_pnl_total"]) is str


def test_membership_boundary_not_overclaimed() -> None:
    payload = paper_session_realized_pnl_evidence_manifest_to_dict(_manifest())
    assert not any("membership" in key for key in payload)
    assert not any("episode_member" in key for key in payload)


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_session_realized_pnl_evidence_manifest.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported.append(node.module)
    forbidden_prefixes = (
        "crypto_core.venue",
        "crypto_core.execution",
        "crypto_core.runtime",
        "crypto_core.service",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.audit",
    )
    for module in imported:
        for prefix in forbidden_prefixes:
            assert module != prefix and not module.startswith(prefix + "."), f"forbidden import: {module}"
        if module.startswith("crypto_core"):
            assert module.startswith("crypto_core.validation"), f"unexpected crypto_core import: {module}"
