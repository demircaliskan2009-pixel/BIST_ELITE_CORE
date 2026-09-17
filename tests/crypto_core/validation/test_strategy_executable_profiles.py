"""Tests for the closed executable profile registry (DETERMINISTIC_HISTORICAL_SIGNAL_SPINE_V1, contract B + H1)."""

from __future__ import annotations

import decimal
import inspect
from dataclasses import replace

import pytest

import crypto_core.validation.strategy_executable_profiles as profiles_module
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    ProfileAction,
    ProfileDirection,
    ProfileParameterAssignment,
    ProfileParameterKind,
    ProfileSemanticElementKind,
    StrategyExecutableProfileError,
    canonical_profile_parameter_assignment,
    evaluate_strategy_executable_profile,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
    strategy_executable_profile_accepts_decimal,
    strategy_executable_profile_ids,
    strategy_executable_profile_semantics_digest,
    strategy_executable_profile_to_dict,
)
from tests.crypto_core.validation import test_historical_pit_dataset as support

_ZERO = "0.000000000000000000"
_UNIT = "1.000000000000000000"


def params(
    *, entry: str = "0.000100000000000000", exit_: str = "0.000050000000000000", n: str = "2", unit: str = _UNIT
) -> tuple[ProfileParameterAssignment, ...]:
    return (
        ProfileParameterAssignment("entry_threshold", entry),
        ProfileParameterAssignment("exit_threshold", exit_),
        ProfileParameterAssignment("final_funding_lookback_count", n),
        ProfileParameterAssignment("unit_size", unit),
    )


def _profile():
    return get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)


def _decide(rates: tuple[str, ...], prior: ProfileDirection = ProfileDirection.FLAT, **overrides: str):
    return evaluate_strategy_executable_profile(
        _profile(), final_funding_rates=rates, parameter_assignment=params(**overrides), prior_direction=prior
    )


# --- closed registry ----------------------------------------------------------------------------------------------------


def test_registry_is_closed_and_code_defined() -> None:
    assert strategy_executable_profile_ids() == (PASSIVE_FUNDING_CARRY_V1,)
    for unknown in ("passive_funding_carry.v2", "", None, 1, b"passive_funding_carry.v1", len, lambda: None):
        with pytest.raises(StrategyExecutableProfileError, match="profile_unknown"):
            get_strategy_executable_profile(unknown)
    assert get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1) is _profile()


def test_profile_binds_every_required_semantic_surface() -> None:
    profile = _profile()
    assert (profile.profile_id, profile.profile_version) == (PASSIVE_FUNDING_CARRY_V1, "1")
    assert profile.implementation_id.endswith(":_decide_passive_funding_carry_v1")
    assert profile.required_data_requirement_keys == ("funding_rate",)
    assert profile.required_value_names == ("funding_rate",)
    assert profile.required_funding_semantics == "final"
    assert {(spec.parameter_id, spec.kind) for spec in profile.parameter_schema} == {
        ("entry_threshold", ProfileParameterKind.POSITIVE_DECIMAL),
        ("exit_threshold", ProfileParameterKind.NONNEGATIVE_DECIMAL),
        ("final_funding_lookback_count", ProfileParameterKind.POSITIVE_INTEGER),
        ("unit_size", ProfileParameterKind.POSITIVE_DECIMAL),
    }
    assert profile.parameter_constraints == ("exit_threshold_lte_entry_threshold",)
    kinds = {element.element_id: (element.kind, element.load_bearing) for element in profile.semantic_elements}
    assert kinds == {
        "data_final_funding_settlements": (ProfileSemanticElementKind.DATA_REQUIREMENT, True),
        "entry_long_on_negative_mean": (ProfileSemanticElementKind.ENTRY, True),
        "entry_short_on_positive_mean": (ProfileSemanticElementKind.ENTRY, True),
        "exit_below_exit_threshold": (ProfileSemanticElementKind.EXIT, True),
        "exit_on_sign_flip": (ProfileSemanticElementKind.EXIT, True),
        "feature_mean_last_n_final_funding_rates": (ProfileSemanticElementKind.FEATURE, True),
        "invalidation_insufficient_final_history": (ProfileSemanticElementKind.INVALIDATION, True),
        "kill_triggers_not_evaluated_by_profile": (ProfileSemanticElementKind.KILL_TRIGGER_SURFACE, True),
        "schedule_final_funding_max_available_finalized": (ProfileSemanticElementKind.DECISION_SCHEDULE, False),
        "sizing_fixed_unit_size": (ProfileSemanticElementKind.SIZING, True),
        "state_exit_precedes_reentry": (ProfileSemanticElementKind.STATE_RULE, False),
    }
    assert profile.decision_schedule_id == "final_funding_record_max_available_finalized.v1"
    assert profile.state_rule_id == "exit_precedes_reentry_same_instant.v1"


