"""Closed, code-defined registry of executable strategy profiles for deterministic historical evaluation.

A ``StrategyExecutableProfile`` is the only executable authority a historical decision run may use. Profiles exist
only as module constants here: there is no dynamic import, plugin loading, entry point, ``eval``/``exec`` or caller
callable, and a profile is looked up by id through a closed mapping. Each profile declares its implementation
identifier, required PIT data semantics, parameter schema and constraints, structured semantic elements, decision
schedule and state rule; ``profile_semantics_digest`` is recomputed from those code-defined constants and can never be
chosen by a caller.

The first and only profile, ``passive_funding_carry.v1``, implements the human-authorized H1 rule structure over final
funding settlements of one instrument with the H2 decision schedule ``max(available_at_ns, finalized_at_ns)``:

* fewer than N visible final funding rates → ``NO_ACTION`` (direction unchanged);
* the exact arithmetic mean of the last N final rates drives the decision (compared exactly, recorded as an
  18-place ``ROUND_HALF_EVEN`` decimal);
* when flat: mean > entry_threshold → ``SHORT``; mean < −entry_threshold → ``LONG``; otherwise ``NO_ACTION``;
* when positioned: a sign flip (SHORT with mean < 0, LONG with mean > 0) or |mean| < exit_threshold → ``EXIT``;
  otherwise ``HOLD``. EXIT takes precedence and an opposite entry can only occur at a later decision instant.

Every numeric value comes from the exact governed parameter assignment; the profile has no production defaults. These
semantics are deterministic historical-evaluation mechanics only: they prove no edge, profitability or readiness.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)

PASSIVE_FUNDING_CARRY_V1 = "passive_funding_carry.v1"

_REASON_PREFIX = "strategy_executable_profile"
_SELF_DIGEST_FIELD = "profile_semantics_digest"
_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{18}")
_CANONICAL_POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*")
_NEGATIVE_ZERO = "-0.000000000000000000"
_ZERO = "0.000000000000000000"
_MEAN_PRECISION = 80
_MEAN_QUANTUM = Decimal("0.000000000000000001")


class StrategyExecutableProfileError(EdgeArtifactError):
    """Raised for an unknown profile, a malformed parameter assignment or malformed decision input."""


class ProfileSemanticElementKind(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    INVALIDATION = "invalidation"
    FEATURE = "feature"
    DATA_REQUIREMENT = "data_requirement"
    SIZING = "sizing"
    KILL_TRIGGER_SURFACE = "kill_trigger_surface"
    DECISION_SCHEDULE = "decision_schedule"
    STATE_RULE = "state_rule"


class ProfileParameterKind(str, Enum):
    POSITIVE_INTEGER = "positive_integer"
    POSITIVE_DECIMAL = "positive_decimal"
    NONNEGATIVE_DECIMAL = "nonnegative_decimal"


class ProfileDirection(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class ProfileAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class ProfileParameterSpec:
    parameter_id: str
    kind: ProfileParameterKind
    definition: str


@dataclass(frozen=True)
class ProfileSemanticElement:
    """One structured semantic element; load-bearing elements must be covered by a StrategySpec binding."""

    element_id: str
    kind: ProfileSemanticElementKind
    definition: str
    load_bearing: bool


@dataclass(frozen=True)
class StrategyExecutableProfile:
    """Code-defined executable profile; ``profile_semantics_digest`` covers every other field."""

    profile_id: str
    profile_version: str
    implementation_id: str
    required_data_requirement_keys: tuple[str, ...]
    required_value_names: tuple[str, ...]
    required_funding_semantics: str
    parameter_schema: tuple[ProfileParameterSpec, ...]
    parameter_constraints: tuple[str, ...]
    semantic_elements: tuple[ProfileSemanticElement, ...]
    decision_schedule_id: str
    state_rule_id: str
    profile_semantics_digest: str


@dataclass(frozen=True)
class ProfileParameterAssignment:
    """One governed parameter value as a canonical ASCII string (integer or 18-place decimal per schema)."""

    parameter_id: str
    value: str


@dataclass(frozen=True)
class ProfileDecision:
    """Deterministic profile output at one decision instant. Never an order, fill, price or PnL."""

    action: ProfileAction
    prior_direction: ProfileDirection
    resulting_direction: ProfileDirection
    target_units: str | None
    feature_mean: str | None
    used_observation_count: int
    reason: str


def _fail(code: str) -> StrategyExecutableProfileError:
    return StrategyExecutableProfileError(f"{_REASON_PREFIX}:{code}")


def _is_canonical_decimal(value: object) -> bool:
    return type(value) is str and _CANONICAL_DECIMAL.fullmatch(value) is not None and value != _NEGATIVE_ZERO


def _profile_payload(profile: StrategyExecutableProfile) -> dict[str, object]:
    def serialize(value: object) -> object:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return [serialize(item) for item in value]
        if isinstance(value, (ProfileParameterSpec, ProfileSemanticElement)):
            return {field.name: serialize(getattr(value, field.name)) for field in fields(value)}
        return value

    return {field.name: serialize(getattr(profile, field.name)) for field in fields(profile)}


def strategy_executable_profile_semantics_digest(profile: StrategyExecutableProfile) -> str:
    """Recompute a profile's semantics digest from its fields, excluding only ``profile_semantics_digest``."""

    return edge_payload_digest(_profile_payload(profile), _SELF_DIGEST_FIELD)


