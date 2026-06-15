"""Tests for the PaperSleevePromotionCandidate -> EvidenceJournal audit/provenance bridge."""

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
from crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter import (
    PaperSleevePromotionCandidateJournalAdapterError,
    append_paper_sleeve_promotion_candidate_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    PaperSleevePromotionCandidate,
    PaperSleevePromotionCandidateStatus,
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_digest,
    paper_sleeve_promotion_candidate_to_dict,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_to_dict,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict

_VALID_DIGEST = "f" * 64
_BAD_DIGEST = "0" * 64
_JOURNAL_CORR = "corr:journal-dec"
_AUDIT_CORR = "corr:audit"


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


def _journal_entry_for_tick(tick):
    journal = EvidenceJournal()
    return journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id="corr:journal"
    )


def _state(sleeve_id: str = "sleeve-1"):
    return build_initial_paper_sleeve_state(sleeve_id=sleeve_id, correlation_id="corr:sleeve")


def _apply(state, tick, *, correlation_id: str, bind: bool = True):
    entry = _journal_entry_for_tick(tick) if bind else None
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


def _blocked_state():
    state = _state()
    return _apply(state, _tick(tick_id="t1", quantity="0"), correlation_id="c1")  # REJECTED -> blocked record


def _insufficient_state():
    state = _state()
    return _apply(state, _tick(tick_id="t1", upstream_report_digest=""), correlation_id="c1")  # INSUFFICIENT record


def _journaled(*, state=None, policy=None, decision_corr: str = "corr:dec", journal_corr: str = _JOURNAL_CORR):
    """Journal a risk-budget decision; return (decision_journal_entry, decision)."""
    state = state if state is not None else _eligible_state()
    policy = policy if policy is not None else _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id=decision_corr)
    journal = EvidenceJournal()
    entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=journal_corr
    )
    return entry, decision


def _candidate(entry, decision, *, correlation_id: str = _JOURNAL_CORR, metadata=None):
    return build_paper_sleeve_promotion_candidate(entry, decision, correlation_id=correlation_id, metadata=metadata)


def _append(journal, candidate, entry, decision, *, correlation_id: str = _AUDIT_CORR) -> EvidenceJournalEntry:
    return append_paper_sleeve_promotion_candidate_to_evidence_journal(
        journal, candidate, decision_journal_entry=entry, decision=decision, correlation_id=correlation_id
    )


def _reseal_candidate(candidate):
    return replace(candidate, candidate_digest=paper_sleeve_promotion_candidate_digest(candidate))


# 1. happy path: a journal-anchored eligible candidate appends under PAPER_SLEEVE_PROMOTION_CANDIDATE.
def test_valid_candidate_appends_under_artifact_type() -> None:
    assert (
        EvidenceArtifactType("PAPER_SLEEVE_PROMOTION_CANDIDATE")
        is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE
    )
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    assert candidate.status is PaperSleevePromotionCandidateStatus.ELIGIBLE
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    assert isinstance(appended, EvidenceJournalEntry)
    assert appended.entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE
    assert appended.correlation_id == _AUDIT_CORR
    assert appended.payload["real_orders_enabled"] is False
    assert appended.payload["real_money_enabled"] is False
    assert appended.payload["paper_only"] is True
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 2. journaled payload equals paper_sleeve_promotion_candidate_to_dict(candidate).
def test_appended_payload_equals_canonical_to_dict() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    assert appended.payload == paper_sleeve_promotion_candidate_to_dict(candidate)
    assert appended.payload["candidate_digest"] == candidate.candidate_digest
    assert appended.payload["journal_entry_digest"] == entry.entry_digest
    assert appended.payload["journal_payload_digest"] == entry.payload_digest


# 3. entry payload_digest / entry_digest are journal-computed 64-hex.
def test_entry_payload_digest_is_journal_hex64() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    assert _is_hex64(appended.payload_digest)
    assert _is_hex64(appended.entry_digest)


# 3b. export/import round-trip accepts the additive PAPER_SLEEVE_PROMOTION_CANDIDATE artifact type.
def test_serialization_round_trip_accepts_artifact_type() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    _append(journal, candidate, entry, decision)
    data = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=journal.entry_count, expected_head_digest=journal.head_digest
    )
    assert loaded.entry_count == 1
    assert loaded.verify_chain().accepted is True
    assert loaded.snapshot()[0].entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE


# 3c. blocked / insufficient candidates also journal (status flows verbatim).
@pytest.mark.parametrize(
    ("state", "status"),
    [
        (_blocked_state(), PaperSleevePromotionCandidateStatus.BLOCKED),
        (_insufficient_state(), PaperSleevePromotionCandidateStatus.INSUFFICIENT_EVIDENCE),
    ],
)
def test_blocked_and_insufficient_candidates_journal(state, status) -> None:
    entry, decision = _journaled(state=state)
    candidate = _candidate(entry, decision)
    assert candidate.status is status
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    assert appended.payload["status"] == status.value
    assert journal.entry_count == 1


# 4. wrong journal type rejected.
def test_wrong_journal_type_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        append_paper_sleeve_promotion_candidate_to_evidence_journal(
            "not-a-journal",  # type: ignore[arg-type]
            candidate,
            decision_journal_entry=entry,
            decision=decision,
            correlation_id=_AUDIT_CORR,
        )
    assert "journal_malformed" in str(exc.value)


# 5. wrong candidate type rejected.
def test_wrong_candidate_type_rejected() -> None:
    entry, decision = _journaled()
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        append_paper_sleeve_promotion_candidate_to_evidence_journal(
            journal,
            "not-a-candidate",  # type: ignore[arg-type]
            decision_journal_entry=entry,
            decision=decision,
            correlation_id=_AUDIT_CORR,
        )
    assert "candidate_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 6. wrong decision_journal_entry type rejected.
def test_wrong_decision_journal_entry_type_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        append_paper_sleeve_promotion_candidate_to_evidence_journal(
            journal,
            candidate,
            decision_journal_entry="not-an-entry",  # type: ignore[arg-type]
            decision=decision,
            correlation_id=_AUDIT_CORR,
        )
    assert "decision_journal_entry_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 7. wrong decision type rejected.
def test_wrong_decision_type_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        append_paper_sleeve_promotion_candidate_to_evidence_journal(
            journal,
            candidate,
            decision_journal_entry=entry,
            decision="not-a-decision",  # type: ignore[arg-type]
            correlation_id=_AUDIT_CORR,
        )
    assert "decision_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 7b. unsafe candidate paper-safety triple rejected before append.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "candidate_not_paper_only"),
        ({"real_orders_enabled": True}, "candidate_real_orders_enabled"),
        ({"real_money_enabled": True}, "candidate_real_money_enabled"),
    ],
)
def test_unsafe_candidate_rejected(override: dict[str, bool], reason: str) -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    tampered = _reseal_candidate(replace(candidate, **override))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, tampered, entry, decision)
    assert reason in str(exc.value)
    assert journal.entry_count == 0


# 8. forged candidate_digest rejected (self-digest re-proof).
def test_forged_candidate_digest_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    forged = replace(candidate, candidate_digest=_BAD_DIGEST)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, forged, entry, decision)
    assert "candidate_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 9. stale/resealed candidate (self-consistent but not what the journaled decision yields) rejected by rebuild.
def test_resealed_candidate_rejected_by_rebuild() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    assert candidate.status is PaperSleevePromotionCandidateStatus.ELIGIBLE
    tampered = _reseal_candidate(replace(candidate, status=PaperSleevePromotionCandidateStatus.BLOCKED))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, tampered, entry, decision)
    assert "candidate_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 10. forged decision_journal_entry.entry_digest rejected through rebuild (coordinated forge bypasses the
# explicit anchor check, but the builder's own entry self-digest re-proof still rejects it).
def test_forged_entry_digest_rejected_through_rebuild() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    forged_entry = replace(entry, entry_digest=_BAD_DIGEST)
    forged_candidate = _reseal_candidate(replace(candidate, journal_entry_digest=_BAD_DIGEST))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, forged_candidate, forged_entry, decision)
    assert "candidate_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 11. decision_journal_entry payload mismatch rejected through rebuild.
def test_entry_payload_mismatch_rejected_through_rebuild() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    other_state = _state()
    other_state = _apply(
        other_state, _tick(tick_id="z1", instrument_id="BTC-USD", quantity="3", limit_price="100"), correlation_id="z"
    )
    other_decision = evaluate_paper_sleeve_risk_budget(other_state, _policy(), correlation_id="corr:dec")
    forged_entry = replace(entry, payload=paper_sleeve_risk_budget_decision_to_dict(other_decision))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, candidate, forged_entry, decision)
    assert "candidate_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 12. decision_journal_entry payload_digest mismatch rejected through rebuild (coordinated forge).
