"""Tests for the closed executable profile registry (DETERMINISTIC_HISTORICAL_SIGNAL_SPINE_V1, contract B + H1)."""

from __future__ import annotations

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
