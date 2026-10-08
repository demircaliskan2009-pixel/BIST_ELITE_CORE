"""RG-8 paper portfolio governance decision (RG8_PAPER_PORTFOLIO_GOVERNANCE_DECISION_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 1, item 7 (RG-8), under the
controller structural authority ``RG8_TERMINAL_GOVERNANCE_AND_PORTFOLIO_STOP_POLICY_V1``.

The terminal PAPER governance record of the RG-2 to RG-8 chain. It binds four things into one deterministic,
digest-bound record that decides the portfolio stop and the terminal paper allocation governance:
- the accepted portfolio constitution (RG-2);
- the portfolio drawdown evidence (RG-4);
- one historical ladder decision per envelope sleeve (RG-6);
- the exact allocation proposal (RG-7).

It is paper governance only: never capital, an order, execution permission, or live, shadow or operational readiness.

Inputs. Each is REBUILT through its accepted public builder and must equal the supplied artifact canonically; only the
reconstruction is used:

* RG-2: the envelope, re-pinned through its total verifier, its rule set and its pending regime markers;
* RG-4: the ``PaperSleeveDrawdownEvidence``, from its exact inputs. This transitively re-proves RG-3 and the governed
  performance-path policy;
* RG-6: exactly one ``PaperSleevePromotionDemotionDecision`` per envelope-declared sleeve, from its exact inputs. This
  transitively re-proves its lineage and its RG-3, RG-4 and RG-5;
* RG-7: the ``PaperPortfolioAllocationDecision``, from its exact inputs. This transitively re-proves RG-5, the intra-sleeve
  reservations, the EF-7 admissions and the governed EF-8 current-head attestations.

Coherence: everything belongs to one exact evaluation world, and any contradiction raises.
- Every artifact binds the same envelope digest.
- RG-4 ends at the injected UTC-day-aligned evaluation end, and every RG-6 and RG-7 is evaluated there.
- Every RG-6 binds the supplied RG-4 digest, the RG-5 digest RG-7 re-proved, and its sleeve's RG-3 digest as RG-4
  records it.

RG-6 is HISTORICAL provenance only (``BIND_EXACT_SAME_COORDINATE_RG6_DECISION_AS_HISTORICAL_PROVENANCE_ONLY``).
- Its status gates terminal completeness.
- Its tier and transition never reach the stop or the allocation.
- ``current_ladder_head_proven`` stays structurally False.

Portfolio stop (``RG8_PORTFOLIO_STOP_MAX_PEAK_DISTANCE_V1``).
- The stop consumes ONLY the RG-4 portfolio ``max_peak_distance``, checked against the RG-2 ``portfolio_stop_levels``.
  That is the largest drawdown the governed evidence window ever reached, which is what a governed maximum allowed
  portfolio drawdown limits. The current peak distance is carried as evidence only.
- A level is breached exactly when the maximum STRICTLY exceeds its threshold; equality does not breach. Every level is
  checked, every breached level is recorded, and the highest breached level is reported.
- The stop is evaluated only when the envelope is governed and the RG-4 evidence is READY with a computed portfolio
  measurement. Otherwise it is not evaluated, and no drawdown is fabricated.
- It depends on nothing else. No correlation, tier, allocation amount, Sharpe, lifecycle state or regime marker creates
  or suppresses it, and the pending regime advisory can never trigger it.

Terminal status. Provenance contradictions raise; otherwise the first matching rule wins:
1. NEEDS_GOVERNANCE_APPROVAL when the envelope or RG-4 lacks governance (stop not evaluated);
2. NOT_COMPUTABLE when the RG-4 portfolio drawdown is not computable (stop not evaluated);
3. PORTFOLIO_STOP_TRIGGERED when the evaluated stop triggers, whatever RG-6 or RG-7 say;
4. NEEDS_GOVERNANCE_APPROVAL for any RG-6 or RG-7 lacking governance;
5. NOT_COMPUTABLE for any RG-6 that is not computable;
6. ALLOCATION_REJECTED for an RG-7 rejection;
7. READY when every RG-6 and RG-7 is READY.

Terminal paper allocation governance.
- READY carries every RG-7 final allocation exactly; every other status governs zero for every sleeve.
- The RG-7 proposal and its own finals are kept as evidence.
- There is no new sizing, scaling or partial fit.

Exact ``Fraction`` comparison of the accepted texts; no float or ``decimal``, and no IO, clock, randomness, network or
environment access. The verifier rebuilds from the exact inputs and is total.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperPortfolioAllocationDecision,
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationStatus,
    build_paper_portfolio_allocation_decision,
    paper_portfolio_allocation_decision_to_dict,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioRiskEnvelope,
    PaperPortfolioStopLevel,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownStatus,
    build_paper_sleeve_drawdown_evidence,
    paper_sleeve_drawdown_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleevePromotionDemotionDecision,
    PaperSleevePromotionDemotionInputs,
    build_paper_sleeve_promotion_demotion_decision,
    paper_sleeve_promotion_demotion_decision_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "paper_portfolio_governance_decision"
_SCHEMA = "paper-portfolio-governance-decision.v1"
_DIGEST_FIELD = "governance_decision_digest"
_IDENTIFIER_PUNCTUATION = frozenset("-_./:")
_ZERO = "0"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_portfolio_governance_decision_rules.v1",
    "contract_id": "RG8_PAPER_PORTFOLIO_GOVERNANCE_DECISION_V1",
    "structural_authority_id": "RG8_TERMINAL_GOVERNANCE_AND_PORTFOLIO_STOP_POLICY_V1",
    "scope_rule_id": "terminal_paper_governance_record_never_capital_order_execution_live_shadow_or_readiness.v1",
    "input_rule_id": "rg2_rg4_one_rg6_per_declared_sleeve_and_rg7_each_rebuilt_and_canonically_equal.v1",
    "coherence_rule_id": "one_envelope_one_utc_day_evaluation_end_rg6_bound_to_the_supplied_rg4_rg5_and_rg3.v1",
    "rg6_role_id": "BIND_EXACT_SAME_COORDINATE_RG6_DECISION_AS_HISTORICAL_PROVENANCE_ONLY",
    "rg6_rule_id": "rg6_status_gates_completeness_tier_and_transition_never_reach_stop_or_allocation.v1",
    "rg7_role_id": "EXACT_REPROVEN_ALLOCATION_INPUT",
    "drawdown_consumption": "RG8_PORTFOLIO_STOP_MAX_PEAK_DISTANCE_V1",
    "stop_input_rule_id": "rg4_portfolio_max_peak_distance_only_current_peak_distance_is_evidence_only.v1",
    "stop_breach_operator": "STRICT_GREATER_THAN",
    "stop_rule_id": "level_breached_iff_max_peak_distance_strictly_exceeds_its_governed_threshold.v1",
    "stop_record_rule_id": "every_level_checked_every_breach_recorded_highest_breached_level_reported.v1",
    "stop_readiness_rule_id": "evaluated_only_with_a_governed_envelope_and_a_ready_rg4_portfolio_measurement.v1",
    "stop_independence_rule_id": "stop_reads_only_the_rg2_stop_levels_and_the_rg4_portfolio_maximum.v1",
    "regime_rule_id": "regime_advisory_pending_unavailable_never_triggers_or_suppresses_a_stop.v1",
    "status_order": (
        "provenance_contradiction_raises",
        "stop_authority_needs_governance_approval",
        "stop_input_not_computable",
        "portfolio_stop_triggered",
        "rg6_or_rg7_needs_governance_approval",
        "rg6_not_computable",
        "rg7_allocation_rejected",
        "ready",
    ),
    "allocation_rule_id": "ready_carries_every_rg7_final_exactly_every_other_status_governs_zero.v1",
    "no_scaling_rule_id": "no_sizing_scaling_clipping_or_partial_fit.v1",
    "numeric_rule_id": "exact_fraction_comparison_of_accepted_texts_no_float_no_decimal.v1",
    "utc_day_ns": 86_400_000_000_000,
    "decimal_scale": 18,
    "decimal_text_max_length": 60,
    "fraction_max_part_digits": 4096,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
}
PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_DRAWDOWN_CONSUMPTION = str(_RULE_SET_V1["drawdown_consumption"])
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_text_max_length"]  # type: ignore[assignment]
_MAX_FRACTION_DIGITS: int = _RULE_SET_V1["fraction_max_part_digits"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]


def paper_portfolio_governance_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperPortfolioGovernanceError(EdgeArtifactError):
    """A malformed input or any provenance or coherence defect: an invalid terminal record is never represented."""


class PaperPortfolioGovernanceStatus(str, Enum):
    """The terminal status; only READY accepts the paper allocation governance."""

    READY = "READY"
    PORTFOLIO_STOP_TRIGGERED = "PORTFOLIO_STOP_TRIGGERED"
    ALLOCATION_REJECTED = "ALLOCATION_REJECTED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


@dataclass(frozen=True)
class PaperPortfolioGovernanceSleeveInputs:
    """One envelope-declared sleeve's exact RG-6 historical decision and the inputs it is rebuilt from."""

    sleeve_id: str
    ladder_decision_inputs: PaperSleevePromotionDemotionInputs
    ladder_decision: PaperSleevePromotionDemotionDecision


