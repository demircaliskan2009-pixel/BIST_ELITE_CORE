"""Governed paper portfolio performance-path policy (RG4_PORTFOLIO_PERFORMANCE_PATH_POLICY_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-4 prerequisite). A
``PaperPortfolioPerformancePathPolicy`` is the human-owned policy that defines the ONE synthetic paper-performance path
over which RG-4 measures portfolio drawdown. It is POLICY EVIDENCE ONLY. It is never an allocation, a risk-budget
allocation, capital, account equity, margin, a balance, deployable capital or execution permission.

Governed values are caller-supplied GOVERNANCE inputs. Nothing is defaulted, and this module holds no production value:

* the bound RG-2 envelope: the policy is built against one verified ``PaperPortfolioRiskEnvelope`` and commits its
  ``envelope_digest``;
* ``performance_weights``: exactly one dimensionless synthetic ``performance_weight`` for every sleeve the envelope
  declares. No sleeve is missing and none is added; ids are unique exactly and case-insensitively and canonically
  sorted. Every weight is strictly positive and the weights sum to exactly one.

A performance weight is an aggregation weight of the synthetic performance path only. It is never derived from, or
read as, the RG-2 total budget, a sleeve or market cap, a sleeve's ``paper_performance_reference_notional``, account
value, capital or an RG-7 allocation.

The code-defined rule set (``PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST``) commits the path:

* the portfolio index is the fixed-weight convex combination ``P_t = sum_i(w_i * I_i,t)`` of the sleeves' exact
  normalized paper-performance indices. Every accepted sleeve index starts at exactly one, so ``P_0 = 1``;
* ``NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1``: the weights are fixed initial synthetic index weights for the whole
  evidence window. Nothing drifts or rebalances, and no transaction economics are inferred;
* every covered sleeve must supply re-proven performance evidence on the exact same ordered UTC-day grid. A covered
  sleeve without computable evidence makes the path not computable. A sleeve or a day is never dropped, interpolated
  or carried forward, and no future observation is used.

``policy_digest`` commits every governed value, the structural non-claims and the rule set. A
``PaperPortfolioPerformancePathApproval`` must commit the exact policy id, version, ``policy_digest`` and rule-set
digest:

* a missing, mismatched or stale approval leaves the policy ``NEEDS_GOVERNANCE_APPROVAL``;
* a ``TEST_ONLY_SYNTHETIC`` approval is surfaced through ``synthetic_test_approval_used`` and never advances;
* only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.

``approval_reference`` and ``approval_digest`` identify the external governance record and are carried, not re-proven:
this module cannot prove who approved the policy.

Malformed, missing, out-of-domain, uncovered or inconsistent governed input raises
``PaperPortfolioPerformancePathPolicyError``. One assembly path serves the builder and the verifier reassembly, and
``verify_paper_portfolio_performance_path_policy`` is total. The verifier re-proves the policy itself; whether its
weights still cover an envelope is re-checked by every consumer against the envelope it re-pins. Numeric discipline:
canonical fixed scale-18 ASCII decimal text (at most 60 characters), int64 bounds, exact ``Fraction`` arithmetic, no
float and no ``decimal`` context. Deterministic and pure: no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import cast

from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
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
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    verify_paper_portfolio_risk_envelope,
)

_SCHEMA_VERSION = "paper-portfolio-performance-path-policy.v1"
_REASON_PREFIX = "paper_portfolio_performance_path_policy"
_SELF_DIGEST_FIELD = "performance_path_policy_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")


class PaperPortfolioPerformancePathPolicyError(EdgeArtifactError):
    """Raised on malformed, missing, out-of-domain or uncovered governed input, or a malformed approval."""


class PaperPortfolioPerformancePathApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` approvals exist for tests only: they are surfaced and never advance a policy."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_portfolio_performance_path_rules.v1",
    "scope_rule_id": "paper_only_synthetic_performance_path_never_allocation_capital_equity_margin_or_balance.v1",
    "weight_unit_id": "dimensionless_synthetic_performance_weight_never_capital_budget_cap_or_reference_notional.v1",
    "weight_rule_id": "one_strictly_positive_weight_per_envelope_declared_sleeve_summing_to_exactly_one.v1",
    "coverage_rule_id": "weight_sleeve_set_equals_the_bound_envelope_sleeve_cap_set_exactly.v1",
    "envelope_binding_rule_id": "policy_binds_one_verified_envelope_by_its_envelope_digest.v1",
    "identifier_rule_id": "ascii_token_sleeve_ids_unique_exactly_and_case_insensitively_canonically_sorted.v1",
    "index_rule_id": "portfolio_index_is_the_fixed_weight_convex_combination_of_exact_sleeve_normalized_indices.v1",
    "initial_index_rule_id": "every_sleeve_index_and_the_portfolio_index_start_at_exactly_one.v1",
    "rebalancing_convention": "NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1",
    "alignment_rule_id": "every_covered_sleeve_on_the_exact_same_ordered_utc_day_grid.v1",
    "completeness_rule_id": "a_covered_sleeve_without_computable_evidence_makes_the_path_not_computable.v1",
    "observation_rule_id": "no_dropped_sleeve_or_day_no_interpolation_no_carry_forward_no_future_observation.v1",
    "governance_rule_id": "approval_commits_policy_id_version_policy_digest_and_rule_set_digest.v1",
    "gate_rule_id": "pass_iff_exact_matching_human_governance_approval_test_only_synthetic_never_advances.v1",
    "numeric_rule_id": "canonical_fixed_scale_decimal_text_exact_fraction_arithmetic_no_float_no_decimal_context.v1",
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_sleeve_id_length": 128,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_REBALANCING_CONVENTION = str(_RULE_SET_V1["rebalancing_convention"])
PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_SLEEVE_ID: int = _RULE_SET_V1["max_sleeve_id_length"]  # type: ignore[assignment]


def paper_portfolio_performance_path_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("portfolio_allocation_approved", False),
    ("risk_budget_used_as_weight", False),
    ("reference_notional_used_as_weight", False),
    ("execution_authorized", False),
    ("prdv4_stage4_complete", False),
)
_FLAG_NAMES = frozenset(name for name, _ in PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS)


@dataclass(frozen=True)
class PaperPortfolioPerformanceWeight:
    """One governed synthetic performance weight of one envelope-declared sleeve. Never an allocation or capital."""

    sleeve_id: str
    performance_weight: str


@dataclass(frozen=True)
class PaperPortfolioPerformancePathApproval:
    """Governance approval of one exact policy: every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: PaperPortfolioPerformancePathApprovalKind
    approved_policy_id: str
    approved_policy_version: str
    approved_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class PaperPortfolioPerformancePathPolicy:
    """Immutable, digest-bound portfolio performance-path policy. POLICY EVIDENCE ONLY; never allocation or capital."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    envelope_digest: str
    performance_weights: tuple[PaperPortfolioPerformanceWeight, ...]
    rebalancing_convention: str
    rule_set_id: str
    rule_set_digest: str
    policy_digest: str
    approval: PaperPortfolioPerformancePathApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    performance_path_policy_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
    performance_data_consumed: bool = False
    oos_evidence_consumed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    account_equity_represented: bool = False
    capital_represented: bool = False
    portfolio_allocation_approved: bool = False
    risk_budget_used_as_weight: bool = False
    reference_notional_used_as_weight: bool = False
    execution_authorized: bool = False
    prdv4_stage4_complete: bool = False


# Everything outside the governed policy: the approval, the verdict it yields, and the two digests themselves.
_NON_POLICY_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "performance_path_policy_digest",
    }
)
_RECORD_TYPES = frozenset({PaperPortfolioPerformanceWeight, PaperPortfolioPerformancePathApproval})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperPortfolioPerformancePathApproval: {"approval_kind": PaperPortfolioPerformancePathApprovalKind},
    PaperPortfolioPerformancePathPolicy: {"gate_verdict": EdgeGateVerdict},
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperPortfolioPerformancePathPolicyError:
    return PaperPortfolioPerformancePathPolicyError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _decimal_is_canonical(value: object) -> bool:
    """Canonical ASCII fixed-scale decimal text within the rule set's representation-safety length."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        return False
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _SCALE:
        return False
    if not _ascii_digits(integer) or not _ascii_digits(fraction):
        return False
    if integer != "0" and integer.startswith("0"):
        return False
    if negative and integer == "0" and fraction.strip("0") == "":
        return False
    return True


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_identifier(value: object, field_name: str, *, max_length: int) -> str:
    if type(value) is not str or value == "" or len(value) > max_length or not value.isascii():
        raise _fail(f"{field_name}_invalid")
    if not value[0].isalnum() or any(not (char.isalnum() or char in _IDENTIFIER_EXTRA_CHARS) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise _fail(f"{field_name}_invalid")


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


# --- governed weights -----------------------------------------------------------------------------------------------


def _require_weight(value: object) -> tuple[str, Fraction]:
    if not _decimal_is_canonical(value):
        raise _fail("performance_weight_invalid")
    text = cast(str, value)
    number = Fraction(text)
    if number <= 0:
        raise _fail("performance_weight_not_positive")
    return text, number


def _canonical_weights(values: object) -> tuple[PaperPortfolioPerformanceWeight, ...]:
    """Non-empty exact records, unique exact and case-insensitive sleeve ids, sorted, strictly positive, sum one."""

    items = _snapshot(values, "performance_weights")
    if not items:
        raise _fail("performance_weights_missing")
    by_sleeve: dict[str, PaperPortfolioPerformanceWeight] = {}
    folded: set[str] = set()
    total = Fraction(0)
    for item in items:
        if type(item) is not PaperPortfolioPerformanceWeight:
            raise _fail("performance_weight_malformed")
        sleeve_id = _require_identifier(getattr(item, "sleeve_id", None), "sleeve_id", max_length=_MAX_SLEEVE_ID)
        weight, value = _require_weight(getattr(item, "performance_weight", None))
        if sleeve_id in by_sleeve:
            raise _fail("performance_weight_sleeve_duplicate")
        if sleeve_id.lower() in folded:
            raise _fail("performance_weight_sleeve_case_ambiguous")
        folded.add(sleeve_id.lower())
        total += value
        by_sleeve[sleeve_id] = PaperPortfolioPerformanceWeight(sleeve_id=sleeve_id, performance_weight=weight)
    if total != 1:
        raise _fail("performance_weights_sum_not_one")
    return tuple(by_sleeve[sleeve_id] for sleeve_id in sorted(by_sleeve))


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    if type(value) is not PaperPortfolioRiskEnvelope:
        raise _fail("portfolio_risk_envelope_malformed")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    return value


# --- governance approval --------------------------------------------------------------------------------------------


def _canonical_approval(approval: object) -> PaperPortfolioPerformancePathApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not PaperPortfolioPerformancePathApproval:
        raise _fail("governance_approval_malformed")

    def attribute(name: str) -> object:
        return getattr(approval, name, None)

    return PaperPortfolioPerformancePathApproval(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            attribute("approval_kind"), PaperPortfolioPerformancePathApprovalKind, "governance_approval_kind"
        ),
        approved_policy_id=_require_text(attribute("approved_policy_id"), "governance_approved_policy_id"),
        approved_policy_version=_require_text(
            attribute("approved_policy_version"), "governance_approved_policy_version"
        ),
        approved_policy_digest=_require_hex64(attribute("approved_policy_digest"), "governance_approved_policy_digest"),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "governance_approved_rule_set_digest"
        ),
    )


