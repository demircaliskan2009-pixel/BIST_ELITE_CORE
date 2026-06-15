"""Audit bridge: append an existing PaperSleeveRiskBudgetDecision into the EvidenceJournal.

Anchors a paper-only risk-budget eligibility decision in the append-only evidence journal before any
downstream allocator/promotion consumer can read it: the risk-budget seam *decides* eligibility/reservation
over recorded paper intents, and this bridge *journals* that decision under its own
``EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION`` — paper/audit-only. It is not a runtime,
allocator, promotion, scheduler, order router, connector, or execution path: no DB/file/network/env IO, no
clocks, no random, no threading, no orders/fills/PnL/position surface. It journals an already-built
decision; it never allocates, promotes, executes, routes, schedules, connects, or mutates anything.

Design rules:
  - Digest re-proof: the decision self-digest is recomputed via the public
    ``paper_sleeve_risk_budget_decision_digest`` and every per-record decision via
    ``paper_sleeve_risk_budget_record_decision_digest``; a mismatch is rejected before any append. The
    decision's bound ``state_digest`` / ``policy_digest`` are re-proven against the supplied state/policy via
    the public ``paper_sleeve_state_digest`` / ``paper_sleeve_risk_budget_policy_digest``. No hashing
    convention is duplicated here; the upstream serializers/digests are the single source of truth.
  - Re-render re-proof: the decision is re-built by re-running the public
    ``evaluate_paper_sleeve_risk_budget`` on the supplied state + policy with the decision's own
    ``correlation_id`` / ``metadata`` and requiring an identical canonical payload
    (``paper_sleeve_risk_budget_decision_to_dict``). A stale/forged/tampered decision whose self-digests
    were resealed but whose contents do not correspond to the current state+policy is rejected before append.
  - Consistency re-proof (strict ``Decimal``, no float): blocked/insufficient records must reserve ``"0"``,
    ``total_reserved_budget`` must not exceed ``total_budget``, the eligible/blocked/insufficient counts and
    the reserved/requested totals must agree with the per-record decisions. These are exact decimal
    cross-checks over the canonical decision strings, not a re-implementation of the budget decision logic.
  - Append the canonical dict only: the journaled payload is exactly
    ``paper_sleeve_risk_budget_decision_to_dict(decision)``; no caller-supplied ``payload_digest`` is trusted
    (the journal computes it and applies its own token/duplicate guards, not weakened here).
  - Fail closed, no mutation before prechecks: a wrong-typed journal/decision/state/policy, an empty
    ``correlation_id``, an unexpected schema, a malformed decision artifact, a digest mismatch, a
    state/policy mismatch, an unsafe paper-safety flag, a budget inconsistency, or a non-reproducible
    decision raises ``PaperSleeveRiskBudgetDecisionJournalAdapterError`` before any append, leaving the
    journal unchanged. Forbidden BIST/live/private/order/scheduler/connector/shadow tokens and duplicate
    payloads fail through the journal's own ``EvidenceJournalError`` guard.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveState,
    paper_sleeve_state_digest,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetPolicy,
    PaperSleeveRiskBudgetRecordStatus,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
    paper_sleeve_risk_budget_policy_digest,
    paper_sleeve_risk_budget_record_decision_digest,
)

# The decision schema this bridge is written against. A bump is a coordinated, reviewed migration.
_EXPECTED_DECISION_SCHEMA_VERSION = "paper-sleeve-risk-budget-decision.v1"

# Strict decimal-string grammar (mirrors the decision contract): used only for exact cross-check parsing.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class PaperSleeveRiskBudgetDecisionJournalAdapterError(RuntimeError):
    """Raised when a decision handed to the journal bridge fails type/digest/re-render/consistency re-proof."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _strict_decimal(value: object, reason: str) -> Decimal:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(reason)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(reason) from exc
    if not parsed.is_finite():
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(reason)
    return parsed


