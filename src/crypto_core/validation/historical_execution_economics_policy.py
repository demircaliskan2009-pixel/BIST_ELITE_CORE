"""Governed execution-economics policy for deterministic historical execution (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V1).

A ``HistoricalExecutionEconomicsPolicy`` is the only source of every load-bearing execution and economic convention a
historical execution result may use: contract scope, quantity semantics, PIT economics data contract, execution timing,
fill-ratio model, spread and slippage model, participation impact, fees, funding, valuation schedule, terminal rule,
divergence rule, leverage rule, initial equity and numeric policy. Every identity and every value is a first-class field
committed by ``policy_digest``; nothing is defaulted and nothing is read from ambient state.

Governed values (latency, delays, staleness, spread threshold, slippage floor, depth cap, impact coefficient, taker fee,
funding interval, initial equity) are caller-supplied GOVERNANCE inputs. The builder hard-enforces the six PRDV4 §12.2
prohibitions on them (positive latency, slippage floor >= 5 bps, visible depth cap <= 2%, time-varying spread and a
deterministic fill-ratio model by construction, next-observation execution by construction) and refuses any other
contract scope than linear USDT perpetuals (``inverse_perp`` and every other market type fail closed).

Venue mechanics are never taken from model memory. Each venue-fact field must be supported by a canonical, digest-bound
``HistoricalExecutionExternalFactCitation`` whose ``cited_value`` equals the policy value exactly; a missing, foreign
or non-matching citation leaves the policy ``READY`` + ``NEEDS_EXTERNAL_FACTS``. A tampered citation (carried digest
mismatch) makes the policy ``REJECTED``. ``TEST_ONLY_SYNTHETIC`` citations are allowed for tests and are always
surfaced as ``synthetic_test_facts_used=True``; they are never production truth.

``HistoricalExecutionEconomicsApproval`` is the separate governance authority: it binds the exact policy digest, the
authenticated StrategySpec digest, instrument, market type, DataRequirementRegistry digest, quantity semantics and the
execution and funding identity digests. Approval matching is decided by the consumer (the historical execution
result) with ``historical_execution_economics_approval_mismatches``.

Numeric discipline (``HISTORICAL_EXECUTION_NUMERIC_POLICY_V1``, committed by the digest): ASCII fixed scale-18 decimals,
no exponent, plus sign or negative zero, at most 60 characters; native integers bounded to int64 before serialization;
exact ``Fraction`` arithmetic; monetary values rendered once with exact integer ``ROUND_HALF_EVEN`` and executable
quantities truncated toward zero. There is no ``decimal`` context anywhere.

Status is integrity only (READY/REJECTED); REJECTED implies NOT_EVALUATED. One assembly path serves the builder and
verifier reassembly; ``verify_historical_execution_economics_policy`` is total. Deterministic and pure: no IO, clock,
randomness, network or environment. It proves no edge, profitability, venue truth or readiness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
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

_SCHEMA_VERSION = "historical-execution-economics-policy.v1"
_REASON_PREFIX = "historical_execution_economics_policy"
_SELF_DIGEST_FIELD = "policy_digest"
_CITATION_DIGEST_FIELD = "citation_digest"
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")

# --- v1 contract identities (committed by the policy digest) --------------------------------------------------------

MARKET_TYPE_USDT_PERP = "usdt_perp"
CONTRACT_MODEL_V1 = "linear_usdt_perpetual_v1"
QUANTITY_SEMANTICS_V1 = "base_asset_quantity_v1"
DATA_SERIES_CONTRACT_V1 = "final_funding_mark_price_order_book_top_of_book_v1"
FUNDING_DATA_KEY = "funding_rate"
FUNDING_VALUE_NAME = "funding_rate"
MARK_DATA_KEY = "mark_price"
MARK_VALUE_NAME = "mark_price"
ORDER_BOOK_DATA_KEY = "order_book"
BEST_BID_PRICE_NAME = "best_bid_price"
BEST_ASK_PRICE_NAME = "best_ask_price"
BEST_BID_QUANTITY_NAME = "best_bid_quantity"
BEST_ASK_QUANTITY_NAME = "best_ask_quantity"
REQUIRED_REVISION_POLICY = "immutable_after_finalization"
EXECUTION_TIMING_POLICY_V1 = "pit_visibility_after_latency_next_observation_v1"
LATENCY_TIER_PRDV4_T1 = "prdv4_t1_critical"
FILL_RATIO_MODEL_V1 = "visible_depth_linear_v1"
SLIPPAGE_MODEL_V1 = "max_floor_vs_half_spread_plus_impact_v1"
IMPACT_MODEL_V1 = "participation_linear_v1"
FEE_MODEL_V1 = "all_taker_bps_on_fill_notional_v1"
FUNDING_MODEL_V1 = "linear_final_funding_settlement_v1"
FUNDING_LIABILITY_RULE_V1 = "event_time_plus_interval_v1"
FUNDING_NOTIONAL_PRICE_SOURCE_V1 = "mark_price_at_liability_time_v1"
FUNDING_SIGN_CONVENTION_V1 = "positive_rate_long_pays_v1"
SAME_TIMESTAMP_PRIORITY_V1 = "funding_settlement_before_fill_v1"
VALUATION_SCHEDULE_V1 = "events_plus_utc_day_boundaries_v1"
TERMINAL_RULE_V1 = "mark_to_market_no_forced_close_v1"
DIVERGENCE_RULE_V1 = "target_delta_close_only_clamp_v1"
LEVERAGE_RULE_V1 = "strategy_spec_max_leverage_post_fill_mark_notional_v1"

_EXECUTION_IDENTITY_FIELDS = (
    "execution_timing_policy_id",
    "latency_tier_id",
    "fill_ratio_model_id",
    "slippage_model_id",
    "impact_model_id",
    "fee_model_id",
    "valuation_schedule_id",
    "terminal_rule_id",
    "divergence_rule_id",
    "leverage_rule_id",
)
_FUNDING_IDENTITY_FIELDS = (
    "funding_model_id",
    "funding_liability_rule_id",
    "funding_notional_price_source_id",
    "funding_sign_convention_id",
    "same_timestamp_priority_id",
)

HISTORICAL_EXECUTION_POLICY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("venue_facts_proven", False),
    ("production_values_approved", False),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_EXECUTION_POLICY_NON_CLAIM_FLAGS)


class HistoricalExecutionEconomicsPolicyError(EdgeArtifactError):
    """Raised on malformed caller input, a PRDV4 prohibited assumption, an unsupported scope or a scope token."""


class HistoricalExecutionFactId(str, Enum):
    """Venue-mechanics facts that must be supported by an external citation before a policy can advance."""

    TAKER_FEE_BPS = "taker_fee_bps"
    FUNDING_INTERVAL_NS = "funding_interval_ns"
    FUNDING_LIABILITY_RULE = "funding_liability_rule"
    FUNDING_NOTIONAL_PRICE_SOURCE = "funding_notional_price_source"
    FUNDING_SIGN_CONVENTION = "funding_sign_convention"
    CONTRACT_MODEL = "contract_model"
    QUANTITY_SEMANTICS = "quantity_semantics"
    ORDER_BOOK_TOP_OF_BOOK_SEMANTICS = "order_book_top_of_book_semantics"


class HistoricalExecutionCitationKind(str, Enum):
    DEEP_RESEARCH_CITED = "DEEP_RESEARCH_CITED"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class HistoricalExecutionApprovalKind(str, Enum):
    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


@dataclass(frozen=True)
class HistoricalExecutionNumericPolicy:
    """Every load-bearing numeric representation and rounding rule; committed by the policy digest."""

    numeric_policy_id: str
    decimal_grammar_id: str
    decimal_scale: int
    max_decimal_text_length: int
    integer_grammar_id: str
    max_wire_integer: int
    arithmetic_id: str
    amount_rounding_id: str
    quantity_rounding_id: str
    render_id: str


@dataclass(frozen=True)
class HistoricalExecutionConformance:
    """Digest-bound PRDV4 conformance declaration of the v1 execution model; false fields are never hidden."""

    same_observation_fill_prohibited: bool
    fill_ratio_model_enforced: bool
    zero_slippage_prohibited: bool
    positive_latency_enforced: bool
    visible_depth_cap_enforced: bool
    time_varying_spread_enforced: bool
    actual_final_funding_stream_required: bool
    almgren_chriss_modeled: bool
    maker_rebate_modeled: bool
    lot_tick_rounding_modeled: bool
    margin_liquidation_modeled: bool
    inverse_contract_modeled: bool
    prdv4_min_slippage_floor_bps: str
    prdv4_max_visible_depth_cap_fraction: str


@dataclass(frozen=True)
class HistoricalExecutionExternalFactCitation:
    """Canonical, digest-bound external evidence for one venue fact; ``citation_digest`` covers every other field."""

    fact_id: HistoricalExecutionFactId
    instrument: str
    cited_value: str
    citation_kind: HistoricalExecutionCitationKind
    citation_reference: str
    evidence_digest: str
    citation_digest: str


@dataclass(frozen=True)
class HistoricalExecutionEconomicsPolicy:
    """Immutable, digest-bound governed execution-economics policy. Historical evaluation only; proves no edge."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    instrument: str
    market_type: str
    contract_model_id: str
    quantity_semantics_id: str
    data_series_contract_id: str
    funding_data_key: str
    funding_value_name: str
    mark_data_key: str
    mark_value_name: str
    order_book_data_key: str
    best_bid_price_name: str
    best_ask_price_name: str
    best_bid_quantity_name: str
    best_ask_quantity_name: str
    required_revision_policy: str
    execution_timing_policy_id: str
    latency_tier_id: str
    latency_ns: int
    max_execution_delay_ns: int
    max_mark_staleness_ns: int
    fill_ratio_model_id: str
    visible_depth_cap_fraction: str
    max_spread_bps: str
    slippage_model_id: str
    slippage_floor_bps: str
    impact_model_id: str
    impact_coefficient_bps_per_participation_pct: str
    fee_model_id: str
    taker_fee_bps: str
    funding_model_id: str
    funding_liability_rule_id: str
    funding_interval_ns: int
    funding_notional_price_source_id: str
    funding_sign_convention_id: str
    same_timestamp_priority_id: str
    valuation_schedule_id: str
    terminal_rule_id: str
    divergence_rule_id: str
    leverage_rule_id: str
    initial_equity: str
    satisfies_fee_model_requirement: str
    satisfies_slippage_model_requirement: str
    satisfies_latency_sensitivity: str
    numeric_policy: HistoricalExecutionNumericPolicy
    conformance: HistoricalExecutionConformance
    external_fact_citations: tuple[HistoricalExecutionExternalFactCitation, ...]
    synthetic_test_facts_used: bool
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    policy_digest: str
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
    venue_facts_proven: bool = False
    production_values_approved: bool = False
    pbo_passed: bool = False
    stress_passed: bool = False
    performance_metrics_computed: bool = False


