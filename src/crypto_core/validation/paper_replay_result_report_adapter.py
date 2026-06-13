"""Producer adapter: deterministic replay output -> existing PaperReplayResultReport.

Bridges the deterministic replay executor (PR #259) into the existing ``PaperReplayResultReport`` record
contract *without inventing a new report contract and without weakening fail-closed/digest-boundary
doctrine*. The executor is the only component that *computes* the three result digests
(``replay_trace_digest``, ``metrics_digest``, ``decision_trace_digest``); the result report *records*
them. This adapter is the trusted seam that re-proves the executor evidence and feeds exactly those
computed digests into ``build_paper_replay_result_report`` — never caller-supplied digests.

Design rules:
  - Boundary digest re-proof (executor evidence): the input digest is recomputed via
    ``deterministic_replay_input_digest`` and the output digest via ``deterministic_replay_output_digest``;
    ``replay_output.input_digest`` must equal the recomputed input digest (ties output to the current
    input), ``replay_input.input_digest`` must self-prove, and ``replay_output.output_digest`` must
    re-prove. The run-plan digest is independently re-proven downstream by the result report itself.
  - Schema pinning: both ``schema_version`` values must equal the executor schema this adapter targets;
    since ``schema_version`` is inside both digests, a forged value also fails the digest re-proof.
  - No trust of caller digests: the adapter exposes no ``*_digest`` parameter — the recorded digests are
    taken from ``replay_output`` only.
  - Fail closed: a wrong-typed/empty call input, a malformed executor artifact, a digest/schema mismatch,
    or a non-canonical result digest raises ``PaperReplayResultReportAdapterError``. A legitimately
    REJECTED replay output (valid digests, rejected events) maps to a REJECTED report via the existing
    outcome semantics; forbidden/BIST tokens in id/correlation/metadata are rejected by the downstream
    report (REJECTED). No clocks, random, IO, threading, persistence, orders, scheduler, connector,
    runtime, shadow, or BIST.
"""

from __future__ import annotations

from collections.abc import Mapping

from crypto_core.validation.deterministic_replay_executor import (
    DeterministicReplayInput,
    DeterministicReplayOutput,
    DeterministicReplayStatus,
    deterministic_replay_input_digest,
    deterministic_replay_output_digest,
)
from crypto_core.validation.paper_replay_result_report import (
    PaperReplayOutcomeStatus,
    PaperReplayResultReport,
    build_paper_replay_result_report,
)

# The executor schema this adapter is written against. A bump must be a coordinated, reviewed migration.
_EXPECTED_REPLAY_SCHEMA_VERSION = "deterministic-replay-executor.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


class PaperReplayResultReportAdapterError(RuntimeError):
    """Raised when the executor artifacts handed to the adapter are malformed or fail digest re-proof."""


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def build_paper_replay_result_report_from_deterministic_replay(
    replay_input: DeterministicReplayInput,
    replay_output: DeterministicReplayOutput,
    *,
    report_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayResultReport:
    """Build a ``PaperReplayResultReport`` from a deterministic replay input/output pair.

    ``replay_input`` and ``replay_output`` must be the executor's own dataclasses; a wrong type, an empty
    ``report_id``/``correlation_id``, a malformed executor artifact, an unexpected ``schema_version``, a
    digest re-proof mismatch, or a non-canonical result digest raises ``PaperReplayResultReportAdapterError``.
    The recorded ``replay_trace_digest``/``metrics_digest``/``decision_trace_digest`` come *only* from
    ``replay_output`` (no caller override). An ACCEPTED output maps to a COMPLETED outcome; any other
    output maps to REJECTED, and the downstream report applies its own run-plan re-proof, scope-token, and
    status semantics. Deterministic; records evidence, computes nothing.
    """
    if not isinstance(replay_input, DeterministicReplayInput):
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:replay_input_malformed")
    if not isinstance(replay_output, DeterministicReplayOutput):
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:replay_output_malformed")
    if not _is_non_empty_string(report_id):
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:report_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:correlation_id_invalid")

    if replay_input.schema_version != _EXPECTED_REPLAY_SCHEMA_VERSION:
        raise PaperReplayResultReportAdapterError(
            "paper_replay_result_report_adapter:replay_input_schema_version_unexpected"
        )
    if replay_output.schema_version != _EXPECTED_REPLAY_SCHEMA_VERSION:
        raise PaperReplayResultReportAdapterError(
            "paper_replay_result_report_adapter:replay_output_schema_version_unexpected"
        )

    # Boundary digest re-proof of the executor evidence. Any failure to serialize/digest a malformed
    # artifact (a directly-constructed input/output that bypassed the executor — non-canonical event
    # strings, a malformed run plan, malformed trace entries) surfaces as a clean adapter error, never a
    # raw AttributeError/TypeError/ValueError leak. BaseException is deliberately not caught.
    try:
        expected_input_digest = deterministic_replay_input_digest(replay_input)
        expected_output_digest = deterministic_replay_output_digest(replay_output)
    except Exception as exc:
        raise PaperReplayResultReportAdapterError(
            "paper_replay_result_report_adapter:replay_evidence_malformed"
        ) from exc

    if replay_input.input_digest != expected_input_digest:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:replay_input_digest_mismatch")
    if replay_output.input_digest != expected_input_digest:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:input_digest_mismatch")
    if replay_output.output_digest != expected_output_digest:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:output_digest_mismatch")

    # Context binding: a self-consistent forged output must not carry a different run-plan/replay context
    # than the input whose run plan the report will record. Each field the report sources from the input
    # must match the output's own copy.
    run_plan = replay_input.run_plan
    if replay_output.run_plan_digest != run_plan.run_plan_digest:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:run_plan_digest_mismatch")
    if replay_output.replay_mode != run_plan.replay_mode:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:replay_mode_mismatch")
    if replay_output.requested_replay_id != run_plan.requested_replay_id:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:requested_replay_id_mismatch")
    if replay_output.correlation_id != replay_input.correlation_id:
        raise PaperReplayResultReportAdapterError("paper_replay_result_report_adapter:correlation_id_mismatch")

    for name, digest in (
        ("replay_trace_digest", replay_output.replay_trace_digest),
        ("metrics_digest", replay_output.metrics_digest),
        ("decision_trace_digest", replay_output.decision_trace_digest),
    ):
        if not _is_sha256_hex(digest):
            raise PaperReplayResultReportAdapterError(f"paper_replay_result_report_adapter:{name}_invalid")

    if replay_output.status is DeterministicReplayStatus.ACCEPTED and replay_output.accepted is True:
        outcome_status = PaperReplayOutcomeStatus.COMPLETED
    else:
        outcome_status = PaperReplayOutcomeStatus.REJECTED

    return build_paper_replay_result_report(
        run_plan,
        result_report_id=report_id,
        outcome_status=outcome_status,
        replay_trace_digest=replay_output.replay_trace_digest,
        metrics_digest=replay_output.metrics_digest,
        decision_trace_digest=replay_output.decision_trace_digest,
        correlation_id=correlation_id,
        metadata=metadata,
    )


__all__ = [
    "PaperReplayResultReportAdapterError",
    "build_paper_replay_result_report_from_deterministic_replay",
]
