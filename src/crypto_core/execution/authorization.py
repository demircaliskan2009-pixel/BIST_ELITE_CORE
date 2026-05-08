"""Inert live execution authorization contract.

This module defines auditable metadata for a future live-execution phase. It is
intentionally disconnected from lifecycle engines, adapters, sessions,
credentials, networking, allocation, and order submission.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LIVE_AUTH_SCHEMA_VERSION = 1
LIVE_AUTH_ALLOWED_ALLOCATION_TIERS_PCT = (10.0, 25.0, 50.0, 100.0)

LIVE_AUTH_VALIDATION_NOT_READY = "live_auth:validation_not_ready"
LIVE_AUTH_STAGE4_NOT_PASSED = "live_auth:stage4_not_passed"
LIVE_AUTH_STAGE4_HASH_MISSING = "live_auth:stage4_hash_missing"
LIVE_AUTH_STAGE5_NOT_PASSED = "live_auth:stage5_not_passed"
LIVE_AUTH_STAGE5_HASH_MISSING = "live_auth:stage5_hash_missing"
LIVE_AUTH_OPERATOR_APPROVAL_MISSING = "live_auth:operator_approval_missing"
LIVE_AUTH_CREDENTIAL_ATTESTATION_MISSING = "live_auth:credential_attestation_missing"
LIVE_AUTH_KILL_SWITCH_NOT_CLEAR = "live_auth:kill_switch_not_clear"
LIVE_AUTH_RISK_GOVERNANCE_NOT_CLEAR = "live_auth:risk_governance_not_clear"
LIVE_AUTH_NO_TRADE_GUARD_NOT_CLEAR = "live_auth:no_trade_guard_not_clear"
LIVE_AUTH_INVALID_ALLOCATION_TIER = "live_auth:invalid_allocation_tier"
LIVE_AUTH_INVALID_NOTIONAL_LIMITS = "live_auth:invalid_notional_limits"
LIVE_AUTH_VENUE_ALLOWLIST_MISSING = "live_auth:venue_allowlist_missing"
LIVE_AUTH_SYMBOL_ALLOWLIST_MISSING = "live_auth:symbol_allowlist_missing"
LIVE_AUTH_EXPIRED_OR_INVALID_WINDOW = "live_auth:expired_or_invalid_window"

_LIVE_AUTH_SCHEMA_VERSION_INVALID = "live_auth:schema_version_invalid"
_LIVE_AUTH_AUTHORIZATION_ID_MISSING = "live_auth:authorization_id_missing"
_LIVE_AUTH_SLEEVE_ID_MISSING = "live_auth:sleeve_id_missing"
_LIVE_AUTH_EDGE_ID_MISSING = "live_auth:edge_id_missing"
_LIVE_AUTH_AUDIT_ID_MISSING = "live_auth:audit_id_missing"
_LIVE_AUTH_REJECTION_REASONS_MALFORMED = "live_auth:rejection_reasons_malformed"


class LiveExecutionAuthorizationCorruptError(ValueError):
    """Raised when a live authorization payload is structurally malformed."""


@dataclass(frozen=True, kw_only=True)
class LiveExecutionAuthorization:
    """Future live-execution authorization metadata.

    This dataclass is inert. Possessing a passing authorization object does not
    enable live execution in the current system.
    """

    authorization_id: str
    schema_version: int = LIVE_AUTH_SCHEMA_VERSION
    sleeve_id: str
    edge_id: str
    as_of_ns: int
    expires_at_ns: int
    validation_ready: bool
    validation_result_hash: str | None
    stage4_comparison_hash: str | None
    stage4_passed: bool
    stage5_gate_hash: str | None
    stage5_passed: bool
    stage5_runtime_evidence_record_id: str | None
    operator_approval_reference: str | None
    credential_attestation_reference: str | None
    kill_switch_clear: bool
    risk_governance_clear: bool
    no_trade_guard_clear: bool
    allocation_tier_pct: float
    max_live_notional_usd: float
    max_order_notional_usd: float
    venue_allowlist: tuple[str, ...]
    symbol_allowlist: tuple[str, ...]
    margin_mode: str | None
    position_mode: str | None
    decision_pack_hash: str | None
    audit_id: str
    rejection_reasons: tuple[str, ...] = ()
    passed: bool = False


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _optional_non_empty_str(value: object) -> bool:
    return value is None or _is_non_empty_str(value)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _is_finite_positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0


def _valid_string_tuple(value: object) -> bool:
    return isinstance(value, tuple) and bool(value) and all(_is_non_empty_str(item) for item in value)


def _valid_rejection_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(_is_non_empty_str(item) for item in value)


def _coerce_string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return ()


def _tuple_from_payload(value: object, field_name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization field {field_name!r} must be a list or tuple")
    result = tuple(value)
    if (not allow_empty and not result) or any(not _is_non_empty_str(item) for item in result):
        raise LiveExecutionAuthorizationCorruptError(
            f"Live authorization field {field_name!r} must contain non-empty strings"
        )
    return result


def _require_key(data: dict, field_name: str) -> object:
    if field_name not in data:
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization missing required field {field_name!r}")
    return data[field_name]


def _require_non_empty_str(data: dict, field_name: str) -> str:
    value = _require_key(data, field_name)
    if not _is_non_empty_str(value):
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization field {field_name!r} must be a non-empty str")
    return value


def _require_optional_non_empty_str(data: dict, field_name: str) -> str | None:
    value = _require_key(data, field_name)
    if not _optional_non_empty_str(value):
        raise LiveExecutionAuthorizationCorruptError(
            f"Live authorization field {field_name!r} must be null or a non-empty str"
        )
    return value


def _require_bool(data: dict, field_name: str) -> bool:
    value = _require_key(data, field_name)
    if not isinstance(value, bool):
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization field {field_name!r} must be a bool")
    return value


def _require_int(data: dict, field_name: str) -> int:
    value = _require_key(data, field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization field {field_name!r} must be an int")
    return value


def _require_float(data: dict, field_name: str) -> float:
    value = _require_key(data, field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise LiveExecutionAuthorizationCorruptError(f"Live authorization field {field_name!r} must be finite numeric")
    return float(value)


def live_execution_authorization_rejection_reasons(auth: LiveExecutionAuthorization) -> tuple[str, ...]:
    """Recompute fail-closed live authorization rejection reasons."""

    reasons: list[str] = []
    if not isinstance(auth, LiveExecutionAuthorization):
        return ("live_auth:authorization_malformed",)

    if auth.schema_version != LIVE_AUTH_SCHEMA_VERSION:
        reasons.append(_LIVE_AUTH_SCHEMA_VERSION_INVALID)
    if not _is_non_empty_str(auth.authorization_id):
        reasons.append(_LIVE_AUTH_AUTHORIZATION_ID_MISSING)
    if not _is_non_empty_str(auth.sleeve_id):
        reasons.append(_LIVE_AUTH_SLEEVE_ID_MISSING)
    if not _is_non_empty_str(auth.edge_id):
        reasons.append(_LIVE_AUTH_EDGE_ID_MISSING)
    if not _is_non_empty_str(auth.audit_id):
        reasons.append(_LIVE_AUTH_AUDIT_ID_MISSING)
    if (
        not _is_positive_int(auth.as_of_ns)
        or not _is_positive_int(auth.expires_at_ns)
        or auth.expires_at_ns <= auth.as_of_ns
    ):
        reasons.append(LIVE_AUTH_EXPIRED_OR_INVALID_WINDOW)
    if auth.validation_ready is not True:
        reasons.append(LIVE_AUTH_VALIDATION_NOT_READY)
    if auth.stage4_passed is not True:
        reasons.append(LIVE_AUTH_STAGE4_NOT_PASSED)
    if not _is_non_empty_str(auth.stage4_comparison_hash):
        reasons.append(LIVE_AUTH_STAGE4_HASH_MISSING)
    if auth.stage5_passed is not True:
        reasons.append(LIVE_AUTH_STAGE5_NOT_PASSED)
    if not _is_non_empty_str(auth.stage5_gate_hash):
        reasons.append(LIVE_AUTH_STAGE5_HASH_MISSING)
    if not _is_non_empty_str(auth.operator_approval_reference):
        reasons.append(LIVE_AUTH_OPERATOR_APPROVAL_MISSING)
    if not _is_non_empty_str(auth.credential_attestation_reference):
        reasons.append(LIVE_AUTH_CREDENTIAL_ATTESTATION_MISSING)
    if auth.kill_switch_clear is not True:
        reasons.append(LIVE_AUTH_KILL_SWITCH_NOT_CLEAR)
    if auth.risk_governance_clear is not True:
        reasons.append(LIVE_AUTH_RISK_GOVERNANCE_NOT_CLEAR)
    if auth.no_trade_guard_clear is not True:
        reasons.append(LIVE_AUTH_NO_TRADE_GUARD_NOT_CLEAR)
    if (
        isinstance(auth.allocation_tier_pct, bool)
        or not isinstance(auth.allocation_tier_pct, (int, float))
        or not math.isfinite(float(auth.allocation_tier_pct))
        or float(auth.allocation_tier_pct) not in LIVE_AUTH_ALLOWED_ALLOCATION_TIERS_PCT
    ):
        reasons.append(LIVE_AUTH_INVALID_ALLOCATION_TIER)
    if (
        not _is_finite_positive_number(auth.max_live_notional_usd)
        or not _is_finite_positive_number(auth.max_order_notional_usd)
        or float(auth.max_order_notional_usd) > float(auth.max_live_notional_usd)
    ):
        reasons.append(LIVE_AUTH_INVALID_NOTIONAL_LIMITS)
    if not _valid_string_tuple(auth.venue_allowlist):
        reasons.append(LIVE_AUTH_VENUE_ALLOWLIST_MISSING)
    if not _valid_string_tuple(auth.symbol_allowlist):
        reasons.append(LIVE_AUTH_SYMBOL_ALLOWLIST_MISSING)
    if not _optional_non_empty_str(auth.validation_result_hash):
        reasons.append("live_auth:validation_result_hash_malformed")
    if not _optional_non_empty_str(auth.stage5_runtime_evidence_record_id):
        reasons.append("live_auth:stage5_runtime_evidence_record_id_malformed")
    if not _optional_non_empty_str(auth.margin_mode):
        reasons.append("live_auth:margin_mode_malformed")
    if not _optional_non_empty_str(auth.position_mode):
        reasons.append("live_auth:position_mode_malformed")
    if not _optional_non_empty_str(auth.decision_pack_hash):
        reasons.append("live_auth:decision_pack_hash_malformed")
    if not _valid_rejection_tuple(auth.rejection_reasons):
        reasons.append(_LIVE_AUTH_REJECTION_REASONS_MALFORMED)
    else:
        reasons.extend(auth.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def live_execution_authorization_ready(
    auth: LiveExecutionAuthorization | None,
    *,
    now_ns: int | None = None,
) -> bool:
    """Return True only when authorization metadata is present and clean."""

    if not isinstance(auth, LiveExecutionAuthorization):
        return False
    if auth.passed is not True:
        return False
    if live_execution_authorization_rejection_reasons(auth):
        return False
    if now_ns is not None and (
        not isinstance(now_ns, int) or isinstance(now_ns, bool) or now_ns <= 0 or now_ns > auth.expires_at_ns
    ):
        return False
    return True


def build_live_execution_authorization(
    *,
    authorization_id: str,
    sleeve_id: str,
    edge_id: str,
    as_of_ns: int,
    expires_at_ns: int,
    validation_ready: bool,
    validation_result_hash: str | None,
    stage4_comparison_hash: str | None,
    stage4_passed: bool,
    stage5_gate_hash: str | None,
    stage5_passed: bool,
    stage5_runtime_evidence_record_id: str | None,
    operator_approval_reference: str | None,
    credential_attestation_reference: str | None,
    kill_switch_clear: bool,
    risk_governance_clear: bool,
    no_trade_guard_clear: bool,
    allocation_tier_pct: float,
    max_live_notional_usd: float,
    max_order_notional_usd: float,
    venue_allowlist: tuple[str, ...],
    symbol_allowlist: tuple[str, ...],
    margin_mode: str | None,
    position_mode: str | None,
    decision_pack_hash: str | None,
    audit_id: str,
    rejection_reasons: tuple[str, ...] = (),
) -> LiveExecutionAuthorization:
    """Build inert live authorization metadata with deterministic blockers."""

    auth = LiveExecutionAuthorization(
        authorization_id=authorization_id,
        sleeve_id=sleeve_id,
        edge_id=edge_id,
        as_of_ns=as_of_ns,
        expires_at_ns=expires_at_ns,
        validation_ready=validation_ready,
        validation_result_hash=validation_result_hash,
        stage4_comparison_hash=stage4_comparison_hash,
        stage4_passed=stage4_passed,
        stage5_gate_hash=stage5_gate_hash,
        stage5_passed=stage5_passed,
        stage5_runtime_evidence_record_id=stage5_runtime_evidence_record_id,
        operator_approval_reference=operator_approval_reference,
        credential_attestation_reference=credential_attestation_reference,
        kill_switch_clear=kill_switch_clear,
        risk_governance_clear=risk_governance_clear,
        no_trade_guard_clear=no_trade_guard_clear,
        allocation_tier_pct=float(allocation_tier_pct) if isinstance(allocation_tier_pct, (int, float)) else 0.0,
        max_live_notional_usd=(
            float(max_live_notional_usd) if isinstance(max_live_notional_usd, (int, float)) else 0.0
        ),
        max_order_notional_usd=(
            float(max_order_notional_usd) if isinstance(max_order_notional_usd, (int, float)) else 0.0
        ),
        venue_allowlist=_coerce_string_tuple(venue_allowlist),
        symbol_allowlist=_coerce_string_tuple(symbol_allowlist),
        margin_mode=margin_mode,
        position_mode=position_mode,
        decision_pack_hash=decision_pack_hash,
        audit_id=audit_id,
        rejection_reasons=rejection_reasons,
        passed=False,
    )
    reasons = live_execution_authorization_rejection_reasons(auth)
    return LiveExecutionAuthorization(
        authorization_id=auth.authorization_id,
        sleeve_id=auth.sleeve_id,
        edge_id=auth.edge_id,
        as_of_ns=auth.as_of_ns,
        expires_at_ns=auth.expires_at_ns,
        validation_ready=auth.validation_ready,
        validation_result_hash=auth.validation_result_hash,
        stage4_comparison_hash=auth.stage4_comparison_hash,
        stage4_passed=auth.stage4_passed,
        stage5_gate_hash=auth.stage5_gate_hash,
        stage5_passed=auth.stage5_passed,
        stage5_runtime_evidence_record_id=auth.stage5_runtime_evidence_record_id,
        operator_approval_reference=auth.operator_approval_reference,
        credential_attestation_reference=auth.credential_attestation_reference,
        kill_switch_clear=auth.kill_switch_clear,
        risk_governance_clear=auth.risk_governance_clear,
        no_trade_guard_clear=auth.no_trade_guard_clear,
        allocation_tier_pct=auth.allocation_tier_pct,
        max_live_notional_usd=auth.max_live_notional_usd,
        max_order_notional_usd=auth.max_order_notional_usd,
        venue_allowlist=auth.venue_allowlist,
        symbol_allowlist=auth.symbol_allowlist,
        margin_mode=auth.margin_mode,
        position_mode=auth.position_mode,
        decision_pack_hash=auth.decision_pack_hash,
        audit_id=auth.audit_id,
        rejection_reasons=reasons,
        passed=not reasons,
    )


def live_execution_authorization_to_dict(auth: LiveExecutionAuthorization) -> dict[str, object]:
    """Serialize live authorization metadata to a JSON-safe dict."""

    return {
        "authorization_id": auth.authorization_id,
        "schema_version": auth.schema_version,
        "sleeve_id": auth.sleeve_id,
        "edge_id": auth.edge_id,
        "as_of_ns": auth.as_of_ns,
        "expires_at_ns": auth.expires_at_ns,
        "validation_ready": auth.validation_ready,
        "validation_result_hash": auth.validation_result_hash,
        "stage4_comparison_hash": auth.stage4_comparison_hash,
        "stage4_passed": auth.stage4_passed,
        "stage5_gate_hash": auth.stage5_gate_hash,
        "stage5_passed": auth.stage5_passed,
        "stage5_runtime_evidence_record_id": auth.stage5_runtime_evidence_record_id,
        "operator_approval_reference": auth.operator_approval_reference,
        "credential_attestation_reference": auth.credential_attestation_reference,
        "kill_switch_clear": auth.kill_switch_clear,
        "risk_governance_clear": auth.risk_governance_clear,
        "no_trade_guard_clear": auth.no_trade_guard_clear,
        "allocation_tier_pct": auth.allocation_tier_pct,
        "max_live_notional_usd": auth.max_live_notional_usd,
        "max_order_notional_usd": auth.max_order_notional_usd,
        "venue_allowlist": list(auth.venue_allowlist),
        "symbol_allowlist": list(auth.symbol_allowlist),
        "margin_mode": auth.margin_mode,
        "position_mode": auth.position_mode,
        "decision_pack_hash": auth.decision_pack_hash,
        "audit_id": auth.audit_id,
        "rejection_reasons": list(auth.rejection_reasons),
        "passed": auth.passed,
    }


def live_execution_authorization_from_dict(data: object) -> LiveExecutionAuthorization:
    """Deserialize inert live authorization metadata fail-closed."""

    if not isinstance(data, dict):
        raise LiveExecutionAuthorizationCorruptError(
            f"Live authorization payload must be a dict, got {type(data).__name__!r}"
        )
    schema_version = _require_int(data, "schema_version")
    if schema_version != LIVE_AUTH_SCHEMA_VERSION:
        raise LiveExecutionAuthorizationCorruptError("Live authorization schema_version must be 1")

    auth = LiveExecutionAuthorization(
        authorization_id=_require_non_empty_str(data, "authorization_id"),
        schema_version=schema_version,
        sleeve_id=_require_non_empty_str(data, "sleeve_id"),
        edge_id=_require_non_empty_str(data, "edge_id"),
        as_of_ns=_require_int(data, "as_of_ns"),
        expires_at_ns=_require_int(data, "expires_at_ns"),
        validation_ready=_require_bool(data, "validation_ready"),
        validation_result_hash=_require_optional_non_empty_str(data, "validation_result_hash"),
        stage4_comparison_hash=_require_optional_non_empty_str(data, "stage4_comparison_hash"),
        stage4_passed=_require_bool(data, "stage4_passed"),
        stage5_gate_hash=_require_optional_non_empty_str(data, "stage5_gate_hash"),
        stage5_passed=_require_bool(data, "stage5_passed"),
        stage5_runtime_evidence_record_id=_require_optional_non_empty_str(data, "stage5_runtime_evidence_record_id"),
        operator_approval_reference=_require_optional_non_empty_str(data, "operator_approval_reference"),
        credential_attestation_reference=_require_optional_non_empty_str(data, "credential_attestation_reference"),
        kill_switch_clear=_require_bool(data, "kill_switch_clear"),
        risk_governance_clear=_require_bool(data, "risk_governance_clear"),
        no_trade_guard_clear=_require_bool(data, "no_trade_guard_clear"),
        allocation_tier_pct=_require_float(data, "allocation_tier_pct"),
        max_live_notional_usd=_require_float(data, "max_live_notional_usd"),
        max_order_notional_usd=_require_float(data, "max_order_notional_usd"),
        venue_allowlist=_tuple_from_payload(_require_key(data, "venue_allowlist"), "venue_allowlist"),
        symbol_allowlist=_tuple_from_payload(_require_key(data, "symbol_allowlist"), "symbol_allowlist"),
        margin_mode=_require_optional_non_empty_str(data, "margin_mode"),
        position_mode=_require_optional_non_empty_str(data, "position_mode"),
        decision_pack_hash=_require_optional_non_empty_str(data, "decision_pack_hash"),
        audit_id=_require_non_empty_str(data, "audit_id"),
        rejection_reasons=_tuple_from_payload(
            _require_key(data, "rejection_reasons"), "rejection_reasons", allow_empty=True
        ),
        passed=_require_bool(data, "passed"),
    )
    reasons = live_execution_authorization_rejection_reasons(auth)
    if auth.passed is True and reasons:
        raise LiveExecutionAuthorizationCorruptError(
            "Live authorization payload claims passed=True but evidence recomputes blockers"
        )
    return LiveExecutionAuthorization(
        authorization_id=auth.authorization_id,
        schema_version=auth.schema_version,
        sleeve_id=auth.sleeve_id,
        edge_id=auth.edge_id,
        as_of_ns=auth.as_of_ns,
        expires_at_ns=auth.expires_at_ns,
        validation_ready=auth.validation_ready,
        validation_result_hash=auth.validation_result_hash,
        stage4_comparison_hash=auth.stage4_comparison_hash,
        stage4_passed=auth.stage4_passed,
        stage5_gate_hash=auth.stage5_gate_hash,
        stage5_passed=auth.stage5_passed,
        stage5_runtime_evidence_record_id=auth.stage5_runtime_evidence_record_id,
        operator_approval_reference=auth.operator_approval_reference,
        credential_attestation_reference=auth.credential_attestation_reference,
        kill_switch_clear=auth.kill_switch_clear,
        risk_governance_clear=auth.risk_governance_clear,
        no_trade_guard_clear=auth.no_trade_guard_clear,
        allocation_tier_pct=auth.allocation_tier_pct,
        max_live_notional_usd=auth.max_live_notional_usd,
        max_order_notional_usd=auth.max_order_notional_usd,
        venue_allowlist=auth.venue_allowlist,
        symbol_allowlist=auth.symbol_allowlist,
        margin_mode=auth.margin_mode,
        position_mode=auth.position_mode,
        decision_pack_hash=auth.decision_pack_hash,
        audit_id=auth.audit_id,
        rejection_reasons=reasons,
        passed=auth.passed is True and not reasons,
    )


__all__ = [
    "LIVE_AUTH_SCHEMA_VERSION",
    "LiveExecutionAuthorization",
    "LiveExecutionAuthorizationCorruptError",
    "build_live_execution_authorization",
    "live_execution_authorization_from_dict",
    "live_execution_authorization_ready",
    "live_execution_authorization_rejection_reasons",
    "live_execution_authorization_to_dict",
]