@dataclass(frozen=True)
class HistoricalExecutionEconomicsApproval:
    """Governance approval of one exact policy for one authenticated strategy, instrument and data context."""

    approval_reference: str
    approval_digest: str
    approval_kind: HistoricalExecutionApprovalKind
    approved_economics_policy_digest: str
    approved_strategy_spec_digest: str
    approved_instrument: str
    approved_market_type: str
    approved_data_requirement_registry_digest: str
    approved_quantity_semantics_id: str
    approved_execution_identity_digest: str
    approved_funding_identity_digest: str


HISTORICAL_EXECUTION_NUMERIC_POLICY_V1 = HistoricalExecutionNumericPolicy(
    numeric_policy_id="historical_execution_numeric_policy.v1",
    decimal_grammar_id="ascii_signed_canonical_integer_dot_fixed_scale_no_exponent_no_plus_no_negative_zero.v1",
    decimal_scale=18,
    max_decimal_text_length=60,
    integer_grammar_id="native_int_bounded_signed_int64.v1",
    max_wire_integer=9223372036854775807,
    arithmetic_id="exact_fraction_arithmetic.v1",
    amount_rounding_id="round_half_even",
    quantity_rounding_id="round_toward_zero",
    render_id="exact_integer_divmod_fixed_scale_render.v1",
)