def strategy_executable_profile_to_dict(profile: StrategyExecutableProfile) -> dict[str, object]:
    """Canonical JSON-ready mapping of a profile, including its semantics digest."""

    return _profile_payload(profile)


def _sealed(profile: StrategyExecutableProfile) -> StrategyExecutableProfile:
    return replace(profile, profile_semantics_digest=strategy_executable_profile_semantics_digest(profile))


_PASSIVE_FUNDING_CARRY_DEFINITION = StrategyExecutableProfile(
    profile_id=PASSIVE_FUNDING_CARRY_V1,
    profile_version="1",
    implementation_id="crypto_core.validation.strategy_executable_profiles:_decide_passive_funding_carry_v1",
    required_data_requirement_keys=("funding_rate",),
    required_value_names=("funding_rate",),
    required_funding_semantics="final",
    parameter_schema=(
        ProfileParameterSpec(
            "entry_threshold",
            ProfileParameterKind.POSITIVE_DECIMAL,
            "Mean final funding rate magnitude strictly exceeded to enter.",
        ),
        ProfileParameterSpec(
            "exit_threshold",
            ProfileParameterKind.NONNEGATIVE_DECIMAL,
            "Absolute mean final funding rate strictly below which an open direction exits.",
        ),
        ProfileParameterSpec(
            "final_funding_lookback_count",
            ProfileParameterKind.POSITIVE_INTEGER,
            "N: number of most recent visible final funding rates averaged.",
        ),
        ProfileParameterSpec(
            "unit_size",
            ProfileParameterKind.POSITIVE_DECIMAL,
            "Target units for a LONG or SHORT decision.",
        ),
    ),
    parameter_constraints=("exit_threshold_lte_entry_threshold",),
    semantic_elements=(
        ProfileSemanticElement(
            "data_final_funding_settlements",
            ProfileSemanticElementKind.DATA_REQUIREMENT,
            "funding_rate series with final funding semantics for one instrument; a record is visible only when "
            "available_at_ns and finalized_at_ns are at or before the decision time.",
            True,
        ),
        ProfileSemanticElement(
            "entry_long_on_negative_mean",
            ProfileSemanticElementKind.ENTRY,
            "When flat, target LONG with unit_size units when the mean is strictly less than -entry_threshold.",
            True,
        ),
        ProfileSemanticElement(
            "entry_short_on_positive_mean",
            ProfileSemanticElementKind.ENTRY,
            "When flat, target SHORT with unit_size units when the mean is strictly greater than entry_threshold.",
            True,
        ),
        ProfileSemanticElement(
            "exit_below_exit_threshold",
            ProfileSemanticElementKind.EXIT,
            "When positioned, target EXIT when the absolute mean is strictly less than exit_threshold.",
            True,
        ),
        ProfileSemanticElement(
            "exit_on_sign_flip",
            ProfileSemanticElementKind.EXIT,
            "When SHORT and the mean is strictly negative, or LONG and the mean is strictly positive, target EXIT.",
            True,
        ),
        ProfileSemanticElement(
            "feature_mean_last_n_final_funding_rates",
            ProfileSemanticElementKind.FEATURE,
            "Exact arithmetic mean of the funding_rate values of the last N visible final funding records ordered "
            "by event time then sequence; recorded as an 18-place ROUND_HALF_EVEN decimal, compared exactly.",
            True,
        ),
        ProfileSemanticElement(
            "invalidation_insufficient_final_history",
            ProfileSemanticElementKind.INVALIDATION,
            "When fewer than N final funding rates are visible, take NO_ACTION and keep the current direction.",
            True,
        ),
        ProfileSemanticElement(
            "kill_triggers_not_evaluated_by_profile",
            ProfileSemanticElementKind.KILL_TRIGGER_SURFACE,
            "Kill criteria are not evaluated by this profile; mapped kill-switch triggers are accounted for by "
            "governance only and are enforced by a later lifecycle gate.",
            True,
        ),
        ProfileSemanticElement(
            "schedule_final_funding_max_available_finalized",
            ProfileSemanticElementKind.DECISION_SCHEDULE,
            "One decision per distinct max(available_at_ns, finalized_at_ns) of final funding records inside "
            "[start_ns, end_ns).",
            False,
        ),
        ProfileSemanticElement(
            "sizing_fixed_unit_size",
            ProfileSemanticElementKind.SIZING,
            "LONG and SHORT target exactly unit_size units; EXIT targets zero units; HOLD and NO_ACTION carry no "
            "target.",
            True,
        ),
        ProfileSemanticElement(
            "state_exit_precedes_reentry",
            ProfileSemanticElementKind.STATE_RULE,
            "Each run starts FLAT. When positioned, EXIT takes precedence and an opposite entry can only occur at a "
            "later decision instant; a positioned non-exit decision is HOLD and a flat non-entry decision is "
            "NO_ACTION.",
            False,
        ),
    ),
    decision_schedule_id="final_funding_record_max_available_finalized.v1",
    state_rule_id="exit_precedes_reentry_same_instant.v1",
    profile_semantics_digest="",
)

