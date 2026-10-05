"""Paper portfolio performance-path policy tests (RG4_PORTFOLIO_PERFORMANCE_PATH_POLICY_V1).

SYNTHETIC TEST VALUES ONLY. Every performance weight, identifier and approval in this file is a synthetic test value
that exercises structure. None is a production value, none is a recommended weighting and none is production-approved.
The RG-2 envelope is the synthetic fixture of its own test module; the ``HUMAN_GOVERNANCE`` approvals built here are
synthetic test fixtures for the PASS branch only.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import inspect
import json
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_portfolio_performance_path_policy as policy_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_performance_path_policy import (
    PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS,
    PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
    PaperPortfolioPerformancePathApproval,
    PaperPortfolioPerformancePathApprovalKind,
    PaperPortfolioPerformancePathPolicy,
    PaperPortfolioPerformancePathPolicyError,
    PaperPortfolioPerformanceWeight,
    build_paper_portfolio_performance_path_policy,
    paper_portfolio_performance_path_policy_digest,
    paper_portfolio_performance_path_policy_from_payload,
    paper_portfolio_performance_path_policy_payload_is_well_formed,
    paper_portfolio_performance_path_policy_to_dict,
    paper_portfolio_performance_path_rule_set,
    verify_paper_portfolio_performance_path_policy,
)
from crypto_core.validation.paper_portfolio_risk_envelope import PaperPortfolioRiskEnvelope
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module object pytest collects (basename import), so the RG-2 fixtures are shared
    import test_paper_portfolio_risk_envelope as rg2
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2

_PREFIX = "paper_portfolio_performance_path_policy"
INT64_MAX = 9223372036854775807
HUMAN = PaperPortfolioPerformancePathApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperPortfolioPerformancePathApprovalKind.TEST_ONLY_SYNTHETIC
REBALANCING_CONVENTION = "NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1"
DOCS = Path(__file__).resolve().parents[3] / "docs" / "crypto_core"
# The approval, the verdict it yields and the two digests are outside the governed policy (the module's contract).
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
POLICY_FLAGS = frozenset(
    {
        "account_equity_represented",
        "capital_represented",
        "portfolio_allocation_approved",
        "risk_budget_used_as_weight",
        "reference_notional_used_as_weight",
        "execution_authorized",
        "prdv4_stage4_complete",
    }
)


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


class _List(list):
    """A ``list`` subclass, refused wherever an exact caller sequence is required."""


@dataclass(frozen=True)
class _WeightSubclass(PaperPortfolioPerformanceWeight):
    """A record subclass, refused wherever the exact record type is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperPortfolioPerformancePathPolicyError, match=f"^{re.escape(_code(code))}$")


def weight(sleeve_id: str, value: str) -> PaperPortfolioPerformanceWeight:
    """A SYNTHETIC TEST weight rendered as canonical scale-18 decimal text."""

    return PaperPortfolioPerformanceWeight(sleeve_id=sleeve_id, performance_weight=rg2.d(value))


def synthetic_weights() -> list[PaperPortfolioPerformanceWeight]:
    """SYNTHETIC TEST weights over the RG-2 fixture's two declared sleeves; deliberately not equal weights."""

    return [weight("sleeve-alpha", "0.6"), weight("sleeve-beta", "0.4")]


@functools.lru_cache(maxsize=None)
def world_envelope() -> PaperPortfolioRiskEnvelope:
    return rg2.governed()


@functools.lru_cache(maxsize=None)
def three_sleeve_envelope() -> PaperPortfolioRiskEnvelope:
    return rg2.governed(
        sleeve_caps=[
            rg2.sleeve("sleeve-alpha", "400"),
            rg2.sleeve("sleeve-beta", "250"),
            rg2.sleeve("sleeve-gamma", "100"),
        ]
    )


def policy_args(**overrides: object) -> dict[str, object]:
    """SYNTHETIC TEST VALUES for every governed input; no default exists in the module itself."""

    args: dict[str, object] = {
        "policy_id": "rg4-synthetic-performance-path",
        "policy_version": "synthetic-v1",
        "portfolio_risk_envelope": world_envelope(),
        "performance_weights": synthetic_weights(),
        "approval": None,
    }
    args.update(overrides)
    return args


