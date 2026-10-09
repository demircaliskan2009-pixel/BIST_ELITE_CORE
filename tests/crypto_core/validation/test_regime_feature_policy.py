"""Tests for the RF-2 governed regime feature and label policy (``regime_feature_policy``).

SYNTHETIC TEST VALUES ONLY. Every feature, lookback, threshold, cap, minimum and approval below is a synthetic test value
chosen to exercise structure; none is a production threshold and none is production-approved. ``HUMAN_GOVERNANCE``
approvals built here are synthetic test fixtures for the PASS branch.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import re
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.regime_feature_policy as policy_module
from crypto_core.validation.edge_artifact_core import EdgeGateVerdict, edge_canonical_json, edge_sha256_text
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDatasetError,
    HistoricalPitValue,
    build_historical_pit_record,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_F1_FORMULA_POLICY_ID,
    REGIME_F2_FORMULA_POLICY_ID,
    REGIME_FEATURE_POLICY_RULE_SET_DIGEST,
    REGIME_NON_CLAIM_FLAGS,
    REGIME_NUMERIC_POLICY_ID,
    REGIME_UNLABELED,
    RegimeFeatureClass,
    RegimeFeatureDefinition,
    RegimeFeaturePolicy,
    RegimeFeaturePolicyApproval,
    RegimeFeaturePolicyApprovalKind,
    RegimeFeaturePolicyError,
    RegimeLabelPredicate,
    RegimeLabelRule,
    RegimePredicateOperator,
    build_regime_feature_policy,
    regime_decimal_text,
    regime_decimal_value,
    regime_feature_policy_digest,
    regime_feature_policy_from_payload,
    regime_feature_policy_payload_is_well_formed,
    regime_feature_policy_rule_set,
    regime_feature_policy_to_dict,
    verify_regime_feature_policy,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "regime_feature_policy"
HUMAN = RegimeFeaturePolicyApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC
F1 = RegimeFeatureClass.F1_REALIZED_VOL
F2 = RegimeFeatureClass.F2_DRAWDOWN_STATE
LT, LTE, GT, GTE = (RegimePredicateOperator(name) for name in ("LT", "LTE", "GT", "GTE"))
UNIT = Fraction(1, 10**18)
INT64_MAX = 9223372036854775807
SOURCE = Path(policy_module.__file__).read_text(encoding="utf-8")
SERIES, INSTRUMENT = "mark-majors", "BTC-PERPETUAL"  # an eligible price series of the EF-3 test manifest
VALUE = "close"  # SYNTHETIC governed value name of the close in each authenticated PIT record
VOL, DD = "vol-btc-3d", "dd-btc-2d"


def d(text: str) -> str:
    """A SYNTHETIC TEST VALUE rendered as canonical scale-18 decimal text."""

    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    rendered = f"{integer}.{fraction.ljust(18, '0')}"
    return f"-{rendered}" if negative else rendered


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RF-2 construction error."""

    return pytest.raises(RegimeFeaturePolicyError, match=f"^{re.escape(code(text))}$")


def feature(
    feature_id: str = VOL,
    feature_class: object = F1,
    *,
    series: object = SERIES,
    instrument: object = INSTRUMENT,
    value_name: object = VALUE,
    lookback: object = 3,
    formula: object = None,
) -> RegimeFeatureDefinition:
    if formula is None:
        formula = (
            REGIME_F1_FORMULA_POLICY_ID if feature_class in (F1, "F1_REALIZED_VOL") else REGIME_F2_FORMULA_POLICY_ID
        )
    return RegimeFeatureDefinition(
        feature_id=feature_id,
        feature_class=feature_class,  # type: ignore[arg-type]
        source_series_id=series,  # type: ignore[arg-type]
        instrument_id=instrument,  # type: ignore[arg-type]
        value_name=value_name,  # type: ignore[arg-type]
        lookback_days=lookback,  # type: ignore[arg-type]
        formula_policy_id=formula,  # type: ignore[arg-type]
    )


def predicate(feature_id: str, operator: object, threshold: str) -> RegimeLabelPredicate:
    return RegimeLabelPredicate(feature_id, operator, threshold)  # type: ignore[arg-type]