def _exact_total(values: list[Decimal]) -> Decimal:
    """Sum exact decimals under a precision wide enough that no addition is rounded (input-derived)."""
    if not values:
        return Decimal(0)
    needed = sum(len(value.as_tuple().digits) for value in values) + 32
    with localcontext() as ctx:
        ctx.prec = max(28, needed)
        total = Decimal(0)
        for value in values:
            total += value
        return total


def _reject_inconsistent_decision(decision: PaperSleeveRiskBudgetDecision) -> None:
    """Exact strict-``Decimal`` cross-checks of counts, reserved-zero, and reserved/requested totals."""
    reserved_values: list[Decimal] = []
    requested_values: list[Decimal] = []
    eligible = 0
    blocked = 0
    insufficient = 0
    for record in decision.record_decisions:
        if (
            record.paper_only is not True
            or record.real_orders_enabled is not False
            or record.real_money_enabled is not False
        ):
            raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                "paper_sleeve_risk_budget_decision_journal_adapter:record_decision_not_paper_safe"
            )
        reserved = _strict_decimal(
            record.reserved_budget,
            "paper_sleeve_risk_budget_decision_journal_adapter:record_reserved_budget_malformed",
        )
        requested = _strict_decimal(
            record.requested_budget,
            "paper_sleeve_risk_budget_decision_journal_adapter:record_requested_budget_malformed",
        )
        reserved_values.append(reserved)
        requested_values.append(requested)
        if record.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE:
            eligible += 1
        elif record.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED:
            blocked += 1
            if reserved != 0:
                raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                    "paper_sleeve_risk_budget_decision_journal_adapter:blocked_record_reserved_budget_nonzero"
                )
        elif record.status is PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE:
            insufficient += 1
            if reserved != 0:
                raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                    "paper_sleeve_risk_budget_decision_journal_adapter:insufficient_record_reserved_budget_nonzero"
                )
        else:
            raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                "paper_sleeve_risk_budget_decision_journal_adapter:record_status_malformed"
            )

    if decision.eligible_count != eligible:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:eligible_count_mismatch"
        )
    if decision.blocked_count != blocked:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:blocked_count_mismatch"
        )
    if decision.insufficient_count != insufficient:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:insufficient_count_mismatch"
        )

    total_budget = _strict_decimal(
        decision.total_budget, "paper_sleeve_risk_budget_decision_journal_adapter:total_budget_malformed"
    )
    total_reserved = _strict_decimal(
        decision.total_reserved_budget,
        "paper_sleeve_risk_budget_decision_journal_adapter:total_reserved_budget_malformed",
    )
    total_requested = _strict_decimal(
        decision.total_requested_budget,
        "paper_sleeve_risk_budget_decision_journal_adapter:total_requested_budget_malformed",
    )
    if total_reserved > total_budget:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:total_reserved_budget_exceeds_total_budget"
        )
    if _exact_total(reserved_values) != total_reserved:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:total_reserved_budget_mismatch"
        )
    if _exact_total(requested_values) != total_requested:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:total_requested_budget_mismatch"
        )


