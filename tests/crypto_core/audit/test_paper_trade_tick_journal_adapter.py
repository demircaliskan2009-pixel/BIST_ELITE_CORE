"""Tests for the PaperTradeTick -> EvidenceJournal audit bridge."""

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
from crypto_core.audit.paper_trade_tick_journal_adapter import (
    PaperTradeTickJournalAdapterError,
    append_paper_trade_tick_to_evidence_journal,
)
from crypto_core.validation.paper_trade_tick import (
    PaperTradeTick,
    PaperTradeTickStatus,
    build_paper_trade_tick,
    paper_trade_tick_digest,
    paper_trade_tick_to_dict,
)

_VALID_DIGEST = "f" * 64


def _build_tick(**overrides: object) -> PaperTradeTick:
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


def _reseal_tick(tick: PaperTradeTick) -> PaperTradeTick:
    # Recompute the self-digest over the (tampered) fields so the bridge's digest re-proof passes and the
    # later paper-safety / status checks are exercised in isolation.
    return replace(tick, paper_trade_tick_digest=paper_trade_tick_digest(tick))


def _append(
    journal: EvidenceJournal, tick: PaperTradeTick, correlation_id: str = "corr:journal-1"
) -> EvidenceJournalEntry:
    return append_paper_trade_tick_to_evidence_journal(journal, tick, correlation_id=correlation_id)


# 1 / 20. PAPER_TRADE_TICK exists and round-trips through journal serialization/load.
def test_artifact_type_exists_and_round_trips() -> None:
    assert EvidenceArtifactType("PAPER_TRADE_TICK") is EvidenceArtifactType.PAPER_TRADE_TICK
    tick = _build_tick()
    journal = EvidenceJournal()
    _append(journal, tick)
    data = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=journal.entry_count, expected_head_digest=journal.head_digest
    )
    assert loaded.entry_count == 1
    assert loaded.verify_chain().accepted is True
    assert loaded.snapshot()[0].entry_type is EvidenceArtifactType.PAPER_TRADE_TICK


# 2. valid ACCEPTED tick appends one PAPER_TRADE_TICK entry.
def test_accepted_tick_appends_one_entry() -> None:
    tick = _build_tick()
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    journal = EvidenceJournal()
    entry = _append(journal, tick)
    assert isinstance(entry, EvidenceJournalEntry)
    assert entry.entry_type is EvidenceArtifactType.PAPER_TRADE_TICK
    assert entry.payload["real_orders_enabled"] is False
    assert entry.payload["real_money_enabled"] is False
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 3. valid REJECTED tick appends under PAPER_TRADE_TICK (benign rejection reason).
def test_rejected_tick_appends() -> None:
    tick = _build_tick(quantity="0")  # quantity_not_positive -> REJECTED
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert tick.accepted is False
    journal = EvidenceJournal()
    entry = _append(journal, tick, correlation_id="corr:journal-rej")
    assert entry.entry_type is EvidenceArtifactType.PAPER_TRADE_TICK
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 4. valid INSUFFICIENT_EVIDENCE tick appends under PAPER_TRADE_TICK.
def test_insufficient_evidence_tick_appends() -> None:
    tick = _build_tick(upstream_report_digest="")
    assert tick.status is PaperTradeTickStatus.INSUFFICIENT_EVIDENCE
    assert tick.accepted is False
    journal = EvidenceJournal()
    entry = _append(journal, tick, correlation_id="corr:journal-ins")
    assert entry.entry_type is EvidenceArtifactType.PAPER_TRADE_TICK
    assert journal.entry_count == 1


# 5. appended payload equals paper_trade_tick_to_dict(tick).
def test_appended_payload_equals_canonical_to_dict() -> None:
    tick = _build_tick()
    journal = EvidenceJournal()
    entry = _append(journal, tick)
    assert entry.payload == paper_trade_tick_to_dict(tick)
    assert entry.payload["paper_trade_tick_digest"] == tick.paper_trade_tick_digest


# 6. journal.verify_chain() accepted after append; payload digest deterministic across journals.
def test_verify_chain_accepted_and_digest_deterministic() -> None:
    first_journal = EvidenceJournal()
    second_journal = EvidenceJournal()
    first = _append(first_journal, _build_tick())
    second = _append(second_journal, _build_tick())
    assert first.payload_digest == second.payload_digest
    assert first_journal.verify_chain().accepted is True
    assert second_journal.verify_chain().accepted is True


# 7. duplicate payload replay fails closed and journal unchanged.
def test_duplicate_payload_replay_fails_closed_and_journal_unchanged() -> None:
    tick = _build_tick()
    journal = EvidenceJournal()
    _append(journal, tick, correlation_id="corr:a")
    head_before = journal.head_digest
    with pytest.raises(EvidenceJournalError):
        _append(journal, tick, correlation_id="corr:b")  # identical payload -> payload_digest_replay
    assert journal.entry_count == 1
    assert journal.head_digest == head_before


# 8. forged paper_trade_tick_digest fails before append; journal unchanged.
def test_forged_digest_fails_before_append() -> None:
    tick = replace(_build_tick(), paper_trade_tick_digest="0" * 64)
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, tick)
    assert "paper_trade_tick_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0
    assert journal.head_digest is None


# 9. schema_version tamper fails before append; journal unchanged.
def test_forged_schema_version_fails_before_append() -> None:
    tick = replace(_build_tick(), schema_version="evil")
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, tick)
    assert "tick_schema_version_unexpected" in str(exc.value)
    assert journal.entry_count == 0


