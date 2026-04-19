"""Crypto multi-sleeve portfolio contracts.

Deterministic, serialization-friendly portfolio allocation contracts for the
crypto paper-live control surface.

Phase 14A scope:
  - explicit sleeve identity/state contracts
  - validated allocation decomposition
  - compact operator-facing portfolio snapshot
  - additive governance hooks only

Design rules:
  - frozen dataclasses only
  - fail-closed validation on invalid or ambiguous weights
  - no synthetic alpha, PnL, or performance fields
  - crypto-only sleeve taxonomy
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

_ALLOCATION_EPSILON = 1e-9


class CryptoSleeveType(str, Enum):
    """Research-aligned crypto sleeve categories."""

    MICROSTRUCTURE = "microstructure"
    TREND = "trend"
    CARRY = "carry"
    EVENT_VOL = "event_vol"


class CryptoSleeveStatus(str, Enum):
    """Deterministic sleeve lifecycle state."""

    DEFINED = "defined"
    ENABLED = "enabled"
    ALLOCATED = "allocated"
    BLOCKED = "blocked"
    DISABLED = "disabled"


class SleevePortfolioValidationError(ValueError):
    """Raised when sleeve portfolio state is invalid."""


class SleevePortfolioCorruptError(RuntimeError):
    """Raised when a persisted sleeve portfolio payload is malformed."""


@dataclass(frozen=True)
class CryptoSleeveState:
    """Single crypto sleeve identity and allocation state.

    Allocation decomposition is explicit:
      target_allocation = active_allocation + blocked_allocation + disabled_allocation

    This keeps the contract additive and truthful without inventing runtime PnL
    or alpha claims.
    """

    sleeve_id: str
    sleeve_type: CryptoSleeveType
    status: CryptoSleeveStatus
    target_allocation: float = 0.0
    active_allocation: float = 0.0
    blocked_allocation: float = 0.0
    disabled_allocation: float = 0.0
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_summary: str = ""
    readiness_level: str | None = None
    escalation_stage: str | None = None


@dataclass(frozen=True)
class SleeveAllocationSummary:
    """Compact portfolio allocation summary across all sleeves."""

    target_allocated_share: float
    active_allocated_share: float
    blocked_allocated_share: float
    disabled_allocated_share: float
    unallocated_share: float
    total_sleeves: int
    defined_sleeves: int
    enabled_sleeves: int
    allocated_sleeves: int
    blocked_sleeves: int
    disabled_sleeves: int


@dataclass(frozen=True)
class SleevePortfolioSnapshot:
    """Operator-facing sleeve portfolio snapshot."""

    as_of_ns: int
    sleeves: tuple[CryptoSleeveState, ...] = field(default_factory=tuple)
    allocation: SleeveAllocationSummary = field(
        default_factory=lambda: SleeveAllocationSummary(
            target_allocated_share=0.0,
            active_allocated_share=0.0,
            blocked_allocated_share=0.0,
            disabled_allocated_share=0.0,
            unallocated_share=1.0,
            total_sleeves=0,
            defined_sleeves=0,
            enabled_sleeves=0,
            allocated_sleeves=0,
            blocked_sleeves=0,
            disabled_sleeves=0,
        )
    )
    enabled_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    allocated_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)
    blocked_reason_summaries: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
    readiness_level: str | None = None
    readiness_is_supportive: bool = False
    escalation_allowed_next_step: str | None = None
    external_regime_execution_blocked: bool | None = None


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a non-empty str")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be an int")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a bool")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a str or None")
    return value


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a list/tuple of str")
    return tuple(value)


def _require_float_like(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} must be finite")
    if result < -_ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} cannot be negative")
    if result > 1.0 + _ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError(f"Sleeve allocation field {field_name!r} cannot exceed 1.0")
    return 0.0 if abs(result) <= _ALLOCATION_EPSILON else result


def _nearly_equal(left: float, right: float) -> bool:
    return abs(left - right) <= _ALLOCATION_EPSILON


def _validate_sleeve_state(state: CryptoSleeveState) -> CryptoSleeveState:
    if not state.sleeve_id:
        raise SleevePortfolioValidationError("sleeve_id must be non-empty")

    target = _require_float_like(state.target_allocation, "target_allocation")
    active = _require_float_like(state.active_allocation, "active_allocation")
    blocked = _require_float_like(state.blocked_allocation, "blocked_allocation")
    disabled = _require_float_like(state.disabled_allocation, "disabled_allocation")

    decomposition_total = active + blocked + disabled
    if not _nearly_equal(target, decomposition_total):
        raise SleevePortfolioValidationError(
            f"Sleeve {state.sleeve_id!r} target_allocation must equal active + blocked + disabled"
        )

    if state.status == CryptoSleeveStatus.DEFINED:
        if any(value > 0.0 for value in (target, active, blocked, disabled)):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'defined' cannot carry allocation"
            )
    elif state.status == CryptoSleeveStatus.ENABLED:
        if any(value > 0.0 for value in (target, active, blocked, disabled)):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'enabled' cannot carry allocation until allocated"
            )
    elif state.status == CryptoSleeveStatus.ALLOCATED:
        if active <= 0.0 or blocked > 0.0 or disabled > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'allocated' must have only active allocation"
            )
    elif state.status == CryptoSleeveStatus.BLOCKED:
        if blocked <= 0.0 or active > 0.0 or disabled > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' must have only blocked allocation"
            )
        if not state.blocked_reasons and not state.reason_summary:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' requires a blocking reason"
            )
    elif state.status == CryptoSleeveStatus.DISABLED:
        if disabled <= 0.0 or active > 0.0 or blocked > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'disabled' must have only disabled allocation"
            )

    if state.status != CryptoSleeveStatus.BLOCKED and state.blocked_reasons:
        raise SleevePortfolioValidationError(
            f"Sleeve {state.sleeve_id!r} cannot carry blocked_reasons unless status is 'blocked'"
        )

    return CryptoSleeveState(
        sleeve_id=state.sleeve_id,
        sleeve_type=state.sleeve_type,
        status=state.status,
        target_allocation=target,
        active_allocation=active,
        blocked_allocation=blocked,
        disabled_allocation=disabled,
        blocked_reasons=tuple(state.blocked_reasons),
        reason_summary=state.reason_summary,
        readiness_level=state.readiness_level,
        escalation_stage=state.escalation_stage,
    )


def build_sleeve_portfolio_snapshot(
    *,
    sleeves: tuple[CryptoSleeveState, ...] = (),
    as_of_ns: int,
    readiness_level: str | None = None,
    readiness_is_supportive: bool = False,
    escalation_allowed_next_step: str | None = None,
    external_regime_execution_blocked: bool | None = None,
) -> SleevePortfolioSnapshot:
    """Build a validated sleeve portfolio snapshot."""
    if not isinstance(as_of_ns, int) or as_of_ns < 0:
        raise SleevePortfolioValidationError("as_of_ns must be a non-negative int")

    validated: list[CryptoSleeveState] = []
    seen_ids: set[str] = set()
    for sleeve in sleeves:
        checked = _validate_sleeve_state(sleeve)
        if checked.sleeve_id in seen_ids:
            raise SleevePortfolioValidationError(f"Duplicate sleeve_id {checked.sleeve_id!r}")
        seen_ids.add(checked.sleeve_id)
        validated.append(checked)

    total_target = sum(sleeve.target_allocation for sleeve in validated)
    total_active = sum(sleeve.active_allocation for sleeve in validated)
    total_blocked = sum(sleeve.blocked_allocation for sleeve in validated)
    total_disabled = sum(sleeve.disabled_allocation for sleeve in validated)

    if total_target > 1.0 + _ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError("Total target allocation cannot exceed 1.0")
    if not _nearly_equal(total_target, total_active + total_blocked + total_disabled):
        raise SleevePortfolioValidationError("Portfolio allocation decomposition is inconsistent")

    unallocated_share = 1.0 - total_target
    if unallocated_share < -_ALLOCATION_EPSILON:
        raise SleevePortfolioValidationError("Unallocated share cannot be negative")
    if abs(unallocated_share) <= _ALLOCATION_EPSILON:
        unallocated_share = 0.0

    enabled_ids = tuple(
        sleeve.sleeve_id
        for sleeve in validated
        if sleeve.status in {CryptoSleeveStatus.ENABLED, CryptoSleeveStatus.ALLOCATED}
    )
    blocked_ids = tuple(sleeve.sleeve_id for sleeve in validated if sleeve.status == CryptoSleeveStatus.BLOCKED)
    allocated_ids = tuple(sleeve.sleeve_id for sleeve in validated if sleeve.status == CryptoSleeveStatus.ALLOCATED)
    blocked_reason_summaries = tuple(
        f"{sleeve.sleeve_id}:{sleeve.reason_summary or ', '.join(sleeve.blocked_reasons)}"
        for sleeve in validated
        if sleeve.status == CryptoSleeveStatus.BLOCKED
    )

    allocation = SleeveAllocationSummary(
        target_allocated_share=total_target,
        active_allocated_share=total_active,
        blocked_allocated_share=total_blocked,
        disabled_allocated_share=total_disabled,
        unallocated_share=unallocated_share,
        total_sleeves=len(validated),
        defined_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.DEFINED),
        enabled_sleeves=sum(
            1 for sleeve in validated if sleeve.status in {CryptoSleeveStatus.ENABLED, CryptoSleeveStatus.ALLOCATED}
        ),
        allocated_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.ALLOCATED),
        blocked_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.BLOCKED),
        disabled_sleeves=sum(1 for sleeve in validated if sleeve.status == CryptoSleeveStatus.DISABLED),
    )

    if not validated:
        summary = "No explicit sleeves configured; sleeve-level capital remains fully unallocated."
    else:
        summary = (
            f"sleeves={allocation.total_sleeves}; enabled={allocation.enabled_sleeves}; "
            f"blocked={allocation.blocked_sleeves}; allocated_share={allocation.target_allocated_share:.3f}; "
            f"unallocated_share={allocation.unallocated_share:.3f}"
        )

    return SleevePortfolioSnapshot(
        as_of_ns=as_of_ns,
        sleeves=tuple(validated),
        allocation=allocation,
        enabled_sleeve_ids=enabled_ids,
        blocked_sleeve_ids=blocked_ids,
        allocated_sleeve_ids=allocated_ids,
        blocked_reason_summaries=blocked_reason_summaries,
        summary=summary,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        escalation_allowed_next_step=escalation_allowed_next_step,
        external_regime_execution_blocked=external_regime_execution_blocked,
    )


def crypto_sleeve_state_to_dict(state: CryptoSleeveState) -> dict:
    """Serialize CryptoSleeveState to a plain dict."""
    return {
        "sleeve_id": state.sleeve_id,
        "sleeve_type": state.sleeve_type.value,
        "status": state.status.value,
        "target_allocation": state.target_allocation,
        "active_allocation": state.active_allocation,
        "blocked_allocation": state.blocked_allocation,
        "disabled_allocation": state.disabled_allocation,
        "blocked_reasons": list(state.blocked_reasons),
        "reason_summary": state.reason_summary,
        "readiness_level": state.readiness_level,
        "escalation_stage": state.escalation_stage,
    }


def crypto_sleeve_state_from_dict(data: dict) -> CryptoSleeveState:
    """Deserialize CryptoSleeveState from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve state payload must be a dict, got {type(data).__name__!r}")

    try:
        state = CryptoSleeveState(
            sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
            sleeve_type=CryptoSleeveType(_require_non_empty_str(data.get("sleeve_type"), "sleeve_type")),
            status=CryptoSleeveStatus(_require_non_empty_str(data.get("status"), "status")),
            target_allocation=_require_float_like(data.get("target_allocation", 0.0), "target_allocation"),
            active_allocation=_require_float_like(data.get("active_allocation", 0.0), "active_allocation"),
            blocked_allocation=_require_float_like(data.get("blocked_allocation", 0.0), "blocked_allocation"),
            disabled_allocation=_require_float_like(data.get("disabled_allocation", 0.0), "disabled_allocation"),
            blocked_reasons=_tuple_of_strings(data.get("blocked_reasons", ()), "blocked_reasons"),
            reason_summary=("" if data.get("reason_summary", "") is None else str(data.get("reason_summary", ""))),
            readiness_level=_optional_str(data.get("readiness_level"), "readiness_level"),
            escalation_stage=_optional_str(data.get("escalation_stage"), "escalation_stage"),
        )
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc

    try:
        return _validate_sleeve_state(state)
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


