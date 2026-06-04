"""Paper governor readiness / current-exposure gate — Phase 16I.

Turns the paper-governor lifecycle current-state view into a deterministic, fail-closed
*readiness gate*: given the current governor lifecycle state (and an optional exposure policy), it
reports whether the paper governor is ``READY`` to apply, ``BLOCKED`` by governance state, or
``OVER_BUDGET`` against a configured exposure cap. This is a governance boundary — it produces a
verdict only, never an order, route, venue, scheduler, or any live/persistent side effect.

Consumes a ``PaperGovernorLifecycleView`` directly, or a store / ordered ledger entries (delegated to
``summarize_paper_governor_lifecycle``, which reuses replay chain validation). No append / store /
sizing logic is duplicated here.

Conservative defaults (no silent permissive live limits):
  - Caps are opt-in. If a cap is not provided, that budget sub-check is NOT applied and the verdict is
    structural only — absence of a cap means "no exposure gate configured", never "unlimited". The
    configured caps (or None) are recorded on the readiness object for audit.
  - By default any current blocked plan prevents readiness (``blocked_plans_block_readiness=True``).

Fail closed:
  - A malformed / tampered / broken source is rejected through lifecycle/replay validation.
  - An invalid cap (negative / non-finite / non-numeric) or a non-bool policy flag is rejected.
  - A non-paper lifecycle view is rejected.

PAPER ONLY: no order intent, live route, venue execution, scheduler, or execution field.

PRD reference: §1.14-§1.28 Risk/Governance, §1.21 No-Trade, §4 DecisionLedger/EvidenceStore, Phase 16I.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.portfolio_governor_ledger import PortfolioGovernorLedgerEntry
from crypto_core.audit.portfolio_governor_ledger_store import PortfolioGovernorLedgerStore
from crypto_core.audit.portfolio_governor_lifecycle import (
    PaperGovernorLifecycleView,
    summarize_paper_governor_lifecycle,
)

_READINESS_SCHEMA_VERSION = "paper-governor-readiness.v1"
_LIFECYCLE_SCHEMA_VERSION = "portfolio-governor-lifecycle-view.v1"
_TOLERANCE = 1e-9

_BLOCKED_PLANS_PRESENT = "paper_governor_readiness:blocked_plans_present"
_ACTIVE_WEIGHT_EXCEEDS_CAP = "paper_governor_readiness:active_weight_exceeds_cap"
_ACTIVE_NOTIONAL_EXCEEDS_CAP = "paper_governor_readiness:active_notional_exceeds_cap"


class PaperGovernorReadinessError(RuntimeError):
    """Raised when a readiness input is malformed, non-paper, or has an invalid cap (fail-closed)."""


class PaperGovernorReadinessStatus(str, Enum):
    """Deterministic paper-governor readiness verdict. Never an order/live action."""

    READY = "ready"
    BLOCKED = "blocked"
    OVER_BUDGET = "over_budget"


@dataclass(frozen=True)
class PaperGovernorReadinessPolicy:
    """Opt-in exposure policy for the readiness gate. Caps None = sub-check not applied. PAPER ONLY."""

    max_current_active_weight: float | None = None
    max_current_active_notional: float | None = None
    blocked_plans_block_readiness: bool = True


#: Default policy: no exposure caps configured, blocked plans prevent readiness (conservative).
_DEFAULT_POLICY = PaperGovernorReadinessPolicy()


@dataclass(frozen=True)
class PaperGovernorReadiness:
    """Deterministic, immutable paper-governor readiness verdict. PAPER ONLY."""

    schema_version: str
    status: PaperGovernorReadinessStatus
    ready: bool
    head_digest: str | None
    entry_count: int
    active_count: int
    blocked_count: int
    total_active_weight: float
    total_active_notional: float
    max_current_active_weight: float | None
    max_current_active_notional: float | None
    blocked_plans_block_readiness: bool
    block_reasons: tuple[str, ...]
    blocker_summary: tuple[str, ...]
    replay_digest: str
    lifecycle_digest: str
    readiness_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_plan_states(states: tuple[object, ...]) -> list[list[object]]:
    return [
        [
            state.plan_id,
            state.status.value,
            state.entry_digest,
            state.total_weight,
            state.total_notional,
            list(state.blockers),
        ]
        for state in states
    ]


def _expected_lifecycle_digest(view: PaperGovernorLifecycleView) -> str:
    # Mirror of the lifecycle view digest payload (``summarize_paper_governor_lifecycle``). Recomputed
    # here only to verify a directly-supplied view has not been tampered with (e.g. via
    # ``dataclasses.replace`` lowering an exposure total while keeping the original digest) before its
    # exposure fields are trusted by this fail-closed gate. A real view keeps this in lockstep
    # (asserted by the tests). Views produced through a store/entries source are validated by replay.
    payload: dict[str, object] = {
        "schema_version": _LIFECYCLE_SCHEMA_VERSION,
        "head_digest": view.head_digest,
        "entry_count": view.entry_count,
        "active_count": view.active_count,
        "blocked_count": view.blocked_count,
        "current_active_plans": _serialize_plan_states(view.current_active_plans),
        "current_blocked_plans": _serialize_plan_states(view.current_blocked_plans),
        "total_active_weight": view.total_active_weight,
        "total_active_notional": view.total_active_notional,
        "blocker_summary": list(view.blocker_summary),
        "replay_digest": view.replay_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _validate_policy(policy: PaperGovernorReadinessPolicy) -> None:
    if not isinstance(policy, PaperGovernorReadinessPolicy):
        raise PaperGovernorReadinessError("paper_governor_readiness:policy_malformed")
    if not isinstance(policy.blocked_plans_block_readiness, bool):
        raise PaperGovernorReadinessError("paper_governor_readiness:policy_flag_invalid")
    if policy.max_current_active_weight is not None and not _is_non_negative_finite(policy.max_current_active_weight):
        raise PaperGovernorReadinessError("paper_governor_readiness:max_active_weight_invalid")
    if policy.max_current_active_notional is not None and not _is_non_negative_finite(
        policy.max_current_active_notional
    ):
        raise PaperGovernorReadinessError("paper_governor_readiness:max_active_notional_invalid")


def _lifecycle_view_of(
    source: PaperGovernorLifecycleView
    | PortfolioGovernorLedgerStore
    | tuple[PortfolioGovernorLedgerEntry, ...]
    | list[PortfolioGovernorLedgerEntry],
) -> PaperGovernorLifecycleView:
    if isinstance(source, PaperGovernorLifecycleView):
        view = source
        # A directly-supplied view is not chain-validated by replay, so its exposure fields cannot be
        # trusted on faith: re-verify it hashes to its own ``lifecycle_digest`` (tamper detection).
        if not isinstance(view.lifecycle_digest, str) or view.lifecycle_digest != _expected_lifecycle_digest(view):
            raise PaperGovernorReadinessError("paper_governor_readiness:lifecycle_digest_mismatch")
    else:
        # Delegates chain validation to the lifecycle/replay layer (reused, not duplicated).
        view = summarize_paper_governor_lifecycle(source)
    if not (view.paper_only is True and view.real_orders_enabled is False and view.real_money_enabled is False):
        raise PaperGovernorReadinessError("paper_governor_readiness:non_paper_view_rejected")
    return view


def evaluate_paper_governor_readiness(
    source: PaperGovernorLifecycleView
    | PortfolioGovernorLedgerStore
    | tuple[PortfolioGovernorLedgerEntry, ...]
    | list[PortfolioGovernorLedgerEntry],
    *,
    policy: PaperGovernorReadinessPolicy = _DEFAULT_POLICY,
) -> PaperGovernorReadiness:
    """Evaluate paper-governor readiness over the current lifecycle state under ``policy``.

    Returns a deterministic verdict: ``READY`` only when no current plan is blocked (per policy) and
    every provided exposure cap is satisfied; ``BLOCKED`` when a current plan is blocked; ``OVER_BUDGET``
    when an exposure cap is exceeded (and no governance block applies). A malformed/tampered/broken
    source fails closed through lifecycle/replay validation, and an invalid cap is rejected. Caps are
    opt-in: an unset cap applies no budget gate (structural verdict only). No order intent or live
    wiring is produced.
    """
    _validate_policy(policy)
    view = _lifecycle_view_of(source)

    reasons: list[str] = []
    if policy.blocked_plans_block_readiness and view.blocked_count > 0:
        reasons.append(_BLOCKED_PLANS_PRESENT)
    weight_cap = policy.max_current_active_weight
    if weight_cap is not None and view.total_active_weight > float(weight_cap) + _TOLERANCE:
        reasons.append(_ACTIVE_WEIGHT_EXCEEDS_CAP)
    notional_cap = policy.max_current_active_notional
    if notional_cap is not None and view.total_active_notional > float(notional_cap) + _TOLERANCE:
        reasons.append(_ACTIVE_NOTIONAL_EXCEEDS_CAP)
    block_reasons = tuple(sorted(set(reasons)))

    if _BLOCKED_PLANS_PRESENT in block_reasons:
        status = PaperGovernorReadinessStatus.BLOCKED
    elif block_reasons:
        status = PaperGovernorReadinessStatus.OVER_BUDGET
    else:
        status = PaperGovernorReadinessStatus.READY

    readiness_payload: dict[str, object] = {
        "schema_version": _READINESS_SCHEMA_VERSION,
        "status": status.value,
        "head_digest": view.head_digest,
        "entry_count": view.entry_count,
        "active_count": view.active_count,
        "blocked_count": view.blocked_count,
        "total_active_weight": view.total_active_weight,
        "total_active_notional": view.total_active_notional,
        "max_current_active_weight": weight_cap,
        "max_current_active_notional": notional_cap,
        "blocked_plans_block_readiness": policy.blocked_plans_block_readiness,
        "block_reasons": list(block_reasons),
        "blocker_summary": list(view.blocker_summary),
        "replay_digest": view.replay_digest,
        "lifecycle_digest": view.lifecycle_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PaperGovernorReadiness(
        schema_version=_READINESS_SCHEMA_VERSION,
        status=status,
        ready=status == PaperGovernorReadinessStatus.READY,
        head_digest=view.head_digest,
        entry_count=view.entry_count,
        active_count=view.active_count,
        blocked_count=view.blocked_count,
        total_active_weight=view.total_active_weight,
        total_active_notional=view.total_active_notional,
        max_current_active_weight=weight_cap,
        max_current_active_notional=notional_cap,
        blocked_plans_block_readiness=policy.blocked_plans_block_readiness,
        block_reasons=block_reasons,
        blocker_summary=view.blocker_summary,
        replay_digest=view.replay_digest,
        lifecycle_digest=view.lifecycle_digest,
        readiness_digest=_canonical_digest(readiness_payload),
    )


def paper_governor_readiness_to_dict(readiness: PaperGovernorReadiness) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a readiness verdict (deterministic key/value shape)."""
    return {
        "schema_version": readiness.schema_version,
        "status": readiness.status.value,
        "ready": readiness.ready,
        "head_digest": readiness.head_digest,
        "entry_count": readiness.entry_count,
        "active_count": readiness.active_count,
        "blocked_count": readiness.blocked_count,
        "total_active_weight": readiness.total_active_weight,
        "total_active_notional": readiness.total_active_notional,
        "max_current_active_weight": readiness.max_current_active_weight,
        "max_current_active_notional": readiness.max_current_active_notional,
        "blocked_plans_block_readiness": readiness.blocked_plans_block_readiness,
        "block_reasons": list(readiness.block_reasons),
        "blocker_summary": list(readiness.blocker_summary),
        "replay_digest": readiness.replay_digest,
        "lifecycle_digest": readiness.lifecycle_digest,
        "readiness_digest": readiness.readiness_digest,
        "paper_only": readiness.paper_only,
        "real_orders_enabled": readiness.real_orders_enabled,
        "real_money_enabled": readiness.real_money_enabled,
    }
