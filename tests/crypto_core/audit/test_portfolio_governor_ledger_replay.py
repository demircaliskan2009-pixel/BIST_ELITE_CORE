"""Tests for Phase 16G — deterministic paper governor ledger replay.

Covers ``replay_portfolio_governor_ledger``: projecting the append-only
``PortfolioGovernorLedgerStore`` (or an ordered entry tuple) into a deterministic, immutable
paper-governor lifecycle replay snapshot.

  1. Empty source replay is deterministic and safe
  2. Valid active+blocked chain replays in order with correct counts/head/totals
  3. Store source and equivalent tuple source produce identical replays
  4. Latest governor state per plan_id is deterministic (last occurrence wins)
  5. Broken previous_entry_digest chain rejects (fail-closed)
  6. Duplicate entry_digest rejects (fail-closed)
  7. Tampered / non-canonical entry rejects (fail-closed)
  8. Malformed source / non-entry element rejects (fail-closed)
  9. Snapshot/replay output is immutable
 10. Repeated replay yields identical digest/output
 11. No order/live/venue/scheduler field leaks

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16G.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerStatus,
    build_portfolio_governor_ledger_entry,
)
from crypto_core.audit.portfolio_governor_ledger_replay import (
    PortfolioGovernorLedgerReplayError,
    portfolio_governor_ledger_replay_to_dict,
    replay_portfolio_governor_ledger,
)
from crypto_core.audit.portfolio_governor_ledger_store import (
    PortfolioGovernorLedgerStore,
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


def _active_blocked_chain():
    active = _entry(_allocated_directive())
    blocked = _entry(_blocked_directive(), previous=active.entry_digest)
    return active, blocked


def test_empty_source_replay_is_safe_and_deterministic():
    first = replay_portfolio_governor_ledger(PortfolioGovernorLedgerStore())
    second = replay_portfolio_governor_ledger(())
    assert first.entry_count == 0
    assert first.active_count == 0
    assert first.blocked_count == 0
    assert first.head_digest is None
    assert first.ordered_entry_digests == ()
    assert first.latest_by_plan_id == ()
    assert first.total_active_weight == 0.0
    assert first.total_active_notional == 0.0
    assert first == second
    assert first.replay_digest == second.replay_digest
    assert len(first.replay_digest) == 64


def test_valid_chain_replays_in_order():
    active, blocked = _active_blocked_chain()
    store = PortfolioGovernorLedgerStore()
    store.append(active)
    store.append(blocked)
    replay = replay_portfolio_governor_ledger(store)
    assert replay.entry_count == 2
    assert replay.active_count == 1
    assert replay.blocked_count == 1
    assert replay.head_digest == blocked.entry_digest
    assert replay.ordered_entry_digests == (active.entry_digest, blocked.entry_digest)
    plans = {state.plan_id: state for state in replay.latest_by_plan_id}
    assert plans["paper-shadow-activation:deadbeef"].status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
    assert plans["paper-shadow-activation:blocked"].status == PortfolioGovernorLedgerStatus.RECORDED_BLOCKED
    # Only the active plan's latest totals contribute.
    assert replay.total_active_weight == active.total_weight
    assert abs(replay.total_active_notional - active.total_notional) < 1e-9


def test_store_and_tuple_sources_match():
    active, blocked = _active_blocked_chain()
    store = PortfolioGovernorLedgerStore()
    store.append(active)
    store.append(blocked)
    from_store = replay_portfolio_governor_ledger(store)
    from_tuple = replay_portfolio_governor_ledger((active, blocked))
    assert from_store == from_tuple
    assert from_store.replay_digest == from_tuple.replay_digest


def test_latest_by_plan_id_last_occurrence_wins():
    first = _entry(_allocated_directive())
    second = _entry(_allocated_directive(), previous=first.entry_digest)
    assert first.entry_digest != second.entry_digest  # same plan, different chain position
    replay = replay_portfolio_governor_ledger((first, second))
    plans = {state.plan_id: state for state in replay.latest_by_plan_id}
    assert plans["paper-shadow-activation:deadbeef"].entry_digest == second.entry_digest
    assert replay.head_digest == second.entry_digest


def test_broken_chain_rejects():
    active = _entry(_allocated_directive())
    orphan = _entry(_blocked_directive(), previous=_HEX64)  # wrong previous digest
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        replay_portfolio_governor_ledger((active, orphan))


def test_duplicate_entry_digest_rejects():
    active = _entry(_allocated_directive())
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        replay_portfolio_governor_ledger((active, active))


def test_tampered_entry_rejects():
    active = _entry(_allocated_directive())
    # Self-consistent digest but impossible totals -> store integrity rejects -> wrapped replay error.
    forged = replace(active, total_weight=999.0)
    forged = replace(forged, entry_digest=_expected_entry_digest(forged))
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        replay_portfolio_governor_ledger((forged,))


def test_malformed_source_rejects():
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        replay_portfolio_governor_ledger({"not": "a source"})


def test_non_entry_element_rejects():
    with pytest.raises(PortfolioGovernorLedgerReplayError):
        replay_portfolio_governor_ledger(("not-an-entry",))


def test_replay_output_is_immutable():
    active, blocked = _active_blocked_chain()
    replay = replay_portfolio_governor_ledger((active, blocked))
    assert isinstance(replay.ordered_entry_digests, tuple)
    assert isinstance(replay.latest_by_plan_id, tuple)
    with pytest.raises((AttributeError, TypeError)):
        replay.entry_count = 5  # type: ignore[misc]


def test_repeated_replay_is_deterministic():
    active, blocked = _active_blocked_chain()
    first = replay_portfolio_governor_ledger((active, blocked))
    second = replay_portfolio_governor_ledger((active, blocked))
    assert first == second
    assert first.replay_digest == second.replay_digest


def test_no_order_or_live_fields_leak():
    active, blocked = _active_blocked_chain()
    replay = replay_portfolio_governor_ledger((active, blocked))
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(replay)}.isdisjoint(forbidden)
    assert {field.name for field in fields(replay.latest_by_plan_id[0])}.isdisjoint(forbidden)
    assert replay.paper_only is True
    assert replay.real_orders_enabled is False
    assert replay.real_money_enabled is False
    payload = portfolio_governor_ledger_replay_to_dict(replay)
    assert payload["schema_version"] == "portfolio-governor-ledger-replay.v1"
    assert set(payload).isdisjoint(forbidden)