def sleeve_allocation_summary_to_dict(summary: SleeveAllocationSummary) -> dict:
    """Serialize SleeveAllocationSummary to a plain dict."""
    return {
        "target_allocated_share": summary.target_allocated_share,
        "active_allocated_share": summary.active_allocated_share,
        "blocked_allocated_share": summary.blocked_allocated_share,
        "disabled_allocated_share": summary.disabled_allocated_share,
        "unallocated_share": summary.unallocated_share,
        "total_sleeves": summary.total_sleeves,
        "defined_sleeves": summary.defined_sleeves,
        "enabled_sleeves": summary.enabled_sleeves,
        "allocated_sleeves": summary.allocated_sleeves,
        "blocked_sleeves": summary.blocked_sleeves,
        "disabled_sleeves": summary.disabled_sleeves,
    }


def sleeve_allocation_summary_from_dict(data: dict) -> SleeveAllocationSummary:
    """Deserialize SleeveAllocationSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve allocation summary payload must be a dict, got {type(data).__name__!r}"
        )
    try:
        return SleeveAllocationSummary(
            target_allocated_share=_require_float_like(
                data.get("target_allocated_share", 0.0), "target_allocated_share"
            ),
            active_allocated_share=_require_float_like(
                data.get("active_allocated_share", 0.0), "active_allocated_share"
            ),
            blocked_allocated_share=_require_float_like(
                data.get("blocked_allocated_share", 0.0), "blocked_allocated_share"
            ),
            disabled_allocated_share=_require_float_like(
                data.get("disabled_allocated_share", 0.0), "disabled_allocated_share"
            ),
            unallocated_share=_require_float_like(data.get("unallocated_share", 0.0), "unallocated_share"),
            total_sleeves=_require_int(data.get("total_sleeves"), "total_sleeves"),
            defined_sleeves=_require_int(data.get("defined_sleeves"), "defined_sleeves"),
            enabled_sleeves=_require_int(data.get("enabled_sleeves"), "enabled_sleeves"),
            allocated_sleeves=_require_int(data.get("allocated_sleeves"), "allocated_sleeves"),
            blocked_sleeves=_require_int(data.get("blocked_sleeves"), "blocked_sleeves"),
            disabled_sleeves=_require_int(data.get("disabled_sleeves"), "disabled_sleeves"),
        )
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


def sleeve_portfolio_snapshot_to_dict(snapshot: SleevePortfolioSnapshot) -> dict:
    """Serialize SleevePortfolioSnapshot to a plain dict."""
    return {
        "as_of_ns": snapshot.as_of_ns,
        "sleeves": [crypto_sleeve_state_to_dict(sleeve) for sleeve in snapshot.sleeves],
        "allocation": sleeve_allocation_summary_to_dict(snapshot.allocation),
        "enabled_sleeve_ids": list(snapshot.enabled_sleeve_ids),
        "blocked_sleeve_ids": list(snapshot.blocked_sleeve_ids),
        "allocated_sleeve_ids": list(snapshot.allocated_sleeve_ids),
        "blocked_reason_summaries": list(snapshot.blocked_reason_summaries),
        "summary": snapshot.summary,
        "readiness_level": snapshot.readiness_level,
        "readiness_is_supportive": snapshot.readiness_is_supportive,
        "escalation_allowed_next_step": snapshot.escalation_allowed_next_step,
        "external_regime_execution_blocked": snapshot.external_regime_execution_blocked,
    }


def sleeve_portfolio_snapshot_from_dict(data: dict) -> SleevePortfolioSnapshot:
    """Deserialize SleevePortfolioSnapshot from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio snapshot payload must be a dict, got {type(data).__name__!r}"
        )

    sleeves_value = data.get("sleeves", ())
    if not isinstance(sleeves_value, (list, tuple)):
        raise SleevePortfolioCorruptError("Sleeve portfolio field 'sleeves' must be a list/tuple")

    sleeves = tuple(crypto_sleeve_state_from_dict(item) for item in sleeves_value)
    snapshot = build_sleeve_portfolio_snapshot(
        sleeves=sleeves,
        as_of_ns=_require_int(data.get("as_of_ns"), "as_of_ns"),
        readiness_level=_optional_str(data.get("readiness_level"), "readiness_level"),
        readiness_is_supportive=_require_bool(data.get("readiness_is_supportive", False), "readiness_is_supportive"),
        escalation_allowed_next_step=_optional_str(
            data.get("escalation_allowed_next_step"), "escalation_allowed_next_step"
        ),
        external_regime_execution_blocked=(
            None
            if data.get("external_regime_execution_blocked") is None
            else _require_bool(data.get("external_regime_execution_blocked"), "external_regime_execution_blocked")
        ),
    )

    allocation_value = data.get("allocation")
    if allocation_value is not None:
        restored_allocation = sleeve_allocation_summary_from_dict(allocation_value)
        if restored_allocation != snapshot.allocation:
            raise SleevePortfolioCorruptError("Sleeve portfolio allocation summary does not match sleeve decomposition")

    enabled_ids = _tuple_of_strings(data.get("enabled_sleeve_ids", ()), "enabled_sleeve_ids")
    blocked_ids = _tuple_of_strings(data.get("blocked_sleeve_ids", ()), "blocked_sleeve_ids")
    allocated_ids = _tuple_of_strings(data.get("allocated_sleeve_ids", ()), "allocated_sleeve_ids")
    blocked_reason_summaries = _tuple_of_strings(data.get("blocked_reason_summaries", ()), "blocked_reason_summaries")

    if enabled_ids and enabled_ids != snapshot.enabled_sleeve_ids:
        raise SleevePortfolioCorruptError("Enabled sleeve ids do not match sleeve statuses")
    if blocked_ids and blocked_ids != snapshot.blocked_sleeve_ids:
        raise SleevePortfolioCorruptError("Blocked sleeve ids do not match sleeve statuses")
    if allocated_ids and allocated_ids != snapshot.allocated_sleeve_ids:
        raise SleevePortfolioCorruptError("Allocated sleeve ids do not match sleeve statuses")
    if blocked_reason_summaries and blocked_reason_summaries != snapshot.blocked_reason_summaries:
        raise SleevePortfolioCorruptError("Blocked reason summaries do not match sleeve states")

    return snapshot