def rule(priority: object, label: str, *predicates: RegimeLabelPredicate) -> RegimeLabelRule:
    return RegimeLabelRule(priority, label, predicates)  # type: ignore[arg-type]


def default_features() -> list[RegimeFeatureDefinition]:
    return [feature(VOL, F1, lookback=3), feature(DD, F2, lookback=2)]


def default_rules() -> list[RegimeLabelRule]:
    """SYNTHETIC: stressed on a drawdown or high vol, calm on neither; a middle band of vol stays UNLABELED."""

    return [
        rule(1, "STRESSED", predicate(DD, GT, d("0.05"))),
        rule(2, "STRESSED", predicate(VOL, GT, d("0.03"))),
        rule(3, "CALM", predicate(DD, LTE, d("0.05")), predicate(VOL, LTE, d("0.02"))),
    ]


def policy_args(**overrides: object) -> dict[str, object]:
    """SYNTHETIC TEST VALUES for every governed input; the module itself has no default."""

    args: dict[str, object] = {
        "policy_id": "rf2-synthetic-policy",
        "policy_version": "synthetic-v1",
        "features": default_features(),
        "label_set": ["STRESSED", "CALM"],
        "label_rules": default_rules(),
        "max_unlabeled_fraction": d("0.5"),
        "stability_min_overlap_days": 3,
        "stability_min_asof_gap_days": 1,
        "distribution_drift_cap": d("0.25"),
        "approval": None,
    }
    args.update(overrides)
    return args


def build(**overrides: object) -> RegimeFeaturePolicy:
    return build_regime_feature_policy(**policy_args(**overrides))  # type: ignore[arg-type]


def approval_for(
    policy: RegimeFeaturePolicy, *, kind: object = HUMAN, **overrides: object
) -> RegimeFeaturePolicyApproval:
    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "c" * 64,
        "approval_kind": kind,
        "approved_policy_id": policy.policy_id,
        "approved_policy_version": policy.policy_version,
        "approved_policy_digest": policy.policy_digest,
        "approved_rule_set_digest": policy.rule_set_digest,
    }
    values.update(overrides)
    return RegimeFeaturePolicyApproval(**values)  # type: ignore[arg-type]


def governed(**overrides: object) -> RegimeFeaturePolicy:
    """A policy under an exact synthetic HUMAN_GOVERNANCE test approval (PASS-branch fixture only)."""

    overrides.pop("approval", None)
    return build(approval=approval_for(build(**overrides)), **overrides)


def reseal(policy: RegimeFeaturePolicy, **changes: object) -> RegimeFeaturePolicy:
    changed = replace(policy, **changes)  # type: ignore[arg-type]
    return replace(changed, regime_feature_policy_digest=regime_feature_policy_digest(changed))


def assert_intact(policy: RegimeFeaturePolicy) -> None:
    verification = verify_regime_feature_policy(policy)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == policy.regime_feature_policy_digest
    assert regime_feature_policy_from_payload(json.loads(verification.canonical_json)) == policy
    assert {name: getattr(policy, name) for name, _ in REGIME_NON_CLAIM_FLAGS} == dict(REGIME_NON_CLAIM_FLAGS)


# --- A. governance --------------------------------------------------------------------------------------------------


def test_an_exact_human_approval_advances_the_policy_and_binds_every_governed_value() -> None:
    policy = governed()
    assert (policy.gate_verdict, policy.advances, policy.verdict_reason_codes) == (EdgeGateVerdict.PASS, True, ())
    assert policy.synthetic_test_approval_used is False
    assert (policy.rule_set_digest, policy.numeric_policy_id, policy.unlabeled_label_id) == (
        REGIME_FEATURE_POLICY_RULE_SET_DIGEST,
        REGIME_NUMERIC_POLICY_ID,
        REGIME_UNLABELED,
    )
    assert [item.feature_id for item in policy.features] == [DD, VOL]  # canonical order
    assert policy.label_set == ("CALM", "STRESSED")
    assert [item.priority for item in policy.label_rules] == [1, 2, 3]
    assert (policy.max_unlabeled_fraction, policy.distribution_drift_cap) == (d("0.5"), d("0.25"))
    assert (policy.stability_min_overlap_days, policy.stability_min_asof_gap_days) == (3, 1)
    assert policy.approval is not None and policy.approval.approved_policy_digest == policy.policy_digest
    assert_intact(policy)
    assert regime_feature_policy_payload_is_well_formed(regime_feature_policy_to_dict(policy)) is True


