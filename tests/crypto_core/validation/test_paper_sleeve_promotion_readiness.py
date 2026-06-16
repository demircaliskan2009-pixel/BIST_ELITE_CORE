"""Tests for the journal-anchored paper sleeve promotion readiness read-model gate."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
)
from crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter import (
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
    PaperSleevePromotionCandidateStatus,
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_digest,
    paper_sleeve_promotion_candidate_to_dict,
)
from crypto_core.validation.paper_sleeve_promotion_readiness import (
    PaperSleevePromotionReadiness,
    PaperSleevePromotionReadinessError,
    PaperSleevePromotionReadinessStatus,
    build_paper_sleeve_promotion_readiness,
    paper_sleeve_promotion_readiness_digest,
    paper_sleeve_promotion_readiness_to_dict,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict

_VALID_DIGEST = "f" * 64
_BAD_DIGEST = "0" * 64
_DECISION_CORR = "corr:journal-dec"
_CANDIDATE_AUDIT_CORR = "corr:journal-cand"
_READINESS_CORR = "corr:readiness"


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


def _full_chain(*, state=None):
    """Build a journal holding the decision (seq 0) and the promotion candidate (seq 1) in one chain.

    Returns (journal, decision_entry, decision, promotion_candidate_entry, candidate).
    """
    state = state if state is not None else _eligible_state()
    policy = _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:dec")
    journal = EvidenceJournal()
    decision_entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=_DECISION_CORR
    )
    candidate = build_paper_sleeve_promotion_candidate(decision_entry, decision, correlation_id=_DECISION_CORR)
    pce = append_paper_sleeve_promotion_candidate_to_evidence_journal(
        journal,
        candidate,
        decision_journal_entry=decision_entry,
        decision=decision,
        correlation_id=_CANDIDATE_AUDIT_CORR,
    )
    return journal, decision_entry, decision, pce, candidate


def _journal_with_decision(state=None):
    """Journal only the risk-budget decision (seq 0); return (journal, decision_entry, decision, candidate).

    The genuine candidate is built but NOT appended, so a forged variant can be raw-appended in its place to
    exercise the candidate-vs-decision re-proof against a same-chain decision anchor.
    """
    state = state if state is not None else _eligible_state()
    policy = _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:dec")
    journal = EvidenceJournal()
    decision_entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=_DECISION_CORR
    )
    candidate = build_paper_sleeve_promotion_candidate(decision_entry, decision, correlation_id=_DECISION_CORR)
    return journal, decision_entry, decision, candidate


def _raw_append_candidate(journal, candidate, *, correlation_id: str = "corr:raw-cand") -> EvidenceJournalEntry:
    return journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE,
        paper_sleeve_promotion_candidate_to_dict(candidate),
        correlation_id=correlation_id,
    )


def _build_readiness(journal, pce, candidate, *, correlation_id: str = _READINESS_CORR, metadata=None):
    return build_paper_sleeve_promotion_readiness(
        journal, pce, candidate, correlation_id=correlation_id, metadata=metadata
    )


def _reseal_candidate(candidate):
    return replace(candidate, candidate_digest=paper_sleeve_promotion_candidate_digest(candidate))


# 1. happy path: journaled eligible candidate -> READY.
def test_journaled_eligible_candidate_is_ready() -> None:
    assert PaperSleevePromotionReadinessStatus("READY") is PaperSleevePromotionReadinessStatus.READY
    journal, decision_entry, _decision, pce, candidate = _full_chain()
    readiness = _build_readiness(journal, pce, candidate)
    assert isinstance(readiness, PaperSleevePromotionReadiness)
    assert readiness.status is PaperSleevePromotionReadinessStatus.READY
    assert readiness.sleeve_id == candidate.sleeve_id
    assert readiness.policy_id == candidate.policy_id
    assert readiness.candidate_digest == candidate.candidate_digest
    assert readiness.promotion_candidate_journal_entry_digest == pce.entry_digest
    assert readiness.promotion_candidate_payload_digest == pce.payload_digest
    assert readiness.decision_journal_entry_digest == decision_entry.entry_digest
    assert readiness.decision_journal_payload_digest == decision_entry.payload_digest
    assert readiness.eligible_count == candidate.eligible_count
    assert readiness.correlation_id == _READINESS_CORR
    assert readiness.paper_only is True
    assert readiness.real_orders_enabled is False
    assert readiness.real_money_enabled is False
    assert _is_hex64(readiness.readiness_digest)
    # read-only: the journal is never appended to.
    assert journal.entry_count == 2


# 2. journaled blocked candidate -> BLOCKED, not ready.
def test_journaled_blocked_candidate_is_blocked() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain(state=_blocked_state())
    assert candidate.status is PaperSleevePromotionCandidateStatus.BLOCKED
    readiness = _build_readiness(journal, pce, candidate)
    assert readiness.status is PaperSleevePromotionReadinessStatus.BLOCKED
    assert readiness.blocked_count == 1
    assert journal.entry_count == 2


# 3. journaled insufficient candidate -> INSUFFICIENT_EVIDENCE, not ready.
def test_journaled_insufficient_candidate_is_insufficient() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain(state=_insufficient_state())
    assert candidate.status is PaperSleevePromotionCandidateStatus.INSUFFICIENT_EVIDENCE
    readiness = _build_readiness(journal, pce, candidate)
    assert readiness.status is PaperSleevePromotionReadinessStatus.INSUFFICIENT_EVIDENCE
    assert readiness.insufficient_count == 1
    assert journal.entry_count == 2


# 4. wrong journal type rejected.
def test_wrong_journal_type_rejected() -> None:
    _journal, _decision_entry, _decision, pce, candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        build_paper_sleeve_promotion_readiness(
            "not-a-journal",  # type: ignore[arg-type]
            pce,
            candidate,
            correlation_id=_READINESS_CORR,
        )
    assert "journal_malformed" in str(exc.value)


# 5. wrong promotion candidate journal entry type rejected.
def test_wrong_promotion_candidate_entry_type_rejected() -> None:
    journal, _decision_entry, _decision, _pce, candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        build_paper_sleeve_promotion_readiness(
            journal,
            "not-an-entry",  # type: ignore[arg-type]
            candidate,
            correlation_id=_READINESS_CORR,
        )
    assert "promotion_candidate_entry_malformed" in str(exc.value)
    assert journal.entry_count == 2


# 6. wrong candidate type rejected.
def test_wrong_candidate_type_rejected() -> None:
    journal, _decision_entry, _decision, pce, _candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        build_paper_sleeve_promotion_readiness(
            journal,
            pce,
            "not-a-candidate",  # type: ignore[arg-type]
            correlation_id=_READINESS_CORR,
        )
    assert "candidate_malformed" in str(exc.value)
    assert journal.entry_count == 2


# 7. candidate journal entry not present in target journal rejected.
def test_promotion_candidate_entry_not_in_journal_rejected() -> None:
    _journal_a, _decision_entry, _decision, pce, candidate = _full_chain()
    other_journal = EvidenceJournal()  # does NOT contain the promotion candidate entry
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(other_journal, pce, candidate)
    assert "promotion_candidate_entry_not_in_journal" in str(exc.value)
    assert other_journal.entry_count == 0


# 8. wrong artifact type for candidate journal entry rejected.
def test_promotion_candidate_entry_wrong_artifact_type_rejected() -> None:
    _journal_a, _decision_entry, _decision, _pce, candidate = _full_chain()
    journal = EvidenceJournal()
    tick_entry = journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_trade_tick_to_dict(_tick(tick_id="wrong")),
        correlation_id="corr:tick",
    )
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, tick_entry, candidate)
    assert "promotion_candidate_entry_artifact_type_mismatch" in str(exc.value)
    assert journal.entry_count == 1


# 9. candidate journal entry self-digest mismatch rejected (supplied entry tampered, entry_digest intact).
def test_promotion_candidate_entry_self_digest_mismatch_rejected() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    forged_pce = replace(pce, prev_entry_digest=_BAD_DIGEST)  # entry_digest unchanged -> membership still passes
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, forged_pce, candidate)
    assert "promotion_candidate_entry_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 10. candidate journal entry payload mismatch rejected (entry anchors a different candidate).
def test_promotion_candidate_entry_payload_mismatch_rejected() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    other_candidate = _reseal_candidate(replace(candidate, blockers=("synthetic-blocker",)))
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, other_candidate)
    assert "promotion_candidate_payload_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 11. candidate journal entry payload_digest mismatch rejected (payload matches, digest forged).
def test_promotion_candidate_entry_payload_digest_mismatch_rejected() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    forged_pce = replace(pce, payload_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, forged_pce, candidate)
    assert "promotion_candidate_payload_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 12. candidate candidate_digest mismatch rejected.
def test_candidate_digest_mismatch_rejected() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    forged = replace(candidate, candidate_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged)
    assert "candidate_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 13. candidate unsafe paper flag rejected.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "candidate_not_paper_only"),
        ({"real_orders_enabled": True}, "candidate_real_orders_enabled"),
        ({"real_money_enabled": True}, "candidate_real_money_enabled"),
    ],
)
def test_unsafe_candidate_paper_flag_rejected(override: dict[str, bool], reason: str) -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    tampered = _reseal_candidate(replace(candidate, **override))
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, tampered)
    assert reason in str(exc.value)
    assert journal.entry_count == 2


# 14. upstream decision anchor not present in same journal rejected.
def test_upstream_decision_anchor_not_in_journal_rejected() -> None:
    _journal_a, _decision_entry, _decision, _pce, candidate = _full_chain()
    journal = EvidenceJournal()  # contains the candidate entry but NOT its upstream decision anchor
    pce = _raw_append_candidate(journal, candidate)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, candidate)
    assert "decision_entry_not_in_journal" in str(exc.value)
    assert journal.entry_count == 1


# 15. upstream decision anchor wrong artifact type rejected.
def test_upstream_decision_anchor_wrong_artifact_type_rejected() -> None:
    _journal_a, _decision_entry, _decision, _pce, candidate = _full_chain()
    journal = EvidenceJournal()
    tick_entry = journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_trade_tick_to_dict(_tick(tick_id="upstream-wrong")),
        correlation_id="corr:tick",
    )
    # forge the candidate's upstream anchor to point at the (wrong-type) tick entry, then journal that candidate.
    forged_candidate = _reseal_candidate(replace(candidate, journal_entry_digest=tick_entry.entry_digest))
    pce = _raw_append_candidate(journal, forged_candidate)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged_candidate)
    assert "decision_entry_artifact_type_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 16. a tampered upstream decision entry (self-digest broken) can never yield a readiness — fail closed. The
# explicit upstream self-digest re-proof is defense-in-depth; a corrupt chain also trips get_by_entry_digest.
def test_tampered_upstream_decision_entry_fails_closed() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    # Break the stored upstream decision entry's self-digest; the chain no longer verifies.
    journal._entries[0] = replace(journal._entries[0], entry_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessError):
        _build_readiness(journal, pce, candidate)


# 17. candidate.journal_payload_digest vs upstream decision entry payload_digest mismatch rejected.
def test_decision_journal_payload_digest_mismatch_rejected() -> None:
    state = _eligible_state()
    policy = _policy()
    decision = evaluate_paper_sleeve_risk_budget(state, policy, correlation_id="corr:dec")
    journal = EvidenceJournal()
    decision_entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=policy, correlation_id=_DECISION_CORR
    )
    candidate = build_paper_sleeve_promotion_candidate(decision_entry, decision, correlation_id=_DECISION_CORR)
    # keep the upstream entry_digest anchor (so the decision entry resolves) but forge the payload-digest anchor.
    forged_candidate = _reseal_candidate(replace(candidate, journal_payload_digest=_BAD_DIGEST))
    pce = _raw_append_candidate(journal, forged_candidate)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged_candidate)
    assert "decision_journal_payload_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 18. stale/resealed candidate rejected by journal anchoring (self-consistent, but not what the entry anchors).
def test_resealed_candidate_rejected_by_journal_anchoring() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    assert candidate.status is PaperSleevePromotionCandidateStatus.ELIGIBLE
    tampered = _reseal_candidate(replace(candidate, status=PaperSleevePromotionCandidateStatus.BLOCKED))
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, tampered)
    assert "promotion_candidate_payload_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 18b (review P1). a forged candidate that anchors a BLOCKED decision but reseals itself ELIGIBLE (counts that
# do NOT match the decision) is rejected — a raw-appended self-consistent candidate can never claim READY over
# a decision whose journaled counts disagree.
def test_forged_candidate_counts_vs_decision_rejected() -> None:
    journal, _decision_entry, _decision, candidate = _journal_with_decision(_blocked_state())
    assert candidate.status is PaperSleevePromotionCandidateStatus.BLOCKED
    forged = _reseal_candidate(
        replace(
            candidate,
            status=PaperSleevePromotionCandidateStatus.ELIGIBLE,
            eligible_count=1,
            blocked_count=0,
            insufficient_count=0,
        )
    )
    pce = _raw_append_candidate(journal, forged)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged)
    assert "candidate_decision_counts_mismatch" in str(exc.value)
    assert journal.entry_count == 2


# 18c (review P1). a forged candidate that keeps the BLOCKED decision's counts but reseals its status as
# ELIGIBLE is rejected — status must be the verdict the candidate gate derives from the decision-bound counts.
def test_forged_candidate_status_inconsistent_with_counts_rejected() -> None:
    journal, _decision_entry, _decision, candidate = _journal_with_decision(_blocked_state())
    forged = _reseal_candidate(replace(candidate, status=PaperSleevePromotionCandidateStatus.ELIGIBLE))
    pce = _raw_append_candidate(journal, forged)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged)
    assert "candidate_status_inconsistent" in str(exc.value)
    assert journal.entry_count == 2


# 18d (review P1). a forged candidate whose decision_digest / identity / blockers disagree with the anchored
# decision payload is rejected (the candidate must faithfully derive from the decision it points at).
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"decision_digest": _BAD_DIGEST}, "candidate_decision_digest_mismatch"),
        ({"sleeve_id": "other-sleeve"}, "candidate_decision_identity_mismatch"),
        ({"policy_id": "other-policy"}, "candidate_decision_identity_mismatch"),
        ({"blockers": ("synthetic-blocker",)}, "candidate_decision_blockers_mismatch"),
    ],
)
def test_forged_candidate_fields_vs_decision_rejected(override: dict[str, object], reason: str) -> None:
    journal, _decision_entry, _decision, candidate = _journal_with_decision()
    forged = _reseal_candidate(replace(candidate, **override))
    pce = _raw_append_candidate(journal, forged)
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, forged)
    assert reason in str(exc.value)
    assert journal.entry_count == 2


# 19. wrong/empty/forbidden correlation_id or metadata rejected.
def test_empty_correlation_id_rejected() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, candidate, correlation_id="   ")
    assert "correlation_id_invalid" in str(exc.value)
    assert journal.entry_count == 2


@pytest.mark.parametrize(
    "correlation_id",
    ["order_router_loop", "live_execution", "bist_session"],
)
def test_forbidden_correlation_id_rejected(correlation_id: str) -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, candidate, correlation_id=correlation_id)
    assert "scope_violation" in str(exc.value)
    assert journal.entry_count == 2


@pytest.mark.parametrize(
    "metadata",
    [{"note": "order_router"}, {"venue": "live_order"}, {"market": "bist-100"}],
)
def test_forbidden_metadata_rejected(metadata: dict[str, str]) -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    with pytest.raises(PaperSleevePromotionReadinessError) as exc:
        _build_readiness(journal, pce, candidate, metadata=metadata)
    assert "scope_violation" in str(exc.value)
    assert journal.entry_count == 2


def test_safe_market_data_metadata_allowed() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    readiness = _build_readiness(journal, pce, candidate, metadata={"market_data_source": "order_book"})
    assert readiness.metadata == (("market_data_source", "order_book"),)
    assert journal.entry_count == 2


# 20. no mutation: journal entry_count / head_digest unchanged on every rejection path.
def test_journal_unchanged_on_all_rejection_paths() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    count_before = journal.entry_count
    head_before = journal.head_digest
    rejections = [
        lambda: _build_readiness(journal, pce, replace(candidate, candidate_digest=_BAD_DIGEST)),
        lambda: _build_readiness(journal, replace(pce, payload_digest=_BAD_DIGEST), candidate),
        lambda: _build_readiness(journal, pce, candidate, correlation_id="   "),
        lambda: _build_readiness(journal, pce, candidate, correlation_id="order_router"),
        lambda: _build_readiness(journal, pce, _reseal_candidate(replace(candidate, real_orders_enabled=True))),
    ]
    for call in rejections:
        with pytest.raises(PaperSleevePromotionReadinessError):
            call()
    assert journal.entry_count == count_before
    assert journal.head_digest == head_before


# 21. to_dict / digest deterministic roundtrip.
def test_to_dict_and_digest_deterministic_roundtrip() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    readiness = _build_readiness(journal, pce, candidate)
    payload = paper_sleeve_promotion_readiness_to_dict(readiness)
    assert payload["readiness_digest"] == readiness.readiness_digest
    assert paper_sleeve_promotion_readiness_digest(readiness) == readiness.readiness_digest
    # rebuilding from the same chain yields an identical digest (deterministic).
    journal2, _de2, _d2, pce2, candidate2 = _full_chain()
    readiness2 = build_paper_sleeve_promotion_readiness(journal2, pce2, candidate2, correlation_id=_READINESS_CORR)
    assert readiness2.readiness_digest == readiness.readiness_digest
    assert paper_sleeve_promotion_readiness_to_dict(readiness2) == payload


# 22. no execution/live/order/scheduler/connector/BIST fields in the readiness payload.
def test_no_execution_fields_in_payload() -> None:
    journal, _decision_entry, _decision, pce, candidate = _full_chain()
    readiness = _build_readiness(journal, pce, candidate)
    keys = set(paper_sleeve_promotion_readiness_to_dict(readiness).keys())
    banned = {
        "fill",
        "filled",
        "fills",
        "fill_price",
        "executed",
        "execution",
        "pnl",
        "realized_pnl",
        "position",
        "order_id",
        "venue",
        "venue_order_id",
        "allocation",
        "allocated",
        "reserved_capital",
        "scheduler",
        "connector",
    }
    assert keys.isdisjoint(banned)


# 23a. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.validation.paper_sleeve_promotion_readiness as mod

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


# 23b. no live/order/scheduler/connector/execution implementation surface (exact public API only).
def test_no_forbidden_implementation_surface() -> None:
    import crypto_core.validation.paper_sleeve_promotion_readiness as mod

    assert set(mod.__all__) == {
        "PaperSleevePromotionReadiness",
        "PaperSleevePromotionReadinessError",
        "PaperSleevePromotionReadinessStatus",
        "build_paper_sleeve_promotion_readiness",
        "paper_sleeve_promotion_readiness_digest",
        "paper_sleeve_promotion_readiness_to_dict",
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
        "allocate",
        "position",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name
