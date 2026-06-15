"""Paper sleeve promotion candidate — deterministic, paper-only read model over a journaled risk-budget decision.

A small, immutable, fail-closed *read-model gate* that classifies whether a **journal-anchored**
``PaperSleeveRiskBudgetDecision`` is eligible to be *considered* by a future allocator / paper runner. It is
*only* a classification/provenance gate: a downstream consumer must read a decision that is anchored in the
``EvidenceJournal`` (via a ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` entry whose payload/digest re-prove the
decision), never a bare self-contained decision. ELIGIBLE here means *eligible for consideration*, **never an
execution permission**: this module reserves no capital, allocates nothing, creates/fills no order, computes
no PnL, mutates no state, and appends nothing to the journal — no DB/file/network/env IO, no wall-clock, no
random, no threading, no connector/scheduler/runtime/live/shadow surface, no BIST.

Design rules:
  - Journal anchoring is mandatory: the supplied ``EvidenceJournalEntry`` must be a
    ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` entry whose ``correlation_id`` matches the caller-asserted
    journaling ``correlation_id``, whose ``payload`` equals ``paper_sleeve_risk_budget_decision_to_dict(decision)``
    exactly, and whose ``payload_digest`` equals the canonical digest of that payload. A bare decision that is
    not anchored in such an entry is rejected — the decision alone is never enough.
  - Decision re-proof: ``decision.decision_digest`` is recomputed via the public
    ``paper_sleeve_risk_budget_decision_digest`` and a mismatch is rejected; the decision and every per-record
    decision must attest the exact paper-safety triple (``paper_only=True``, real orders/money ``False``); the
    stored eligible/blocked/insufficient counts must equal the counts derived from the record decisions.
  - Deterministic classification: ELIGIBLE iff at least one record is budget-ELIGIBLE; else
    INSUFFICIENT_EVIDENCE iff (no eligible, no blocked, and at least one insufficient); else BLOCKED (covers
    all-blocked, mixed-without-eligible, and the empty decision). Classification is a verdict, not a capital
    action.
  - Deterministic digest: canonical SHA-256 over the public serializer output (enum ``.value``, stable list
    ordering) excluding the self-digest. Frozen dataclass; stable sorted blockers; no input is mutated.
  - Fail closed: a wrong-typed entry/decision, an empty/forbidden ``correlation_id``, a wrong artifact type, a
    journal payload / payload-digest / correlation mismatch, a decision-digest mismatch, an unsafe paper-safety
    flag, a count mismatch, or a malformed decision raises ``PaperSleevePromotionCandidateError`` before any
    candidate is built.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournalEntry
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetRecordStatus,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
)

_CANDIDATE_SCHEMA_VERSION = "paper-sleeve-promotion-candidate.v1"
_EXPECTED_DECISION_SCHEMA_VERSION = "paper-sleeve-risk-budget-decision.v1"

# Scope guard mirrors the sibling paper-sleeve modules (word-bounded). A bare ``order``/``orders`` token is
# rejected while ``border``/``reorder`` are spared; market-data terms are scrubbed before the scan.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector_ready|credential|"
    r"credentials|scheduler|shadow)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperSleevePromotionCandidateError(RuntimeError):
    """Raised when a journaled risk-budget decision fails type/anchoring/digest/safety re-proof."""


class PaperSleevePromotionCandidateStatus(str, Enum):
    """Promotion-consideration classification of a journaled decision. Never an execution permission."""

    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSleevePromotionCandidate:
    """Deterministic, immutable read model: a journal-anchored decision's promotion eligibility. PAPER ONLY."""

    schema_version: str
    status: PaperSleevePromotionCandidateStatus
    sleeve_id: str
    policy_id: str
    decision_digest: str
    journal_payload_digest: str
    journal_entry_digest: str
    eligible_count: int
    blocked_count: int
    insufficient_count: int
    blockers: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    candidate_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_sleeve_promotion_candidate:bist_scope_leakage")
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            reasons.append("paper_sleeve_promotion_candidate:forbidden_scope_token")
    return tuple(reasons)


def _promotion_status(eligible: int, blocked: int, insufficient: int) -> PaperSleevePromotionCandidateStatus:
    """Deterministic decision-level classification from the derived per-record counts (verdict only)."""
    if eligible > 0:
        return PaperSleevePromotionCandidateStatus.ELIGIBLE
    if blocked == 0 and insufficient > 0:
        return PaperSleevePromotionCandidateStatus.INSUFFICIENT_EVIDENCE
    return PaperSleevePromotionCandidateStatus.BLOCKED