def test_a_missing_approval_needs_governance_and_never_advances() -> None:
    policy = build()
    assert (policy.gate_verdict, policy.advances) == (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, False)
    assert policy.verdict_reason_codes == (code("governance_approval_missing"),)
    assert_intact(policy)


def test_a_test_only_synthetic_approval_is_surfaced_and_never_advances() -> None:
    policy = build(approval=approval_for(build(), kind=SYNTHETIC))
    assert (policy.gate_verdict, policy.advances, policy.synthetic_test_approval_used) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        True,
    )
    assert policy.verdict_reason_codes == (code("governance_approval_test_only_synthetic"),)
    assert_intact(policy)


def test_any_governed_change_makes_an_earlier_approval_stale() -> None:
    approval = approval_for(build())
    stale = build(approval=approval, distribution_drift_cap=d("0.3"))
    assert stale.policy_digest != approval.approved_policy_digest
    assert (stale.gate_verdict, stale.advances) == (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, False)
    assert stale.verdict_reason_codes == (code("governance_approval_policy_digest_mismatch"),)
    # Every governed value is committed by the policy digest; the approval and the verdict are not.
    base = build()
    for overrides in (
        {"policy_id": "rf2-other"},
        {
            "label_set": ["STRESSED", "CALM"],
            "label_rules": [
                *default_rules()[:2],
                rule(3, "CALM", predicate(DD, LT, d("0.05")), predicate(VOL, LTE, d("0.02"))),
            ],
        },
        {"features": [feature(VOL, F1, lookback=4), feature(DD, F2, lookback=2)]},
        {"features": [feature(VOL, F1, value_name="settle_close"), feature(DD, F2, lookback=2)]},
        {"max_unlabeled_fraction": d("0.4")},
        {"stability_min_overlap_days": 4},
        {"stability_min_asof_gap_days": 2},
    ):
        assert build(**overrides).policy_digest != base.policy_digest, overrides
    assert build(approval=approval_for(base)).policy_digest == base.policy_digest


@pytest.mark.parametrize("name", ["policy_id", "policy_version", "policy_digest", "rule_set_digest"])
def test_each_approval_commitment_must_match_exactly(name: str) -> None:
    other = "f" * 64 if name.endswith("digest") else "rf2-other"
    policy = build(approval=approval_for(build(), **{f"approved_{name}": other}))
    assert (policy.gate_verdict, policy.advances) == (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, False)
    assert policy.verdict_reason_codes == (code(f"governance_approval_{name}_mismatch"),)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"approval_reference": ""}, "governance_approval_reference_invalid"),
        ({"approval_digest": "C" * 64}, "governance_approval_digest_invalid"),
        ({"approval_kind": "HUMAN"}, "governance_approval_kind_invalid"),
        ({"approved_policy_digest": "not-a-digest"}, "governance_approved_policy_digest_invalid"),
    ],
)
def test_a_malformed_approval_is_refused_never_downgraded(changes: dict[str, object], reason: str) -> None:
    with refused(reason):
        build(approval=approval_for(build(), **changes))
    with refused("governance_approval_malformed"):
        build(approval={"approval_kind": "HUMAN_GOVERNANCE"})


# --- A. governed structure ------------------------------------------------------------------------------------------


def test_no_governed_value_has_a_default() -> None:
    parameters = inspect.signature(build_regime_feature_policy).parameters.values()
    assert all(item.kind is inspect.Parameter.KEYWORD_ONLY for item in parameters)
    assert all(item.default is inspect.Parameter.empty for item in parameters)
    for record in (RegimeFeatureDefinition, RegimeLabelPredicate, RegimeLabelRule, RegimeFeaturePolicyApproval):
        assert all(item.default is dataclasses.MISSING for item in fields(record))
    integers = {
        node.value for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Constant) and type(node.value) is int
    }
    # The scale and its base, representation bounds, the structural minimum closes per class, indexes and parity.
    assert integers <= {0, 1, 2, 3, 10, 18, 32, 60, 64, 127, 128, 256, INT64_MAX}


