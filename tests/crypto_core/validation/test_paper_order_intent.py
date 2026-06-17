"""Tests for the inert paper order intent artifact — deterministic, paper-only, non-executable."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_order_intent
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_order_intent import (
    PaperOrderIntent,
    PaperOrderIntentError,
    PaperOrderIntentStatus,
    build_paper_order_intent,
    paper_order_intent_digest,
    paper_order_intent_to_dict,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentAdmissionDecision,
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
    paper_order_intent_admission_decision_digest,
)

_DRAFT_HEX = "a" * 64

_EXPECTED_INTENT_KEYS = {
    "schema_version",
    "status",
    "intent_id",
    "admission_decision_digest",
    "request_digest",
    "capacity_decision_digest",
    "market_symbol",
    "side",
    "intent_type",
    "requested_notional",
    "requested_units",
    "limit_price",
    "correlation_id",
    "metadata",
    "paper_only",
    "real_orders_enabled",
    "real_money_enabled",
    "capital_reserved",
    "order_routed",
    "venue_order_id_created",
    "exchange_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "execution_authorized",
    "fill_created",
    "pnl_computed",
    "position_mutated",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
    "intent_digest",
}

_SAFE_FALSE_FLAGS = (
    "real_orders_enabled",
    "real_money_enabled",
    "capital_reserved",
    "order_routed",
    "venue_order_id_created",
    "exchange_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
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


def _admitted_capacity(*, requested_notional: str = "500", requested_units: str = "50"):
    policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="1000",
        max_units="100",
        max_open_intents=5,
    )
    return evaluate_paper_capacity_gate(
        _make_draft(),
        policy,
        requested_notional=requested_notional,
        requested_units=requested_units,
        correlation_id="corr-capacity",
    )


def _make_request(capacity, **overrides: object):
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


def _admitted_admission(**req_overrides: object) -> PaperOrderIntentAdmissionDecision:
    capacity = _admitted_capacity()
    request = _make_request(capacity, **req_overrides)
    return evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")


def _rejected_admission() -> PaperOrderIntentAdmissionDecision:
    capacity = _admitted_capacity()
    request = _make_request(capacity, requested_notional="600")  # demand mismatch -> REJECTED
    return evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")


def _build(admission: PaperOrderIntentAdmissionDecision, **overrides: object) -> PaperOrderIntent:
    kwargs: dict[str, object] = {"intent_id": "intent-1", "correlation_id": "corr-intent"}
    kwargs.update(overrides)
    return build_paper_order_intent(admission, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy path + echo
# --------------------------------------------------------------------------------------------------


def test_happy_path_limit_creates_inert_intent() -> None:
    admission = _admitted_admission()
    intent = _build(admission)
    assert intent.status is PaperOrderIntentStatus.CREATED
    assert intent.intent_id == "intent-1"
    assert intent.admission_decision_digest == admission.decision_digest
    assert intent.request_digest == admission.request_digest
    assert intent.capacity_decision_digest == admission.capacity_decision_digest
    assert intent.market_symbol == admission.market_symbol == "BTC-PERPETUAL"
    assert intent.side == "BUY"
    assert intent.intent_type == "LIMIT"
    assert intent.limit_price == admission.limit_price == "100"
    assert intent.requested_notional == admission.requested_notional
    assert intent.requested_units == admission.requested_units
    assert _is_hex64(intent.intent_digest)
    assert paper_order_intent_digest(intent) == intent.intent_digest


def test_happy_path_market_limit_price_none() -> None:
    admission = _admitted_admission(intent_type=PaperOrderIntentType.MARKET, limit_price=None, side=PaperOrderSide.SELL)
    intent = _build(admission)
    assert intent.status is PaperOrderIntentStatus.CREATED
    assert intent.intent_type == "MARKET"
    assert intent.side == "SELL"
    assert intent.limit_price is None


# --------------------------------------------------------------------------------------------------
# Fail-closed (typed errors)
# --------------------------------------------------------------------------------------------------


def test_non_admitted_admission_rejected() -> None:
    rejected = _rejected_admission()
    with pytest.raises(PaperOrderIntentError, match="admission_decision_not_admitted"):
        _build(rejected)


def test_admission_digest_mismatch_rejected() -> None:
    admission = replace(_admitted_admission(), decision_digest="d" * 64)
    with pytest.raises(PaperOrderIntentError, match="admission_decision_digest_mismatch"):
        _build(admission)


def test_forged_self_consistent_bad_schema_rejected() -> None:
    admission = replace(_admitted_admission(), schema_version="paper-order-intent-admission-decision.vX")
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    assert paper_order_intent_admission_decision_digest(admission) == admission.decision_digest
    with pytest.raises(PaperOrderIntentError, match="admission_decision_schema_unexpected"):
        _build(admission)


def test_forged_self_consistent_admitted_with_reason_codes_rejected() -> None:
    admission = replace(_admitted_admission(), reason_codes=("spurious",))
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_malformed"):
        _build(admission)


@pytest.mark.parametrize(
    "flag",
    [
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
    ],
)
def test_forged_self_consistent_unsafe_flag_rejected(flag: str) -> None:
    admission = replace(_admitted_admission(), **{flag: True})
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_unsafe_flags"):
        _build(admission)


def test_forged_paper_only_false_rejected() -> None:
    admission = replace(_admitted_admission(), paper_only=False)
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_unsafe_flags"):
        _build(admission)


@pytest.mark.parametrize(
    "override",
    [
        {"correlation_id": "live_order"},
        {"market_symbol": "place_order-PERP"},
        {"market_symbol": "bist100"},
        {"metadata": (("note", "place_order"),)},
    ],
)
def test_forged_self_consistent_forbidden_token_rejected(override: dict[str, object]) -> None:
    admission = replace(_admitted_admission(), **override)
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_scope_violation"):
        _build(admission)


def test_forged_malformed_admission_metadata_shape_rejected() -> None:
    admission = replace(_admitted_admission(), metadata=("place_order",))
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_malformed"):
        _build(admission)


@pytest.mark.parametrize("field", ["request_digest", "capacity_decision_digest"])
def test_forged_admission_bad_echoed_digest_rejected(field: str) -> None:
    admission = replace(_admitted_admission(), **{field: "short"})
    admission = replace(admission, decision_digest=paper_order_intent_admission_decision_digest(admission))
    with pytest.raises(PaperOrderIntentError, match="admission_decision_malformed"):
        _build(admission)


def test_wrong_typed_admission_rejected() -> None:
    with pytest.raises(PaperOrderIntentError, match="admission_decision_malformed"):
        build_paper_order_intent({"not": "admission"}, intent_id="i", correlation_id="c")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_intent_id_rejected(bad: str) -> None:
    with pytest.raises(PaperOrderIntentError, match="intent_id_invalid"):
        _build(_admitted_admission(), intent_id=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_correlation_id_rejected(bad: str) -> None:
    with pytest.raises(PaperOrderIntentError, match="correlation_id_invalid"):
        _build(_admitted_admission(), correlation_id=bad)


@pytest.mark.parametrize(
    "override",
    [
        {"intent_id": "place_order"},
        {"correlation_id": "shadow-run"},
    ],
)
def test_build_scope_violation_rejected(override: dict[str, object]) -> None:
    with pytest.raises(PaperOrderIntentError, match="scope_violation"):
        _build(_admitted_admission(), **override)


def test_build_metadata_malformed_rejected() -> None:
    with pytest.raises(PaperOrderIntentError, match="metadata_malformed"):
        _build(_admitted_admission(), metadata={"k": 5})  # type: ignore[dict-item]


def test_build_metadata_scope_violation_rejected() -> None:
    with pytest.raises(PaperOrderIntentError, match="scope_violation"):
        _build(_admitted_admission(), metadata={"note": "place_order"})


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-mutation / no-leak
# --------------------------------------------------------------------------------------------------


def test_intent_paper_only_flags_safe() -> None:
    intent = _build(_admitted_admission())
    assert intent.paper_only is True
    for flag in _SAFE_FALSE_FLAGS:
        assert getattr(intent, flag) is False


def test_intent_digest_deterministic() -> None:
    admission = _admitted_admission()
    first = _build(admission)
    second = _build(admission)
    assert first == second
    assert first.intent_digest == second.intent_digest


def test_to_dict_roundtrips_digest_and_keys() -> None:
    intent = _build(_admitted_admission())
    payload = paper_order_intent_to_dict(intent)
    assert set(payload) == _EXPECTED_INTENT_KEYS
    assert payload["intent_digest"] == intent.intent_digest
    assert payload["status"] == "CREATED"
    assert payload["paper_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False


def test_no_forbidden_value_fields_in_payload() -> None:
    payload = paper_order_intent_to_dict(_build(_admitted_admission()))
    # Any key referencing an order/venue/exchange/route/execution/fill/pnl/position/capital concept must
    # be a negative-attestation boolean set to False — never a concrete id/value/number field.
    concept_tokens = (
        "order",
        "venue",
        "exchange",
        "client",
        "route",
        "execution",
        "fill",
        "pnl",
        "position",
        "capital",
        "live",
        "scheduler",
        "connector",
    )
    for key, value in payload.items():
        if any(token in key for token in concept_tokens):
            assert value is False, f"{key!r} must be a False negative attestation, got {value!r}"


def test_intent_is_immutable() -> None:
    intent = _build(_admitted_admission())
    with pytest.raises(FrozenInstanceError):
        intent.market_symbol = "X"  # type: ignore[misc]


def test_input_admission_not_mutated() -> None:
    admission = _admitted_admission()
    before = paper_order_intent_admission_decision_digest(admission)
    _build(admission)
    assert paper_order_intent_admission_decision_digest(admission) == before
    assert admission.decision_digest == before


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_order_intent.__file__).read_text(encoding="utf-8")
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