_REGISTRY: dict[str, StrategyExecutableProfile] = {PASSIVE_FUNDING_CARRY_V1: _sealed(_PASSIVE_FUNDING_CARRY_DEFINITION)}


def strategy_executable_profile_ids() -> tuple[str, ...]:
    """The closed set of registered profile ids."""

    return tuple(sorted(_REGISTRY))


def get_strategy_executable_profile(profile_id: object) -> StrategyExecutableProfile:
    """Return the code-defined profile for ``profile_id``; raises for any unregistered id."""

    if type(profile_id) is not str or profile_id not in _REGISTRY:
        raise _fail("profile_unknown")
    return _REGISTRY[profile_id]


def canonical_profile_parameter_assignment(
    profile: StrategyExecutableProfile, assignment: object
) -> tuple[ProfileParameterAssignment, ...]:
    """Validate an assignment against the profile schema and constraints; returns it ordered by parameter id."""

    if (
        type(profile) is not StrategyExecutableProfile
        or type(profile.profile_id) is not str
        or _REGISTRY.get(profile.profile_id) != profile
    ):
        raise _fail("profile_unregistered")
    if type(assignment) not in (tuple, list):
        raise _fail("parameter_assignment_malformed")
    schema = {spec.parameter_id: spec for spec in profile.parameter_schema}
    canonical: dict[str, ProfileParameterAssignment] = {}
    for item in assignment:  # type: ignore[union-attr]
        if type(item) is not ProfileParameterAssignment or type(item.parameter_id) is not str:
            raise _fail("parameter_assignment_entry_malformed")
        spec = schema.get(item.parameter_id)
        if spec is None:
            raise _fail(f"parameter_unknown:{item.parameter_id}")
        if item.parameter_id in canonical:
            raise _fail(f"parameter_duplicate:{item.parameter_id}")
        value = item.value
        if spec.kind is ProfileParameterKind.POSITIVE_INTEGER:
            valid = type(value) is str and _CANONICAL_POSITIVE_INTEGER.fullmatch(value) is not None
        elif spec.kind is ProfileParameterKind.POSITIVE_DECIMAL:
            valid = _is_canonical_decimal(value) and Decimal(value) > 0
        else:
            valid = _is_canonical_decimal(value) and Decimal(value) >= 0
        if not valid:
            raise _fail(f"parameter_value_invalid:{item.parameter_id}")
        canonical[item.parameter_id] = ProfileParameterAssignment(parameter_id=item.parameter_id, value=value)
    missing = sorted(set(schema) - set(canonical))
    if missing:
        raise _fail(f"parameter_missing:{missing[0]}")
    if "exit_threshold_lte_entry_threshold" in profile.parameter_constraints and Decimal(
        canonical["exit_threshold"].value
    ) > Decimal(canonical["entry_threshold"].value):
        raise _fail("parameter_constraint_violated:exit_threshold_lte_entry_threshold")
    return tuple(canonical[key] for key in sorted(canonical))


def profile_parameter_assignment_digest(assignment: Sequence[ProfileParameterAssignment]) -> str:
    """Canonical digest of an already-canonical parameter assignment."""

    return edge_sha256_text(
        edge_canonical_json([{"parameter_id": item.parameter_id, "value": item.value} for item in assignment])
    )


