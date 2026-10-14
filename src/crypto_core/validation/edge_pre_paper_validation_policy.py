"""Governed pre-paper validation policy (EDGE_PRE_PAPER_VALIDATION_POLICY_V1).

``EdgePrePaperValidationPolicy`` is the only source of every human-owned value the pre-paper validation evidence uses:
the PBO band thresholds and allocation cap fractions, the Monte Carlo significance level and trade floor, the
sensitivity retention floor, the Stage-3 stress multipliers, the flash-crash maintenance fraction and the pinned
governed trial-chain genesis. Every value is a first-class field committed by ``policy_values_digest``; nothing is
defaulted, no production value lives in code, and a value looser than the PRDV4 §1.13 Stage 3 / §1.20 requirement is
refused at construction (``value_looser_than_prdv4:<name>``):

* PBO bands (§1.20): ``a <= 0.20`` (normal), ``c <= 0.40`` (approved with a cap), ``e <= 0.60`` (above it: rejected;
  from ``c`` to ``e``: additional out-of-sample evidence required), ``0 < a <= c <= e < 1``; the capped band's
  allocation fraction is at most ``1/2``;
* LIMITED_S1_PAPER_V1 regime cap: the regime-conditional PBO is UNPROVEN, so the PRDV4 worst case applies to every
  regime and the regime allocation fraction is at most ``1/4``;
* Monte Carlo: ``p_max <= 0.05`` over exactly 10 000 samples (a method constant) and at least the PRDV4 Stage 1 floor of
  50 closed trades;
* sensitivity: the retention floor is at least ``0.5`` (PRDV4: a Sharpe drop of more than 50% within ±10% rejects);
* stress: high volatility ``slippage >= 2.0`` (the return multiplier is the method constant 1.5); low liquidity
  ``depth <= 0.2`` and ``slippage >= 3.0``; flash crash ``gap >= 10%`` and ``recovery >= 5 minutes``. PRDV4 names no
  flash-crash depth, slippage or maintenance value: they are governed inputs only (``0 < depth <= 1``,
  ``slippage >= 1``, ``0 < maintenance < 1``) and never venue liquidation facts.

Approval. ``EdgePrePaperValidationApproval`` commits to the exact values digest and the rule set. Only an exact
``HUMAN_GOVERNANCE`` approval makes the policy PASS; a missing, non-matching or ``TEST_ONLY_SYNTHETIC`` approval is
``NEEDS_GOVERNANCE_APPROVAL``. ``production_values_approved`` is structurally False: a policy is never a claim that its
values are calibrated to a venue.

``status`` is integrity only (READY); only READY + PASS advances. One assembly path serves the builder and verifier
reassembly; ``verify_edge_pre_paper_validation_policy`` is total. Deterministic and pure: no IO, clock, randomness,
network, float or decimal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionStressScenario,
    HistoricalExecutionStressScenarioKind,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_decimal_is_canonical

_SCHEMA_VERSION = "edge-pre-paper-validation-policy.v1"
_REASON_PREFIX = "edge_pre_paper_validation_policy"
_SELF_DIGEST_FIELD = "policy_digest"
_INT64_MAX = 9223372036854775807
_MAX_TEXT_LENGTH = 256
_MAX_TOKEN_LENGTH = 128

EDGE_PRE_PAPER_ADMISSION_SCOPE = "LIMITED_S1_PAPER_V1"
EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN = "UNPROVEN"
EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT = 10_000
EDGE_PRE_PAPER_CSCV_BLOCK_COUNT = 16
_ZERO = "0.000000000000000000"
_ONE = "1.000000000000000000"
_HIGH_VOLATILITY_RETURN_MULTIPLIER = "1.500000000000000000"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_pre_paper_validation_policy_rules.v1",
    "admission_scope": EDGE_PRE_PAPER_ADMISSION_SCOPE,
    "regime_conditional_pbo_status": EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN,
    "regime_cap_rule_id": "prdv4_regime_pbo_worst_case_cap_applied_to_every_regime_no_regime_label_consumed.v1",
    "prdv4_floor_rule_id": "every_value_at_least_as_strict_as_prdv4_1_13_stage_3_and_1_20_else_refused.v1",
    "approval_rule_id": "only_an_exact_human_governance_approval_of_the_values_digest_establishes_the_policy.v1",
    "cscv_block_count": EDGE_PRE_PAPER_CSCV_BLOCK_COUNT,
    "monte_carlo_sample_count": EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT,
    "prdv4_pbo_normal_max_exclusive": "0.200000000000000000",
    "prdv4_pbo_capped_max_exclusive": "0.400000000000000000",
    "prdv4_pbo_additional_oos_max_inclusive": "0.600000000000000000",
    "prdv4_pbo_capped_allocation_fraction_max": "0.500000000000000000",
    "limited_s1_regime_allocation_fraction_max": "0.250000000000000000",
    "prdv4_monte_carlo_p_value_max": "0.050000000000000000",
    "prdv4_min_closed_trade_count": 50,
    "prdv4_sensitivity_min_retention_ratio": "0.500000000000000000",
    "prdv4_high_volatility_return_multiplier": _HIGH_VOLATILITY_RETURN_MULTIPLIER,
    "prdv4_high_volatility_slippage_multiplier_min": "2.000000000000000000",
    "prdv4_low_liquidity_depth_multiplier_max": "0.200000000000000000",
    "prdv4_low_liquidity_slippage_multiplier_min": "3.000000000000000000",
    "prdv4_flash_crash_gap_fraction_min": "0.100000000000000000",
    "prdv4_flash_crash_recovery_ns_min": 300_000_000_000,
    "flash_crash_unspecified_by_prdv4": ["depth_multiplier", "slippage_multiplier", "maintenance_margin_fraction"],
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("production_values_approved", False),
    ("venue_liquidation_facts_proven", False),
    ("regime_conditional_pbo_proven", False),
    ("full_prdv4_compliance_claimed", False),
    ("edge_proven", False),
    ("live_ready", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS)

# (field, lower bound, lower inclusive, upper bound, upper inclusive) of every governed decimal; None is unbounded.
_DECIMAL_BOUNDS: tuple[tuple[str, Fraction | None, bool, Fraction | None, bool], ...] = (
    ("pbo_normal_max_exclusive", Fraction(0), False, Fraction(1, 5), True),
    ("pbo_capped_max_exclusive", Fraction(0), False, Fraction(2, 5), True),
    ("pbo_additional_oos_max_inclusive", Fraction(0), False, Fraction(3, 5), True),
    ("pbo_capped_allocation_fraction", Fraction(0), False, Fraction(1, 2), True),
    ("regime_allocation_fraction", Fraction(0), False, Fraction(1, 4), True),
    ("monte_carlo_p_value_max", Fraction(0), False, Fraction(1, 20), True),
    ("sensitivity_min_retention_ratio", Fraction(1, 2), True, Fraction(1), True),
    ("high_volatility_slippage_multiplier", Fraction(2), True, None, False),
    ("low_liquidity_depth_multiplier", Fraction(0), False, Fraction(1, 5), True),
    ("low_liquidity_slippage_multiplier", Fraction(3), True, None, False),
    ("flash_crash_gap_fraction", Fraction(1, 10), True, Fraction(1), False),
    ("flash_crash_depth_multiplier", Fraction(0), False, Fraction(1), True),
    ("flash_crash_slippage_multiplier", Fraction(1), True, None, False),
    ("flash_crash_maintenance_margin_fraction", Fraction(0), False, Fraction(1), False),
)
_MIN_CLOSED_TRADE_COUNT = 50
_MIN_FLASH_CRASH_RECOVERY_NS = 300_000_000_000


def edge_pre_paper_validation_policy_rule_set() -> dict[str, object]:
    """A fresh copy of the rule set committed by ``EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST``."""

    return {key: list(value) if isinstance(value, list) else value for key, value in _RULE_SET_V1.items()}


class EdgePrePaperValidationPolicyError(EdgeArtifactError):
    """Raised on malformed caller input, a value looser than PRDV4, or a forbidden scope token."""


class EdgePrePaperApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` exists for tests: it is recorded and never establishes the policy."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


@dataclass(frozen=True)
class EdgePrePaperValidationApproval:
    """Governance approval of one exact set of policy values under this rule set."""

    approval_reference: str
    approval_digest: str
    approval_kind: EdgePrePaperApprovalKind
    approved_policy_values_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class EdgePrePaperValidationPolicy:
    """Immutable, digest-bound governed pre-paper validation policy. Paper only; proves no edge or venue fact."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    rule_set_id: str
    rule_set_digest: str
    admission_scope: str
    regime_conditional_pbo_status: str
    pbo_normal_max_exclusive: str
    pbo_capped_max_exclusive: str
    pbo_additional_oos_max_inclusive: str
    pbo_capped_allocation_fraction: str
    regime_allocation_fraction: str
    monte_carlo_p_value_max: str
    monte_carlo_min_closed_trade_count: int
    sensitivity_min_retention_ratio: str
    high_volatility_slippage_multiplier: str
    low_liquidity_depth_multiplier: str
    low_liquidity_slippage_multiplier: str
    flash_crash_gap_fraction: str
    flash_crash_recovery_ns: int
    flash_crash_depth_multiplier: str
    flash_crash_slippage_multiplier: str
    flash_crash_maintenance_margin_fraction: str
    approved_trial_chain_genesis_digest: str
    policy_values_digest: str
    approval: EdgePrePaperValidationApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    policy_digest: str
    paper_only: bool = True
    production_values_approved: bool = False
    venue_liquidation_facts_proven: bool = False
    regime_conditional_pbo_proven: bool = False
    full_prdv4_compliance_claimed: bool = False
    edge_proven: bool = False
    live_ready: bool = False


