"""Tests for the deterministic, paper-only paper sleeve intent ledger."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal, EvidenceJournalEntry
from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveIntentLedgerError,
    PaperSleeveIntentStatus,
    PaperSleeveTransition,
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
    paper_sleeve_intent_record_digest,
    paper_sleeve_intent_record_to_dict,
    paper_sleeve_state_digest,
    paper_sleeve_state_to_dict,
    paper_sleeve_transition_digest,
    paper_sleeve_transition_to_dict,
)
from crypto_core.validation.paper_trade_tick import (
    PaperTradeTickStatus,
    build_paper_trade_tick,
    paper_trade_tick_digest,
    paper_trade_tick_to_dict,
)

_VALID_DIGEST = "f" * 64
_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "paper_sleeve_intent_ledger.py"
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _build_tick(**overrides: object):
    base: dict[str, object] = {
        "tick_id": "tick-1",
        "action": "BUY",
        "intent_type": "LIMIT",
        "instrument_id": "BTC-USD",
        "quantity": "1.5",
        "strategy_id": "momentum-1",
        "run_plan_id": "run-1",
        "upstream_report_digest": _VALID_DIGEST,
        "correlation_id": "corr-1",
        "limit_price": "20000.5",
    }
    base.update(overrides)
    return build_paper_trade_tick(**base)


def _reseal_tick(tick):
    return replace(tick, paper_trade_tick_digest=paper_trade_tick_digest(tick))


def _state():
    return build_initial_paper_sleeve_state(sleeve_id="sleeve-1", correlation_id="corr:sleeve-1")


def _journal_entry(tick, correlation_id: str = "corr:journal-1") -> EvidenceJournalEntry:
    journal = EvidenceJournal()
    return journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id=correlation_id
    )


# 1. initial sleeve state builds with deterministic digest.
def test_initial_state_deterministic_digest() -> None:
    first = build_initial_paper_sleeve_state(sleeve_id="sleeve-1", correlation_id="corr:s")
    second = build_initial_paper_sleeve_state(sleeve_id="sleeve-1", correlation_id="corr:s")
    assert first.record_count == 0
    assert first.records == ()
    assert _is_hex64(first.state_digest)
    assert first.state_digest == second.state_digest
    assert paper_sleeve_state_digest(first) == first.state_digest
    assert first.paper_only is True
    assert first.real_orders_enabled is False
    assert first.real_money_enabled is False


# 2. accepted PaperTradeTick records into sleeve ledger and returns a new state.
def test_accepted_tick_records() -> None:
    state = _state()
    tick = _build_tick()
    transition = apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:apply-1")
    assert isinstance(transition, PaperSleeveTransition)
    to_state = transition.to_state
    assert to_state.record_count == 1
    assert to_state.recorded_count == 1
    assert transition.intent_status is PaperSleeveIntentStatus.RECORDED
    assert transition.record.tick_status == "ACCEPTED"
    assert transition.record.paper_trade_tick_digest == tick.paper_trade_tick_digest
    assert transition.from_state_digest == state.state_digest
    assert transition.to_state_digest == to_state.state_digest


# 3. original state remains unchanged.
def test_original_state_unchanged() -> None:
    state = _state()
    before = state.state_digest
    apply_paper_trade_tick_to_sleeve_state(state, _build_tick(), correlation_id="corr:apply")
    assert state.record_count == 0
    assert state.records == ()
    assert state.state_digest == before


# 4. record payload references tick digest and status.
def test_record_references_tick_digest_and_status() -> None:
    tick = _build_tick()
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a")
    payload = paper_sleeve_intent_record_to_dict(transition.record)
    assert payload["paper_trade_tick_digest"] == tick.paper_trade_tick_digest
    assert payload["intent_digest"] == tick.intent_digest
    assert payload["tick_status"] == "ACCEPTED"
    assert payload["intent_status"] == "RECORDED"
    assert payload["tick_id"] == tick.tick_id


# 5. record/state/transition digests re-prove.
def test_digests_reprove() -> None:
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), _build_tick(), correlation_id="corr:a")
    assert paper_sleeve_intent_record_digest(transition.record) == transition.record.record_digest
    assert paper_sleeve_state_digest(transition.to_state) == transition.to_state.state_digest
    assert paper_sleeve_transition_digest(transition) == transition.transition_digest
    assert _is_hex64(transition.record.record_digest)
    assert _is_hex64(transition.to_state.state_digest)


# 6. duplicate tick digest fails closed; no unsafe state change.
def test_duplicate_tick_digest_fails_closed() -> None:
    tick = _build_tick()
    first = apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:1")
    state2 = first.to_state
    before = state2.state_digest
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state2, tick, correlation_id="corr:2")
    assert "duplicate_tick_digest" in str(exc.value)
    assert state2.record_count == 1
    assert state2.state_digest == before


# 7. forged tick digest rejected before state change.
def test_forged_tick_digest_rejected() -> None:
    tick = replace(_build_tick(), paper_trade_tick_digest="0" * 64)
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:a")
    assert "tick_digest_mismatch" in str(exc.value)
    assert state.record_count == 0


# 7b. a tampered+resealed tick (stale verdict/intent digest) is rejected by the re-render re-proof.
def test_resealed_tampered_tick_rejected_by_rerender() -> None:
    tampered = _reseal_tick(replace(_build_tick(), quantity="0"))
    assert tampered.status is PaperTradeTickStatus.ACCEPTED  # stale verdict, internally consistent
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tampered, correlation_id="corr:a")
    assert "tick_not_reproducible" in str(exc.value)
    assert state.record_count == 0


# 8. paper_only=False / real_orders_enabled=True / real_money_enabled=True rejected.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "tick_not_paper_only"),
        ({"real_orders_enabled": True}, "tick_real_orders_enabled"),
        ({"real_money_enabled": True}, "tick_real_money_enabled"),
    ],
)
def test_paper_safety_triple_rejected(override: dict[str, bool], reason: str) -> None:
    tick = _reseal_tick(replace(_build_tick(), **override))
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:a")
    assert reason in str(exc.value)
    assert state.record_count == 0


# 9. ACCEPTED with accepted=False and REJECTED with accepted=True rejected.
def test_accepted_status_with_accepted_false_rejected() -> None:
    tick = _reseal_tick(replace(_build_tick(), accepted=False))
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a")
    assert "tick_status_accepted_mismatch" in str(exc.value)


def test_rejected_status_with_accepted_true_rejected() -> None:
    tick = _reseal_tick(replace(_build_tick(quantity="0"), accepted=True))
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a")
    assert "tick_status_accepted_mismatch" in str(exc.value)


# 10. malformed tick internals do not leak raw exceptions.
def test_malformed_tick_internals_no_raw_exception() -> None:
    tick = replace(_build_tick(), metadata=123)
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:a")
    assert "tick_malformed" in str(exc.value)
    assert state.record_count == 0


# 11. optional EvidenceJournalEntry binding succeeds for a PAPER_TRADE_TICK entry.
def test_journal_entry_binding_succeeds() -> None:
    tick = _build_tick()
    entry = _journal_entry(tick)
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a", journal_entry=entry)
    assert transition.record.journal_bound is True
    assert transition.record.journal_payload_digest == entry.payload_digest
    assert _is_hex64(transition.record.journal_payload_digest)


# 12. wrong artifact type fails if EvidenceJournalEntry is used.
def test_journal_entry_wrong_artifact_type_fails() -> None:
    tick = _build_tick()
    journal = EvidenceJournal()
    entry = journal.append(
        EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT, paper_trade_tick_to_dict(tick), correlation_id="corr:j"
    )
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:a", journal_entry=entry)
    assert "journal_entry_artifact_type_mismatch" in str(exc.value)
    assert state.record_count == 0


# 13. payload mismatch between journal entry and tick fails.
def test_journal_entry_payload_mismatch_fails() -> None:
    tick = _build_tick()
    entry = _journal_entry(_build_tick(action="SELL"))  # entry for a different tick
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(state, tick, correlation_id="corr:a", journal_entry=entry)
    assert "journal_entry_payload_mismatch" in str(exc.value)
    assert state.record_count == 0


# 14. rejected tick can be recorded as a non-executable audit record.
def test_rejected_tick_recorded_as_audit_record() -> None:
    tick = _build_tick(quantity="0")  # quantity_not_positive -> REJECTED
    assert tick.status is PaperTradeTickStatus.REJECTED
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a")
    assert transition.intent_status is PaperSleeveIntentStatus.REJECTED
    assert transition.record.tick_status == "REJECTED"
    assert transition.record.accepted is False
    assert transition.to_state.record_count == 1
    assert transition.to_state.recorded_count == 0


# 15. insufficient evidence tick can be recorded as a non-executable audit record.
def test_insufficient_evidence_tick_recorded_as_audit_record() -> None:
    tick = _build_tick(upstream_report_digest="")  # INSUFFICIENT_EVIDENCE
    assert tick.status is PaperTradeTickStatus.INSUFFICIENT_EVIDENCE
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), tick, correlation_id="corr:a")
    assert transition.intent_status is PaperSleeveIntentStatus.INSUFFICIENT_EVIDENCE
    assert transition.to_state.recorded_count == 0
    assert transition.to_state.record_count == 1


# 16. forbidden metadata/correlation/sleeve ids fail closed.
def test_forbidden_sleeve_id_fails_closed() -> None:
    with pytest.raises(PaperSleeveIntentLedgerError):
        build_initial_paper_sleeve_state(sleeve_id="order_router_sleeve", correlation_id="corr:s")


def test_forbidden_correlation_in_apply_fails_closed() -> None:
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError):
        apply_paper_trade_tick_to_sleeve_state(state, _build_tick(), correlation_id="scheduler_loop")
    assert state.record_count == 0


@pytest.mark.parametrize("token", ["live_order", "order_router", "scheduler", "connector_ready", "shadow", "bist"])
def test_forbidden_metadata_in_apply_fails_closed(token: str) -> None:
    state = _state()
    with pytest.raises(PaperSleeveIntentLedgerError):
        apply_paper_trade_tick_to_sleeve_state(state, _build_tick(), correlation_id="corr:a", metadata={"note": token})
    assert state.record_count == 0


# 17. market-data safe terms remain allowed.
def test_market_data_terms_allowed() -> None:
    state = build_initial_paper_sleeve_state(
        sleeve_id="sleeve-1", correlation_id="corr:s", metadata={"src": "order_book"}
    )
    transition = apply_paper_trade_tick_to_sleeve_state(
        state, _build_tick(), correlation_id="corr:a", metadata={"feed": "order_flow"}
    )
    assert transition.to_state.record_count == 1
    assert transition.record.metadata == (("feed", "order_flow"),)


# 18. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
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


# 19. no live/order/scheduler/connector/BIST implementation surface (public API names).
def test_no_forbidden_surface() -> None:
    import crypto_core.validation.paper_sleeve_intent_ledger as mod

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


# 20. no fill/PnL/execution fields are present.
def test_no_execution_fields() -> None:
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), _build_tick(), correlation_id="corr:a")
    record_keys = set(paper_sleeve_intent_record_to_dict(transition.record).keys())
    state_keys = set(paper_sleeve_state_to_dict(transition.to_state).keys())
    transition_keys = set(paper_sleeve_transition_to_dict(transition).keys())
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
    assert record_keys.isdisjoint(banned)
    assert state_keys.isdisjoint(banned)
    assert transition_keys.isdisjoint(banned)


# 21. serialization round-trip: serializers are JSON-stable and digests re-prove.
def test_serialization_json_roundtrip() -> None:
    transition = apply_paper_trade_tick_to_sleeve_state(_state(), _build_tick(), correlation_id="corr:a")
    state_dict = paper_sleeve_state_to_dict(transition.to_state)
    reloaded = json.loads(
        json.dumps(state_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    )
    assert reloaded == state_dict
    assert paper_sleeve_state_digest(transition.to_state) == transition.to_state.state_digest
    json.dumps(paper_sleeve_transition_to_dict(transition))
    json.dumps(paper_sleeve_intent_record_to_dict(transition.record))


# 22. changing any material state field changes the digest.
def test_material_state_field_change_changes_digest() -> None:
    state = _state()
    first = apply_paper_trade_tick_to_sleeve_state(state, _build_tick(), correlation_id="corr:a")
    second = apply_paper_trade_tick_to_sleeve_state(state, _build_tick(action="SELL"), correlation_id="corr:a")
    assert first.to_state.state_digest != second.to_state.state_digest
    tampered = replace(first.to_state, sleeve_id="sleeve-2")
    assert paper_sleeve_state_digest(tampered) != tampered.state_digest


# 22b. a tampered (resealed-inconsistent) incoming state is rejected before any record is appended.
def test_inconsistent_incoming_state_rejected() -> None:
    state = _state()
    forged = replace(state, record_count=5)  # count disagrees with empty records, self-digest stale
    with pytest.raises(PaperSleeveIntentLedgerError) as exc:
        apply_paper_trade_tick_to_sleeve_state(forged, _build_tick(), correlation_id="corr:a")
    assert "state_digest_mismatch" in str(exc.value)
