"""Tests for the journal-anchored paper allocator intent draft read-model seam."""

from __future__ import annotations

import ast
from collections import namedtuple
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter import (
    append_paper_sleeve_promotion_candidate_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_promotion_readiness_journal_adapter import (
    append_paper_sleeve_promotion_readiness_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftError,
    PaperAllocatorIntentDraftStatus,
    build_paper_allocator_intent_draft,
    paper_allocator_intent_draft_digest,
    paper_allocator_intent_draft_to_dict,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import build_paper_sleeve_promotion_candidate
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
_READINESS_AUDIT_CORR = "corr:journal-readiness"
_DRAFT_CORR = "corr:draft"

_Chain = namedtuple("_Chain", "journal state policy decision decision_entry candidate pce readiness pre")


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


def _to_candidate(state=None):
    """Journal decision (seq 0) + promotion candidate (seq 1); return parts plus the (unjournaled) readiness."""
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
    readiness = build_paper_sleeve_promotion_readiness(journal, pce, candidate, correlation_id=_READINESS_CORR)
    return journal, state, policy, decision, decision_entry, candidate, pce, readiness


def _chain(state=None) -> _Chain:
    """Journal the full chain: decision (0) + candidate (1) + readiness (2). Returns all parts incl. the entry."""
    journal, state, policy, decision, decision_entry, candidate, pce, readiness = _to_candidate(state)
    pre = append_paper_sleeve_promotion_readiness_to_evidence_journal(
        journal,
        readiness,
        promotion_candidate_journal_entry=pce,
        candidate=candidate,
        correlation_id=_READINESS_AUDIT_CORR,
    )
    return _Chain(journal, state, policy, decision, decision_entry, candidate, pce, readiness, pre)


def _raw_append_readiness(journal, readiness, *, correlation_id: str = "corr:raw-readiness"):
    return journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS,
        paper_sleeve_promotion_readiness_to_dict(readiness),
        correlation_id=correlation_id,
    )


def _append_tick(journal, *, tick_id: str = "x"):
    return journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        paper_trade_tick_to_dict(_tick(tick_id=tick_id)),
        correlation_id="corr:tick",
    )


def _build_draft(journal, pre, readiness, *, correlation_id: str = _DRAFT_CORR, metadata=None):
    return build_paper_allocator_intent_draft(journal, pre, readiness, correlation_id=correlation_id, metadata=metadata)


def _reseal_readiness(readiness):
    return replace(readiness, readiness_digest=paper_sleeve_promotion_readiness_digest(readiness))


# 1. happy path: journaled READY readiness -> DRAFT_READY.
def test_journaled_ready_readiness_is_draft_ready() -> None:
    assert PaperAllocatorIntentDraftStatus("DRAFT_READY") is PaperAllocatorIntentDraftStatus.DRAFT_READY
    c = _chain()
    draft = _build_draft(c.journal, c.pre, c.readiness)
    assert isinstance(draft, PaperAllocatorIntentDraft)
    assert draft.status is PaperAllocatorIntentDraftStatus.DRAFT_READY
    assert draft.sleeve_id == c.readiness.sleeve_id
    assert draft.policy_id == c.readiness.policy_id
    assert draft.readiness_digest == c.readiness.readiness_digest
    assert draft.promotion_readiness_journal_entry_digest == c.pre.entry_digest
    assert draft.promotion_readiness_payload_digest == c.pre.payload_digest
    assert draft.promotion_candidate_journal_entry_digest == c.pce.entry_digest
    assert draft.decision_journal_entry_digest == c.decision_entry.entry_digest
    assert draft.correlation_id == _DRAFT_CORR
    assert draft.paper_only is True
    assert draft.real_orders_enabled is False
    assert draft.real_money_enabled is False
    assert _is_hex64(draft.draft_digest)
    # read-only: the journal is never appended to.
    assert c.journal.entry_count == 3


# 2. journaled BLOCKED readiness -> BLOCKED.
def test_journaled_blocked_readiness_is_blocked() -> None:
    c = _chain(state=_blocked_state())
    assert c.readiness.status is PaperSleevePromotionReadinessStatus.BLOCKED
    draft = _build_draft(c.journal, c.pre, c.readiness)
    assert draft.status is PaperAllocatorIntentDraftStatus.BLOCKED
    assert draft.blocked_count == 1
    assert c.journal.entry_count == 3