@pytest.mark.parametrize(
    "deferred", ["F3_TREND_RANGE_PERSISTENCE", "F4_FUNDING_REGIME", "F5_LIQUIDITY_SPREAD", "F6_LIQUIDATION_EVENT"]
)
def test_every_deferred_feature_class_is_refused_explicitly(deferred: str) -> None:
    with refused("feature_class_deferred_not_supported_in_v1"):
        build(features=[*default_features(), feature("deferred-1", deferred, formula="RF_DEFERRED_V1")])
    assert deferred in regime_feature_policy_rule_set()["deferred_feature_classes"]  # type: ignore[operator]
    assert deferred not in {member.value for member in RegimeFeatureClass}


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        ([], "features_missing"),
        ("vol", "features_malformed"),
        ([*default_features(), {"feature_id": "x"}], "feature_malformed"),
        ([feature(VOL, "F7_UNKNOWN"), feature(DD, F2, lookback=2)], "feature_class_invalid"),
        ([feature(VOL, F1), feature(DD, F2, lookback=2), feature(VOL, F2, lookback=5)], "feature_id_duplicate"),
        (
            [feature(VOL, F1), feature(DD, F2, lookback=2), feature("VOL-BTC-3D", F2, lookback=5)],
            "feature_id_duplicate",
        ),
        ([feature(VOL, F1), feature(DD, F2, lookback=2), feature("vol-copy", F1)], "feature_binding_duplicate"),
        ([feature(VOL, F1, lookback=2), feature(DD, F2, lookback=2)], "feature_lookback_days_below_minimum"),
        ([feature(VOL, F1), feature(DD, F2, lookback=1)], "feature_lookback_days_below_minimum"),
        ([feature(VOL, F1, lookback=True), feature(DD, F2, lookback=2)], "feature_lookback_days_invalid"),
        ([feature(VOL, F1, lookback=INT64_MAX + 1), feature(DD, F2, lookback=2)], "feature_lookback_days_invalid"),
        (
            [feature(VOL, F1, formula=REGIME_F2_FORMULA_POLICY_ID), feature(DD, F2, lookback=2)],
            "feature_formula_policy_mismatch",
        ),
        ([feature(VOL, F1, series="Mark-Majors"), feature(DD, F2, lookback=2)], "feature_source_series_id_invalid"),
        ([feature(VOL, F1, instrument="BTC PERPETUAL"), feature(DD, F2, lookback=2)], "feature_instrument_id_invalid"),
        ([feature(VOL, F1, value_name=""), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name="Close"), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name="close price"), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name="_close"), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name="c" * 129), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name="clöse"), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        ([feature(VOL, F1, value_name=None), feature(DD, F2, lookback=2)], "feature_value_name_invalid"),
        (
            [feature(VOL, F1, value_name="live"), feature(DD, F2, lookback=2)],
            "forbidden_scope_token:feature_value_name",
        ),
        ([feature("vol live", F1), feature(DD, F2, lookback=2)], "feature_id_invalid"),
    ],
)
def test_malformed_or_inconsistent_features_are_refused(features: object, reason: str) -> None:
    with refused(reason):
        build(features=features)


def test_the_same_series_may_carry_distinct_features() -> None:
    features = [
        feature(VOL, F1),
        feature(DD, F2, lookback=2),
        feature("vol-btc-5d", F1, lookback=5),
        feature("vol-btc-3d-settle", F1, value_name="settle_close"),  # the same binding but another governed value
    ]
    rules = [
        *default_rules(),
        rule(4, "STRESSED", predicate("vol-btc-5d", GT, d("0.04"))),
        rule(5, "STRESSED", predicate("vol-btc-3d-settle", GT, d("0.04"))),
    ]
    policy = build(features=features, label_rules=rules)
    assert [item.feature_id for item in policy.features] == [DD, VOL, "vol-btc-3d-settle", "vol-btc-5d"]
    assert [item.value_name for item in policy.features] == [VALUE, VALUE, "settle_close", VALUE]


