"""Audit bridge: append an existing PaperSleevePromotionReadiness into the EvidenceJournal.

Anchors a paper-only promotion-readiness *read model* in the append-only evidence journal before any
downstream allocator-intent / paper runner can read it. The readiness gate *classifies* whether a same-chain
journal-anchored ``PaperSleevePromotionCandidate`` (whose upstream ``PAPER_SLEEVE_RISK_BUDGET_DECISION`` anchor
lives in the same chain) is ready to be *considered*; this bridge *journals* that classification under its own
``EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS`` — paper/audit only. It is not a runtime, allocator,
allocator-intent, promotion, scheduler, order router, connector, or execution path: no DB/file/network/env IO,
no clocks, no random, no threading, no orders/fills/PnL/position surface. It journals an already-built
readiness; it never allocates, reserves capital, promotes, executes, routes, schedules, connects, or mutates
anything.

Design rules:
  - Readiness self-proof: ``readiness.readiness_digest`` is recomputed via the public
    ``paper_sleeve_promotion_readiness_digest`` and a mismatch is rejected before any append. No hashing
    convention is duplicated here; the upstream serializer/digest is the single source of truth.
  - Same-chain provenance re-proof (the bridge's core invariant): the readiness must have been *built from the
    supplied same-chain journal-anchored candidate*. The bridge re-runs the public
    ``build_paper_sleeve_promotion_readiness`` on the SAME target ``journal`` + ``promotion_candidate_journal_entry``
    + ``candidate`` with the readiness's own ``correlation_id`` / ``metadata`` and requires an identical canonical
    payload (``paper_sleeve_promotion_readiness_to_dict``). Because that builder re-proves the full same-chain
    anchoring (the promotion-candidate entry is present in the journal and re-proves the candidate, and the
    candidate's upstream risk-budget-decision anchor is present in the same chain), a bare/forged/stale readiness
    whose self-digest was resealed but whose contents do not correspond to that journaled candidate is rejected
    before append.
  - Anchor cross-checks: the readiness's recorded provenance anchors must match the supplied inputs exactly —
    ``promotion_candidate_journal_entry.entry_digest == readiness.promotion_candidate_journal_entry_digest``,
    ``promotion_candidate_journal_entry.payload_digest == readiness.promotion_candidate_payload_digest``,
    ``candidate.journal_entry_digest == readiness.decision_journal_entry_digest``, and
    ``candidate.journal_payload_digest == readiness.decision_journal_payload_digest`` — and the upstream
    risk-budget-decision entry must resolve in the same target journal to a ``PAPER_SLEEVE_RISK_BUDGET_DECISION``.
  - Append the canonical dict only: the journaled payload is exactly
    ``paper_sleeve_promotion_readiness_to_dict(readiness)``; no caller-supplied ``payload_digest`` is trusted
    (the journal computes it and applies its own token/duplicate guards, not weakened here). The new entry is
    journaled under the caller-supplied audit ``correlation_id``.
  - Fail closed, no mutation before prechecks: a wrong-typed journal/readiness/entry/candidate, an empty
    ``correlation_id``, an unexpected schema, a malformed readiness artifact, a readiness-digest mismatch, an
    anchor mismatch, an unsafe paper-safety flag, or a readiness that does not re-build from the supplied
    same-chain candidate raises ``PaperSleevePromotionReadinessJournalAdapterError`` before any append, leaving
    the journal unchanged. Forbidden BIST/live/private/order/scheduler/connector/shadow tokens and duplicate
    payloads fail through the journal's own ``EvidenceJournalError`` guard.
"""

from __future__ import annotations

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
    EvidenceJournalError,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import PaperSleevePromotionCandidate
from crypto_core.validation.paper_sleeve_promotion_readiness import (
    PaperSleevePromotionReadiness,
    PaperSleevePromotionReadinessError,
    build_paper_sleeve_promotion_readiness,
    paper_sleeve_promotion_readiness_digest,
    paper_sleeve_promotion_readiness_to_dict,
)

# The readiness schema this bridge is written against. A bump is a coordinated, reviewed migration.
_EXPECTED_READINESS_SCHEMA_VERSION = "paper-sleeve-promotion-readiness.v1"


