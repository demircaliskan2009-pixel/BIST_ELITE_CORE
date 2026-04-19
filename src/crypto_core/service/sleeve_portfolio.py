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
from dataclasses import dataclass, field, replace
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


class SleeveReasonSource(str, Enum):
    """Compact source taxonomy for sleeve gating reasons."""

    CONFIGURATION = "configuration"
    OPERATOR = "operator"
    GOVERNANCE = "governance"
    EVIDENCE = "evidence"


class SleeveInactiveCapitalMode(str, Enum):
    """Deterministic handling for inactive sleeve target capital."""

    CONSERVE = "conserve"
    REDISTRIBUTE_PRO_RATA = "redistribute_pro_rata"


class SleevePortfolioValidationError(ValueError):
    """Raised when sleeve portfolio state is invalid."""


class SleevePortfolioCorruptError(RuntimeError):
    """Raised when a persisted sleeve portfolio payload is malformed."""


@dataclass(frozen=True)
class SleeveReason:
    """Compact sleeve-level explanation for current workflow state."""

    source: SleeveReasonSource
    code: str
    summary: str
    required_change: str = ""


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
    reasons: tuple[SleeveReason, ...] = field(default_factory=tuple)
    required_changes: tuple[str, ...] = field(default_factory=tuple)
    effective_allocation: float = 0.0


@dataclass(frozen=True)
class SleeveAllocationPolicy:
    """Explicit policy for recomputing effective sleeve deployment."""

    blocked_allocation_mode: SleeveInactiveCapitalMode = SleeveInactiveCapitalMode.CONSERVE
    disabled_allocation_mode: SleeveInactiveCapitalMode = SleeveInactiveCapitalMode.CONSERVE


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
class SleeveEffectiveAllocationSummary:
    """Effective post-policy deployment summary across all sleeves."""

    effective_allocated_share: float
    effective_unallocated_share: float
    redistributed_blocked_share: float
    redistributed_disabled_share: float
    conserved_blocked_share: float
    conserved_disabled_share: float
    recipient_sleeve_ids: tuple[str, ...] = field(default_factory=tuple)


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
    allocation_policy: SleeveAllocationPolicy = field(default_factory=SleeveAllocationPolicy)
    effective_allocation: SleeveEffectiveAllocationSummary = field(
        default_factory=lambda: SleeveEffectiveAllocationSummary(
            effective_allocated_share=0.0,
            effective_unallocated_share=1.0,
            redistributed_blocked_share=0.0,
            redistributed_disabled_share=0.0,
            conserved_blocked_share=0.0,
            conserved_disabled_share=0.0,
            recipient_sleeve_ids=(),
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
    workflow_status: str = "static"
    comparison_to_previous: dict = field(default_factory=dict)
    history_summary: dict = field(default_factory=dict)


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


def _tuple_of_reasons(value: object, field_name: str) -> tuple[SleeveReason, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleevePortfolioCorruptError(f"Sleeve portfolio field {field_name!r} must be a list/tuple")
    return tuple(item if isinstance(item, SleeveReason) else sleeve_reason_from_dict(item) for item in value)


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
    effective_allocation = _require_float_like(state.effective_allocation, "effective_allocation")

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
        if active > 0.0 or disabled > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' must have only blocked allocation"
            )
        if not _nearly_equal(blocked, target):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' must map target allocation to blocked allocation"
            )
        if not state.blocked_reasons and not state.reason_summary and not state.reasons:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'blocked' requires a blocking reason"
            )
    elif state.status == CryptoSleeveStatus.DISABLED:
        if active > 0.0 or blocked > 0.0:
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'disabled' must have only disabled allocation"
            )
        if not _nearly_equal(disabled, target):
            raise SleevePortfolioValidationError(
                f"Sleeve {state.sleeve_id!r} in status 'disabled' must map target allocation to disabled allocation"
            )

    if state.status != CryptoSleeveStatus.BLOCKED and state.blocked_reasons:
        raise SleevePortfolioValidationError(
            f"Sleeve {state.sleeve_id!r} cannot carry blocked_reasons unless status is 'blocked'"
        )

    required_changes = tuple(item for item in state.required_changes if item)
    reasons = tuple(state.reasons)
    if reasons:
        for item in reasons:
            if not item.code:
                raise SleevePortfolioValidationError(f"Sleeve {state.sleeve_id!r} reason code must be non-empty")
            if not item.summary:
                raise SleevePortfolioValidationError(f"Sleeve {state.sleeve_id!r} reason summary must be non-empty")
        if not required_changes:
            required_changes = tuple(item.required_change for item in reasons if item.required_change)

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
        reasons=reasons,
        required_changes=required_changes,
        effective_allocation=effective_allocation,
    )


