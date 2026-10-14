"""Tests for the governed cumulative trial-count chain (EDGE_TRIAL_COUNT_CHAIN_V1).

Links re-prove REAL sealed EF-5 preregistrations of the EF-6 module (world A's ledger ``A``) and of the pre-paper module
(world P's nine-variant star grid). Every genesis count, approval and attestation below is a SYNTHETIC TEST VALUE: the
pre-genesis count E1 is a human fact this code never knows, and no production genesis exists.
"""

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest

from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
)
from crypto_core.validation.edge_trial_count_chain import (
    EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS,
    EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST,
    EdgeTrialCountApprovalKind,
    EdgeTrialCountChain,
    EdgeTrialCountChainError,
    EdgeTrialCountCurrentnessAttestation,
    build_edge_trial_count_chain,
    build_edge_trial_count_genesis,
    canonical_edge_trial_count_currentness_attestation,
    edge_trial_count_chain_digest,
    edge_trial_count_chain_from_payload,
    edge_trial_count_chain_payload_is_well_formed,
    edge_trial_count_chain_rule_set,
    edge_trial_count_chain_to_dict,
    edge_trial_count_currentness_reasons,
    extend_edge_trial_count_chain,
    verify_edge_trial_count_chain,
)

try:  # the module objects pytest collects (basename import), so the authentic worlds and memos are built once
    import test_edge_pre_paper_validation_evidence as pret
    import test_edge_walk_forward_oos_evidence as ef6t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_pre_paper_validation_evidence as pret
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t

_PREFIX = "edge_trial_count_chain"
HUMAN = EdgeTrialCountApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = EdgeTrialCountApprovalKind.TEST_ONLY_SYNTHETIC


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        pret.apply_memos(patch)
        yield


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def chain(*preregistrations, record=None, approval: object = "auto", chain_id: str = "trial-chain-1"):
    record = pret.genesis() if record is None else record
    return build_edge_trial_count_chain(
        chain_id=chain_id,
        genesis=record,
        genesis_approval=pret.genesis_approval(record) if approval == "auto" else approval,
        preregistrations=preregistrations,
        expected_preregistration_digests=tuple(item.leakage_bias_evidence_digest for item in preregistrations),
    )


def _assert_intact(value: EdgeTrialCountChain) -> None:
    verification = verify_edge_trial_count_chain(value)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == value.chain_digest == edge_trial_count_chain_digest(value)
    payload = json.loads(verification.canonical_json)
    assert edge_trial_count_chain_payload_is_well_formed(payload)
    assert edge_trial_count_chain_from_payload(payload) == value
    assert {name: getattr(value, name) for name, _ in EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS} == dict(
        EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS
    )


def _reseal(value: EdgeTrialCountChain, **changes: object) -> EdgeTrialCountChain:
    changed = replace(value, **changes)
    return replace(changed, chain_digest=edge_trial_count_chain_digest(changed))


# --- genesis --------------------------------------------------------------------------------------------------------------


def test_genesis_is_explicit_sealed_and_never_defaulted() -> None:
    record = pret.genesis()
    assert record.pre_genesis_trial_count == 3
    assert record.genesis_digest == edge_payload_digest(
        {item.name: getattr(record, item.name) for item in fields(record)}, "genesis_digest"
    )
    zero = build_edge_trial_count_genesis(
        genesis_id="trial-genesis-0", pre_genesis_trial_count=0, pre_genesis_evidence_reference="test-fixture:zero"
    )
    assert zero.pre_genesis_trial_count == 0 and zero.genesis_digest != record.genesis_digest


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"pre_genesis_trial_count": -1}, "pre_genesis_trial_count_invalid"),
        ({"pre_genesis_trial_count": True}, "pre_genesis_trial_count_invalid"),
        ({"pre_genesis_trial_count": 2**63}, "pre_genesis_trial_count_invalid"),
        ({"pre_genesis_trial_count": None}, "pre_genesis_trial_count_invalid"),
        ({"genesis_id": "Genesis"}, "genesis_id_invalid"),
        ({"pre_genesis_evidence_reference": ""}, "pre_genesis_evidence_reference_invalid"),
        ({"pre_genesis_evidence_reference": "live attestation"}, "forbidden_scope_token"),
    ],
)
def test_malformed_genesis_is_refused(changes: dict[str, object], code: str) -> None:
    values: dict[str, object] = {
        "genesis_id": "trial-genesis-1",
        "pre_genesis_trial_count": 3,
        "pre_genesis_evidence_reference": "test-fixture:x",
        **changes,
    }
    with pytest.raises(EdgeTrialCountChainError, match=code):
        build_edge_trial_count_genesis(**values)  # type: ignore[arg-type]


