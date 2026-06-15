"""Audit bridge: append an existing PaperSleevePromotionCandidate into the EvidenceJournal.

Anchors a paper-only promotion-candidate *read model* in the append-only evidence journal before any
downstream allocator/promotion consumer can read it. The promotion-candidate gate *classifies* whether a
journal-anchored ``PaperSleeveRiskBudgetDecision`` is eligible to be *considered*; this bridge *journals*
that classification under its own ``EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE`` — paper/audit
only. It is not a runtime, allocator, promotion, scheduler, order router, connector, or execution path: no
DB/file/network/env IO, no clocks, no random, no threading, no orders/fills/PnL/position surface. It journals
an already-built candidate; it never allocates, promotes, executes, routes, schedules, connects, reserves
capital, or mutates anything.

Design rules:
  - Candidate self-proof: ``candidate.candidate_digest`` is recomputed via the public
    ``paper_sleeve_promotion_candidate_digest`` and a mismatch is rejected before any append. No hashing
    convention is duplicated here; the upstream serializer/digest is the single source of truth.
  - Provenance re-proof (the bridge's core invariant): the candidate must have been *built from the supplied
    journal-anchored decision*. The bridge re-runs the public ``build_paper_sleeve_promotion_candidate`` on the
    supplied ``decision_journal_entry`` + ``decision`` with the candidate's own ``correlation_id`` / ``metadata``
    and requires an identical canonical payload (``paper_sleeve_promotion_candidate_to_dict``). Because that
    builder re-proves the full journal anchoring (artifact type, correlation, payload, payload-digest, the
    entry self-digest, the decision digest, the paper-safety triples, and the derived counts), a bare/forged/
    stale candidate whose self-digest was resealed but whose contents do not correspond to that journaled
    decision is rejected before append.
  - Anchor cross-checks: the candidate's recorded provenance anchors must match the supplied entry exactly —
    ``candidate.journal_entry_digest == decision_journal_entry.entry_digest`` and
    ``candidate.journal_payload_digest == decision_journal_entry.payload_digest``.
  - Append the canonical dict only: the journaled payload is exactly
    ``paper_sleeve_promotion_candidate_to_dict(candidate)``; no caller-supplied ``payload_digest`` is trusted
    (the journal computes it and applies its own token/duplicate guards, not weakened here). The new entry is
    journaled under the caller-supplied audit ``correlation_id``.
  - Fail closed, no mutation before prechecks: a wrong-typed journal/candidate/entry/decision, an empty
    ``correlation_id``, an unexpected schema, a malformed candidate artifact, a candidate-digest mismatch, an
    anchor mismatch, an unsafe paper-safety flag, or a candidate that does not re-build from the supplied
    journaled decision raises ``PaperSleevePromotionCandidateJournalAdapterError`` before any append, leaving
    the journal unchanged. Forbidden BIST/live/private/order/scheduler/connector/shadow tokens and duplicate
    payloads fail through the journal's own ``EvidenceJournalError`` guard.
"""

from __future__ import annotations

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    PaperSleevePromotionCandidate,
    PaperSleevePromotionCandidateError,
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_digest,
    paper_sleeve_promotion_candidate_to_dict,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import PaperSleeveRiskBudgetDecision

# The candidate schema this bridge is written against. A bump is a coordinated, reviewed migration.
_EXPECTED_CANDIDATE_SCHEMA_VERSION = "paper-sleeve-promotion-candidate.v1"


