"""Tests for the PaperSleevePromotionReadiness -> EvidenceJournal audit/provenance bridge."""

from __future__ import annotations

import ast
from collections import namedtuple
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
    append_paper_sleeve_promotion_candidate_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_promotion_readiness_journal_adapter import (
    PaperSleevePromotionReadinessJournalAdapterError,
    append_paper_sleeve_promotion_readiness_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_digest,
)
from crypto_core.validation.paper_sleeve_promotion_readiness import (
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
_AUDIT_CORR = "corr:audit"

_Chain = namedtuple("_Chain", "journal state policy decision decision_entry candidate pce readiness")


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


def _readied(state=None, *, readiness_metadata=None) -> _Chain:
    """Build a journal with decision (seq 0) + promotion candidate (seq 1) and a same-chain readiness."""
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
    readiness = build_paper_sleeve_promotion_readiness(
        journal, pce, candidate, correlation_id=_READINESS_CORR, metadata=readiness_metadata
    )
    return _Chain(journal, state, policy, decision, decision_entry, candidate, pce, readiness)


def _append(journal, readiness, pce, candidate, *, correlation_id: str = _AUDIT_CORR) -> EvidenceJournalEntry:
    return append_paper_sleeve_promotion_readiness_to_evidence_journal(
        journal, readiness, promotion_candidate_journal_entry=pce, candidate=candidate, correlation_id=correlation_id
    )


def _reseal_readiness(readiness):
    return replace(readiness, readiness_digest=paper_sleeve_promotion_readiness_digest(readiness))


def _reseal_candidate(candidate):
    return replace(candidate, candidate_digest=paper_sleeve_promotion_candidate_digest(candidate))


# 1. happy path: a same-chain journal-anchored readiness appends under PAPER_SLEEVE_PROMOTION_READINESS.
def test_valid_readiness_appends_under_artifact_type() -> None:
    assert (
        EvidenceArtifactType("PAPER_SLEEVE_PROMOTION_READINESS")
        is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS
    )
    c = _readied()
    appended = _append(c.journal, c.readiness, c.pce, c.candidate)
    assert isinstance(appended, EvidenceJournalEntry)
    assert appended.entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS
    assert appended.correlation_id == _AUDIT_CORR
    assert appended.payload["status"] == PaperSleevePromotionReadinessStatus.READY.value
    assert appended.payload["real_orders_enabled"] is False
    assert appended.payload["real_money_enabled"] is False
    assert appended.payload["paper_only"] is True
    # decision (seq 0) + candidate (seq 1) + readiness (seq 2) live in the same chain.
    assert c.journal.entry_count == 3
    assert appended.prev_entry_digest == c.pce.entry_digest
    assert c.journal.verify_chain().accepted is True


# 2. journaled payload equals paper_sleeve_promotion_readiness_to_dict(readiness).
def test_appended_payload_equals_canonical_to_dict() -> None:
    c = _readied()
    appended = _append(c.journal, c.readiness, c.pce, c.candidate)
    assert appended.payload == paper_sleeve_promotion_readiness_to_dict(c.readiness)
    assert appended.payload["readiness_digest"] == c.readiness.readiness_digest
    assert appended.payload["promotion_candidate_journal_entry_digest"] == c.pce.entry_digest
    assert appended.payload["decision_journal_entry_digest"] == c.decision_entry.entry_digest


# 3. entry payload_digest / entry_digest are journal-computed 64-hex.
def test_entry_payload_digest_is_journal_hex64() -> None:
    c = _readied()
    appended = _append(c.journal, c.readiness, c.pce, c.candidate)
    assert _is_hex64(appended.payload_digest)
    assert _is_hex64(appended.entry_digest)


# 4. export/import round-trip accepts the additive PAPER_SLEEVE_PROMOTION_READINESS artifact type.
def test_serialization_round_trip_accepts_artifact_type() -> None:
    c = _readied()
    _append(c.journal, c.readiness, c.pce, c.candidate)
    data = evidence_journal_to_dict(c.journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=c.journal.entry_count, expected_head_digest=c.journal.head_digest
    )
    assert loaded.entry_count == 3
    assert loaded.verify_chain().accepted is True
    assert loaded.snapshot()[2].entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS


# 4b. blocked / insufficient readiness also journal (status flows verbatim).
@pytest.mark.parametrize(
    ("state", "status"),
    [
        (_blocked_state(), PaperSleevePromotionReadinessStatus.BLOCKED),
        (_insufficient_state(), PaperSleevePromotionReadinessStatus.INSUFFICIENT_EVIDENCE),
    ],
)
def test_blocked_and_insufficient_readiness_journal(state, status) -> None:
    c = _readied(state=state)
    assert c.readiness.status is status
    appended = _append(c.journal, c.readiness, c.pce, c.candidate)
    assert appended.payload["status"] == status.value
    assert c.journal.entry_count == 3


# 5. wrong journal type rejected.
def test_wrong_journal_type_rejected() -> None:
    c = _readied()
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        append_paper_sleeve_promotion_readiness_to_evidence_journal(
            "not-a-journal",  # type: ignore[arg-type]
            c.readiness,
            promotion_candidate_journal_entry=c.pce,
            candidate=c.candidate,
            correlation_id=_AUDIT_CORR,
        )
    assert "journal_malformed" in str(exc.value)


# 6. wrong readiness type rejected.
def test_wrong_readiness_type_rejected() -> None:
    c = _readied()
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        append_paper_sleeve_promotion_readiness_to_evidence_journal(
            c.journal,
            "not-a-readiness",  # type: ignore[arg-type]
            promotion_candidate_journal_entry=c.pce,
            candidate=c.candidate,
            correlation_id=_AUDIT_CORR,
        )
    assert "readiness_malformed" in str(exc.value)
    assert c.journal.entry_count == 2


# 7. wrong promotion_candidate_journal_entry type rejected.
def test_wrong_promotion_candidate_entry_type_rejected() -> None:
    c = _readied()
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        append_paper_sleeve_promotion_readiness_to_evidence_journal(
            c.journal,
            c.readiness,
            promotion_candidate_journal_entry="not-an-entry",  # type: ignore[arg-type]
            candidate=c.candidate,
            correlation_id=_AUDIT_CORR,
        )
    assert "promotion_candidate_entry_malformed" in str(exc.value)
    assert c.journal.entry_count == 2


# 8. wrong candidate type rejected.
def test_wrong_candidate_type_rejected() -> None:
    c = _readied()
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        append_paper_sleeve_promotion_readiness_to_evidence_journal(
            c.journal,
            c.readiness,
            promotion_candidate_journal_entry=c.pce,
            candidate="not-a-candidate",  # type: ignore[arg-type]
            correlation_id=_AUDIT_CORR,
        )
    assert "candidate_malformed" in str(exc.value)
    assert c.journal.entry_count == 2


# 9. forged readiness_digest rejected (self-digest re-proof).
def test_forged_readiness_digest_rejected() -> None:
    c = _readied()
    forged = replace(c.readiness, readiness_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, c.pce, c.candidate)
    assert "readiness_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 10. stale/resealed readiness (self-consistent but not what the journaled candidate yields) rejected by rebuild.
def test_resealed_readiness_rejected_by_rebuild() -> None:
    c = _readied()
    assert c.readiness.status is PaperSleevePromotionReadinessStatus.READY
    tampered = _reseal_readiness(replace(c.readiness, status=PaperSleevePromotionReadinessStatus.BLOCKED))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, tampered, c.pce, c.candidate)
    assert "readiness_not_reproducible" in str(exc.value)
    assert c.journal.entry_count == 2


