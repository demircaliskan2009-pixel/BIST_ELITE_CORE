"""Paper sleeve intent ledger — deterministic, paper-only state/ledger for journaled trade-tick intent.

A small, deterministic, fail-closed state layer that records *already-built* ``PaperTradeTick`` evidence as
immutable intent records in a paper sleeve ledger. It is *state/ledger only*: it does **not** execute,
route, fill, price-improve, compute PnL, open/close positions, connect, schedule, run a loop, or mutate any
hidden/global state — no DB/file/network/env IO, no wall-clock, no random, no threading. Every transition
returns new frozen dataclasses; the input state is never mutated.

Design rules:
  - Boundary re-proof: a consumed tick is re-proven via the public ``paper_trade_tick_digest`` (self-digest)
    AND re-rendered through the public ``build_paper_trade_tick`` (requiring an identical canonical payload),
    so a stale/forged/tampered tick — including one resealed with a stale carried intent digest or verdict —
    is rejected before any state change. The contract module's serializer/digest is the single source of
    truth; no hashing convention of the tick is duplicated here.
  - Paper-safety + consistency: the tick paper-safety triple (``paper_only`` True, ``real_orders_enabled`` /
    ``real_money_enabled`` False) and ``status``/``accepted`` agreement are enforced before recording.
  - Optional journal binding: when an ``EvidenceJournalEntry`` is supplied it must be a
    ``PAPER_TRADE_TICK`` entry whose payload equals ``paper_trade_tick_to_dict(tick)`` and whose
    ``payload_digest`` is canonical 64-hex; the record then binds that journal payload digest. Without an
    entry the record is tick-bound but not journal-entry-bound.
  - Record verdict, never execute: an ACCEPTED tick is recorded as a RECORDED (candidate) paper intent; a
    REJECTED / NEEDS_RESEARCH tick as a REJECTED non-executable audit record; an INSUFFICIENT_EVIDENCE tick
    as an INSUFFICIENT_EVIDENCE audit record. No position/fill/PnL/venue/order-id field exists.
  - Fail closed, no mutation before prechecks: a wrong-typed state/tick/entry, an empty id, an unexpected
    schema, a malformed tick, a digest/reproducibility/safety/consistency failure, a journal-binding
    mismatch, a forbidden BIST/live/order/scheduler/connector/shadow token, or a duplicate tick digest
    raises ``PaperSleeveIntentLedgerError`` before any record is appended, leaving the input state intact.
  - Deterministic: canonical SHA-256 record/state/transition digests (each excluding its own self-digest);
    frozen dataclasses; stable tuple ordering. ``paper_only=True`` and no order/route/venue/scheduler/
    runtime/fill/PnL/position field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournalEntry
from crypto_core.validation.paper_trade_tick import (
    PaperTradeTick,
    PaperTradeTickStatus,
    build_paper_trade_tick,
    paper_trade_tick_digest,
    paper_trade_tick_to_dict,
)

_SCHEMA_VERSION = "paper-sleeve-intent-ledger.v1"
_RECORD_SCHEMA_VERSION = "paper-sleeve-intent-record.v1"
_TRANSITION_SCHEMA_VERSION = "paper-sleeve-intent-transition.v1"
_EXPECTED_TICK_SCHEMA_VERSION = "paper-trade-tick.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order-routing/scheduler/private/shadow tokens
# (word-bounded). A bare ``order``/``orders`` token is rejected while ``border``/``reorder`` are spared;
# market-data terms (``order_book``/``order_flow``/``limit_order_book``) are scrubbed before the scan.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector_ready|credential|"
    r"credentials|scheduler|shadow)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperSleeveIntentLedgerError(RuntimeError):
    """Raised when sleeve ledger inputs are malformed or a tick fails re-proof/safety/consistency."""


class PaperSleeveIntentStatus(str, Enum):
    """Terminal classification of a recorded paper intent. Never an execution action."""

    RECORDED = "RECORDED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSleeveIntentRecord:
    """Deterministic, immutable record of one journaled/tick-bound paper intent. PAPER ONLY."""

    schema_version: str
    intent_status: PaperSleeveIntentStatus
    sleeve_id: str
    sequence: int
    tick_id: str
    tick_status: str
    accepted: bool
    instrument_id: str
    action: str
    intent_type: str
    quantity: str
    limit_price: str | None
    strategy_id: str
    run_plan_id: str
    upstream_report_digest: str
    intent_digest: str
    paper_trade_tick_digest: str
    journal_payload_digest: str
    journal_bound: bool
    metadata: tuple[tuple[str, str], ...]
    correlation_id: str
    record_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperSleeveState:
    """Deterministic, immutable paper sleeve ledger state (append-only intent records). PAPER ONLY."""

    schema_version: str
    sleeve_id: str
    records: tuple[PaperSleeveIntentRecord, ...]
    record_count: int
    recorded_count: int
    metadata: tuple[tuple[str, str], ...]
    correlation_id: str
    state_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperSleeveTransition:
    """Deterministic, immutable transition produced by recording one tick into a sleeve state. PAPER ONLY."""

    schema_version: str
    sleeve_id: str
    from_state_digest: str
    to_state_digest: str
    intent_status: PaperSleeveIntentStatus
    sequence: int
    record: PaperSleeveIntentRecord
    to_state: PaperSleeveState
    correlation_id: str
    transition_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_sleeve_intent_ledger:bist_scope_leakage")
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            reasons.append("paper_sleeve_intent_ledger:forbidden_scope_token")
    return tuple(reasons)


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _classify_intent_status(tick_status: PaperTradeTickStatus) -> PaperSleeveIntentStatus:
    if tick_status is PaperTradeTickStatus.ACCEPTED:
        return PaperSleeveIntentStatus.RECORDED
    if tick_status is PaperTradeTickStatus.INSUFFICIENT_EVIDENCE:
        return PaperSleeveIntentStatus.INSUFFICIENT_EVIDENCE
    return PaperSleeveIntentStatus.REJECTED


def _reprove_tick(tick: object) -> dict[str, object]:
    """Re-prove a consumed tick at the ledger boundary; return its canonical payload or raise."""
    if not isinstance(tick, PaperTradeTick):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_malformed")
    if tick.schema_version != _EXPECTED_TICK_SCHEMA_VERSION:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_schema_version_unexpected")

    # Serialize, re-prove the self-digest, and re-render the tick from its own fields via the public
    # contract builder. A malformed tick artifact surfaces as a clean adapter error, never a raw exception.
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
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_malformed") from exc

    stored_digest = tick.paper_trade_tick_digest
    if not isinstance(stored_digest, str) or stored_digest != expected_digest:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_digest_mismatch")
    if tick.paper_only is not True:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_not_paper_only")
    if tick.real_orders_enabled is not False:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_real_orders_enabled")
    if tick.real_money_enabled is not False:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_real_money_enabled")
    if not isinstance(tick.status, PaperTradeTickStatus):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_status_malformed")
    expected_accepted = tick.status is PaperTradeTickStatus.ACCEPTED
    if tick.accepted is not expected_accepted:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_status_accepted_mismatch")
    if rebuilt_payload != payload:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:tick_not_reproducible")
    return payload


def _validate_journal_binding(journal_entry: object, tick_payload: dict[str, object]) -> str:
    if not isinstance(journal_entry, EvidenceJournalEntry):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:journal_entry_malformed")
    if journal_entry.entry_type is not EvidenceArtifactType.PAPER_TRADE_TICK:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:journal_entry_artifact_type_mismatch")
    if dict(journal_entry.payload) != tick_payload:
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:journal_entry_payload_mismatch")
    if not _is_sha256_hex(journal_entry.payload_digest):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:journal_entry_payload_digest_invalid")
    return journal_entry.payload_digest


def _state_self_consistent(state: PaperSleeveState) -> bool:
    if state.record_count != len(state.records):
        return False
    recorded = sum(1 for record in state.records if record.intent_status is PaperSleeveIntentStatus.RECORDED)
    if state.recorded_count != recorded:
        return False
    return paper_sleeve_state_digest(state) == state.state_digest


def _finalize_record(record: PaperSleeveIntentRecord) -> PaperSleeveIntentRecord:
    return replace(record, record_digest=paper_sleeve_intent_record_digest(record))


def _finalize_state(state: PaperSleeveState) -> PaperSleeveState:
    return replace(state, state_digest=paper_sleeve_state_digest(state))


def _finalize_transition(transition: PaperSleeveTransition) -> PaperSleeveTransition:
    return replace(transition, transition_digest=paper_sleeve_transition_digest(transition))


def _assemble_state(
    *,
    sleeve_id: str,
    records: tuple[PaperSleeveIntentRecord, ...],
    metadata: tuple[tuple[str, str], ...],
    correlation_id: str,
) -> PaperSleeveState:
    recorded_count = sum(1 for record in records if record.intent_status is PaperSleeveIntentStatus.RECORDED)
    state = PaperSleeveState(
        schema_version=_SCHEMA_VERSION,
        sleeve_id=sleeve_id,
        records=records,
        record_count=len(records),
        recorded_count=recorded_count,
        metadata=metadata,
        correlation_id=correlation_id,
        state_digest="",
    )
    return _finalize_state(state)


def build_initial_paper_sleeve_state(
    *,
    sleeve_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleeveState:
    """Build an empty, deterministic paper sleeve ledger state.

    ``sleeve_id`` and ``correlation_id`` must be non-empty token-clean strings and ``metadata`` (if given)
    a ``Mapping[str, str]``; a malformed id/metadata or a forbidden BIST/live/order/scheduler/connector/
    shadow token raises ``PaperSleeveIntentLedgerError``. The returned state has no records and a canonical
    ``state_digest``; it admits, allocates, schedules, routes, and executes nothing.
    """
    if not _is_non_empty_string(sleeve_id):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:sleeve_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _scope_violations(sleeve_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:scope_violation")
    return _assemble_state(sleeve_id=sleeve_id, records=(), metadata=metadata_pairs, correlation_id=correlation_id)


def apply_paper_trade_tick_to_sleeve_state(
    state: PaperSleeveState,
    tick: PaperTradeTick,
    *,
    correlation_id: str,
    journal_entry: EvidenceJournalEntry | None = None,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleeveTransition:
    """Record a re-proven ``PaperTradeTick`` into ``state`` and return a new transition.

    ``state`` must be a self-consistent ``PaperSleeveState`` and ``tick`` a ``PaperTradeTick`` that re-proves
    (self-digest + re-render), is paper-safe, and is status/accepted-consistent; an optional ``journal_entry``
    must be a ``PAPER_TRADE_TICK`` entry whose payload equals ``paper_trade_tick_to_dict(tick)``. A wrong type,
    an empty ``correlation_id``, a forbidden token, a tick re-proof failure, a journal-binding mismatch, or a
    duplicate tick digest raises ``PaperSleeveIntentLedgerError`` before any record is appended (input state
    intact). The new record's status is RECORDED for an ACCEPTED tick and a non-executable REJECTED /
    INSUFFICIENT_EVIDENCE audit record otherwise. Records intent only — no execution, fill, PnL, or position.
    """
    if not isinstance(state, PaperSleeveState):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:state_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:correlation_id_invalid")
    if not _state_self_consistent(state):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:state_digest_mismatch")
    record_metadata = _normalize_metadata(metadata)
    if _scope_violations(correlation_id, *_metadata_texts(record_metadata)):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:scope_violation")

    tick_payload = _reprove_tick(tick)

    journal_payload_digest = ""
    journal_bound = False
    if journal_entry is not None:
        journal_payload_digest = _validate_journal_binding(journal_entry, tick_payload)
        journal_bound = True

    if any(record.paper_trade_tick_digest == tick.paper_trade_tick_digest for record in state.records):
        raise PaperSleeveIntentLedgerError("paper_sleeve_intent_ledger:duplicate_tick_digest")

    intent_status = _classify_intent_status(tick.status)
    record = _finalize_record(
        PaperSleeveIntentRecord(
            schema_version=_RECORD_SCHEMA_VERSION,
            intent_status=intent_status,
            sleeve_id=state.sleeve_id,
            sequence=len(state.records),
            tick_id=tick.tick_id,
            tick_status=tick.status.value,
            accepted=tick.accepted,
            instrument_id=tick.instrument_id,
            action=tick.action,
            intent_type=tick.intent_type,
            quantity=tick.quantity,
            limit_price=tick.limit_price,
            strategy_id=tick.strategy_id,
            run_plan_id=tick.run_plan_id,
            upstream_report_digest=tick.upstream_report_digest,
            intent_digest=tick.intent_digest,
            paper_trade_tick_digest=tick.paper_trade_tick_digest,
            journal_payload_digest=journal_payload_digest,
            journal_bound=journal_bound,
            metadata=record_metadata,
            correlation_id=correlation_id,
            record_digest="",
        )
    )
    to_state = _assemble_state(
        sleeve_id=state.sleeve_id,
        records=(*state.records, record),
        metadata=state.metadata,
        correlation_id=state.correlation_id,
    )
    transition = PaperSleeveTransition(
        schema_version=_TRANSITION_SCHEMA_VERSION,
        sleeve_id=state.sleeve_id,
        from_state_digest=state.state_digest,
        to_state_digest=to_state.state_digest,
        intent_status=intent_status,
        sequence=record.sequence,
        record=record,
        to_state=to_state,
        correlation_id=correlation_id,
        transition_digest="",
    )
    return _finalize_transition(transition)


def paper_sleeve_intent_record_to_dict(record: PaperSleeveIntentRecord) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper sleeve intent record (includes self-digest)."""
    return {
        "schema_version": record.schema_version,
        "intent_status": record.intent_status.value,
        "sleeve_id": record.sleeve_id,
        "sequence": record.sequence,
        "tick_id": record.tick_id,
        "tick_status": record.tick_status,
        "accepted": record.accepted,
        "instrument_id": record.instrument_id,
        "action": record.action,
        "intent_type": record.intent_type,
        "quantity": record.quantity,
        "limit_price": record.limit_price,
        "strategy_id": record.strategy_id,
        "run_plan_id": record.run_plan_id,
        "upstream_report_digest": record.upstream_report_digest,
        "intent_digest": record.intent_digest,
        "paper_trade_tick_digest": record.paper_trade_tick_digest,
        "journal_payload_digest": record.journal_payload_digest,
        "journal_bound": record.journal_bound,
        "metadata": [list(pair) for pair in record.metadata],
        "correlation_id": record.correlation_id,
        "record_digest": record.record_digest,
        "paper_only": record.paper_only,
        "real_orders_enabled": record.real_orders_enabled,
        "real_money_enabled": record.real_money_enabled,
    }