def test_semantics_digest_is_recomputed_from_code_constants_and_covers_every_field() -> None:
    profile = _profile()
    assert profile.profile_semantics_digest == strategy_executable_profile_semantics_digest(profile)
    assert strategy_executable_profile_to_dict(profile)["profile_semantics_digest"] == profile.profile_semantics_digest
    entry = profile.semantic_elements[1]
    for changed in (
        replace(profile, profile_version="2"),
        replace(profile, required_funding_semantics="predicted"),
        replace(profile, decision_schedule_id="other.v1"),
        replace(profile, parameter_constraints=()),
        replace(profile, semantic_elements=(replace(entry, definition="changed"),) + profile.semantic_elements[2:]),
        replace(profile, semantic_elements=profile.semantic_elements[:-1]),
    ):
        assert strategy_executable_profile_semantics_digest(changed) != profile.profile_semantics_digest


def test_caller_profile_or_callable_can_never_execute() -> None:
    profile = _profile()
    forged = replace(profile, semantic_elements=profile.semantic_elements[:-1])
    resealed = replace(forged, profile_semantics_digest=strategy_executable_profile_semantics_digest(forged))
    for candidate in (forged, resealed, replace(profile, profile_id=["x"]), object(), None, lambda *a: None):  # type: ignore[arg-type]
        with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
            evaluate_strategy_executable_profile(
                candidate,  # type: ignore[arg-type]
                final_funding_rates=("0.000200000000000000",) * 2,
                parameter_assignment=params(),
                prior_direction=ProfileDirection.FLAT,
            )
    for function in (evaluate_strategy_executable_profile, canonical_profile_parameter_assignment):
        annotations = " ".join(str(p.annotation) for p in inspect.signature(function).parameters.values())
        assert "Callable" not in annotations
    assert set(profiles_module._IMPLEMENTATIONS) == set(strategy_executable_profile_ids())


# --- parameter assignment -----------------------------------------------------------------------------------------------


def test_parameter_assignment_is_canonical_and_order_insensitive() -> None:
    canonical = canonical_profile_parameter_assignment(_profile(), tuple(reversed(params())))
    assert canonical == params()
    assert profile_parameter_assignment_digest(canonical) == profile_parameter_assignment_digest(
        canonical_profile_parameter_assignment(_profile(), list(params()))
    )
    assert profile_parameter_assignment_digest(params(n="3")) != profile_parameter_assignment_digest(params())