# 11. promotion candidate journal entry not present in target journal rejected through rebuild. The target
# journal holds the same upstream decision (so the explicit anchor checks pass) but NOT the candidate entry.
def test_promotion_candidate_entry_not_in_journal_rejected_through_rebuild() -> None:
    c = _readied()
    other = EvidenceJournal()
    append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        other, c.decision, state=c.state, policy=c.policy, correlation_id=_DECISION_CORR
    )  # other holds the decision at the same digest, but not the candidate entry
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(other, c.readiness, c.pce, c.candidate)
    assert "readiness_not_reproducible" in str(exc.value)
    assert other.entry_count == 1


# 12. promotion candidate journal entry wrong artifact rejected through rebuild (coordinated forge: the
# readiness pretends a tick entry is its candidate anchor, but the rebuild rejects the wrong artifact type).
def test_promotion_candidate_entry_wrong_artifact_rejected_through_rebuild() -> None:
    c = _readied()
    tick_entry = c.journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_trade_tick_to_dict(_tick(tick_id="pce-wrong")),
        correlation_id="corr:tick",
    )
    forged = _reseal_readiness(
        replace(
            c.readiness,
            promotion_candidate_journal_entry_digest=tick_entry.entry_digest,
            promotion_candidate_payload_digest=tick_entry.payload_digest,
        )
    )
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, tick_entry, c.candidate)
    assert "readiness_not_reproducible" in str(exc.value)
    assert c.journal.entry_count == 3