def build(**overrides: object) -> PaperPortfolioPerformancePathPolicy:
    return build_paper_portfolio_performance_path_policy(**policy_args(**overrides))  # type: ignore[arg-type]


def approval_for(
    policy: PaperPortfolioPerformancePathPolicy, *, kind: object = HUMAN, **overrides: object
) -> PaperPortfolioPerformancePathApproval:
    """A synthetic test approval committing exactly to ``policy`` unless overridden."""

    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "a" * 64,
        "approval_kind": kind,
        "approved_policy_id": policy.policy_id,
        "approved_policy_version": policy.policy_version,
        "approved_policy_digest": policy.policy_digest,
        "approved_rule_set_digest": policy.rule_set_digest,
    }
    values.update(overrides)
    return PaperPortfolioPerformancePathApproval(**values)  # type: ignore[arg-type]


def governed(**overrides: object) -> PaperPortfolioPerformancePathPolicy:
    """A policy under an exact synthetic HUMAN_GOVERNANCE test approval (PASS-branch fixture only)."""

    return build(approval=approval_for(build(**overrides)), **overrides)


def verify(policy: object) -> EdgeEvidenceVerification:
    return verify_paper_portfolio_performance_path_policy(policy)


def _reseal(policy: PaperPortfolioPerformancePathPolicy, **changes: object) -> PaperPortfolioPerformancePathPolicy:
    changed = replace(policy, **changes)
    return replace(changed, performance_path_policy_digest=paper_portfolio_performance_path_policy_digest(changed))


def _corrupted(**changes: object) -> PaperPortfolioPerformancePathPolicy:
    copy = replace(governed())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def _assert_intact(policy: PaperPortfolioPerformancePathPolicy) -> None:
    verification = verify(policy)
    assert verification.intact is True, verification.reason_codes
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == policy.performance_path_policy_digest
    assert paper_portfolio_performance_path_policy_from_payload(json.loads(verification.canonical_json)) == policy


def _doc(name: str) -> str:
    """The document's text with every whitespace run collapsed, so a wrapped sentence reads as one line."""

    return " ".join((DOCS / name).read_text(encoding="utf-8").split())


# --- A. governance and advancement ------------------------------------------------------------------------------------


def test_unapproved_policy_is_valid_structure_that_needs_governance_approval() -> None:
    policy = build()
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert policy.advances is False
    assert policy.verdict_reason_codes == (_code("governance_approval_missing"),)
    assert policy.synthetic_test_approval_used is False
    assert policy.envelope_digest == world_envelope().envelope_digest
    assert policy.rebalancing_convention == REBALANCING_CONVENTION
    _assert_intact(policy)


def test_exact_human_governance_approval_passes_without_changing_the_policy_digest() -> None:
    unapproved = build()
    policy = build(approval=approval_for(unapproved))
    assert policy.gate_verdict is EdgeGateVerdict.PASS
    assert policy.advances is True
    assert policy.verdict_reason_codes == ()
    assert policy.synthetic_test_approval_used is False
    assert policy.policy_digest == unapproved.policy_digest
    assert policy.performance_path_policy_digest != unapproved.performance_path_policy_digest
    _assert_intact(policy)


def test_test_only_synthetic_approval_binds_exactly_but_never_advances() -> None:
    policy = build(approval=approval_for(build(), kind=SYNTHETIC))
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert policy.advances is False
    assert policy.synthetic_test_approval_used is True
    assert policy.verdict_reason_codes == (_code("governance_approval_test_only_synthetic"),)
    _assert_intact(policy)


def test_synthetic_approval_with_a_mismatch_reports_both_reasons() -> None:
    policy = build(approval=approval_for(build(), kind=SYNTHETIC, approved_policy_version="synthetic-v2"))
    assert policy.advances is False
    assert policy.verdict_reason_codes == (
        _code("governance_approval_policy_version_mismatch"),
        _code("governance_approval_test_only_synthetic"),
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("approved_policy_id", "another-policy"),
        ("approved_policy_version", "synthetic-v2"),
        ("approved_policy_digest", "b" * 64),
        ("approved_rule_set_digest", "c" * 64),
    ],
)
def test_every_approval_commitment_must_match_exactly(field_name: str, value: str) -> None:
    policy = build(approval=approval_for(build(), **{field_name: value}))
    assert policy.advances is False
    assert policy.verdict_reason_codes == (_code(f"governance_approval_{field_name[len('approved_') :]}_mismatch"),)