# 3. journaled INSUFFICIENT_EVIDENCE readiness -> INSUFFICIENT_EVIDENCE.
def test_journaled_insufficient_readiness_is_insufficient() -> None:
    c = _chain(state=_insufficient_state())
    assert c.readiness.status is PaperSleevePromotionReadinessStatus.INSUFFICIENT_EVIDENCE
    draft = _build_draft(c.journal, c.pre, c.readiness)
    assert draft.status is PaperAllocatorIntentDraftStatus.INSUFFICIENT_EVIDENCE
    assert draft.insufficient_count == 1
    assert c.journal.entry_count == 3


# 4. wrong journal type rejected.
def test_wrong_journal_type_rejected() -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        build_paper_allocator_intent_draft("not-a-journal", c.pre, c.readiness, correlation_id=_DRAFT_CORR)  # type: ignore[arg-type]
    assert "journal_malformed" in str(exc.value)


# 5. wrong readiness journal entry type rejected.
def test_wrong_readiness_entry_type_rejected() -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        build_paper_allocator_intent_draft(c.journal, "not-an-entry", c.readiness, correlation_id=_DRAFT_CORR)  # type: ignore[arg-type]
    assert "promotion_readiness_entry_malformed" in str(exc.value)
    assert c.journal.entry_count == 3


# 6. wrong readiness object type rejected.
def test_wrong_readiness_object_type_rejected() -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        build_paper_allocator_intent_draft(c.journal, c.pre, "not-a-readiness", correlation_id=_DRAFT_CORR)  # type: ignore[arg-type]
    assert "readiness_malformed" in str(exc.value)
    assert c.journal.entry_count == 3


# 7. readiness journal entry not present in target journal rejected.
def test_readiness_entry_not_in_journal_rejected() -> None:
    c = _chain()
    other_journal = EvidenceJournal()  # does NOT contain the readiness entry
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(other_journal, c.pre, c.readiness)
    assert "promotion_readiness_entry_not_in_journal" in str(exc.value)
    assert other_journal.entry_count == 0


# 8. readiness journal entry wrong artifact type rejected.
def test_readiness_entry_wrong_artifact_type_rejected() -> None:
    c = _chain()
    journal = EvidenceJournal()
    tick_entry = _append_tick(journal, tick_id="wrong-pre")
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, tick_entry, c.readiness)
    assert "promotion_readiness_entry_artifact_type_mismatch" in str(exc.value)
    assert journal.entry_count == 1


# 9. readiness journal entry self-digest mismatch rejected (supplied entry tampered, entry_digest intact).
def test_readiness_entry_self_digest_mismatch_rejected() -> None:
    c = _chain()
    forged_pre = replace(c.pre, prev_entry_digest=_BAD_DIGEST)  # entry_digest unchanged -> membership passes
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, forged_pre, c.readiness)
    assert "promotion_readiness_entry_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 3


# 10. readiness entry payload mismatch rejected (entry anchors a different readiness).
def test_readiness_entry_payload_mismatch_rejected() -> None:
    c = _chain()
    other_readiness = _reseal_readiness(replace(c.readiness, blockers=("synthetic-blocker",)))
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, other_readiness)
    assert "promotion_readiness_payload_mismatch" in str(exc.value)
    assert c.journal.entry_count == 3


# 11. readiness entry payload_digest mismatch rejected (payload matches, digest forged).
def test_readiness_entry_payload_digest_mismatch_rejected() -> None:
    c = _chain()
    forged_pre = replace(c.pre, payload_digest=_BAD_DIGEST)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, forged_pre, c.readiness)
    assert "promotion_readiness_payload_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 3


# 12. readiness.readiness_digest mismatch rejected.
def test_readiness_digest_mismatch_rejected() -> None:
    c = _chain()
    forged = replace(c.readiness, readiness_digest=_BAD_DIGEST)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, forged)
    assert "readiness_digest_mismatch" in str(exc.value)
    assert c.journal.entry_count == 3


# 13. readiness unsafe paper flag rejected.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "readiness_not_paper_only"),
        ({"real_orders_enabled": True}, "readiness_real_orders_enabled"),
        ({"real_money_enabled": True}, "readiness_real_money_enabled"),
    ],
)
def test_unsafe_readiness_paper_flag_rejected(override: dict[str, bool], reason: str) -> None:
    c = _chain()
    tampered = _reseal_readiness(replace(c.readiness, **override))
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, tampered)
    assert reason in str(exc.value)
    assert c.journal.entry_count == 3


# 14. missing promotion candidate anchor in same journal rejected.
def test_missing_promotion_candidate_anchor_rejected() -> None:
    journal, _state, _policy, _decision, _de, _candidate, _pce, readiness = _to_candidate()
    forged = _reseal_readiness(replace(readiness, promotion_candidate_journal_entry_digest=_BAD_DIGEST))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "promotion_candidate_anchor_not_in_journal" in str(exc.value)
    assert journal.entry_count == 3


