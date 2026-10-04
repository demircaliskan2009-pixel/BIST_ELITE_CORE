"""Governed paper sleeve equity-basis and valuation policy (PAPER_SLEEVE_EQUITY_BASIS_AND_VALUATION_POLICY_V1).

A ``PaperSleeveEquityBasisPolicy`` is the human-owned policy under which one sleeve's paper performance is valued. It
is POLICY EVIDENCE ONLY. The performance basis it governs is a normalized SYNTHETIC paper-performance index: never
real account equity, capital, margin, a balance, deployable capital, an RG-2 risk budget or allocation authority.

Governed values are caller-supplied GOVERNANCE inputs. Nothing is defaulted, and this module holds no production value:

* ``sleeve_id`` and ``market_symbol``: the one sleeve and the one market whose paper episodes the policy values. V1
  values exactly one market per sleeve, because the accepted daily-return substrate carries exactly one market.
* ``paper_performance_reference_notional``: a strictly positive performance normalization unit, expressed in the
  paper fill-notional units of that market. It is the index denominator only, never account value, capital, a
  balance or an RG-2 budget.
* ``funding_treatment``: ``FUNDING_EVIDENCE_REQUIRED`` (digest-bound funding evidence must cover the valuation
  window, so a missing funding evidence blocks valuation and is never an implicit zero) or
  ``GOVERNED_NOT_APPLICABLE`` (a governed statement that no funding applies, never caller prose).

The code-defined rule set (``PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST``) commits every valuation rule and numeric
bound the sleeve valuation reads. The rules cover:

* the equity form: reference notional + proven gross realized + close MTM unrealized - proven fees + proven funding;
* fee, realized, mark, time and funding provenance;
* the exact bucket-end mark rule, so no mark-age tolerance exists;
* return rendering and the chain-linked index;
* single-market scope and the flat genesis.

``policy_digest`` commits every governed value, the structural non-claims and the rule set. A
``PaperSleeveEquityBasisApproval`` must commit the exact policy id, version, ``policy_digest`` and rule-set digest:

* a missing, mismatched or stale approval leaves the policy ``NEEDS_GOVERNANCE_APPROVAL``;
* a ``TEST_ONLY_SYNTHETIC`` approval is surfaced through ``synthetic_test_approval_used`` and never advances;
* only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.

``approval_reference`` and ``approval_digest`` identify the external governance record and are carried, not re-proven:
this module cannot prove who approved the policy.

``paper_sleeve_equity_basis_methodology_policy_ids`` derives the policy identifiers that a
``PaperReturnSeriesMethodology`` must declare to be bound to this exact policy.

Malformed, missing or out-of-domain governed input raises ``PaperSleeveEquityBasisPolicyError``. One assembly path
serves the builder and the verifier reassembly, and ``verify_paper_sleeve_equity_basis_policy`` is total. Numeric
discipline: canonical fixed scale-18 ASCII decimal text (at most 60 characters), int64 bounds, exact ``Fraction``
comparison, no float and no ``decimal`` context. Deterministic and pure: no IO, clock, randomness, network or
environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction

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

_SCHEMA_VERSION = "paper-sleeve-equity-basis-policy.v1"
_REASON_PREFIX = "paper_sleeve_equity_basis_policy"
_SELF_DIGEST_FIELD = "equity_basis_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")
_METHODOLOGY_POLICY_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("mtm_policy_id", "mtm"),
    ("fee_policy_id", "fee"),
    ("funding_policy_id", "funding"),
    ("mark_policy_id", "mark"),
    ("exposure_policy_id", "exposure"),
    ("liquidation_policy_id", "liquidation"),
)


class PaperSleeveEquityBasisPolicyError(EdgeArtifactError):
    """Raised on malformed, missing or out-of-domain governed input, a malformed approval, or a scope token."""


class PaperSleeveFundingTreatment(str, Enum):
    """How paper funding enters the sleeve performance basis. Never an implicit zero."""

    FUNDING_EVIDENCE_REQUIRED = "FUNDING_EVIDENCE_REQUIRED"
    GOVERNED_NOT_APPLICABLE = "GOVERNED_NOT_APPLICABLE"


class PaperSleeveEquityBasisApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` approvals exist for tests only: they are surfaced and never advance a policy."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_equity_basis_rules.v1",
    "scope_rule_id": "paper_only_synthetic_performance_normalization_never_account_value_capital_or_allocation.v1",
    "performance_basis_id": "normalized_synthetic_paper_performance_index.v1",
    "reference_notional_rule_id": "governed_strictly_positive_normalization_unit_never_account_value_or_risk_budget.v1",
    "reference_notional_unit_id": "paper_fill_notional_units_of_the_single_valuation_market.v1",
    "equity_form_id": "reference_notional_plus_realized_plus_close_unrealized_minus_fees_plus_funding.v1",
    "realized_rule_id": "gross_realized_amount_of_reconstructed_episode_events_with_fill_before_close.v1",
    "fee_rule_id": "fee_amount_of_reconstructed_episode_fill_results_with_fill_before_close.v1",
    "funding_rule_id": "digest_bound_funding_evidence_or_governed_not_applicable_never_implicit_zero.v1",
    "funding_time_rule_id": "settlement_applies_to_position_after_fills_strictly_before_settlement.v1",
    "mark_rule_id": "exact_bucket_end_mark_snapshot_bound_into_reconstructed_close_pnl_report.v1",
    "mtm_rule_id": "close_position_after_fills_strictly_before_bucket_end_valued_by_public_pnl_report.v1",
    "exposure_rule_id": "no_exposure_normalization_reference_notional_only.v1",
    "liquidation_rule_id": "no_liquidation_model_paper_only.v1",
    "time_rule_id": "fill_market_snapshot_observed_at_ns_start_inclusive_end_exclusive_utc_day.v1",
    "sleeve_authority_rule_id": "sleeve_copied_only_from_capacity_decision_reconstructed_from_draft_and_policy.v1",
    "episode_rule_id": "every_episode_hop_reconstructed_by_its_public_builder_and_compared_canonically.v1",
    "genesis_rule_id": "flat_genesis_contiguous_position_chain_all_economics_inside_window.v1",
    "market_scope_rule_id": "single_market_per_sleeve_valuation.v1",
    "return_rule_id": "exact_equity_ratio_minus_one_rendered_once_scale_18_round_half_even.v1",
    "index_rule_id": "chain_linked_product_of_rendered_daily_returns_starting_at_one.v1",
    "blocking_rule_id": (
        "ungoverned_policy_missing_evidence_non_positive_basis_or_growth_or_index_over_bound_is_not_computable.v1"
    ),
    "governance_rule_id": "approval_commits_policy_id_version_policy_digest_and_rule_set_digest.v1",
    "gate_rule_id": "pass_iff_exact_matching_human_governance_approval_test_only_synthetic_never_advances.v1",
    "numeric_rule_id": "canonical_decimal_text_exact_fraction_arithmetic_no_float_no_decimal_context.v1",
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "consumed_decimal_max_text_length": 256,
    "normalized_index_max_text_length": 4000,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_sleeve_id_length": 128,
    "max_market_symbol_length": 64,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_SLEEVE_ID: int = _RULE_SET_V1["max_sleeve_id_length"]  # type: ignore[assignment]
_MAX_MARKET_SYMBOL: int = _RULE_SET_V1["max_market_symbol_length"]  # type: ignore[assignment]


def paper_sleeve_equity_basis_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("risk_budget_used_as_denominator", False),
    ("historical_economics_consumed", False),
    ("execution_authorized", False),
    ("portfolio_allocation_approved", False),
    ("prdv4_stage4_complete", False),
)
_FLAG_NAMES = frozenset(name for name, _ in PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS)


@dataclass(frozen=True)
class PaperSleeveEquityBasisApproval:
    """Governance approval of one exact policy: every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: PaperSleeveEquityBasisApprovalKind
    approved_policy_id: str
    approved_policy_version: str
    approved_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class PaperSleeveEquityBasisPolicy:
    """Immutable, digest-bound sleeve equity-basis policy. POLICY EVIDENCE ONLY; never account value or capital."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    sleeve_id: str
    market_symbol: str
    paper_performance_reference_notional: str
    funding_treatment: PaperSleeveFundingTreatment
    rule_set_id: str
    rule_set_digest: str
    policy_digest: str
    approval: PaperSleeveEquityBasisApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    equity_basis_digest: str
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
    risk_budget_used_as_denominator: bool = False
    historical_economics_consumed: bool = False
    execution_authorized: bool = False
    portfolio_allocation_approved: bool = False
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
        "equity_basis_digest",
    }
)
_RECORD_TYPES = frozenset({PaperSleeveEquityBasisApproval})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveEquityBasisApproval: {"approval_kind": PaperSleeveEquityBasisApprovalKind},
    PaperSleeveEquityBasisPolicy: {
        "gate_verdict": EdgeGateVerdict,
        "funding_treatment": PaperSleeveFundingTreatment,
    },
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveEquityBasisPolicyError:
    return PaperSleeveEquityBasisPolicyError(_reason(code))


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


def _wire_int_is_valid(value: object, *, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= _MAX_WIRE_INT


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


def _require_reference_notional(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("paper_performance_reference_notional_invalid")
    if Fraction(value) <= 0:  # type: ignore[arg-type]
        raise _fail("paper_performance_reference_notional_not_positive")
    return value  # type: ignore[return-value]


# --- governance approval --------------------------------------------------------------------------------------------


def _canonical_approval(approval: object) -> PaperSleeveEquityBasisApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not PaperSleeveEquityBasisApproval:
        raise _fail("governance_approval_malformed")

    def attribute(name: str) -> object:
        return getattr(approval, name, None)

    return PaperSleeveEquityBasisApproval(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            attribute("approval_kind"), PaperSleeveEquityBasisApprovalKind, "governance_approval_kind"
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


def _governance_reasons(approval: PaperSleeveEquityBasisApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("governance_approval_missing")]
    reasons = [
        _reason(f"governance_approval_{name}_mismatch")
        for name, value in committed.items()
        if getattr(approval, f"approved_{name}") != value
    ]
    if approval.approval_kind is PaperSleeveEquityBasisApprovalKind.TEST_ONLY_SYNTHETIC:
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
    sleeve_id: object,
    market_symbol: object,
    paper_performance_reference_notional: object,
    funding_treatment: object,
    approval: object,
) -> PaperSleeveEquityBasisPolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    policy_id = _require_text(policy_id, "policy_id")
    policy_version = _require_text(policy_version, "policy_version")
    sleeve_id = _require_identifier(sleeve_id, "sleeve_id", max_length=_MAX_SLEEVE_ID)
    market_symbol = _require_identifier(market_symbol, "market_symbol", max_length=_MAX_MARKET_SYMBOL)
    reference_notional = _require_reference_notional(paper_performance_reference_notional)
    treatment = _require_member(funding_treatment, PaperSleeveFundingTreatment, "funding_treatment")
    approval_record = _canonical_approval(approval)

    seed = PaperSleeveEquityBasisPolicy(
        schema_version=_SCHEMA_VERSION,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        policy_id=policy_id,
        policy_version=policy_version,
        sleeve_id=sleeve_id,
        market_symbol=market_symbol,
        paper_performance_reference_notional=reference_notional,
        funding_treatment=treatment,  # type: ignore[arg-type]
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST,
        policy_digest="",
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is PaperSleeveEquityBasisApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        equity_basis_digest="",
    )
    policy_digest = _policy_digest(_to_payload(seed))
    committed = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "rule_set_digest": PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST,
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
    return replace(governed, equity_basis_digest=edge_payload_digest(_to_payload(governed), _SELF_DIGEST_FIELD))


def build_paper_sleeve_equity_basis_policy(
    *,
    policy_id: str,
    policy_version: str,
    sleeve_id: str,
    market_symbol: str,
    paper_performance_reference_notional: str,
    funding_treatment: PaperSleeveFundingTreatment,
    approval: PaperSleeveEquityBasisApproval | None,
) -> PaperSleeveEquityBasisPolicy:
    """Build the governed equity-basis policy; every governed value is explicit (there are no defaults).

    Malformed, missing or out-of-domain input, or a malformed approval, raises ``PaperSleeveEquityBasisPolicyError``.
    A missing, non-matching or ``TEST_ONLY_SYNTHETIC`` approval yields ``NEEDS_GOVERNANCE_APPROVAL``; only an exact
    ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.
    """

    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        sleeve_id=sleeve_id,
        market_symbol=market_symbol,
        paper_performance_reference_notional=paper_performance_reference_notional,
        funding_treatment=funding_treatment,
        approval=approval,
    )


def paper_sleeve_equity_basis_policy_to_dict(policy: PaperSleeveEquityBasisPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def paper_sleeve_equity_basis_policy_digest(policy: PaperSleeveEquityBasisPolicy) -> str:
    """Recompute the canonical policy artifact digest, excluding only ``equity_basis_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