@dataclass(frozen=True)
class PaperPortfolioGovernanceInputs:
    """Everything RG-8 consumes; consumers re-prove a decision by rebuilding it from exactly these."""

    governance_decision_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    evaluation_end_ns: int
    drawdown_inputs: PaperSleeveDrawdownInputs
    drawdown_evidence: PaperSleeveDrawdownEvidence
    sleeves: tuple[PaperPortfolioGovernanceSleeveInputs, ...]
    allocation_inputs: PaperPortfolioAllocationInputs
    allocation_decision: PaperPortfolioAllocationDecision


@dataclass(frozen=True)
class PaperPortfolioStopLevelCheck:
    """One governed RG-2 stop level and whether the RG-4 portfolio maximum strictly exceeds its threshold."""

    stop_level: int
    max_portfolio_drawdown_fraction: str
    breached: bool


@dataclass(frozen=True)
class PaperPortfolioGovernanceSleeveRecord:
    """One sleeve's terminal binding: its RG-3 digest, its historical RG-6 decision and both of its allocations."""

    sleeve_id: str
    performance_evidence_digest: str
    ladder_decision_digest: str
    ladder_decision_status: str
    ladder_transition: str | None
    ladder_resulting_tier: str | None
    allocation_final_allocated_budget: str
    terminal_final_allocated_budget: str


PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("capital_allocated", False),
    ("account_equity_represented", False),
    ("real_capital_reserved", False),
    ("execution_authorized", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("order_created", False),
    ("order_routed", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("live_api_called", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("private_api_ready", False),
    ("deribit_ready", False),
    ("profitability_proven", False),
    ("edge_proven", False),
    ("current_ladder_head_proven", False),
    ("global_current_lifecycle_head_proven", False),
    ("live_current_lifecycle_head_proven", False),
    ("regime_stop_triggered", False),
    ("regime_advisory_can_trigger_portfolio_stop", False),
    ("prdv4_stage4_complete", False),
)


@dataclass(frozen=True)
class PaperPortfolioGovernanceDecision:
    """Immutable, digest-bound RG-8 terminal paper governance record. Paper only: never capital, an order or readiness.

    ``portfolio_stop_evaluated`` and ``portfolio_stop_triggered`` are RG-8's own decisions, not non-claims.
    """

    schema_version: str
    status: PaperPortfolioGovernanceStatus
    ready: bool
    paper_allocation_governance_accepted: bool
    governance_decision_id: str
    correlation_id: str
    evaluation_end_ns: int
    envelope_id: str
    envelope_version: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    drawdown_evidence_digest: str
    drawdown_status: str
    performance_path_policy_digest: str
    portfolio_current_peak_distance: str
    portfolio_max_peak_distance: str
    drawdown_consumption: str
    portfolio_stop_evaluated: bool
    portfolio_stop_triggered: bool
    stop_level_checks: tuple[PaperPortfolioStopLevelCheck, ...]
    breached_stop_levels: tuple[int, ...]
    highest_breached_stop_level: int | None
    stop_reason_codes: tuple[str, ...]
    correlation_evidence_digest: str
    allocation_decision_digest: str
    allocation_status: str
    allocation_total_final_allocated_budget: str
    terminal_total_final_allocated_budget: str
    declared_sleeve_ids: tuple[str, ...]
    sleeves: tuple[PaperPortfolioGovernanceSleeveRecord, ...]
    governance_reason_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    regime_advisory_status: str
    regime_evidence_status: str
    rule_set_id: str
    rule_set_digest: str
    governance_decision_digest: str
    paper_only: bool = True
    capital_allocated: bool = False
    account_equity_represented: bool = False
    real_capital_reserved: bool = False
    execution_authorized: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    order_created: bool = False
    order_routed: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    live_api_called: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    private_api_ready: bool = False
    deribit_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    current_ladder_head_proven: bool = False
    global_current_lifecycle_head_proven: bool = False
    live_current_lifecycle_head_proven: bool = False
    regime_stop_triggered: bool = False
    regime_advisory_can_trigger_portfolio_stop: bool = False
    prdv4_stage4_complete: bool = False


_RECORD_TYPES = frozenset({PaperPortfolioStopLevelCheck, PaperPortfolioGovernanceSleeveRecord})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperPortfolioGovernanceDecision: {"status": PaperPortfolioGovernanceStatus},
}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> PaperPortfolioGovernanceError:
    return PaperPortfolioGovernanceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _require_identifier(value: object, name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(char.isalnum() or char in _IDENTIFIER_PUNCTUATION for char in value):
        raise _fail(f"{name}_invalid")
    return _require_text(value, name)


def _require_utc_day(value: object, name: str) -> int:
    """An exact non-negative int64 epoch-nanosecond coordinate on a UTC day boundary; never a bool, never a clock."""

    if type(value) is not int or not 0 <= value <= _MAX_WIRE_INT:
        raise _fail(f"{name}_invalid")
    if value % _DAY_NS:
        raise _fail(f"{name}_not_utc_day_aligned")
    return value


def _snapshot(values: object, name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{name}_malformed")
    return tuple(cast(Sequence[object], values))


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this terminal record."""

    try:
        return builder(*args)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- exact numbers --------------------------------------------------------------------------------------------------


def _governed_threshold(value: object) -> Fraction:
    """The exact value of a governed RG-2 stop threshold: canonical scale-18 decimal text in ``[0, 1)``."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        raise _fail("portfolio_stop_threshold_invalid")
    whole, point, decimals = value.partition(".")
    if point != "." or len(decimals) != _SCALE or not _digits(whole) or not _digits(decimals) or whole != "0":
        raise _fail("portfolio_stop_threshold_invalid")
    return Fraction(int(decimals), 10**_SCALE)


def _peak_distance(value: object) -> Fraction:
    """The exact value of an RG-4 peak distance: reduced ``"p/q"`` text in ``[0, 1)`` within the RG-4 digit bound."""

    if type(value) is not str or not value.isascii():
        raise _fail("portfolio_max_peak_distance_invalid")
    numerator, slash, denominator = value.partition("/")
    if slash != "/" or not _digits(numerator) or not _digits(denominator):
        raise _fail("portfolio_max_peak_distance_invalid")
    if len(numerator) > _MAX_FRACTION_DIGITS or len(denominator) > _MAX_FRACTION_DIGITS:
        raise _fail("portfolio_max_peak_distance_invalid")
    if (numerator.startswith("0") and numerator != "0") or denominator.startswith("0"):
        raise _fail("portfolio_max_peak_distance_invalid")
    distance = Fraction(int(numerator), int(denominator))
    if f"{distance.numerator}/{distance.denominator}" != value or not 0 <= distance < 1:
        raise _fail("portfolio_max_peak_distance_invalid")
    return distance


# --- canonical wire form --------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in cast(tuple, value)]
    if type(value) is int:
        if 0 <= cast(int, value) <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if value is None or type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: an enum field holds its exact member, everything else exact records and scalars."""

    enums = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for item in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, item.name)
        enum_cls = enums.get(item.name)
        if enum_cls is None:
            payload[item.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[item.name] = cast(Enum, value).value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- provenance and coherence ---------------------------------------------------------------------------------------


def _require_envelope(value: object) -> PaperPortfolioRiskEnvelope:
    """The RG-2 envelope, re-pinned through its total verifier, its rule set and its pending regime markers."""

    _require_exact(value, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(value).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    envelope = cast(PaperPortfolioRiskEnvelope, value)
    if envelope.rule_set_digest != PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST:
        raise _fail("portfolio_risk_envelope_rule_set_unsupported")
    # V1 carries no regime authority: an envelope no longer marking its regime fields pending is out of scope.
    if (
        envelope.regime_stratified_correlation_status != EDGE_REGIME_LABEL_BINDING_PENDING
        or envelope.regime_concentration_demotion_status != EDGE_REGIME_LABEL_BINDING_PENDING
    ):
        raise _fail("regime_status_unsupported")
    return envelope


def _prove_drawdown(
    inputs: object, evidence: object, *, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> PaperSleeveDrawdownEvidence:
    """RG-4 rebuilt from its exact inputs on the same envelope, ending exactly at the evaluation end."""

    _require_exact(inputs, PaperSleeveDrawdownInputs, "drawdown_inputs")
    _require_exact(evidence, PaperSleeveDrawdownEvidence, "drawdown_evidence")
    rebuilt = _rebuild("drawdown_evidence", build_paper_sleeve_drawdown_evidence, inputs)
    if not _canonically_equal(evidence, rebuilt, paper_sleeve_drawdown_evidence_to_dict):
        raise _fail("drawdown_evidence_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("drawdown_evidence_envelope_mismatch")
    if rebuilt.window_end_ns != evaluation_end:
        raise _fail("drawdown_evidence_not_at_the_evaluation_end")
    return rebuilt


def _prove_allocation(
    inputs: object, decision: object, *, envelope: PaperPortfolioRiskEnvelope, evaluation_end: int
) -> PaperPortfolioAllocationDecision:
    """RG-7 rebuilt from its exact inputs on the same envelope at the evaluation end."""

    _require_exact(inputs, PaperPortfolioAllocationInputs, "allocation_inputs")
    _require_exact(decision, PaperPortfolioAllocationDecision, "allocation_decision")
    rebuilt = _rebuild("allocation_decision", build_paper_portfolio_allocation_decision, inputs)
    if not _canonically_equal(decision, rebuilt, paper_portfolio_allocation_decision_to_dict):
        raise _fail("allocation_decision_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("allocation_decision_envelope_mismatch")
    if rebuilt.evaluation_end_ns != evaluation_end:
        raise _fail("allocation_decision_not_at_the_evaluation_end")
    return rebuilt


def _prove_ladders(
    values: object,
    *,
    envelope: PaperPortfolioRiskEnvelope,
    evaluation_end: int,
    drawdown: PaperSleeveDrawdownEvidence,
    allocation: PaperPortfolioAllocationDecision,
) -> dict[str, PaperSleevePromotionDemotionDecision]:
    """Exactly one RG-6 decision per declared sleeve, each rebuilt and bound to this one evaluation world."""

    declared = frozenset(cap.sleeve_id for cap in envelope.sleeve_caps)
    performance = {record.sleeve_id: record.performance_evidence_digest for record in drawdown.sleeves}
    ladders: dict[str, PaperSleevePromotionDemotionDecision] = {}
    for item in _snapshot(values, "sleeves"):
        _require_exact(item, PaperPortfolioGovernanceSleeveInputs, "sleeve")
        sleeve = cast(PaperPortfolioGovernanceSleeveInputs, item)
        sleeve_id = _require_identifier(sleeve.sleeve_id, "sleeve_id")
        if sleeve_id not in declared:
            raise _fail("sleeve_not_declared_by_envelope")
        if sleeve_id in ladders:
            raise _fail("sleeve_ladder_decision_duplicate")
        _require_exact(sleeve.ladder_decision_inputs, PaperSleevePromotionDemotionInputs, "ladder_decision_inputs")
        _require_exact(sleeve.ladder_decision, PaperSleevePromotionDemotionDecision, "ladder_decision")
        rebuilt = _rebuild(
            "ladder_decision", build_paper_sleeve_promotion_demotion_decision, sleeve.ladder_decision_inputs
        )
        if not _canonically_equal(sleeve.ladder_decision, rebuilt, paper_sleeve_promotion_demotion_decision_to_dict):
            raise _fail("ladder_decision_not_reconstructed")
        if rebuilt.sleeve_id != sleeve_id:
            raise _fail("ladder_decision_sleeve_mismatch")
        if rebuilt.envelope_digest != envelope.envelope_digest:
            raise _fail("ladder_decision_envelope_mismatch")
        if rebuilt.evaluation_end_ns != evaluation_end:
            raise _fail("ladder_decision_not_at_the_evaluation_end")
        if rebuilt.drawdown_evidence_digest != drawdown.drawdown_evidence_digest:
            raise _fail("ladder_decision_drawdown_evidence_mismatch")
        if rebuilt.correlation_evidence_digest != allocation.correlation_evidence_digest:
            raise _fail("ladder_decision_correlation_evidence_mismatch")
        if performance.get(sleeve_id) != rebuilt.performance_evidence_digest:
            raise _fail("ladder_decision_performance_evidence_mismatch")
        ladders[sleeve_id] = rebuilt
    if set(ladders) != declared:
        raise _fail("sleeve_ladder_decisions_incomplete")
    return ladders


# --- the portfolio stop ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stop:
    """The stop stage: evaluated from the governed RG-2 stop levels and the re-proven RG-4 portfolio maximum alone."""

    governance_blockers: tuple[str, ...]
    computability_blockers: tuple[str, ...]
    current_peak_distance: str
    max_peak_distance: str
    checks: tuple[PaperPortfolioStopLevelCheck, ...]
    breached: tuple[int, ...]
    highest: int | None

    @property
    def evaluated(self) -> bool:
        return not self.governance_blockers and not self.computability_blockers


def _check_stop_levels(
    maximum: Fraction, levels: Sequence[PaperPortfolioStopLevel]
) -> tuple[tuple[PaperPortfolioStopLevelCheck, ...], tuple[int, ...], int | None]:
    """Every governed level, breached exactly when the portfolio maximum STRICTLY exceeds its threshold."""

    checks = tuple(
        PaperPortfolioStopLevelCheck(
            stop_level=level.stop_level,
            max_portfolio_drawdown_fraction=level.max_portfolio_drawdown_fraction,
            breached=maximum > _governed_threshold(level.max_portfolio_drawdown_fraction),
        )
        for level in levels
    )
    breached = tuple(check.stop_level for check in checks if check.breached)
    return checks, breached, (max(breached) if breached else None)


def _portfolio_stop(envelope: PaperPortfolioRiskEnvelope, drawdown: PaperSleeveDrawdownEvidence) -> _Stop:
    """Stage 3: the portfolio stop. It reads the RG-2 stop levels and the RG-4 portfolio record, and nothing else."""

    governance: list[str] = []
    computability: list[str] = []
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    if drawdown.status is PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("drawdown_evidence_needs_governance_approval"))
    elif drawdown.status is not PaperSleeveDrawdownStatus.READY:
        computability.append(_reason("drawdown_evidence_not_computable"))
    measurement = drawdown.portfolio.measurement
    if not governance and (drawdown.portfolio.computed is not True or measurement is None):
        computability.append(_reason("portfolio_drawdown_not_computed"))
    if governance or computability or measurement is None:
        return _Stop(_sorted_unique(governance), _sorted_unique(computability), "", "", (), (), None)
    checks, breached, highest = _check_stop_levels(
        _peak_distance(measurement.max_peak_distance), envelope.portfolio_stop_levels
    )
    return _Stop((), (), measurement.current_peak_distance, measurement.max_peak_distance, checks, breached, highest)


def _terminal_status(
    *,
    stop: _Stop,
    downstream_governance: Sequence[str],
    ladder_not_computable: Sequence[str],
    allocation_rejected: bool,
) -> PaperPortfolioGovernanceStatus:
    """The terminal status order: the stop's own inputs first, then a valid stop, then the downstream outcomes."""

    if stop.governance_blockers:
        return PaperPortfolioGovernanceStatus.NEEDS_GOVERNANCE_APPROVAL
    if stop.computability_blockers:
        return PaperPortfolioGovernanceStatus.NOT_COMPUTABLE
    if stop.breached:
        return PaperPortfolioGovernanceStatus.PORTFOLIO_STOP_TRIGGERED
    if downstream_governance:
        return PaperPortfolioGovernanceStatus.NEEDS_GOVERNANCE_APPROVAL
    if ladder_not_computable:
        return PaperPortfolioGovernanceStatus.NOT_COMPUTABLE
    if allocation_rejected:
        return PaperPortfolioGovernanceStatus.ALLOCATION_REJECTED
    return PaperPortfolioGovernanceStatus.READY


# --- the decision ---------------------------------------------------------------------------------------------------


def build_paper_portfolio_governance_decision(
    inputs: PaperPortfolioGovernanceInputs,
) -> PaperPortfolioGovernanceDecision:
    """Decide the terminal paper governance of one exact evaluation world from fully re-proven inputs.

    Malformed input and every provenance or coherence defect raise ``PaperPortfolioGovernanceError``. The portfolio stop
    is decided from the RG-2 stop levels and the RG-4 portfolio maximum alone; the terminal status then follows the
    committed order, and only READY carries the RG-7 final allocations. Inputs are never mutated.
    """

    _require_exact(inputs, PaperPortfolioGovernanceInputs, "inputs")
    decision_id = _require_text(inputs.governance_decision_id, "governance_decision_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    evaluation_end = _require_utc_day(inputs.evaluation_end_ns, "evaluation_end_ns")
    envelope = _require_envelope(inputs.portfolio_risk_envelope)

    # Stage 1: every input is rebuilt and bound to the one evaluation world before anything is decided.
    drawdown = _prove_drawdown(
        inputs.drawdown_inputs, inputs.drawdown_evidence, envelope=envelope, evaluation_end=evaluation_end
    )
    allocation = _prove_allocation(
        inputs.allocation_inputs, inputs.allocation_decision, envelope=envelope, evaluation_end=evaluation_end
    )
    ladders = _prove_ladders(
        inputs.sleeves, envelope=envelope, evaluation_end=evaluation_end, drawdown=drawdown, allocation=allocation
    )

    # Stage 2: the portfolio stop, from the governed stop levels and the RG-4 portfolio maximum alone.
    stop = _portfolio_stop(envelope, drawdown)

    # Stage 3: the downstream RG-6 and RG-7 outcomes, then the terminal status.
    declared = tuple(cap.sleeve_id for cap in envelope.sleeve_caps)
    downstream_governance = [
        _reason(f"ladder_decision_needs_governance_approval:{sleeve_id}")
        for sleeve_id in declared
        if ladders[sleeve_id].status is PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL
    ]
    if allocation.status is PaperPortfolioAllocationStatus.NEEDS_GOVERNANCE_APPROVAL:
        downstream_governance.append(_reason("allocation_decision_needs_governance_approval"))
    ladder_not_computable = [
        _reason(f"ladder_decision_not_computable:{sleeve_id}")
        for sleeve_id in declared
        if ladders[sleeve_id].status is PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
    ]
    allocation_rejected = allocation.status is PaperPortfolioAllocationStatus.ALLOCATION_REJECTED
    status = _terminal_status(
        stop=stop,
        downstream_governance=downstream_governance,
        ladder_not_computable=ladder_not_computable,
        allocation_rejected=allocation_rejected,
    )
    accepted = status is PaperPortfolioGovernanceStatus.READY

    stop_reasons = (
        [_reason(f"portfolio_stop_level_breached:{level}") for level in stop.breached]
        if stop.evaluated
        else [*stop.governance_blockers, *stop.computability_blockers]
    )
    allocation_finals = {sleeve.sleeve_id: sleeve.final_allocated_budget for sleeve in allocation.sleeves}
    records = []
    for sleeve_id in declared:
        ladder = ladders[sleeve_id]
        records.append(
            PaperPortfolioGovernanceSleeveRecord(
                sleeve_id=sleeve_id,
                performance_evidence_digest=ladder.performance_evidence_digest,
                ladder_decision_digest=ladder.decision_digest,
                ladder_decision_status=ladder.status.value,
                ladder_transition=None if ladder.transition is None else ladder.transition.value,
                ladder_resulting_tier=None if ladder.resulting_tier is None else ladder.resulting_tier.value,
                allocation_final_allocated_budget=allocation_finals[sleeve_id],
                terminal_final_allocated_budget=allocation_finals[sleeve_id] if accepted else _ZERO,
            )
        )
    governance = [*stop.governance_blockers, *downstream_governance]
    every_reason = [
        *governance,
        *stop.computability_blockers,
        *ladder_not_computable,
        *([_reason("allocation_decision_rejected")] if allocation_rejected else []),
        *stop_reasons,
    ]

    seed = PaperPortfolioGovernanceDecision(
        schema_version=_SCHEMA,
        status=status,
        ready=accepted,
        paper_allocation_governance_accepted=accepted,
        governance_decision_id=decision_id,
        correlation_id=correlation_id,
        evaluation_end_ns=evaluation_end,
        envelope_id=envelope.envelope_id,
        envelope_version=envelope.envelope_version,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        drawdown_evidence_digest=drawdown.drawdown_evidence_digest,
        drawdown_status=drawdown.status.value,
        performance_path_policy_digest=drawdown.performance_path_policy_digest,
        portfolio_current_peak_distance=stop.current_peak_distance,
        portfolio_max_peak_distance=stop.max_peak_distance,
        drawdown_consumption=_DRAWDOWN_CONSUMPTION,
        portfolio_stop_evaluated=stop.evaluated,
        portfolio_stop_triggered=bool(stop.breached),
        stop_level_checks=stop.checks,
        breached_stop_levels=stop.breached,
        highest_breached_stop_level=stop.highest,
        stop_reason_codes=_sorted_unique(stop_reasons),
        correlation_evidence_digest=allocation.correlation_evidence_digest,
        allocation_decision_digest=allocation.allocation_decision_digest,
        allocation_status=allocation.status.value,
        allocation_total_final_allocated_budget=allocation.total_final_allocated_budget,
        terminal_total_final_allocated_budget=allocation.total_final_allocated_budget if accepted else _ZERO,
        declared_sleeve_ids=declared,
        sleeves=tuple(records),
        governance_reason_codes=_sorted_unique(governance),
        reason_codes=_sorted_unique(every_reason),
        regime_advisory_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST,
        governance_decision_digest="",
    )
    return replace(seed, governance_decision_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def paper_portfolio_governance_decision_to_dict(decision: PaperPortfolioGovernanceDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping of a decision, its self-digest included."""

    return _payload(decision)


def paper_portfolio_governance_decision_digest(decision: PaperPortfolioGovernanceDecision) -> str:
    """Recompute the canonical decision digest, excluding only ``governance_decision_digest``."""

    return edge_payload_digest(_payload(decision), _DIGEST_FIELD)


def verify_paper_portfolio_governance_decision(
    decision: object, inputs: PaperPortfolioGovernanceInputs
) -> EdgeEvidenceVerification:
    """Re-prove a decision by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "evidence_type_invalid"
    try:
        if type(decision) is not PaperPortfolioGovernanceDecision:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(decision)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_paper_portfolio_governance_decision(inputs))
        codes = {_reason("self_digest_mismatch")} if carried[_DIGEST_FIELD] != recomputed else set()
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
    "PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS",
    "PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST",
    "PaperPortfolioGovernanceDecision",
    "PaperPortfolioGovernanceError",
    "PaperPortfolioGovernanceInputs",
    "PaperPortfolioGovernanceSleeveInputs",
    "PaperPortfolioGovernanceSleeveRecord",
    "PaperPortfolioGovernanceStatus",
    "PaperPortfolioStopLevelCheck",
    "build_paper_portfolio_governance_decision",
    "paper_portfolio_governance_decision_digest",
    "paper_portfolio_governance_decision_to_dict",
    "paper_portfolio_governance_rule_set",
    "verify_paper_portfolio_governance_decision",
]