def test_a_forged_genesis_digest_is_refused() -> None:
    with pytest.raises(EdgeTrialCountChainError, match="genesis_digest_mismatch"):
        chain(pret.ef5_p(), record=replace(pret.genesis(), pre_genesis_trial_count=0))


# --- links and cumulative counts ----------------------------------------------------------------------------------------------


def test_one_link_chain_counts_the_pre_genesis_trials_plus_the_sealed_ledger() -> None:
    value = chain(pret.ef5_p())
    _assert_intact(value)
    assert (value.status, value.gate_verdict, value.advances) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.PASS, True)
    (link,) = value.links
    assert (link.link_index, link.prior_digest) == (0, pret.genesis().genesis_digest)
    assert (link.preregistration_digest, link.multiple_testing_count) == (pret.ef5_p().leakage_bias_evidence_digest, 9)
    assert link.cumulative_trial_count == value.head_cumulative_trial_count == 3 + 9
    assert value.head_digest == link.link_digest and value.link_count == 1
    assert value.rule_set_digest == EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST
    assert value.synthetic_test_approval_used is False


def test_links_are_chained_monotone_and_an_extension_keeps_every_prior_link_byte_identical() -> None:
    first = chain(ef6t.ef5("A"))
    second = extend_edge_trial_count_chain(
        first,
        expected_prior_chain_digest=first.chain_digest,
        preregistration=pret.ef5_p(),
        expected_preregistration_digest=pret.ef5_p().leakage_bias_evidence_digest,
    )
    _assert_intact(second)
    assert second.links[0] == first.links[0]
    assert second.links[1].prior_digest == first.links[0].link_digest
    assert [item.cumulative_trial_count for item in second.links] == [3 + 1, 3 + 1 + 9]
    assert second == chain(ef6t.ef5("A"), pret.ef5_p())


def test_the_same_preregistration_twice_is_rejected() -> None:
    value = chain(pret.ef5_p(), pret.ef5_p())
    _assert_intact(value)
    assert value.status is EdgeEvidenceStatus.REJECTED
    assert value.integrity_reason_codes == (_code("link_1:preregistration_duplicate"),)
    assert value.links == () and value.gate_verdict is EdgeGateVerdict.NOT_EVALUATED


def test_an_unsealed_preregistration_is_rejected() -> None:
    unsealed = ef6t.ef5("A", approve=False)
    value = chain(unsealed)
    assert value.status is EdgeEvidenceStatus.REJECTED
    assert value.integrity_reason_codes == (_code("link_0:preregistration_not_sealed"),)


def test_a_cumulative_count_beyond_int64_is_rejected() -> None:
    record = build_edge_trial_count_genesis(
        genesis_id="trial-genesis-big",
        pre_genesis_trial_count=2**63 - 5,
        pre_genesis_evidence_reference="test-fixture:big",
    )
    value = chain(pret.ef5_p(), record=record)
    assert value.integrity_reason_codes == (_code("link_0:cumulative_trial_count_out_of_range"),)