# 10. paper_only=False / real_orders_enabled=True / real_money_enabled=True fail before append, unchanged.
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"paper_only": False}, "tick_not_paper_only"),
        ({"real_orders_enabled": True}, "tick_real_orders_enabled"),
        ({"real_money_enabled": True}, "tick_real_money_enabled"),
    ],
)
def test_resealed_non_paper_tick_rejected_before_append(override: dict[str, bool], reason: str) -> None:
    sealed = _reseal_tick(replace(_build_tick(), **override))
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, sealed)
    assert reason in str(exc.value)
    assert journal.entry_count == 0
    assert journal.head_digest is None


@pytest.mark.parametrize(
    "override",
    [{"paper_only": False}, {"real_orders_enabled": True}, {"real_money_enabled": True}],
)
def test_stale_digest_non_paper_tick_rejected_before_append(override: dict[str, bool]) -> None:
    # without resealing, the digest re-proof already rejects (defense in depth)
    stale = replace(_build_tick(), **override)
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, stale)
    assert "paper_trade_tick_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 11. ACCEPTED with accepted=False / non-ACCEPTED with accepted=True fail before append.
def test_accepted_status_with_accepted_false_rejected() -> None:
    tampered = _reseal_tick(replace(_build_tick(), accepted=False))
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, tampered)
    assert "tick_status_accepted_mismatch" in str(exc.value)
    assert journal.entry_count == 0


def test_rejected_status_with_accepted_true_rejected() -> None:
    tampered = _reseal_tick(replace(_build_tick(quantity="0"), accepted=True))
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, tampered)
    assert "tick_status_accepted_mismatch" in str(exc.value)
    assert journal.entry_count == 0


# 12. wrong journal/tick types raise bridge Error.
def test_wrong_types_raise_bridge_error() -> None:
    with pytest.raises(PaperTradeTickJournalAdapterError):
        _append("not-a-journal", _build_tick())  # type: ignore[arg-type]
    with pytest.raises(PaperTradeTickJournalAdapterError):
        _append(EvidenceJournal(), {"not": "a-tick"})  # type: ignore[arg-type]
    with pytest.raises(PaperTradeTickJournalAdapterError):
        _append(EvidenceJournal(), _build_tick(), correlation_id="")


# 13. malformed direct-constructed tick internals do not leak raw exceptions.
def test_malformed_tick_internals_raise_bridge_error_not_raw() -> None:
    tick = replace(_build_tick(), metadata=123)  # to_dict iterates metadata -> raw TypeError if unguarded
    journal = EvidenceJournal()
    with pytest.raises(PaperTradeTickJournalAdapterError) as exc:
        _append(journal, tick)
    assert "tick_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 14. forbidden correlation token fails through journal guard; journal unchanged.
def test_forbidden_correlation_token_fails_closed() -> None:
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, _build_tick(), correlation_id="order_router_loop")
    assert journal.entry_count == 0


# 15. forbidden payload token (in a REJECTED tick's stored metadata) fails closed; journal unchanged.
def test_forbidden_payload_metadata_token_fails_closed() -> None:
    tick = _build_tick(metadata={"note": "order_router"})  # REJECTED; payload metadata carries the token
    assert tick.status is PaperTradeTickStatus.REJECTED
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, tick, correlation_id="corr:ok")
    assert journal.entry_count == 0


# 16. market-data safe terms order_book/order_flow/limit_order_book still append if the tick was accepted.
@pytest.mark.parametrize("term", ["order_book", "order_flow", "limit_order_book"])
def test_market_data_terms_append_when_accepted(term: str) -> None:
    tick = _build_tick(metadata={"market_data_source": term})
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    journal = EvidenceJournal()
    entry = _append(journal, tick, correlation_id="corr:market-data")
    assert entry.entry_type is EvidenceArtifactType.PAPER_TRADE_TICK
    assert journal.entry_count == 1


# 17. the bridge journals ticks under their own artifact type, never the replay-report type.
def test_bridge_journals_under_paper_trade_tick_not_replay_report() -> None:
    import crypto_core.audit.paper_trade_tick_journal_adapter as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "EvidenceArtifactType.PAPER_TRADE_TICK" in source
    assert "PAPER_REPLAY_RESULT_REPORT" not in source


# 18. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_purity_no_impure_imports() -> None:
    import crypto_core.audit.paper_trade_tick_journal_adapter as mod

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


# 19. no live/order/scheduler/connector/BIST implementation surface (exact public API only).
def test_no_forbidden_implementation_surface() -> None:
    import crypto_core.audit.paper_trade_tick_journal_adapter as mod

    assert set(mod.__all__) == {
        "PaperTradeTickJournalAdapterError",
        "append_paper_trade_tick_to_evidence_journal",
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
    )
    for name in mod.__all__:
        lowered = name.lower()
        assert all(token not in lowered for token in banned), name


# 20. serialization export/import keeps multiple PAPER_TRADE_TICK entries accepted.
def test_serialization_round_trip_multiple_entries() -> None:
    journal = EvidenceJournal()
    _append(journal, _build_tick(), correlation_id="corr:1")
    _append(journal, _build_tick(action="SELL"), correlation_id="corr:2")
    data = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        data, expected_entry_count=journal.entry_count, expected_head_digest=journal.head_digest
    )
    assert loaded.entry_count == 2
    assert loaded.verify_chain().accepted is True
    assert all(entry.entry_type is EvidenceArtifactType.PAPER_TRADE_TICK for entry in loaded.snapshot())
