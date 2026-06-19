"""Tests for the deterministic, paper-only paper sleeve risk-budget decision seam."""

from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal, EvidenceJournalEntry
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
    paper_sleeve_intent_record_digest,
    paper_sleeve_state_digest,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetDecisionError,
    PaperSleeveRiskBudgetRecordStatus,
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
    paper_sleeve_risk_budget_policy_digest,
    paper_sleeve_risk_budget_policy_to_dict,
    paper_sleeve_risk_budget_record_decision_digest,
    paper_sleeve_risk_budget_record_decision_to_dict,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict

_VALID_DIGEST = "f" * 64
_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "paper_sleeve_risk_budget_decision.py"
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _tick(**overrides: object):
    base: dict[str, object] = {
        "tick_id": "tick-1",
        "action": "BUY",
        "intent_type": "LIMIT",
        "instrument_id": "BTC-USD",
        "quantity": "2",
        "strategy_id": "momentum-1",
        "run_plan_id": "run-1",
        "upstream_report_digest": _VALID_DIGEST,
        "correlation_id": "corr-1",
        "limit_price": "100",
    }
    base.update(overrides)
    return build_paper_trade_tick(**base)


def _journal_entry(tick) -> EvidenceJournalEntry:
    journal = EvidenceJournal()
    return journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id="corr:journal"
    )


def _state(sleeve_id: str = "sleeve-1"):
    return build_initial_paper_sleeve_state(sleeve_id=sleeve_id, correlation_id="corr:sleeve")


def _apply(state, tick, *, correlation_id: str, bind: bool = True):
    entry = _journal_entry(tick) if bind else None
    return apply_paper_trade_tick_to_sleeve_state(
        state, tick, correlation_id=correlation_id, journal_entry=entry
    ).to_state


def _policy(**overrides: object):
    base: dict[str, object] = {
        "policy_id": "policy-1",
        "sleeve_id": "sleeve-1",
        "total_budget": "1000",
        "per_intent_budget_cap": "500",
    }
    base.update(overrides)
    return build_paper_sleeve_risk_budget_policy(**base)


def _eligible_single_state():
    return _apply(_state(), _tick(), correlation_id="corr:apply", bind=True)


def _two_eligible_state():
    state = _state()
    state = _apply(
        state, _tick(tick_id="t1", instrument_id="BTC-USD", quantity="2", limit_price="100"), correlation_id="c1"
    )
    state = _apply(
        state, _tick(tick_id="t2", instrument_id="ETH-USD", quantity="1", limit_price="50"), correlation_id="c2"
    )
    return state


def _reseal_record(record):
    return replace(record, record_digest=paper_sleeve_intent_record_digest(record))


def _reseal_state(state):
    return replace(state, state_digest=paper_sleeve_state_digest(state))


# 1. policy builds with deterministic digest.
def test_policy_builds_deterministic_digest() -> None:
    first = _policy()
    second = _policy()
    assert _is_hex64(first.policy_digest)
    assert first.policy_digest == second.policy_digest
    assert paper_sleeve_risk_budget_policy_digest(first) == first.policy_digest
    assert first.paper_only is True
    assert first.real_orders_enabled is False
    assert first.real_money_enabled is False
    assert first.require_journal_bound is True


# 2. decision on empty state is deterministic with zero reserved budget.
def test_empty_state_zero_reserved_deterministic() -> None:
    state = _state()
    policy = _policy()
    first = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:d")
    second = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:d")
    assert isinstance(first, PaperSleeveRiskBudgetDecision)
    assert first.record_decisions == ()
    assert first.total_reserved_budget == "0"
    assert first.total_requested_budget == "0"
    assert first.eligible_count == 0
    assert first.decision_digest == second.decision_digest
    assert paper_sleeve_risk_budget_decision_digest(first) == first.decision_digest


# 3. two journal-bound RECORDED records within caps become ELIGIBLE and reserve deterministic budget.
def test_two_bound_records_eligible_reserve_budget() -> None:
    decision = evaluate_paper_sleeve_risk_budget(_two_eligible_state(), _policy(), correlation_id="corr:d")
    statuses = [rd.status for rd in decision.record_decisions]
    assert statuses == [PaperSleeveRiskBudgetRecordStatus.ELIGIBLE, PaperSleeveRiskBudgetRecordStatus.ELIGIBLE]
    assert decision.record_decisions[0].reserved_budget == "200"
    assert decision.record_decisions[1].reserved_budget == "50"
    assert decision.total_reserved_budget == "250"
    assert decision.total_requested_budget == "250"
    assert decision.eligible_count == 2
    assert decision.blocked_count == 0
    assert Decimal(decision.total_reserved_budget) <= Decimal(decision.total_budget)


