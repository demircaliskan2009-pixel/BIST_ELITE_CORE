"""Tests for the paper evidence admission record — deterministic, paper-only, gross-only, fail-closed
admission gate over a READY ``PaperSessionRealizedPnlEvidenceManifest`` with an independent expected digest."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_evidence_admission_record
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
from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionError,
    PaperEvidenceAdmissionStatus,
    build_paper_evidence_admission_record,
    paper_evidence_admission_record_digest,
    paper_evidence_admission_record_to_dict,
)
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
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
    PaperSessionRealizedPnlEvidenceManifestStatus,
    build_paper_session_realized_pnl_evidence_manifest,
    paper_session_realized_pnl_evidence_manifest_digest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence

_HEX = "b" * 64


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _reseal_manifest(manifest):
    """Recompute the manifest self-digest after an in-place tamper (resealed, self-consistent)."""
    return replace(manifest, manifest_digest=paper_session_realized_pnl_evidence_manifest_digest(manifest))


# --------------------------------------------------------------------------------------------------
# Manifest fixtures (mirror test_paper_session_realized_pnl_evidence_manifest.py)
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


def _prov_for(idx: str, *, market_symbol: str = "BTC-PERPETUAL") -> PaperSessionSequenceProvenance:
    eps = [_episode(idx, market_symbol=market_symbol)]
    session = build_paper_session_sequence(eps, paper_session_id=f"sess-{idx}", correlation_id=f"corr-sess-{idx}")
    return PaperSessionSequenceProvenance(session_sequence=session, episodes=tuple(eps))


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


def _fill(side: str, filled: str, price: str, *, market_symbol: str = "BTC-PERPETUAL", idn: str = "1"):
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


def _bundle(event_id: str, *, prior_side: str = "LONG", price: str = "150", filled: str = "4"):
    if prior_side == "LONG":
        prior = _long(idn=event_id)
        fill = _fill("SELL", filled, price, idn=event_id)
    else:  # open from flat -> NO_REALIZED_PNL
        prior = _rflat(idn=event_id)
        fill = _fill("BUY", filled, price, idn=event_id)
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


def _entry(idx: str = "1", *, bundles=None):
    prov = _prov_for(idx)
    ents = tuple(bundles) if bundles is not None else (_bundle(f"e{idx}"),)
    bridge = build_paper_session_realized_pnl_bridge(
        prov, ents, bridge_id=f"bridge-{idx}", correlation_id="corr-bridge"
    )
    return PaperSessionRealizedPnlAggregateInput(bridge=bridge, session_input=prov, rollup_entries=ents)


def _aggregate(entries=None):
    ents = entries if entries is not None else [_entry("1")]
    return build_paper_session_realized_pnl_aggregate(ents, aggregate_id="agg-1", correlation_id="corr-agg")


def _ready_manifest(aggregate=None):
    agg = aggregate if aggregate is not None else _aggregate()
    return build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=agg.aggregate_digest, correlation_id="corr-manifest"
    )


def _rejected_manifest():
    agg = _aggregate()
    return build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest="a" * 64, correlation_id="corr-manifest"
    )


def _insufficient_manifest():
    agg = _aggregate([_entry("1", bundles=(_bundle("n1", prior_side="FLAT", filled="10", price="100"),))])
    return build_paper_session_realized_pnl_evidence_manifest(
        agg, expected_aggregate_digest=agg.aggregate_digest, correlation_id="corr-manifest"
    )


def _admission(manifest=None, *, expected=None, correlation_id: str = "corr-adm", metadata=None):
    m = manifest if manifest is not None else _ready_manifest()
    digest = expected if expected is not None else m.manifest_digest
    return build_paper_evidence_admission_record(
        m, expected_manifest_digest=digest, correlation_id=correlation_id, metadata=metadata
    )


_EXPECTED_KEYS = {
    "schema_version",
    "status",
    "admitted",
    "manifest_digest",
    "expected_manifest_digest",
    "manifest_status",
    "aggregate_id",
    "aggregate_digest",
    "market_symbol",
    "session_bridge_count",
    "event_count",
    "computed_event_count",
    "closed_units_total",
    "realized_pnl_total",
    "rejection_reasons",
    "correlation_id",
    "metadata",
    "admission_digest",
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
    "total_pnl",
    "equity",
    "capital",
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
# Happy path / ADMITTED
# --------------------------------------------------------------------------------------------------


def test_ready_manifest_admitted() -> None:
    manifest = _ready_manifest()
    assert manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.READY
    record = _admission(manifest)
    assert record.status is PaperEvidenceAdmissionStatus.ADMITTED
    assert record.admitted is True
    assert record.rejection_reasons == ()
    assert record.manifest_digest == manifest.manifest_digest
    assert record.expected_manifest_digest == manifest.manifest_digest
    assert record.manifest_status == "READY"
    assert record.aggregate_id == manifest.aggregate_id
    assert record.aggregate_digest == manifest.aggregate_digest
    assert record.market_symbol == "BTC-PERPETUAL"
    assert record.event_count == 1
    assert record.computed_event_count == 1
    assert record.realized_pnl_total == manifest.realized_pnl_total
    assert record.closed_units_total == manifest.closed_units_total
    assert record.gross_only is True
    assert _is_hex64(record.admission_digest)


def test_wrong_expected_digest_rejected() -> None:
    manifest = _ready_manifest()
    record = _admission(manifest, expected="a" * 64)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert record.admitted is False
    assert any("expected_manifest_digest_mismatch" in r for r in record.rejection_reasons)


@pytest.mark.parametrize("manifest_factory", [_rejected_manifest, _insufficient_manifest])
def test_non_ready_manifest_rejected(manifest_factory) -> None:
    manifest = manifest_factory()
    assert manifest.status is not PaperSessionRealizedPnlEvidenceManifestStatus.READY
    record = _admission(manifest, expected=manifest.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_not_ready" in r for r in record.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Fail-closed: call-level input
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, {"not": "a-manifest"}, "x", 5])
def test_wrong_typed_manifest_raises(bad: object) -> None:
    with pytest.raises(PaperEvidenceAdmissionError, match="manifest_malformed"):
        build_paper_evidence_admission_record(bad, expected_manifest_digest="0" * 64, correlation_id="c")  # type: ignore[arg-type]


def test_expected_digest_required_keyword() -> None:
    manifest = _ready_manifest()
    with pytest.raises(TypeError):
        build_paper_evidence_admission_record(manifest, correlation_id="c")  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", ["", "not-a-digest", "A" * 64, "b" * 63, "b" * 65, 5, None])
def test_malformed_expected_digest_raises(bad: object) -> None:
    manifest = _ready_manifest()
    with pytest.raises(PaperEvidenceAdmissionError, match="expected_manifest_digest_invalid"):
        build_paper_evidence_admission_record(manifest, expected_manifest_digest=bad, correlation_id="c")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_correlation_id_raises(bad: str) -> None:
    manifest = _ready_manifest()
    with pytest.raises(PaperEvidenceAdmissionError, match="correlation_id_invalid"):
        _admission(manifest, correlation_id=bad)


def test_malformed_metadata_raises() -> None:
    manifest = _ready_manifest()
    with pytest.raises(PaperEvidenceAdmissionError, match="metadata_malformed"):
        _admission(manifest, metadata={"k": 5})  # type: ignore[dict-item]


@pytest.mark.parametrize(
    "correlation_id,metadata",
    [("live_order", None), ("bist", None), ("scheduler", None), ("c", {"note": "place_order"})],
)
def test_scope_violation_in_inputs_raises(correlation_id: str, metadata: object) -> None:
    manifest = _ready_manifest()
    with pytest.raises(PaperEvidenceAdmissionError, match="scope_violation"):
        _admission(manifest, correlation_id=correlation_id, metadata=metadata)


def test_safe_market_data_terms_allowed() -> None:
    manifest = _ready_manifest()
    record = _admission(manifest, correlation_id="c", metadata={"src": "order_book"})
    assert record.metadata == (("src", "order_book"),)
    assert record.status is PaperEvidenceAdmissionStatus.ADMITTED


# --------------------------------------------------------------------------------------------------
# Fail-closed: manifest snapshot / serializer
# --------------------------------------------------------------------------------------------------


def test_manifest_serializer_error_rejected_not_admitted(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _ready_manifest()

    def boom(_m: object) -> dict:
        raise RuntimeError("serializer exploded")

    monkeypatch.setattr(paper_evidence_admission_record, "paper_session_realized_pnl_evidence_manifest_to_dict", boom)
    record = build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id="c"
    )
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_payload_invalid" in r for r in record.rejection_reasons)


def test_manifest_serializer_called_exactly_once_no_toctou(monkeypatch: pytest.MonkeyPatch) -> None:
    # A stateful serializer whose 2nd call diverges cannot create a divergence window: capture is once.
    manifest = _ready_manifest()
    from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
        paper_session_realized_pnl_evidence_manifest_to_dict as genuine_to_dict,
    )

    genuine = genuine_to_dict(manifest)
    divergent = dict(genuine)
    divergent["manifest_digest"] = "b" * 64
    divergent["aggregate_id"] = "TAMPERED"
    calls = {"n": 0}

    def fake_to_dict(_m: object) -> dict:
        calls["n"] += 1
        return genuine if calls["n"] == 1 else divergent

    monkeypatch.setattr(
        paper_evidence_admission_record, "paper_session_realized_pnl_evidence_manifest_to_dict", fake_to_dict
    )
    record = build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id="c"
    )
    assert calls["n"] == 1  # serialized exactly once -> no TOCTOU window
    assert record.status is PaperEvidenceAdmissionStatus.ADMITTED
    assert record.aggregate_id == manifest.aggregate_id  # bound from the single genuine snapshot


def test_forged_manifest_digest_rejected() -> None:
    manifest = _ready_manifest()
    forged = replace(manifest, manifest_digest="d" * 64)  # canonical hex64 but not the real digest
    record = _admission(forged, expected=manifest.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_digest_mismatch" in r for r in record.rejection_reasons)


def test_resealed_manifest_internal_scope_leak_rejected() -> None:
    # A resealed (self-consistent) manifest whose internal aggregate_id carries a forbidden token, paired
    # with its own expected digest, passes the triple-digest binding but must fail the scope re-proof.
    manifest = _ready_manifest()
    forged = _reseal_manifest(replace(manifest, aggregate_id="live_order"))
    record = _admission(forged, expected=forged.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_scope_violation" in r for r in record.rejection_reasons)


def test_resealed_manifest_malformed_internal_metadata_rejected() -> None:
    manifest = _ready_manifest()
    forged = _reseal_manifest(replace(manifest, metadata=(("nested", {"x": "scheduler"}),)))
    record = _admission(forged, expected=forged.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_metadata_malformed" in r for r in record.rejection_reasons)


def test_resealed_manifest_safety_flag_true_rejected() -> None:
    manifest = _ready_manifest()
    forged = _reseal_manifest(replace(manifest, order_routed=True))
    record = _admission(forged, expected=forged.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_safety_violation" in r for r in record.rejection_reasons)


def test_resealed_manifest_not_ready_flag_rejected() -> None:
    manifest = _ready_manifest()
    forged = _reseal_manifest(replace(manifest, ready=False))
    record = _admission(forged, expected=forged.manifest_digest)
    assert record.status is PaperEvidenceAdmissionStatus.REJECTED
    assert any("manifest_not_ready" in r for r in record.rejection_reasons)


# --------------------------------------------------------------------------------------------------
# Determinism / digest binding
# --------------------------------------------------------------------------------------------------


def test_admission_digest_deterministic_and_recomputes() -> None:
    manifest = _ready_manifest()
    a = _admission(manifest, correlation_id="corr-adm")
    b = _admission(manifest, correlation_id="corr-adm")
    assert a.admission_digest == b.admission_digest
    assert paper_evidence_admission_record_digest(a) == a.admission_digest
    assert paper_evidence_admission_record_to_dict(a)["admission_digest"] == a.admission_digest


def test_correlation_id_changes_admission_digest() -> None:
    manifest = _ready_manifest()
    a = _admission(manifest, correlation_id="corr-a")
    b = _admission(manifest, correlation_id="corr-b")
    assert a.admission_digest != b.admission_digest


def test_two_wrong_expected_digests_produce_distinct_records() -> None:
    manifest = _ready_manifest()
    a = _admission(manifest, expected="a" * 64)
    b = _admission(manifest, expected="c" * 64)
    assert a.status is PaperEvidenceAdmissionStatus.REJECTED
    assert b.status is PaperEvidenceAdmissionStatus.REJECTED
    pa = paper_evidence_admission_record_to_dict(a)
    pb = paper_evidence_admission_record_to_dict(b)
    assert pa["expected_manifest_digest"] == "a" * 64
    assert pb["expected_manifest_digest"] == "c" * 64
    assert pa != pb
    assert a.admission_digest != b.admission_digest


def test_metadata_canonicalized_deterministic() -> None:
    manifest = _ready_manifest()
    a = _admission(manifest, correlation_id="c", metadata={"z": "1", "a": "2"})
    b = _admission(manifest, correlation_id="c", metadata={"a": "2", "z": "1"})
    assert a.metadata == (("a", "2"), ("z", "1"))
    assert a.admission_digest == b.admission_digest


# --------------------------------------------------------------------------------------------------
# Immutability / no-leak / no-mutation
# --------------------------------------------------------------------------------------------------


def test_output_frozen() -> None:
    record = _admission()
    with pytest.raises(FrozenInstanceError):
        record.admitted = False  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    manifest = _ready_manifest()
    digest_before = manifest.manifest_digest
    payload_before = paper_session_realized_pnl_evidence_manifest_digest(manifest)
    _admission(manifest, metadata={"k": "v"})
    assert manifest.manifest_digest == digest_before
    assert paper_session_realized_pnl_evidence_manifest_digest(manifest) == payload_before


def test_dict_keys_and_safe_flags_no_forbidden_value_fields() -> None:
    payload = paper_evidence_admission_record_to_dict(_admission())
    assert set(payload) == _EXPECTED_KEYS
    assert payload["paper_only"] is True
    assert payload["gross_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert _FORBIDDEN_VALUE_KEYS.isdisjoint(payload.keys())


def test_serializer_identity_values_are_exact_primitives() -> None:
    payload = paper_evidence_admission_record_to_dict(_admission())
    assert type(payload["manifest_digest"]) is str
    assert type(payload["expected_manifest_digest"]) is str
    assert type(payload["realized_pnl_total"]) is str
    assert type(payload["closed_units_total"]) is str


# --------------------------------------------------------------------------------------------------
# Import / IO discipline
# --------------------------------------------------------------------------------------------------


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_evidence_admission_record.__file__).read_text(encoding="utf-8")
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


def test_module_has_no_io_or_nondeterminism_imports() -> None:
    source = Path(paper_evidence_admission_record.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    forbidden = {"os", "io", "socket", "random", "time", "datetime", "subprocess", "pathlib", "requests", "urllib"}
    for module in imported:
        root = module.split(".")[0]
        assert root not in forbidden, f"forbidden IO/nondeterminism import: {module}"


def test_membership_boundary_not_overclaimed() -> None:
    payload = paper_evidence_admission_record_to_dict(_admission())
    assert not any("membership" in key for key in payload)
    assert not any("episode_member" in key for key in payload)