STALE_CHANGES: dict[str, Callable[[], dict[str, object]]] = {
    "weights": lambda: {"performance_weights": [weight("sleeve-alpha", "0.7"), weight("sleeve-beta", "0.3")]},
    "envelope_budget": lambda: {"portfolio_risk_envelope": rg2.governed(total_paper_risk_budget=rg2.d("1200"))},
    "envelope_caps": lambda: {
        "portfolio_risk_envelope": rg2.governed(
            sleeve_caps=[rg2.sleeve("sleeve-alpha", "300"), rg2.sleeve("sleeve-beta", "250")]
        )
    },
    "envelope_reapproved": lambda: {
        "portfolio_risk_envelope": rg2.build(approval=rg2.approval_for(rg2.build(), approval_digest="b" * 64))
    },
}


@pytest.mark.parametrize("name", sorted(STALE_CHANGES))
def test_any_governed_value_change_makes_an_earlier_approval_stale(name: str) -> None:
    approved = governed()
    changed = build(approval=approved.approval, **STALE_CHANGES[name]())
    assert changed.policy_digest != approved.policy_digest
    assert changed.advances is False
    assert changed.verdict_reason_codes == (_code("governance_approval_policy_digest_mismatch"),)
    _assert_intact(changed)


def test_identity_change_makes_an_earlier_approval_stale() -> None:
    renamed = build(approval=governed().approval, policy_version="synthetic-v2")
    assert renamed.advances is False
    assert renamed.verdict_reason_codes == (
        _code("governance_approval_policy_digest_mismatch"),
        _code("governance_approval_policy_version_mismatch"),
    )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"approval_reference": ""}, "governance_approval_reference_invalid"),
        ({"approval_reference": _Text("subclass")}, "governance_approval_reference_invalid"),
        ({"approval_reference": "approved-by-live-desk"}, "forbidden_scope_token:governance_approval_reference"),
        ({"approval_digest": "A" * 64}, "governance_approval_digest_invalid"),
        ({"approval_kind": "HUMAN"}, "governance_approval_kind_invalid"),
        ({"approval_kind": _Text("HUMAN_GOVERNANCE")}, "governance_approval_kind_invalid"),
        ({"approval_kind": EdgeGateVerdict.PASS}, "governance_approval_kind_invalid"),
        ({"approved_policy_id": None}, "governance_approved_policy_id_invalid"),
        ({"approved_policy_version": 1}, "governance_approved_policy_version_invalid"),
        ({"approved_policy_digest": "g" * 64}, "governance_approved_policy_digest_invalid"),
        ({"approved_rule_set_digest": 7}, "governance_approved_rule_set_digest_invalid"),
    ],
)
def test_malformed_approval_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(approval=approval_for(build(), **overrides))


@pytest.mark.parametrize("candidate", [{"approval_kind": "HUMAN_GOVERNANCE"}, "approved", 1, True])
def test_approval_must_be_the_exact_record_type(candidate: object) -> None:
    with _raises("governance_approval_malformed"):
        build(approval=candidate)


def test_approval_kind_text_is_canonicalized_to_the_exact_member() -> None:
    policy = build(approval=approval_for(build(), kind="HUMAN_GOVERNANCE"))
    assert policy.approval is not None
    assert type(policy.approval.approval_kind) is PaperPortfolioPerformancePathApprovalKind
    assert policy.advances is True
    _assert_intact(policy)