@pytest.mark.parametrize(
    ("assignment", "code"),
    [
        (params()[:3], "parameter_missing:unit_size"),
        (params() + (ProfileParameterAssignment("leverage", "2"),), "parameter_unknown:leverage"),
        (params() + (params()[0],), "parameter_duplicate:entry_threshold"),
        (params(n="0"), "parameter_value_invalid:final_funding_lookback_count"),
        (params(n="02"), "parameter_value_invalid:final_funding_lookback_count"),
        (params(n="2.0"), "parameter_value_invalid:final_funding_lookback_count"),
        (params(n="２"), "parameter_value_invalid:final_funding_lookback_count"),
        (params(n=2), "parameter_value_invalid:final_funding_lookback_count"),  # type: ignore[arg-type]
        (params(n=True), "parameter_value_invalid:final_funding_lookback_count"),  # type: ignore[arg-type]
        (params(entry=_ZERO, exit_=_ZERO), "parameter_value_invalid:entry_threshold"),
        (params(entry="-0.000100000000000000"), "parameter_value_invalid:entry_threshold"),
        (params(entry="1e-4"), "parameter_value_invalid:entry_threshold"),
        (params(entry="+0.000100000000000000"), "parameter_value_invalid:entry_threshold"),
        (params(entry="NaN"), "parameter_value_invalid:entry_threshold"),
        (params(exit_="-0.000000000000000000"), "parameter_value_invalid:exit_threshold"),
        (params(exit_="-0.000010000000000000"), "parameter_value_invalid:exit_threshold"),
        (params(unit=_ZERO), "parameter_value_invalid:unit_size"),
        (params(unit=1.0), "parameter_value_invalid:unit_size"),  # type: ignore[arg-type]
        (params(exit_="0.000200000000000000"), "parameter_constraint_violated:exit_threshold_lte_entry_threshold"),
        (None, "parameter_assignment_malformed"),
        ({"entry_threshold": "0.000100000000000000"}, "parameter_assignment_malformed"),
        ((("entry_threshold", "0.000100000000000000"),), "parameter_assignment_entry_malformed"),
    ],
)
def test_invalid_parameter_assignments_raise(assignment: object, code: str) -> None:
    with pytest.raises(StrategyExecutableProfileError, match=code):
        canonical_profile_parameter_assignment(_profile(), assignment)


def test_zero_exit_threshold_and_equal_thresholds_are_allowed() -> None:
    assert canonical_profile_parameter_assignment(_profile(), params(exit_=_ZERO))
    assert canonical_profile_parameter_assignment(_profile(), params(exit_="0.000100000000000000"))


# --- H1 decision semantics ----------------------------------------------------------------------------------------------


def test_flat_positive_mean_above_entry_targets_short() -> None:
    decision = _decide(("0.000200000000000000", "0.000300000000000000"))
    assert (decision.action, decision.resulting_direction, decision.target_units) == (
        ProfileAction.SHORT,
        ProfileDirection.SHORT,
        _UNIT,
    )
    assert (decision.feature_mean, decision.used_observation_count, decision.reason) == (
        "0.000250000000000000",
        2,
        "entry_short_on_positive_mean",
    )


def test_flat_negative_mean_below_negative_entry_targets_long() -> None:
    decision = _decide(("-0.000200000000000000", "-0.000300000000000000"), unit="2.500000000000000000")
    assert (decision.action, decision.resulting_direction, decision.target_units, decision.reason) == (
        ProfileAction.LONG,
        ProfileDirection.LONG,
        "2.500000000000000000",
        "entry_long_on_negative_mean",
    )


def test_flat_inside_entry_band_is_no_action_and_thresholds_are_strict() -> None:
    at_entry = _decide(("0.000100000000000000", "0.000100000000000000"))
    at_negative_entry = _decide(("-0.000100000000000000", "-0.000100000000000000"))
    for decision in (at_entry, at_negative_entry):
        assert (decision.action, decision.resulting_direction, decision.target_units, decision.reason) == (
            ProfileAction.NO_ACTION,
            ProfileDirection.FLAT,
            None,
            "no_entry_signal",
        )
        assert decision.feature_mean is not None


def test_uses_only_the_last_n_rates() -> None:
    decision = _decide(("-0.009000000000000000", "0.000200000000000000", "0.000300000000000000"))
    assert decision.action is ProfileAction.SHORT
    assert decision.feature_mean == "0.000250000000000000"


def test_positioned_below_exit_threshold_exits_with_zero_target() -> None:
    decision = _decide(("0.000040000000000000", "0.000040000000000000"), ProfileDirection.SHORT)
    assert (decision.action, decision.resulting_direction, decision.target_units, decision.reason) == (
        ProfileAction.EXIT,
        ProfileDirection.FLAT,
        _ZERO,
        "exit_below_exit_threshold",
    )
    at_exit = _decide(("0.000050000000000000", "0.000050000000000000"), ProfileDirection.SHORT)
    assert at_exit.action is ProfileAction.HOLD