def paper_sleeve_state_to_dict(state: PaperSleeveState) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper sleeve ledger state (includes self-digest)."""
    return {
        "schema_version": state.schema_version,
        "sleeve_id": state.sleeve_id,
        "records": [paper_sleeve_intent_record_to_dict(record) for record in state.records],
        "record_count": state.record_count,
        "recorded_count": state.recorded_count,
        "metadata": [list(pair) for pair in state.metadata],
        "correlation_id": state.correlation_id,
        "state_digest": state.state_digest,
        "paper_only": state.paper_only,
        "real_orders_enabled": state.real_orders_enabled,
        "real_money_enabled": state.real_money_enabled,
    }


def paper_sleeve_transition_to_dict(transition: PaperSleeveTransition) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper sleeve transition (flat; includes self-digest)."""
    return {
        "schema_version": transition.schema_version,
        "sleeve_id": transition.sleeve_id,
        "from_state_digest": transition.from_state_digest,
        "to_state_digest": transition.to_state_digest,
        "intent_status": transition.intent_status.value,
        "sequence": transition.sequence,
        "record_digest": transition.record.record_digest,
        "correlation_id": transition.correlation_id,
        "transition_digest": transition.transition_digest,
        "paper_only": transition.paper_only,
        "real_orders_enabled": transition.real_orders_enabled,
        "real_money_enabled": transition.real_money_enabled,
    }