# 4. unbound RECORDED record blocks with zero reserved budget.
def test_unbound_recorded_blocks() -> None:
    state = _apply(_state(), _tick(), correlation_id="corr:apply", bind=False)
    decision = evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    rd = decision.record_decisions[0]
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "record_not_journal_bound" in rd.blockers
    assert rd.reserved_budget == "0"
    assert decision.total_reserved_budget == "0"


# 5. REJECTED record blocks with zero reserved budget.
def test_rejected_record_blocks() -> None:
    tick = _tick(quantity="0")  # quantity_not_positive -> REJECTED
    state = _apply(_state(), tick, correlation_id="corr:apply", bind=True)
    decision = evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    rd = decision.record_decisions[0]
    assert rd.intent_status == "REJECTED"
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "record_rejected" in rd.blockers
    assert rd.reserved_budget == "0"


# 6. INSUFFICIENT_EVIDENCE record classifies insufficient with zero reserved budget.
def test_insufficient_evidence_record_blocks() -> None:
    tick = _tick(upstream_report_digest="")  # INSUFFICIENT_EVIDENCE
    state = _apply(_state(), tick, correlation_id="corr:apply", bind=True)
    decision = evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    rd = decision.record_decisions[0]
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE
    assert rd.reserved_budget == "0"
    assert decision.insufficient_count == 1


# 7. state digest tamper rejects before decision.
def test_state_digest_tamper_rejected() -> None:
    state = replace(_eligible_single_state(), state_digest="0" * 64)
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    assert "state_digest_mismatch" in str(exc.value)


# 8. record digest tamper rejects before decision.
def test_record_digest_tamper_rejected() -> None:
    state = _eligible_single_state()
    tampered = replace(state.records[0], action="SELL")  # not resealed -> record digest stale
    forged = replace(state, records=(tampered,))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "record_digest_mismatch" in str(exc.value)


# 9. duplicate paper_trade_tick_digest rejects.
def test_duplicate_tick_digest_rejected() -> None:
    state = _eligible_single_state()
    r0 = state.records[0]
    r1 = _reseal_record(replace(r0, sequence=1))  # distinct record digest, same tick digest
    forged = _reseal_state(replace(state, records=(r0, r1), record_count=2, recorded_count=2))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "duplicate_tick_digest" in str(exc.value)


# 10. duplicate record_digest rejects.
def test_duplicate_record_digest_rejected() -> None:
    state = _eligible_single_state()
    r0 = state.records[0]
    forged = _reseal_state(replace(state, records=(r0, r0), record_count=2, recorded_count=2))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "duplicate_record_digest" in str(exc.value)


# 11. sequence gap / duplicate sequence rejects.
def test_sequence_gap_rejected() -> None:
    state = _two_eligible_state()
    r0, r1 = state.records
    r1_gap = _reseal_record(replace(r1, sequence=2))  # gap: 0, 2
    forged = _reseal_state(replace(state, records=(r0, r1_gap)))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "sequence_invalid" in str(exc.value)


# 12. wrong record.sleeve_id rejects.
def test_record_sleeve_id_mismatch_rejected() -> None:
    state = _eligible_single_state()
    bad = _reseal_record(replace(state.records[0], sleeve_id="sleeve-2"))
    forged = _reseal_state(replace(state, records=(bad,)))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "record_sleeve_id_mismatch" in str(exc.value)


# 13. unsafe state paper-safety triple rejects even if resealed.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "state_not_paper_only"),
        ({"real_orders_enabled": True}, "state_real_orders_enabled"),
        ({"real_money_enabled": True}, "state_real_money_enabled"),
    ],
)
def test_unsafe_state_rejected(override: dict[str, bool], reason: str) -> None:
    state = _reseal_state(replace(_state(), **override))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    assert reason in str(exc.value)


# 14. unsafe record paper-safety triple rejects even if state resealed.
def test_unsafe_record_rejected() -> None:
    state = _eligible_single_state()
    bad = _reseal_record(replace(state.records[0], real_orders_enabled=True))
    forged = _reseal_state(replace(state, records=(bad,)))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(forged, _policy(), correlation_id="corr:d")
    assert "state_record_not_paper_safe" in str(exc.value)