@pytest.mark.parametrize(
    ("prior", "rates"),
    [
        (ProfileDirection.SHORT, ("-0.000300000000000000", "-0.000300000000000000")),
        (ProfileDirection.LONG, ("0.000300000000000000", "0.000300000000000000")),
    ],
)
def test_sign_flip_exits_first_and_never_reverses_in_the_same_instant(
    prior: ProfileDirection, rates: tuple[str, ...]
) -> None:
    decision = _decide(rates, prior)
    assert (decision.action, decision.resulting_direction, decision.target_units, decision.reason) == (
        ProfileAction.EXIT,
        ProfileDirection.FLAT,
        _ZERO,
        "exit_on_sign_flip",
    )
    reentry = _decide(rates, decision.resulting_direction)
    assert reentry.action is (ProfileAction.LONG if prior is ProfileDirection.SHORT else ProfileAction.SHORT)


def test_positioned_same_sign_outside_exit_band_holds() -> None:
    for prior, rates in (
        (ProfileDirection.SHORT, ("0.000200000000000000", "0.000200000000000000")),
        (ProfileDirection.LONG, ("-0.000060000000000000", "-0.000060000000000000")),
    ):
        decision = _decide(rates, prior)
        assert (decision.action, decision.resulting_direction, decision.target_units, decision.reason) == (
            ProfileAction.HOLD,
            prior,
            None,
            "hold_position",
        )


def test_zero_mean_with_zero_exit_threshold_holds_without_inventing_a_flip() -> None:
    decision = _decide(("0.000100000000000000", "-0.000100000000000000"), ProfileDirection.SHORT, exit_=_ZERO)
    assert decision.action is ProfileAction.HOLD
    assert decision.feature_mean == _ZERO


@pytest.mark.parametrize("prior", list(ProfileDirection))
def test_insufficient_final_history_is_no_action_without_an_invented_signal(prior: ProfileDirection) -> None:
    for rates in ((), ("0.009000000000000000",)):
        decision = _decide(rates, prior)
        assert (decision.action, decision.resulting_direction, decision.target_units, decision.feature_mean) == (
            ProfileAction.NO_ACTION,
            prior,
            None,
            None,
        )
        assert decision.used_observation_count == len(rates)
        assert decision.reason == "invalidation_insufficient_final_history"


def test_decisions_compare_exactly_and_record_a_half_even_mean() -> None:
    tiny = "0.000000000000000001"
    decision = _decide((tiny, tiny, "0.000000000000000002"), entry=tiny, exit_=_ZERO, n="3")
    assert decision.action is ProfileAction.SHORT  # exact mean 4/3e-18 > 1e-18
    assert decision.feature_mean == tiny  # rendered mean equals the threshold; the decision did not use it
    half = _decide((tiny, _ZERO), entry=tiny, exit_=_ZERO)
    assert half.feature_mean == _ZERO  # 0.5e-18 rounds half-even to zero
    negative_half = _decide(("-0.000000000000000001", _ZERO), ProfileDirection.LONG, entry=tiny, exit_=_ZERO)
    assert negative_half.feature_mean == _ZERO  # never a negative zero
    assert negative_half.action is ProfileAction.HOLD  # exact mean < 0 is not a LONG sign flip


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"prior_direction": "FLAT"}, "prior_direction_invalid"),
        ({"prior_direction": None}, "prior_direction_invalid"),
        ({"final_funding_rates": ("0.0002", "0.000300000000000000")}, "final_funding_rates_malformed"),
        ({"final_funding_rates": ("-0.000000000000000000",) * 2}, "final_funding_rates_malformed"),
        ({"final_funding_rates": (0.0002, 0.0003)}, "final_funding_rates_malformed"),
        ({"final_funding_rates": iter(("0.000200000000000000",) * 2)}, "final_funding_rates_malformed"),
        ({"final_funding_rates": "0.000200000000000000"}, "final_funding_rates_malformed"),
        ({"parameter_assignment": params()[:2]}, "parameter_missing"),
    ],
)
def test_malformed_decision_input_raises(kwargs: dict[str, object], code: str) -> None:
    arguments: dict[str, object] = {
        "final_funding_rates": ("0.000200000000000000",) * 2,
        "parameter_assignment": params(),
        "prior_direction": ProfileDirection.FLAT,
    }
    arguments.update(kwargs)
    with pytest.raises(StrategyExecutableProfileError, match=code):
        evaluate_strategy_executable_profile(_profile(), **arguments)  # type: ignore[arg-type]