def test_a_preregistration_anchor_mismatch_is_rejected() -> None:
    value = build_edge_trial_count_chain(
        chain_id="trial-chain-1",
        genesis=pret.genesis(),
        genesis_approval=pret.genesis_approval(),
        preregistrations=(pret.ef5_p(),),
        expected_preregistration_digests=("0" * 64,),
    )
    assert value.integrity_reason_codes == (_code("link_0:preregistration_digest_mismatch"),)


def test_an_empty_chain_is_its_governed_genesis() -> None:
    value = chain()
    _assert_intact(value)
    assert (value.link_count, value.head_digest) == (0, pret.genesis().genesis_digest)
    assert value.head_cumulative_trial_count == 3


# --- governance ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("approval", "codes"),
    [
        (None, ("genesis_approval_missing",)),
        ("synthetic", ("genesis_approval_not_human_governance",)),
        ("foreign", ("genesis_approval_genesis_digest_mismatch",)),
        ("rules", ("genesis_approval_rule_set_digest_mismatch",)),
    ],
)
def test_only_an_exact_human_governance_genesis_approval_advances(approval: object, codes: tuple[str, ...]) -> None:
    record = pret.genesis()
    value = {
        None: None,
        "synthetic": pret.genesis_approval(record, approval_kind=SYNTHETIC),
        "foreign": pret.genesis_approval(record, approved_genesis_digest="f" * 64),
        "rules": pret.genesis_approval(record, approved_rule_set_digest="f" * 64),
    }[approval]  # type: ignore[index]
    result = chain(pret.ef5_p(), approval=value)
    _assert_intact(result)
    assert (result.status, result.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL)
    assert result.verdict_reason_codes == tuple(_code(code) for code in codes)
    assert result.synthetic_test_approval_used is (approval == "synthetic")


def test_extending_a_non_advancing_or_non_authentic_prior_is_refused() -> None:
    unapproved = chain(ef6t.ef5("A"), approval=None)
    with pytest.raises(EdgeTrialCountChainError, match="prior_chain_not_advancing"):
        extend_edge_trial_count_chain(
            unapproved,
            expected_prior_chain_digest=unapproved.chain_digest,
            preregistration=pret.ef5_p(),
            expected_preregistration_digest=pret.ef5_p().leakage_bias_evidence_digest,
        )
    with pytest.raises(EdgeTrialCountChainError, match="prior_chain_not_authentic"):
        extend_edge_trial_count_chain(
            chain(ef6t.ef5("A")),
            expected_prior_chain_digest="0" * 64,
            preregistration=pret.ef5_p(),
            expected_preregistration_digest=pret.ef5_p().leakage_bias_evidence_digest,
        )


# --- verification ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        lambda v: {"head_cumulative_trial_count": v.head_cumulative_trial_count - 1},
        lambda v: {"links": (replace(v.links[0], cumulative_trial_count=4),)},
        lambda v: {"links": (replace(v.links[0], multiple_testing_count=1),)},
        lambda v: {"gate_verdict": EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, "advances": False},
        lambda v: {"genesis_approval": None},
        lambda v: {"head_digest": "f" * 64},
    ],
)
def test_a_resealed_forged_chain_never_verifies(changes) -> None:
    value = chain(pret.ef5_p())
    verification = verify_edge_trial_count_chain(_reseal(value, **changes(value)))
    assert verification.intact is False
    assert any(code.startswith(_code("field_mismatch:")) for code in verification.reason_codes)


def test_the_strict_parser_refuses_extra_missing_and_mistyped_fields() -> None:
    payload = json.loads(edge_canonical_json(edge_trial_count_chain_to_dict(chain(pret.ef5_p()))))
    assert edge_trial_count_chain_payload_is_well_formed(payload)
    for mutate in (
        lambda p: p.update({"extra": 1}),
        lambda p: p.pop("links"),
        lambda p: p.update({"link_count": "1"}),
        lambda p: p["links"][0].update({"cumulative_trial_count": True}),
        lambda p: p.update({"off_chain_trial_completeness_proven": 1}),
    ):
        broken = json.loads(json.dumps(payload))
        mutate(broken)
        assert edge_trial_count_chain_payload_is_well_formed(broken) is False