def append_paper_sleeve_risk_budget_decision_to_evidence_journal(
    journal: EvidenceJournal,
    decision: PaperSleeveRiskBudgetDecision,
    *,
    state: PaperSleeveState,
    policy: PaperSleeveRiskBudgetPolicy,
    correlation_id: str,
) -> EvidenceJournalEntry:
    """Append a re-proven ``PaperSleeveRiskBudgetDecision`` to ``journal`` as PAPER_SLEEVE_RISK_BUDGET_DECISION.

    ``journal`` must be an ``EvidenceJournal``, ``decision`` a ``PaperSleeveRiskBudgetDecision``, ``state`` a
    ``PaperSleeveState``, and ``policy`` a ``PaperSleeveRiskBudgetPolicy``. The decision is rejected before any
    append (journal unchanged) on a wrong type, an empty ``correlation_id``, an unexpected ``schema_version``,
    an unsafe paper-safety flag, a malformed decision artifact, a decision/record digest mismatch, a
    state/policy digest mismatch, a budget inconsistency (blocked/insufficient reserve, count, or total), or a
    decision that does not re-render from the supplied state+policy. The journaled payload is exactly
    ``paper_sleeve_risk_budget_decision_to_dict(decision)``; the journal computes the payload digest and
    applies its own token/duplicate guards (forbidden tokens and replays surface as ``EvidenceJournalError``).
    Journals audit provenance only — no allocation, promotion, execution, routing, fill, PnL, or position.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:journal_malformed"
        )
    if not isinstance(decision, PaperSleeveRiskBudgetDecision):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_malformed"
        )
    if not isinstance(state, PaperSleeveState):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:state_malformed"
        )
    if not isinstance(policy, PaperSleeveRiskBudgetPolicy):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:policy_malformed"
        )
    if not _is_non_empty_string(correlation_id):
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:correlation_id_invalid"
        )
    if decision.schema_version != _EXPECTED_DECISION_SCHEMA_VERSION:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_schema_version_unexpected"
        )

    # Paper-only invariant: a self-consistent (resealed) decision can still attest ``paper_only=False`` or
    # enabled real orders/money. The journal token guard only covers the real-orders/real-money attestation
    # keys, so the bridge enforces the full paper-safety triple itself before journaling.
    if decision.paper_only is not True:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_not_paper_only"
        )
    if decision.real_orders_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_real_orders_enabled"
        )
    if decision.real_money_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_real_money_enabled"
        )

    # Serialize and recompute the bound digests via the public helpers. A malformed decision artifact
    # surfaces as a clean adapter error, never a raw AttributeError/TypeError/ValueError. BaseException
    # is deliberately not caught.
    try:
        payload = paper_sleeve_risk_budget_decision_to_dict(decision)
        expected_decision_digest = paper_sleeve_risk_budget_decision_digest(decision)
        rebound_state_digest = paper_sleeve_state_digest(state)
        rebound_policy_digest = paper_sleeve_risk_budget_policy_digest(policy)
    except Exception as exc:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_malformed"
        ) from exc

    if expected_decision_digest != decision.decision_digest:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_digest_mismatch"
        )
    if rebound_state_digest != decision.state_digest:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:state_mismatch"
        )
    if rebound_policy_digest != decision.policy_digest:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:policy_mismatch"
        )

    # Per-record decision digest re-proof.
    for record in decision.record_decisions:
        try:
            rebound_record_digest = paper_sleeve_risk_budget_record_decision_digest(record)
        except Exception as exc:
            raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                "paper_sleeve_risk_budget_decision_journal_adapter:decision_malformed"
            ) from exc
        if rebound_record_digest != record.record_decision_digest:
            raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
                "paper_sleeve_risk_budget_decision_journal_adapter:record_decision_digest_mismatch"
            )

    # Exact strict-Decimal consistency cross-checks (counts, reserved-zero, totals).
    _reject_inconsistent_decision(decision)

    # Re-render re-proof: re-run the public evaluator on the supplied state+policy with the decision's own
    # correlation_id/metadata and require an identical canonical payload. This re-proves the bound state and
    # policy together with every record decision, rejecting any stale/tampered decision before journaling.
    try:
        rebuilt = evaluate_paper_sleeve_risk_budget(
            state,
            policy,
            correlation_id=decision.correlation_id,
            metadata=dict(decision.metadata),
        )
        rebuilt_payload = paper_sleeve_risk_budget_decision_to_dict(rebuilt)
    except Exception as exc:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_not_reproducible"
        ) from exc
    if rebuilt_payload != payload:
        raise PaperSleeveRiskBudgetDecisionJournalAdapterError(
            "paper_sleeve_risk_budget_decision_journal_adapter:decision_not_reproducible"
        )

    # Exactly one append after all prechecks pass; no caller payload_digest is trusted.
    return journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION,
        payload,
        correlation_id=correlation_id,
    )


__all__ = [
    "PaperSleeveRiskBudgetDecisionJournalAdapterError",
    "append_paper_sleeve_risk_budget_decision_to_evidence_journal",
]
