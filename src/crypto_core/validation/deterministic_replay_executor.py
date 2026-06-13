"""Deterministic replay executor — pure paper-only replay over a READY run plan.

The first pure execution skeleton on the path to a first measurable paper-trade tick. It consumes a
READY :class:`~crypto_core.validation.paper_replay_run_plan.PaperReplayRunPlan` plus a caller-supplied,
deterministic sequence of replay events and produces a deterministic execution result/trace whose three
digests (``replay_trace_digest``, ``metrics_digest``, ``decision_trace_digest``) are exactly the evidence
the existing ``PaperReplayResultReport`` *records but never computes*. It is *not* storage, *not* a
runtime, *not* a scheduler, *not* a backtest engine, and *not* execution: no DB/file/network/env IO, no
persistence/repository adapter, no clocks, no random, no threading, no connector/readiness, no orders.

Design rules:
  - Pure + deterministic: output is a pure function of (run plan, events). No wall-clock, no unseeded
    random, no IO/threading. Canonical SHA-256 digests; identical input yields an identical
    ``output_digest``.
  - Boundary digest re-proof: the run-plan digest is recomputed via the public
    ``paper_replay_run_plan_to_dict`` serializer (excluding ``run_plan_digest``) and a mismatch is
    rejected — a stale/forged/tampered run plan cannot execute. The executor input re-proves its own
    ``input_digest`` the same way.
  - Record classification, compute no PnL: each event is normalized to canonical JSON, digested, and
    classified ACCEPT/REJECT by deterministic paper-safety checks only (BIST/live/private/order/
    scheduler/connector/shadow scope tokens, wall-clock field names, JSON-canonical shape). No fills,
    no PnL, no performance fields are invented.
  - Fail closed: a wrong-typed run plan/input, an empty correlation id, a non-sequence ``events``, a
    non-mapping event, or a non-canonical/NaN/non-JSON value raises ``DeterministicReplayExecutorError``;
    a run-plan-digest mismatch, a non-READY/unsafe run plan, an input-digest mismatch, an empty event
    sequence, or any rejected event yields a REJECTED output. Frozen dataclasses; ``paper_only=True`` and
    no order/route/venue/scheduler/runtime/connector field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)

_SCHEMA_VERSION = "deterministic-replay-executor.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_ALLOWED_REPLAY_MODES = frozenset({"offline_paper_replay", "deterministic_replay_dry_run"})

# Safely-detectable BIST markers and forbidden live/private/order/scheduler/connector/shadow tokens
# (word-bounded). A bare ``order``/``orders`` token is rejected while ``border``/``orderly``/``preorder``
# are spared; ``live`` is rejected as a word/prefix while ``alive``/``delivery`` are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow|credential|credentials|scheduler|connector)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
# Wall-clock field-name markers, applied to event *keys* only (clock fields, not arbitrary values).
_WALL_CLOCK_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:timestamp|timestamp_ns|time_ns|created_at|updated_at|wall_clock|utcnow|datetime)(?![a-z0-9])"
    r"|\b(?:now|clock)\b",
    re.IGNORECASE,
)


class DeterministicReplayExecutorError(RuntimeError):
    """Raised when executor inputs are malformed at the call level (wrong type / bad event / bad id)."""


class DeterministicReplayStatus(str, Enum):
    """Terminal status of a deterministic replay execution. Never an order/live action."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DeterministicReplayEventDecision(str, Enum):
    """Per-event deterministic classification. Never an order/live action."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class DeterministicReplayInput:
    """Deterministic, immutable executor input over a run plan and a canonical event sequence. PAPER ONLY."""

    schema_version: str
    run_plan: PaperReplayRunPlan
    events: tuple[str, ...]
    correlation_id: str
    input_digest: str


@dataclass(frozen=True)
class DeterministicReplayTraceEntry:
    """Deterministic, immutable per-event trace entry (stable sequence id + event digest + decision)."""

    sequence_id: int
    event_digest: str
    decision: DeterministicReplayEventDecision
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DeterministicReplayOutput:
    """Deterministic, immutable replay execution result/trace over a run plan. PAPER ONLY."""

    schema_version: str
    status: DeterministicReplayStatus
    accepted: bool
    run_plan_digest: str
    replay_mode: str
    requested_replay_id: str
    correlation_id: str
    input_digest: str
    event_count: int
    accepted_event_count: int
    rejected_event_count: int
    trace_entries: tuple[DeterministicReplayTraceEntry, ...]
    replay_trace_digest: str
    metrics_digest: str
    decision_trace_digest: str
    rejection_reasons: tuple[str, ...]
    output_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class DeterministicReplayExecutor:
    """Stateless, pure deterministic replay executor over a READY paper run plan. PAPER ONLY."""

    def execute(self, replay_input: DeterministicReplayInput) -> DeterministicReplayOutput:
        """Run the pure deterministic replay; delegates to ``execute_deterministic_replay``."""
        return execute_deterministic_replay(replay_input)


def _canonical_json(payload: object) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DeterministicReplayExecutorError("deterministic_replay_executor:payload_not_canonical_json") from exc


def _canonical_digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _safe_digest_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _sorted_unique(reasons: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_token_reasons(text: object) -> tuple[str, ...]:
    if not isinstance(text, str) or text == "":
        return ()
    reasons: list[str] = []
    if _BIST_PATTERN.search(text):
        reasons.append("deterministic_replay_executor:bist_scope_leakage")
    if _FORBIDDEN_PATTERN.search(text):
        reasons.append("deterministic_replay_executor:forbidden_scope_token")
    return tuple(reasons)


def _wall_clock_reasons(text: object) -> tuple[str, ...]:
    if not isinstance(text, str) or text == "":
        return ()
    if _WALL_CLOCK_PATTERN.search(text):
        return ("deterministic_replay_executor:wall_clock_field",)
    return ()


def _validate_json_value(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DeterministicReplayExecutorError("deterministic_replay_executor:event_key_malformed")
            _validate_json_value(item)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_json_value(item)
        return
    if value is None or isinstance(value, str | bool | int | float):
        return
    raise DeterministicReplayExecutorError("deterministic_replay_executor:event_value_malformed")


def _normalize_event(event: object) -> str:
    if not isinstance(event, Mapping):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:event_malformed")
    _validate_json_value(event)
    return _canonical_json(event)


def _event_field_reasons(event: object) -> tuple[str, ...]:
    reasons: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str):
                    reasons.extend(_scope_token_reasons(key))
                    reasons.extend(_wall_clock_reasons(key))
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            reasons.extend(_scope_token_reasons(node))

    _walk(event)
    return _sorted_unique(tuple(reasons))


def _expected_run_plan_digest(run_plan: PaperReplayRunPlan) -> str | None:
    try:
        payload = paper_replay_run_plan_to_dict(run_plan)
        payload.pop("run_plan_digest", None)
        return _canonical_digest(payload)
    except Exception:
        return None


def _run_plan_reasons(run_plan: PaperReplayRunPlan) -> list[str]:
    reasons: list[str] = []
    if not _is_sha256_hex(run_plan.run_plan_digest):
        reasons.append("deterministic_replay_executor:run_plan_digest_invalid")
    elif run_plan.run_plan_digest != _expected_run_plan_digest(run_plan):
        reasons.append("deterministic_replay_executor:run_plan_digest_mismatch")
    if run_plan.status is not PaperReplayRunPlanStatus.READY or run_plan.ready is not True:
        reasons.append("deterministic_replay_executor:run_plan_not_ready")
    if not isinstance(run_plan.replay_mode, str) or run_plan.replay_mode not in _ALLOWED_REPLAY_MODES:
        reasons.append("deterministic_replay_executor:replay_mode_unknown")
    if run_plan.paper_only is not True:
        reasons.append("deterministic_replay_executor:run_plan_non_paper")
    if run_plan.real_orders_enabled is not False:
        reasons.append("deterministic_replay_executor:run_plan_real_orders_enabled")
    if run_plan.real_money_enabled is not False:
        reasons.append("deterministic_replay_executor:run_plan_real_money_enabled")
    return reasons


def _input_payload(run_plan: PaperReplayRunPlan, events: tuple[str, ...], correlation_id: str) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "run_plan": paper_replay_run_plan_to_dict(run_plan),
        "events": [json.loads(event) for event in events],
        "correlation_id": correlation_id,
    }


def build_deterministic_replay_input(
    run_plan: PaperReplayRunPlan,
    *,
    events: list[Mapping[str, object]] | tuple[Mapping[str, object], ...],
    correlation_id: str,
) -> DeterministicReplayInput:
    """Build a deterministic executor input from a run plan and a canonical event sequence.

    ``run_plan`` must be a ``PaperReplayRunPlan``; a wrong-typed run plan, an empty ``correlation_id``, a
    non-sequence ``events``, a non-mapping event, or a non-canonical/NaN/non-JSON event value raises
    ``DeterministicReplayExecutorError``. Each event is normalized to canonical JSON (str keys only) and a
    canonical ``input_digest`` is computed. Readiness/paper-safety are *not* judged here — that is the
    executor's job at run time; this builder only proves the input is canonical and well-typed.
    """
    if not isinstance(run_plan, PaperReplayRunPlan):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:run_plan_malformed")
    if not _is_non_empty_string(correlation_id):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:correlation_id_invalid")
    if not isinstance(events, list | tuple):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:events_malformed")
    normalized_events = tuple(_normalize_event(event) for event in events)
    correlation = correlation_id.strip()
    input_digest = _canonical_digest(_input_payload(run_plan, normalized_events, correlation))
    return DeterministicReplayInput(
        schema_version=_SCHEMA_VERSION,
        run_plan=run_plan,
        events=normalized_events,
        correlation_id=correlation,
        input_digest=input_digest,
    )


def deterministic_replay_input_to_dict(replay_input: DeterministicReplayInput) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an executor input (deterministic shape)."""
    payload = _input_payload(replay_input.run_plan, replay_input.events, replay_input.correlation_id)
    payload["input_digest"] = replay_input.input_digest
    return payload