def test_rule_set_records_the_completeness_non_claim() -> None:
    rules = edge_trial_count_chain_rule_set()
    assert rules["authority_id"] == "EDGE_TRIAL_COUNT_CHAIN_V1"
    assert "off_chain" in str(rules["completeness_non_claim_id"])


# --- currentness ---------------------------------------------------------------------------------------------------------------


def _attestation(value: EdgeTrialCountChain, **changes: object) -> EdgeTrialCountCurrentnessAttestation:
    return pret.attestation_for(value, preregistration_digest=pret.ef5_p().leakage_bias_evidence_digest, **changes)


def _reasons(value: EdgeTrialCountChain, attestation: object) -> list[str]:
    return edge_trial_count_currentness_reasons(
        attestation,  # type: ignore[arg-type]
        chain=value,
        evaluation_id=pret.EVIDENCE_ID,
        correlation_id="corr-1",
        preregistration_digest=pret.ef5_p().leakage_bias_evidence_digest,
    )


def test_an_exact_human_attestation_establishes_currentness() -> None:
    value = chain(pret.ef5_p())
    assert _reasons(value, _attestation(value)) == []
    assert _reasons(value, None) == [_code("currentness_attestation_missing")]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"approval_kind": SYNTHETIC}, "currentness_attestation_not_human_governance"),
        ({"attested_chain_id": "trial-chain-2"}, "currentness_attestation_chain_id_mismatch"),
        ({"attested_chain_digest": "f" * 64}, "currentness_attestation_chain_digest_mismatch"),
        ({"attested_head_digest": "f" * 64}, "currentness_attestation_head_digest_mismatch"),
        ({"attested_cumulative_trial_count": 11}, "currentness_attestation_cumulative_trial_count_mismatch"),
        ({"attested_evaluation_id": "pre-paper-9"}, "currentness_attestation_evaluation_id_mismatch"),
        ({"attested_correlation_id": "corr-9"}, "currentness_attestation_correlation_id_mismatch"),
        ({"attested_preregistration_digest": "f" * 64}, "currentness_attestation_preregistration_digest_mismatch"),
        ({"no_off_chain_trial_attested": False}, "currentness_attestation_off_chain_trials_not_excluded"),
    ],
)
def test_every_currentness_commitment_must_match(changes: dict[str, object], code: str) -> None:
    value = chain(pret.ef5_p())
    assert _reasons(value, _attestation(value, **changes)) == [_code(code)]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"attestation_digest": "X" * 64}, "currentness_attestation_digest_invalid"),
        ({"approval_kind": "HUMAN_GOVERNANCE"}, "currentness_attestation_kind_invalid"),
        ({"attested_at_ns": 0}, "currentness_attestation_attested_at_ns_invalid"),
        ({"attested_at_ns": True}, "currentness_attestation_attested_at_ns_invalid"),
        ({"no_off_chain_trial_attested": 1}, "currentness_attestation_no_off_chain_trial_attested_invalid"),
        ({"attested_cumulative_trial_count": -1}, "currentness_attested_cumulative_trial_count_invalid"),
        ({"attestation_reference": "scheduler note"}, "forbidden_scope_token"),
    ],
)
def test_a_malformed_attestation_is_refused(changes: dict[str, object], code: str) -> None:
    value = chain(pret.ef5_p())
    with pytest.raises(EdgeTrialCountChainError, match=code):
        canonical_edge_trial_count_currentness_attestation(_attestation(value, **changes))
    with pytest.raises(EdgeTrialCountChainError, match="currentness_attestation_malformed"):
        canonical_edge_trial_count_currentness_attestation(object())