def _compute_effective_allocation(
    sleeves: tuple[CryptoSleeveState, ...],
    allocation: SleeveAllocationSummary,
    allocation_policy: SleeveAllocationPolicy,
) -> tuple[tuple[CryptoSleeveState, ...], SleeveEffectiveAllocationSummary]:
    allocated_sleeves = tuple(
        sleeve for sleeve in sleeves if sleeve.status == CryptoSleeveStatus.ALLOCATED and sleeve.active_allocation > 0.0
    )
    allocated_share = sum(sleeve.active_allocation for sleeve in allocated_sleeves)

    redistribute_blocked = (
        allocation.blocked_allocated_share
        if allocation_policy.blocked_allocation_mode == SleeveInactiveCapitalMode.REDISTRIBUTE_PRO_RATA
        and allocated_share > 0.0
        else 0.0
    )
    redistribute_disabled = (
        allocation.disabled_allocated_share
        if allocation_policy.disabled_allocation_mode == SleeveInactiveCapitalMode.REDISTRIBUTE_PRO_RATA
        and allocated_share > 0.0
        else 0.0
    )
    redistributed_share = redistribute_blocked + redistribute_disabled

    effective_sleeves: list[CryptoSleeveState] = []
    for sleeve in sleeves:
        effective_allocation = sleeve.active_allocation
        if redistributed_share > 0.0 and sleeve.status == CryptoSleeveStatus.ALLOCATED and allocated_share > 0.0:
            effective_allocation += redistributed_share * (sleeve.active_allocation / allocated_share)
        effective_sleeves.append(replace(sleeve, effective_allocation=effective_allocation))

    effective_summary = SleeveEffectiveAllocationSummary(
        effective_allocated_share=allocated_share + redistributed_share,
        effective_unallocated_share=allocation.unallocated_share,
        redistributed_blocked_share=redistribute_blocked,
        redistributed_disabled_share=redistribute_disabled,
        conserved_blocked_share=allocation.blocked_allocated_share - redistribute_blocked,
        conserved_disabled_share=allocation.disabled_allocated_share - redistribute_disabled,
        recipient_sleeve_ids=tuple(sleeve.sleeve_id for sleeve in allocated_sleeves),
    )
    return tuple(effective_sleeves), effective_summary


