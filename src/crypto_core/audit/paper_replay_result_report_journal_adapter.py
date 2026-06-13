"""Audit bridge: append an existing PaperReplayResultReport into the EvidenceJournal.

Closes the executor -> report -> journal evidence chain. The deterministic replay executor *computes*
the result digests, the result-report contract *records* them, and this bridge *journals* the recorded
report as ``EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT`` — paper/replay/audit-only. It is not a
runtime, scheduler, persistence layer, or paper-tick execution: no DB/file/network/env IO, no clocks,
no random, no threading, no orders/connector/live surface.

Design rules:
  - Boundary digest re-proof: the report digest is recomputed from the public
    ``paper_replay_result_report_to_dict(report)`` serializer (excluding ``result_report_digest``) using
    the same canonical hashing convention as the report module, and a mismatch is rejected before any
    append — a stale/forged/tampered report cannot be journaled.
  - Schema pinning: ``report.schema_version`` must equal the result-report schema this bridge targets.
  - Append the canonical dict only: the journaled payload is exactly ``paper_replay_result_report_to_dict``
    output; no caller-supplied ``payload_digest`` is trusted (the journal computes it).
  - Any-status: a valid report of any terminal status is journaled if its digest re-proves — the journal
    stores valid artifacts, not only READY ones.
  - Fail closed, no mutation before prechecks: a wrong-typed journal/report, an empty correlation id, an
    unexpected schema, a malformed report artifact, or a digest mismatch raises
    ``PaperReplayResultReportJournalAdapterError`` before any append, leaving the journal unchanged.
    Forbidden BIST/live/private/order/scheduler/connector/shadow tokens and duplicate payloads fail
    through the journal's own ``EvidenceJournalError`` guard (not weakened here).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
)
from crypto_core.validation.deterministic_replay_executor import (
    DeterministicReplayInput,
    DeterministicReplayOutput,
)
from crypto_core.validation.paper_replay_result_report import (
    PaperReplayResultReport,
    paper_replay_result_report_to_dict,
)
from crypto_core.validation.paper_replay_result_report_adapter import (
    build_paper_replay_result_report_from_deterministic_replay,
)

# The result-report schema this bridge is written against. A bump is a coordinated, reviewed migration.
_EXPECTED_RESULT_REPORT_SCHEMA_VERSION = "paper-replay-result-report.v1"


class PaperReplayResultReportJournalAdapterError(RuntimeError):
    """Raised when a report handed to the journal bridge is malformed or fails digest/schema re-proof."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _canonical_digest(payload: Mapping[str, object]) -> str:
    # Same convention as crypto_core.validation.paper_replay_result_report._canonical_digest.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def append_paper_replay_result_report_to_evidence_journal(
    journal: EvidenceJournal,
    report: PaperReplayResultReport,
    *,
    correlation_id: str,
) -> EvidenceJournalEntry:
    """Append a re-proven ``PaperReplayResultReport`` to ``journal`` as ``PAPER_REPLAY_RESULT_REPORT``.

    ``journal`` must be an ``EvidenceJournal`` and ``report`` a ``PaperReplayResultReport``; a wrong type,
    an empty ``correlation_id``, an unexpected ``schema_version``, a malformed report artifact, or a
    ``result_report_digest`` that does not re-prove raises ``PaperReplayResultReportJournalAdapterError``
    before any append (journal unchanged). The journaled payload is exactly
    ``paper_replay_result_report_to_dict(report)``; the journal computes the payload digest and applies its
    own token/duplicate guards (forbidden tokens and replays surface as ``EvidenceJournalError``).
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperReplayResultReportJournalAdapterError("paper_replay_result_report_journal_adapter:journal_malformed")
    if not isinstance(report, PaperReplayResultReport):
        raise PaperReplayResultReportJournalAdapterError("paper_replay_result_report_journal_adapter:report_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperReplayResultReportJournalAdapterError(
            "paper_replay_result_report_journal_adapter:correlation_id_invalid"
        )
    if report.schema_version != _EXPECTED_RESULT_REPORT_SCHEMA_VERSION:
        raise PaperReplayResultReportJournalAdapterError(
            "paper_replay_result_report_journal_adapter:report_schema_version_unexpected"
        )

    # Serialize + re-prove the digest. A malformed report artifact surfaces as a clean adapter error,
    # never a raw AttributeError/TypeError/ValueError. BaseException is deliberately not caught.
    try:
        payload = paper_replay_result_report_to_dict(report)
        digest_basis = dict(payload)
        digest_basis.pop("result_report_digest", None)
        expected_digest = _canonical_digest(digest_basis)
    except Exception as exc:
        raise PaperReplayResultReportJournalAdapterError(
            "paper_replay_result_report_journal_adapter:report_malformed"
        ) from exc

    stored_digest = report.result_report_digest
    if not isinstance(stored_digest, str) or stored_digest != expected_digest:
        raise PaperReplayResultReportJournalAdapterError(
            "paper_replay_result_report_journal_adapter:result_report_digest_mismatch"
        )

    # Exactly one append after all prechecks pass; no caller payload_digest is trusted.
    return journal.append(
        EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT,
        payload,
        correlation_id=correlation_id,
    )


def build_and_append_paper_replay_result_report_from_deterministic_replay(
    journal: EvidenceJournal,
    replay_input: DeterministicReplayInput,
    replay_output: DeterministicReplayOutput,
    *,
    report_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> tuple[PaperReplayResultReport, EvidenceJournalEntry]:
    """Build a report from a deterministic replay pair via the validation adapter, then journal it.

    ``journal`` must be an ``EvidenceJournal``. The report is built by
    ``build_paper_replay_result_report_from_deterministic_replay`` (which re-proves the replay input/output
    digests and binds context); a tampered/forged replay artifact raises through that adapter before any
    append, leaving the journal unchanged. The returned report is then journaled via
    ``append_paper_replay_result_report_to_evidence_journal``.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperReplayResultReportJournalAdapterError("paper_replay_result_report_journal_adapter:journal_malformed")

    report = build_paper_replay_result_report_from_deterministic_replay(
        replay_input,
        replay_output,
        report_id=report_id,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    entry = append_paper_replay_result_report_to_evidence_journal(journal, report, correlation_id=correlation_id)
    return report, entry


__all__ = [
    "PaperReplayResultReportJournalAdapterError",
    "append_paper_replay_result_report_to_evidence_journal",
    "build_and_append_paper_replay_result_report_from_deterministic_replay",
]
