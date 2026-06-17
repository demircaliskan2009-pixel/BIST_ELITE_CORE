"""Tests for the paper order-intent admission gate — deterministic, paper-only admission verdict."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_order_intent_admission
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    PaperCapacityGateDecision,
    PaperCapacityGateStatus,
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
    paper_capacity_gate_decision_digest,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentAdmissionError,
    PaperOrderIntentAdmissionStatus,
    PaperOrderIntentRequest,
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
    paper_order_intent_admission_decision_digest,
    paper_order_intent_admission_decision_to_dict,
    paper_order_intent_request_digest,
)

_DRAFT_HEX = "a" * 64

_EXPECTED_DECISION_KEYS = {
    "schema_version",
    "status",
    "request_digest",
    "capacity_decision_digest",
    "market_symbol",
    "side",
    "intent_type",
    "requested_notional",
    "requested_units",
    "limit_price",
    "reason_codes",
    "correlation_id",
    "metadata",
    "paper_only",
    "real_orders_enabled",
    "real_money_enabled",
    "capital_reserved",
    "order_routed",
    "venue_order_id_created",
    "execution_authorized",
    "fill_created",
    "pnl_computed",
    "position_mutated",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
    "decision_digest",
}

_SAFE_FALSE_FLAGS = (
    "real_orders_enabled",
    "real_money_enabled",
    "capital_reserved",
    "order_routed",
    "venue_order_id_created",
    "execution_authorized",
    "fill_created",
    "pnl_computed",
    "position_mutated",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _make_draft() -> PaperAllocatorIntentDraft:
    fields: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": _DRAFT_HEX,
        "promotion_readiness_journal_entry_digest": _DRAFT_HEX,
        "promotion_readiness_payload_digest": _DRAFT_HEX,
        "promotion_candidate_journal_entry_digest": _DRAFT_HEX,
        "decision_journal_entry_digest": _DRAFT_HEX,
        "decision_journal_payload_digest": _DRAFT_HEX,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _admitted_capacity(*, requested_notional: str = "500", requested_units: str = "50") -> PaperCapacityGateDecision:
    policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="1000",
        max_units="100",
        max_open_intents=5,
    )
    decision = evaluate_paper_capacity_gate(
        _make_draft(),
        policy,
        requested_notional=requested_notional,
        requested_units=requested_units,
        correlation_id="corr-capacity",
    )
    return decision


def _rejected_capacity() -> PaperCapacityGateDecision:
    policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="1000",
        max_units="100",
        max_open_intents=5,
    )
    decision = evaluate_paper_capacity_gate(
        _make_draft(),
        policy,
        requested_notional="5000",
        requested_units="50",
        correlation_id="corr-capacity",
    )
    return decision


def _make_request(capacity: PaperCapacityGateDecision, **overrides: object) -> PaperOrderIntentRequest:
    base: dict[str, object] = {
        "request_id": "req-1",
        "capacity_decision_digest": capacity.decision_digest,
        "market_symbol": "BTC-PERPETUAL",
        "side": PaperOrderSide.BUY,
        "intent_type": PaperOrderIntentType.LIMIT,
        "requested_notional": capacity.requested_notional,
        "requested_units": capacity.requested_units,
        "limit_price": "100",
        "correlation_id": "corr-req",
    }
    base.update(overrides)
    return build_paper_order_intent_request(**base)  # type: ignore[arg-type]


def _admit(capacity: PaperCapacityGateDecision, request: PaperOrderIntentRequest, **overrides: object):
    kwargs: dict[str, object] = {"correlation_id": "corr-admit"}
    kwargs.update(overrides)
    return evaluate_paper_order_intent_admission(capacity, request, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------------------------------


def test_admitted_happy_path_limit() -> None:
    capacity = _admitted_capacity()
    assert capacity.status is PaperCapacityGateStatus.ADMITTED
    request = _make_request(capacity)
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.ADMITTED
    assert decision.reason_codes == ()
    assert decision.request_digest == request.request_digest
    assert decision.capacity_decision_digest == capacity.decision_digest
    assert decision.side == "BUY"
    assert decision.intent_type == "LIMIT"
    assert decision.limit_price == "100"
    assert _is_hex64(decision.decision_digest)
    assert paper_order_intent_admission_decision_digest(decision) == decision.decision_digest


def test_admitted_happy_path_market() -> None:
    capacity = _admitted_capacity()
    request = _make_request(
        capacity, intent_type=PaperOrderIntentType.MARKET, limit_price=None, side=PaperOrderSide.SELL
    )
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.ADMITTED
    assert decision.intent_type == "MARKET"
    assert decision.side == "SELL"
    assert decision.limit_price is None


# --------------------------------------------------------------------------------------------------
# REJECTED verdicts
# --------------------------------------------------------------------------------------------------


def test_capacity_not_admitted_rejected() -> None:
    capacity = _rejected_capacity()
    assert capacity.status is PaperCapacityGateStatus.REJECTED
    request = _make_request(capacity)
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "capacity_not_admitted" in decision.reason_codes


def test_capacity_digest_mismatch_rejected() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    tampered = replace(capacity, decision_digest="d" * 64)
    decision = _admit(tampered, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert decision.reason_codes == ("capacity_decision_digest_mismatch",)


def test_forged_self_consistent_malformed_capacity_rejected() -> None:
    capacity = _admitted_capacity()
    forged = replace(capacity, schema_version="paper-capacity-gate-decision.vX")
    forged = replace(forged, decision_digest=paper_capacity_gate_decision_digest(forged))
    # Self-consistent: the digest recomputes over the bad schema version.
    assert paper_capacity_gate_decision_digest(forged) == forged.decision_digest
    request = _make_request(forged)
    decision = _admit(forged, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "capacity_decision_malformed" in decision.reason_codes


def test_demand_mismatch_rejected() -> None:
    capacity = _admitted_capacity(requested_notional="500", requested_units="50")
    request = _make_request(capacity, requested_notional="600")
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "demand_mismatch" in decision.reason_codes


def test_request_digest_mismatch_rejected() -> None:
    capacity = _admitted_capacity()
    request = replace(_make_request(capacity), request_digest="e" * 64)
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert decision.reason_codes == ("request_digest_mismatch",)


def test_capacity_binding_mismatch_rejected() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity, capacity_decision_digest="f" * 64)
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "capacity_binding_mismatch" in decision.reason_codes


def test_forged_request_unsafe_flag_rejected() -> None:
    capacity = _admitted_capacity()
    request = replace(_make_request(capacity), real_orders_enabled=True)
    request = replace(request, request_digest=paper_order_intent_request_digest(request))
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "request_unsafe_flags" in decision.reason_codes


def test_forged_request_bad_schema_rejected() -> None:
    capacity = _admitted_capacity()
    request = replace(_make_request(capacity), schema_version="paper-order-intent-request.vX")
    request = replace(request, request_digest=paper_order_intent_request_digest(request))
    decision = _admit(capacity, request)
    assert decision.status is PaperOrderIntentAdmissionStatus.REJECTED
    assert "request_malformed" in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# Request builder fail-closed (typed errors)
# --------------------------------------------------------------------------------------------------


def test_builder_empty_request_id_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="request_id_invalid"):
        _make_request(capacity, request_id="")


def test_builder_bad_capacity_digest_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="capacity_decision_digest_invalid"):
        _make_request(capacity, capacity_decision_digest="not-hex")


def test_builder_empty_market_symbol_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="market_symbol_invalid"):
        _make_request(capacity, market_symbol="")


def test_builder_invalid_side_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="side_invalid"):
        _make_request(capacity, side="BUY")


def test_builder_invalid_intent_type_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="intent_type_invalid"):
        _make_request(capacity, intent_type="LIMIT")


@pytest.mark.parametrize("bad", ["0", "-1", "1e5", "abc", "", "1.", "NaN"])
def test_builder_non_positive_notional_raises(bad: str) -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="requested_notional"):
        _make_request(capacity, requested_notional=bad)


@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_builder_non_positive_units_raises(bad: str) -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="requested_units"):
        _make_request(capacity, requested_units=bad)


def test_builder_limit_without_limit_price_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="limit_price"):
        _make_request(capacity, intent_type=PaperOrderIntentType.LIMIT, limit_price=None)


def test_builder_limit_non_positive_price_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="limit_price_not_positive"):
        _make_request(capacity, intent_type=PaperOrderIntentType.LIMIT, limit_price="0")


def test_builder_market_with_limit_price_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="market_intent_with_limit_price"):
        _make_request(capacity, intent_type=PaperOrderIntentType.MARKET, limit_price="100")


@pytest.mark.parametrize(
    "field,value",
    [
        ("market_symbol", "place_order-PERP"),
        ("market_symbol", "bist100"),
        ("request_id", "live_req"),
        ("correlation_id", "shadow-corr"),
    ],
)
def test_builder_scope_violation_raises(field: str, value: str) -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="request_scope_violation"):
        _make_request(capacity, **{field: value})


def test_builder_metadata_malformed_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="metadata_malformed"):
        _make_request(capacity, metadata={"k": 5})  # type: ignore[dict-item]


def test_builder_metadata_scope_violation_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="request_scope_violation"):
        _make_request(capacity, metadata={"note": "place_order"})


# --------------------------------------------------------------------------------------------------
# Gate-level typed errors
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_capacity_raises() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    with pytest.raises(PaperOrderIntentAdmissionError, match="capacity_decision_malformed"):
        evaluate_paper_order_intent_admission({"not": "capacity"}, request, correlation_id="c")  # type: ignore[arg-type]


def test_wrong_typed_request_raises() -> None:
    capacity = _admitted_capacity()
    with pytest.raises(PaperOrderIntentAdmissionError, match="request_malformed"):
        evaluate_paper_order_intent_admission(capacity, {"not": "request"}, correlation_id="c")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   "])
def test_gate_correlation_id_invalid_raises(bad: str) -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    with pytest.raises(PaperOrderIntentAdmissionError, match="correlation_id_invalid"):
        _admit(capacity, request, correlation_id=bad)


def test_gate_metadata_scope_violation_raises() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    with pytest.raises(PaperOrderIntentAdmissionError, match="scope_violation"):
        _admit(capacity, request, metadata={"k": "live_order"})


def test_gate_metadata_malformed_raises() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    with pytest.raises(PaperOrderIntentAdmissionError, match="metadata_malformed"):
        _admit(capacity, request, metadata={"k": 5})  # type: ignore[dict-item]


# --------------------------------------------------------------------------------------------------
# Paper-safety / determinism / immutability / no-mutation / no-leak
# --------------------------------------------------------------------------------------------------


def test_decision_paper_only_flags_safe() -> None:
    decision = _admit(_admitted_capacity(), _make_request(_admitted_capacity()))
    assert decision.paper_only is True
    assert decision.real_orders_enabled is False
    assert decision.real_money_enabled is False
    assert decision.capital_reserved is False
    assert decision.order_routed is False
    assert decision.venue_order_id_created is False
    assert decision.execution_authorized is False
    assert decision.fill_created is False
    assert decision.pnl_computed is False
    assert decision.position_mutated is False
    assert decision.live_api_called is False
    assert decision.scheduler_enabled is False
    assert decision.connector_invoked is False


def test_decision_digest_deterministic() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    first = _admit(capacity, request)
    second = _admit(capacity, request)
    assert first == second
    assert first.decision_digest == second.decision_digest


def test_decision_to_dict_roundtrips_digest_and_keys() -> None:
    decision = _admit(_admitted_capacity(), _make_request(_admitted_capacity()))
    payload = paper_order_intent_admission_decision_to_dict(decision)
    assert set(payload) == _EXPECTED_DECISION_KEYS
    assert payload["decision_digest"] == decision.decision_digest
    assert payload["paper_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False


def test_decision_is_immutable() -> None:
    decision = _admit(_admitted_capacity(), _make_request(_admitted_capacity()))
    with pytest.raises(FrozenInstanceError):
        decision.status = PaperOrderIntentAdmissionStatus.REJECTED  # type: ignore[misc]


def test_request_is_immutable() -> None:
    request = _make_request(_admitted_capacity())
    with pytest.raises(FrozenInstanceError):
        request.requested_notional = "1"  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    capacity = _admitted_capacity()
    request = _make_request(capacity)
    capacity_before = paper_capacity_gate_decision_digest(capacity)
    request_before = paper_order_intent_request_digest(request)
    _admit(capacity, request)
    assert paper_capacity_gate_decision_digest(capacity) == capacity_before
    assert paper_order_intent_request_digest(request) == request_before
    assert capacity.decision_digest == capacity_before
    assert request.request_digest == request_before


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_order_intent_admission.__file__).read_text(encoding="utf-8")
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