# 15. promotion candidate anchor wrong artifact type rejected.
def test_promotion_candidate_anchor_wrong_artifact_type_rejected() -> None:
    journal, _state, _policy, _decision, _de, _candidate, _pce, readiness = _to_candidate()
    tick_entry = _append_tick(journal, tick_id="cand-anchor-wrong")
    forged = _reseal_readiness(replace(readiness, promotion_candidate_journal_entry_digest=tick_entry.entry_digest))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "promotion_candidate_anchor_artifact_type_mismatch" in str(exc.value)
    assert journal.entry_count == 4


# 16. missing upstream decision anchor in same journal rejected.
def test_missing_decision_anchor_rejected() -> None:
    journal, _state, _policy, _decision, _de, _candidate, _pce, readiness = _to_candidate()
    forged = _reseal_readiness(replace(readiness, decision_journal_entry_digest=_BAD_DIGEST))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "decision_anchor_not_in_journal" in str(exc.value)
    assert journal.entry_count == 3


# 17. upstream decision anchor wrong artifact type rejected.
def test_decision_anchor_wrong_artifact_type_rejected() -> None:
    journal, _state, _policy, _decision, _de, _candidate, _pce, readiness = _to_candidate()
    tick_entry = _append_tick(journal, tick_id="dec-anchor-wrong")
    forged = _reseal_readiness(replace(readiness, decision_journal_entry_digest=tick_entry.entry_digest))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "decision_anchor_artifact_type_mismatch" in str(exc.value)
    assert journal.entry_count == 4


# 17b (review P1). a forged readiness raw-appended via the public journal that keeps the BLOCKED candidate's
# counts but reseals its status as READY is rejected — status must be the verdict derived from the ANCHORED
# candidate, not the readiness's self-claim.
def test_forged_readiness_status_over_blocked_candidate_rejected() -> None:
    journal, _s, _p, _d, _de, _c, _pce, readiness = _to_candidate(_blocked_state())
    assert readiness.status is PaperSleevePromotionReadinessStatus.BLOCKED
    forged = _reseal_readiness(replace(readiness, status=PaperSleevePromotionReadinessStatus.READY))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "readiness_status_inconsistent" in str(exc.value)
    assert journal.entry_count == 3


# 17c (review P1). a forged readiness that reseals READY with forged counts (not the anchored BLOCKED candidate's)
# is rejected — counts must match the anchored candidate.
def test_forged_readiness_counts_over_blocked_candidate_rejected() -> None:
    journal, _s, _p, _d, _de, _c, _pce, readiness = _to_candidate(_blocked_state())
    forged = _reseal_readiness(
        replace(
            readiness,
            status=PaperSleevePromotionReadinessStatus.READY,
            eligible_count=1,
            blocked_count=0,
            insufficient_count=0,
        )
    )
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert "readiness_counts_mismatch" in str(exc.value)
    assert journal.entry_count == 3


# 17d (review P1). a forged readiness whose recorded provenance fields disagree with the anchored candidate /
# decision payloads is rejected (digest-boundary: the readiness must faithfully derive from its anchors).
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"candidate_digest": _BAD_DIGEST}, "readiness_candidate_digest_mismatch"),
        ({"promotion_candidate_payload_digest": _BAD_DIGEST}, "promotion_candidate_anchor_payload_digest_mismatch"),
        ({"sleeve_id": "other-sleeve"}, "readiness_identity_mismatch"),
        ({"policy_id": "other-policy"}, "readiness_identity_mismatch"),
        ({"blockers": ("synthetic-blocker",)}, "readiness_blockers_mismatch"),
        ({"decision_journal_payload_digest": _BAD_DIGEST}, "decision_anchor_payload_digest_mismatch"),
    ],
)
def test_forged_readiness_fields_vs_anchors_rejected(override: dict[str, object], reason: str) -> None:
    journal, _s, _p, _d, _de, _c, _pce, readiness = _to_candidate()
    forged = _reseal_readiness(replace(readiness, **override))
    pre = _raw_append_readiness(journal, forged)
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(journal, pre, forged)
    assert reason in str(exc.value)
    assert journal.entry_count == 3


# 18. wrong/empty/forbidden correlation_id or metadata rejected.
def test_empty_correlation_id_rejected() -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, c.readiness, correlation_id="   ")
    assert "correlation_id_invalid" in str(exc.value)
    assert c.journal.entry_count == 3


