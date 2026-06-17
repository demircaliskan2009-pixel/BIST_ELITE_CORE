"""Paper allocator intent draft — deterministic, paper-only read model over a journaled promotion readiness.

A small, immutable, fail-closed *read-model / draft contract* that says: "this **journal-anchored**
``PaperSleevePromotionReadiness`` is eligible to be *considered* by a future allocator capacity gate." It is the
seam after the promotion-readiness journal bridge: a downstream paper allocator / paper runner must read a
readiness that is anchored in the ``EvidenceJournal`` (a ``PAPER_SLEEVE_PROMOTION_READINESS`` entry whose
payload/digest re-prove the readiness) whose full upstream chain (the ``PAPER_SLEEVE_PROMOTION_CANDIDATE`` and
``PAPER_SLEEVE_RISK_BUDGET_DECISION`` anchors) also lives in the same chain — never a bare readiness.

DRAFT_READY here means *eligible for draft consideration*, **never an execution permission, never a capital
reservation, never an order**. This module reserves no capital, allocates nothing, creates/routes/fills no
order, computes no PnL, mutates no journal/state/portfolio/position, and appends nothing to the journal — no
DB/file/network/env IO, no wall-clock, no random, no threading, no connector/scheduler/runtime/live/shadow
surface, no BIST. The draft payload carries explicit negative attestations (``capital_reserved=False``,
``execution_authorized=False``, ``order_created=False``, ``fill_created=False``, ``position_mutated=False``) to
make the non-execution contract auditable.

Design rules:
  - Same-chain journal anchoring is mandatory: the supplied promotion-readiness ``EvidenceJournalEntry`` must be
    present in the target journal (``journal.get_by_entry_digest``), be a ``PAPER_SLEEVE_PROMOTION_READINESS``
    entry whose ``payload`` equals ``paper_sleeve_promotion_readiness_to_dict(readiness)`` and whose
    ``payload_digest`` / self ``entry_digest`` re-prove. The readiness's recorded upstream anchors
    (``promotion_candidate_journal_entry_digest`` and ``decision_journal_entry_digest``) must ALSO resolve in the
    same journal to a ``PAPER_SLEEVE_PROMOTION_CANDIDATE`` and a ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` entry
    respectively. A bare readiness, or one whose anchors live outside this chain, is rejected.
  - Readiness re-proof: ``readiness.readiness_digest`` is recomputed via the public
    ``paper_sleeve_promotion_readiness_digest`` and a mismatch is rejected; the readiness must attest the exact
    paper-safety triple (``paper_only=True``, real orders/money ``False``).
  - Deterministic classification: READY -> DRAFT_READY, BLOCKED -> BLOCKED,
    INSUFFICIENT_EVIDENCE -> INSUFFICIENT_EVIDENCE — only after every journal/provenance check passes. The verdict
    is a draft-consideration state, not a capital action.
  - Deterministic digest: canonical SHA-256 over the public serializer output excluding the self-digest. Frozen
    dataclass; stable sorted blockers; no input is mutated; the journal is never appended to.
  - Fail closed: a wrong-typed input, an empty/forbidden ``correlation_id``/metadata, a missing/forged journal
    anchor, an artifact-type mismatch, a digest mismatch, an unsafe paper-safety flag, or a malformed readiness
    raises ``PaperAllocatorIntentDraftError`` before any draft is built.
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
from crypto_core.validation.paper_sleeve_promotion_candidate import PaperSleevePromotionCandidateStatus
from crypto_core.validation.paper_sleeve_promotion_readiness import (
    PaperSleevePromotionReadiness,
    PaperSleevePromotionReadinessStatus,
    _readiness_status,
    paper_sleeve_promotion_readiness_digest,
    paper_sleeve_promotion_readiness_to_dict,
)

_DRAFT_SCHEMA_VERSION = "paper-allocator-intent-draft.v1"
_EXPECTED_READINESS_SCHEMA_VERSION = "paper-sleeve-promotion-readiness.v1"

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


class PaperAllocatorIntentDraftError(RuntimeError):
    """Raised when a journaled promotion readiness fails type/anchoring/digest/safety re-proof."""


class PaperAllocatorIntentDraftStatus(str, Enum):
    """Allocator-intent draft classification of a journaled readiness. Never an execution permission."""

    DRAFT_READY = "DRAFT_READY"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperAllocatorIntentDraft:
    """Deterministic, immutable read model: a same-chain journal-anchored readiness's draft eligibility.

    PAPER ONLY. DRAFT_READY is a draft-consideration state, never an execution permission / capital reservation /
    order. The explicit negative attestations are always False.
    """

    schema_version: str
    status: PaperAllocatorIntentDraftStatus
    sleeve_id: str
    policy_id: str
    readiness_digest: str
    promotion_readiness_journal_entry_digest: str
    promotion_readiness_payload_digest: str
    promotion_candidate_journal_entry_digest: str
    decision_journal_entry_digest: str
    decision_journal_payload_digest: str
    eligible_count: int
    blocked_count: int
    insufficient_count: int
    blockers: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    draft_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    execution_authorized: bool = False
    order_created: bool = False
    fill_created: bool = False
    position_mutated: bool = False


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
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:metadata_malformed")
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
            reasons.append("paper_allocator_intent_draft:bist_scope_leakage")
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            reasons.append("paper_allocator_intent_draft:forbidden_scope_token")
    return tuple(reasons)


def _draft_status(readiness_status: object) -> PaperAllocatorIntentDraftStatus:
    """Map the journaled readiness status to a draft verdict (1:1, verdict only)."""
    if readiness_status is PaperSleevePromotionReadinessStatus.READY:
        return PaperAllocatorIntentDraftStatus.DRAFT_READY
    if readiness_status is PaperSleevePromotionReadinessStatus.BLOCKED:
        return PaperAllocatorIntentDraftStatus.BLOCKED
    if readiness_status is PaperSleevePromotionReadinessStatus.INSUFFICIENT_EVIDENCE:
        return PaperAllocatorIntentDraftStatus.INSUFFICIENT_EVIDENCE
    raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_status_malformed")


def _require_same_chain_anchor(
    journal: EvidenceJournal, entry_digest: str, expected_type: EvidenceArtifactType, *, missing: str, mismatch: str
) -> EvidenceJournalEntry:
    """Resolve ``entry_digest`` in ``journal`` and require ``expected_type``; return it or fail closed."""
    try:
        anchor = journal.get_by_entry_digest(entry_digest)
    except EvidenceJournalError as exc:
        raise PaperAllocatorIntentDraftError(missing) from exc
    if anchor.entry_type is not expected_type:
        raise PaperAllocatorIntentDraftError(mismatch)
    return anchor


def build_paper_allocator_intent_draft(
    journal: EvidenceJournal,
    promotion_readiness_journal_entry: EvidenceJournalEntry,
    readiness: PaperSleevePromotionReadiness,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperAllocatorIntentDraft:
    """Classify a same-chain journal-anchored ``PaperSleevePromotionReadiness`` into a draft (verdict only).

    ``journal`` must be an ``EvidenceJournal`` that contains the supplied ``promotion_readiness_journal_entry``
    (a ``PAPER_SLEEVE_PROMOTION_READINESS`` entry re-proving ``readiness``) and the readiness's full upstream
    chain (``PAPER_SLEEVE_PROMOTION_CANDIDATE`` and ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` anchors). Any violation
    raises ``PaperAllocatorIntentDraftError`` before a draft is built. Returns DRAFT_READY / BLOCKED /
    INSUFFICIENT_EVIDENCE — a draft-consideration verdict, **never** an execution permission / capital
    reservation / order: this gate reserves no capital, allocates nothing, routes/fills no order, appends nothing
    to the journal, and mutates nothing.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:journal_malformed")
    if not isinstance(promotion_readiness_journal_entry, EvidenceJournalEntry):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:promotion_readiness_entry_malformed")
    if not isinstance(readiness, PaperSleevePromotionReadiness):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:correlation_id_invalid")
    draft_metadata = _normalize_metadata(metadata)
    if _scope_violations(correlation_id, *_metadata_texts(draft_metadata)):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:scope_violation")

    if readiness.schema_version != _EXPECTED_READINESS_SCHEMA_VERSION:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_schema_version_unexpected")
    if readiness.paper_only is not True:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_not_paper_only")
    if readiness.real_orders_enabled is not False:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_real_orders_enabled")
    if readiness.real_money_enabled is not False:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_real_money_enabled")

    # Serialize + recompute the readiness self-digest via the public helpers. A malformed readiness artifact
    # surfaces as a clean error, never a raw AttributeError/TypeError/ValueError. BaseException is not caught.
    try:
        readiness_payload = paper_sleeve_promotion_readiness_to_dict(readiness)
        expected_readiness_digest = paper_sleeve_promotion_readiness_digest(readiness)
        expected_payload_digest = _canonical_digest(readiness_payload)
    except Exception as exc:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_malformed") from exc
    if not isinstance(readiness.readiness_digest, str) or readiness.readiness_digest != expected_readiness_digest:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_digest_mismatch")

    # Same-chain anchoring (1): the promotion-readiness entry must be present in the target journal and re-prove
    # the readiness. ``get_by_entry_digest`` verifies the whole chain, so a corrupt journal also fails closed.
    try:
        journal.get_by_entry_digest(promotion_readiness_journal_entry.entry_digest)
    except EvidenceJournalError as exc:
        raise PaperAllocatorIntentDraftError(
            "paper_allocator_intent_draft:promotion_readiness_entry_not_in_journal"
        ) from exc
    if promotion_readiness_journal_entry.entry_type is not EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS:
        raise PaperAllocatorIntentDraftError(
            "paper_allocator_intent_draft:promotion_readiness_entry_artifact_type_mismatch"
        )
    if (
        not isinstance(promotion_readiness_journal_entry.payload, Mapping)
        or dict(promotion_readiness_journal_entry.payload) != readiness_payload
    ):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:promotion_readiness_payload_mismatch")
    if (
        not isinstance(promotion_readiness_journal_entry.payload_digest, str)
        or promotion_readiness_journal_entry.payload_digest != expected_payload_digest
    ):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:promotion_readiness_payload_digest_mismatch")
    try:
        expected_pre_entry_digest = evidence_journal_entry_digest(promotion_readiness_journal_entry)
    except Exception as exc:
        raise PaperAllocatorIntentDraftError(
            "paper_allocator_intent_draft:promotion_readiness_entry_malformed"
        ) from exc
    if (
        not isinstance(promotion_readiness_journal_entry.entry_digest, str)
        or promotion_readiness_journal_entry.entry_digest != expected_pre_entry_digest
    ):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:promotion_readiness_entry_digest_mismatch")

    # Same-chain anchoring (2): the readiness's recorded upstream anchors must ALSO resolve in the same journal
    # to the expected artifact types, so a downstream reader can resolve the full chain within THIS journal.
    candidate_anchor = _require_same_chain_anchor(
        journal,
        readiness.promotion_candidate_journal_entry_digest,
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE,
        missing="paper_allocator_intent_draft:promotion_candidate_anchor_not_in_journal",
        mismatch="paper_allocator_intent_draft:promotion_candidate_anchor_artifact_type_mismatch",
    )
    decision_anchor = _require_same_chain_anchor(
        journal,
        readiness.decision_journal_entry_digest,
        EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION,
        missing="paper_allocator_intent_draft:decision_anchor_not_in_journal",
        mismatch="paper_allocator_intent_draft:decision_anchor_artifact_type_mismatch",
    )

    # Re-prove the readiness's recorded verdict/provenance fields back against the ACTUAL anchored entries. The
    # anchors merely existing with the right artifact types is not enough: a readiness raw-appended via the public
    # ``EvidenceJournal.append`` (bypassing the readiness adapter's rebuild) could point at a BLOCKED candidate
    # entry yet reseal itself READY. So the candidate anchor payload is bound to the readiness's candidate-derived
    # fields (payload digest, candidate_digest, identity, counts, blockers) and the readiness status is re-derived
    # from the anchored candidate's own status via the readiness gate's rule before the draft verdict is mapped.
    candidate_payload = candidate_anchor.payload
    if not isinstance(candidate_payload, Mapping):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:promotion_candidate_anchor_malformed")
    if candidate_anchor.payload_digest != readiness.promotion_candidate_payload_digest:
        raise PaperAllocatorIntentDraftError(
            "paper_allocator_intent_draft:promotion_candidate_anchor_payload_digest_mismatch"
        )
    if candidate_payload.get("candidate_digest") != readiness.candidate_digest:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_candidate_digest_mismatch")
    if (
        candidate_payload.get("sleeve_id") != readiness.sleeve_id
        or candidate_payload.get("policy_id") != readiness.policy_id
    ):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_identity_mismatch")
    if (
        candidate_payload.get("eligible_count") != readiness.eligible_count
        or candidate_payload.get("blocked_count") != readiness.blocked_count
        or candidate_payload.get("insufficient_count") != readiness.insufficient_count
    ):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_counts_mismatch")
    candidate_blockers = candidate_payload.get("blockers")
    if not isinstance(candidate_blockers, list) or readiness.blockers != _sorted_unique(tuple(candidate_blockers)):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_blockers_mismatch")
    try:
        anchored_candidate_status = PaperSleevePromotionCandidateStatus(candidate_payload.get("status"))
    except (ValueError, TypeError) as exc:
        raise PaperAllocatorIntentDraftError(
            "paper_allocator_intent_draft:promotion_candidate_anchor_malformed"
        ) from exc
    if readiness.status is not _readiness_status(anchored_candidate_status):
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:readiness_status_inconsistent")
    if decision_anchor.payload_digest != readiness.decision_journal_payload_digest:
        raise PaperAllocatorIntentDraftError("paper_allocator_intent_draft:decision_anchor_payload_digest_mismatch")

    status = _draft_status(readiness.status)
    blockers = _sorted_unique(tuple(readiness.blockers))
    draft = PaperAllocatorIntentDraft(
        schema_version=_DRAFT_SCHEMA_VERSION,
        status=status,
        sleeve_id=readiness.sleeve_id,
        policy_id=readiness.policy_id,
        readiness_digest=readiness.readiness_digest,
        promotion_readiness_journal_entry_digest=promotion_readiness_journal_entry.entry_digest,
        promotion_readiness_payload_digest=promotion_readiness_journal_entry.payload_digest,
        promotion_candidate_journal_entry_digest=readiness.promotion_candidate_journal_entry_digest,
        decision_journal_entry_digest=readiness.decision_journal_entry_digest,
        decision_journal_payload_digest=readiness.decision_journal_payload_digest,
        eligible_count=readiness.eligible_count,
        blocked_count=readiness.blocked_count,
        insufficient_count=readiness.insufficient_count,
        blockers=blockers,
        correlation_id=correlation_id,
        metadata=draft_metadata,
        draft_digest="",
    )
    return PaperAllocatorIntentDraft(
        schema_version=draft.schema_version,
        status=draft.status,
        sleeve_id=draft.sleeve_id,
        policy_id=draft.policy_id,
        readiness_digest=draft.readiness_digest,
        promotion_readiness_journal_entry_digest=draft.promotion_readiness_journal_entry_digest,
        promotion_readiness_payload_digest=draft.promotion_readiness_payload_digest,
        promotion_candidate_journal_entry_digest=draft.promotion_candidate_journal_entry_digest,
        decision_journal_entry_digest=draft.decision_journal_entry_digest,
        decision_journal_payload_digest=draft.decision_journal_payload_digest,
        eligible_count=draft.eligible_count,
        blocked_count=draft.blocked_count,
        insufficient_count=draft.insufficient_count,
        blockers=draft.blockers,
        correlation_id=draft.correlation_id,
        metadata=draft.metadata,
        draft_digest=paper_allocator_intent_draft_digest(draft),
    )


def _draft_payload(
    *,
    schema_version: str,
    status_value: str,
    sleeve_id: str,
    policy_id: str,
    readiness_digest: str,
    promotion_readiness_journal_entry_digest: str,
    promotion_readiness_payload_digest: str,
    promotion_candidate_journal_entry_digest: str,
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
    capital_reserved: bool,
    execution_authorized: bool,
    order_created: bool,
    fill_created: bool,
    position_mutated: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "sleeve_id": sleeve_id,
        "policy_id": policy_id,
        "readiness_digest": readiness_digest,
        "promotion_readiness_journal_entry_digest": promotion_readiness_journal_entry_digest,
        "promotion_readiness_payload_digest": promotion_readiness_payload_digest,
        "promotion_candidate_journal_entry_digest": promotion_candidate_journal_entry_digest,
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
        "capital_reserved": capital_reserved,
        "execution_authorized": execution_authorized,
        "order_created": order_created,
        "fill_created": fill_created,
        "position_mutated": position_mutated,
    }


def paper_allocator_intent_draft_to_dict(draft: PaperAllocatorIntentDraft) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an allocator-intent draft (deterministic shape, includes self-digest)."""
    payload = _draft_payload(
        schema_version=draft.schema_version,
        status_value=draft.status.value,
        sleeve_id=draft.sleeve_id,
        policy_id=draft.policy_id,
        readiness_digest=draft.readiness_digest,
        promotion_readiness_journal_entry_digest=draft.promotion_readiness_journal_entry_digest,
        promotion_readiness_payload_digest=draft.promotion_readiness_payload_digest,
        promotion_candidate_journal_entry_digest=draft.promotion_candidate_journal_entry_digest,
        decision_journal_entry_digest=draft.decision_journal_entry_digest,
        decision_journal_payload_digest=draft.decision_journal_payload_digest,
        eligible_count=draft.eligible_count,
        blocked_count=draft.blocked_count,
        insufficient_count=draft.insufficient_count,
        blockers=draft.blockers,
        correlation_id=draft.correlation_id,
        metadata=draft.metadata,
        paper_only=draft.paper_only,
        real_orders_enabled=draft.real_orders_enabled,
        real_money_enabled=draft.real_money_enabled,
        capital_reserved=draft.capital_reserved,
        execution_authorized=draft.execution_authorized,
        order_created=draft.order_created,
        fill_created=draft.fill_created,
        position_mutated=draft.position_mutated,
    )
    payload["draft_digest"] = draft.draft_digest
    return payload


def paper_allocator_intent_draft_digest(draft: PaperAllocatorIntentDraft) -> str:
    """Recompute the canonical draft digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _draft_payload(
            schema_version=draft.schema_version,
            status_value=draft.status.value,
            sleeve_id=draft.sleeve_id,
            policy_id=draft.policy_id,
            readiness_digest=draft.readiness_digest,
            promotion_readiness_journal_entry_digest=draft.promotion_readiness_journal_entry_digest,
            promotion_readiness_payload_digest=draft.promotion_readiness_payload_digest,
            promotion_candidate_journal_entry_digest=draft.promotion_candidate_journal_entry_digest,
            decision_journal_entry_digest=draft.decision_journal_entry_digest,
            decision_journal_payload_digest=draft.decision_journal_payload_digest,
            eligible_count=draft.eligible_count,
            blocked_count=draft.blocked_count,
            insufficient_count=draft.insufficient_count,
            blockers=draft.blockers,
            correlation_id=draft.correlation_id,
            metadata=draft.metadata,
            paper_only=draft.paper_only,
            real_orders_enabled=draft.real_orders_enabled,
            real_money_enabled=draft.real_money_enabled,
            capital_reserved=draft.capital_reserved,
            execution_authorized=draft.execution_authorized,
            order_created=draft.order_created,
            fill_created=draft.fill_created,
            position_mutated=draft.position_mutated,
        )
    )


__all__ = [
    "PaperAllocatorIntentDraft",
    "PaperAllocatorIntentDraftError",
    "PaperAllocatorIntentDraftStatus",
    "build_paper_allocator_intent_draft",
    "paper_allocator_intent_draft_digest",
    "paper_allocator_intent_draft_to_dict",
]