# 13. supplied promotion candidate entry digest mismatch (vs the readiness anchor) rejected.
def test_supplied_promotion_candidate_entry_digest_mismatch_rejected() -> None:
    c = _readied()
    forged_pce = replace(c.pce, entry_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, c.readiness, forged_pce, c.candidate)
    assert "promotion_candidate_entry_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 14. supplied promotion candidate payload digest mismatch (vs the readiness anchor) rejected.
def test_supplied_promotion_candidate_payload_digest_mismatch_rejected() -> None:
    c = _readied()
    forged_pce = replace(c.pce, payload_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, c.readiness, forged_pce, c.candidate)
    assert "promotion_candidate_payload_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 15. upstream decision entry missing in the same journal rejected (coordinated forge of the decision anchor).
def test_upstream_decision_entry_missing_rejected() -> None:
    c = _readied()
    forged_candidate = _reseal_candidate(replace(c.candidate, journal_entry_digest=_BAD_DIGEST))
    forged_readiness = _reseal_readiness(replace(c.readiness, decision_journal_entry_digest=_BAD_DIGEST))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged_readiness, c.pce, forged_candidate)
    assert "decision_entry_not_in_journal" in str(exc.value)
    assert c.journal.entry_count == 2


# 16. upstream decision entry wrong artifact type rejected (decision anchor points at a tick entry).
def test_upstream_decision_entry_wrong_artifact_type_rejected() -> None:
    c = _readied()
    tick_entry = c.journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_trade_tick_to_dict(_tick(tick_id="upstream-wrong")),
        correlation_id="corr:tick",
    )
    forged_candidate = _reseal_candidate(replace(c.candidate, journal_entry_digest=tick_entry.entry_digest))
    forged_readiness = _reseal_readiness(replace(c.readiness, decision_journal_entry_digest=tick_entry.entry_digest))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged_readiness, c.pce, forged_candidate)
    assert "decision_entry_artifact_type_mismatch" in str(exc.value)
    assert c.journal.entry_count == 3


# 17. readiness promotion_candidate_journal_entry_digest mismatch (vs the supplied entry) rejected.
def test_readiness_promotion_candidate_entry_digest_mismatch_rejected() -> None:
    c = _readied()
    forged = _reseal_readiness(replace(c.readiness, promotion_candidate_journal_entry_digest=_BAD_DIGEST))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, c.pce, c.candidate)
    assert "promotion_candidate_entry_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 18. readiness promotion_candidate_payload_digest mismatch (vs the supplied entry) rejected.
def test_readiness_promotion_candidate_payload_digest_mismatch_rejected() -> None:
    c = _readied()
    forged = _reseal_readiness(replace(c.readiness, promotion_candidate_payload_digest=_BAD_DIGEST))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, c.pce, c.candidate)
    assert "promotion_candidate_payload_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 19. readiness decision_journal_entry_digest mismatch (vs the supplied candidate) rejected.