# 15. policy sleeve_id mismatch rejects.
def test_policy_sleeve_id_mismatch_rejected() -> None:
    policy = _policy(sleeve_id="sleeve-2")
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(_state("sleeve-1"), policy, correlation_id="corr:d")
    assert "policy_sleeve_id_mismatch" in str(exc.value)


# 16. policy paper-safety violation rejects.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "policy_not_paper_only"),
        ({"real_orders_enabled": True}, "policy_real_orders_enabled"),
        ({"real_money_enabled": True}, "policy_real_money_enabled"),
    ],
)
def test_unsafe_policy_rejected(override: dict[str, bool], reason: str) -> None:
    policy = replace(_policy(), **override)
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(_state(), policy, correlation_id="corr:d")
    assert reason in str(exc.value)


# 17. total cap exceeded blocks later record; total_reserved_budget never exceeds total_budget.
def test_total_cap_exceeded_blocks_later() -> None:
    decision = evaluate_paper_sleeve_risk_budget(
        _two_eligible_state(), _policy(total_budget="220", per_intent_budget_cap="500"), correlation_id="corr:d"
    )
    first, second = decision.record_decisions
    assert first.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE  # 200 reserved
    assert second.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED  # 200 + 50 > 220
    assert "total_budget_exceeded" in second.blockers
    assert second.reserved_budget == "0"
    assert decision.total_reserved_budget == "200"
    assert Decimal(decision.total_reserved_budget) <= Decimal(decision.total_budget)


# 18. per-intent cap exceeded blocks that record.
def test_per_intent_cap_exceeded_blocks() -> None:
    decision = evaluate_paper_sleeve_risk_budget(
        _eligible_single_state(), _policy(total_budget="1000", per_intent_budget_cap="150"), correlation_id="corr:d"
    )
    rd = decision.record_decisions[0]  # notional 200 > 150
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "per_intent_budget_cap_exceeded" in rd.blockers
    assert rd.requested_budget == "200"
    assert rd.reserved_budget == "0"


# 19. per-instrument cap exceeded blocks later same-instrument record.
def test_per_instrument_cap_exceeded_blocks() -> None:
    state = _state()
    state = _apply(
        state, _tick(tick_id="t1", instrument_id="BTC-USD", quantity="2", limit_price="100"), correlation_id="c1"
    )
    state = _apply(
        state, _tick(tick_id="t2", instrument_id="BTC-USD", quantity="1", limit_price="100"), correlation_id="c2"
    )
    decision = evaluate_paper_sleeve_risk_budget(
        state,
        _policy(total_budget="1000", per_intent_budget_cap="500", per_instrument_budget_cap="250"),
        correlation_id="corr:d",
    )
    first, second = decision.record_decisions
    assert first.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE  # BTC 200
    assert second.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED  # BTC 200 + 100 > 250
    assert "per_instrument_budget_cap_exceeded" in second.blockers
    assert decision.total_reserved_budget == "200"


# 20. malformed decimal strings reject.
@pytest.mark.parametrize("bad", ["abc", "12.3.4", "1.", ".5", "00", ""])
def test_malformed_decimal_policy_rejected(bad: str) -> None:
    with pytest.raises(PaperSleeveRiskBudgetDecisionError):
        _policy(total_budget=bad)


# 21. float/NaN/inf/scientific notation/negative budget reject.
@pytest.mark.parametrize("bad", [1000, 1000.5, True, "NaN", "inf", "1e5", "-5", " 5", "1_000"])
def test_non_strict_decimal_policy_rejected(bad: object) -> None:
    with pytest.raises(PaperSleeveRiskBudgetDecisionError):
        build_paper_sleeve_risk_budget_policy(
            policy_id="policy-1", sleeve_id="sleeve-1", total_budget=bad, per_intent_budget_cap="500"
        )


# 22. missing limit price on RECORDED record blocks with missing_price.
def test_missing_price_recorded_blocks() -> None:
    # HOLD tick is ACCEPTED (-> RECORDED) with zero quantity and no limit price.
    tick = _tick(action="HOLD", intent_type="LIMIT", quantity="0", limit_price=None)
    state = _apply(_state(), tick, correlation_id="corr:apply", bind=True)
    decision = evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    rd = decision.record_decisions[0]
    assert rd.intent_status == "RECORDED"
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "missing_price" in rd.blockers
    assert rd.reserved_budget == "0"


