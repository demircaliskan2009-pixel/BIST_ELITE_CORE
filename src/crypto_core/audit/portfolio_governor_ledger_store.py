"""Append-only paper governor ledger store — Phase 16F.

In-memory, append-only, deterministically-chained repository for
``PortfolioGovernorLedgerEntry`` records (the output of
``build_portfolio_governor_ledger_entry``). Gives the paper governor lifecycle an auditable,
replayable history of governor target directives — without any disk write, order intent, live
route, venue execution, or scheduler.

Design rules:
  - Accepts only ``PortfolioGovernorLedgerEntry`` instances; everything else fails closed.
  - Validates each entry before append (schema version, paper-only flags, canonical 64-hex
    digests, present/canonical evidence refs, structurally valid targets/blockers, and the
    entry's own content re-hashing to its ``entry_digest`` — tamper detection).
  - Append-only chain: the first entry must have ``previous_entry_digest is None``; every later
    entry must reference the previous entry's ``entry_digest``. A mismatch, a duplicate
    ``entry_digest``, or a tampered entry is rejected (fail closed).
  - Preserve verbatim: entries are stored exactly as supplied (no mutation, re-sizing, or
    re-digesting beyond integrity verification).
  - Deterministic retrieval: by entry digest, plan_id, correlation_id, or the full ordered
    snapshot — always returned as immutable tuples, never mutable internal state.
  - PAPER ONLY / in-memory only: no persistence, no order/live/scheduler/venue.

Persistent disk write is intentionally out of scope for this bounded store; the canonical
``portfolio_governor_ledger_entry_to_dict`` projection already exists for a later store layer.

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16F.
"""

from __future__ import annotations

import hashlib
import json
import math

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.audit.portfolio_governor_ledger import (
    PortfolioGovernorLedgerEntry,
    PortfolioGovernorLedgerStatus,
)
from crypto_core.service.portfolio_governor_consumption import (
    GovernorActionType,
    SleeveTargetDirective,
)

_EXPECTED_ENTRY_SCHEMA_VERSION = "portfolio-governor-ledger-entry.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_EXPECTED_EVIDENCE_SOURCES = (
    "portfolio_allocation_decision",
    "allocation_governor_view",
    "portfolio_allocation_record",
    "portfolio_governor_directive",
)


class PortfolioGovernorLedgerStoreError(RuntimeError):
    """Raised when an append/retrieval input is malformed, tampered, or breaks the chain (fail-closed)."""


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _sha256_hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _is_positive_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_targets(targets: tuple[SleeveTargetDirective, ...]) -> list[list[object]]:
    return [[t.sleeve_id, t.action.value, t.weight, t.notional] for t in targets]


