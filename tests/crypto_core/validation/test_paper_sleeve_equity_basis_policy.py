"""Paper sleeve equity-basis policy tests (PAPER_SLEEVE_EQUITY_BASIS_AND_VALUATION_POLICY_V1).

SYNTHETIC TEST VALUES ONLY. Every reference notional, identifier and approval in this file is a synthetic test value
that exercises structure. None is a production value and none is production-approved. The ``HUMAN_GOVERNANCE``
approvals built here are synthetic test fixtures for the PASS branch only.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_equity_basis_policy as policy_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodologyStatus,
    build_paper_return_series_methodology,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST,
    PaperSleeveEquityBasisApproval,
    PaperSleeveEquityBasisApprovalKind,
    PaperSleeveEquityBasisPolicy,
    PaperSleeveEquityBasisPolicyError,
    PaperSleeveFundingTreatment,
    build_paper_sleeve_equity_basis_policy,
    paper_sleeve_equity_basis_methodology_policy_ids,
    paper_sleeve_equity_basis_policy_digest,
    paper_sleeve_equity_basis_policy_from_payload,
    paper_sleeve_equity_basis_policy_payload_is_well_formed,
    paper_sleeve_equity_basis_policy_to_dict,
    paper_sleeve_equity_basis_rule_set,
    verify_paper_sleeve_equity_basis_policy,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "paper_sleeve_equity_basis_policy"
INT64_MAX = 9223372036854775807
HUMAN = PaperSleeveEquityBasisApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperSleeveEquityBasisApprovalKind.TEST_ONLY_SYNTHETIC
REQUIRED = PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED
NOT_APPLICABLE = PaperSleeveFundingTreatment.GOVERNED_NOT_APPLICABLE
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


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleeveEquityBasisPolicyError, match=re.escape(_code(code)))


def d(text: str) -> str:
    """A SYNTHETIC TEST VALUE rendered as canonical scale-18 decimal text."""

    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    rendered = f"{integer}.{fraction.ljust(18, '0')}"
    return f"-{rendered}" if negative else rendered


def policy_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "policy_id": "sleeve-basis-policy",
        "policy_version": "synthetic-v1",
        "sleeve_id": "sleeve-alpha",
        "market_symbol": "BTC-PERPETUAL",
        "paper_performance_reference_notional": d("1000"),
        "funding_treatment": REQUIRED,
        "approval": None,
    }
    args.update(overrides)
    return args


def build(**overrides: object) -> PaperSleeveEquityBasisPolicy:
    return build_paper_sleeve_equity_basis_policy(**policy_args(**overrides))  # type: ignore[arg-type]


def approval_for(
    policy: PaperSleeveEquityBasisPolicy, *, kind: object = HUMAN, **overrides: object
) -> PaperSleeveEquityBasisApproval:
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
    return PaperSleeveEquityBasisApproval(**values)  # type: ignore[arg-type]


def governed(**overrides: object) -> PaperSleeveEquityBasisPolicy:
    """A policy under an exact synthetic HUMAN_GOVERNANCE test approval (PASS-branch fixture only)."""

    return build(approval=approval_for(build(**overrides)), **overrides)


def verify(policy: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_equity_basis_policy(policy)


def _reseal(policy: PaperSleeveEquityBasisPolicy, **changes: object) -> PaperSleeveEquityBasisPolicy:
    changed = replace(policy, **changes)
    return replace(changed, equity_basis_digest=paper_sleeve_equity_basis_policy_digest(changed))


def _corrupted(**changes: object) -> PaperSleeveEquityBasisPolicy:
    copy = replace(governed())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def _assert_intact(policy: PaperSleeveEquityBasisPolicy) -> None:
    verification = verify(policy)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == policy.equity_basis_digest
    assert paper_sleeve_equity_basis_policy_from_payload(json.loads(verification.canonical_json)) == policy


# --- governance and advancement ---------------------------------------------------------------------------------------


def test_unapproved_policy_is_valid_structure_that_needs_governance_approval() -> None:
    policy = build()
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert policy.advances is False
    assert policy.verdict_reason_codes == (_code("governance_approval_missing"),)
    assert policy.synthetic_test_approval_used is False
    _assert_intact(policy)


def test_exact_human_governance_approval_passes_without_changing_the_policy_digest() -> None:
    unapproved = build()
    policy = build(approval=approval_for(unapproved))
    assert policy.gate_verdict is EdgeGateVerdict.PASS
    assert policy.advances is True
    assert policy.verdict_reason_codes == ()
    assert policy.policy_digest == unapproved.policy_digest
    assert policy.equity_basis_digest != unapproved.equity_basis_digest
    _assert_intact(policy)


def test_test_only_synthetic_approval_binds_exactly_but_never_advances() -> None:
    policy = build(approval=approval_for(build(), kind=SYNTHETIC))
    assert policy.advances is False
    assert policy.synthetic_test_approval_used is True
    assert policy.verdict_reason_codes == (_code("governance_approval_test_only_synthetic"),)
    _assert_intact(policy)


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


@pytest.mark.parametrize(
    "change",
    [
        {"sleeve_id": "sleeve-beta"},
        {"market_symbol": "ETH-PERPETUAL"},
        {"paper_performance_reference_notional": d("1000.5")},
        {"funding_treatment": NOT_APPLICABLE},
    ],
    ids=lambda change: next(iter(change)),
)
def test_any_governed_value_change_makes_an_earlier_approval_stale(change: dict[str, object]) -> None:
    approved = governed()
    changed = build(approval=approved.approval, **change)
    assert changed.policy_digest != approved.policy_digest
    assert changed.advances is False
    assert changed.verdict_reason_codes == (_code("governance_approval_policy_digest_mismatch"),)
    _assert_intact(changed)


def test_approval_for_another_sleeve_never_advances_this_sleeve() -> None:
    other = build(sleeve_id="sleeve-beta")
    policy = build(approval=approval_for(other))
    assert policy.advances is False
    assert _code("governance_approval_policy_digest_mismatch") in policy.verdict_reason_codes


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
    assert type(policy.approval.approval_kind) is PaperSleeveEquityBasisApprovalKind
    assert policy.advances is True


# --- governed values ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (d("0"), "paper_performance_reference_notional_not_positive"),
        (d("-1"), "paper_performance_reference_notional_not_positive"),
        ("1000", "paper_performance_reference_notional_invalid"),
        ("1e3", "paper_performance_reference_notional_invalid"),
        ("-" + d("0"), "paper_performance_reference_notional_invalid"),
        ("9" * 42 + "." + "0" * 18, "paper_performance_reference_notional_invalid"),
        (1000, "paper_performance_reference_notional_invalid"),
        (1000.0, "paper_performance_reference_notional_invalid"),
        (True, "paper_performance_reference_notional_invalid"),
        (None, "paper_performance_reference_notional_invalid"),
        (_Text(d("1000")), "paper_performance_reference_notional_invalid"),
    ],
)
def test_reference_notional_must_be_canonical_and_strictly_positive(value: object, code: str) -> None:
    with _raises(code):
        build(paper_performance_reference_notional=value)


@pytest.mark.parametrize("value", ["0." + "0" * 17 + "1", "9" * 41 + "." + "0" * 18])
def test_reference_notional_representation_boundaries_are_accepted(value: str) -> None:
    assert build(paper_performance_reference_notional=value).paper_performance_reference_notional == value


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"funding_treatment": "IMPLICIT_ZERO"}, "funding_treatment_invalid"),
        ({"funding_treatment": None}, "funding_treatment_invalid"),
        ({"funding_treatment": _Text("FUNDING_EVIDENCE_REQUIRED")}, "funding_treatment_invalid"),
        ({"sleeve_id": "sleeve alpha"}, "sleeve_id_invalid"),
        ({"sleeve_id": "bist-sleeve"}, "bist_scope_leakage:sleeve_id"),
        ({"sleeve_id": "x" * 129}, "sleeve_id_invalid"),
        ({"market_symbol": "BTC PERP"}, "market_symbol_invalid"),
        ({"market_symbol": "x" * 65}, "market_symbol_invalid"),
        ({"policy_id": ""}, "policy_id_invalid"),
        ({"policy_version": "live-v1"}, "forbidden_scope_token:policy_version"),
    ],
)
def test_governed_identity_and_treatment_are_validated(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(**overrides)


def test_funding_treatment_text_is_canonicalized_to_the_exact_member() -> None:
    policy = build(funding_treatment="GOVERNED_NOT_APPLICABLE")
    assert policy.funding_treatment is NOT_APPLICABLE
    _assert_intact(policy)


def test_no_production_defaults_or_values_exist() -> None:
    signature = inspect.signature(build_paper_sleeve_equity_basis_policy)
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    flags = dict(PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS)
    assert all(item.default is dataclasses.MISSING for item in fields(PaperSleeveEquityBasisApproval))
    assert all(
        item.default is dataclasses.MISSING for item in fields(PaperSleeveEquityBasisPolicy) if item.name not in flags
    )
    tree = ast.parse(Path(policy_module.__file__).read_text(encoding="utf-8"))
    constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    numeric_text = re.compile(r"-?(?:[0-9]+\.[0-9]+|[0-9]{2,})")
    assert not [value for value in constants if type(value) is str and numeric_text.fullmatch(value)]
    # Slice and character bounds, representation bounds and the UTC day; never a governed number.
    structural = {0, 1, 18, 32, 60, 64, 127, 128, 256, 4000, 86_400_000_000_000, INT64_MAX}
    assert {value for value in constants if type(value) is int} <= structural


# --- methodology binding ----------------------------------------------------------------------------------------------


def test_methodology_policy_ids_bind_the_exact_policy_digest() -> None:
    policy = governed()
    ids = paper_sleeve_equity_basis_methodology_policy_ids(policy)
    assert set(ids) == {
        "mtm_policy_id",
        "fee_policy_id",
        "funding_policy_id",
        "mark_policy_id",
        "exposure_policy_id",
        "liquidation_policy_id",
    }
    assert all(policy.policy_digest in value for value in ids.values())
    assert ids == paper_sleeve_equity_basis_methodology_policy_ids(build())
    assert ids != paper_sleeve_equity_basis_methodology_policy_ids(
        build(paper_performance_reference_notional=d("2000"))
    )
    methodology = build_paper_return_series_methodology(
        methodology_id="sleeve-method-1",
        correlation_id="corr-ep",
        risk_free_policy_id="constant_zero_daily_review_only.v1",
        **ids,
    )
    assert methodology.status is PaperReturnSeriesMethodologyStatus.READY


@pytest.mark.parametrize("candidate", [None, "policy", replace(build(), policy_digest="not-a-digest")])
def test_methodology_policy_ids_refuse_malformed_policies(candidate: object) -> None:
    with _raises("policy_malformed"):
        paper_sleeve_equity_basis_methodology_policy_ids(candidate)  # type: ignore[arg-type]


# --- digest and serialization -----------------------------------------------------------------------------------------


def test_rule_set_digest_commits_the_rule_set_the_valuation_reads() -> None:
    rule_set = paper_sleeve_equity_basis_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST
    assert build().rule_set_digest == PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST
    assert rule_set["mark_rule_id"] == "exact_bucket_end_mark_snapshot_bound_into_reconstructed_close_pnl_report.v1"
    assert "never_implicit_zero" in str(rule_set["funding_rule_id"])
    assert "never_account_value_or_risk_budget" in str(rule_set["reference_notional_rule_id"])
    assert rule_set["decimal_scale"] == 18
    rule_set["decimal_scale"] = 2
    assert paper_sleeve_equity_basis_rule_set()["decimal_scale"] == 18


def test_policy_digest_excludes_only_the_approval_verdict_and_digests() -> None:
    payload = paper_sleeve_equity_basis_policy_to_dict(governed())
    governed_payload = {name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS}
    assert edge_sha256_text(edge_canonical_json(governed_payload)) == governed().policy_digest


def test_payload_round_trips_and_digests_recompute() -> None:
    for policy in (build(), governed(), build(approval=approval_for(build(), kind=SYNTHETIC))):
        payload = json.loads(json.dumps(paper_sleeve_equity_basis_policy_to_dict(policy)))
        assert paper_sleeve_equity_basis_policy_payload_is_well_formed(payload) is True
        assert paper_sleeve_equity_basis_policy_from_payload(payload) == policy
        assert paper_sleeve_equity_basis_policy_digest(policy) == policy.equity_basis_digest
        _assert_intact(policy)


def test_stale_self_digest_is_rejected() -> None:
    verification = verify(replace(governed(), equity_basis_digest="0" * 64))
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"paper_performance_reference_notional": d("5000")},
        {"sleeve_id": "sleeve-beta"},
        {"funding_treatment": NOT_APPLICABLE},
    ],
    ids=lambda change: next(iter(change)),
)
def test_resealed_semantic_mutation_is_rejected(changes: dict[str, object]) -> None:
    verification = verify(_reseal(governed(), **changes))
    assert verification.intact is False
    assert _code("field_mismatch:policy_digest") in verification.reason_codes
    assert _code("field_mismatch:gate_verdict") in verification.reason_codes


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(None, id="none"),
        pytest.param("policy", id="str"),
        pytest.param({}, id="dict"),
        pytest.param(object.__new__(PaperSleeveEquityBasisPolicy), id="uninitialized"),
        pytest.param(_corrupted(gate_verdict="PASS"), id="verdict_alias"),
        pytest.param(_corrupted(funding_treatment="FUNDING_EVIDENCE_REQUIRED"), id="treatment_alias"),
        pytest.param(_corrupted(paper_performance_reference_notional=1000.0), id="float_notional"),
        pytest.param(_corrupted(approval=None), id="approval_removed"),
        pytest.param(_corrupted(advances=False), id="advances_flipped"),
        pytest.param(_corrupted(rule_set_digest="0" * 64), id="rule_set_digest"),
        pytest.param(_corrupted(verdict_reason_codes=["x"]), id="reason_list"),
        pytest.param(_corrupted(sleeve_id=_Text("sleeve-alpha")), id="text_subclass"),
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
        (("paper_performance_reference_notional",), "1000"),
        (("funding_treatment",), "IMPLICIT_ZERO"),
        (("approval", "approval_kind"), "ROBOT"),
        (("gate_verdict",), "ACCEPTED"),
        (("advances",), "true"),
        (("live_ready",), None),
    ],
    ids=lambda value: str(value)[:30],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[str, ...], value: object) -> None:
    payload = json.loads(json.dumps(paper_sleeve_equity_basis_policy_to_dict(governed())))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert paper_sleeve_equity_basis_policy_payload_is_well_formed(payload) is False


def test_policy_is_frozen() -> None:
    policy = governed()
    with pytest.raises(FrozenInstanceError):
        policy.advances = False  # type: ignore[misc]


# --- safety ----------------------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(PAPER_SLEEVE_EQUITY_BASIS_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    assert {
        "account_equity_represented",
        "capital_represented",
        "risk_budget_used_as_denominator",
        "historical_economics_consumed",
        "execution_authorized",
    } <= set(flags)
    defaults = {item.name: item.default for item in fields(PaperSleeveEquityBasisPolicy) if item.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_paper_sleeve_equity_basis_policy).parameters)


@pytest.mark.parametrize("flag", ["account_equity_represented", "risk_budget_used_as_denominator", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify(_reseal(governed(), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_module_is_pure_and_consumes_only_the_edge_kernel() -> None:
    pit.assert_module_is_pure(policy_module, {"crypto_core.validation.edge_artifact_core"})


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        policy_module,
        "PaperSleeveEquityBasisPolicy",
        "_assemble_policy",
        "build_paper_sleeve_equity_basis_policy",
        "_reassemble_policy",
    )


def test_public_api_is_exact() -> None:
    assert set(policy_module.__all__) == {
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
    }