def build_sleeve_portfolio_snapshot(
    *,
    sleeves: tuple[CryptoSleeveState, ...] = (),
    as_of_ns: int,
    readiness_level: str | None = None,
    readiness_is_supportive: bool = False,
    escalation_allowed_next_step: str | None = None,
    external_regime_execution_blocked: bool | None = None,
    allocation_policy: SleeveAllocationPolicy | None = None,
    workflow_status: str = "static",
    comparison_to_previous: dict | None = None,
    history_summary: dict | None = None,
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
    resolved_policy = SleeveAllocationPolicy() if allocation_policy is None else allocation_policy
    effective_sleeves, effective_allocation = _compute_effective_allocation(
        tuple(validated),
        allocation,
        resolved_policy,
    )

    if not effective_sleeves:
        summary = "No explicit sleeves configured; sleeve-level capital remains fully unallocated."
    else:
        summary = (
            f"sleeves={allocation.total_sleeves}; enabled={allocation.enabled_sleeves}; "
            f"blocked={allocation.blocked_sleeves}; allocated_share={allocation.target_allocated_share:.3f}; "
            f"unallocated_share={allocation.unallocated_share:.3f}"
        )
        if not _nearly_equal(allocation.active_allocated_share, effective_allocation.effective_allocated_share):
            summary += f"; effective_allocated_share={effective_allocation.effective_allocated_share:.3f}"

    return SleevePortfolioSnapshot(
        as_of_ns=as_of_ns,
        sleeves=effective_sleeves,
        allocation=allocation,
        allocation_policy=resolved_policy,
        effective_allocation=effective_allocation,
        enabled_sleeve_ids=enabled_ids,
        blocked_sleeve_ids=blocked_ids,
        allocated_sleeve_ids=allocated_ids,
        blocked_reason_summaries=blocked_reason_summaries,
        summary=summary,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        escalation_allowed_next_step=escalation_allowed_next_step,
        external_regime_execution_blocked=external_regime_execution_blocked,
        workflow_status=workflow_status,
        comparison_to_previous={} if comparison_to_previous is None else dict(comparison_to_previous),
        history_summary={} if history_summary is None else dict(history_summary),
    )


def sleeve_reason_to_dict(reason: SleeveReason) -> dict:
    """Serialize SleeveReason to a plain dict."""
    return {
        "source": reason.source.value,
        "code": reason.code,
        "summary": reason.summary,
        "required_change": reason.required_change,
    }


def sleeve_reason_from_dict(data: dict) -> SleeveReason:
    """Deserialize SleeveReason from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(f"Sleeve reason payload must be a dict, got {type(data).__name__!r}")
    source = SleeveReasonSource(_require_non_empty_str(data.get("source"), "source"))
    code = _require_non_empty_str(data.get("code"), "code")
    summary = _require_non_empty_str(data.get("summary"), "summary")
    required_change = "" if data.get("required_change", "") is None else str(data.get("required_change", ""))
    return SleeveReason(
        source=source,
        code=code,
        summary=summary,
        required_change=required_change,
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
        "reasons": [sleeve_reason_to_dict(item) for item in state.reasons],
        "required_changes": list(state.required_changes),
        "effective_allocation": state.effective_allocation,
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
            reasons=_tuple_of_reasons(data.get("reasons", ()), "reasons"),
            required_changes=_tuple_of_strings(data.get("required_changes", ()), "required_changes"),
            effective_allocation=_require_float_like(data.get("effective_allocation", 0.0), "effective_allocation"),
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


def sleeve_allocation_policy_to_dict(policy: SleeveAllocationPolicy) -> dict:
    """Serialize SleeveAllocationPolicy to a plain dict."""
    return {
        "blocked_allocation_mode": policy.blocked_allocation_mode.value,
        "disabled_allocation_mode": policy.disabled_allocation_mode.value,
    }


def sleeve_allocation_policy_from_dict(data: dict) -> SleeveAllocationPolicy:
    """Deserialize SleeveAllocationPolicy from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve allocation policy payload must be a dict, got {type(data).__name__!r}"
        )
    return SleeveAllocationPolicy(
        blocked_allocation_mode=SleeveInactiveCapitalMode(
            _require_non_empty_str(
                data.get("blocked_allocation_mode", SleeveInactiveCapitalMode.CONSERVE.value), "blocked_allocation_mode"
            )
        ),
        disabled_allocation_mode=SleeveInactiveCapitalMode(
            _require_non_empty_str(
                data.get("disabled_allocation_mode", SleeveInactiveCapitalMode.CONSERVE.value),
                "disabled_allocation_mode",
            )
        ),
    )


def sleeve_effective_allocation_summary_to_dict(summary: SleeveEffectiveAllocationSummary) -> dict:
    """Serialize SleeveEffectiveAllocationSummary to a plain dict."""
    return {
        "effective_allocated_share": summary.effective_allocated_share,
        "effective_unallocated_share": summary.effective_unallocated_share,
        "redistributed_blocked_share": summary.redistributed_blocked_share,
        "redistributed_disabled_share": summary.redistributed_disabled_share,
        "conserved_blocked_share": summary.conserved_blocked_share,
        "conserved_disabled_share": summary.conserved_disabled_share,
        "recipient_sleeve_ids": list(summary.recipient_sleeve_ids),
    }


