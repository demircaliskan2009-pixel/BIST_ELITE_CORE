"""Tests for the paper capacity gate — deterministic, paper-only admissibility verdict."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_capacity_gate
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    PaperCapacityGateError,
    PaperCapacityGatePolicy,
    PaperCapacityGateStatus,
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
    paper_capacity_gate_decision_digest,
    paper_capacity_gate_decision_to_dict,
    paper_capacity_gate_policy_digest,
)

_DRAFT_HEX = "a" * 64
_SAFETY_KEYS = frozenset(
    {
        "paper_only",
        "real_orders_enabled",
        "real_money_enabled",
        "capital_reserved",
        "execution_authorized",
        "order_created",
        "fill_created",
        "position_mutated",
    }
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _make_draft(**overrides: object) -> PaperAllocatorIntentDraft:
    """Build a digest-self-consistent ``PaperAllocatorIntentDraft`` directly (no journal chain needed)."""
    safety = {key: overrides.pop(key) for key in list(overrides) if key in _SAFETY_KEYS}
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
    fields.update(overrides)
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="", **safety)  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _make_policy(**overrides: object) -> PaperCapacityGatePolicy:
    base: dict[str, object] = {
        "policy_id": "policy-alpha",
        "sleeve_id": "sleeve-alpha",
        "max_notional": "1000",
        "max_units": "100",
        "max_open_intents": 5,
    }
    base.update(overrides)
    return build_paper_capacity_gate_policy(**base)  # type: ignore[arg-type]


def _evaluate(draft: PaperAllocatorIntentDraft, policy: PaperCapacityGatePolicy, **overrides: object):
    kwargs: dict[str, object] = {
        "requested_notional": "500",
        "requested_units": "50",
        "correlation_id": "corr-gate",
    }
    kwargs.update(overrides)
    return evaluate_paper_capacity_gate(draft, policy, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy path + boundaries
# --------------------------------------------------------------------------------------------------


def test_admitted_happy_path() -> None:
    decision = _evaluate(_make_draft(eligible_count=2), _make_policy())
    assert decision.status is PaperCapacityGateStatus.ADMITTED
    assert decision.reason_codes == ()
    assert decision.draft_digest == _make_draft(eligible_count=2).draft_digest
    assert decision.sleeve_id == "sleeve-alpha"
    assert decision.policy_id == "policy-alpha"
    assert decision.eligible_count == 2
    assert decision.requested_notional == "500"
    assert decision.requested_units == "50"
    assert _is_hex64(decision.decision_digest)
    assert paper_capacity_gate_decision_digest(decision) == decision.decision_digest


def test_open_intents_at_cap_admitted() -> None:
    decision = _evaluate(_make_draft(eligible_count=5), _make_policy(max_open_intents=5))
    assert decision.status is PaperCapacityGateStatus.ADMITTED


def test_notional_and_units_at_cap_admitted() -> None:
    decision = _evaluate(_make_draft(), _make_policy(), requested_notional="1000", requested_units="100")
    assert decision.status is PaperCapacityGateStatus.ADMITTED


# --------------------------------------------------------------------------------------------------
# REJECTED verdicts (untrustworthy / ineligible / over-capacity draft)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [PaperAllocatorIntentDraftStatus.BLOCKED, PaperAllocatorIntentDraftStatus.INSUFFICIENT_EVIDENCE],
)
def test_non_draft_ready_rejected(status: PaperAllocatorIntentDraftStatus) -> None:
    decision = _evaluate(_make_draft(status=status), _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_not_ready" in decision.reason_codes


def test_tampered_draft_digest_rejected() -> None:
    draft = replace(_make_draft(), draft_digest="b" * 64)
    decision = _evaluate(draft, _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert decision.reason_codes == ("draft_digest_mismatch",)


@pytest.mark.parametrize(
    "override",
    [
        {"schema_version": "paper-allocator-intent-draft.v0"},
        {"readiness_digest": "not-a-digest"},
        {"sleeve_id": ""},
        {"policy_id": ""},
        {"correlation_id": ""},
        {"eligible_count": -1},
        {"blocked_count": -1},
        {"insufficient_count": -1},
        {"eligible_count": 0, "status": PaperAllocatorIntentDraftStatus.DRAFT_READY},
        {"eligible_count": 1, "status": PaperAllocatorIntentDraftStatus.BLOCKED},
        {"metadata": ("place_order",)},
        {"metadata": (("note", "ok"), ("note", "duplicate"))},
        {"blockers": ["place_order"]},
        {"blockers": ("duplicate", "duplicate")},
        {"blockers": ("orphan-blocker",), "eligible_count": 1, "blocked_count": 0, "insufficient_count": 0},
    ],
)
def test_self_consistent_malformed_draft_rejected(override: dict[str, object]) -> None:
    draft = _make_draft(**override)
    assert paper_allocator_intent_draft_digest(draft) == draft.draft_digest
    decision = _evaluate(draft, _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_malformed" in decision.reason_codes


def test_forged_self_consistent_unsafe_flags_rejected() -> None:
    # Self-consistent: the digest is recomputed over the unsafe flag, so the digest check passes.
    draft = _make_draft(capital_reserved=True)
    assert paper_allocator_intent_draft_digest(draft) == draft.draft_digest
    decision = _evaluate(draft, _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_unsafe_flags" in decision.reason_codes


@pytest.mark.parametrize(
    "flag",
    [
        "real_orders_enabled",
        "real_money_enabled",
        "execution_authorized",
        "order_created",
        "fill_created",
        "position_mutated",
    ],
)
def test_each_unsafe_flag_rejected(flag: str) -> None:
    decision = _evaluate(_make_draft(**{flag: True}), _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_unsafe_flags" in decision.reason_codes


def test_paper_only_false_rejected() -> None:
    decision = _evaluate(_make_draft(paper_only=False), _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_unsafe_flags" in decision.reason_codes


def test_over_max_notional_rejected() -> None:
    decision = _evaluate(_make_draft(), _make_policy(max_notional="100"), requested_notional="100.0001")
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "notional_over_capacity" in decision.reason_codes


def test_over_max_units_rejected() -> None:
    decision = _evaluate(_make_draft(), _make_policy(max_units="10"), requested_units="11")
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "units_over_capacity" in decision.reason_codes


def test_over_max_open_intents_rejected() -> None:
    decision = _evaluate(_make_draft(eligible_count=6), _make_policy(max_open_intents=5))
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "open_intents_over_capacity" in decision.reason_codes


def test_identity_mismatch_rejected() -> None:
    decision = _evaluate(_make_draft(sleeve_id="sleeve-other"), _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "identity_mismatch" in decision.reason_codes


def test_policy_id_mismatch_rejected() -> None:
    decision = _evaluate(_make_draft(policy_id="policy-other"), _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "identity_mismatch" in decision.reason_codes


@pytest.mark.parametrize("token", ["bist100 alpha", "place_order soon", "order", "live_now", "private key"])
def test_draft_metadata_forbidden_token_rejected(token: str) -> None:
    draft = _make_draft(metadata=(("note", token),))
    decision = _evaluate(draft, _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_scope_violation" in decision.reason_codes


def test_draft_blocker_forbidden_token_rejected() -> None:
    draft = _make_draft(blockers=("place_order",), blocked_count=1)
    decision = _evaluate(draft, _make_policy())
    assert decision.status is PaperCapacityGateStatus.REJECTED
    assert "draft_scope_violation" in decision.reason_codes


def test_multiple_reasons_accumulate_sorted() -> None:
    decision = _evaluate(
        _make_draft(eligible_count=99),
        _make_policy(max_notional="10", max_units="10", max_open_intents=1),
        requested_notional="20",
        requested_units="20",
    )
    assert decision.status is PaperCapacityGateStatus.REJECTED
    expected = (
        "notional_over_capacity",
        "open_intents_over_capacity",
        "units_over_capacity",
    )
    assert decision.reason_codes == expected
    assert list(decision.reason_codes) == sorted(decision.reason_codes)


# --------------------------------------------------------------------------------------------------
# Typed errors (wrong-typed / malformed inputs / misconfigured policy)
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_draft_raises() -> None:
    with pytest.raises(PaperCapacityGateError, match="draft_malformed"):
        evaluate_paper_capacity_gate(
            {"not": "a draft"},  # type: ignore[arg-type]
            _make_policy(),
            requested_notional="1",
            requested_units="1",
            correlation_id="corr-gate",
        )


def test_wrong_typed_policy_raises() -> None:
    with pytest.raises(PaperCapacityGateError, match="policy_malformed"):
        evaluate_paper_capacity_gate(
            _make_draft(),
            {"not": "a policy"},  # type: ignore[arg-type]
            requested_notional="1",
            requested_units="1",
            correlation_id="corr-gate",
        )


@pytest.mark.parametrize("bad", ["1e5", "abc", "1.", ".5", "00", " 1", "NaN", "inf", "", "-5"])
def test_non_decimal_or_negative_demand_raises(bad: str) -> None:
    with pytest.raises(PaperCapacityGateError):
        _evaluate(_make_draft(), _make_policy(), requested_notional=bad)
    with pytest.raises(PaperCapacityGateError):
        _evaluate(_make_draft(), _make_policy(), requested_units=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_gate_correlation_id_invalid_raises(bad: str) -> None:
    with pytest.raises(PaperCapacityGateError, match="correlation_id_invalid"):
        _evaluate(_make_draft(), _make_policy(), correlation_id=bad)


def test_gate_metadata_forbidden_token_raises() -> None:
    with pytest.raises(PaperCapacityGateError, match="scope_violation"):
        _evaluate(_make_draft(), _make_policy(), metadata={"k": "place_order"})


def test_gate_metadata_malformed_raises() -> None:
    with pytest.raises(PaperCapacityGateError, match="metadata_malformed"):
        _evaluate(_make_draft(), _make_policy(), metadata={"k": 5})  # type: ignore[dict-item]


def test_policy_digest_mismatch_raises() -> None:
    tampered = replace(_make_policy(), policy_digest="c" * 64)
    with pytest.raises(PaperCapacityGateError, match="policy_digest_mismatch"):
        _evaluate(_make_draft(), tampered)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_notional": "0"},
        {"max_notional": "-1"},
        {"max_notional": "abc"},
        {"max_units": "0"},
        {"max_units": "1e3"},
        {"max_open_intents": 0},
        {"max_open_intents": -1},
        {"max_open_intents": True},
        {"max_open_intents": "5"},
        {"policy_id": ""},
        {"sleeve_id": ""},
        {"policy_id": "place_order"},
    ],
)
def test_policy_builder_rejects_bad_config(kwargs: dict[str, object]) -> None:
    with pytest.raises(PaperCapacityGateError):
        _make_policy(**kwargs)


def test_policy_builder_digest_reproves() -> None:
    policy = _make_policy()
    assert _is_hex64(policy.policy_digest)
    assert paper_capacity_gate_policy_digest(policy) == policy.policy_digest


# --------------------------------------------------------------------------------------------------
# Paper-safety / determinism / immutability / no-mutation / no-leak
# --------------------------------------------------------------------------------------------------


def test_decision_paper_only_flags_safe() -> None:
    decision = _evaluate(_make_draft(), _make_policy())
    assert decision.paper_only is True
    assert decision.real_orders_enabled is False
    assert decision.real_money_enabled is False
    assert decision.capital_reserved is False
    assert decision.execution_authorized is False
    assert decision.order_created is False
    assert decision.fill_created is False
    assert decision.position_mutated is False


def test_decision_digest_deterministic() -> None:
    draft, policy = _make_draft(), _make_policy()
    first = _evaluate(draft, policy)
    second = _evaluate(draft, policy)
    assert first == second
    assert first.decision_digest == second.decision_digest


def test_decision_to_dict_roundtrips_digest() -> None:
    decision = _evaluate(_make_draft(), _make_policy())
    payload = paper_capacity_gate_decision_to_dict(decision)
    assert payload["decision_digest"] == decision.decision_digest
    assert payload["status"] == "ADMITTED"


def test_decision_is_immutable() -> None:
    decision = _evaluate(_make_draft(), _make_policy())
    with pytest.raises(FrozenInstanceError):
        decision.status = PaperCapacityGateStatus.REJECTED  # type: ignore[misc]


def test_policy_is_immutable() -> None:
    policy = _make_policy()
    with pytest.raises(FrozenInstanceError):
        policy.max_notional = "1"  # type: ignore[misc]


def test_input_draft_not_mutated() -> None:
    draft = _make_draft()
    before = paper_allocator_intent_draft_digest(draft)
    _evaluate(draft, _make_policy())
    assert paper_allocator_intent_draft_digest(draft) == before
    assert draft.draft_digest == before


def test_no_forbidden_fields_in_exported_payload() -> None:
    payload = paper_capacity_gate_decision_to_dict(_evaluate(_make_draft(), _make_policy()))
    forbidden_tokens = (
        "fill_price",
        "filled_qty",
        "position_qty",
        "pnl",
        "venue",
        "order_id",
        "route",
        "realized",
        "unrealized",
        "credential",
        "secret",
        "api_key",
    )
    for key in payload:
        for token in forbidden_tokens:
            assert token not in key, f"forbidden field token {token!r} in {key!r}"
    assert payload["paper_only"] is True
    for flag in (
        "real_orders_enabled",
        "real_money_enabled",
        "capital_reserved",
        "execution_authorized",
        "order_created",
        "fill_created",
        "position_mutated",
    ):
        assert payload[flag] is False


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_capacity_gate.__file__).read_text(encoding="utf-8")
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
        "crypto_core.data.ingestion",
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