# --- A. envelope coverage -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weights", "code"),
    [
        pytest.param([weight("sleeve-alpha", "1")], "performance_weight_sleeve_missing", id="missing"),
        pytest.param(
            [weight("sleeve-alpha", "0.6"), weight("sleeve-gamma", "0.4")],
            "performance_weight_sleeve_missing",
            id="substituted",
        ),
        pytest.param(
            [weight("sleeve-alpha", "0.5"), weight("sleeve-beta", "0.3"), weight("sleeve-gamma", "0.2")],
            "performance_weight_sleeve_not_declared",
            id="additional",
        ),
        pytest.param(
            [weight("Sleeve-Alpha", "0.6"), weight("sleeve-beta", "0.4")],
            "performance_weight_sleeve_missing",
            id="case_variant_never_aliases",
        ),
        pytest.param(
            [weight("sleeve-alpha", "0.3"), weight("sleeve-alpha", "0.3"), weight("sleeve-beta", "0.4")],
            "performance_weight_sleeve_duplicate",
            id="duplicate",
        ),
        pytest.param(
            [weight("sleeve-alpha", "0.4"), weight("sleeve-beta", "0.3"), weight("SLEEVE-BETA", "0.3")],
            "performance_weight_sleeve_case_ambiguous",
            id="case_insensitive_duplicate",
        ),
    ],
)
def test_weights_cover_exactly_the_envelope_declared_sleeves(
    weights: list[PaperPortfolioPerformanceWeight], code: str
) -> None:
    with _raises(code):
        build(performance_weights=weights)


def test_every_declared_sleeve_of_a_three_sleeve_envelope_needs_its_own_weight() -> None:
    envelope = three_sleeve_envelope()
    with _raises("performance_weight_sleeve_missing"):
        build(portfolio_risk_envelope=envelope, performance_weights=synthetic_weights())
    weights = [weight("sleeve-gamma", "0.1"), weight("sleeve-alpha", "0.2"), weight("sleeve-beta", "0.7")]
    policy = build(portfolio_risk_envelope=envelope, performance_weights=weights)
    assert [item.sleeve_id for item in policy.performance_weights] == ["sleeve-alpha", "sleeve-beta", "sleeve-gamma"]
    assert sum(Fraction(item.performance_weight) for item in policy.performance_weights) == 1
    _assert_intact(policy)


@pytest.mark.parametrize("candidate", [None, "envelope", {}, 1])
def test_the_envelope_must_be_the_exact_record(candidate: object) -> None:
    with _raises("portfolio_risk_envelope_malformed"):
        build(portfolio_risk_envelope=candidate)


def test_a_tampered_envelope_is_refused() -> None:
    tampered = replace(world_envelope(), total_paper_risk_budget=rg2.d("5000"))
    with _raises("portfolio_risk_envelope_not_intact"):
        build(portfolio_risk_envelope=tampered)


def test_the_policy_binds_the_exact_envelope_artifact_and_its_own_approval_is_separate() -> None:
    envelope = rg2.build()
    policy = governed(portfolio_risk_envelope=envelope)
    assert envelope.advances is False
    assert policy.envelope_digest == envelope.envelope_digest != world_envelope().envelope_digest
    assert policy.advances is True  # the consumer re-checks the envelope's own governance (RG-4 does)


# --- A. governed weights --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (rg2.d("0"), "performance_weight_not_positive"),
        (rg2.d("-0.1"), "performance_weight_not_positive"),
        ("0.6", "performance_weight_invalid"),
        ("6e-1", "performance_weight_invalid"),
        ("-" + rg2.d("0"), "performance_weight_invalid"),
        (" " + rg2.d("0.6"), "performance_weight_invalid"),
        ("9" * 42 + "." + "0" * 18, "performance_weight_invalid"),
        (0.6, "performance_weight_invalid"),
        (Fraction(3, 5), "performance_weight_invalid"),
        (1, "performance_weight_invalid"),
        (True, "performance_weight_invalid"),
        (None, "performance_weight_invalid"),
        (_Text(rg2.d("0.6")), "performance_weight_invalid"),
    ],
)
def test_each_weight_is_canonical_decimal_text_and_strictly_positive(value: object, code: str) -> None:
    alpha = PaperPortfolioPerformanceWeight("sleeve-alpha", value)  # type: ignore[arg-type]
    with _raises(code):
        build(performance_weights=[alpha, weight("sleeve-beta", "0.4")])