def test_evaluation_is_deterministic() -> None:
    rates = ("0.000200000000000000", "-0.000100000000000000", "0.000700000000000000")
    assert len({_decide(rates, ProfileDirection.LONG) for _ in range(5)}) == 1


# --- purity -------------------------------------------------------------------------------------------------------------


def test_module_is_pure_and_has_no_dynamic_execution_surface() -> None:
    support.assert_module_is_pure(profiles_module, {"crypto_core.validation.edge_artifact_core"})


# --- F1: scale-18 representation safety ---------------------------------------------------------------------------------

TINY = "0.000000000000000001"
MAX_POSITIVE_SCALE18 = "9" * 41 + "." + "9" * 18
MAX_NEGATIVE_SCALE18 = "-" + "9" * 40 + "." + "9" * 18
OVER_POSITIVE_SCALE18 = "1" * 42 + "." + "0" * 18
OVER_NEGATIVE_SCALE18 = "-" + "1" * 41 + "." + "0" * 18
EIGHTY_DIGIT_SCALE18 = "1" * 80 + "." + "0" * 18


def test_scale18_representation_boundary_is_exactly_sixty_characters() -> None:
    assert (len(MAX_POSITIVE_SCALE18), len(MAX_NEGATIVE_SCALE18)) == (60, 60)
    assert (len(OVER_POSITIVE_SCALE18), len(OVER_NEGATIVE_SCALE18)) == (61, 61)
    profile = _profile()
    for value in (MAX_POSITIVE_SCALE18, MAX_NEGATIVE_SCALE18, TINY):
        assert strategy_executable_profile_accepts_decimal(profile, value) is True
    for value in (OVER_POSITIVE_SCALE18, OVER_NEGATIVE_SCALE18, EIGHTY_DIGIT_SCALE18, "１.000000000000000000"):
        assert strategy_executable_profile_accepts_decimal(profile, value) is False


def test_every_accepted_boundary_value_is_safely_consumable() -> None:
    maximum = _decide((MAX_POSITIVE_SCALE18,) * 2, entry=TINY, exit_=_ZERO, unit=MAX_POSITIVE_SCALE18)
    assert (maximum.action, maximum.feature_mean, maximum.target_units) == (
        ProfileAction.SHORT,
        MAX_POSITIVE_SCALE18,
        MAX_POSITIVE_SCALE18,
    )
    minimum = _decide((MAX_NEGATIVE_SCALE18,) * 2, entry=TINY, exit_=_ZERO)
    assert (minimum.action, minimum.feature_mean) == (ProfileAction.LONG, MAX_NEGATIVE_SCALE18)
    mixed = _decide((MAX_POSITIVE_SCALE18, MAX_NEGATIVE_SCALE18), ProfileDirection.SHORT, entry=TINY, exit_=TINY)
    assert mixed.feature_mean == "45" + "0" * 39 + "." + "0" * 18
    assert mixed.action is ProfileAction.HOLD
    thresholds = _decide((MAX_NEGATIVE_SCALE18,) * 2, entry=MAX_POSITIVE_SCALE18, exit_=MAX_POSITIVE_SCALE18)
    assert thresholds.action is ProfileAction.NO_ACTION


@pytest.mark.parametrize("rate", [EIGHTY_DIGIT_SCALE18, OVER_POSITIVE_SCALE18, OVER_NEGATIVE_SCALE18])
def test_oversized_funding_rates_are_domain_errors(rate: str) -> None:
    with pytest.raises(StrategyExecutableProfileError, match="final_funding_rates_malformed"):
        _decide((rate,), n="1")