# 23. forbidden BIST/live/private/order-routing/scheduler/connector/shadow tokens reject.
@pytest.mark.parametrize("token", ["live_order", "order_router", "scheduler", "connector_ready", "shadow", "bist"])
def test_forbidden_tokens_rejected(token: str) -> None:
    with pytest.raises(PaperSleeveRiskBudgetDecisionError):
        _policy(metadata={"note": token})
    with pytest.raises(PaperSleeveRiskBudgetDecisionError):
        evaluate_paper_sleeve_risk_budget(_state(), _policy(), correlation_id="corr:d", metadata={"note": token})


# 24. safe market-data terms remain allowed.
def test_safe_market_data_terms_allowed() -> None:
    policy = _policy(metadata={"src": "order_book"})
    decision = evaluate_paper_sleeve_risk_budget(
        _eligible_single_state(), policy, correlation_id="corr:d", metadata={"feed": "order_flow"}
    )
    assert decision.metadata == (("feed", "order_flow"),)
    assert decision.record_decisions[0].status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE


# 25. serializer/digest stability for policy, record decision, and decision.
def test_serializer_digest_stability() -> None:
    decision = evaluate_paper_sleeve_risk_budget(_two_eligible_state(), _policy(), correlation_id="corr:d")
    policy = _policy()
    assert paper_sleeve_risk_budget_policy_to_dict(policy)["policy_digest"] == policy.policy_digest
    rd = decision.record_decisions[0]
    assert paper_sleeve_risk_budget_record_decision_to_dict(rd)["record_decision_digest"] == rd.record_decision_digest
    assert paper_sleeve_risk_budget_record_decision_digest(rd) == rd.record_decision_digest
    assert paper_sleeve_risk_budget_decision_to_dict(decision)["decision_digest"] == decision.decision_digest
    assert paper_sleeve_risk_budget_decision_digest(decision) == decision.decision_digest


# 26. material-field mutation changes the decision/policy/record digest.
def test_material_mutation_changes_digest() -> None:
    decision = evaluate_paper_sleeve_risk_budget(_two_eligible_state(), _policy(), correlation_id="corr:d")
    tampered = replace(decision, total_reserved_budget="999")
    assert paper_sleeve_risk_budget_decision_digest(tampered) != tampered.decision_digest
    policy = _policy()
    tampered_policy = replace(policy, total_budget="2000")
    assert paper_sleeve_risk_budget_policy_digest(tampered_policy) != tampered_policy.policy_digest
    rd = decision.record_decisions[0]
    tampered_rd = replace(rd, reserved_budget="999")
    assert paper_sleeve_risk_budget_record_decision_digest(tampered_rd) != tampered_rd.record_decision_digest


# 27. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    crypto_submodules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
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
        "random",
        "secrets",
        "uuid",
        "threading",
        "asyncio",
        "multiprocessing",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "sqlite3",
    }
    assert roots.isdisjoint(impure)
    assert crypto_submodules.isdisjoint({"service", "connector", "runtime", "venue", "execution", "orchestrator"})


