"""Tests for the journal-anchored paper sleeve promotion candidate read-model gate."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    PaperSleevePromotionCandidate,
    PaperSleevePromotionCandidateError,
    PaperSleevePromotionCandidateStatus,
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_digest,
    paper_sleeve_promotion_candidate_to_dict,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
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


def _journaled(*, state=None, policy=None, decision_corr: str = "corr:dec", journal_corr: str = "corr:journal-dec"):
    state = state if state is not None else _eligible_state()
    policy = policy if policy is not None else _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id=decision_corr)
    journal = EvidenceJournal()
    entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=journal_corr
    )
    return entry, decision


def _reseal_decision(decision):
    return replace(decision, decision_digest=paper_sleeve_risk_budget_decision_digest(decision))


# 1. happy path: journaled eligible decision -> ELIGIBLE candidate.
def test_journaled_eligible_decision_is_eligible() -> None:
    entry, decision = _journaled()
    candidate = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    assert isinstance(candidate, PaperSleevePromotionCandidate)
    assert candidate.status is PaperSleevePromotionCandidateStatus.ELIGIBLE
    assert candidate.eligible_count == 2
    assert candidate.decision_digest == decision.decision_digest
    assert candidate.journal_payload_digest == entry.payload_digest
    assert candidate.journal_entry_digest == entry.entry_digest
    assert candidate.correlation_id == "corr:journal-dec"
    assert candidate.paper_only is True
    assert candidate.real_orders_enabled is False
    assert candidate.real_money_enabled is False
    assert _is_hex64(candidate.candidate_digest)


# 2. blocked decision -> BLOCKED candidate, not eligible.
def test_journaled_blocked_decision_is_blocked() -> None:
    entry, decision = _journaled(state=_blocked_state())
    candidate = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    assert candidate.status is PaperSleevePromotionCandidateStatus.BLOCKED
    assert candidate.eligible_count == 0
    assert candidate.blocked_count == 1


# 3. insufficient evidence decision -> INSUFFICIENT_EVIDENCE candidate.
def test_journaled_insufficient_decision_is_insufficient() -> None:
    entry, decision = _journaled(state=_insufficient_state())
    candidate = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    assert candidate.status is PaperSleevePromotionCandidateStatus.INSUFFICIENT_EVIDENCE
    assert candidate.eligible_count == 0
    assert candidate.blocked_count == 0
    assert candidate.insufficient_count == 1


# 4. wrong artifact type rejected.
def test_wrong_artifact_type_rejected() -> None:
    state = _eligible_state()
    policy = _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:dec")
    journal = EvidenceJournal()
    wrong_entry = journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_sleeve_risk_budget_decision_to_dict(decision),
        correlation_id="corr:journal-dec",
    )
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(wrong_entry, decision, correlation_id="corr:journal-dec")
    assert "journal_entry_artifact_type_mismatch" in str(exc.value)


# 5. journal payload mismatch rejected (entry anchors a different decision).
def test_journal_payload_mismatch_rejected() -> None:
    entry, _ = _journaled()  # entry anchors the eligible decision
    other_state = _state()
    other_state = _apply(
        other_state, _tick(tick_id="z1", instrument_id="BTC-USD", quantity="3", limit_price="100"), correlation_id="z"
    )
    other_decision = evaluate_paper_sleeve_risk_budget(other_state, _policy(), correlation_id="corr:dec")
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, other_decision, correlation_id="corr:journal-dec")
    assert "journal_payload_mismatch" in str(exc.value)


# 6. journal payload_digest mismatch rejected (payload matches, digest forged).
def test_journal_payload_digest_mismatch_rejected() -> None:
    entry, decision = _journaled()
    forged_entry = replace(entry, payload_digest="0" * 64)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(forged_entry, decision, correlation_id="corr:journal-dec")
    assert "journal_payload_digest_mismatch" in str(exc.value)


# 6b (review P1). a forged journal entry self-digest is rejected before binding, even when type /
# correlation / payload / payload_digest are all intact (digest-boundary / audit-provenance contract).
def test_journal_entry_digest_mismatch_rejected() -> None:
    entry, decision = _journaled()
    forged_entry = replace(entry, entry_digest="0" * 64)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(forged_entry, decision, correlation_id="corr:journal-dec")
    assert "journal_entry_digest_mismatch" in str(exc.value)


# 7. decision digest mismatch rejected.
def test_decision_digest_mismatch_rejected() -> None:
    entry, decision = _journaled()
    forged = replace(decision, decision_digest="0" * 64)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, forged, correlation_id="corr:journal-dec")
    assert "decision_digest_mismatch" in str(exc.value)


# 8. stale/resealed decision rejected by journal anchoring (bare decision is not enough).
def test_stale_resealed_decision_rejected_by_anchoring() -> None:
    entry, decision = _journaled()
    tampered = _reseal_decision(replace(decision, total_reserved_budget="999"))  # re-proves but != journaled payload
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, tampered, correlation_id="corr:journal-dec")
    assert "journal_payload_mismatch" in str(exc.value)


# 9. journal correlation mismatch rejected.
def test_journal_correlation_mismatch_rejected() -> None:
    entry, decision = _journaled(journal_corr="corr:journal-dec")
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:other")
    assert "journal_correlation_id_mismatch" in str(exc.value)


# 10. unsafe decision paper-safety flag rejected.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "decision_not_paper_only"),
        ({"real_orders_enabled": True}, "decision_real_orders_enabled"),
        ({"real_money_enabled": True}, "decision_real_money_enabled"),
    ],
)
def test_unsafe_decision_flag_rejected(override: dict[str, bool], reason: str) -> None:
    entry, decision = _journaled()
    tampered = replace(decision, **override)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, tampered, correlation_id="corr:journal-dec")
    assert reason in str(exc.value)


# 11. unsafe record paper-safety flag rejected.
def test_unsafe_record_flag_rejected() -> None:
    entry, decision = _journaled()
    bad_record = replace(decision.record_decisions[0], real_orders_enabled=True)
    tampered = _reseal_decision(replace(decision, record_decisions=(bad_record, *decision.record_decisions[1:])))
    with pytest.raises(PaperSleevePromotionCandidateError) as exc:
        build_paper_sleeve_promotion_candidate(entry, tampered, correlation_id="corr:journal-dec")
    assert "record_decision_not_paper_safe" in str(exc.value)


# 12. wrong input types rejected.
def test_wrong_input_types_rejected() -> None:
    entry, decision = _journaled()
    with pytest.raises(PaperSleevePromotionCandidateError) as exc1:
        build_paper_sleeve_promotion_candidate("not-an-entry", decision, correlation_id="corr:journal-dec")  # type: ignore[arg-type]
    assert "journal_entry_malformed" in str(exc1.value)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc2:
        build_paper_sleeve_promotion_candidate(entry, "not-a-decision", correlation_id="corr:journal-dec")  # type: ignore[arg-type]
    assert "decision_malformed" in str(exc2.value)
    with pytest.raises(PaperSleevePromotionCandidateError) as exc3:
        build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="")
    assert "correlation_id_invalid" in str(exc3.value)


# 13. no forbidden execution/live/order/scheduler/connector/BIST implementation surface (public API names).
def test_no_forbidden_surface() -> None:
    import crypto_core.validation.paper_sleeve_promotion_candidate as mod

    assert set(mod.__all__) == {
        "PaperSleevePromotionCandidate",
        "PaperSleevePromotionCandidateError",
        "PaperSleevePromotionCandidateStatus",
        "build_paper_sleeve_promotion_candidate",
        "paper_sleeve_promotion_candidate_digest",
        "paper_sleeve_promotion_candidate_to_dict",
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
        "order_router",
        "live",
        "fill",
        "pnl",
        "venue",
        "allocator",
        "allocate",
        "position",
        "runtime",
        "shadow",
        "bist",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# 13b. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity() -> None:
    import crypto_core.validation.paper_sleeve_promotion_candidate as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
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


# 14. to_dict / digest deterministic roundtrip.
def test_to_dict_and_digest_deterministic() -> None:
    entry, decision = _journaled()
    first = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    second = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    assert first.candidate_digest == second.candidate_digest
    payload = paper_sleeve_promotion_candidate_to_dict(first)
    assert payload["candidate_digest"] == first.candidate_digest
    assert paper_sleeve_promotion_candidate_digest(first) == first.candidate_digest
    tampered = replace(first, status=PaperSleevePromotionCandidateStatus.BLOCKED)
    assert paper_sleeve_promotion_candidate_digest(tampered) != tampered.candidate_digest


# 15. no hidden IO/runtime/execution fields in the candidate payload.
def test_no_execution_fields_in_payload() -> None:
    entry, decision = _journaled()
    candidate = build_paper_sleeve_promotion_candidate(entry, decision, correlation_id="corr:journal-dec")
    keys = set(paper_sleeve_promotion_candidate_to_dict(candidate).keys())
    banned = {
        "fill",
        "filled",
        "fills",
        "executed",
        "execution",
        "pnl",
        "realized_pnl",
        "position",
        "order_id",
        "venue",
        "venue_order_id",
        "connector",
        "scheduler",
        "runtime",
        "allocator",
        "reserved_capital",
    }
    assert keys.isdisjoint(banned)