def test_readiness_decision_entry_digest_mismatch_rejected() -> None:
    c = _readied()
    forged = _reseal_readiness(replace(c.readiness, decision_journal_entry_digest=_BAD_DIGEST))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, c.pce, c.candidate)
    assert "decision_entry_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 20. readiness decision_journal_payload_digest mismatch (vs the supplied candidate) rejected.
def test_readiness_decision_payload_digest_mismatch_rejected() -> None:
    c = _readied()
    forged = _reseal_readiness(replace(c.readiness, decision_journal_payload_digest=_BAD_DIGEST))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, forged, c.pce, c.candidate)
    assert "decision_payload_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 2


# 21. unsafe readiness paper-safety triple rejected before append.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "readiness_not_paper_only"),
        ({"real_orders_enabled": True}, "readiness_real_orders_enabled"),
        ({"real_money_enabled": True}, "readiness_real_money_enabled"),
    ],
)
def test_unsafe_readiness_rejected(override: dict[str, bool], reason: str) -> None:
    c = _readied()
    tampered = _reseal_readiness(replace(c.readiness, **override))
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, tampered, c.pce, c.candidate)
    assert reason in str(exc.value)
    assert c.journal.entry_count == 2


# 22a. empty audit correlation_id rejected by the adapter before append.
def test_empty_audit_correlation_id_rejected() -> None:
    c = _readied()
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError) as exc:
        _append(c.journal, c.readiness, c.pce, c.candidate, correlation_id="   ")
    assert "correlation_id_invalid" in str(exc.value)
    assert c.journal.entry_count == 2


# 22b. forbidden token in the audit correlation_id fails closed through the journal guard; journal unchanged.
def test_forbidden_audit_correlation_token_fails_closed() -> None:
    c = _readied()
    with pytest.raises(EvidenceJournalError):
        _append(c.journal, c.readiness, c.pce, c.candidate, correlation_id="order_router_loop")
    assert c.journal.entry_count == 2


# 23. journal unchanged on a rejection even when the readiness already appended.
def test_journal_unchanged_on_rejection_mid_journal() -> None:
    c = _readied()
    _append(c.journal, c.readiness, c.pce, c.candidate, correlation_id="corr:audit-a")
    assert c.journal.entry_count == 3
    head_before = c.journal.head_digest
    forged = replace(c.readiness, readiness_digest=_BAD_DIGEST)
    with pytest.raises(PaperSleevePromotionReadinessJournalAdapterError):
        _append(c.journal, forged, c.pce, c.candidate, correlation_id="corr:audit-c")
    assert c.journal.entry_count == 3
    assert c.journal.head_digest == head_before


# 24. duplicate readiness payload replay fails closed through EvidenceJournal; journal unchanged.
def test_duplicate_readiness_payload_replay_fails_closed() -> None:
    c = _readied()
    _append(c.journal, c.readiness, c.pce, c.candidate, correlation_id="corr:audit-a")
    head_before = c.journal.head_digest
    with pytest.raises(EvidenceJournalError):
        _append(c.journal, c.readiness, c.pce, c.candidate, correlation_id="corr:audit-b")  # identical payload
    assert c.journal.entry_count == 3
    assert c.journal.head_digest == head_before


# 24b. safe market-data terms in readiness metadata remain allowed end-to-end.
@pytest.mark.parametrize("term", ["order_book", "order_flow", "limit_order_book"])
def test_market_data_terms_allowed(term: str) -> None:
    c = _readied(readiness_metadata={"market_data_source": term})
    appended = _append(c.journal, c.readiness, c.pce, c.candidate)
    assert appended.entry_type is EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS
    assert c.journal.entry_count == 3


# 25. no live/order/scheduler/connector/execution implementation surface (exact public API only).
def test_no_forbidden_implementation_surface() -> None:
    import crypto_core.audit.paper_sleeve_promotion_readiness_journal_adapter as mod

    assert set(mod.__all__) == {
        "PaperSleevePromotionReadinessJournalAdapterError",
        "append_paper_sleeve_promotion_readiness_to_evidence_journal",
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


# 26. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.audit.paper_sleeve_promotion_readiness_journal_adapter as mod

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
