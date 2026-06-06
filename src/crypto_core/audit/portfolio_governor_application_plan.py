"""Paper governor application plan.

A deterministic, fail-closed, paper-only consumer that collapses the whole paper-governor readiness
foundation (readiness → record → store → replay → transition → stability) into a single
product-facing decision: APPLY / HOLD / BLOCK. This is the product bridge over the now-frozen
audit/forensics chain — it derives, never mirrors, and wires no live/runtime/orchestrator path.

Design rules:
  - Consume, don't mirror: the readiness chain is validated and reduced to a stability verdict by a
    single call to ``evaluate_paper_governor_readiness_stability`` (which snapshots the source once
    and derives replay → transition → stability from that same immutable snapshot). No record/store/
    replay/stability logic is reimplemented and the source store is read at most once.
  - Derive from records, never trust precomputed objects: the source must be a readiness record store
    or an ordered tuple/list of records. A precomputed replay/transition/stability/trace object is not
    an accepted source (it would bypass fresh validation) and is rejected.
  - Application semantics: APPLY only when the latest verdict is READY, latest_ready, and the stability
    gate is stable_ready with no blockers; HOLD when the latest is READY but not stable enough; BLOCK
    when empty or the latest is not READY.
  - Fail closed: a malformed/tampered/broken/wrong-type source or an invalid ``min_ready_tail_records``
    raises a typed ``PaperGovernorApplicationPlanError``; a valid (including empty) chain always yields
    a deterministic plan.
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, persistence, or execution field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.portfolio_governor_readiness import PaperGovernorReadinessStatus
from crypto_core.audit.portfolio_governor_readiness_record_replay import PaperGovernorReadinessRecordReplayError
from crypto_core.audit.portfolio_governor_readiness_record_store import (
    PaperGovernorReadinessRecordStore,
    PaperGovernorReadinessRecordStoreError,
)
from crypto_core.audit.portfolio_governor_readiness_stability import (
    PaperGovernorReadinessStability,
    PaperGovernorReadinessStabilityError,
    PaperGovernorReadinessStabilityPolicy,
    PaperGovernorReadinessStabilityStatus,
    evaluate_paper_governor_readiness_stability,
)

_APPLICATION_PLAN_SCHEMA_VERSION = "paper-governor-application-plan.v1"

_REASON_STABLE_READY = "paper_governor_application_plan:stable_ready"
_REASON_READY_BUT_UNSTABLE = "paper_governor_application_plan:ready_but_unstable"
_REASON_NOT_READY = "paper_governor_application_plan:not_ready"


class PaperGovernorApplicationPlanError(RuntimeError):
    """Raised when an application-plan source is malformed/tampered/broken or its policy is invalid."""


class PaperGovernorApplicationMode(str, Enum):
    """Product-facing paper-governor application decision. Never an order/live action."""

    APPLY = "apply"
    HOLD = "hold"
    BLOCK = "block"


@dataclass(frozen=True)
class PaperGovernorApplicationPlan:
    """Deterministic, immutable paper-governor application decision. PAPER ONLY."""

    schema_version: str
    application_mode: PaperGovernorApplicationMode
    can_apply: bool
    latest_status: PaperGovernorReadinessStatus | None
    latest_ready: bool
    stable_ready: bool
    stability_status: PaperGovernorReadinessStabilityStatus
    entry_count: int
    transition_count: int
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...]
    head_record_digest: str | None
    replay_digest: str
    transition_digest: str
    stability_digest: str
    plan_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def build_paper_governor_application_plan(
    source: object,
    *,
    min_ready_tail_records: int | None = None,
) -> PaperGovernorApplicationPlan:
    """Build a deterministic paper-governor application plan (APPLY / HOLD / BLOCK) from a record chain.

    ``source`` must be a ``PaperGovernorReadinessRecordStore`` or an ordered tuple/list of readiness
    records; a precomputed replay/transition/stability/trace object is rejected so the plan always
    derives from freshly-validated records. The chain is reduced to a stability verdict via a single
    ``evaluate_paper_governor_readiness_stability`` call (one snapshot, derives replay → transition →
    stability). STABLE_READY → APPLY; UNSTABLE → HOLD; NOT_READY (empty or latest non-READY) → BLOCK. A
    malformed/tampered/broken source or an invalid ``min_ready_tail_records`` raises a typed
    ``PaperGovernorApplicationPlanError``. The plan is deterministic and immutable; no order intent or
    live wiring is produced.
    """
    if min_ready_tail_records is not None and not _is_positive_int(min_ready_tail_records):
        raise PaperGovernorApplicationPlanError("paper_governor_application_plan:min_ready_tail_records_invalid")
    if not isinstance(source, (PaperGovernorReadinessRecordStore, tuple, list)):
        # Precomputed objects (replay/transition/stability/trace) and unknown types are not accepted:
        # the plan must derive from records, never trust a stale precomputed object.
        raise PaperGovernorApplicationPlanError("paper_governor_application_plan:source_type_invalid")

    tail = 1 if min_ready_tail_records is None else min_ready_tail_records
    policy = PaperGovernorReadinessStabilityPolicy(min_ready_tail_records=tail)
    try:
        stability: PaperGovernorReadinessStability = evaluate_paper_governor_readiness_stability(source, policy=policy)
    except (
        PaperGovernorReadinessStabilityError,
        PaperGovernorReadinessRecordReplayError,
        PaperGovernorReadinessRecordStoreError,
    ) as exc:
        raise PaperGovernorApplicationPlanError(f"paper_governor_application_plan:source_invalid:{exc}") from exc
    except Exception as exc:
        raise PaperGovernorApplicationPlanError(f"paper_governor_application_plan:source_invalid:{exc}") from exc

    if stability.stability_status is PaperGovernorReadinessStabilityStatus.STABLE_READY:
        application_mode = PaperGovernorApplicationMode.APPLY
        reason_codes: tuple[str, ...] = (_REASON_STABLE_READY,)
    elif stability.stability_status is PaperGovernorReadinessStabilityStatus.UNSTABLE:
        application_mode = PaperGovernorApplicationMode.HOLD
        reason_codes = (_REASON_READY_BUT_UNSTABLE,)
    else:  # NOT_READY (empty chain or latest status not READY)
        application_mode = PaperGovernorApplicationMode.BLOCK
        reason_codes = (_REASON_NOT_READY,)

    can_apply = application_mode is PaperGovernorApplicationMode.APPLY
    blockers = tuple(sorted(set(stability.block_reasons)))

    plan_payload: dict[str, object] = {
        "schema_version": _APPLICATION_PLAN_SCHEMA_VERSION,
        "application_mode": application_mode.value,
        "can_apply": can_apply,
        "latest_status": stability.latest_status.value if stability.latest_status is not None else None,
        "latest_ready": stability.latest_ready,
        "stable_ready": stability.stable_ready,
        "stability_status": stability.stability_status.value,
        "entry_count": stability.entry_count,
        "transition_count": stability.transition_count,
        "reason_codes": list(reason_codes),
        "blockers": list(blockers),
        "head_record_digest": stability.head_record_digest,
        "replay_digest": stability.replay_digest,
        "transition_digest": stability.transition_digest,
        "stability_digest": stability.stability_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorApplicationPlan(
        schema_version=_APPLICATION_PLAN_SCHEMA_VERSION,
        application_mode=application_mode,
        can_apply=can_apply,
        latest_status=stability.latest_status,
        latest_ready=stability.latest_ready,
        stable_ready=stability.stable_ready,
        stability_status=stability.stability_status,
        entry_count=stability.entry_count,
        transition_count=stability.transition_count,
        reason_codes=reason_codes,
        blockers=blockers,
        head_record_digest=stability.head_record_digest,
        replay_digest=stability.replay_digest,
        transition_digest=stability.transition_digest,
        stability_digest=stability.stability_digest,
        plan_digest=_canonical_digest(plan_payload),
    )


def paper_governor_application_plan_to_dict(plan: PaperGovernorApplicationPlan) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper-governor application plan (deterministic shape)."""
    return {
        "schema_version": plan.schema_version,
        "application_mode": plan.application_mode.value,
        "can_apply": plan.can_apply,
        "latest_status": plan.latest_status.value if plan.latest_status is not None else None,
        "latest_ready": plan.latest_ready,
        "stable_ready": plan.stable_ready,
        "stability_status": plan.stability_status.value,
        "entry_count": plan.entry_count,
        "transition_count": plan.transition_count,
        "reason_codes": list(plan.reason_codes),
        "blockers": list(plan.blockers),
        "head_record_digest": plan.head_record_digest,
        "replay_digest": plan.replay_digest,
        "transition_digest": plan.transition_digest,
        "stability_digest": plan.stability_digest,
        "plan_digest": plan.plan_digest,
        "paper_only": plan.paper_only,
        "real_orders_enabled": plan.real_orders_enabled,
        "real_money_enabled": plan.real_money_enabled,
    }


__all__ = [
    "PaperGovernorApplicationMode",
    "PaperGovernorApplicationPlan",
    "PaperGovernorApplicationPlanError",
    "build_paper_governor_application_plan",
    "paper_governor_application_plan_to_dict",
]