@pytest.mark.parametrize("oversized", [OVER_POSITIVE_SCALE18, EIGHTY_DIGIT_SCALE18])
@pytest.mark.parametrize(
    ("override", "parameter"),
    [
        ("entry", "entry_threshold"),
        ("exit_", "exit_threshold"),
        ("unit", "unit_size"),
    ],
)
def test_oversized_decimal_parameters_are_domain_errors(oversized: str, override: str, parameter: str) -> None:
    assignment = params(**{override: oversized})
    with pytest.raises(StrategyExecutableProfileError, match=f"parameter_value_invalid:{parameter}"):
        canonical_profile_parameter_assignment(_profile(), assignment)
    with pytest.raises(StrategyExecutableProfileError, match=f"parameter_value_invalid:{parameter}"):
        evaluate_strategy_executable_profile(
            _profile(),
            final_funding_rates=("0.000200000000000000",) * 2,
            parameter_assignment=assignment,
            prior_direction=ProfileDirection.FLAT,
        )


# --- F2: integer representation safety ----------------------------------------------------------------------------------

INT64_MAX_TEXT = "9223372036854775807"


@pytest.mark.parametrize(
    "lookback",
    ["1" * 4301, "9223372036854775808", "10000000000000000000", "9" * 20, "99999999999999999999999999"],
    ids=["4301_digits", "int64_max_plus_one", "twenty_digits_low", "twenty_nines", "twenty_six_digits"],
)
def test_oversized_lookback_is_a_domain_error_without_interpreter_limits(lookback: str) -> None:
    with pytest.raises(StrategyExecutableProfileError, match="parameter_value_invalid:final_funding_lookback_count"):
        canonical_profile_parameter_assignment(_profile(), params(n=lookback))
    with pytest.raises(StrategyExecutableProfileError, match="parameter_value_invalid:final_funding_lookback_count"):
        _decide(("0.000200000000000000",) * 3, n=lookback)


def test_int64_max_lookback_is_representation_valid_and_never_invents_a_signal() -> None:
    assert canonical_profile_parameter_assignment(_profile(), params(n=INT64_MAX_TEXT))
    decision = _decide(("0.000200000000000000",) * 3, ProfileDirection.SHORT, n=INT64_MAX_TEXT)
    assert (decision.action, decision.resulting_direction, decision.feature_mean, decision.used_observation_count) == (
        ProfileAction.NO_ACTION,
        ProfileDirection.SHORT,
        None,
        3,
    )


# --- F3: ambient Decimal context independence ---------------------------------------------------------------------------

_AMBIENT_CONTEXTS = {
    "default": lambda: decimal.Context(),
    "round_down": lambda: decimal.Context(rounding=decimal.ROUND_DOWN),
    "round_up_prec_2": lambda: decimal.Context(prec=2, rounding=decimal.ROUND_UP),
    "inexact_trap": lambda: decimal.Context(traps=[decimal.Inexact]),
    "rounded_trap": lambda: decimal.Context(traps=[decimal.Rounded]),
    "tight_exponents_all_traps": lambda: decimal.Context(
        prec=1,
        Emin=-1,
        Emax=1,
        traps=[
            decimal.Inexact,
            decimal.Rounded,
            decimal.Overflow,
            decimal.Underflow,
            decimal.Subnormal,
            decimal.Clamped,
            decimal.InvalidOperation,
        ],
    ),
}


def context_state(context: decimal.Context) -> tuple[object, ...]:
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple(sorted((signal.__name__, bool(enabled)) for signal, enabled in context.traps.items())),
        tuple(sorted((signal.__name__, bool(raised)) for signal, raised in context.flags.items())),
    )


def _astra_decision():
    return _decide((TINY, TINY, "0.000000000000000002"), entry=TINY, exit_=_ZERO, n="3")


@pytest.mark.parametrize("context_name", sorted(_AMBIENT_CONTEXTS))
def test_evaluation_is_independent_of_the_ambient_decimal_context(context_name: str) -> None:
    baseline = _astra_decision()
    assert (baseline.action, baseline.feature_mean) == (ProfileAction.SHORT, TINY)
    with decimal.localcontext(_AMBIENT_CONTEXTS[context_name]()) as active:
        before = context_state(active)
        assert _astra_decision() == baseline
        assert _decide(("-0.000000000000000005", _ZERO), entry=TINY, exit_=_ZERO).feature_mean == (
            "-0.000000000000000002"
        )
        assert context_state(decimal.getcontext()) == before
        assert decimal.getcontext() is active