def paper_sleeve_intent_record_digest(record: PaperSleeveIntentRecord) -> str:
    """Recompute the canonical record digest from the serializer output, excluding the self-digest field."""
    payload = paper_sleeve_intent_record_to_dict(record)
    payload.pop("record_digest", None)
    return _canonical_digest(payload)


def paper_sleeve_state_digest(state: PaperSleeveState) -> str:
    """Recompute the canonical state digest from the serializer output, excluding the self-digest field."""
    payload = paper_sleeve_state_to_dict(state)
    payload.pop("state_digest", None)
    return _canonical_digest(payload)


def paper_sleeve_transition_digest(transition: PaperSleeveTransition) -> str:
    """Recompute the canonical transition digest from the serializer output, excluding the self-digest."""
    payload = paper_sleeve_transition_to_dict(transition)
    payload.pop("transition_digest", None)
    return _canonical_digest(payload)


__all__ = [
    "PaperSleeveIntentLedgerError",
    "PaperSleeveIntentRecord",
    "PaperSleeveIntentStatus",
    "PaperSleeveState",
    "PaperSleeveTransition",
    "apply_paper_trade_tick_to_sleeve_state",
    "build_initial_paper_sleeve_state",
    "paper_sleeve_intent_record_digest",
    "paper_sleeve_intent_record_to_dict",
    "paper_sleeve_state_digest",
    "paper_sleeve_state_to_dict",
    "paper_sleeve_transition_digest",
    "paper_sleeve_transition_to_dict",
]
