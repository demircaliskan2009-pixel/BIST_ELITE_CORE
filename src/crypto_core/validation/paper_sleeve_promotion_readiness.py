"""Paper sleeve promotion readiness — deterministic, paper-only read model over a journaled promotion candidate.

A small, immutable, fail-closed *read-model gate* that classifies whether a **journal-anchored**
``PaperSleevePromotionCandidate`` is ready to be *considered* by a future allocator / paper runner. It is the
seam after the promotion-candidate journal bridge: a downstream consumer must read a candidate that is
anchored in the ``EvidenceJournal`` (a ``PAPER_SLEEVE_PROMOTION_CANDIDATE`` entry whose payload/digest re-prove
the candidate) **and** whose upstream risk-budget-decision anchor (``PAPER_SLEEVE_RISK_BUDGET_DECISION``) is
present in the *same* evidence chain — never a bare candidate. READY here means *ready for consideration*,
**never an execution permission**: this module reserves no capital, allocates nothing, creates/routes/fills no
order, computes no PnL, mutates no state, and appends nothing to the journal — no DB/file/network/env IO, no
wall-clock, no random, no threading, no connector/scheduler/runtime/live/shadow surface, no BIST.

Design rules:
  - Same-chain journal anchoring is mandatory: the supplied promotion-candidate ``EvidenceJournalEntry`` must be
    present in the target journal (``journal.get_by_entry_digest``), be a ``PAPER_SLEEVE_PROMOTION_CANDIDATE``
    entry whose ``payload`` equals ``paper_sleeve_promotion_candidate_to_dict(candidate)`` and whose
    ``payload_digest`` / self ``entry_digest`` re-prove. The candidate's recorded upstream anchor
    (``candidate.journal_entry_digest``) must ALSO resolve in the same journal to a
    ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` entry whose self-digest re-proves and whose ``payload_digest`` equals
    ``candidate.journal_payload_digest``. A bare candidate, or one whose anchors live outside this chain, is
    rejected — the candidate alone is never enough.
  - Candidate re-proof: ``candidate.candidate_digest`` is recomputed via the public
    ``paper_sleeve_promotion_candidate_digest`` and a mismatch is rejected; the candidate must attest the exact
    paper-safety triple (``paper_only=True``, real orders/money ``False``).
  - Deterministic classification: READY iff the journaled candidate is ELIGIBLE; BLOCKED iff BLOCKED;
    INSUFFICIENT_EVIDENCE iff INSUFFICIENT_EVIDENCE — all only after every journal/provenance check passes.
    Classification is a consideration verdict, not a capital action.
  - Deterministic digest: canonical SHA-256 over the public serializer output excluding the self-digest.
    Frozen dataclass; stable sorted blockers; no input is mutated; the journal is never appended to.
  - Fail closed: a wrong-typed input, an empty/forbidden ``correlation_id``/metadata, a missing/forged journal
    anchor, an artifact-type mismatch, a digest mismatch, an unsafe paper-safety flag, or a malformed candidate
    raises ``PaperSleevePromotionReadinessError`` before any readiness is built.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
    EvidenceJournalError,
    evidence_journal_entry_digest,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    PaperSleevePromotionCandidate,
    PaperSleevePromotionCandidateStatus,
    paper_sleeve_promotion_candidate_digest,
    paper_sleeve_promotion_candidate_to_dict,
)

_READINESS_SCHEMA_VERSION = "paper-sleeve-promotion-readiness.v1"
_EXPECTED_CANDIDATE_SCHEMA_VERSION = "paper-sleeve-promotion-candidate.v1"

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


class PaperSleevePromotionReadinessError(RuntimeError):
    """Raised when a journaled promotion candidate fails type/anchoring/digest/safety re-proof."""


class PaperSleevePromotionReadinessStatus(str, Enum):
    """Promotion-consideration readiness of a journaled candidate. Never an execution permission."""

    READY = "READY"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSleevePromotionReadiness:
    """Deterministic, immutable read model: a same-chain journal-anchored candidate's readiness. PAPER ONLY."""

    schema_version: str
    status: PaperSleevePromotionReadinessStatus
    sleeve_id: str
    policy_id: str
    candidate_digest: str
    promotion_candidate_journal_entry_digest: str
    promotion_candidate_payload_digest: str
    decision_journal_entry_digest: str
    decision_journal_payload_digest: str
    eligible_count: int
    blocked_count: int
    insufficient_count: int
    blockers: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    readiness_digest: str
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
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:metadata_malformed")
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
            reasons.append("paper_sleeve_promotion_readiness:bist_scope_leakage")
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            reasons.append("paper_sleeve_promotion_readiness:forbidden_scope_token")
    return tuple(reasons)


