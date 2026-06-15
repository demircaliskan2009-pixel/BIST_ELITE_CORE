"""Tests for the PaperSleeveRiskBudgetDecision -> EvidenceJournal audit bridge."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
    EvidenceJournalError,
    evidence_journal_from_dict,
    evidence_journal_to_dict,
)
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    PaperSleeveRiskBudgetDecisionJournalAdapterError,
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetRecordStatus,
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
    paper_sleeve_risk_budget_record_decision_digest,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict

_VALID_DIGEST = "f" * 64


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


def _journal_entry(tick):
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


def _eligible_state():
    state = _state()
    state = _apply(
        state, _tick(tick_id="t1", instrument_id="BTC-USD", quantity="2", limit_price="100"), correlation_id="c1"
    )
    state = _apply(
        state, _tick(tick_id="t2", instrument_id="ETH-USD", quantity="1", limit_price="50"), correlation_id="c2"
    )
    return state


def _decision(*, state=None, policy=None, correlation_id: str = "corr:dec", metadata=None):
    state = state if state is not None else _eligible_state()
    policy = policy if policy is not None else _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id=correlation_id, metadata=metadata)
    return state, policy, decision


def _append(journal, decision, state, policy, correlation_id: str = "corr:journal-dec") -> EvidenceJournalEntry:
    return append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=correlation_id
    )


def _reseal_decision(decision):
    return replace(decision, decision_digest=paper_sleeve_risk_budget_decision_digest(decision))


def _reseal_record(record):
    return replace(record, record_decision_digest=paper_sleeve_risk_budget_record_decision_digest(record))


def _blocked_state():
    state = _state()
    state = _apply(state, _tick(tick_id="t1", quantity="2", limit_price="100"), correlation_id="c1")  # eligible
    state = _apply(state, _tick(tick_id="t2", quantity="0"), correlation_id="c2")  # REJECTED -> blocked
    return state


def _insufficient_state():
    state = _state()
    state = _apply(state, _tick(tick_id="t1", quantity="2", limit_price="100"), correlation_id="c1")  # eligible
    state = _apply(state, _tick(tick_id="t2", upstream_report_digest=""), correlation_id="c2")  # INSUFFICIENT
    return state


# 1. valid decision appends under PAPER_SLEEVE_RISK_BUDGET_DECISION.
def test_valid_decision_appends_under_artifact_type() -> None:
    assert (
        EvidenceArtifactType("PAPER_SLEEVE_RISK_BUDGET_DECISION")
        is EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION
    )
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    entry = _append(journal, decision, state, policy)
    assert isinstance(entry, EvidenceJournalEntry)
    assert entry.entry_type is EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION
    assert entry.payload["real_orders_enabled"] is False
    assert entry.payload["real_money_enabled"] is False
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 2. journal entry payload equals paper_sleeve_risk_budget_decision_to_dict(decision).
def test_appended_payload_equals_canonical_to_dict() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    entry = _append(journal, decision, state, policy)
    assert entry.payload == paper_sleeve_risk_budget_decision_to_dict(decision)
    assert entry.payload["decision_digest"] == decision.decision_digest


# 3. entry payload_digest is journal-computed 64-hex.
def test_entry_payload_digest_is_journal_hex64() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    entry = _append(journal, decision, state, policy)
    assert _is_hex64(entry.payload_digest)
    assert _is_hex64(entry.entry_digest)


# 4. export/import round-trip accepts PAPER_SLEEVE_RISK_BUDGET_DECISION.
def test_serialization_round_trip_accepts_artifact_type() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    _append(journal, decision, state, policy)
    data = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=journal.entry_count, expected_head_digest=journal.head_digest
    )
    assert loaded.entry_count == 1
    assert loaded.verify_chain().accepted is True
    assert loaded.snapshot()[0].entry_type is EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION


# 5. forged decision digest rejected before append.
def test_forged_decision_digest_rejected() -> None:
    state, policy, decision = _decision()
    forged = replace(decision, decision_digest="0" * 64)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, forged, state, policy)
    assert "decision_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 6. forged record-decision digest rejected before append.
def test_forged_record_decision_digest_rejected() -> None:
    state, policy, decision = _decision()
    bad_record = replace(decision.record_decisions[0], record_decision_digest="0" * 64)
    forged = _reseal_decision(replace(decision, record_decisions=(bad_record, *decision.record_decisions[1:])))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, forged, state, policy)
    assert "record_decision_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 7. stale/resealed decision (content not matching state+policy) rejected by re-render equality.
def test_resealed_decision_rejected_by_rerender() -> None:
    state, policy, decision = _decision()
    bad_record = _reseal_record(replace(decision.record_decisions[0], instrument_id="XRP-USD"))
    tampered = _reseal_decision(replace(decision, record_decisions=(bad_record, *decision.record_decisions[1:])))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "decision_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 8. state mismatch rejected before append.
def test_state_mismatch_rejected() -> None:
    state, policy, decision = _decision()
    other_state = _state()
    other_state = _apply(
        other_state, _tick(tick_id="z1", instrument_id="BTC-USD", quantity="3", limit_price="100"), correlation_id="z"
    )
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, decision, other_state, policy)
    assert "state_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 9. policy mismatch rejected before append.
def test_policy_mismatch_rejected() -> None:
    state, policy, decision = _decision()
    other_policy = _policy(total_budget="2000")
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, decision, state, other_policy)
    assert "policy_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 10/11/12. unsafe decision paper-safety triple rejected.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "decision_not_paper_only"),
        ({"real_orders_enabled": True}, "decision_real_orders_enabled"),
        ({"real_money_enabled": True}, "decision_real_money_enabled"),
    ],
)
def test_unsafe_decision_rejected(override: dict[str, bool], reason: str) -> None:
    state, policy, decision = _decision()
    tampered = replace(decision, **override)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert reason in str(exc.value)
    assert journal.entry_count == 0


# 13. blocked record with nonzero reserved_budget rejected.
def test_blocked_record_nonzero_reserved_rejected() -> None:
    state, policy, decision = _decision(state=_blocked_state())
    blocked = decision.record_decisions[1]
    assert blocked.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED
    bad_record = _reseal_record(replace(blocked, reserved_budget="5"))
    tampered = _reseal_decision(replace(decision, record_decisions=(decision.record_decisions[0], bad_record)))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "blocked_record_reserved_budget_nonzero" in str(exc.value)
    assert journal.entry_count == 0


# 14. insufficient record with nonzero reserved_budget rejected.
def test_insufficient_record_nonzero_reserved_rejected() -> None:
    state, policy, decision = _decision(state=_insufficient_state())
    insufficient = decision.record_decisions[1]
    assert insufficient.status is PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE
    bad_record = _reseal_record(replace(insufficient, reserved_budget="3"))
    tampered = _reseal_decision(replace(decision, record_decisions=(decision.record_decisions[0], bad_record)))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "insufficient_record_reserved_budget_nonzero" in str(exc.value)
    assert journal.entry_count == 0


# 15. total_reserved_budget > total_budget rejected.
def test_total_reserved_exceeds_total_budget_rejected() -> None:
    state, policy, decision = _decision()
    tampered = _reseal_decision(replace(decision, total_reserved_budget="2000"))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "total_reserved_budget_exceeds_total_budget" in str(exc.value)
    assert journal.entry_count == 0


# 16. count mismatch rejected.
def test_count_mismatch_rejected() -> None:
    state, policy, decision = _decision()
    tampered = _reseal_decision(replace(decision, eligible_count=99))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "eligible_count_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 17. total_reserved_budget mismatch vs records (within total_budget) rejected.
def test_total_reserved_mismatch_vs_records_rejected() -> None:
    state, policy, decision = _decision()
    assert decision.total_reserved_budget == "250"
    tampered = _reseal_decision(replace(decision, total_reserved_budget="300"))  # <= total_budget but != sum
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "total_reserved_budget_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 18. duplicate payload replay fails closed through EvidenceJournal; journal unchanged.
def test_duplicate_payload_replay_fails_closed() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    _append(journal, decision, state, policy, correlation_id="corr:a")
    head_before = journal.head_digest
    with pytest.raises(EvidenceJournalError):
        _append(journal, decision, state, policy, correlation_id="corr:b")  # identical payload
    assert journal.entry_count == 1
    assert journal.head_digest == head_before


# 19. forbidden token in correlation_id fails through journal guard; journal unchanged.
def test_forbidden_correlation_token_fails_closed() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, decision, state, policy, correlation_id="order_router_loop")
    assert journal.entry_count == 0


# 20. forbidden token in payload/metadata rejected (re-render fails closed).
def test_forbidden_metadata_token_rejected() -> None:
    state, policy, decision = _decision()
    tampered = _reseal_decision(replace(decision, metadata=(("note", "order_router"),)))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "decision_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 21. safe market-data terms remain allowed.
@pytest.mark.parametrize("term", ["order_book", "order_flow", "limit_order_book"])
def test_market_data_terms_allowed(term: str) -> None:
    state = _eligible_state()
    policy = _policy()
    decision = evaluate_paper_sleeve_risk_budget(
        state, policy, correlation_id="corr:dec", metadata={"market_data_source": term}
    )
    journal = EvidenceJournal()
    entry = _append(journal, decision, state, policy, correlation_id="corr:market")
    assert entry.entry_type is EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION
    assert journal.entry_count == 1


# 22. malformed decision internals wrap into adapter error, no raw AttributeError/TypeError leak.
def test_malformed_decision_internals_wrap_into_adapter_error() -> None:
    state, policy, decision = _decision()
    broken = replace(decision, metadata=123)  # to_dict iterates metadata -> raw TypeError if unguarded
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, broken, state, policy)
    assert "decision_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 23. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
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
    assert crypto_submodules.isdisjoint({"service", "connector", "runtime", "venue", "execution", "orchestrator"})


# 24. no live/order/scheduler/connector/BIST implementation surface (exact public API only).
def test_no_forbidden_implementation_surface() -> None:
    import crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter as mod

    assert set(mod.__all__) == {
        "PaperSleeveRiskBudgetDecisionJournalAdapterError",
        "append_paper_sleeve_risk_budget_decision_to_evidence_journal",
    }
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
        "allocator",
        "promotion",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# 25. no fill/PnL/execution/position/venue/order-id fields introduced in the journaled payload.
def test_no_execution_fields_in_payload() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    entry = _append(journal, decision, state, policy)
    keys = set(entry.payload.keys())
    for record in entry.payload["record_decisions"]:
        keys |= set(record.keys())
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
    assert keys.isdisjoint(banned)


def _decision_with_record_field(decision, field: str, value: object):
    """Tamper one field of the first record decision, resealing record + decision digests."""
    bad_record = _reseal_record(replace(decision.record_decisions[0], **{field: value}))
    return _reseal_decision(replace(decision, record_decisions=(bad_record, *decision.record_decisions[1:])))


# 26 (review P2). total_requested_budget that disagrees with the per-record requested sum is rejected.
def test_total_requested_budget_mismatch_rejected() -> None:
    state, policy, decision = _decision()
    assert decision.total_requested_budget == "250"
    tampered = _reseal_decision(replace(decision, total_requested_budget="300"))  # valid decimal, != sum
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "total_requested_budget_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 27 (review P2). malformed decimal strings in reachable decision-level budget fields are rejected.
@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("total_budget", "total_budget_malformed"),
        ("total_reserved_budget", "total_reserved_budget_malformed"),
        ("total_requested_budget", "total_requested_budget_malformed"),
    ],
)
def test_malformed_decision_total_decimal_rejected(field: str, reason: str) -> None:
    state, policy, decision = _decision()
    tampered = _reseal_decision(replace(decision, **{field: "1.2.3"}))  # not a strict decimal string
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert reason in str(exc.value)
    assert journal.entry_count == 0


# 27b (review P2). malformed decimal strings in reachable record-level budget fields are rejected.
@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("reserved_budget", "record_reserved_budget_malformed"),
        ("requested_budget", "record_requested_budget_malformed"),
    ],
)
def test_malformed_record_decimal_rejected(field: str, reason: str) -> None:
    state, policy, decision = _decision()
    tampered = _decision_with_record_field(decision, field, "1.2.3")
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert reason in str(exc.value)
    assert journal.entry_count == 0


# 28 (review P2). wrong-type gates for journal / decision / state / policy reject before append.
def test_wrong_journal_type_rejected() -> None:
    state, policy, decision = _decision()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        append_paper_sleeve_risk_budget_decision_to_evidence_journal(
            "not-a-journal",  # type: ignore[arg-type]
            decision,
            state=state,
            policy=policy,
            correlation_id="corr:x",
        )
    assert "journal_malformed" in str(exc.value)


def test_wrong_decision_type_rejected() -> None:
    state, policy, _ = _decision()
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        append_paper_sleeve_risk_budget_decision_to_evidence_journal(
            journal,
            "not-a-decision",  # type: ignore[arg-type]
            state=state,
            policy=policy,
            correlation_id="corr:x",
        )
    assert "decision_malformed" in str(exc.value)
    assert journal.entry_count == 0


def test_wrong_state_type_rejected() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        append_paper_sleeve_risk_budget_decision_to_evidence_journal(
            journal,
            decision,
            state="not-a-state",  # type: ignore[arg-type]
            policy=policy,
            correlation_id="corr:x",
        )
    assert "state_malformed" in str(exc.value)
    assert journal.entry_count == 0


def test_wrong_policy_type_rejected() -> None:
    state, policy, decision = _decision()
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        append_paper_sleeve_risk_budget_decision_to_evidence_journal(
            journal,
            decision,
            state=state,
            policy="not-a-policy",  # type: ignore[arg-type]
            correlation_id="corr:x",
        )
    assert "policy_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 29 (review P2). a record decision attesting an unsafe paper-safety flag is rejected before append.
@pytest.mark.parametrize(
    "override",
    [{"paper_only": False}, {"real_orders_enabled": True}, {"real_money_enabled": True}],
)
def test_record_decision_not_paper_safe_rejected(override: dict[str, bool]) -> None:
    state, policy, decision = _decision()
    bad_record = _reseal_record(replace(decision.record_decisions[0], **override))
    tampered = _reseal_decision(replace(decision, record_decisions=(bad_record, *decision.record_decisions[1:])))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleeveRiskBudgetDecisionJournalAdapterError) as exc:
        _append(journal, tampered, state, policy)
    assert "record_decision_not_paper_safe" in str(exc.value)
    assert journal.entry_count == 0