@pytest.mark.parametrize(
    ("alpha", "beta"),
    [
        pytest.param("0.6", "0.3", id="below_one"),
        pytest.param("0.6", "0.5", id="above_one"),
        pytest.param("0.6", "0.400000000000000001", id="one_unit_above"),
        pytest.param("0.6", "0.399999999999999999", id="one_unit_below"),
    ],
)
def test_weights_must_sum_to_exactly_one(alpha: str, beta: str) -> None:
    with _raises("performance_weights_sum_not_one"):
        build(performance_weights=[weight("sleeve-alpha", alpha), weight("sleeve-beta", beta)])


@pytest.mark.parametrize(
    ("alpha", "beta"),
    [("0.333333333333333333", "0.666666666666666667"), ("0.000000000000000001", "0.999999999999999999")],
)
def test_an_exact_sum_of_one_is_accepted_without_rounding(alpha: str, beta: str) -> None:
    policy = build(performance_weights=[weight("sleeve-alpha", alpha), weight("sleeve-beta", beta)])
    assert [item.performance_weight for item in policy.performance_weights] == [rg2.d(alpha), rg2.d(beta)]
    assert sum(Fraction(item.performance_weight) for item in policy.performance_weights) == 1
    _assert_intact(policy)


@pytest.mark.parametrize(
    ("weights", "code"),
    [
        pytest.param(None, "performance_weights_malformed", id="none"),
        pytest.param({"sleeve-alpha": rg2.d("1")}, "performance_weights_malformed", id="mapping"),
        pytest.param(_List(synthetic_weights()), "performance_weights_malformed", id="list_subclass"),
        pytest.param(frozenset(synthetic_weights()), "performance_weights_malformed", id="set"),
        pytest.param((item for item in synthetic_weights()), "performance_weights_malformed", id="generator"),
        pytest.param([], "performance_weights_missing", id="empty"),
        pytest.param([("sleeve-alpha", rg2.d("1"))], "performance_weight_malformed", id="tuple_record"),
        pytest.param(
            [_WeightSubclass("sleeve-alpha", rg2.d("0.6")), weight("sleeve-beta", "0.4")],
            "performance_weight_malformed",
            id="record_subclass",
        ),
    ],
)
def test_weights_are_an_exact_sequence_of_exact_records(weights: object, code: str) -> None:
    with _raises(code):
        build(performance_weights=weights)


@pytest.mark.parametrize(
    ("sleeve_id", "code"),
    [
        ("sleeve alpha", "sleeve_id_invalid"),
        ("", "sleeve_id_invalid"),
        ("-sleeve", "sleeve_id_invalid"),
        ("x" * 129, "sleeve_id_invalid"),
        (_Text("sleeve-alpha"), "sleeve_id_invalid"),
        ("bist-sleeve", "bist_scope_leakage:sleeve_id"),
    ],
)
def test_weight_sleeve_ids_follow_the_identifier_grammar(sleeve_id: object, code: str) -> None:
    alpha = PaperPortfolioPerformanceWeight(sleeve_id, rg2.d("0.6"))  # type: ignore[arg-type]
    with _raises(code):
        build(performance_weights=[alpha, weight("sleeve-beta", "0.4")])


def test_weight_order_and_sequence_type_do_not_change_the_policy() -> None:
    forward = build()
    assert build(performance_weights=list(reversed(synthetic_weights()))) == forward
    assert build(performance_weights=tuple(synthetic_weights())) == forward
    assert type(forward.performance_weights) is tuple
    assert [item.sleeve_id for item in forward.performance_weights] == ["sleeve-alpha", "sleeve-beta"]


def test_the_caller_sequence_is_read_once_and_never_mutated() -> None:
    supplied = list(reversed(synthetic_weights()))
    snapshot = list(supplied)
    build(performance_weights=supplied)
    assert supplied == snapshot


def test_weights_are_exactly_the_governed_values_whatever_the_envelope_budget_and_caps() -> None:
    baseline = build()
    for envelope in (
        rg2.governed(total_paper_risk_budget=rg2.d("1200")),
        rg2.governed(sleeve_caps=[rg2.sleeve("sleeve-alpha", "100"), rg2.sleeve("sleeve-beta", "900")]),
    ):
        policy = build(portfolio_risk_envelope=envelope)
        assert policy.performance_weights == baseline.performance_weights == tuple(synthetic_weights())
        assert policy.envelope_digest == envelope.envelope_digest != baseline.envelope_digest