@pytest.mark.parametrize(
    ("rates", "rendered"),
    [
        ((TINY, _ZERO), _ZERO),
        (("0.000000000000000003", _ZERO), "0.000000000000000002"),
        (("0.000000000000000005", _ZERO), "0.000000000000000002"),
        (("0.000000000000000007", _ZERO), "0.000000000000000004"),
        (("-0.000000000000000001", _ZERO), _ZERO),
        (("-0.000000000000000003", _ZERO), "-0.000000000000000002"),
        (("-0.000000000000000007", _ZERO), "-0.000000000000000004"),
        (("1.000000000000000001", "0.000000000000000000"), "0.500000000000000000"),
        (("1.000000000000000003", "0.000000000000000000"), "0.500000000000000002"),
    ],
)
def test_mean_rendering_is_exact_round_half_even(rates: tuple[str, str], rendered: str) -> None:
    assert _decide(rates, entry=TINY, exit_=_ZERO).feature_mean == rendered


# --- F4: numeric policy committed and consumed ---------------------------------------------------------------------------

POLICY_DRIFTS: list[dict[str, object]] = [
    {"numeric_policy_id": "passive_funding_carry_numeric_policy.v2"},
    {"decimal_grammar_id": "ascii_decimal_with_exponent.v1"},
    {"decimal_scale": 17},
    {"max_decimal_text_length": 59},
    {"integer_grammar_id": "ascii_positive_integer_unbounded.v1"},
    {"max_positive_integer": 2**31 - 1},
    {"mean_arithmetic_id": "binary_float_mean.v1"},
    {"mean_rounding_id": "round_half_up"},
    {"mean_output_scale": 8},
    {"mean_render_id": "decimal_context_quantize.v1"},
]


def _drifted(**changes: object):
    profile = _profile()
    changed = replace(profile, numeric_policy=replace(profile.numeric_policy, **changes))
    return replace(changed, profile_semantics_digest=strategy_executable_profile_semantics_digest(changed))


def test_numeric_policy_commits_every_load_bearing_rule() -> None:
    policy = _profile().numeric_policy
    assert strategy_executable_profile_to_dict(_profile())["numeric_policy"] == {
        "numeric_policy_id": "passive_funding_carry_numeric_policy.v1",
        "decimal_grammar_id": "ascii_signed_canonical_integer_dot_fixed_scale_no_exponent_no_plus_no_negative_zero.v1",
        "decimal_scale": 18,
        "max_decimal_text_length": 60,
        "integer_grammar_id": "ascii_positive_integer_no_leading_zero_lexically_bounded_int64.v1",
        "max_positive_integer": 9223372036854775807,
        "mean_arithmetic_id": "exact_fraction_arithmetic_mean.v1",
        "mean_rounding_id": "round_half_even",
        "mean_output_scale": 18,
        "mean_render_id": "exact_integer_divmod_fixed_scale_render.v1",
    }
    assert type(policy.max_positive_integer) is int
    assert _drifted().profile_semantics_digest == _profile().profile_semantics_digest
    assert strategy_executable_profile_semantics_digest(_profile()) == _profile().profile_semantics_digest
    source = inspect.getsource(profiles_module)
    assert "_MEAN_PRECISION" not in source
    assert "_MEAN_QUANTUM" not in source


@pytest.mark.parametrize("drift", POLICY_DRIFTS, ids=lambda drift: next(iter(drift)))
def test_every_numeric_policy_change_changes_the_semantics_digest(drift: dict[str, object]) -> None:
    assert _drifted(**drift).profile_semantics_digest != _profile().profile_semantics_digest


@pytest.mark.parametrize(
    "drift",
    [
        {"decimal_grammar_id": "ascii_decimal_with_exponent.v1"},
        {"integer_grammar_id": "ascii_positive_integer_unbounded.v1"},
        {"mean_arithmetic_id": "binary_float_mean.v1"},
        {"mean_rounding_id": "round_half_up"},
        {"mean_render_id": "decimal_context_quantize.v1"},
        {"decimal_scale": 0},
        {"max_positive_integer": 2**64},
    ],
    ids=lambda drift: next(iter(drift)),
)
def test_execution_refuses_an_unimplemented_numeric_policy(
    drift: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, _drifted(**drift))
    with pytest.raises(StrategyExecutableProfileError, match="numeric_policy_unsupported"):
        _decide(("0.000200000000000000",) * 2)