def test_the_governed_value_name_is_mandatory_and_committed_by_the_approval() -> None:
    assert {item.name: item.default for item in fields(RegimeFeatureDefinition)}["value_name"] is dataclasses.MISSING
    base = governed()
    assert {item.value_name for item in base.features} == {VALUE}
    renamed = [feature(VOL, F1, value_name="settle_close"), feature(DD, F2, lookback=2)]
    stale = build(features=renamed, approval=base.approval)
    assert stale.policy_digest != base.policy_digest  # only the value name changed
    assert (stale.gate_verdict, stale.advances) == (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, False)
    assert stale.verdict_reason_codes == (code("governance_approval_policy_digest_mismatch"),)
    fresh = governed(features=renamed)
    assert (fresh.gate_verdict, fresh.advances) == (EdgeGateVerdict.PASS, True)
    assert [item["value_name"] for item in regime_feature_policy_to_dict(fresh)["features"]] == [VALUE, "settle_close"]  # type: ignore[index,union-attr]
    synthetic = build(features=renamed, approval=approval_for(build(features=renamed), kind=SYNTHETIC))
    assert (synthetic.advances, synthetic.synthetic_test_approval_used) == (False, True)
    assert_intact(fresh)


@pytest.mark.parametrize(
    "name", ["close", "settle_close", "a.b:c-d", "9close", "", "Close", "close price", "_close", "c" * 129, "live"]
)
def test_the_value_name_grammar_is_the_accepted_pit_value_name_grammar(name: str) -> None:
    """The accepted ``HistoricalPitRecord`` builder is the oracle: RF-2 accepts exactly the value names it accepts."""

    try:
        build_historical_pit_record(
            series_id=SERIES,
            data_requirement_key="mark_price",
            instrument=INSTRUMENT,
            sequence_id=0,
            event_time_ns=1,
            available_at_ns=1,
            finalized_at_ns=1,
            revision_vintage_id=None,
            values=(HistoricalPitValue(name, d("1")),),
        )
        pit_accepts = True
    except HistoricalPitDatasetError:
        pit_accepts = False
    try:
        build(features=[feature(VOL, F1, value_name=name), feature(DD, F2, lookback=2)])
        policy_accepts = True
    except RegimeFeaturePolicyError:
        policy_accepts = False
    assert policy_accepts is pit_accepts


@pytest.mark.parametrize(
    ("label_set", "reason"),
    [
        ([], "label_set_missing"),
        ({"CALM"}, "label_set_malformed"),
        (["STRESSED", "CALM", "UNLABELED"], "label_set_reserved_unlabeled"),
        (["STRESSED", "CALM", "unlabeled"], "label_set_reserved_unlabeled"),
        (["STRESSED", "CALM", "calm"], "label_set_duplicate"),
        (["STRESSED", " CALM"], "label_set_member_invalid"),
        (["STRESSED", "CALM", "QUIET"], "label_set_member_without_rule"),
    ],
)
def test_the_label_set_is_closed_reserved_and_exactly_the_rule_outputs(label_set: object, reason: str) -> None:
    with refused(reason):
        build(label_set=label_set)


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        ([], "label_rules_missing"),
        ([*default_rules(), "rule"], "label_rule_malformed"),
        (
            [rule(1, "STRESSED", predicate(DD, GT, d("0.05"))), rule(3, "CALM", predicate(VOL, LTE, d("0.02")))],
            "label_rule_priorities_not_contiguous_from_one",
        ),
        (
            [rule(1, "STRESSED", predicate(DD, GT, d("0.05"))), rule(1, "CALM", predicate(VOL, LTE, d("0.02")))],
            "label_rule_priority_duplicate",
        ),
        (
            [rule(0, "STRESSED", predicate(DD, GT, d("0.05"))), rule(1, "CALM", predicate(VOL, LTE, d("0.02")))],
            "label_rule_priority_below_minimum",
        ),
        (
            [rule(True, "STRESSED", predicate(DD, GT, d("0.05"))), rule(2, "CALM", predicate(VOL, LTE, d("0.02")))],
            "label_rule_priority_invalid",
        ),
        ([*default_rules(), rule(4, "UNLABELED", predicate(DD, GT, d("0.5")))], "label_rule_label_reserved_unlabeled"),
        ([*default_rules(), rule(4, "QUIET", predicate(DD, GT, d("0.5")))], "label_rule_label_not_in_label_set"),
        ([*default_rules(), rule(4, "CALM", predicate(DD, GT, d("0.05")))], "label_rule_predicates_duplicate"),
        (
            [rule(1, "STRESSED", predicate(DD, GT, d("0.05"))), rule(2, "CALM", predicate(DD, LTE, d("0.05")))],
            "feature_not_read_by_any_rule",
        ),
        ([*default_rules()[:2], rule(3, "CALM")], "label_predicates_missing"),
        ([*default_rules()[:2], RegimeLabelRule(3, "CALM", "predicate")], "label_predicates_malformed"),  # type: ignore[arg-type]
        ([*default_rules()[:2], rule(3, "CALM", predicate(DD, LT, d("0.05")), "p")], "label_predicate_malformed"),  # type: ignore[arg-type]
        (
            [*default_rules()[:2], rule(3, "CALM", predicate("vol-unknown", LT, d("0.05")))],
            "label_predicate_feature_unknown",
        ),
        ([*default_rules()[:2], rule(3, "CALM", predicate(DD, "EQ", d("0.05")))], "label_predicate_operator_invalid"),
        (
            [*default_rules()[:2], rule(3, "CALM", predicate(DD, LT, d("0.05")), predicate(DD, "LT", d("0.05")))],
            "label_predicate_duplicate",
        ),
    ],
)
def test_malformed_or_inconsistent_label_rules_are_refused(rules: object, reason: str) -> None:
    with refused(reason):
        build(label_rules=rules)