def deterministic_replay_input_digest(replay_input: DeterministicReplayInput) -> str:
    """Recompute the canonical input digest via the public serializer (excluding ``input_digest``)."""
    payload = deterministic_replay_input_to_dict(replay_input)
    payload.pop("input_digest", None)
    return _canonical_digest(payload)


def _output_payload(
    *,
    status: DeterministicReplayStatus,
    accepted: bool,
    run_plan_digest: str,
    replay_mode: str,
    requested_replay_id: str,
    correlation_id: str,
    input_digest: str,
    metrics: Mapping[str, int],
    replay_trace: list[dict[str, object]],
    decision_trace: list[dict[str, object]],
    replay_trace_digest: str,
    metrics_digest: str,
    decision_trace_digest: str,
    rejection_reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "accepted": accepted,
        "run_plan_digest": run_plan_digest,
        "replay_mode": replay_mode,
        "requested_replay_id": requested_replay_id,
        "correlation_id": correlation_id,
        "input_digest": input_digest,
        "metrics": dict(metrics),
        "replay_trace": [dict(entry) for entry in replay_trace],
        "decision_trace": [dict(entry) for entry in decision_trace],
        "replay_trace_digest": replay_trace_digest,
        "metrics_digest": metrics_digest,
        "decision_trace_digest": decision_trace_digest,
        "rejection_reasons": list(rejection_reasons),
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }


def execute_deterministic_replay(replay_input: DeterministicReplayInput) -> DeterministicReplayOutput:
    """Run a pure deterministic replay over a READY run plan and a canonical event sequence.

    ``replay_input`` must be a ``DeterministicReplayInput`` carrying a ``PaperReplayRunPlan``; otherwise
    ``DeterministicReplayExecutorError`` is raised. The output is ACCEPTED only when the input digest and
    the run-plan digest both re-prove, the run plan is READY + paper-safe, there is at least one event, and
    every event is paper-safe (no BIST/live/private/order/scheduler/connector/shadow token and no
    wall-clock field name); any violation yields a REJECTED output with sorted rejection reasons. No PnL,
    fill, or performance value is computed. Deterministic and immutable.
    """
    if not isinstance(replay_input, DeterministicReplayInput):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:input_malformed")
    run_plan = replay_input.run_plan
    if not isinstance(run_plan, PaperReplayRunPlan):
        raise DeterministicReplayExecutorError("deterministic_replay_executor:run_plan_malformed")

    hard: list[str] = []

    expected_input_digest = deterministic_replay_input_digest(replay_input)
    if replay_input.input_digest != expected_input_digest:
        hard.append("deterministic_replay_executor:input_digest_mismatch")

    hard.extend(_scope_token_reasons(replay_input.correlation_id))
    hard.extend(_wall_clock_reasons(replay_input.correlation_id))
    hard.extend(_run_plan_reasons(run_plan))

    trace_entries: list[DeterministicReplayTraceEntry] = []
    accepted_event_count = 0
    rejected_event_count = 0
    for sequence_id, event_json in enumerate(replay_input.events):
        event = json.loads(event_json)
        event_reasons = _event_field_reasons(event)
        if event_reasons:
            decision = DeterministicReplayEventDecision.REJECT
            rejected_event_count += 1
        else:
            decision = DeterministicReplayEventDecision.ACCEPT
            accepted_event_count += 1
        trace_entries.append(
            DeterministicReplayTraceEntry(
                sequence_id=sequence_id,
                event_digest=_canonical_digest(event),
                decision=decision,
                rejection_reasons=event_reasons,
            )
        )
        hard.extend(event_reasons)

    event_count = len(replay_input.events)
    if event_count == 0:
        hard.append("deterministic_replay_executor:empty_event_sequence")

    rejection_reasons = _sorted_unique(tuple(hard))
    status = DeterministicReplayStatus.REJECTED if rejection_reasons else DeterministicReplayStatus.ACCEPTED
    accepted = status is DeterministicReplayStatus.ACCEPTED
    trace_entries_tuple = tuple(trace_entries)

    metrics = {
        "event_count": event_count,
        "accepted_event_count": accepted_event_count,
        "rejected_event_count": rejected_event_count,
    }
    replay_trace = [
        {"sequence_id": entry.sequence_id, "event_digest": entry.event_digest} for entry in trace_entries_tuple
    ]
    decision_trace = [
        {
            "sequence_id": entry.sequence_id,
            "decision": entry.decision.value,
            "rejection_reasons": list(entry.rejection_reasons),
        }
        for entry in trace_entries_tuple
    ]
    replay_trace_digest = _canonical_digest(replay_trace)
    metrics_digest = _canonical_digest(metrics)
    decision_trace_digest = _canonical_digest(decision_trace)

    run_plan_digest = _safe_digest_value(run_plan.run_plan_digest)
    replay_mode = run_plan.replay_mode if isinstance(run_plan.replay_mode, str) else ""
    requested_replay_id = run_plan.requested_replay_id if isinstance(run_plan.requested_replay_id, str) else ""

    output_digest = _canonical_digest(
        _output_payload(
            status=status,
            accepted=accepted,
            run_plan_digest=run_plan_digest,
            replay_mode=replay_mode,
            requested_replay_id=requested_replay_id,
            correlation_id=replay_input.correlation_id,
            input_digest=expected_input_digest,
            metrics=metrics,
            replay_trace=replay_trace,
            decision_trace=decision_trace,
            replay_trace_digest=replay_trace_digest,
            metrics_digest=metrics_digest,
            decision_trace_digest=decision_trace_digest,
            rejection_reasons=rejection_reasons,
        )
    )

    return DeterministicReplayOutput(
        schema_version=_SCHEMA_VERSION,
        status=status,
        accepted=accepted,
        run_plan_digest=run_plan_digest,
        replay_mode=replay_mode,
        requested_replay_id=requested_replay_id,
        correlation_id=replay_input.correlation_id,
        input_digest=expected_input_digest,
        event_count=event_count,
        accepted_event_count=accepted_event_count,
        rejected_event_count=rejected_event_count,
        trace_entries=trace_entries_tuple,
        replay_trace_digest=replay_trace_digest,
        metrics_digest=metrics_digest,
        decision_trace_digest=decision_trace_digest,
        rejection_reasons=rejection_reasons,
        output_digest=output_digest,
    )