def test_the_policy_never_reads_budgets_caps_or_reference_notionals() -> None:
    tree = ast.parse(Path(policy_module.__file__).read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "sleeve_caps" in attributes  # coverage reads the declared sleeve ids, never a cap value
    assert not attributes & {
        "max_paper_risk_budget",
        "total_paper_risk_budget",
        "market_caps",
        "correlation_cap",
        "paper_performance_reference_notional",
    }


def test_no_production_defaults_or_values_exist() -> None:
    signature = inspect.signature(build_paper_portfolio_performance_path_policy)
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    flags = dict(PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS)
    for record in (PaperPortfolioPerformanceWeight, PaperPortfolioPerformancePathApproval):
        assert all(item.default is dataclasses.MISSING for item in fields(record))
    assert all(
        item.default is dataclasses.MISSING
        for item in fields(PaperPortfolioPerformancePathPolicy)
        if item.name not in flags
    )
    args = policy_args()
    del args["performance_weights"]
    with pytest.raises(TypeError):
        build_paper_portfolio_performance_path_policy(**args)  # type: ignore[arg-type]
    tree = ast.parse(Path(policy_module.__file__).read_text(encoding="utf-8"))
    constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    numeric_text = re.compile(r"-?(?:[0-9]+\.[0-9]+|[0-9]{2,})")
    assert not [value for value in constants if type(value) is str and numeric_text.fullmatch(value)]
    # Slice and character bounds, representation bounds and the exact sum one; never a governed weight.
    structural = {0, 1, 18, 32, 60, 127, 128, 256, INT64_MAX}
    assert {value for value in constants if type(value) is int} <= structural


# --- H. digest, serialization and tamper ------------------------------------------------------------------------------


def test_rule_set_digest_commits_the_path_rules() -> None:
    rule_set = paper_portfolio_performance_path_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST
    assert build().rule_set_digest == PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST
    assert rule_set["rebalancing_convention"] == REBALANCING_CONVENTION
    for name, phrase in (
        ("index_rule_id", "fixed_weight_convex_combination"),
        ("initial_index_rule_id", "start_at_exactly_one"),
        ("weight_unit_id", "never_capital_budget_cap_or_reference_notional"),
        ("weight_rule_id", "strictly_positive_weight_per_envelope_declared_sleeve_summing_to_exactly_one"),
        ("coverage_rule_id", "equals_the_bound_envelope_sleeve_cap_set_exactly"),
        ("alignment_rule_id", "exact_same_ordered_utc_day_grid"),
        ("completeness_rule_id", "makes_the_path_not_computable"),
        ("observation_rule_id", "no_interpolation_no_carry_forward_no_future_observation"),
        ("gate_rule_id", "test_only_synthetic_never_advances"),
    ):
        assert phrase in str(rule_set[name]), name
    rule_set["rebalancing_convention"] = "DAILY_REBALANCE"
    assert paper_portfolio_performance_path_rule_set()["rebalancing_convention"] == REBALANCING_CONVENTION


def test_policy_digest_excludes_only_the_approval_verdict_and_digests() -> None:
    for policy in (build(), governed()):
        payload = paper_portfolio_performance_path_policy_to_dict(policy)
        governed_payload = {name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS}
        assert edge_sha256_text(edge_canonical_json(governed_payload)) == policy.policy_digest
        assert {"envelope_digest", "performance_weights", "rebalancing_convention", "live_ready"} <= set(
            governed_payload
        )


def test_payload_round_trips_and_digests_recompute() -> None:
    for policy in (build(), governed(), build(approval=approval_for(build(), kind=SYNTHETIC))):
        payload = json.loads(json.dumps(paper_portfolio_performance_path_policy_to_dict(policy)))
        assert paper_portfolio_performance_path_policy_payload_is_well_formed(payload) is True
        assert paper_portfolio_performance_path_policy_from_payload(payload) == policy
        assert paper_portfolio_performance_path_policy_digest(policy) == policy.performance_path_policy_digest
        _assert_intact(policy)


def test_stale_self_digest_is_rejected() -> None:
    verification = verify(replace(governed(), performance_path_policy_digest="0" * 64))
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"performance_weights": (weight("sleeve-alpha", "0.7"), weight("sleeve-beta", "0.3"))},
        {"envelope_digest": "e" * 64},
    ],
    ids=lambda change: next(iter(change)),
)
def test_resealed_governed_mutation_is_rejected(changes: dict[str, object]) -> None:
    verification = verify(_reseal(governed(), **changes))
    assert verification.intact is False
    assert _code("field_mismatch:policy_digest") in verification.reason_codes
    assert _code("field_mismatch:gate_verdict") in verification.reason_codes