@pytest.mark.parametrize(
    "threshold",
    [
        "0.05",
        "0.0500000000000000000",
        "+0.050000000000000000",
        "-0.000000000000000000",
        "00.050000000000000000",
        "5e-2",
        "0.05" + "0" * 16 + " ",
        0.05,
        None,
        "1" * 42 + ".000000000000000000",
    ],
)
def test_every_threshold_is_canonical_scale_18_text(threshold: object) -> None:
    with refused("label_predicate_threshold_invalid"):
        build(
            label_rules=[
                *default_rules()[:2],
                rule(3, "CALM", predicate(DD, LTE, threshold), predicate(VOL, LTE, d("0.02"))),
            ]
        )  # type: ignore[arg-type]


def test_predicates_and_rules_are_held_in_one_canonical_order() -> None:
    shuffled = [
        default_rules()[2],
        rule(1, "STRESSED", predicate(DD, GT, d("0.05"))),
        rule(2, "STRESSED", predicate(VOL, GT, d("0.03"))),
    ]
    reversed_predicates = [
        *default_rules()[:2],
        rule(3, "CALM", predicate(VOL, LTE, d("0.02")), predicate(DD, LTE, d("0.05"))),
    ]
    base = governed()
    assert governed(label_rules=shuffled) == base
    assert governed(label_rules=reversed_predicates) == base
    assert governed(features=list(reversed(default_features())), label_set=("CALM", "STRESSED")) == base
    assert [predicate.feature_id for predicate in base.label_rules[2].predicates] == [DD, VOL]


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("max_unlabeled_fraction", d("-0.000000000000000001"), "max_unlabeled_fraction_out_of_domain"),
        ("max_unlabeled_fraction", d("1.000000000000000001"), "max_unlabeled_fraction_out_of_domain"),
        ("max_unlabeled_fraction", "0.5", "max_unlabeled_fraction_invalid"),
        ("distribution_drift_cap", d("1.000000000000000001"), "distribution_drift_cap_out_of_domain"),
        ("distribution_drift_cap", None, "distribution_drift_cap_invalid"),
        ("stability_min_overlap_days", 0, "stability_min_overlap_days_below_minimum"),
        ("stability_min_overlap_days", True, "stability_min_overlap_days_invalid"),
        ("stability_min_asof_gap_days", 0, "stability_min_asof_gap_days_below_minimum"),
        ("stability_min_asof_gap_days", INT64_MAX + 1, "stability_min_asof_gap_days_invalid"),
        ("policy_id", "", "policy_id_invalid"),
        ("policy_id", "rf2 live policy", "forbidden_scope_token:policy_id"),
        ("policy_version", " v1", "policy_version_invalid"),
    ],
)
def test_out_of_domain_values_are_refused(name: str, value: object, reason: str) -> None:
    with refused(reason):
        build(**{name: value})