def test_execution_consumes_the_registered_policy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    sixty = "1" * 41 + "." + "0" * 18
    assert _decide((sixty, sixty)).action is ProfileAction.SHORT
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, _drifted(max_decimal_text_length=59))
    with pytest.raises(StrategyExecutableProfileError, match="final_funding_rates_malformed"):
        _decide((sixty, sixty))
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, _drifted(max_positive_integer=2**31 - 1))
    with pytest.raises(StrategyExecutableProfileError, match="parameter_value_invalid:final_funding_lookback_count"):
        _decide(("0.000200000000000000",) * 2, n="2147483648")
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, _drifted(mean_output_scale=2))
    assert _decide(("0.000200000000000000",) * 2).feature_mean == "0.00"


# --- F6: registry schema authority --------------------------------------------------------------------------------------


def _kind_aliased(kind: ProfileParameterKind):
    profile = _profile()
    schema = tuple(
        replace(spec, kind=spec.kind.value) if spec.kind is kind else spec for spec in profile.parameter_schema
    )
    return replace(profile, parameter_schema=schema)


@pytest.mark.parametrize("kind", list(ProfileParameterKind), ids=lambda kind: kind.value)
def test_plain_string_parameter_kind_alias_is_refused(kind: ProfileParameterKind) -> None:
    aliased = _kind_aliased(kind)
    assert aliased == _profile()  # equal-comparing: dataclass equality alone cannot be the authority
    assert strategy_executable_profile_semantics_digest(aliased) == _profile().profile_semantics_digest
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        canonical_profile_parameter_assignment(aliased, params())
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        evaluate_strategy_executable_profile(
            aliased,
            final_funding_rates=("0.000200000000000000",) * 2,
            parameter_assignment=params(),
            prior_direction=ProfileDirection.FLAT,
        )
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        strategy_executable_profile_accepts_decimal(aliased, TINY)


@pytest.mark.parametrize(
    ("kind", "assignment", "parameter"),
    [
        (ProfileParameterKind.POSITIVE_DECIMAL, params(unit=_ZERO), "unit_size"),
        (ProfileParameterKind.POSITIVE_DECIMAL, params(entry=_ZERO, exit_=_ZERO), "entry_threshold"),
        (ProfileParameterKind.POSITIVE_INTEGER, params(n="2.000000000000000000"), "final_funding_lookback_count"),
    ],
    ids=["unit_size_zero", "entry_threshold_zero", "decimal_lookback"],
)
def test_alias_widened_domains_are_rejected_and_registry_rejects_them_too(
    kind: ProfileParameterKind, assignment: tuple[ProfileParameterAssignment, ...], parameter: str
) -> None:
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        canonical_profile_parameter_assignment(_kind_aliased(kind), assignment)
    with pytest.raises(StrategyExecutableProfileError, match=f"parameter_value_invalid:{parameter}"):
        canonical_profile_parameter_assignment(_profile(), assignment)


def test_only_the_registered_object_is_authoritative() -> None:
    copy = replace(_profile())
    assert copy == _profile()
    assert copy is not _profile()
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        canonical_profile_parameter_assignment(copy, params())
    hollow = object.__new__(type(_profile()))
    with pytest.raises(StrategyExecutableProfileError, match="profile_unregistered"):
        canonical_profile_parameter_assignment(hollow, params())
    assert canonical_profile_parameter_assignment(_profile(), params()) == params()


@pytest.mark.parametrize("kind", ["positive_integer", "positive_decimal", "nonnegative_decimal", None])
def test_schema_dispatch_requires_the_exact_enum_type(kind: object) -> None:
    policy = _profile().numeric_policy
    with pytest.raises(StrategyExecutableProfileError, match="parameter_kind_invalid"):
        profiles_module._parameter_value_is_valid(policy, kind, "1.000000000000000000")
