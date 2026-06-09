"""Paper replay run plan — deterministic paper-only run-plan gate over a READY replay intake.

A small, deterministic, fail-closed gate/candidate that turns a READY ``PaperReplayIntake`` into a
concrete *plan* for a later offline paper replay run (which mode, which run id), re-proving the intake
digest at the boundary. It is *not* storage, *not* runtime, *not* a scheduler, *not* a backtest engine,
and *not* execution: no DB/file/network IO, no persistence/repository adapter, no event loading, no
connector/readiness, no replay execution.

Design rules:
  - Boundary digest re-proof: the intake digest is recomputed via the public
    ``paper_replay_intake_to_dict`` serializer (excluding ``intake_digest``) and a mismatch is rejected
    before READY — a stale/forged/tampered intake cannot plan.
  - Consume, don't re-validate: terminal status (READY/REJECTED/NEEDS_RESEARCH/INSUFFICIENT_EVIDENCE)
    propagates from the intake; the run plan adds only the boundary digest re-proof, the run-plan
    identity, the replay-mode whitelist, and chain-digest shape checks. No upstream validation is redone.
  - Fail closed: a wrong-typed intake, empty correlation id, or malformed metadata raises; a hard intake
    rejection, an intake-digest mismatch, a malformed chain digest / id, an unknown replay mode, or a
    BIST/live/private/order/scheduler token in an identity/mode/metadata value yields REJECTED;
    needs-research and insufficient-evidence propagate.
  - Deterministic: a canonical SHA-256 ``run_plan_digest``; no wall-clock/random/IO. Frozen dataclass;
    ``paper_only=True`` and no order/route/venue/scheduler/runtime/persistence/store/engine field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_intake import (
    PaperReplayIntake,
    PaperReplayIntakeStatus,
    paper_replay_intake_to_dict,
)

_SCHEMA_VERSION = "paper-replay-run-plan.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_ALLOWED_REPLAY_MODES = frozenset({"offline_paper_replay", "deterministic_replay_dry_run"})

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
# A bare ``order``/``orders`` token is rejected (non-alphanumeric boundaries) while ``border``/``orderly``/
# ``preorder`` are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperReplayRunPlanError(RuntimeError):
    """Raised when run-plan inputs are malformed at the call level (wrong type / bad id / bad metadata)."""


class PaperReplayRunPlanStatus(str, Enum):
    """Terminal readiness of a paper replay run plan. Never an order/live action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperReplayRunPlan:
    """Deterministic, immutable paper replay run plan over a READY intake. PAPER ONLY."""

    schema_version: str
    status: PaperReplayRunPlanStatus
    ready: bool
    run_plan_id: str
    replay_mode: str
    requested_replay_id: str
    operator_id: str
    strategy_id: str | None
    strategy_digest: str | None
    bundle_digest: str
    admission_digest: str
    bridge_digest: str
    manifest_digest: str
    intake_digest: str
    intake_status: str
    replay_source_id: str
    historical_data_source_id: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    run_plan_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_replay_run_plan:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_replay_run_plan:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReplayRunPlanError("paper_replay_run_plan:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperReplayRunPlanError("paper_replay_run_plan:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _expected_intake_digest(intake: PaperReplayIntake) -> str:
    payload = paper_replay_intake_to_dict(intake)
    payload.pop("intake_digest", None)
    return _canonical_digest(payload)


def build_paper_replay_run_plan(
    intake: PaperReplayIntake,
    *,
    run_plan_id: str,
    replay_mode: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayRunPlan:
    """Build a deterministic paper replay run plan from a READY ``PaperReplayIntake``.

    ``intake`` must be a ``PaperReplayIntake``; a wrong-typed intake, an empty ``correlation_id``, or non
    ``Mapping[str, str]`` metadata raises ``PaperReplayRunPlanError``. The plan is READY only when the
    intake is READY + ready, its ``intake_digest`` re-proves via the public serializer, the chain digests
    are canonical 64-hex, the ids/source ids are non-empty, the ``replay_mode`` is whitelisted, and no
    forbidden/BIST token appears in an identity/mode/metadata value; every other outcome maps fail-closed
    to REJECTED / INSUFFICIENT_EVIDENCE / NEEDS_RESEARCH. Deterministic and immutable; no run execution.
    """
    if not isinstance(intake, PaperReplayIntake):
        raise PaperReplayRunPlanError("paper_replay_run_plan:intake_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperReplayRunPlanError("paper_replay_run_plan:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(run_plan_id):
        hard.append("paper_replay_run_plan:run_plan_id_invalid")
    if not _is_non_empty_string(replay_mode):
        hard.append("paper_replay_run_plan:replay_mode_invalid")
    elif replay_mode not in _ALLOWED_REPLAY_MODES:
        hard.append("paper_replay_run_plan:replay_mode_unknown")

    if not _is_non_empty_string(intake.requested_replay_id):
        hard.append("paper_replay_run_plan:requested_replay_id_invalid")
    if not _is_non_empty_string(intake.operator_id):
        hard.append("paper_replay_run_plan:operator_id_invalid")
    if not _is_non_empty_string(intake.replay_source_id):
        hard.append("paper_replay_run_plan:replay_source_id_invalid")
    if not _is_non_empty_string(intake.historical_data_source_id):
        hard.append("paper_replay_run_plan:historical_data_source_id_invalid")

    hard.extend(
        _scope_violations(
            run_plan_id,
            replay_mode,
            correlation_id,
            intake.requested_replay_id,
            intake.operator_id,
            intake.replay_source_id,
            intake.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", intake.bundle_digest),
        ("admission_digest", intake.admission_digest),
        ("bridge_digest", intake.bridge_digest),
        ("manifest_digest", intake.manifest_digest),
        ("intake_digest", intake.intake_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_replay_run_plan:{name}_invalid")

    # Boundary digest re-proof: a stale/forged intake must not plan.
    if _is_sha256_hex(intake.intake_digest) and intake.intake_digest != _expected_intake_digest(intake):
        hard.append("paper_replay_run_plan:intake_digest_mismatch")

    if intake.status is PaperReplayIntakeStatus.REJECTED:
        hard.append("paper_replay_run_plan:intake_rejected")
        hard.extend(intake.rejection_reasons)
    elif intake.status is PaperReplayIntakeStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_run_plan:intake_needs_research")
        needs.extend(intake.needs_research_reasons)
    elif intake.status is PaperReplayIntakeStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_run_plan:intake_insufficient_evidence")
    elif intake.status is PaperReplayIntakeStatus.READY and not intake.ready:
        hard.append("paper_replay_run_plan:intake_ready_mismatch")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperReplayRunPlanStatus.REJECTED
    elif insufficient_reasons:
        status = PaperReplayRunPlanStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperReplayRunPlanStatus.NEEDS_RESEARCH
    elif intake.status is PaperReplayIntakeStatus.READY and intake.ready:
        status = PaperReplayRunPlanStatus.READY
    else:
        status = PaperReplayRunPlanStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        intake=intake,
        run_plan_id=run_plan_id,
        replay_mode=replay_mode,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: PaperReplayRunPlanStatus,
    intake: PaperReplayIntake,
    run_plan_id: str,
    replay_mode: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> PaperReplayRunPlan:
    ready = status is PaperReplayRunPlanStatus.READY
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "run_plan_id": run_plan_id,
        "replay_mode": replay_mode,
        "requested_replay_id": intake.requested_replay_id,
        "operator_id": intake.operator_id,
        "strategy_id": intake.strategy_id,
        "strategy_digest": intake.strategy_digest,
        "bundle_digest": intake.bundle_digest,
        "admission_digest": intake.admission_digest,
        "bridge_digest": intake.bridge_digest,
        "manifest_digest": intake.manifest_digest,
        "intake_digest": intake.intake_digest,
        "intake_status": intake.status.value,
        "replay_source_id": intake.replay_source_id,
        "historical_data_source_id": intake.historical_data_source_id,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return PaperReplayRunPlan(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        run_plan_id=run_plan_id,
        replay_mode=replay_mode,
        requested_replay_id=intake.requested_replay_id,
        operator_id=intake.operator_id,
        strategy_id=intake.strategy_id,
        strategy_digest=intake.strategy_digest,
        bundle_digest=intake.bundle_digest,
        admission_digest=intake.admission_digest,
        bridge_digest=intake.bridge_digest,
        manifest_digest=intake.manifest_digest,
        intake_digest=intake.intake_digest,
        intake_status=intake.status.value,
        replay_source_id=intake.replay_source_id,
        historical_data_source_id=intake.historical_data_source_id,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        run_plan_digest=_canonical_digest(payload),
    )


def paper_replay_run_plan_to_dict(run_plan: PaperReplayRunPlan) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper replay run plan (deterministic shape)."""
    return {
        "schema_version": run_plan.schema_version,
        "status": run_plan.status.value,
        "ready": run_plan.ready,
        "run_plan_id": run_plan.run_plan_id,
        "replay_mode": run_plan.replay_mode,
        "requested_replay_id": run_plan.requested_replay_id,
        "operator_id": run_plan.operator_id,
        "strategy_id": run_plan.strategy_id,
        "strategy_digest": run_plan.strategy_digest,
        "bundle_digest": run_plan.bundle_digest,
        "admission_digest": run_plan.admission_digest,
        "bridge_digest": run_plan.bridge_digest,
        "manifest_digest": run_plan.manifest_digest,
        "intake_digest": run_plan.intake_digest,
        "intake_status": run_plan.intake_status,
        "replay_source_id": run_plan.replay_source_id,
        "historical_data_source_id": run_plan.historical_data_source_id,
        "metadata": [list(pair) for pair in run_plan.metadata],
        "rejection_reasons": list(run_plan.rejection_reasons),
        "needs_research_reasons": list(run_plan.needs_research_reasons),
        "correlation_id": run_plan.correlation_id,
        "run_plan_digest": run_plan.run_plan_digest,
        "paper_only": run_plan.paper_only,
        "real_orders_enabled": run_plan.real_orders_enabled,
        "real_money_enabled": run_plan.real_money_enabled,
    }


__all__ = [
    "PaperReplayRunPlan",
    "PaperReplayRunPlanError",
    "PaperReplayRunPlanStatus",
    "build_paper_replay_run_plan",
    "paper_replay_run_plan_to_dict",
]