def _expected_entry_digest(entry: PortfolioGovernorLedgerEntry) -> str:
    # Mirror of the ledger-entry digest payload (``build_portfolio_governor_ledger_entry``).
    # Recomputed here only to verify the supplied entry has not been tampered with after
    # construction (matching the upstream consumer pattern); it re-derives no decision logic.
    # A real entry built by the ledger module keeps this in lockstep (asserted by the tests).
    payload: dict[str, object] = {
        "schema_version": entry.schema_version,
        "status": entry.status.value,
        "action": entry.action.value,
        "plan_id": entry.plan_id,
        "source_decision_digest": entry.source_decision_digest,
        "view_digest": entry.view_digest,
        "record_digest": entry.record_digest,
        "directive_digest": entry.directive_digest,
        "budget": entry.budget,
        "capital_base": entry.capital_base,
        "total_weight": entry.total_weight,
        "total_notional": entry.total_notional,
        "targets": _serialize_targets(entry.targets),
        "blockers": list(entry.blockers),
        "evidence_refs": [[ref.source_type, ref.digest] for ref in entry.evidence_refs],
        "correlation_id": entry.correlation_id,
        "previous_entry_digest": entry.previous_entry_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _validate_targets(entry: PortfolioGovernorLedgerEntry) -> None:
    if not isinstance(entry.targets, tuple):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:targets_malformed")
    seen: set[str] = set()
    for target in entry.targets:
        if not isinstance(target, SleeveTargetDirective):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:target_malformed")
        if not _non_empty_str(target.sleeve_id):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:sleeve_id_invalid")
        if not isinstance(target.action, GovernorActionType):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:target_action_invalid")
        if not _is_positive_finite(target.weight):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:weight_invalid")
        if not _is_non_negative_finite(target.notional):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:notional_invalid")
        if target.sleeve_id in seen:
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:duplicate_sleeve_id")
        seen.add(target.sleeve_id)


def _validate_evidence_refs(entry: PortfolioGovernorLedgerEntry) -> None:
    if not isinstance(entry.evidence_refs, tuple) or not entry.evidence_refs:
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:evidence_refs_missing")
    for ref in entry.evidence_refs:
        if not isinstance(ref, DecisionEvidenceRef):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:evidence_ref_malformed")
        if not _non_empty_str(ref.source_type):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:evidence_ref_source_type_invalid")
        if not _sha256_hex_digest(ref.digest):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:evidence_ref_digest_invalid")
    if tuple(ref.source_type for ref in entry.evidence_refs) != _EXPECTED_EVIDENCE_SOURCES:
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:evidence_refs_unexpected")


def _validate_status_coherence(entry: PortfolioGovernorLedgerEntry) -> None:
    if entry.status == PortfolioGovernorLedgerStatus.RECORDED_ACTIVE:
        if entry.action != GovernorActionType.SET_PAPER_TARGET or not entry.targets:
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_inconsistent")
        if any(target.action != GovernorActionType.SET_PAPER_TARGET for target in entry.targets):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_inconsistent")
    elif entry.status == PortfolioGovernorLedgerStatus.RECORDED_BLOCKED:
        if entry.action != GovernorActionType.HOLD or entry.targets:
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_inconsistent")
    else:
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:status_unknown")


def _validate_entry(entry: object) -> PortfolioGovernorLedgerEntry:
    if not isinstance(entry, PortfolioGovernorLedgerEntry):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_malformed")
    if not isinstance(entry.status, PortfolioGovernorLedgerStatus) or not isinstance(entry.action, GovernorActionType):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_malformed")
    if entry.schema_version != _EXPECTED_ENTRY_SCHEMA_VERSION:
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:schema_version_unexpected")
    if not (entry.paper_only is True and entry.real_orders_enabled is False and entry.real_money_enabled is False):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:non_paper_entry_rejected")
    if not _non_empty_str(entry.plan_id):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:plan_id_missing")
    if not _non_empty_str(entry.correlation_id):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:correlation_id_missing")
    if not (
        _sha256_hex_digest(entry.entry_digest)
        and _sha256_hex_digest(entry.directive_digest)
        and _sha256_hex_digest(entry.source_decision_digest)
        and _sha256_hex_digest(entry.view_digest)
        and _sha256_hex_digest(entry.record_digest)
    ):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:digest_invalid")
    if entry.previous_entry_digest is not None and not _sha256_hex_digest(entry.previous_entry_digest):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:previous_entry_digest_invalid")
    if not _is_non_negative_finite(entry.budget):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:budget_invalid")
    if not _is_positive_finite(entry.capital_base):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:capital_base_invalid")
    if not (_is_non_negative_finite(entry.total_weight) and _is_non_negative_finite(entry.total_notional)):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:totals_invalid")

    _validate_targets(entry)
    if not isinstance(entry.blockers, tuple) or any(not _non_empty_str(value) for value in entry.blockers):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:blockers_malformed")
    if entry.blockers != _sorted_unique(entry.blockers):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:blockers_not_canonical")
    _validate_evidence_refs(entry)
    _validate_status_coherence(entry)

    # Integrity: the entry's own digest must match its content (tamper detection).
    if entry.entry_digest != _expected_entry_digest(entry):
        raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_digest_mismatch")
    return entry


class PortfolioGovernorLedgerStore:
    """Append-only, deterministically-chained in-memory store of ``PortfolioGovernorLedgerEntry``.

    Paper-only by construction. Validates and chains entries on append; exposes deterministic,
    immutable retrieval. Holds no disk/persistence and produces no order/live/scheduler/venue.
    """

    def __init__(self) -> None:
        self._entries: list[PortfolioGovernorLedgerEntry] = []
        self._by_digest: dict[str, PortfolioGovernorLedgerEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, entry: PortfolioGovernorLedgerEntry) -> PortfolioGovernorLedgerEntry:
        """Validate and append one entry, enforcing the append-only chain. Fail-closed on any breach."""
        validated = _validate_entry(entry)
        if validated.entry_digest in self._by_digest:
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:duplicate_entry_digest")
        if not self._entries:
            if validated.previous_entry_digest is not None:
                raise PortfolioGovernorLedgerStoreError(
                    "portfolio_governor_ledger_store:first_entry_previous_digest_must_be_none"
                )
        elif validated.previous_entry_digest != self._entries[-1].entry_digest:
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:previous_entry_digest_mismatch")
        self._entries.append(validated)
        self._by_digest[validated.entry_digest] = validated
        return validated

    def snapshot(self) -> tuple[PortfolioGovernorLedgerEntry, ...]:
        """Full ordered ledger snapshot as an immutable tuple (oldest first)."""
        return tuple(self._entries)

    def head_digest(self) -> str | None:
        """``entry_digest`` of the most recent entry, or ``None`` when the store is empty."""
        return self._entries[-1].entry_digest if self._entries else None

    def get_by_entry_digest(self, entry_digest: str) -> PortfolioGovernorLedgerEntry | None:
        """Return the entry with this ``entry_digest``, or ``None`` if absent. Fail-closed on bad input."""
        if not _non_empty_str(entry_digest):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:entry_digest_query_invalid")
        return self._by_digest.get(entry_digest)

    def find_by_plan_id(self, plan_id: str) -> tuple[PortfolioGovernorLedgerEntry, ...]:
        """Return entries for this ``plan_id`` in append order (immutable tuple)."""
        if not _non_empty_str(plan_id):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:plan_id_query_invalid")
        return tuple(entry for entry in self._entries if entry.plan_id == plan_id)

    def find_by_correlation_id(self, correlation_id: str) -> tuple[PortfolioGovernorLedgerEntry, ...]:
        """Return entries for this ``correlation_id`` in append order (immutable tuple)."""
        if not _non_empty_str(correlation_id):
            raise PortfolioGovernorLedgerStoreError("portfolio_governor_ledger_store:correlation_id_query_invalid")
        return tuple(entry for entry in self._entries if entry.correlation_id == correlation_id)