def _governance_reasons(
    approval: PaperPortfolioPerformancePathApproval | None, committed: Mapping[str, str]
) -> list[str]:
    if approval is None:
        return [_reason("governance_approval_missing")]
    reasons = [
        _reason(f"governance_approval_{name}_mismatch")
        for name, value in committed.items()
        if getattr(approval, f"approved_{name}") != value
    ]
    if approval.approval_kind is PaperPortfolioPerformancePathApprovalKind.TEST_ONLY_SYNTHETIC:
        reasons.append(_reason("governance_approval_test_only_synthetic"))
    return reasons


# --- serialization --------------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in value]
    if type(value) is int:
        if value < 0 or value > _MAX_WIRE_INT:
            raise _fail("payload_integer_out_of_range")
        return value
    if value is None or type(value) in (str, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize exactly: an enum field must hold the exact member and every other value an exact builtin or record."""

    enum_fields = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for field in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, field.name)
        enum_cls = enum_fields.get(field.name)
        if enum_cls is None:
            payload[field.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[field.name] = value.value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


def _policy_digest(payload: Mapping[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS})
    )


# --- policy assembly ------------------------------------------------------------------------------------------------


def _assemble_policy(
    *,
    policy_id: object,
    policy_version: object,
    envelope_digest: object,
    performance_weights: object,
    approval: object,
) -> PaperPortfolioPerformancePathPolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    policy_id = _require_text(policy_id, "policy_id")
    policy_version = _require_text(policy_version, "policy_version")
    envelope_digest = _require_hex64(envelope_digest, "envelope_digest")
    weights = _canonical_weights(performance_weights)
    approval_record = _canonical_approval(approval)

    seed = PaperPortfolioPerformancePathPolicy(
        schema_version=_SCHEMA_VERSION,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        policy_id=policy_id,
        policy_version=policy_version,
        envelope_digest=envelope_digest,
        performance_weights=weights,
        rebalancing_convention=_REBALANCING_CONVENTION,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
        policy_digest="",
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is PaperPortfolioPerformancePathApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        performance_path_policy_digest="",
    )
    policy_digest = _policy_digest(_to_payload(seed))
    committed = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "rule_set_digest": PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
    }
    needs_governance = _governance_reasons(approval_record, committed)
    verdict = resolve_edge_gate_verdict([], [], needs_governance)
    governed = replace(
        seed,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(needs_governance),
    )
    return replace(
        governed, performance_path_policy_digest=edge_payload_digest(_to_payload(governed), _SELF_DIGEST_FIELD)
    )


def build_paper_portfolio_performance_path_policy(
    *,
    policy_id: str,
    policy_version: str,
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope,
    performance_weights: Sequence[PaperPortfolioPerformanceWeight],
    approval: PaperPortfolioPerformancePathApproval | None,
) -> PaperPortfolioPerformancePathPolicy:
    """Build the governed performance-path policy against one verified envelope; nothing is defaulted.

    The envelope is re-proven through its total verifier, and the weights must cover exactly its declared sleeves.
    Malformed, missing, out-of-domain or uncovered input, or a malformed approval, raises
    ``PaperPortfolioPerformancePathPolicyError``. A missing, non-matching or ``TEST_ONLY_SYNTHETIC`` approval yields
    ``NEEDS_GOVERNANCE_APPROVAL``; only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.
    """

    envelope = _require_envelope(portfolio_risk_envelope)
    weights = _canonical_weights(performance_weights)
    weighted = {weight.sleeve_id for weight in weights}
    declared = {cap.sleeve_id for cap in envelope.sleeve_caps}
    if declared - weighted:
        raise _fail("performance_weight_sleeve_missing")
    if weighted - declared:
        raise _fail("performance_weight_sleeve_not_declared")
    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        envelope_digest=envelope.envelope_digest,
        performance_weights=weights,
        approval=approval,
    )


def paper_portfolio_performance_path_policy_to_dict(policy: PaperPortfolioPerformancePathPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def paper_portfolio_performance_path_policy_digest(policy: PaperPortfolioPerformancePathPolicy) -> str:
    """Recompute the canonical policy artifact digest, excluding only ``performance_path_policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


# --- strict parsing -------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_decimal(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


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
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_optional(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, item, converters) for item in value)

    return convert