def test_resealed_rebalancing_convention_is_rejected() -> None:
    verification = verify(_reseal(governed(), rebalancing_convention="DAILY_REBALANCE_V1"))
    assert verification.intact is False
    assert verification.reason_codes == (
        _code("field_mismatch:performance_path_policy_digest"),
        _code("field_mismatch:rebalancing_convention"),
    )


@pytest.mark.parametrize(
    "weights",
    [
        pytest.param((weight("sleeve-alpha", "0.6"), weight("sleeve-beta", "0.6")), id="sum_above_one"),
        pytest.param((weight("sleeve-alpha", "1"), weight("sleeve-beta", "0")), id="zero_weight"),
        pytest.param((weight("sleeve-alpha", "0.6"), weight("sleeve-alpha", "0.4")), id="duplicate"),
    ],
)
def test_resealed_weights_the_builder_refuses_fail_reassembly(weights: tuple[object, ...]) -> None:
    verification = verify(_reseal(governed(), performance_weights=weights))
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_reassembly_failed"),)


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(None, id="none"),
        pytest.param("policy", id="str"),
        pytest.param({}, id="dict"),
        pytest.param(object.__new__(PaperPortfolioPerformancePathPolicy), id="uninitialized"),
        pytest.param(_corrupted(gate_verdict="PASS"), id="verdict_alias"),
        pytest.param(_corrupted(performance_weights=synthetic_weights()), id="weights_list"),
        pytest.param(_corrupted(performance_weights=()), id="weights_removed"),
        pytest.param(
            _corrupted(
                performance_weights=(PaperPortfolioPerformanceWeight("sleeve-alpha", 0.6), weight("sleeve-beta", "0.4"))
            ),
            id="float_weight",
        ),
        pytest.param(
            _corrupted(
                performance_weights=(_WeightSubclass("sleeve-alpha", rg2.d("0.6")), weight("sleeve-beta", "0.4"))
            ),
            id="weight_subclass",
        ),
        pytest.param(_corrupted(approval=None), id="approval_removed"),
        pytest.param(_corrupted(advances=False), id="advances_flipped"),
        pytest.param(_corrupted(rule_set_digest="0" * 64), id="rule_set_digest"),
        pytest.param(_corrupted(verdict_reason_codes=["x"]), id="reason_list"),
        pytest.param(_corrupted(policy_id=_Text("rg4-synthetic-performance-path")), id="text_subclass"),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("performance_weights", 0, "performance_weight"), "0.6"),
        (("performance_weights", 0, "performance_weight"), 0.6),
        (("performance_weights", 0, "sleeve_id"), None),
        (("performance_weights",), {"sleeve-alpha": "0.6"}),
        (("approval", "approval_kind"), "ROBOT"),
        (("gate_verdict",), "ACCEPTED"),
        (("advances",), "true"),
        (("live_ready",), None),
        (("risk_budget_used_as_weight",), 0),
    ],
    ids=lambda value: str(value)[:40],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = json.loads(json.dumps(paper_portfolio_performance_path_policy_to_dict(governed())))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert paper_portfolio_performance_path_policy_payload_is_well_formed(payload) is False


def test_parser_requires_exactly_the_policy_fields() -> None:
    payload = json.loads(json.dumps(paper_portfolio_performance_path_policy_to_dict(governed())))
    assert paper_portfolio_performance_path_policy_payload_is_well_formed({**payload, "allocation": "x"}) is False
    del payload["rebalancing_convention"]
    assert paper_portfolio_performance_path_policy_payload_is_well_formed(payload) is False