HISTORICAL_EXECUTION_MAX_WIRE_INT = HISTORICAL_EXECUTION_NUMERIC_POLICY_V1.max_wire_integer
_SCALE = HISTORICAL_EXECUTION_NUMERIC_POLICY_V1.decimal_scale
_MAX_TEXT = HISTORICAL_EXECUTION_NUMERIC_POLICY_V1.max_decimal_text_length
_PRDV4_MIN_SLIPPAGE_FLOOR_BPS = Fraction(5)
_PRDV4_MAX_VISIBLE_DEPTH_CAP_FRACTION = Fraction(2, 100)


# --- numeric helpers (single source: HISTORICAL_EXECUTION_NUMERIC_POLICY_V1) -----------------------------------------


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def historical_execution_decimal_is_canonical(value: object) -> bool:
    """Canonical ASCII fixed-scale decimal within the representation-safety length of the v1 numeric policy."""

    if type(value) is not str or len(value) > _MAX_TEXT or not value.isascii():
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


def historical_execution_decimal(value: object) -> Fraction:
    """Exact value of a canonical decimal; raises for any non-canonical text."""

    if not historical_execution_decimal_is_canonical(value):
        raise HistoricalExecutionEconomicsPolicyError(f"{_REASON_PREFIX}:decimal_noncanonical")
    return Fraction(value)  # type: ignore[arg-type]


def _render_scaled(negative: bool, quotient: int) -> str | None:
    digits = str(quotient).rjust(_SCALE + 1, "0")
    rendered = f"{digits[:-_SCALE]}.{digits[-_SCALE:]}"
    if negative and quotient != 0:
        rendered = f"-{rendered}"
    return rendered if len(rendered) <= _MAX_TEXT else None


def historical_execution_render_amount(value: Fraction) -> str | None:
    """Exact ROUND_HALF_EVEN render at the v1 scale; ``None`` when the result exceeds the representation domain."""

    magnitude = abs(value)
    quotient, remainder = divmod(magnitude.numerator * 10**_SCALE, magnitude.denominator)
    twice = 2 * remainder
    if twice > magnitude.denominator or (twice == magnitude.denominator and quotient % 2 == 1):
        quotient += 1
    return _render_scaled(value < 0, quotient)


def historical_execution_render_quantity(value: Fraction) -> str | None:
    """Render truncated toward zero at the v1 scale (never exceeds the exact quantity); ``None`` when unrepresentable."""

    magnitude = abs(value)
    quotient = (magnitude.numerator * 10**_SCALE) // magnitude.denominator
    return _render_scaled(value < 0, quotient)