# 28. no live/order/scheduler/connector/BIST implementation surface (public API names).
def test_no_forbidden_surface() -> None:
    import crypto_core.validation.paper_sleeve_risk_budget_decision as mod

    banned = (
        "execute",
        "route",
        "router",
        "send",
        "submit",
        "schedule",
        "connector",
        "place_order",
        "live",
        "fill",
        "pnl",
        "venue",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# 29. no fill/PnL/execution/position/venue/order-id fields in public serializers.
def test_no_execution_fields() -> None:
    decision = evaluate_paper_sleeve_risk_budget(_eligible_single_state(), _policy(), correlation_id="corr:d")
    policy_keys = set(paper_sleeve_risk_budget_policy_to_dict(_policy()).keys())
    record_keys = set(paper_sleeve_risk_budget_record_decision_to_dict(decision.record_decisions[0]).keys())
    decision_keys = set(paper_sleeve_risk_budget_decision_to_dict(decision).keys())
    banned = {
        "fill",
        "filled",
        "fills",
        "fill_price",
        "avg_fill_price",
        "filled_quantity",
        "executed",
        "execution",
        "pnl",
        "realized_pnl",
        "position",
        "order_id",
        "venue",
        "venue_order_id",
    }
    assert policy_keys.isdisjoint(banned)
    assert record_keys.isdisjoint(banned)
    assert decision_keys.isdisjoint(banned)


# 30. original state remains unchanged after evaluation.
def test_original_state_unchanged() -> None:
    state = _two_eligible_state()
    before_digest = state.state_digest
    before_records = state.records
    evaluate_paper_sleeve_risk_budget(state, _policy(), correlation_id="corr:d")
    assert state.state_digest == before_digest
    assert state.records is before_records
    assert state.record_count == 2


# 31 (review P1). a high-precision notional whose exact product exceeds the cap must not round down to
# the cap and slip through ELIGIBLE; the exact product is preserved and the record is BLOCKED.
def test_high_precision_product_not_rounded_under_cap() -> None:
    quantity = "10000000000000000000000000004"  # 29 significant digits (> default 28-digit context)
    state = _apply(_state(), _tick(quantity=quantity, limit_price="1"), correlation_id="corr:apply", bind=True)
    decision = evaluate_paper_sleeve_risk_budget(
        state,
        _policy(total_budget="100000000000000000000000000000", per_intent_budget_cap="10000000000000000000000000000"),
        correlation_id="corr:d",
    )
    rd = decision.record_decisions[0]
    assert rd.requested_budget == quantity  # exact product preserved (no context rounding)
    assert rd.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "per_intent_budget_cap_exceeded" in rd.blockers
    assert rd.reserved_budget == "0"
    assert decision.total_reserved_budget == "0"


# 31b (review P1 span-aware). A tiny high-scale second reservation that, summed exactly with the first,
# exceeds the total budget must NOT round back inside the cap and slip through ELIGIBLE. ``1e-100`` is
# written in the contract-valid fixed form ("0." + 99 zeros + "1"); the strict grammar forbids the
# "1E-100" scientific form. Coefficient-only precision rounds ``1 + 1e-100`` back to ``1`` and would mark
# the second record ELIGIBLE; span-aware precision keeps the sum exact and blocks it.
def test_high_scale_total_budget_cap_not_bypassed() -> None:
    tiny = "0." + "0" * 99 + "1"  # 1e-100, exact fixed-point form
    state = _state()
    state = _apply(state, _tick(tick_id="t1", quantity="1", limit_price="1"), correlation_id="c1")
    state = _apply(state, _tick(tick_id="t2", quantity=tiny, limit_price="1"), correlation_id="c2")
    decision = evaluate_paper_sleeve_risk_budget(
        state, _policy(total_budget="1", per_intent_budget_cap="1"), correlation_id="corr:d"
    )
    first, second = decision.record_decisions
    assert first.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE
    assert first.reserved_budget == "1"
    assert second.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    assert "total_budget_exceeded" in second.blockers
    assert second.reserved_budget == "0"
    assert decision.total_reserved_budget == "1"
    assert Decimal(decision.total_reserved_budget) <= Decimal(decision.total_budget)
    # High-scale exactness: the tiny requested tail is preserved (not rounded to "0" or scientific form),
    # and the exact running total 1 + 1e-100 is rendered in full fixed-point.
    assert second.requested_budget == tiny
    assert "e" not in second.requested_budget.lower()
    assert decision.total_requested_budget == "1." + "0" * 99 + "1"


# 32 (review P2). require_journal_bound must be exactly True; a non-True value fails closed at build and a
# resealed policy attesting False is rejected at re-proof (the flag can attest, never loosen, binding).
@pytest.mark.parametrize("bad", [False, "yes", 1, None])
def test_require_journal_bound_must_be_true_at_build(bad: object) -> None:
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        build_paper_sleeve_risk_budget_policy(
            policy_id="policy-1",
            sleeve_id="sleeve-1",
            total_budget="1000",
            per_intent_budget_cap="500",
            require_journal_bound=bad,
        )
    assert "policy_require_journal_bound_must_be_true" in str(exc.value)


def test_require_journal_bound_false_rejected_at_reprove() -> None:
    forged = replace(_policy(), require_journal_bound=False)
    forged = replace(forged, policy_digest=paper_sleeve_risk_budget_policy_digest(forged))
    with pytest.raises(PaperSleeveRiskBudgetDecisionError) as exc:
        evaluate_paper_sleeve_risk_budget(_state(), forged, correlation_id="corr:d")
    assert "policy_require_journal_bound_must_be_true" in str(exc.value)