def build_paper_sleeve_promotion_candidate(
    journal_entry: EvidenceJournalEntry,
    decision: PaperSleeveRiskBudgetDecision,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleevePromotionCandidate:
    """Classify a journal-anchored ``PaperSleeveRiskBudgetDecision`` into a promotion candidate (verdict only).

    ``journal_entry`` must be an ``EvidenceJournalEntry`` of type ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` whose
    ``correlation_id`` equals the caller-asserted journaling ``correlation_id``, whose ``payload`` equals
    ``paper_sleeve_risk_budget_decision_to_dict(decision)``, and whose ``payload_digest`` equals the canonical
    digest of that payload; ``decision`` must be a ``PaperSleeveRiskBudgetDecision`` whose ``decision_digest``
    re-proves, whose paper-safety triple (and every record's) is exact, and whose stored counts equal the
    derived counts. Any violation raises ``PaperSleevePromotionCandidateError`` before a candidate is built.
    Returns ELIGIBLE / BLOCKED / INSUFFICIENT_EVIDENCE — a consideration verdict, **never** an execution
    permission: this gate reserves no capital, allocates nothing, routes/fills no order, and mutates nothing.
    """
    if not isinstance(journal_entry, EvidenceJournalEntry):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:journal_entry_malformed")
    if not isinstance(decision, PaperSleeveRiskBudgetDecision):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:correlation_id_invalid")
    candidate_metadata = _normalize_metadata(metadata)
    if _scope_violations(correlation_id, *_metadata_texts(candidate_metadata)):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:scope_violation")

    if decision.schema_version != _EXPECTED_DECISION_SCHEMA_VERSION:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_schema_version_unexpected")
    if decision.paper_only is not True:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_not_paper_only")
    if decision.real_orders_enabled is not False:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_real_orders_enabled")
    if decision.real_money_enabled is not False:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_real_money_enabled")

    # Serialize + recompute digests via the public helpers. A malformed decision artifact surfaces as a clean
    # adapter error, never a raw AttributeError/TypeError/ValueError. BaseException is deliberately not caught.
    try:
        payload = paper_sleeve_risk_budget_decision_to_dict(decision)
        expected_decision_digest = paper_sleeve_risk_budget_decision_digest(decision)
        expected_payload_digest = _canonical_digest(payload)
    except Exception as exc:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_malformed") from exc

    if expected_decision_digest != decision.decision_digest:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:decision_digest_mismatch")

    # Per-record paper-safety + derive counts (never trust the stored counts blindly).
    eligible = 0
    blocked = 0
    insufficient = 0
    for record in decision.record_decisions:
        if (
            record.paper_only is not True
            or record.real_orders_enabled is not False
            or record.real_money_enabled is not False
        ):
            raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:record_decision_not_paper_safe")
        if record.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE:
            eligible += 1
        elif record.status is PaperSleeveRiskBudgetRecordStatus.BLOCKED:
            blocked += 1
        elif record.status is PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE:
            insufficient += 1
        else:
            raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:record_status_malformed")
    if (eligible, blocked, insufficient) != (
        decision.eligible_count,
        decision.blocked_count,
        decision.insufficient_count,
    ):
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:count_mismatch")

    # Journal anchoring: the decision must be anchored in a PAPER_SLEEVE_RISK_BUDGET_DECISION entry whose
    # correlation matches and whose payload/digest re-prove this exact decision (bare decision is not enough).
    if journal_entry.entry_type is not EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION:
        raise PaperSleevePromotionCandidateError(
            "paper_sleeve_promotion_candidate:journal_entry_artifact_type_mismatch"
        )
    if not _is_non_empty_string(journal_entry.correlation_id) or journal_entry.correlation_id != correlation_id:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:journal_correlation_id_mismatch")
    if not isinstance(journal_entry.payload, Mapping) or dict(journal_entry.payload) != payload:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:journal_payload_mismatch")
    if not isinstance(journal_entry.payload_digest, str) or journal_entry.payload_digest != expected_payload_digest:
        raise PaperSleevePromotionCandidateError("paper_sleeve_promotion_candidate:journal_payload_digest_mismatch")

    status = _promotion_status(eligible, blocked, insufficient)
    blockers = _sorted_unique(tuple(decision.blockers))
    candidate = PaperSleevePromotionCandidate(
        schema_version=_CANDIDATE_SCHEMA_VERSION,
        status=status,
        sleeve_id=decision.sleeve_id,
        policy_id=decision.policy_id,
        decision_digest=decision.decision_digest,
        journal_payload_digest=journal_entry.payload_digest,
        journal_entry_digest=journal_entry.entry_digest,
        eligible_count=eligible,
        blocked_count=blocked,
        insufficient_count=insufficient,
        blockers=blockers,
        correlation_id=correlation_id,
        metadata=candidate_metadata,
        candidate_digest="",
    )
    return PaperSleevePromotionCandidate(
        schema_version=candidate.schema_version,
        status=candidate.status,
        sleeve_id=candidate.sleeve_id,
        policy_id=candidate.policy_id,
        decision_digest=candidate.decision_digest,
        journal_payload_digest=candidate.journal_payload_digest,
        journal_entry_digest=candidate.journal_entry_digest,
        eligible_count=candidate.eligible_count,
        blocked_count=candidate.blocked_count,
        insufficient_count=candidate.insufficient_count,
        blockers=candidate.blockers,
        correlation_id=candidate.correlation_id,
        metadata=candidate.metadata,
        candidate_digest=paper_sleeve_promotion_candidate_digest(candidate),
    )


def _candidate_payload(
    *,
    schema_version: str,
    status_value: str,
    sleeve_id: str,
    policy_id: str,
    decision_digest: str,
    journal_payload_digest: str,
    journal_entry_digest: str,
    eligible_count: int,
    blocked_count: int,
    insufficient_count: int,
    blockers: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "sleeve_id": sleeve_id,
        "policy_id": policy_id,
        "decision_digest": decision_digest,
        "journal_payload_digest": journal_payload_digest,
        "journal_entry_digest": journal_entry_digest,
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "insufficient_count": insufficient_count,
        "blockers": list(blockers),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def paper_sleeve_promotion_candidate_to_dict(candidate: PaperSleevePromotionCandidate) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a promotion candidate (deterministic shape, includes self-digest)."""
    payload = _candidate_payload(
        schema_version=candidate.schema_version,
        status_value=candidate.status.value,
        sleeve_id=candidate.sleeve_id,
        policy_id=candidate.policy_id,
        decision_digest=candidate.decision_digest,
        journal_payload_digest=candidate.journal_payload_digest,
        journal_entry_digest=candidate.journal_entry_digest,
        eligible_count=candidate.eligible_count,
        blocked_count=candidate.blocked_count,
        insufficient_count=candidate.insufficient_count,
        blockers=candidate.blockers,
        correlation_id=candidate.correlation_id,
        metadata=candidate.metadata,
        paper_only=candidate.paper_only,
        real_orders_enabled=candidate.real_orders_enabled,
        real_money_enabled=candidate.real_money_enabled,
    )
    payload["candidate_digest"] = candidate.candidate_digest
    return payload


def paper_sleeve_promotion_candidate_digest(candidate: PaperSleevePromotionCandidate) -> str:
    """Recompute the canonical candidate digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _candidate_payload(
            schema_version=candidate.schema_version,
            status_value=candidate.status.value,
            sleeve_id=candidate.sleeve_id,
            policy_id=candidate.policy_id,
            decision_digest=candidate.decision_digest,
            journal_payload_digest=candidate.journal_payload_digest,
            journal_entry_digest=candidate.journal_entry_digest,
            eligible_count=candidate.eligible_count,
            blocked_count=candidate.blocked_count,
            insufficient_count=candidate.insufficient_count,
            blockers=candidate.blockers,
            correlation_id=candidate.correlation_id,
            metadata=candidate.metadata,
            paper_only=candidate.paper_only,
            real_orders_enabled=candidate.real_orders_enabled,
            real_money_enabled=candidate.real_money_enabled,
        )
    )


__all__ = [
    "PaperSleevePromotionCandidate",
    "PaperSleevePromotionCandidateError",
    "PaperSleevePromotionCandidateStatus",
    "build_paper_sleeve_promotion_candidate",
    "paper_sleeve_promotion_candidate_digest",
    "paper_sleeve_promotion_candidate_to_dict",
]