def _render_mean(mean: Fraction) -> str:
    with localcontext() as context:
        context.prec = _MEAN_PRECISION
        context.rounding = ROUND_HALF_EVEN
        rendered = format(
            (Decimal(mean.numerator) / Decimal(mean.denominator)).quantize(_MEAN_QUANTUM, rounding=ROUND_HALF_EVEN),
            "f",
        )
    return _ZERO if rendered == _NEGATIVE_ZERO else rendered


def _decide_passive_funding_carry_v1(
    final_funding_rates: Sequence[str],
    parameters: Mapping[str, str],
    prior_direction: ProfileDirection,
) -> ProfileDecision:
    lookback = int(parameters["final_funding_lookback_count"])
    entry = Fraction(parameters["entry_threshold"])
    exit_threshold = Fraction(parameters["exit_threshold"])
    unit_size = parameters["unit_size"]
    if len(final_funding_rates) < lookback:
        return ProfileDecision(
            action=ProfileAction.NO_ACTION,
            prior_direction=prior_direction,
            resulting_direction=prior_direction,
            target_units=None,
            feature_mean=None,
            used_observation_count=len(final_funding_rates),
            reason="invalidation_insufficient_final_history",
        )
    window = final_funding_rates[-lookback:]
    mean = sum((Fraction(rate) for rate in window), Fraction(0)) / lookback
    rendered = _render_mean(mean)
    if prior_direction is ProfileDirection.FLAT:
        if mean > entry:
            action, resulting, units, reason = (
                ProfileAction.SHORT,
                ProfileDirection.SHORT,
                unit_size,
                "entry_short_on_positive_mean",
            )
        elif mean < -entry:
            action, resulting, units, reason = (
                ProfileAction.LONG,
                ProfileDirection.LONG,
                unit_size,
                "entry_long_on_negative_mean",
            )
        else:
            action, resulting, units, reason = ProfileAction.NO_ACTION, ProfileDirection.FLAT, None, "no_entry_signal"
    else:
        sign_flip = (prior_direction is ProfileDirection.SHORT and mean < 0) or (
            prior_direction is ProfileDirection.LONG and mean > 0
        )
        if sign_flip:
            action, resulting, units, reason = ProfileAction.EXIT, ProfileDirection.FLAT, _ZERO, "exit_on_sign_flip"
        elif abs(mean) < exit_threshold:
            action, resulting, units, reason = (
                ProfileAction.EXIT,
                ProfileDirection.FLAT,
                _ZERO,
                "exit_below_exit_threshold",
            )
        else:
            action, resulting, units, reason = ProfileAction.HOLD, prior_direction, None, "hold_position"
    return ProfileDecision(
        action=action,
        prior_direction=prior_direction,
        resulting_direction=resulting,
        target_units=units,
        feature_mean=rendered,
        used_observation_count=lookback,
        reason=reason,
    )


_IMPLEMENTATIONS = {PASSIVE_FUNDING_CARRY_V1: _decide_passive_funding_carry_v1}


def evaluate_strategy_executable_profile(
    profile: StrategyExecutableProfile,
    *,
    final_funding_rates: Sequence[str],
    parameter_assignment: Sequence[ProfileParameterAssignment],
    prior_direction: ProfileDirection,
) -> ProfileDecision:
    """Run the registered implementation of ``profile`` over visible final funding rates (oldest first)."""

    assignment = canonical_profile_parameter_assignment(profile, parameter_assignment)
    if type(prior_direction) is not ProfileDirection:
        raise _fail("prior_direction_invalid")
    if type(final_funding_rates) not in (tuple, list) or not all(
        _is_canonical_decimal(rate) for rate in final_funding_rates
    ):
        raise _fail("final_funding_rates_malformed")
    implementation = _IMPLEMENTATIONS[profile.profile_id]
    return implementation(
        tuple(final_funding_rates), {item.parameter_id: item.value for item in assignment}, prior_direction
    )


__all__ = [
    "PASSIVE_FUNDING_CARRY_V1",
    "ProfileAction",
    "ProfileDecision",
    "ProfileDirection",
    "ProfileParameterAssignment",
    "ProfileParameterKind",
    "ProfileParameterSpec",
    "ProfileSemanticElement",
    "ProfileSemanticElementKind",
    "StrategyExecutableProfile",
    "StrategyExecutableProfileError",
    "canonical_profile_parameter_assignment",
    "evaluate_strategy_executable_profile",
    "get_strategy_executable_profile",
    "profile_parameter_assignment_digest",
    "strategy_executable_profile_ids",
    "strategy_executable_profile_semantics_digest",
    "strategy_executable_profile_to_dict",
]