def _readiness_status(candidate_status: object) -> PaperSleevePromotionReadinessStatus:
    """Map the journaled candidate status to a readiness verdict (1:1, verdict only)."""
    if candidate_status is PaperSleevePromotionCandidateStatus.ELIGIBLE:
        return PaperSleevePromotionReadinessStatus.READY
    if candidate_status is PaperSleevePromotionCandidateStatus.BLOCKED:
        return PaperSleevePromotionReadinessStatus.BLOCKED
    if candidate_status is PaperSleevePromotionCandidateStatus.INSUFFICIENT_EVIDENCE:
        return PaperSleevePromotionReadinessStatus.INSUFFICIENT_EVIDENCE
    raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_status_malformed")


def build_paper_sleeve_promotion_readiness(
    journal: EvidenceJournal,
    promotion_candidate_journal_entry: EvidenceJournalEntry,
    candidate: PaperSleevePromotionCandidate,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleevePromotionReadiness:
    """Classify a same-chain journal-anchored ``PaperSleevePromotionCandidate`` into a readiness (verdict only).

    ``journal`` must be an ``EvidenceJournal`` that contains BOTH the supplied
    ``promotion_candidate_journal_entry`` (a ``PAPER_SLEEVE_PROMOTION_CANDIDATE`` entry re-proving ``candidate``)
    and the candidate's upstream ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` anchor
    (``candidate.journal_entry_digest``). Any violation raises ``PaperSleevePromotionReadinessError`` before a
    readiness is built. Returns READY / BLOCKED / INSUFFICIENT_EVIDENCE — a consideration verdict, **never** an
    execution permission: this gate reserves no capital, allocates nothing, routes/fills no order, appends
    nothing to the journal, and mutates nothing.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:journal_malformed")
    if not isinstance(promotion_candidate_journal_entry, EvidenceJournalEntry):
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:promotion_candidate_entry_malformed")
    if not isinstance(candidate, PaperSleevePromotionCandidate):
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:correlation_id_invalid")
    readiness_metadata = _normalize_metadata(metadata)
    if _scope_violations(correlation_id, *_metadata_texts(readiness_metadata)):
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:scope_violation")

    if candidate.schema_version != _EXPECTED_CANDIDATE_SCHEMA_VERSION:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_schema_version_unexpected")
    if candidate.paper_only is not True:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_not_paper_only")
    if candidate.real_orders_enabled is not False:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_real_orders_enabled")
    if candidate.real_money_enabled is not False:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_real_money_enabled")

    # Serialize + recompute the candidate self-digest via the public helpers. A malformed candidate artifact
    # surfaces as a clean error, never a raw AttributeError/TypeError/ValueError. BaseException is not caught.
    try:
        candidate_payload = paper_sleeve_promotion_candidate_to_dict(candidate)
        expected_candidate_digest = paper_sleeve_promotion_candidate_digest(candidate)
        expected_payload_digest = _canonical_digest(candidate_payload)
    except Exception as exc:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_malformed") from exc
    if not isinstance(candidate.candidate_digest, str) or candidate.candidate_digest != expected_candidate_digest:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:candidate_digest_mismatch")

    # Same-chain anchoring (1): the promotion-candidate entry must be present in the target journal and re-prove
    # the candidate. ``get_by_entry_digest`` verifies the whole chain, so a corrupt journal also fails closed.
    try:
        journal.get_by_entry_digest(promotion_candidate_journal_entry.entry_digest)
    except EvidenceJournalError as exc:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_entry_not_in_journal"
        ) from exc
    if promotion_candidate_journal_entry.entry_type is not EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_entry_artifact_type_mismatch"
        )
    if (
        not isinstance(promotion_candidate_journal_entry.payload, Mapping)
        or dict(promotion_candidate_journal_entry.payload) != candidate_payload
    ):
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_payload_mismatch"
        )
    if (
        not isinstance(promotion_candidate_journal_entry.payload_digest, str)
        or promotion_candidate_journal_entry.payload_digest != expected_payload_digest
    ):
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_payload_digest_mismatch"
        )
    try:
        expected_pce_entry_digest = evidence_journal_entry_digest(promotion_candidate_journal_entry)
    except Exception as exc:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_entry_malformed"
        ) from exc
    if (
        not isinstance(promotion_candidate_journal_entry.entry_digest, str)
        or promotion_candidate_journal_entry.entry_digest != expected_pce_entry_digest
    ):
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:promotion_candidate_entry_digest_mismatch"
        )

    # Same-chain anchoring (2): the candidate's upstream risk-budget-decision anchor must resolve in the SAME
    # journal to a PAPER_SLEEVE_RISK_BUDGET_DECISION entry whose self-digest re-proves and whose payload_digest
    # equals the candidate's recorded ``journal_payload_digest``.
    try:
        decision_entry = journal.get_by_entry_digest(candidate.journal_entry_digest)
    except EvidenceJournalError as exc:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:decision_entry_not_in_journal"
        ) from exc
    if decision_entry.entry_type is not EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:decision_entry_artifact_type_mismatch"
        )
    try:
        expected_decision_entry_digest = evidence_journal_entry_digest(decision_entry)
    except Exception as exc:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:decision_entry_malformed") from exc
    if decision_entry.entry_digest != expected_decision_entry_digest:
        raise PaperSleevePromotionReadinessError("paper_sleeve_promotion_readiness:decision_entry_digest_mismatch")
    if candidate.journal_payload_digest != decision_entry.payload_digest:
        raise PaperSleevePromotionReadinessError(
            "paper_sleeve_promotion_readiness:decision_journal_payload_digest_mismatch"
        )

    status = _readiness_status(candidate.status)
    blockers = _sorted_unique(tuple(candidate.blockers))
    readiness = PaperSleevePromotionReadiness(
        schema_version=_READINESS_SCHEMA_VERSION,
        status=status,
        sleeve_id=candidate.sleeve_id,
        policy_id=candidate.policy_id,
        candidate_digest=candidate.candidate_digest,
        promotion_candidate_journal_entry_digest=promotion_candidate_journal_entry.entry_digest,
        promotion_candidate_payload_digest=promotion_candidate_journal_entry.payload_digest,
        decision_journal_entry_digest=candidate.journal_entry_digest,
        decision_journal_payload_digest=candidate.journal_payload_digest,
        eligible_count=candidate.eligible_count,
        blocked_count=candidate.blocked_count,
        insufficient_count=candidate.insufficient_count,
        blockers=blockers,
        correlation_id=correlation_id,
        metadata=readiness_metadata,
        readiness_digest="",
    )
    return PaperSleevePromotionReadiness(
        schema_version=readiness.schema_version,
        status=readiness.status,
        sleeve_id=readiness.sleeve_id,
        policy_id=readiness.policy_id,
        candidate_digest=readiness.candidate_digest,
        promotion_candidate_journal_entry_digest=readiness.promotion_candidate_journal_entry_digest,
        promotion_candidate_payload_digest=readiness.promotion_candidate_payload_digest,
        decision_journal_entry_digest=readiness.decision_journal_entry_digest,
        decision_journal_payload_digest=readiness.decision_journal_payload_digest,
        eligible_count=readiness.eligible_count,
        blocked_count=readiness.blocked_count,
        insufficient_count=readiness.insufficient_count,
        blockers=readiness.blockers,
        correlation_id=readiness.correlation_id,
        metadata=readiness.metadata,
        readiness_digest=paper_sleeve_promotion_readiness_digest(readiness),
    )


def _readiness_payload(
    *,
    schema_version: str,
    status_value: str,
    sleeve_id: str,
    policy_id: str,
    candidate_digest: str,
    promotion_candidate_journal_entry_digest: str,
    promotion_candidate_payload_digest: str,
    decision_journal_entry_digest: str,
    decision_journal_payload_digest: str,
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
        "candidate_digest": candidate_digest,
        "promotion_candidate_journal_entry_digest": promotion_candidate_journal_entry_digest,
        "promotion_candidate_payload_digest": promotion_candidate_payload_digest,
        "decision_journal_entry_digest": decision_journal_entry_digest,
        "decision_journal_payload_digest": decision_journal_payload_digest,
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


def paper_sleeve_promotion_readiness_to_dict(readiness: PaperSleevePromotionReadiness) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a readiness record (deterministic shape, includes self-digest)."""
    payload = _readiness_payload(
        schema_version=readiness.schema_version,
        status_value=readiness.status.value,
        sleeve_id=readiness.sleeve_id,
        policy_id=readiness.policy_id,
        candidate_digest=readiness.candidate_digest,
        promotion_candidate_journal_entry_digest=readiness.promotion_candidate_journal_entry_digest,
        promotion_candidate_payload_digest=readiness.promotion_candidate_payload_digest,
        decision_journal_entry_digest=readiness.decision_journal_entry_digest,
        decision_journal_payload_digest=readiness.decision_journal_payload_digest,
        eligible_count=readiness.eligible_count,
        blocked_count=readiness.blocked_count,
        insufficient_count=readiness.insufficient_count,
        blockers=readiness.blockers,
        correlation_id=readiness.correlation_id,
        metadata=readiness.metadata,
        paper_only=readiness.paper_only,
        real_orders_enabled=readiness.real_orders_enabled,
        real_money_enabled=readiness.real_money_enabled,
    )
    payload["readiness_digest"] = readiness.readiness_digest
    return payload


def paper_sleeve_promotion_readiness_digest(readiness: PaperSleevePromotionReadiness) -> str:
    """Recompute the canonical readiness digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _readiness_payload(
            schema_version=readiness.schema_version,
            status_value=readiness.status.value,
            sleeve_id=readiness.sleeve_id,
            policy_id=readiness.policy_id,
            candidate_digest=readiness.candidate_digest,
            promotion_candidate_journal_entry_digest=readiness.promotion_candidate_journal_entry_digest,
            promotion_candidate_payload_digest=readiness.promotion_candidate_payload_digest,
            decision_journal_entry_digest=readiness.decision_journal_entry_digest,
            decision_journal_payload_digest=readiness.decision_journal_payload_digest,
            eligible_count=readiness.eligible_count,
            blocked_count=readiness.blocked_count,
            insufficient_count=readiness.insufficient_count,
            blockers=readiness.blockers,
            correlation_id=readiness.correlation_id,
            metadata=readiness.metadata,
            paper_only=readiness.paper_only,
            real_orders_enabled=readiness.real_orders_enabled,
            real_money_enabled=readiness.real_money_enabled,
        )
    )


__all__ = [
    "PaperSleevePromotionReadiness",
    "PaperSleevePromotionReadinessError",
    "PaperSleevePromotionReadinessStatus",
    "build_paper_sleeve_promotion_readiness",
    "paper_sleeve_promotion_readiness_digest",
    "paper_sleeve_promotion_readiness_to_dict",
]