def deterministic_replay_output_to_dict(output: DeterministicReplayOutput) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a replay output (deterministic shape)."""
    metrics = {
        "event_count": output.event_count,
        "accepted_event_count": output.accepted_event_count,
        "rejected_event_count": output.rejected_event_count,
    }
    replay_trace = [
        {"sequence_id": entry.sequence_id, "event_digest": entry.event_digest} for entry in output.trace_entries
    ]
    decision_trace = [
        {
            "sequence_id": entry.sequence_id,
            "decision": entry.decision.value,
            "rejection_reasons": list(entry.rejection_reasons),
        }
        for entry in output.trace_entries
    ]
    payload = _output_payload(
        status=output.status,
        accepted=output.accepted,
        run_plan_digest=output.run_plan_digest,
        replay_mode=output.replay_mode,
        requested_replay_id=output.requested_replay_id,
        correlation_id=output.correlation_id,
        input_digest=output.input_digest,
        metrics=metrics,
        replay_trace=replay_trace,
        decision_trace=decision_trace,
        replay_trace_digest=output.replay_trace_digest,
        metrics_digest=output.metrics_digest,
        decision_trace_digest=output.decision_trace_digest,
        rejection_reasons=output.rejection_reasons,
    )
    payload["output_digest"] = output.output_digest
    return payload


def deterministic_replay_output_digest(output: DeterministicReplayOutput) -> str:
    """Recompute the canonical output digest via the public serializer (excluding ``output_digest``)."""
    payload = deterministic_replay_output_to_dict(output)
    payload.pop("output_digest", None)
    return _canonical_digest(payload)


__all__ = [
    "DeterministicReplayEventDecision",
    "DeterministicReplayExecutor",
    "DeterministicReplayExecutorError",
    "DeterministicReplayInput",
    "DeterministicReplayOutput",
    "DeterministicReplayStatus",
    "DeterministicReplayTraceEntry",
    "build_deterministic_replay_input",
    "deterministic_replay_input_digest",
    "deterministic_replay_input_to_dict",
    "deterministic_replay_output_digest",
    "deterministic_replay_output_to_dict",
    "execute_deterministic_replay",
]
