"""Edge trial-count chain (EDGE_TRIAL_COUNT_CHAIN_V1): the governed cumulative count of edge variants ever tested.

PRDV4 §1.20 deflates the best Sharpe by ``N_strategies``, "the cumulative count of ALL edge variants ever tested
(monotonically increasing, never reset)". An EF-5 ledger only counts its own registered variants, so this module is the
one authority that accumulates those counts across preregistrations. It is a paper-only governance record: it never
proves that no trial happened off the chain.

Chain (one ``EdgeTrialCountChain`` artifact holds the complete ordered chain, re-proven iteratively from genesis):

* Genesis. ``EdgeTrialCountGenesis`` declares the human-attested count of edge variants tested BEFORE the chain
  (``pre_genesis_trial_count``, the external fact E1) and where that attestation lives. Nothing is defaulted: there is
  no implicit zero and no guessed genesis. The genesis is governed: an ``EdgeTrialCountGenesisApproval`` of kind
  ``HUMAN_GOVERNANCE`` must commit to the exact genesis digest and this rule set; a missing, non-matching or
  ``TEST_ONLY_SYNTHETIC`` approval leaves the chain ``NEEDS_GOVERNANCE_APPROVAL``. A consumer pins the governed
  genesis digest in its own approved policy, so a second genesis is never silently substituted.
* Links. Link ``k`` binds one sealed EF-5 preregistration (an ``EdgeAuthorityBinding`` re-proven through the public
  ``verify_edge_leakage_bias_evidence`` against its anchor; READY + PASS + advancing + sealed), its exact
  ``multiple_testing_count`` read from that authenticated EF-5, the digest of link ``k-1`` (the genesis digest for
  ``k = 0``) and ``cumulative = previous cumulative + count`` (starting from ``pre_genesis_trial_count``), bounded to
  int64. The same EF-5 digest twice is refused; links are re-derived in order, so a prior link can never change
  without changing every later digest. ``extend_edge_trial_count_chain`` appends one EF-5 to a re-proven prior chain
  and keeps every prior link byte-identical.
* Currentness. A chain cannot see trials recorded after it, so a consumer additionally needs one exact
  ``EdgeTrialCountCurrentnessAttestation`` per evaluation: a ``HUMAN_GOVERNANCE`` attestation that this exact chain head
  and cumulative count are current for that evaluation and that no tested variant is missing from the chain.
  ``edge_trial_count_currentness_reasons`` decides whether one attestation matches.

``status`` is integrity only (READY/REJECTED); REJECTED implies NOT_EVALUATED; only READY + PASS advances. One assembly
path serves the builders and verifier reassembly; ``verify_edge_trial_count_chain`` is total. Deterministic and pure:
no IO, clock, randomness, network, float or decimal. It proves no edge, profitability, readiness or the completeness
of off-chain research.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    verify_edge_leakage_bias_evidence,
)

_SCHEMA_VERSION = "edge-trial-count-chain.v1"
_REASON_PREFIX = "edge_trial_count_chain"
_SELF_DIGEST_FIELD = "chain_digest"
_GENESIS_DIGEST_FIELD = "genesis_digest"
_LINK_DIGEST_FIELD = "link_digest"
_INT64_MAX = 9223372036854775807
_MAX_TEXT_LENGTH = 256
_MAX_TOKEN_LENGTH = 128

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_trial_count_chain_rules.v1",
    "authority_id": "EDGE_TRIAL_COUNT_CHAIN_V1",
    "count_source_id": "prdv4_1_20_cumulative_count_of_all_edge_variants_ever_tested_never_reset.v1",
    "genesis_rule_id": "explicit_human_attested_pre_genesis_trial_count_no_default_governed_genesis_digest.v1",
    "link_rule_id": "one_reproven_sealed_ef5_per_link_exact_multiple_testing_count_prior_digest_chained.v1",
    "cumulative_rule_id": "cumulative_equals_previous_plus_link_count_from_pre_genesis_count_int64_bounded.v1",
    "duplicate_rule_id": "an_ef5_digest_appears_at_most_once_in_a_chain.v1",
    "reconstruction_rule_id": "iterative_in_order_rederivation_from_genesis_no_recursion.v1",
    "currentness_rule_id": "exact_human_governance_attestation_per_evaluation_of_head_count_and_no_off_chain_trial.v1",
    "approval_rule_id": "only_human_governance_establishes_test_only_synthetic_never_does.v1",
    "completeness_non_claim_id": "the_chain_cannot_detect_off_chain_trials_or_a_human_approving_a_second_genesis.v1",
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("off_chain_trial_completeness_proven", False),
    ("global_trial_registry_proven", False),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("candidate_admitted_to_paper", False),
    ("live_ready", False),
    ("operational_readiness", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS)


def edge_trial_count_chain_rule_set() -> dict[str, object]:
    """A fresh copy of the rule set committed by ``EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST``."""

    return dict(_RULE_SET_V1)


class EdgeTrialCountChainError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgeTrialCountApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` exists for tests: it is recorded and never establishes a genesis or currentness."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


@dataclass(frozen=True)
class EdgeTrialCountGenesis:
    """The governed chain origin: the human-attested pre-genesis trial count E1 and its evidence reference."""

    genesis_id: str
    pre_genesis_trial_count: int
    pre_genesis_evidence_reference: str
    genesis_digest: str


@dataclass(frozen=True)
class EdgeTrialCountGenesisApproval:
    """Governance approval of one exact genesis under this rule set."""

    approval_reference: str
    approval_digest: str
    approval_kind: EdgeTrialCountApprovalKind
    approved_genesis_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class EdgeTrialCountLink:
    """One chained preregistration: its re-proven EF-5 identity, exact count and the running cumulative count."""

    link_index: int
    prior_digest: str
    preregistration_digest: str
    preregistration_id: str
    candidate_strategy_id: str
    multiple_testing_count: int
    cumulative_trial_count: int
    link_digest: str


@dataclass(frozen=True)
class EdgeTrialCountCurrentnessAttestation:
    """One HUMAN_GOVERNANCE attestation that one exact chain head is current for one exact evaluation."""

    attestation_reference: str
    attestation_digest: str
    approval_kind: EdgeTrialCountApprovalKind
    attested_chain_id: str
    attested_chain_digest: str
    attested_head_digest: str
    attested_cumulative_trial_count: int
    attested_evaluation_id: str
    attested_correlation_id: str
    attested_preregistration_digest: str
    attested_at_ns: int
    no_off_chain_trial_attested: bool


@dataclass(frozen=True)
class EdgeTrialCountChain:
    """Immutable, digest-bound cumulative trial-count chain. Governance record only; proves no edge."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    chain_id: str
    rule_set_id: str
    rule_set_digest: str
    genesis: EdgeTrialCountGenesis
    genesis_approval: EdgeTrialCountGenesisApproval | None
    preregistration_bindings: tuple[EdgeAuthorityBinding, ...]
    links: tuple[EdgeTrialCountLink, ...]
    link_count: int
    head_digest: str
    head_cumulative_trial_count: int
    synthetic_test_approval_used: bool
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    chain_digest: str
    paper_only: bool = True
    off_chain_trial_completeness_proven: bool = False
    global_trial_registry_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    live_ready: bool = False
    operational_readiness: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeTrialCountChainError:
    return EdgeTrialCountChainError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT_LENGTH
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_token(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_TOKEN_LENGTH
        or not (value[0].isascii() and value[0].isalnum())
        or any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_count(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail(f"{field_name}_invalid")
    return value


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize a record; an enum-typed field must hold the exact enum member, never an equal plain string."""

    for name, enum_cls in _ENUM_FIELDS.get(type(artifact), ()):
        if type(getattr(artifact, name)) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset(
    {
        EdgeTrialCountGenesis,
        EdgeTrialCountGenesisApproval,
        EdgeTrialCountLink,
        EdgeTrialCountCurrentnessAttestation,
    }
)
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgeTrialCountChain: (("status", EdgeEvidenceStatus), ("gate_verdict", EdgeGateVerdict)),
    EdgeTrialCountGenesisApproval: (("approval_kind", EdgeTrialCountApprovalKind),),
    EdgeTrialCountCurrentnessAttestation: (("approval_kind", EdgeTrialCountApprovalKind),),
}


def _sealed(record: object, digest_field: str) -> object:
    return replace(record, **{digest_field: edge_payload_digest(_to_payload(record), digest_field)})  # type: ignore[type-var]


# --- caller declarations -----------------------------------------------------------------------------------------------


def build_edge_trial_count_genesis(
    *, genesis_id: str, pre_genesis_trial_count: int, pre_genesis_evidence_reference: str
) -> EdgeTrialCountGenesis:
    """Construct one sealed genesis; ``pre_genesis_trial_count`` is required and never defaulted."""

    seed = EdgeTrialCountGenesis(
        genesis_id=_require_token(genesis_id, "genesis_id"),
        pre_genesis_trial_count=_require_count(pre_genesis_trial_count, "pre_genesis_trial_count"),
        pre_genesis_evidence_reference=_require_text(pre_genesis_evidence_reference, "pre_genesis_evidence_reference"),
        genesis_digest="",
    )
    return _sealed(seed, _GENESIS_DIGEST_FIELD)  # type: ignore[return-value]


def _canonical_genesis(value: object) -> EdgeTrialCountGenesis:
    if type(value) is not EdgeTrialCountGenesis:
        raise _fail("genesis_malformed")
    rebuilt = build_edge_trial_count_genesis(
        genesis_id=getattr(value, "genesis_id", None),  # type: ignore[arg-type]
        pre_genesis_trial_count=getattr(value, "pre_genesis_trial_count", None),  # type: ignore[arg-type]
        pre_genesis_evidence_reference=getattr(value, "pre_genesis_evidence_reference", None),  # type: ignore[arg-type]
    )
    if getattr(value, "genesis_digest", None) != rebuilt.genesis_digest:
        raise _fail("genesis_digest_mismatch")
    return rebuilt


def _canonical_genesis_approval(value: object) -> EdgeTrialCountGenesisApproval | None:
    if value is None:
        return None
    if type(value) is not EdgeTrialCountGenesisApproval:
        raise _fail("genesis_approval_malformed")
    kind = getattr(value, "approval_kind", None)
    if type(kind) is not EdgeTrialCountApprovalKind:
        raise _fail("genesis_approval_kind_invalid")
    return EdgeTrialCountGenesisApproval(
        approval_reference=_require_text(getattr(value, "approval_reference", None), "genesis_approval_reference"),
        approval_digest=_require_hex64(getattr(value, "approval_digest", None), "genesis_approval_digest"),
        approval_kind=kind,
        approved_genesis_digest=_require_hex64(
            getattr(value, "approved_genesis_digest", None), "genesis_approved_genesis_digest"
        ),
        approved_rule_set_digest=_require_hex64(
            getattr(value, "approved_rule_set_digest", None), "genesis_approved_rule_set_digest"
        ),
    )


def canonical_edge_trial_count_currentness_attestation(value: object) -> EdgeTrialCountCurrentnessAttestation | None:
    """Structural validation of one currentness attestation; whether it MATCHES is decided by the consumer."""

    if value is None:
        return None
    if type(value) is not EdgeTrialCountCurrentnessAttestation:
        raise _fail("currentness_attestation_malformed")

    def attribute(name: str) -> object:
        return getattr(value, name, None)

    kind = attribute("approval_kind")
    if type(kind) is not EdgeTrialCountApprovalKind:
        raise _fail("currentness_attestation_kind_invalid")
    attested_at = attribute("attested_at_ns")
    if type(attested_at) is not int or not 0 < attested_at <= _INT64_MAX:
        raise _fail("currentness_attestation_attested_at_ns_invalid")
    if type(attribute("no_off_chain_trial_attested")) is not bool:
        raise _fail("currentness_attestation_no_off_chain_trial_attested_invalid")
    return EdgeTrialCountCurrentnessAttestation(
        attestation_reference=_require_text(attribute("attestation_reference"), "currentness_attestation_reference"),
        attestation_digest=_require_hex64(attribute("attestation_digest"), "currentness_attestation_digest"),
        approval_kind=kind,
        attested_chain_id=_require_token(attribute("attested_chain_id"), "currentness_attested_chain_id"),
        attested_chain_digest=_require_hex64(attribute("attested_chain_digest"), "currentness_attested_chain_digest"),
        attested_head_digest=_require_hex64(attribute("attested_head_digest"), "currentness_attested_head_digest"),
        attested_cumulative_trial_count=_require_count(
            attribute("attested_cumulative_trial_count"), "currentness_attested_cumulative_trial_count"
        ),
        attested_evaluation_id=_require_text(attribute("attested_evaluation_id"), "currentness_attested_evaluation_id"),
        attested_correlation_id=_require_text(
            attribute("attested_correlation_id"), "currentness_attested_correlation_id"
        ),
        attested_preregistration_digest=_require_hex64(
            attribute("attested_preregistration_digest"), "currentness_attested_preregistration_digest"
        ),
        attested_at_ns=attested_at,  # type: ignore[arg-type]
        no_off_chain_trial_attested=attribute("no_off_chain_trial_attested"),  # type: ignore[arg-type]
    )


def edge_trial_count_currentness_attestation_digest(attestation: EdgeTrialCountCurrentnessAttestation) -> str:
    """The canonical digest of one structurally valid attestation record (every field, including its reference)."""

    return edge_sha256_text(edge_canonical_json(_to_payload(attestation)))


def edge_trial_count_currentness_reasons(
    attestation: EdgeTrialCountCurrentnessAttestation | None,
    *,
    chain: EdgeTrialCountChain,
    evaluation_id: str,
    correlation_id: str,
    preregistration_digest: str,
) -> list[str]:
    """Governance reasons (empty iff currentness is established) for one evaluation over one READY chain."""

    if attestation is None:
        return [_reason("currentness_attestation_missing")]
    codes: list[str] = []
    if attestation.approval_kind is not EdgeTrialCountApprovalKind.HUMAN_GOVERNANCE:
        codes.append(_reason("currentness_attestation_not_human_governance"))
    expected = {
        "chain_id": chain.chain_id,
        "chain_digest": chain.chain_digest,
        "head_digest": chain.head_digest,
        "cumulative_trial_count": chain.head_cumulative_trial_count,
        "evaluation_id": evaluation_id,
        "correlation_id": correlation_id,
        "preregistration_digest": preregistration_digest,
    }
    codes.extend(
        _reason(f"currentness_attestation_{name}_mismatch")
        for name, value in expected.items()
        if getattr(attestation, f"attested_{name}") != value
    )
    if attestation.no_off_chain_trial_attested is not True:
        codes.append(_reason("currentness_attestation_off_chain_trials_not_excluded"))
    return codes


# --- the authenticated preregistrations --------------------------------------------------------------------------------


def _preregistration_authority(
    binding: EdgeAuthorityBinding, index: int
) -> tuple[list[str], EdgeLeakageBiasEvidence | None]:
    ef5 = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_leakage_bias_evidence(ef5)
    if not verification.intact:
        return [
            _reason(f"link_{index}:preregistration_integrity_failure:{code}") for code in verification.reason_codes
        ], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason(f"link_{index}:preregistration_digest_mismatch")], None
    if (
        ef5.status is not EdgeEvidenceStatus.READY
        or ef5.gate_verdict is not EdgeGateVerdict.PASS
        or ef5.advances is not True
        or ef5.preregistration_sealed is not True
    ):
        return [_reason(f"link_{index}:preregistration_not_sealed")], None
    if not 0 < ef5.multiple_testing_count <= _INT64_MAX:
        return [_reason(f"link_{index}:preregistration_count_invalid")], None
    return [], ef5


def _require_bindings(values: object) -> tuple[EdgeAuthorityBinding, ...]:
    if type(values) is not tuple:
        raise _fail("preregistration_bindings_malformed")
    return tuple(
        require_edge_authority_binding(  # type: ignore[misc]
            item,
            shape=edge_leakage_bias_evidence_payload_is_well_formed,
            error=EdgeTrialCountChainError,
            code=_reason("preregistration"),
            optional=False,
        )
        for item in values  # type: ignore[union-attr]
    )


# --- the chain ---------------------------------------------------------------------------------------------------------


def _assemble_chain(
    *, chain_id: object, genesis: object, genesis_approval: object, preregistration_bindings: object
) -> EdgeTrialCountChain:
    """The one chain assembly path, shared by the builders and verifier reassembly (iterative, in link order)."""

    chain_id = _require_token(chain_id, "chain_id")
    genesis_record = _canonical_genesis(genesis)
    approval = _canonical_genesis_approval(genesis_approval)
    bindings = _require_bindings(preregistration_bindings)

    codes: list[str] = []
    links: list[EdgeTrialCountLink] = []
    seen: set[str] = set()
    prior = genesis_record.genesis_digest
    cumulative = genesis_record.pre_genesis_trial_count
    for index, binding in enumerate(bindings):
        if binding.expected_digest in seen:
            codes.append(_reason(f"link_{index}:preregistration_duplicate"))
            break
        seen.add(binding.expected_digest)
        link_codes, ef5 = _preregistration_authority(binding, index)
        if ef5 is None:
            codes.extend(link_codes)
            break
        cumulative += ef5.multiple_testing_count
        if cumulative > _INT64_MAX:
            codes.append(_reason(f"link_{index}:cumulative_trial_count_out_of_range"))
            break
        link: EdgeTrialCountLink = _sealed(  # type: ignore[assignment]
            EdgeTrialCountLink(
                link_index=index,
                prior_digest=prior,
                preregistration_digest=binding.expected_digest,
                preregistration_id=ef5.preregistration_id,
                candidate_strategy_id=ef5.candidate_strategy_id,
                multiple_testing_count=ef5.multiple_testing_count,
                cumulative_trial_count=cumulative,
                link_digest="",
            ),
            _LINK_DIGEST_FIELD,
        )
        links.append(link)
        prior = link.link_digest
    integrity = _sorted_unique(codes)

    if integrity:
        status, verdict, reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
        links = []
    else:
        governance: list[str] = []
        if approval is None:
            governance.append(_reason("genesis_approval_missing"))
        else:
            if approval.approval_kind is not EdgeTrialCountApprovalKind.HUMAN_GOVERNANCE:
                governance.append(_reason("genesis_approval_not_human_governance"))
            if approval.approved_genesis_digest != genesis_record.genesis_digest:
                governance.append(_reason("genesis_approval_genesis_digest_mismatch"))
            if approval.approved_rule_set_digest != EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST:
                governance.append(_reason("genesis_approval_rule_set_digest_mismatch"))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict([], [], governance)
        reasons = _sorted_unique(governance)

    head_digest = links[-1].link_digest if links else genesis_record.genesis_digest
    head_count = links[-1].cumulative_trial_count if links else genesis_record.pre_genesis_trial_count
    seed = EdgeTrialCountChain(
        schema_version=_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        chain_id=chain_id,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST,
        genesis=genesis_record,
        genesis_approval=approval,
        preregistration_bindings=bindings,
        links=tuple(links),
        link_count=len(links),
        head_digest=head_digest,
        head_cumulative_trial_count=head_count,
        synthetic_test_approval_used=approval is not None
        and approval.approval_kind is EdgeTrialCountApprovalKind.TEST_ONLY_SYNTHETIC,
        integrity_reason_codes=integrity,
        verdict_reason_codes=reasons,
        chain_digest="",
    )
    return replace(seed, chain_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def _preregistration_binding(evidence: object, expected_digest: object) -> EdgeAuthorityBinding:
    if type(evidence) is not EdgeLeakageBiasEvidence:
        raise _fail("preregistration_malformed")
    try:
        payload = edge_leakage_bias_evidence_to_dict(evidence)
    except Exception as exc:  # noqa: BLE001 - a hollow EF-5 object is a construction error, never a receipt
        raise _fail("preregistration_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=expected_digest,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeTrialCountChainError,
        code=_reason("preregistration"),
    )


def build_edge_trial_count_chain(
    *,
    chain_id: str,
    genesis: EdgeTrialCountGenesis,
    genesis_approval: EdgeTrialCountGenesisApproval | None,
    preregistrations: Sequence[EdgeLeakageBiasEvidence],
    expected_preregistration_digests: Sequence[str],
) -> EdgeTrialCountChain:
    """Build one chain from its governed genesis and its sealed EF-5 preregistrations, in link order.

    Malformed caller input or a non-serializable EF-5 raises ``EdgeTrialCountChainError``. A preregistration that fails
    re-proof, a duplicate or a count overflow yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the chain is ``READY``
    with ``PASS`` only under an exact ``HUMAN_GOVERNANCE`` genesis approval.
    """

    if type(preregistrations) not in (tuple, list) or type(expected_preregistration_digests) not in (tuple, list):
        raise _fail("preregistrations_malformed")
    if len(preregistrations) != len(expected_preregistration_digests):
        raise _fail("preregistration_anchor_count_mismatch")
    bindings = tuple(
        _preregistration_binding(evidence, digest)
        for evidence, digest in zip(preregistrations, expected_preregistration_digests, strict=True)
    )
    return _assemble_chain(
        chain_id=chain_id, genesis=genesis, genesis_approval=genesis_approval, preregistration_bindings=bindings
    )


def extend_edge_trial_count_chain(
    prior: EdgeTrialCountChain,
    *,
    expected_prior_chain_digest: str,
    preregistration: EdgeLeakageBiasEvidence,
    expected_preregistration_digest: str,
) -> EdgeTrialCountChain:
    """Append one sealed EF-5 to a re-proven, advancing prior chain; every prior link stays byte-identical."""

    verification = verify_edge_trial_count_chain(prior)
    if not verification.intact or verification.recomputed_digest != expected_prior_chain_digest:
        raise _fail("prior_chain_not_authentic")
    if prior.advances is not True:
        raise _fail("prior_chain_not_advancing")
    return _assemble_chain(
        chain_id=prior.chain_id,
        genesis=prior.genesis,
        genesis_approval=prior.genesis_approval,
        preregistration_bindings=(
            *prior.preregistration_bindings,
            _preregistration_binding(preregistration, expected_preregistration_digest),
        ),
    )


def edge_trial_count_chain_to_dict(chain: EdgeTrialCountChain) -> dict[str, object]:
    """Canonical JSON-ready mapping of a chain, including its self-digest."""

    return _to_payload(chain)


def edge_trial_count_chain_digest(chain: EdgeTrialCountChain) -> str:
    """Recompute the canonical chain digest, excluding only ``chain_digest``."""

    return edge_payload_digest(_to_payload(chain), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


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
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _as_optional(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _parse_bindings(value: object) -> tuple[EdgeAuthorityBinding, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(
        parse_edge_authority_binding(  # type: ignore[misc]
            item,
            shape=edge_leakage_bias_evidence_payload_is_well_formed,
            error=EdgeTrialCountChainError,
            code=_reason("preregistration"),
            optional=False,
        )
        for item in value
    )


_GENESIS_CONVERTERS: dict[str, Callable[[object], object]] = {"pre_genesis_trial_count": _as_int}
_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {"approval_kind": _as_enum(EdgeTrialCountApprovalKind)}
_LINK_CONVERTERS: dict[str, Callable[[object], object]] = {
    "link_index": _as_int,
    "multiple_testing_count": _as_int,
    "cumulative_trial_count": _as_int,
}
_CHAIN_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "genesis": lambda value: _parse_exact(EdgeTrialCountGenesis, value, _GENESIS_CONVERTERS),
    "genesis_approval": _as_optional(EdgeTrialCountGenesisApproval, _APPROVAL_CONVERTERS),
    "preregistration_bindings": _parse_bindings,
    "links": _as_records(EdgeTrialCountLink, _LINK_CONVERTERS),
    "link_count": _as_int,
    "head_cumulative_trial_count": _as_int,
    "synthetic_test_approval_used": _as_bool,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}
_ATTESTATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(EdgeTrialCountApprovalKind),
    "attested_cumulative_trial_count": _as_int,
    "attested_at_ns": _as_int,
    "no_off_chain_trial_attested": _as_bool,
}


def edge_trial_count_chain_from_payload(payload: object) -> EdgeTrialCountChain:
    """Strictly reconstruct a chain from its serialized payload (exact fields, types and bindings; no proof)."""

    return _parse_exact(EdgeTrialCountChain, payload, _CHAIN_CONVERTERS)  # type: ignore[return-value]


def edge_trial_count_chain_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a chain snapshot consumed by a later artifact."""

    try:
        edge_trial_count_chain_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def edge_trial_count_currentness_attestation_to_dict(attestation: EdgeTrialCountCurrentnessAttestation) -> dict:
    """Canonical JSON-ready mapping of one attestation record."""

    return _to_payload(attestation)


def edge_trial_count_currentness_attestation_from_payload(payload: object) -> EdgeTrialCountCurrentnessAttestation:
    """Strictly reconstruct one attestation record (exact fields and types; no matching)."""

    return _parse_exact(EdgeTrialCountCurrentnessAttestation, payload, _ATTESTATION_CONVERTERS)  # type: ignore[return-value]


def _reassemble_chain(chain: object) -> EdgeTrialCountChain:
    return _assemble_chain(
        chain_id=chain.chain_id,  # type: ignore[attr-defined]
        genesis=chain.genesis,  # type: ignore[attr-defined]
        genesis_approval=chain.genesis_approval,  # type: ignore[attr-defined]
        preregistration_bindings=chain.preregistration_bindings,  # type: ignore[attr-defined]
    )


def verify_edge_trial_count_chain(chain: object) -> EdgeEvidenceVerification:
    """Re-prove a chain by strict parse and in-order reassembly from genesis and its EF-5 bindings. Total."""

    return verify_edge_artifact_total(
        chain,
        cls=EdgeTrialCountChain,
        to_payload=_to_payload,
        parse_payload=edge_trial_count_chain_from_payload,
        reassemble=_reassemble_chain,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_TRIAL_COUNT_CHAIN_NON_CLAIM_FLAGS",
    "EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST",
    "EdgeTrialCountApprovalKind",
    "EdgeTrialCountChain",
    "EdgeTrialCountChainError",
    "EdgeTrialCountCurrentnessAttestation",
    "EdgeTrialCountGenesis",
    "EdgeTrialCountGenesisApproval",
    "EdgeTrialCountLink",
    "build_edge_trial_count_chain",
    "build_edge_trial_count_genesis",
    "canonical_edge_trial_count_currentness_attestation",
    "edge_trial_count_chain_digest",
    "edge_trial_count_chain_from_payload",
    "edge_trial_count_chain_payload_is_well_formed",
    "edge_trial_count_chain_rule_set",
    "edge_trial_count_chain_to_dict",
    "edge_trial_count_currentness_attestation_digest",
    "edge_trial_count_currentness_attestation_from_payload",
    "edge_trial_count_currentness_attestation_to_dict",
    "edge_trial_count_currentness_reasons",
    "extend_edge_trial_count_chain",
    "verify_edge_trial_count_chain",
]