def test_entry_payload_digest_mismatch_rejected_through_rebuild() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    forged_entry = replace(entry, payload_digest=_BAD_DIGEST)
    forged_candidate = _reseal_candidate(replace(candidate, journal_payload_digest=_BAD_DIGEST))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, forged_candidate, forged_entry, decision)
    assert "candidate_not_reproducible" in str(exc.value)
    assert journal.entry_count == 0


# 13. candidate.journal_entry_digest mismatch (vs the supplied entry) rejected by the explicit anchor check.
def test_candidate_journal_entry_digest_mismatch_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    tampered = _reseal_candidate(replace(candidate, journal_entry_digest=_BAD_DIGEST))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, tampered, entry, decision)
    assert "journal_entry_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 14. candidate.journal_payload_digest mismatch (vs the supplied entry) rejected by the explicit anchor check.
def test_candidate_journal_payload_digest_mismatch_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    tampered = _reseal_candidate(replace(candidate, journal_payload_digest=_BAD_DIGEST))
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, tampered, entry, decision)
    assert "journal_payload_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 15a. empty audit correlation_id rejected by the adapter before append.
def test_empty_audit_correlation_id_rejected() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, candidate, entry, decision, correlation_id="   ")
    assert "correlation_id_invalid" in str(exc.value)
    assert journal.entry_count == 0


# 15b. forbidden token in the audit correlation_id fails closed through the journal guard; journal unchanged.
def test_forbidden_audit_correlation_token_fails_closed() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, candidate, entry, decision, correlation_id="order_router_loop")
    assert journal.entry_count == 0


# 16. journal unchanged on a rejection even when it already holds entries (duplicate replay + mid-journal).
def test_journal_unchanged_on_rejection_mid_journal() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    _append(journal, candidate, entry, decision, correlation_id="corr:audit-a")
    head_before = journal.head_digest
    # identical candidate payload -> duplicate-payload replay fails through the journal guard.
    with pytest.raises(EvidenceJournalError):
        _append(journal, candidate, entry, decision, correlation_id="corr:audit-b")
    # a forged candidate is rejected by the adapter; the journal is still unchanged.
    forged = replace(candidate, candidate_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError):
        _append(journal, forged, entry, decision, correlation_id="corr:audit-c")
    assert journal.entry_count == 1
    assert journal.head_digest == head_before


# 16b. safe market-data terms in candidate metadata remain allowed end-to-end.
@pytest.mark.parametrize("term", ["order_book", "order_flow", "limit_order_book"])
def test_market_data_terms_allowed(term: str) -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision, metadata={"market_data_source": term})
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    assert appended.entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE
    assert journal.entry_count == 1


# 16c. malformed candidate internals wrap into an adapter error, no raw AttributeError/TypeError leak.
def test_malformed_candidate_internals_wrap_into_adapter_error() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    broken = replace(candidate, metadata=123)  # to_dict iterates metadata -> raw TypeError if unguarded
    journal = EvidenceJournal()
    with pytest.raises(PaperSleevePromotionCandidateJournalAdapterError) as exc:
        _append(journal, broken, entry, decision)
    assert "candidate_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 17a. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter as mod

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


# 17b. no live/order/scheduler/connector/execution implementation surface (exact public API only).
def test_no_forbidden_implementation_surface() -> None:
    import crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter as mod

    assert set(mod.__all__) == {
        "PaperSleevePromotionCandidateJournalAdapterError",
        "append_paper_sleeve_promotion_candidate_to_evidence_journal",
    }
    banned = (
        "execute",
        "execution",
        "route",
        "router",
        "send",
        "submit",
        "schedule",
        "scheduler",
        "connector",
        "place_order",
        "live",
        "fill",
        "pnl",
        "venue",
        "allocator",
        "position",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# 17c. no fill/PnL/execution/position/venue/order-id fields introduced in the journaled candidate payload.
def test_no_execution_fields_in_payload() -> None:
    entry, decision = _journaled()
    candidate = _candidate(entry, decision)
    journal = EvidenceJournal()
    appended = _append(journal, candidate, entry, decision)
    keys = set(appended.payload.keys())
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
        "allocation",
        "reserved_capital",
    }
    assert keys.isdisjoint(banned)
    assert isinstance(candidate, PaperSleevePromotionCandidate)