def test_policy_is_frozen() -> None:
    policy = governed()
    with pytest.raises(FrozenInstanceError):
        policy.advances = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.performance_weights[0].performance_weight = rg2.d("1")  # type: ignore[misc]


# --- G. safety ------------------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(PAPER_PORTFOLIO_PERFORMANCE_PATH_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    assert POLICY_FLAGS <= set(flags)
    assert flags["paper_only"] is True
    assert not [name for name, value in flags.items() if value and name != "paper_only"]
    defaults = {item.name: item.default for item in fields(PaperPortfolioPerformancePathPolicy) if item.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_paper_portfolio_performance_path_policy).parameters)


@pytest.mark.parametrize(
    "flag",
    [
        "portfolio_allocation_approved",
        "risk_budget_used_as_weight",
        "reference_notional_used_as_weight",
        "capital_represented",
        "execution_authorized",
        "live_ready",
    ],
)
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify(_reseal(governed(), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_module_is_pure_and_consumes_only_the_edge_kernel_and_the_envelope() -> None:
    pit.assert_module_is_pure(
        policy_module,
        {"crypto_core.validation.edge_artifact_core", "crypto_core.validation.paper_portfolio_risk_envelope"},
    )


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        policy_module,
        "PaperPortfolioPerformancePathPolicy",
        "_assemble_policy",
        "build_paper_portfolio_performance_path_policy",
        "_reassemble_policy",
    )


def test_public_api_is_exact() -> None:
    assert set(policy_module.__all__) == {
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
    }


# --- I. document authority ------------------------------------------------------------------------------------------


def test_design_doc_records_the_rg4_prerequisite_and_the_path_rules() -> None:
    text = _doc("multi_sleeve_risk_governance_design.md")
    rg4 = text[text.index("3. **RG-4") : text.index("4. **RG-5")]
    for phrase in (
        "Prerequisite: the governed `paper_portfolio_performance_path_policy.py`",
        "(strictly positive, exact sum 1, GOVERNANCE_REQUIRED)",
        "never allocation, capital, risk-budget, cap or `paper_performance_reference_notional` semantics",
        "`P_t = sum_i(w_i * I_i,t)`",
        "fixed initial weights and no rebalance within the evidence window",
        "(`NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1`), so `P_0 = 1`",
        "on the exact same ordered UTC-day grid",
        "a missing or uncomputable sleeve makes the portfolio NOT_COMPUTABLE",
        "nothing is dropped, interpolated or carried forward",
        "the start index 1 is the first running-peak observation",
        "both the current (end-of-window) and the maximum peak distance",
        "and decides nothing",
    ):
        assert phrase in rg4, phrase
    assert "RG-6 owns how ladder thresholds consume RG-4 sleeve drawdown evidence" in text
    assert "RG-8 owns how portfolio-stop levels consume RG-4 portfolio drawdown evidence" in text
    governance = text[text.index("## 3. GOVERNANCE_REQUIRED") : text.index("## 4.")]
    assert "portfolio performance weights (`paper_portfolio_performance_path_policy.py`)" in governance
    assert "RG-4 needs merged RG-3 plus the governed `paper_portfolio_performance_path_policy.py`" in text


def test_governance_framework_lists_the_weights_as_governance_required_without_a_number() -> None:
    lines = (DOCS / "governance_decision_framework.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("## 5. RG"))
    end = next(index for index, line in enumerate(lines) if line.startswith("## 6."))
    rows = [line for line in lines[start:end] if line.startswith("| portfolio performance weights")]
    assert len(rows) == 1
    row = rows[0]
    for phrase in (
        "(consumer: `paper_portfolio_performance_path_policy.py`)",
        "synthetic performance weights only",
        "never derived from or read as budgets, caps, reference notionals, capital or RG-7 allocation",
        "strictly positive",
        "exact sum one",
        "fixed for the evidence window",
    ):
        assert phrase in row, phrase
    assert not re.search(r"[0-9]", re.sub(r"RG-[0-9]", "", row))
