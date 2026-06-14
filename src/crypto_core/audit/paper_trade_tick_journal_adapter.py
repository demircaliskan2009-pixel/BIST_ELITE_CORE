"""Audit bridge: append an existing PaperTradeTick into the EvidenceJournal.

Closes the paper-trade-tick provenance gap left out of the contract PR: the paper trade tick contract
*records* a deterministic, paper-only trade intent and renders a fail-closed verdict, and this bridge
*journals* that recorded tick under its own ``EvidenceArtifactType.PAPER_TRADE_TICK`` — paper/audit-only.
It is not a runtime, scheduler, order router, connector, or execution path: no DB/file/network/env IO, no
clocks, no random, no threading, no orders/fills/PnL/sleeve-state surface. It journals an already-built
tick; it never builds, executes, routes, schedules, connects, or mutates anything.

Design rules:
  - Boundary digest re-proof: the tick digest is recomputed via the public ``paper_trade_tick_digest``
    re-proof (which serializes the tick through ``paper_trade_tick_to_dict`` excluding the self-digest) and
    a mismatch is rejected before any append — a stale/forged/tampered tick cannot be journaled. No hashing
    convention is duplicated here; the contract module's serializer/digest is the single source of truth.
  - Re-render re-proof: the self-digest hashes the stored ``intent_digest`` and verdict as opaque fields,
    so a tick whose intent fields were tampered and then resealed could still carry a stale carried
    ``intent_digest`` / ``status`` / ``accepted``. The bridge re-runs the tick's own intent fields through
    the public ``build_paper_trade_tick`` and requires an identical canonical payload, re-proving the
    carried intent digest and the rendered verdict together; a non-reproducible tick is rejected.
  - Schema pinning: ``tick.schema_version`` must equal the tick schema this bridge targets.
  - Append the canonical dict only: the journaled payload is exactly ``paper_trade_tick_to_dict(tick)``;
    no caller-supplied ``payload_digest`` is trusted (the journal computes it).
  - Any-status: a valid tick of any terminal status (ACCEPTED / REJECTED / INSUFFICIENT_EVIDENCE /
    NEEDS_RESEARCH) is journaled if its digest re-proves and the ``status``/``accepted`` flag agree — the
    journal stores valid artifacts, not only ACCEPTED ones. (A tick rejected for a scope/wall-clock reason
    whose canonical payload itself carries a forbidden token still fails closed through the journal guard.)
  - Fail closed, no mutation before prechecks: a wrong-typed journal/tick, an empty correlation id, an
    unexpected schema, a malformed tick artifact, a digest mismatch, an unsafe paper-safety flag, or a
    ``status``/``accepted`` disagreement raises ``PaperTradeTickJournalAdapterError`` before any append,
    leaving the journal unchanged. Forbidden BIST/live/private/order/scheduler/connector/shadow tokens and
    duplicate payloads fail through the journal's own ``EvidenceJournalError`` guard (not weakened here).
"""

from __future__ import annotations

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
)
from crypto_core.validation.paper_trade_tick import (
    PaperTradeTick,
    PaperTradeTickStatus,
    build_paper_trade_tick,
    paper_trade_tick_digest,
    paper_trade_tick_to_dict,
)

# The paper-trade-tick schema this bridge is written against. A bump is a coordinated, reviewed migration.
_EXPECTED_TICK_SCHEMA_VERSION = "paper-trade-tick.v1"