def paper_sleeve_equity_basis_methodology_policy_ids(policy: PaperSleeveEquityBasisPolicy) -> dict[str, str]:
    """The policy identifiers a ``PaperReturnSeriesMethodology`` must declare to be bound to this exact policy."""

    if type(policy) is not PaperSleeveEquityBasisPolicy or not edge_is_hex64(policy.policy_digest):
        raise _fail("policy_malformed")
    return {name: f"sleeve-basis-{policy.policy_digest}-{suffix}" for name, suffix in _METHODOLOGY_POLICY_SUFFIXES}


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


_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(PaperSleeveEquityBasisApprovalKind),
}
_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "paper_performance_reference_notional": _as_decimal,
    "funding_treatment": _as_enum(PaperSleeveFundingTreatment),
    "approval": _as_optional(PaperSleeveEquityBasisApproval, _APPROVAL_CONVERTERS),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def paper_sleeve_equity_basis_policy_from_payload(payload: object) -> PaperSleeveEquityBasisPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(PaperSleeveEquityBasisPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def paper_sleeve_equity_basis_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        paper_sleeve_equity_basis_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> PaperSleeveEquityBasisPolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        sleeve_id=policy.sleeve_id,  # type: ignore[attr-defined]
        market_symbol=policy.market_symbol,  # type: ignore[attr-defined]
        paper_performance_reference_notional=policy.paper_performance_reference_notional,  # type: ignore[attr-defined]
        funding_treatment=policy.funding_treatment,  # type: ignore[attr-defined]
        approval=policy.approval,  # type: ignore[attr-defined]
    )


def verify_paper_sleeve_equity_basis_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=PaperSleeveEquityBasisPolicy,
        to_payload=_to_payload,
        parse_payload=paper_sleeve_equity_basis_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST",
    "PaperSleeveEquityBasisApproval",
    "PaperSleeveEquityBasisApprovalKind",
    "PaperSleeveEquityBasisPolicy",
    "PaperSleeveEquityBasisPolicyError",
    "PaperSleeveFundingTreatment",
    "build_paper_sleeve_equity_basis_policy",
    "paper_sleeve_equity_basis_methodology_policy_ids",
    "paper_sleeve_equity_basis_policy_digest",
    "paper_sleeve_equity_basis_policy_from_payload",
    "paper_sleeve_equity_basis_policy_payload_is_well_formed",
    "paper_sleeve_equity_basis_policy_to_dict",
    "paper_sleeve_equity_basis_rule_set",
    "verify_paper_sleeve_equity_basis_policy",
]