# The values the approval commits to: everything but the verdict, approval and digests.
_VALUE_FIELDS = (
    "policy_id",
    "policy_version",
    "rule_set_id",
    "rule_set_digest",
    "admission_scope",
    "regime_conditional_pbo_status",
    *(name for name, *_ in _DECIMAL_BOUNDS),
    "monte_carlo_min_closed_trade_count",
    "flash_crash_recovery_ns",
    "approved_trial_chain_genesis_digest",
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgePrePaperValidationPolicyError:
    return EdgePrePaperValidationPolicyError(_reason(code))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT_LENGTH
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_token(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_TOKEN_LENGTH
        or not (value[0].isascii() and value[0].isalnum())
        or any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _bounded_decimal(
    value: object, name: str, low: Fraction | None, low_inclusive: bool, high: Fraction | None, high_inclusive: bool
) -> str:
    """A canonical scale-18 decimal inside its PRDV4 bound; a value outside it is refused, never clamped."""

    if not historical_execution_decimal_is_canonical(value):
        raise _fail(f"{name}_invalid")
    exact = Fraction(value)  # type: ignore[arg-type]
    if low is not None and (exact < low or (exact == low and not low_inclusive)):
        raise _fail(f"value_looser_than_prdv4:{name}")
    if high is not None and (exact > high or (exact == high and not high_inclusive)):
        raise _fail(f"value_looser_than_prdv4:{name}")
    return value  # type: ignore[return-value]


def _serialize(value: object) -> object:
    if type(value) is EdgePrePaperValidationApproval:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize a record; an enum-typed field must hold the exact enum member, never an equal plain string."""

    for name, enum_cls in _ENUM_FIELDS.get(type(artifact), ()):
        if type(getattr(artifact, name)) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgePrePaperValidationPolicy: (("status", EdgeEvidenceStatus), ("gate_verdict", EdgeGateVerdict)),
    EdgePrePaperValidationApproval: (("approval_kind", EdgePrePaperApprovalKind),),
}


def _canonical_approval(value: object) -> EdgePrePaperValidationApproval | None:
    if value is None:
        return None
    if type(value) is not EdgePrePaperValidationApproval:
        raise _fail("approval_malformed")
    kind = getattr(value, "approval_kind", None)
    if type(kind) is not EdgePrePaperApprovalKind:
        raise _fail("approval_kind_invalid")
    return EdgePrePaperValidationApproval(
        approval_reference=_require_text(getattr(value, "approval_reference", None), "approval_reference"),
        approval_digest=_require_hex64(getattr(value, "approval_digest", None), "approval_digest"),
        approval_kind=kind,
        approved_policy_values_digest=_require_hex64(
            getattr(value, "approved_policy_values_digest", None), "approved_policy_values_digest"
        ),
        approved_rule_set_digest=_require_hex64(
            getattr(value, "approved_rule_set_digest", None), "approved_rule_set_digest"
        ),
    )


# --- the policy --------------------------------------------------------------------------------------------------------


def _assemble_policy(values: Mapping[str, object], approval: object) -> EdgePrePaperValidationPolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    decimals = {
        name: _bounded_decimal(values.get(name), name, low, low_inclusive, high, high_inclusive)
        for name, low, low_inclusive, high, high_inclusive in _DECIMAL_BOUNDS
    }
    normal, capped, additional = (
        Fraction(decimals[name])
        for name in ("pbo_normal_max_exclusive", "pbo_capped_max_exclusive", "pbo_additional_oos_max_inclusive")
    )
    if not normal <= capped <= additional:
        raise _fail("pbo_band_thresholds_not_ordered")
    trades = values.get("monte_carlo_min_closed_trade_count")
    if type(trades) is not int or not 0 < trades <= _INT64_MAX:
        raise _fail("monte_carlo_min_closed_trade_count_invalid")
    if trades < _MIN_CLOSED_TRADE_COUNT:
        raise _fail("value_looser_than_prdv4:monte_carlo_min_closed_trade_count")
    recovery = values.get("flash_crash_recovery_ns")
    if type(recovery) is not int or not 0 < recovery <= _INT64_MAX:
        raise _fail("flash_crash_recovery_ns_invalid")
    if recovery < _MIN_FLASH_CRASH_RECOVERY_NS:
        raise _fail("value_looser_than_prdv4:flash_crash_recovery_ns")
    record = _canonical_approval(approval)
    value_payload: dict[str, object] = {
        "policy_id": _require_token(values.get("policy_id"), "policy_id"),
        "policy_version": _require_text(values.get("policy_version"), "policy_version"),
        "rule_set_id": _RULE_SET_ID,
        "rule_set_digest": EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST,
        "admission_scope": EDGE_PRE_PAPER_ADMISSION_SCOPE,
        "regime_conditional_pbo_status": EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN,
        **decimals,
        "monte_carlo_min_closed_trade_count": trades,
        "flash_crash_recovery_ns": recovery,
        "approved_trial_chain_genesis_digest": _require_hex64(
            values.get("approved_trial_chain_genesis_digest"), "approved_trial_chain_genesis_digest"
        ),
    }
    values_digest = edge_sha256_text(edge_canonical_json(value_payload))
    governance: list[str] = []
    if record is None:
        governance.append(_reason("policy_approval_missing"))
    else:
        if record.approval_kind is not EdgePrePaperApprovalKind.HUMAN_GOVERNANCE:
            governance.append(_reason("policy_approval_not_human_governance"))
        if record.approved_policy_values_digest != values_digest:
            governance.append(_reason("policy_approval_values_digest_mismatch"))
        if record.approved_rule_set_digest != EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST:
            governance.append(_reason("policy_approval_rule_set_digest_mismatch"))
    verdict = resolve_edge_gate_verdict([], [], governance)
    seed = EdgePrePaperValidationPolicy(
        schema_version=_SCHEMA_VERSION,
        status=EdgeEvidenceStatus.READY,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        **value_payload,  # type: ignore[arg-type]
        policy_values_digest=values_digest,
        approval=record,
        synthetic_test_approval_used=record is not None
        and record.approval_kind is EdgePrePaperApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=tuple(sorted(set(governance))),
        policy_digest="",
    )
    return replace(seed, policy_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_pre_paper_validation_policy(
    *,
    policy_id: str,
    policy_version: str,
    pbo_normal_max_exclusive: str,
    pbo_capped_max_exclusive: str,
    pbo_additional_oos_max_inclusive: str,
    pbo_capped_allocation_fraction: str,
    regime_allocation_fraction: str,
    monte_carlo_p_value_max: str,
    monte_carlo_min_closed_trade_count: int,
    sensitivity_min_retention_ratio: str,
    high_volatility_slippage_multiplier: str,
    low_liquidity_depth_multiplier: str,
    low_liquidity_slippage_multiplier: str,
    flash_crash_gap_fraction: str,
    flash_crash_recovery_ns: int,
    flash_crash_depth_multiplier: str,
    flash_crash_slippage_multiplier: str,
    flash_crash_maintenance_margin_fraction: str,
    approved_trial_chain_genesis_digest: str,
    approval: EdgePrePaperValidationApproval | None = None,
) -> EdgePrePaperValidationPolicy:
    """Build one governed policy. Every value is explicit; a value looser than PRDV4 or malformed raises."""

    values = {key: value for key, value in locals().items() if key != "approval"}
    return _assemble_policy(values, approval)


def edge_pre_paper_validation_policy_to_dict(policy: EdgePrePaperValidationPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def edge_pre_paper_validation_policy_digest(policy: EdgePrePaperValidationPolicy) -> str:
    """Recompute the canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


def edge_pre_paper_stress_scenarios(
    policy: EdgePrePaperValidationPolicy,
) -> tuple[HistoricalExecutionStressScenario, ...]:
    """The three governed Stage-3 scenarios of one policy, in the fixed order HIGH_VOL, LOW_LIQUIDITY, FLASH_CRASH."""

    kinds = HistoricalExecutionStressScenarioKind
    return (
        HistoricalExecutionStressScenario(
            scenario_kind=kinds.HIGH_VOLATILITY,
            return_multiplier=_HIGH_VOLATILITY_RETURN_MULTIPLIER,
            slippage_multiplier=policy.high_volatility_slippage_multiplier,
            depth_multiplier=_ONE,
            gap_fraction=_ZERO,
            recovery_ns=0,
            maintenance_margin_fraction=_ZERO,
        ),
        HistoricalExecutionStressScenario(
            scenario_kind=kinds.LOW_LIQUIDITY,
            return_multiplier=_ONE,
            slippage_multiplier=policy.low_liquidity_slippage_multiplier,
            depth_multiplier=policy.low_liquidity_depth_multiplier,
            gap_fraction=_ZERO,
            recovery_ns=0,
            maintenance_margin_fraction=_ZERO,
        ),
        HistoricalExecutionStressScenario(
            scenario_kind=kinds.FLASH_CRASH,
            return_multiplier=_ONE,
            slippage_multiplier=policy.flash_crash_slippage_multiplier,
            depth_multiplier=policy.flash_crash_depth_multiplier,
            gap_fraction=policy.flash_crash_gap_fraction,
            recovery_ns=policy.flash_crash_recovery_ns,
            maintenance_margin_fraction=policy.flash_crash_maintenance_margin_fraction,
        ),
    )


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "monte_carlo_min_closed_trade_count": _as_int,
    "flash_crash_recovery_ns": _as_int,
    "approval": lambda value: (
        None
        if value is None
        else _parse_exact(EdgePrePaperValidationApproval, value, {"approval_kind": _as_enum(EdgePrePaperApprovalKind)})
    ),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_pre_paper_validation_policy_from_payload(payload: object) -> EdgePrePaperValidationPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(EdgePrePaperValidationPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def edge_pre_paper_validation_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot consumed by the pre-paper evidence."""

    try:
        edge_pre_paper_validation_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> EdgePrePaperValidationPolicy:
    values = {name: getattr(policy, name) for name in _VALUE_FIELDS}
    return _assemble_policy(values, policy.approval)  # type: ignore[attr-defined]


def verify_edge_pre_paper_validation_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy by strict parse and reassembly from its own values and approval. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=EdgePrePaperValidationPolicy,
        to_payload=_to_payload,
        parse_payload=edge_pre_paper_validation_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_PRE_PAPER_ADMISSION_SCOPE",
    "EDGE_PRE_PAPER_CSCV_BLOCK_COUNT",
    "EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT",
    "EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS",
    "EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST",
    "EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN",
    "EdgePrePaperApprovalKind",
    "EdgePrePaperValidationApproval",
    "EdgePrePaperValidationPolicy",
    "EdgePrePaperValidationPolicyError",
    "build_edge_pre_paper_validation_policy",
    "edge_pre_paper_stress_scenarios",
    "edge_pre_paper_validation_policy_digest",
    "edge_pre_paper_validation_policy_from_payload",
    "edge_pre_paper_validation_policy_payload_is_well_formed",
    "edge_pre_paper_validation_policy_rule_set",
    "edge_pre_paper_validation_policy_to_dict",
    "verify_edge_pre_paper_validation_policy",
]