@pytest.mark.parametrize("value", [d("0"), d("1")])
def test_fraction_domains_include_both_bounds(value: str) -> None:
    policy = governed(max_unlabeled_fraction=value, distribution_drift_cap=value)
    assert (policy.max_unlabeled_fraction, policy.distribution_drift_cap) == (value, value)


# --- A. the verifier ------------------------------------------------------------------------------------------------


def test_every_governed_field_is_digest_bound_and_reproven() -> None:
    policy = governed()
    unsealed = verify_regime_feature_policy(replace(policy, distribution_drift_cap=d("0.9")))
    assert set(unsealed.reason_codes) == {
        code("self_digest_mismatch"),
        code("field_mismatch:regime_feature_policy_digest"),
    } | {
        code("field_mismatch:policy_digest"),
        code("field_mismatch:gate_verdict"),
        code("field_mismatch:advances"),
        code("field_mismatch:verdict_reason_codes"),
    }
    # A resealed forgery that keeps PASS for a changed threshold is refused by reassembly.
    forged_rule = rule(1, "STRESSED", predicate(DD, GT, d("0.06")))
    forged = reseal(policy, label_rules=(forged_rule, *policy.label_rules[1:]))
    verification = verify_regime_feature_policy(forged)
    assert verification.intact is False
    assert code("field_mismatch:policy_digest") in verification.reason_codes
    for flag, _ in REGIME_NON_CLAIM_FLAGS:
        assert verify_regime_feature_policy(reseal(policy, **{flag: not getattr(policy, flag)})).intact is False


def test_the_verifier_is_total() -> None:
    policy = governed()
    for value in (
        None,
        {},
        "policy",
        policy.features[0],
        replace(policy, gate_verdict="PASS"),
        replace(policy, stability_min_overlap_days=-1),
        replace(policy, label_set=list(policy.label_set)),
        replace(policy, max_unlabeled_fraction=0.5),
    ):
        verification = verify_regime_feature_policy(value)
        assert verification.intact is False
        assert verification.reason_codes in (
            (code("evidence_type_invalid"),),
            (code("evidence_serialization_failed"),),
        )
    parse_broken = verify_regime_feature_policy(replace(policy, max_unlabeled_fraction="0.5"))
    assert parse_broken.reason_codes == (code("evidence_parse_failed"),)
    reassembly_broken = verify_regime_feature_policy(reseal(policy, label_set=("CALM",)))
    assert reassembly_broken.reason_codes == (code("evidence_reassembly_failed"),)


# --- numeric policy -------------------------------------------------------------------------------------------------


def oracle_half_even(value: Fraction) -> str:
    """An independent exact half-even scale-18 rendering: integer floor plus a twice-the-remainder comparison."""

    scaled = value * 10**18
    floor = scaled.numerator // scaled.denominator
    twice = 2 * (scaled - floor)
    units = floor + 1 if twice > 1 or (twice == 1 and floor % 2) else floor
    sign = "-" if units < 0 else ""
    return f"{sign}{abs(units) // 10**18}.{abs(units) % 10**18:018d}"


@pytest.mark.parametrize(
    "value",
    [
        Fraction(0),
        Fraction(1, 3),
        Fraction(2, 3),
        Fraction(1, 10),
        Fraction(5, 10**19),  # an exact half unit below an even unit: stays 0
        Fraction(15, 10**19),  # an exact half unit above an odd unit: rounds up to 2
        Fraction(-15, 10**19),
        Fraction(-1, 10**20),  # rounds to zero, never a signed zero
        Fraction(10**40),
    ],
)
def test_rationals_render_exactly_half_even_at_scale_18(value: Fraction) -> None:
    assert regime_decimal_text(value) == oracle_half_even(value)
    assert regime_decimal_value(regime_decimal_text(value)) == Fraction(oracle_half_even(value))