class PaperSleevePromotionCandidateJournalAdapterError(RuntimeError):
    """Raised when a candidate handed to the journal bridge fails type/digest/provenance re-proof."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def append_paper_sleeve_promotion_candidate_to_evidence_journal(
    journal: EvidenceJournal,
    candidate: PaperSleevePromotionCandidate,
    *,
    decision_journal_entry: EvidenceJournalEntry,
    decision: PaperSleeveRiskBudgetDecision,
    correlation_id: str,
) -> EvidenceJournalEntry:
    """Append a re-proven ``PaperSleevePromotionCandidate`` as PAPER_SLEEVE_PROMOTION_CANDIDATE.

    ``journal`` must be an ``EvidenceJournal``, ``candidate`` a ``PaperSleevePromotionCandidate``,
    ``decision_journal_entry`` an ``EvidenceJournalEntry``, and ``decision`` a ``PaperSleeveRiskBudgetDecision``.
    The candidate is rejected before any append (journal unchanged) on a wrong type, an empty audit
    ``correlation_id``, an unexpected ``schema_version``, an unsafe paper-safety flag, a malformed candidate
    artifact, a candidate-digest mismatch, an anchor mismatch (``journal_entry_digest`` /
    ``journal_payload_digest``), or a candidate that does not re-build from the supplied ``decision_journal_entry``
    + ``decision``. The journaled payload is exactly ``paper_sleeve_promotion_candidate_to_dict(candidate)``;
    the journal computes the payload digest and applies its own token/duplicate guards (forbidden tokens and
    replays surface as ``EvidenceJournalError``). Journals audit provenance only — no allocation, promotion,
    execution, routing, fill, PnL, or position.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:journal_malformed"
        )
    if not isinstance(candidate, PaperSleevePromotionCandidate):
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_malformed"
        )
    if not isinstance(decision_journal_entry, EvidenceJournalEntry):
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:decision_journal_entry_malformed"
        )
    if not isinstance(decision, PaperSleeveRiskBudgetDecision):
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:decision_malformed"
        )
    if not _is_non_empty_string(correlation_id):
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:correlation_id_invalid"
        )
    if candidate.schema_version != _EXPECTED_CANDIDATE_SCHEMA_VERSION:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_schema_version_unexpected"
        )

    # Paper-only invariant: a self-consistent (resealed) candidate can still attest ``paper_only=False`` or
    # enabled real orders/money. The journal token guard only covers the real-orders/real-money attestation
    # keys, so the bridge enforces the full paper-safety triple itself before journaling.
    if candidate.paper_only is not True:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_not_paper_only"
        )
    if candidate.real_orders_enabled is not False:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_real_orders_enabled"
        )
    if candidate.real_money_enabled is not False:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_real_money_enabled"
        )

    # Serialize + recompute the candidate self-digest via the public helpers. A malformed candidate artifact
    # surfaces as a clean adapter error, never a raw AttributeError/TypeError/ValueError. BaseException is
    # deliberately not caught.
    try:
        candidate_payload = paper_sleeve_promotion_candidate_to_dict(candidate)
        expected_candidate_digest = paper_sleeve_promotion_candidate_digest(candidate)
        candidate_metadata = dict(candidate.metadata)
    except Exception as exc:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_malformed"
        ) from exc

    if not isinstance(candidate.candidate_digest, str) or candidate.candidate_digest != expected_candidate_digest:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_digest_mismatch"
        )

    # Anchor cross-checks: the candidate's recorded provenance anchors must match the supplied entry exactly.
    # These give a specific rejection before the (heavier) re-build re-proof below.
    if decision_journal_entry.entry_digest != candidate.journal_entry_digest:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:journal_entry_digest_mismatch"
        )
    if candidate.journal_payload_digest != decision_journal_entry.payload_digest:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:journal_payload_digest_mismatch"
        )

    # Provenance re-proof: re-build the candidate from the supplied journaled decision with the candidate's own
    # correlation_id/metadata and require an identical canonical payload. The builder re-proves the full journal
    # anchoring (artifact type, correlation, payload, payload-digest, the entry self-digest), the decision digest,
    # the paper-safety triples, and the derived counts, so any forged/stale/resealed candidate that does not
    # correspond to this journaled decision is rejected here before append.
    try:
        rebuilt = build_paper_sleeve_promotion_candidate(
            decision_journal_entry,
            decision,
            correlation_id=candidate.correlation_id,
            metadata=candidate_metadata,
        )
        rebuilt_payload = paper_sleeve_promotion_candidate_to_dict(rebuilt)
    except PaperSleevePromotionCandidateError as exc:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_not_reproducible"
        ) from exc
    except Exception as exc:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_malformed"
        ) from exc
    if rebuilt_payload != candidate_payload or rebuilt.candidate_digest != candidate.candidate_digest:
        raise PaperSleevePromotionCandidateJournalAdapterError(
            "paper_sleeve_promotion_candidate_journal_adapter:candidate_not_reproducible"
        )

    # Exactly one append after all prechecks pass; no caller payload_digest is trusted.
    return journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE,
        candidate_payload,
        correlation_id=correlation_id,
    )


__all__ = [
    "PaperSleevePromotionCandidateJournalAdapterError",
    "append_paper_sleeve_promotion_candidate_to_evidence_journal",
]