@pytest.mark.parametrize("correlation_id", ["order_router_loop", "live_execution", "bist_session"])
def test_forbidden_correlation_id_rejected(correlation_id: str) -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, c.readiness, correlation_id=correlation_id)
    assert "scope_violation" in str(exc.value)
    assert c.journal.entry_count == 3


@pytest.mark.parametrize("metadata", [{"note": "order_router"}, {"venue": "live_order"}, {"market": "bist-100"}])
def test_forbidden_metadata_rejected(metadata: dict[str, str]) -> None:
    c = _chain()
    with pytest.raises(PaperAllocatorIntentDraftError) as exc:
        _build_draft(c.journal, c.pre, c.readiness, metadata=metadata)
    assert "scope_violation" in str(exc.value)
    assert c.journal.entry_count == 3


def test_safe_market_data_metadata_allowed() -> None:
    c = _chain()
    draft = _build_draft(c.journal, c.pre, c.readiness, metadata={"market_data_source": "order_book"})
    assert draft.metadata == (("market_data_source", "order_book"),)
    assert c.journal.entry_count == 3


# 19. no mutation: journal entry_count / head_digest unchanged on every rejection path.
def test_journal_unchanged_on_all_rejection_paths() -> None:
    c = _chain()
    count_before = c.journal.entry_count
    head_before = c.journal.head_digest
    rejections = [
        lambda: _build_draft(c.journal, c.pre, replace(c.readiness, readiness_digest=_BAD_DIGEST)),
        lambda: _build_draft(c.journal, replace(c.pre, payload_digest=_BAD_DIGEST), c.readiness),
        lambda: _build_draft(c.journal, c.pre, c.readiness, correlation_id="   "),
        lambda: _build_draft(c.journal, c.pre, c.readiness, correlation_id="order_router"),
        lambda: _build_draft(c.journal, c.pre, _reseal_readiness(replace(c.readiness, real_orders_enabled=True))),
    ]
    for call in rejections:
        with pytest.raises(PaperAllocatorIntentDraftError):
            call()
    assert c.journal.entry_count == count_before
    assert c.journal.head_digest == head_before


# 20. to_dict / digest deterministic roundtrip.
def test_to_dict_and_digest_deterministic_roundtrip() -> None:
    c = _chain()
    draft = _build_draft(c.journal, c.pre, c.readiness)
    payload = paper_allocator_intent_draft_to_dict(draft)
    assert payload["draft_digest"] == draft.draft_digest
    assert paper_allocator_intent_draft_digest(draft) == draft.draft_digest
    c2 = _chain()
    draft2 = build_paper_allocator_intent_draft(c2.journal, c2.pre, c2.readiness, correlation_id=_DRAFT_CORR)
    assert draft2.draft_digest == draft.draft_digest
    assert paper_allocator_intent_draft_to_dict(draft2) == payload


# 21. payload carries the explicit non-execution negative attestations (all False).
def test_payload_contains_explicit_false_flags() -> None:
    c = _chain()
    payload = paper_allocator_intent_draft_to_dict(_build_draft(c.journal, c.pre, c.readiness))
    for flag in (
        "capital_reserved",
        "execution_authorized",
        "order_created",
        "fill_created",
        "position_mutated",
    ):
        assert flag in payload
        assert payload[flag] is False
    assert payload["real_orders_enabled"] is False
    assert payload["real_money_enabled"] is False
    assert payload["paper_only"] is True


# 22. no execution/live/order/PnL/position DATA fields in the draft payload (negative attestations are not data).
def test_no_execution_data_fields_in_payload() -> None:
    c = _chain()
    keys = set(paper_allocator_intent_draft_to_dict(_build_draft(c.journal, c.pre, c.readiness)).keys())
    banned = {
        "order_id",
        "order_ids",
        "venue_order_id",
        "fill_price",
        "avg_fill_price",
        "filled_quantity",
        "executed_quantity",
        "realized_pnl",
        "pnl",
        "position_qty",
        "position_size",
        "venue",
        "slippage",
        "notional_filled",
        "reserved_capital",
        "allocation",
    }
    assert keys.isdisjoint(banned)


# 23. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.validation.paper_allocator_intent_draft as mod

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
    import crypto_core.validation.paper_allocator_intent_draft as mod

    assert set(mod.__all__) == {
        "PaperAllocatorIntentDraft",
        "PaperAllocatorIntentDraftError",
        "PaperAllocatorIntentDraftStatus",
        "build_paper_allocator_intent_draft",
        "paper_allocator_intent_draft_digest",
        "paper_allocator_intent_draft_to_dict",
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
        "position",
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name