class PaperSleevePromotionReadinessJournalAdapterError(RuntimeError):
    """Raised when a readiness handed to the journal bridge fails type/digest/provenance re-proof."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def append_paper_sleeve_promotion_readiness_to_evidence_journal(
    journal: EvidenceJournal,
    readiness: PaperSleevePromotionReadiness,
    *,
    promotion_candidate_journal_entry: EvidenceJournalEntry,
    candidate: PaperSleevePromotionCandidate,
    correlation_id: str,
) -> EvidenceJournalEntry:
    """Append a re-proven ``PaperSleevePromotionReadiness`` as PAPER_SLEEVE_PROMOTION_READINESS.

    ``journal`` must be an ``EvidenceJournal`` that contains the readiness's same-chain anchors,
    ``readiness`` a ``PaperSleevePromotionReadiness``, ``promotion_candidate_journal_entry`` an
    ``EvidenceJournalEntry``, and ``candidate`` a ``PaperSleevePromotionCandidate``. The readiness is rejected
    before any append (journal unchanged) on a wrong type, an empty audit ``correlation_id``, an unexpected
    ``schema_version``, an unsafe paper-safety flag, a malformed readiness artifact, a readiness-digest mismatch,
    an anchor mismatch, a missing/wrong upstream decision anchor, or a readiness that does not re-build from the
    supplied same-chain ``promotion_candidate_journal_entry`` + ``candidate``. The journaled payload is exactly
    ``paper_sleeve_promotion_readiness_to_dict(readiness)``; the journal computes the payload digest and applies
    its own token/duplicate guards (forbidden tokens and replays surface as ``EvidenceJournalError``). Journals
    audit provenance only — no allocation, allocator-intent, promotion, execution, routing, fill, PnL, or
    position.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:journal_malformed"
        )
    if not isinstance(readiness, PaperSleevePromotionReadiness):
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_malformed"
        )
    if not isinstance(promotion_candidate_journal_entry, EvidenceJournalEntry):
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:promotion_candidate_entry_malformed"
        )
    if not isinstance(candidate, PaperSleevePromotionCandidate):
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:candidate_malformed"
        )
    if not _is_non_empty_string(correlation_id):
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:correlation_id_invalid"
        )
    if readiness.schema_version != _EXPECTED_READINESS_SCHEMA_VERSION:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_schema_version_unexpected"
        )

    # Paper-only invariant: a self-consistent (resealed) readiness can still attest ``paper_only=False`` or
    # enabled real orders/money. The journal token guard only covers the real-orders/real-money attestation
    # keys, so the bridge enforces the full paper-safety triple itself before journaling.
    if readiness.paper_only is not True:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_not_paper_only"
        )
    if readiness.real_orders_enabled is not False:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_real_orders_enabled"
        )
    if readiness.real_money_enabled is not False:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_real_money_enabled"
        )

    # Serialize + recompute the readiness self-digest via the public helpers. A malformed readiness artifact
    # surfaces as a clean adapter error, never a raw AttributeError/TypeError/ValueError. BaseException is
    # deliberately not caught.
    try:
        readiness_payload = paper_sleeve_promotion_readiness_to_dict(readiness)
        expected_readiness_digest = paper_sleeve_promotion_readiness_digest(readiness)
        readiness_metadata = dict(readiness.metadata)
    except Exception as exc:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_malformed"
        ) from exc

    if not isinstance(readiness.readiness_digest, str) or readiness.readiness_digest != expected_readiness_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_digest_mismatch"
        )

    # Anchor cross-checks: the readiness's recorded provenance anchors must match the supplied inputs exactly.
    # These give a specific rejection before the (heavier) re-build re-proof below.
    if promotion_candidate_journal_entry.entry_digest != readiness.promotion_candidate_journal_entry_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:promotion_candidate_entry_digest_mismatch"
        )
    if promotion_candidate_journal_entry.payload_digest != readiness.promotion_candidate_payload_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:promotion_candidate_payload_digest_mismatch"
        )
    if candidate.journal_entry_digest != readiness.decision_journal_entry_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:decision_entry_digest_mismatch"
        )
    if candidate.journal_payload_digest != readiness.decision_journal_payload_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:decision_payload_digest_mismatch"
        )

    # Upstream same-chain provenance: the risk-budget-decision anchor must live in the target journal and be of
    # the expected artifact type, so a downstream reader can resolve the full chain within THIS journal.
    try:
        decision_entry = journal.get_by_entry_digest(readiness.decision_journal_entry_digest)
    except EvidenceJournalError as exc:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:decision_entry_not_in_journal"
        ) from exc
    if decision_entry.entry_type is not EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:decision_entry_artifact_type_mismatch"
        )

    # Same-chain provenance re-proof: re-build the readiness from the SAME target journal + supplied candidate
    # entry + candidate with the readiness's own correlation_id/metadata and require an identical canonical
    # payload. The builder re-proves the full same-chain anchoring (promotion-candidate entry present and
    # re-proving the candidate, plus the upstream risk-budget-decision anchor present in the same chain), so any
    # forged/stale/resealed readiness that does not correspond to this journaled candidate is rejected here.
    try:
        rebuilt = build_paper_sleeve_promotion_readiness(
            journal,
            promotion_candidate_journal_entry,
            candidate,
            correlation_id=readiness.correlation_id,
            metadata=readiness_metadata,
        )
        rebuilt_payload = paper_sleeve_promotion_readiness_to_dict(rebuilt)
    except PaperSleevePromotionReadinessError as exc:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_not_reproducible"
        ) from exc
    except Exception as exc:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_malformed"
        ) from exc
    if rebuilt_payload != readiness_payload or rebuilt.readiness_digest != readiness.readiness_digest:
        raise PaperSleevePromotionReadinessJournalAdapterError(
            "paper_sleeve_promotion_readiness_journal_adapter:readiness_not_reproducible"
        )

    # Exactly one append after all prechecks pass; no caller payload_digest is trusted.
    return journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS,
        readiness_payload,
        correlation_id=correlation_id,
    )


__all__ = [
    "PaperSleevePromotionReadinessJournalAdapterError",
    "append_paper_sleeve_promotion_readiness_to_evidence_journal",
]