def historical_execution_wire_int_is_valid(value: object, *, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= HISTORICAL_EXECUTION_MAX_WIRE_INT


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalExecutionEconomicsPolicyError:
    return HistoricalExecutionEconomicsPolicyError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_instrument(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=minimum):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_decimal(value: object, field_name: str) -> tuple[str, Fraction]:
    if not historical_execution_decimal_is_canonical(value):
        raise _fail(f"{field_name}_invalid")
    return value, Fraction(value)  # type: ignore[arg-type,return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise _fail(f"{field_name}_invalid")


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


HISTORICAL_EXECUTION_CONFORMANCE_V1 = HistoricalExecutionConformance(
    same_observation_fill_prohibited=True,
    fill_ratio_model_enforced=True,
    zero_slippage_prohibited=True,
    positive_latency_enforced=True,
    visible_depth_cap_enforced=True,
    time_varying_spread_enforced=True,
    actual_final_funding_stream_required=True,
    almgren_chriss_modeled=False,
    maker_rebate_modeled=False,
    lot_tick_rounding_modeled=False,
    margin_liquidation_modeled=False,
    inverse_contract_modeled=False,
    prdv4_min_slippage_floor_bps=historical_execution_render_amount(_PRDV4_MIN_SLIPPAGE_FLOOR_BPS),  # type: ignore[arg-type]
    prdv4_max_visible_depth_cap_fraction=historical_execution_render_amount(  # type: ignore[arg-type]
        _PRDV4_MAX_VISIBLE_DEPTH_CAP_FRACTION
    ),
)


# --- external fact citations ----------------------------------------------------------------------------------------


def _canonical_citation_body(citation: object) -> HistoricalExecutionExternalFactCitation:
    if type(citation) is not HistoricalExecutionExternalFactCitation:
        raise _fail("external_fact_citation_malformed")
    return HistoricalExecutionExternalFactCitation(
        fact_id=_require_member(getattr(citation, "fact_id", None), HistoricalExecutionFactId, "citation_fact_id"),  # type: ignore[arg-type]
        instrument=_require_instrument(getattr(citation, "instrument", None), "citation_instrument"),
        cited_value=_require_text(getattr(citation, "cited_value", None), "citation_cited_value"),
        citation_kind=_require_member(  # type: ignore[arg-type]
            getattr(citation, "citation_kind", None), HistoricalExecutionCitationKind, "citation_kind"
        ),
        citation_reference=_require_text(getattr(citation, "citation_reference", None), "citation_reference"),
        evidence_digest=_require_hex64(getattr(citation, "evidence_digest", None), "citation_evidence_digest"),
        citation_digest="",
    )


def historical_execution_external_fact_citation_digest(citation: HistoricalExecutionExternalFactCitation) -> str:
    """Recompute a citation's canonical digest, excluding only ``citation_digest``."""

    return edge_payload_digest(_to_payload(citation), _CITATION_DIGEST_FIELD)


def build_historical_execution_external_fact_citation(
    *,
    fact_id: HistoricalExecutionFactId | str,
    instrument: str,
    cited_value: str,
    citation_kind: HistoricalExecutionCitationKind | str,
    citation_reference: str,
    evidence_digest: str,
) -> HistoricalExecutionExternalFactCitation:
    """Build one canonical citation whose ``citation_digest`` is computed here, never supplied."""

    body = _canonical_citation_body(
        HistoricalExecutionExternalFactCitation(
            fact_id=fact_id,  # type: ignore[arg-type]
            instrument=instrument,
            cited_value=cited_value,
            citation_kind=citation_kind,  # type: ignore[arg-type]
            citation_reference=citation_reference,
            evidence_digest=evidence_digest,
            citation_digest="",
        )
    )
    return replace(body, citation_digest=historical_execution_external_fact_citation_digest(body))


def _policy_fact_values(
    *,
    taker_fee_bps: str,
    funding_interval_ns: int,
) -> dict[HistoricalExecutionFactId, str]:
    return {
        HistoricalExecutionFactId.TAKER_FEE_BPS: taker_fee_bps,
        HistoricalExecutionFactId.FUNDING_INTERVAL_NS: str(funding_interval_ns),
        HistoricalExecutionFactId.FUNDING_LIABILITY_RULE: FUNDING_LIABILITY_RULE_V1,
        HistoricalExecutionFactId.FUNDING_NOTIONAL_PRICE_SOURCE: FUNDING_NOTIONAL_PRICE_SOURCE_V1,
        HistoricalExecutionFactId.FUNDING_SIGN_CONVENTION: FUNDING_SIGN_CONVENTION_V1,
        HistoricalExecutionFactId.CONTRACT_MODEL: CONTRACT_MODEL_V1,
        HistoricalExecutionFactId.QUANTITY_SEMANTICS: QUANTITY_SEMANTICS_V1,
        HistoricalExecutionFactId.ORDER_BOOK_TOP_OF_BOOK_SEMANTICS: DATA_SERIES_CONTRACT_V1,
    }


def historical_execution_cited_value(
    policy: HistoricalExecutionEconomicsPolicy, fact_id: HistoricalExecutionFactId
) -> str:
    """The exact policy value a citation for ``fact_id`` must cite."""

    return _policy_fact_values(taker_fee_bps=policy.taker_fee_bps, funding_interval_ns=policy.funding_interval_ns)[
        fact_id
    ]


# --- policy assembly ------------------------------------------------------------------------------------------------


def _canonical_citations(
    values: object,
) -> tuple[tuple[HistoricalExecutionExternalFactCitation, ...], list[str]]:
    if type(values) not in (tuple, list):
        raise _fail("external_fact_citations_malformed")
    canonical: dict[str, HistoricalExecutionExternalFactCitation] = {}
    integrity: list[str] = []
    for item in values:  # type: ignore[union-attr]
        body = _canonical_citation_body(item)
        carried = getattr(item, "citation_digest", None)
        if not edge_is_hex64(carried):
            raise _fail("external_fact_citation_digest_invalid")
        if body.fact_id.value in canonical:
            raise _fail(f"external_fact_citation_duplicate:{body.fact_id.value}")
        if carried != historical_execution_external_fact_citation_digest(body):
            integrity.append(_reason(f"external_fact_citation_digest_mismatch:{body.fact_id.value}"))
        canonical[body.fact_id.value] = replace(body, citation_digest=carried)  # type: ignore[arg-type]
    return tuple(canonical[key] for key in sorted(canonical)), integrity


def _assemble_policy(
    *,
    policy_id: object,
    policy_version: object,
    instrument: object,
    market_type: object,
    latency_tier_id: object,
    latency_ns: object,
    max_execution_delay_ns: object,
    max_mark_staleness_ns: object,
    visible_depth_cap_fraction: object,
    max_spread_bps: object,
    slippage_floor_bps: object,
    impact_coefficient_bps_per_participation_pct: object,
    taker_fee_bps: object,
    funding_interval_ns: object,
    initial_equity: object,
    satisfies_fee_model_requirement: object,
    satisfies_slippage_model_requirement: object,
    satisfies_latency_sensitivity: object,
    external_fact_citations: object,
) -> HistoricalExecutionEconomicsPolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    policy_id = _require_text(policy_id, "policy_id")
    policy_version = _require_text(policy_version, "policy_version")
    instrument = _require_instrument(instrument, "instrument")
    if type(market_type) is not str or market_type != MARKET_TYPE_USDT_PERP:
        raise _fail("market_type_unsupported_for_economics_v1")
    if latency_tier_id != LATENCY_TIER_PRDV4_T1:
        raise _fail("latency_tier_unsupported")
    latency = _require_int(latency_ns, "latency_ns", minimum=1)
    max_delay = _require_int(max_execution_delay_ns, "max_execution_delay_ns", minimum=latency)
    staleness = _require_int(max_mark_staleness_ns, "max_mark_staleness_ns", minimum=1)
    interval = _require_int(funding_interval_ns, "funding_interval_ns", minimum=1)
    depth_cap_text, depth_cap = _require_decimal(visible_depth_cap_fraction, "visible_depth_cap_fraction")
    if depth_cap <= 0:
        raise _fail("visible_depth_cap_fraction_invalid")
    if depth_cap > _PRDV4_MAX_VISIBLE_DEPTH_CAP_FRACTION:
        raise _fail("visible_depth_cap_exceeds_prdv4_bound")
    spread_text, spread = _require_decimal(max_spread_bps, "max_spread_bps")
    if spread <= 0:
        raise _fail("max_spread_bps_invalid")
    floor_text, floor = _require_decimal(slippage_floor_bps, "slippage_floor_bps")
    if floor < _PRDV4_MIN_SLIPPAGE_FLOOR_BPS:
        raise _fail("slippage_floor_below_prdv4_minimum")
    impact_text, impact = _require_decimal(
        impact_coefficient_bps_per_participation_pct, "impact_coefficient_bps_per_participation_pct"
    )
    if impact < 0:
        raise _fail("impact_coefficient_bps_per_participation_pct_invalid")
    fee_text, fee = _require_decimal(taker_fee_bps, "taker_fee_bps")
    if fee < 0:
        raise _fail("taker_fee_bps_invalid")
    equity_text, equity = _require_decimal(initial_equity, "initial_equity")
    if equity <= 0:
        raise _fail("initial_equity_invalid")
    fee_requirement = _require_text(satisfies_fee_model_requirement, "satisfies_fee_model_requirement")
    slippage_requirement = _require_text(satisfies_slippage_model_requirement, "satisfies_slippage_model_requirement")
    latency_requirement = _require_text(satisfies_latency_sensitivity, "satisfies_latency_sensitivity")
    citations, integrity = _canonical_citations(external_fact_citations)

    needs_external: list[str] = []
    by_fact = {citation.fact_id: citation for citation in citations}
    for fact_id, expected in _policy_fact_values(taker_fee_bps=fee_text, funding_interval_ns=interval).items():
        citation = by_fact.get(fact_id)
        if citation is None:
            needs_external.append(_reason(f"external_fact_missing:{fact_id.value}"))
        elif citation.instrument != instrument:
            needs_external.append(_reason(f"external_fact_instrument_mismatch:{fact_id.value}"))
        elif citation.cited_value != expected:
            needs_external.append(_reason(f"external_fact_value_mismatch:{fact_id.value}"))
    integrity_codes = _sorted_unique(integrity)
    if integrity_codes:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict([], needs_external, [])
        verdict_reasons = _sorted_unique(needs_external)

    seed = HistoricalExecutionEconomicsPolicy(
        schema_version=_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        policy_id=policy_id,
        policy_version=policy_version,
        instrument=instrument,
        market_type=MARKET_TYPE_USDT_PERP,
        contract_model_id=CONTRACT_MODEL_V1,
        quantity_semantics_id=QUANTITY_SEMANTICS_V1,
        data_series_contract_id=DATA_SERIES_CONTRACT_V1,
        funding_data_key=FUNDING_DATA_KEY,
        funding_value_name=FUNDING_VALUE_NAME,
        mark_data_key=MARK_DATA_KEY,
        mark_value_name=MARK_VALUE_NAME,
        order_book_data_key=ORDER_BOOK_DATA_KEY,
        best_bid_price_name=BEST_BID_PRICE_NAME,
        best_ask_price_name=BEST_ASK_PRICE_NAME,
        best_bid_quantity_name=BEST_BID_QUANTITY_NAME,
        best_ask_quantity_name=BEST_ASK_QUANTITY_NAME,
        required_revision_policy=REQUIRED_REVISION_POLICY,
        execution_timing_policy_id=EXECUTION_TIMING_POLICY_V1,
        latency_tier_id=LATENCY_TIER_PRDV4_T1,
        latency_ns=latency,
        max_execution_delay_ns=max_delay,
        max_mark_staleness_ns=staleness,
        fill_ratio_model_id=FILL_RATIO_MODEL_V1,
        visible_depth_cap_fraction=depth_cap_text,
        max_spread_bps=spread_text,
        slippage_model_id=SLIPPAGE_MODEL_V1,
        slippage_floor_bps=floor_text,
        impact_model_id=IMPACT_MODEL_V1,
        impact_coefficient_bps_per_participation_pct=impact_text,
        fee_model_id=FEE_MODEL_V1,
        taker_fee_bps=fee_text,
        funding_model_id=FUNDING_MODEL_V1,
        funding_liability_rule_id=FUNDING_LIABILITY_RULE_V1,
        funding_interval_ns=interval,
        funding_notional_price_source_id=FUNDING_NOTIONAL_PRICE_SOURCE_V1,
        funding_sign_convention_id=FUNDING_SIGN_CONVENTION_V1,
        same_timestamp_priority_id=SAME_TIMESTAMP_PRIORITY_V1,
        valuation_schedule_id=VALUATION_SCHEDULE_V1,
        terminal_rule_id=TERMINAL_RULE_V1,
        divergence_rule_id=DIVERGENCE_RULE_V1,
        leverage_rule_id=LEVERAGE_RULE_V1,
        initial_equity=equity_text,
        satisfies_fee_model_requirement=fee_requirement,
        satisfies_slippage_model_requirement=slippage_requirement,
        satisfies_latency_sensitivity=latency_requirement,
        numeric_policy=HISTORICAL_EXECUTION_NUMERIC_POLICY_V1,
        conformance=HISTORICAL_EXECUTION_CONFORMANCE_V1,
        external_fact_citations=citations,
        synthetic_test_facts_used=any(
            citation.citation_kind is HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC for citation in citations
        ),
        integrity_reason_codes=integrity_codes,
        verdict_reason_codes=verdict_reasons,
        policy_digest="",
    )
    return replace(seed, policy_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_historical_execution_economics_policy(
    *,
    policy_id: str,
    policy_version: str,
    instrument: str,
    market_type: str,
    latency_tier_id: str,
    latency_ns: int,
    max_execution_delay_ns: int,
    max_mark_staleness_ns: int,
    visible_depth_cap_fraction: str,
    max_spread_bps: str,
    slippage_floor_bps: str,
    impact_coefficient_bps_per_participation_pct: str,
    taker_fee_bps: str,
    funding_interval_ns: int,
    initial_equity: str,
    satisfies_fee_model_requirement: str,
    satisfies_slippage_model_requirement: str,
    satisfies_latency_sensitivity: str,
    external_fact_citations: Sequence[HistoricalExecutionExternalFactCitation],
) -> HistoricalExecutionEconomicsPolicy:
    """Build a governed execution-economics policy; every governed value is explicit (there are no defaults).

    Malformed input, an unsupported scope or a PRDV4 §12.2 prohibited assumption raises
    ``HistoricalExecutionEconomicsPolicyError``. A tampered citation yields ``REJECTED``; a missing, foreign or
    non-matching citation yields ``READY`` + ``NEEDS_EXTERNAL_FACTS``; a fully cited policy is ``READY`` + ``PASS``.
    """

    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        instrument=instrument,
        market_type=market_type,
        latency_tier_id=latency_tier_id,
        latency_ns=latency_ns,
        max_execution_delay_ns=max_execution_delay_ns,
        max_mark_staleness_ns=max_mark_staleness_ns,
        visible_depth_cap_fraction=visible_depth_cap_fraction,
        max_spread_bps=max_spread_bps,
        slippage_floor_bps=slippage_floor_bps,
        impact_coefficient_bps_per_participation_pct=impact_coefficient_bps_per_participation_pct,
        taker_fee_bps=taker_fee_bps,
        funding_interval_ns=funding_interval_ns,
        initial_equity=initial_equity,
        satisfies_fee_model_requirement=satisfies_fee_model_requirement,
        satisfies_slippage_model_requirement=satisfies_slippage_model_requirement,
        satisfies_latency_sensitivity=satisfies_latency_sensitivity,
        external_fact_citations=external_fact_citations,
    )


def historical_execution_economics_policy_to_dict(policy: HistoricalExecutionEconomicsPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def historical_execution_economics_policy_digest(policy: HistoricalExecutionEconomicsPolicy) -> str:
    """Recompute the canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


def historical_execution_policy_identity_digests(policy: HistoricalExecutionEconomicsPolicy) -> tuple[str, str]:
    """``(execution_identity_digest, funding_identity_digest)`` over the committed model and rule identities."""

    execution = edge_sha256_text(edge_canonical_json([getattr(policy, name) for name in _EXECUTION_IDENTITY_FIELDS]))
    funding = edge_sha256_text(edge_canonical_json([getattr(policy, name) for name in _FUNDING_IDENTITY_FIELDS]))
    return execution, funding


# --- strict parsing -------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_decimal(value: object) -> str:
    if not historical_execution_decimal_is_canonical(value):
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


def _as_nested(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return _parse_exact(cls, value, converters)

    return convert


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


_NUMERIC_CONVERTERS: dict[str, Callable[[object], object]] = {
    "decimal_scale": _as_int,
    "max_decimal_text_length": _as_int,
    "max_wire_integer": _as_int,
}
_CONFORMANCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    **{field.name: _as_bool for field in fields(HistoricalExecutionConformance) if field.type in ("bool", bool)},
    "prdv4_min_slippage_floor_bps": _as_decimal,
    "prdv4_max_visible_depth_cap_fraction": _as_decimal,
}
_CITATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "fact_id": _as_enum(HistoricalExecutionFactId),
    "citation_kind": _as_enum(HistoricalExecutionCitationKind),
}
_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "latency_ns": _as_int,
    "max_execution_delay_ns": _as_int,
    "max_mark_staleness_ns": _as_int,
    "funding_interval_ns": _as_int,
    "visible_depth_cap_fraction": _as_decimal,
    "max_spread_bps": _as_decimal,
    "slippage_floor_bps": _as_decimal,
    "impact_coefficient_bps_per_participation_pct": _as_decimal,
    "taker_fee_bps": _as_decimal,
    "initial_equity": _as_decimal,
    "numeric_policy": _as_nested(HistoricalExecutionNumericPolicy, _NUMERIC_CONVERTERS),
    "conformance": _as_nested(HistoricalExecutionConformance, _CONFORMANCE_CONVERTERS),
    "external_fact_citations": _as_records(HistoricalExecutionExternalFactCitation, _CITATION_CONVERTERS),
    "synthetic_test_facts_used": _as_bool,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def historical_execution_economics_policy_from_payload(payload: object) -> HistoricalExecutionEconomicsPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(HistoricalExecutionEconomicsPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def historical_execution_economics_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        historical_execution_economics_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> HistoricalExecutionEconomicsPolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        instrument=policy.instrument,  # type: ignore[attr-defined]
        market_type=policy.market_type,  # type: ignore[attr-defined]
        latency_tier_id=policy.latency_tier_id,  # type: ignore[attr-defined]
        latency_ns=policy.latency_ns,  # type: ignore[attr-defined]
        max_execution_delay_ns=policy.max_execution_delay_ns,  # type: ignore[attr-defined]
        max_mark_staleness_ns=policy.max_mark_staleness_ns,  # type: ignore[attr-defined]
        visible_depth_cap_fraction=policy.visible_depth_cap_fraction,  # type: ignore[attr-defined]
        max_spread_bps=policy.max_spread_bps,  # type: ignore[attr-defined]
        slippage_floor_bps=policy.slippage_floor_bps,  # type: ignore[attr-defined]
        impact_coefficient_bps_per_participation_pct=policy.impact_coefficient_bps_per_participation_pct,  # type: ignore[attr-defined]
        taker_fee_bps=policy.taker_fee_bps,  # type: ignore[attr-defined]
        funding_interval_ns=policy.funding_interval_ns,  # type: ignore[attr-defined]
        initial_equity=policy.initial_equity,  # type: ignore[attr-defined]
        satisfies_fee_model_requirement=policy.satisfies_fee_model_requirement,  # type: ignore[attr-defined]
        satisfies_slippage_model_requirement=policy.satisfies_slippage_model_requirement,  # type: ignore[attr-defined]
        satisfies_latency_sensitivity=policy.satisfies_latency_sensitivity,  # type: ignore[attr-defined]
        external_fact_citations=policy.external_fact_citations,  # type: ignore[attr-defined]
    )


def verify_historical_execution_economics_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy by strict parse, citation re-digest and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=HistoricalExecutionEconomicsPolicy,
        to_payload=_to_payload,
        parse_payload=historical_execution_economics_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


# --- governance approval --------------------------------------------------------------------------------------------


def canonical_historical_execution_economics_approval(
    approval: object,
) -> HistoricalExecutionEconomicsApproval | None:
    """Structurally validate an approval (``None`` stays ``None``); raises on any malformed state.

    Structural only: whether the approval MATCHES a policy, strategy and data context is decided by its consumer.
    """

    if approval is None:
        return None
    if type(approval) is not HistoricalExecutionEconomicsApproval:
        raise _fail("economics_approval_malformed")
    return HistoricalExecutionEconomicsApproval(
        approval_reference=_require_text(getattr(approval, "approval_reference", None), "approval_reference"),
        approval_digest=_require_hex64(getattr(approval, "approval_digest", None), "approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            getattr(approval, "approval_kind", None), HistoricalExecutionApprovalKind, "approval_kind"
        ),
        approved_economics_policy_digest=_require_hex64(
            getattr(approval, "approved_economics_policy_digest", None), "approved_economics_policy_digest"
        ),
        approved_strategy_spec_digest=_require_hex64(
            getattr(approval, "approved_strategy_spec_digest", None), "approved_strategy_spec_digest"
        ),
        approved_instrument=_require_instrument(getattr(approval, "approved_instrument", None), "approved_instrument"),
        approved_market_type=_require_text(getattr(approval, "approved_market_type", None), "approved_market_type"),
        approved_data_requirement_registry_digest=_require_hex64(
            getattr(approval, "approved_data_requirement_registry_digest", None),
            "approved_data_requirement_registry_digest",
        ),
        approved_quantity_semantics_id=_require_text(
            getattr(approval, "approved_quantity_semantics_id", None), "approved_quantity_semantics_id"
        ),
        approved_execution_identity_digest=_require_hex64(
            getattr(approval, "approved_execution_identity_digest", None), "approved_execution_identity_digest"
        ),
        approved_funding_identity_digest=_require_hex64(
            getattr(approval, "approved_funding_identity_digest", None), "approved_funding_identity_digest"
        ),
    )


def historical_execution_economics_approval_mismatches(
    approval: HistoricalExecutionEconomicsApproval,
    *,
    policy: HistoricalExecutionEconomicsPolicy,
    strategy_spec_digest: str,
    instrument: str,
    market_type: str,
    data_requirement_registry_digest: str,
) -> tuple[str, ...]:
    """Names of approval fields that do not match the exact policy and authenticated context (sorted)."""

    execution_identity, funding_identity = historical_execution_policy_identity_digests(policy)
    expected = {
        "approved_economics_policy_digest": policy.policy_digest,
        "approved_strategy_spec_digest": strategy_spec_digest,
        "approved_instrument": instrument,
        "approved_market_type": market_type,
        "approved_data_requirement_registry_digest": data_requirement_registry_digest,
        "approved_quantity_semantics_id": policy.quantity_semantics_id,
        "approved_execution_identity_digest": execution_identity,
        "approved_funding_identity_digest": funding_identity,
    }
    return tuple(sorted(name for name, value in expected.items() if getattr(approval, name) != value))


__all__ = [
    "BEST_ASK_PRICE_NAME",
    "BEST_ASK_QUANTITY_NAME",
    "BEST_BID_PRICE_NAME",
    "BEST_BID_QUANTITY_NAME",
    "CONTRACT_MODEL_V1",
    "DATA_SERIES_CONTRACT_V1",
    "DIVERGENCE_RULE_V1",
    "EXECUTION_TIMING_POLICY_V1",
    "FEE_MODEL_V1",
    "FILL_RATIO_MODEL_V1",
    "FUNDING_DATA_KEY",
    "FUNDING_LIABILITY_RULE_V1",
    "FUNDING_MODEL_V1",
    "FUNDING_NOTIONAL_PRICE_SOURCE_V1",
    "FUNDING_SIGN_CONVENTION_V1",
    "FUNDING_VALUE_NAME",
    "HISTORICAL_EXECUTION_CONFORMANCE_V1",
    "HISTORICAL_EXECUTION_MAX_WIRE_INT",
    "HISTORICAL_EXECUTION_NUMERIC_POLICY_V1",
    "HISTORICAL_EXECUTION_POLICY_NON_CLAIM_FLAGS",
    "IMPACT_MODEL_V1",
    "LATENCY_TIER_PRDV4_T1",
    "LEVERAGE_RULE_V1",
    "MARKET_TYPE_USDT_PERP",
    "MARK_DATA_KEY",
    "MARK_VALUE_NAME",
    "ORDER_BOOK_DATA_KEY",
    "QUANTITY_SEMANTICS_V1",
    "REQUIRED_REVISION_POLICY",
    "SAME_TIMESTAMP_PRIORITY_V1",
    "SLIPPAGE_MODEL_V1",
    "TERMINAL_RULE_V1",
    "VALUATION_SCHEDULE_V1",
    "HistoricalExecutionApprovalKind",
    "HistoricalExecutionCitationKind",
    "HistoricalExecutionConformance",
    "HistoricalExecutionEconomicsApproval",
    "HistoricalExecutionEconomicsPolicy",
    "HistoricalExecutionEconomicsPolicyError",
    "HistoricalExecutionExternalFactCitation",
    "HistoricalExecutionFactId",
    "HistoricalExecutionNumericPolicy",
    "build_historical_execution_economics_policy",
    "build_historical_execution_external_fact_citation",
    "canonical_historical_execution_economics_approval",
    "historical_execution_cited_value",
    "historical_execution_decimal",
    "historical_execution_decimal_is_canonical",
    "historical_execution_economics_approval_mismatches",
    "historical_execution_economics_policy_digest",
    "historical_execution_economics_policy_from_payload",
    "historical_execution_economics_policy_payload_is_well_formed",
    "historical_execution_economics_policy_to_dict",
    "historical_execution_external_fact_citation_digest",
    "historical_execution_policy_identity_digests",
    "historical_execution_render_amount",
    "historical_execution_render_quantity",
    "historical_execution_wire_int_is_valid",
    "verify_historical_execution_economics_policy",
]