def sleeve_effective_allocation_summary_from_dict(data: dict) -> SleeveEffectiveAllocationSummary:
    """Deserialize SleeveEffectiveAllocationSummary from a plain dict."""
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve effective allocation payload must be a dict, got {type(data).__name__!r}"
        )
    try:
        return SleeveEffectiveAllocationSummary(
            effective_allocated_share=_require_float_like(
                data.get("effective_allocated_share", 0.0), "effective_allocated_share"
            ),
            effective_unallocated_share=_require_float_like(
                data.get("effective_unallocated_share", 0.0), "effective_unallocated_share"
            ),
            redistributed_blocked_share=_require_float_like(
                data.get("redistributed_blocked_share", 0.0), "redistributed_blocked_share"
            ),
            redistributed_disabled_share=_require_float_like(
                data.get("redistributed_disabled_share", 0.0), "redistributed_disabled_share"
            ),
            conserved_blocked_share=_require_float_like(
                data.get("conserved_blocked_share", 0.0), "conserved_blocked_share"
            ),
            conserved_disabled_share=_require_float_like(
                data.get("conserved_disabled_share", 0.0), "conserved_disabled_share"
            ),
            recipient_sleeve_ids=_tuple_of_strings(data.get("recipient_sleeve_ids", ()), "recipient_sleeve_ids"),
        )
    except SleevePortfolioValidationError as exc:
        raise SleevePortfolioCorruptError(str(exc)) from exc


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
        "allocation_policy": sleeve_allocation_policy_to_dict(snapshot.allocation_policy),
        "effective_allocation": sleeve_effective_allocation_summary_to_dict(snapshot.effective_allocation),
        "enabled_sleeve_ids": list(snapshot.enabled_sleeve_ids),
        "blocked_sleeve_ids": list(snapshot.blocked_sleeve_ids),
        "allocated_sleeve_ids": list(snapshot.allocated_sleeve_ids),
        "blocked_reason_summaries": list(snapshot.blocked_reason_summaries),
        "summary": snapshot.summary,
        "readiness_level": snapshot.readiness_level,
        "readiness_is_supportive": snapshot.readiness_is_supportive,
        "escalation_allowed_next_step": snapshot.escalation_allowed_next_step,
        "external_regime_execution_blocked": snapshot.external_regime_execution_blocked,
        "workflow_status": snapshot.workflow_status,
        "comparison_to_previous": dict(snapshot.comparison_to_previous),
        "history_summary": dict(snapshot.history_summary),
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
        allocation_policy=(
            SleeveAllocationPolicy()
            if data.get("allocation_policy") is None
            else sleeve_allocation_policy_from_dict(dict(data.get("allocation_policy")))
        ),
        workflow_status=(
            "static" if data.get("workflow_status", "static") is None else str(data.get("workflow_status", "static"))
        ),
        comparison_to_previous=(
            {} if data.get("comparison_to_previous") is None else dict(data.get("comparison_to_previous"))
        ),
        history_summary={} if data.get("history_summary") is None else dict(data.get("history_summary")),
    )

    allocation_value = data.get("allocation")
    if allocation_value is not None:
        restored_allocation = sleeve_allocation_summary_from_dict(allocation_value)
        if restored_allocation != snapshot.allocation:
            raise SleevePortfolioCorruptError("Sleeve portfolio allocation summary does not match sleeve decomposition")

    effective_allocation_value = data.get("effective_allocation")
    if effective_allocation_value is not None:
        restored_effective = sleeve_effective_allocation_summary_from_dict(effective_allocation_value)
        if restored_effective != snapshot.effective_allocation:
            raise SleevePortfolioCorruptError("Sleeve effective allocation summary does not match policy recompute")

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