_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(PaperPortfolioPerformancePathApprovalKind),
}
_WEIGHT_CONVERTERS: dict[str, Callable[[object], object]] = {"performance_weight": _as_decimal}
_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "performance_weights": _as_records(PaperPortfolioPerformanceWeight, _WEIGHT_CONVERTERS),
    "approval": _as_optional(PaperPortfolioPerformancePathApproval, _APPROVAL_CONVERTERS),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def paper_portfolio_performance_path_policy_from_payload(payload: object) -> PaperPortfolioPerformancePathPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(PaperPortfolioPerformancePathPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def paper_portfolio_performance_path_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        paper_portfolio_performance_path_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> PaperPortfolioPerformancePathPolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        envelope_digest=policy.envelope_digest,  # type: ignore[attr-defined]
        performance_weights=policy.performance_weights,  # type: ignore[attr-defined]
        approval=policy.approval,  # type: ignore[attr-defined]
    )


def verify_paper_portfolio_performance_path_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=PaperPortfolioPerformancePathPolicy,
        to_payload=_to_payload,
        parse_payload=paper_portfolio_performance_path_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS",
    "PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST",
    "PaperPortfolioPerformancePathApproval",
    "PaperPortfolioPerformancePathApprovalKind",
    "PaperPortfolioPerformancePathPolicy",
    "PaperPortfolioPerformancePathPolicyError",
    "PaperPortfolioPerformanceWeight",
    "build_paper_portfolio_performance_path_policy",
    "paper_portfolio_performance_path_policy_digest",
    "paper_portfolio_performance_path_policy_from_payload",
    "paper_portfolio_performance_path_policy_payload_is_well_formed",
    "paper_portfolio_performance_path_policy_to_dict",
    "paper_portfolio_performance_path_rule_set",
    "verify_paper_portfolio_performance_path_policy",
]