class PaperTradeTickJournalAdapterError(RuntimeError):
    """Raised when a tick handed to the journal bridge is malformed or fails digest/schema/safety re-proof."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def append_paper_trade_tick_to_evidence_journal(
    journal: EvidenceJournal,
    tick: PaperTradeTick,
    *,
    correlation_id: str,
) -> EvidenceJournalEntry:
    """Append a re-proven ``PaperTradeTick`` to ``journal`` as ``PAPER_TRADE_TICK``.

    ``journal`` must be an ``EvidenceJournal`` and ``tick`` a ``PaperTradeTick``; a wrong type, an empty
    ``correlation_id``, an unexpected ``schema_version``, a malformed tick artifact, a
    ``paper_trade_tick_digest`` that does not re-prove, an unsafe paper-safety flag, or a ``status`` /
    ``accepted`` disagreement raises ``PaperTradeTickJournalAdapterError`` before any append (journal
    unchanged). The journaled payload is exactly ``paper_trade_tick_to_dict(tick)``; the journal computes
    the payload digest and applies its own token/duplicate guards (forbidden tokens and replays surface as
    ``EvidenceJournalError``).
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:journal_malformed")
    if not isinstance(tick, PaperTradeTick):
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:correlation_id_invalid")
    if tick.schema_version != _EXPECTED_TICK_SCHEMA_VERSION:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_schema_version_unexpected")

    # Serialize, re-prove the self-digest, and re-render the tick from its own fields via the public
    # contract builder. A malformed tick artifact surfaces as a clean adapter error, never a raw
    # AttributeError/TypeError/ValueError. BaseException is deliberately not caught.
    try:
        payload = paper_trade_tick_to_dict(tick)
        expected_digest = paper_trade_tick_digest(tick)
        rebuilt_payload = paper_trade_tick_to_dict(
            build_paper_trade_tick(
                tick_id=tick.tick_id,
                action=tick.action,
                intent_type=tick.intent_type,
                instrument_id=tick.instrument_id,
                quantity=tick.quantity,
                strategy_id=tick.strategy_id,
                run_plan_id=tick.run_plan_id,
                upstream_report_digest=tick.upstream_report_digest,
                correlation_id=tick.correlation_id,
                limit_price=tick.limit_price,
                metadata=dict(tick.metadata),
                paper_only=tick.paper_only,
                real_orders_enabled=tick.real_orders_enabled,
                real_money_enabled=tick.real_money_enabled,
            )
        )
    except Exception as exc:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_malformed") from exc

    stored_digest = tick.paper_trade_tick_digest
    if not isinstance(stored_digest, str) or stored_digest != expected_digest:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:paper_trade_tick_digest_mismatch")

    # Paper-only invariant: a self-consistent (resealed) tick can still attest ``paper_only=False`` or
    # enabled real orders/money. The journal's token guard does not cover ``paper_only``, so the bridge
    # enforces the full paper-safety triple itself before journaling into the paper-only audit log.
    if tick.paper_only is not True:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_not_paper_only")
    if tick.real_orders_enabled is not False:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_real_orders_enabled")
    if tick.real_money_enabled is not False:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_real_money_enabled")

    # Status/accepted consistency: ACCEPTED <=> accepted is True; any other status <=> accepted is False.
    if not isinstance(tick.status, PaperTradeTickStatus):
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_status_malformed")
    expected_accepted = tick.status is PaperTradeTickStatus.ACCEPTED
    if tick.accepted is not expected_accepted:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_status_accepted_mismatch")

    # Re-render re-proof: the self-digest only covers the *stored* fields, so a tick whose intent fields
    # were tampered and then resealed can still carry a stale ``intent_digest`` / ``status`` / ``accepted``
    # verdict that the self-digest cannot detect. Re-running the tick's own fields through the public
    # contract builder and requiring an identical canonical payload re-proves the carried intent digest
    # and the verdict together, rejecting any non-reproducible (stale/tampered) tick before journaling.
    if rebuilt_payload != payload:
        raise PaperTradeTickJournalAdapterError("paper_trade_tick_journal_adapter:tick_not_reproducible")

    # Exactly one append after all prechecks pass; no caller payload_digest is trusted.
    return journal.append(
        EvidenceArtifactType.PAPER_TRADE_TICK,
        payload,
        correlation_id=correlation_id,
    )


__all__ = [
    "PaperTradeTickJournalAdapterError",
    "append_paper_trade_tick_to_evidence_journal",
]