def test_rendering_and_parsing_respect_the_60_character_bound() -> None:
    largest = Fraction(10**41) - UNIT
    assert len(regime_decimal_text(largest)) == 60  # type: ignore[arg-type]
    assert regime_decimal_text(Fraction(10**41)) is None
    assert regime_decimal_text(Fraction(-(10**40)) + UNIT) is not None
    assert regime_decimal_text(Fraction(-(10**40))) is None
    assert regime_decimal_text(0.5) is None  # type: ignore[arg-type]
    for text in ("0.1", "1e-18", "-0.000000000000000000", 1, None):
        assert regime_decimal_value(text) is None


# --- static discipline, rule set and API ----------------------------------------------------------------------------


def test_the_module_is_pure_and_never_imports_the_runtime_regime_package() -> None:
    pit.assert_module_is_pure(policy_module, {"crypto_core.validation.edge_artifact_core"})
    imports = [node for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, (ast.Import, ast.ImportFrom))]
    modules = {alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names}
    modules |= {node.module for node in imports if isinstance(node, ast.ImportFrom) and node.module}
    assert not [name for name in modules if name == "crypto_core.regime" or name.startswith("crypto_core.regime.")]


def test_execution_capital_and_scheduler_names_are_only_structural_false_flags() -> None:
    flags = dict(REGIME_NON_CLAIM_FLAGS)
    names: set[str] = set()
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
    risky = {
        name
        for name in names
        if re.search(r"(^|_)(live|orders?|capital|scheduler|connector|shadow|execution)(_|$)", name)
    }
    assert risky <= set(flags)
    assert {item.name: item.default for item in fields(RegimeFeaturePolicy) if item.name in flags} == flags
    assert all(item.default is dataclasses.MISSING for item in fields(RegimeFeaturePolicy) if item.name not in flags)
    for name in (
        "edge_proven",
        "direction_signal_emitted",
        "allocation_decided",
        "portfolio_stop_authority",
        "regime_filter_admitted",
    ):
        assert flags[name] is False


def test_the_rule_set_commits_the_controller_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_feature_policy_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_FEATURE_POLICY_RULE_SET_DIGEST
    assert (rule_set["contract_id"], rule_set["structural_authority_id"]) == (
        "RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1",
        "RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1",
    )
    assert rule_set["supported_feature_classes"] == (
        ("F1_REALIZED_VOL", "RF_F1_SIMPLE_RETURN_SAMPLE_STDDEV_V1", 3),
        ("F2_DRAWDOWN_STATE", "RF_F2_ROLLING_PEAK_DISTANCE_V1", 2),
    )
    assert (rule_set["numeric_policy_id"], rule_set["unlabeled_label_id"]) == (
        "RF_FIXED_SCALE18_DECIMAL_HALF_EVEN_P80_V1",
        "UNLABELED",
    )
    assert rule_set["predicate_operators"] == ("LT", "LTE", "GT", "GTE")
    rule_set["numeric_policy_id"] = "other"
    assert regime_feature_policy_rule_set()["numeric_policy_id"] == REGIME_NUMERIC_POLICY_ID


def test_the_public_api_is_exact() -> None:
    assert set(policy_module.__all__) == {
        "REGIME_F1_FORMULA_POLICY_ID",
        "REGIME_F2_FORMULA_POLICY_ID",
        "REGIME_FEATURE_POLICY_RULE_SET_DIGEST",
        "REGIME_NON_CLAIM_FLAGS",
        "REGIME_NUMERIC_POLICY_ID",
        "REGIME_UNLABELED",
        "RegimeFeatureClass",
        "RegimeFeatureDefinition",
        "RegimeFeaturePolicy",
        "RegimeFeaturePolicyApproval",
        "RegimeFeaturePolicyApprovalKind",
        "RegimeFeaturePolicyError",
        "RegimeLabelPredicate",
        "RegimeLabelRule",
        "RegimePredicateOperator",
        "build_regime_feature_policy",
        "regime_decimal_text",
        "regime_decimal_value",
        "regime_feature_policy_digest",
        "regime_feature_policy_from_payload",
        "regime_feature_policy_payload_is_well_formed",
        "regime_feature_policy_rule_set",
        "regime_feature_policy_to_dict",
        "verify_regime_feature_policy",
    }
