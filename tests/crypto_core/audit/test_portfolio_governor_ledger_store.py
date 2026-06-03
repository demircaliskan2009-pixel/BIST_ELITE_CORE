"""Tests for Phase 16F — append-only paper governor ledger store.

Covers ``PortfolioGovernorLedgerStore``: an in-memory, append-only, deterministically-chained
repository for ``PortfolioGovernorLedgerEntry`` with fail-closed validation and immutable,
deterministic retrieval.

  1. Malformed / non-entry input rejects (fail-closed)
  2. Non-paper entry rejects
  3. Invalid digest fields reject
  4. Missing / malformed evidence refs reject
  5. Tampered entry (content != entry_digest) rejects
  6. First entry with a previous digest rejects
  7. Second entry without the required previous digest rejects
  8. Previous digest mismatch rejects
  9. Duplicate entry digest rejects
 10. Valid first + second append succeeds and the chain is ordered
 11. Lookup by entry digest / plan_id / correlation_id is deterministic
 12. Snapshot is an immutable tuple; external use cannot mutate the store
 13. Blocked and active entries both store correctly
 14. No order/live/venue/scheduler field leaks into stored entries
 15. Repeated same append sequence yields the same ordered digests

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16F.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerStatus,
    build_portfolio_governor_ledger_entry,
)
from crypto_core.audit.portfolio_governor_ledger_store import (
    PortfolioGovernorLedgerStore,
    PortfolioGovernorLedgerStoreError,
    _expected_entry_digest,
)
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import (
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.portfolio_allocation_projection import project_governed_allocation
from crypto_core.service.portfolio_governor_consumption import consume_portfolio_allocation
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_CORR = "corr:portfolio-governor-001"
_CAPITAL = 10_000.0
_HEX64 = "a" * 64


def _ready_plan(active=("micro-1", "micro-2"), caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:deadbeef",
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=active,
        pbo_allocation_caps=caps,
    )


def _allocated_directive(budget=1.0, capital_base=_CAPITAL):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(), risk, budget=budget))
    record = project_governed_allocation(view, capital_base=capital_base)
    return consume_portfolio_allocation(record)


def _blocked_directive():
    plan = PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    decision = build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})
    record = project_governed_allocation(govern_allocation_decision(decision), capital_base=_CAPITAL)
    return consume_portfolio_allocation(record)


def _entry(directive, *, previous=None, correlation_id=_CORR):
    return build_portfolio_governor_ledger_entry(
        directive, correlation_id=correlation_id, previous_entry_digest=previous
    )


def test_malformed_entry_rejects():
    store = PortfolioGovernorLedgerStore()
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append({"not": "an entry"})


def test_non_paper_entry_rejects():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    for bad in (
        replace(entry, real_orders_enabled=True),
        replace(entry, real_money_enabled=True),
        replace(entry, paper_only=False),
    ):
        with pytest.raises(PortfolioGovernorLedgerStoreError):
            store.append(bad)


def test_invalid_digest_fields_reject():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    for bad in (
        replace(entry, entry_digest="not-hex"),
        replace(entry, directive_digest="abc"),
        replace(entry, record_digest=""),
    ):
        with pytest.raises(PortfolioGovernorLedgerStoreError):
            store.append(bad)


def test_missing_evidence_refs_reject():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(replace(entry, evidence_refs=()))


def test_tampered_entry_rejects():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    # Content changed but entry_digest left stale -> integrity mismatch.
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(replace(entry, total_weight=entry.total_weight + 0.25))


def test_active_entry_with_mismatched_totals_rejected_even_with_consistent_digest():
    # Regression (Codex P2): an entry forged outside the builder with impossible totals but a
    # self-consistent recomputed digest must still be rejected on independent total re-validation.
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    forged = replace(entry, total_weight=999.0)
    forged = replace(forged, entry_digest=_expected_entry_digest(forged))
    # The digest is now consistent with the forged fields (the digest check would pass) ...
    assert forged.entry_digest == _expected_entry_digest(forged)
    # ... but the store rejects it because the totals no longer match the targets / budget.
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(forged)


def test_blocked_entry_with_nonzero_totals_rejected_even_with_consistent_digest():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_blocked_directive())
    forged = replace(entry, total_weight=5.0)
    forged = replace(forged, entry_digest=_expected_entry_digest(forged))
    assert forged.entry_digest == _expected_entry_digest(forged)
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(forged)


def test_first_entry_with_previous_digest_rejects():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive(), previous=_HEX64)
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(entry)


def test_second_entry_without_previous_digest_rejects():
    store = PortfolioGovernorLedgerStore()
    store.append(_entry(_allocated_directive()))
    orphan = _entry(_blocked_directive())  # previous=None while store is non-empty
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(orphan)


def test_previous_digest_mismatch_rejects():
    store = PortfolioGovernorLedgerStore()
    store.append(_entry(_allocated_directive()))
    wrong = _entry(_blocked_directive(), previous=_HEX64)
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(wrong)


def test_duplicate_entry_digest_rejects():
    store = PortfolioGovernorLedgerStore()
    entry = _entry(_allocated_directive())
    store.append(entry)
    with pytest.raises(PortfolioGovernorLedgerStoreError):
        store.append(entry)


def test_valid_chain_appends_in_order():
    store = PortfolioGovernorLedgerStore()
    first = _entry(_allocated_directive())
    store.append(first)
    second = _entry(_blocked_directive(), previous=first.entry_digest)
    store.append(second)
    snapshot = store.snapshot()
    assert snapshot == (first, second)
    assert snapshot[1].previous_entry_digest == snapshot[0].entry_digest
    assert store.head_digest() == second.entry_digest
    assert len(store) == 2


def test_deterministic_lookup():
    store = PortfolioGovernorLedgerStore()
    active = _entry(_allocated_directive())
    store.append(active)
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    store.append(blocked)

    assert store.get_by_entry_digest(active.entry_digest) is active
    assert store.get_by_entry_digest("f" * 64) is None
    assert store.find_by_plan_id("paper-shadow-activation:deadbeef") == (active,)
    assert store.find_by_plan_id("paper-shadow-activation:blocked") == (blocked,)
    assert store.find_by_correlation_id(_CORR) == (active, blocked)
    assert store.find_by_correlation_id("corr:none") == ()


def test_lookup_rejects_blank_query():
    store = PortfolioGovernorLedgerStore()
    for call in (
        lambda: store.get_by_entry_digest(""),
        lambda: store.find_by_plan_id(""),
        lambda: store.find_by_correlation_id(""),
    ):
        with pytest.raises(PortfolioGovernorLedgerStoreError):
            call()


def test_snapshot_is_immutable_and_isolated():
    store = PortfolioGovernorLedgerStore()
    store.append(_entry(_allocated_directive()))
    snapshot = store.snapshot()
    assert isinstance(snapshot, tuple)
    # Appending more does not retroactively change a previously taken snapshot.
    chained = _entry(_blocked_directive(), previous=snapshot[0].entry_digest)
    store.append(chained)
    assert len(snapshot) == 1
    assert len(store.snapshot()) == 2


def test_blocked_and_active_entries_both_store():
    store = PortfolioGovernorLedgerStore()
    active = _entry(_allocated_directive())
    store.append(active)
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    store.append(blocked)
    statuses = [entry.status for entry in store.snapshot()]
    assert statuses == [
        PortfolioGovernorLedgerStatus.RECORDED_ACTIVE,
        PortfolioGovernorLedgerStatus.RECORDED_BLOCKED,
    ]


def test_no_order_or_live_fields_in_stored_entries():
    store = PortfolioGovernorLedgerStore()
    store.append(_entry(_allocated_directive()))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    for entry in store.snapshot():
        assert {field.name for field in fields(entry)}.isdisjoint(forbidden)
        for target in entry.targets:
            assert {field.name for field in fields(target)}.isdisjoint(forbidden)


def test_repeated_append_sequence_is_deterministic():
    def _build_store():
        store = PortfolioGovernorLedgerStore()
        first = _entry(_allocated_directive())
        store.append(first)
        store.append(_entry(_blocked_directive(), previous=first.entry_digest))
        return store

    digests_a = [entry.entry_digest for entry in _build_store().snapshot()]
    digests_b = [entry.entry_digest for entry in _build_store().snapshot()]
    assert digests_a == digests_b
