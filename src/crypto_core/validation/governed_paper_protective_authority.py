"""Governed paper protective close-only authority (PROTECTIVE_POSITION_LIFECYCLE_V1, DEC-1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7 and the human decision DEC-1 of
this contract. Protective close-only actions of the governed paper path may use a separate, explicitly approved,
digest-bound protective authority. They then do not depend on the entry-side direction ceilings, the per-cycle entry
permission, the reservation price ceiling of a cycle or the entry ban that follows a lifecycle invalidation. Nothing
here opens, increases or reverses a position, routes an order or proves a venue fact. The engine
(``historical_execution_economics``) keeps every execution constraint: book selection, latency, delay, spread, depth,
fees, and close-only construction.

``GovernedPaperProtectiveAuthority`` (one per genesis lineage) binds:

* the verified AUTHORIZED genesis;
* one ``HistoricalPositionManagementPolicy`` of the genesis instrument, together with its ``HUMAN_GOVERNANCE``
  approval. That approval must match the policy, the genesis StrategySpec, the instrument and the adopted OHLC source
  declaration, and it must cover only human-authorized methods. While DEC-9 is unapproved, a policy that applies the
  DEC-9 tightening reading therefore never becomes AUTHORIZED;
* the adopted ``HistoricalOhlcSourceDeclaration``, which must serve the policy's ATR interval and price semantics;
* the protective validity window ``[valid_from_ns, valid_until_ns)``, which starts at or after the genesis instant G.

AUTHORIZED needs an exact ``HUMAN_GOVERNANCE`` approval of the authority policy. A structural shortfall is BLOCKED, and
a missing, synthetic or non-matching approval is NEEDS_GOVERNANCE_APPROVAL.

``GovernedPaperProtectiveRevocation`` is a digest-bound, human-governed revocation of one authority, effective at one
instant. From that instant no protective action is authorized, and the engine records every later protective attempt as
refused while the obligation stays outstanding. A revocation is never undone.

``governed_paper_protective_window`` derives the engine's neutral protective window from a verified AUTHORIZED authority
and its earliest revocation. A missing, malformed, stale (expired) or revoked authority yields no window, and every
protective attempt then fails closed with explicit evidence. Paper-only, deterministic and pure: no IO, clock,
randomness, network or environment. It grants nothing for C1-C9, real orders, capital, shadow or live.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperApprovalKind,
    GovernedPaperGenesis,
    GovernedPaperGenesisInputs,
    governed_paper_genesis_authority,
)
from crypto_core.validation.governed_paper_typed_identity import (
    GovernedPaperTypeDomain,
    governed_paper_typed_identical,
    governed_paper_typed_identity_digest,
    governed_paper_verify_rebuilt,
)
from crypto_core.validation.historical_execution_economics import HistoricalExecutionProtectiveWindow
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchiveError,
    HistoricalOhlcSourceDeclaration,
    canonical_historical_ohlc_source_declaration,
    historical_ohlc_source_declaration_digest,
)
from crypto_core.validation.historical_position_management_policy import (
    HistoricalPositionManagementApproval,
    HistoricalPositionManagementPolicy,
    HistoricalPositionManagementPolicyError,
    canonical_historical_position_management_approval,
    historical_position_management_approval_mismatches,
    historical_position_management_methods_requiring_human_approval,
    verify_historical_position_management_policy,
)

_PREFIX = "governed_paper_protective_authority"
_AUTHORITY_SCHEMA_VERSION = "governed-paper-protective-authority.v1"
_REVOCATION_SCHEMA_VERSION = "governed-paper-protective-revocation.v1"
_AUTHORITY_DIGEST_FIELD = "authority_digest"
_REVOCATION_DIGEST_FIELD = "revocation_digest"

GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET: dict[str, object] = {
    "rule_set_id": "governed-paper-protective-authority.v1",
    "contract_id": "PROTECTIVE_POSITION_LIFECYCLE_V1",
    "human_decision": "DEC-1",
    "scope": "close_only_protective_obligations_of_the_position_management_policy",
    "bypasses": [
        "cycle_direction_ceiling",
        "cycle_window",
        "cycle_reservation_price_ceiling",
        "entry_safety_refusals",
        "lifecycle_invalidation_entry_ban",
    ],
    "never": ["open", "increase", "reverse", "real_order", "capital_mutation"],
    "kept": ["engine_fill_model", "latency", "execution_delay", "spread", "depth", "fees", "close_only_construction"],
    "position_management_approval_rule": "human_governance_exact_match_human_authorized_methods_only",
    "window_rule": "valid_from_at_or_after_genesis_until_valid_until_or_the_earliest_revocation",
    "revocation_rule": "human_governance_revocation_effective_at_one_instant_never_undone",
    "approval_rule": "exact_human_governance_commitments",
}
GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST = edge_sha256_text(
    edge_canonical_json(GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET)
)
_RULE_SET_ID = str(GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET["rule_set_id"])


class GovernedPaperProtectiveAuthorityError(EdgeArtifactError):
    """Malformed input or a provenance defect: an invalid authority or revocation is never represented."""


class GovernedPaperProtectiveAuthorityStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


@dataclass(frozen=True)
class GovernedPaperProtectiveAuthorityApproval:
    """Human governance of one exact protective authority policy (DEC-1 applied to one genesis)."""

    approval_reference: str
    approval_digest: str
    approval_kind: GovernedPaperApprovalKind
    approved_authority_id: str
    approved_authority_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class GovernedPaperProtectiveAuthorityInputs:
    """Everything one protective authority consumes."""

    authority_id: str
    correlation_id: str
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    position_management_policy: HistoricalPositionManagementPolicy
    position_management_approval: HistoricalPositionManagementApproval | None
    ohlc_source: HistoricalOhlcSourceDeclaration
    valid_from_ns: int
    valid_until_ns: int
    approval: GovernedPaperProtectiveAuthorityApproval | None


@dataclass(frozen=True)
class GovernedPaperProtectiveAuthority:
    """One genesis lineage's protective close-only authority; ``authority_digest`` covers every other field."""

    schema_version: str
    status: GovernedPaperProtectiveAuthorityStatus
    authorized: bool
    authority_id: str
    correlation_id: str
    genesis_id: str
    genesis_digest: str
    sleeve_id: str
    instrument: str
    strategy_spec_digest: str
    position_management_policy_digest: str
    position_management_rule_set_digest: str
    position_management_approval_identity_digest: str
    stop_tightening_method_id: str
    ohlc_source_digest: str
    valid_from_ns: int
    valid_until_ns: int
    authority_policy_digest: str
    rule_set_id: str
    rule_set_digest: str
    approval: GovernedPaperProtectiveAuthorityApproval | None
    synthetic_test_approval_used: bool
    reason_codes: tuple[str, ...]
    authority_digest: str
    paper_only: bool = True
    close_only: bool = True
    execution_authorized: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_allocated: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    venue_facts_proven: bool = False


@dataclass(frozen=True)
class GovernedPaperProtectiveRevocation:
    """A human-governed revocation of one protective authority, effective at ``effective_at_ns``."""

    schema_version: str
    revocation_id: str
    authority_digest: str
    effective_at_ns: int
    approval_reference: str
    approval_digest: str
    approval_kind: GovernedPaperApprovalKind
    revocation_digest: str


@dataclass(frozen=True)
class GovernedPaperProtectiveContext:
    """The canonical reconstructions a verified AUTHORIZED authority lets the day seal use (never caller originals)."""

    authority: GovernedPaperProtectiveAuthority
    position_management_policy: HistoricalPositionManagementPolicy
    position_management_approval: HistoricalPositionManagementApproval
    ohlc_source: HistoricalOhlcSourceDeclaration


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperProtectiveAuthorityError:
    return GovernedPaperProtectiveAuthorityError(_reason(code))


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


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


_AUTHORITY_DOMAIN = GovernedPaperTypeDomain(_AUTHORITY_SCHEMA_VERSION, roots=(GovernedPaperProtectiveAuthority,))
_REVOCATION_DOMAIN = GovernedPaperTypeDomain(_REVOCATION_SCHEMA_VERSION, roots=(GovernedPaperProtectiveRevocation,))
_RECORD_DOMAIN = GovernedPaperTypeDomain(
    "governed-paper-protective-records.v1", roots=(HistoricalPositionManagementApproval,)
)


def _canonical_authority_approval(approval: object) -> GovernedPaperProtectiveAuthorityApproval | None:
    if approval is None:
        return None
    if type(approval) is not GovernedPaperProtectiveAuthorityApproval:
        raise _fail("authority_approval_malformed")
    if type(approval.approval_kind) is not GovernedPaperApprovalKind:
        raise _fail("authority_approval_kind_malformed")
    return GovernedPaperProtectiveAuthorityApproval(
        approval_reference=_require_text(approval.approval_reference, "authority_approval_reference"),
        approval_digest=_require_hex64(approval.approval_digest, "authority_approval_digest"),
        approval_kind=approval.approval_kind,
        approved_authority_id=_require_text(approval.approved_authority_id, "approved_authority_id"),
        approved_authority_policy_digest=_require_hex64(
            approval.approved_authority_policy_digest, "approved_authority_policy_digest"
        ),
        approved_rule_set_digest=_require_hex64(approval.approved_rule_set_digest, "approved_rule_set_digest"),
    )


# --- the authority -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _AuthorityProof:
    facts: dict[str, object]
    blocked: tuple[str, ...]
    governance: tuple[str, ...]
    canonical: (
        tuple[HistoricalPositionManagementPolicy, HistoricalPositionManagementApproval, HistoricalOhlcSourceDeclaration]
        | None
    )


def _authority_proof(inputs: GovernedPaperProtectiveAuthorityInputs) -> _AuthorityProof:  # noqa: C901 - one linear proof
    if type(inputs) is not GovernedPaperProtectiveAuthorityInputs:
        raise _fail("authority_inputs_malformed")
    authority_id = _require_text(inputs.authority_id, "authority_id")
    correlation_id = _require_text(inputs.correlation_id, "authority_correlation_id")
    genesis = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs).genesis
    policy = inputs.position_management_policy
    if type(policy) is not HistoricalPositionManagementPolicy:
        raise _fail("position_management_policy_malformed")
    verification = verify_historical_position_management_policy(policy)
    if not verification.intact or verification.recomputed_digest != policy.policy_digest:
        raise _fail("position_management_policy_not_authentic")
    try:
        pm_approval = canonical_historical_position_management_approval(inputs.position_management_approval)
        source = canonical_historical_ohlc_source_declaration(inputs.ohlc_source)
    except (HistoricalPositionManagementPolicyError, HistoricalOhlcBarArchiveError) as exc:
        raise _fail("position_management_input_malformed") from exc
    for name in ("valid_from_ns", "valid_until_ns"):
        if not historical_execution_wire_int_is_valid(getattr(inputs, name), minimum=0):
            raise _fail(f"{name}_invalid")
    source_digest = historical_ohlc_source_declaration_digest(source)
    blocked: list[str] = []
    governance: list[str] = []
    if policy.instrument != genesis.instrument:
        blocked.append(_reason("position_management_policy_instrument_mismatch"))
    if source.instrument != genesis.instrument:
        blocked.append(_reason("ohlc_source_instrument_mismatch"))
    if policy.atr_interval_ns not in source.bar_intervals_ns:
        blocked.append(_reason("ohlc_source_lacks_the_atr_interval"))
    if source.price_semantics is not policy.atr_bar_price_semantics:
        blocked.append(_reason("ohlc_source_price_semantics_mismatch"))
    if inputs.valid_from_ns < genesis.genesis_start_ns:
        blocked.append(_reason("protective_window_starts_before_the_genesis"))
    if inputs.valid_until_ns <= inputs.valid_from_ns:
        blocked.append(_reason("protective_window_empty"))
    if pm_approval is None:
        governance.append(_reason("position_management_approval_missing"))
        approval_identity = edge_sha256_text(edge_canonical_json(None))
    else:
        approval_identity = governed_paper_typed_identity_digest(pm_approval, _RECORD_DOMAIN)
        if pm_approval.approval_kind is not HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE:
            governance.append(_reason("position_management_approval_not_human_governance"))
        governance.extend(
            _reason(f"position_management_approval_mismatch:{name}")
            for name in historical_position_management_approval_mismatches(
                pm_approval,
                policy=policy,
                strategy_spec_digest=genesis.strategy_spec_digest,
                instrument=genesis.instrument,
                ohlc_source_digest=source_digest,
            )
        )
    governance.extend(
        _reason(f"position_management_method_requires_human_approval:{method}")
        for method in historical_position_management_methods_requiring_human_approval(policy)
    )
    facts: dict[str, object] = {
        "authority_id": authority_id,
        "correlation_id": correlation_id,
        "genesis_id": genesis.genesis_id,
        "genesis_digest": genesis.genesis_digest,
        "sleeve_id": genesis.sleeve_id,
        "instrument": genesis.instrument,
        "strategy_spec_digest": genesis.strategy_spec_digest,
        "position_management_policy_digest": policy.policy_digest,
        "position_management_rule_set_digest": policy.rule_set_digest,
        "position_management_approval_identity_digest": approval_identity,
        "stop_tightening_method_id": policy.stop_tightening_method_id,
        "ohlc_source_digest": source_digest,
        "valid_from_ns": inputs.valid_from_ns,
        "valid_until_ns": inputs.valid_until_ns,
    }
    canonical = None if blocked or pm_approval is None else (policy, pm_approval, source)
    return _AuthorityProof(facts, tuple(blocked), tuple(governance), canonical)


def _authority_policy_digest(facts: dict[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({**facts, "rule_set_digest": GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST})
    )


def _assemble_authority(
    inputs: GovernedPaperProtectiveAuthorityInputs, proof: _AuthorityProof
) -> GovernedPaperProtectiveAuthority:
    policy_digest = _authority_policy_digest(proof.facts)
    approval = _canonical_authority_approval(inputs.approval)
    governance = list(proof.governance)
    if approval is None:
        governance.append(_reason("authority_approval_missing"))
    elif approval.approval_kind is not GovernedPaperApprovalKind.HUMAN_GOVERNANCE:
        governance.append(_reason("authority_approval_not_human_governance"))
    else:
        expected = {
            "approved_authority_id": proof.facts["authority_id"],
            "approved_authority_policy_digest": policy_digest,
            "approved_rule_set_digest": GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST,
        }
        governance.extend(
            _reason(f"authority_approval_mismatch:{name}")
            for name, value in expected.items()
            if getattr(approval, name) != value
        )
    if proof.blocked:
        status = GovernedPaperProtectiveAuthorityStatus.BLOCKED
    elif governance:
        status = GovernedPaperProtectiveAuthorityStatus.NEEDS_GOVERNANCE_APPROVAL
    else:
        status = GovernedPaperProtectiveAuthorityStatus.AUTHORIZED
    seed = GovernedPaperProtectiveAuthority(
        schema_version=_AUTHORITY_SCHEMA_VERSION,
        status=status,
        authorized=status is GovernedPaperProtectiveAuthorityStatus.AUTHORIZED,
        **proof.facts,  # type: ignore[arg-type]
        authority_policy_digest=policy_digest,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST,
        approval=approval,
        synthetic_test_approval_used=approval is not None
        and approval.approval_kind is GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC,
        reason_codes=tuple(sorted(set(proof.blocked) | set(governance))),
        authority_digest="",
    )
    return replace(seed, authority_digest=edge_payload_digest(_to_payload(seed), _AUTHORITY_DIGEST_FIELD))


def build_governed_paper_protective_authority(
    inputs: GovernedPaperProtectiveAuthorityInputs,
) -> GovernedPaperProtectiveAuthority:
    """Build one protective authority from fully re-proven inputs (see the module docstring).

    Malformed input or a provenance defect (a genesis that is not AUTHORIZED, a tampered policy) raises
    ``GovernedPaperProtectiveAuthorityError`` or the genesis verifier's error. A structural shortfall is ``BLOCKED``; a
    missing, synthetic or non-matching approval, or a method no human authorized, is ``NEEDS_GOVERNANCE_APPROVAL``.
    Pure.
    """

    return _assemble_authority(inputs, _authority_proof(inputs))


def governed_paper_protective_authority_to_dict(authority: GovernedPaperProtectiveAuthority) -> dict[str, object]:
    return _to_payload(authority)


def governed_paper_protective_authority_digest(authority: GovernedPaperProtectiveAuthority) -> str:
    return edge_payload_digest(_to_payload(authority), _AUTHORITY_DIGEST_FIELD)


def verify_governed_paper_protective_authority(authority: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove an authority by typed identity against its rebuild from ``inputs``. Total: never raises."""

    return governed_paper_verify_rebuilt(
        authority,
        cls=GovernedPaperProtectiveAuthority,
        domain=_AUTHORITY_DOMAIN,
        to_payload=_to_payload,
        digest_field=_AUTHORITY_DIGEST_FIELD,
        rebuild=lambda: build_governed_paper_protective_authority(inputs),  # type: ignore[arg-type]
        code="protective_authority",
        reason=_reason,
    )


def governed_paper_protective_authority_context(
    authority: object, inputs: object
) -> GovernedPaperProtectiveContext | None:
    """One re-proof of ``authority`` against its rebuild from ``inputs``: its canonical context, or None.

    None means the authority is authentic but not AUTHORIZED. Anything that is not the exact rebuild, including
    malformed inputs, raises ``protective_authority_not_authentic``.
    """

    try:
        proof = _authority_proof(inputs)  # type: ignore[arg-type]
        rebuilt = _assemble_authority(inputs, proof)  # type: ignore[arg-type]
        authentic = (
            type(authority) is GovernedPaperProtectiveAuthority
            and governed_paper_protective_authority_digest(authority) == authority.authority_digest
            and governed_paper_typed_identical(authority, rebuilt, _AUTHORITY_DOMAIN)
        )
    except Exception as exc:  # noqa: BLE001 - an uncanonical authority or input is never authentic
        raise _fail("protective_authority_not_authentic") from exc
    if not authentic:
        raise _fail("protective_authority_not_authentic")
    if rebuilt.status is not GovernedPaperProtectiveAuthorityStatus.AUTHORIZED or proof.canonical is None:
        return None
    policy, approval, source = proof.canonical
    return GovernedPaperProtectiveContext(rebuilt, policy, approval, source)


def governed_paper_protective_context(authority: object, inputs: object) -> GovernedPaperProtectiveContext:
    """The canonical reconstructions of a verified AUTHORIZED authority; raises otherwise."""

    context = governed_paper_protective_authority_context(authority, inputs)
    if context is None:
        raise _fail("protective_authority_not_authorized")
    return context


# --- revocation --------------------------------------------------------------------------------------------------------


def build_governed_paper_protective_revocation(
    *,
    revocation_id: str,
    authority_digest: str,
    effective_at_ns: int,
    approval_reference: str,
    approval_digest: str,
    approval_kind: GovernedPaperApprovalKind,
) -> GovernedPaperProtectiveRevocation:
    """Build one revocation record and its digest; malformed input raises. A revocation only ever removes authority."""

    if type(approval_kind) is not GovernedPaperApprovalKind:
        raise _fail("revocation_approval_kind_malformed")
    if not historical_execution_wire_int_is_valid(effective_at_ns, minimum=0):
        raise _fail("revocation_effective_at_ns_invalid")
    seed = GovernedPaperProtectiveRevocation(
        schema_version=_REVOCATION_SCHEMA_VERSION,
        revocation_id=_require_text(revocation_id, "revocation_id"),
        authority_digest=_require_hex64(authority_digest, "revocation_authority_digest"),
        effective_at_ns=effective_at_ns,
        approval_reference=_require_text(approval_reference, "revocation_approval_reference"),
        approval_digest=_require_hex64(approval_digest, "revocation_approval_digest"),
        approval_kind=approval_kind,
        revocation_digest="",
    )
    return replace(seed, revocation_digest=edge_payload_digest(_to_payload(seed), _REVOCATION_DIGEST_FIELD))


def governed_paper_protective_revocation_digest(revocation: GovernedPaperProtectiveRevocation) -> str:
    return edge_payload_digest(_to_payload(revocation), _REVOCATION_DIGEST_FIELD)


def verify_governed_paper_protective_revocation(revocation: object) -> EdgeEvidenceVerification:
    """Re-prove a revocation by typed identity against its rebuild from its own fields. Total: never raises."""

    def rebuild() -> object:
        return build_governed_paper_protective_revocation(
            revocation_id=revocation.revocation_id,  # type: ignore[attr-defined]
            authority_digest=revocation.authority_digest,  # type: ignore[attr-defined]
            effective_at_ns=revocation.effective_at_ns,  # type: ignore[attr-defined]
            approval_reference=revocation.approval_reference,  # type: ignore[attr-defined]
            approval_digest=revocation.approval_digest,  # type: ignore[attr-defined]
            approval_kind=revocation.approval_kind,  # type: ignore[attr-defined]
        )

    return governed_paper_verify_rebuilt(
        revocation,
        cls=GovernedPaperProtectiveRevocation,
        domain=_REVOCATION_DOMAIN,
        to_payload=_to_payload,
        digest_field=_REVOCATION_DIGEST_FIELD,
        rebuild=rebuild,
        code="protective_revocation",
        reason=_reason,
    )


# --- the engine window -------------------------------------------------------------------------------------------------


def governed_paper_protective_window(
    authority: GovernedPaperProtectiveAuthority, *, revoked_from_ns: int | None
) -> HistoricalExecutionProtectiveWindow | None:
    """The neutral engine window of an AUTHORIZED authority, ended by its expiry or its earliest revocation, else None."""

    if type(authority) is not GovernedPaperProtectiveAuthority:
        raise _fail("authority_malformed")
    if authority.status is not GovernedPaperProtectiveAuthorityStatus.AUTHORIZED:
        return None
    if revoked_from_ns is not None and not historical_execution_wire_int_is_valid(revoked_from_ns, minimum=0):
        raise _fail("revoked_from_ns_invalid")
    end = authority.valid_until_ns if revoked_from_ns is None else min(authority.valid_until_ns, revoked_from_ns)
    if end <= authority.valid_from_ns:
        return None
    return HistoricalExecutionProtectiveWindow(
        window_start_ns=authority.valid_from_ns, window_end_ns=end, authority_digest=authority.authority_digest
    )


__all__ = [
    "GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET",
    "GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST",
    "GovernedPaperProtectiveAuthority",
    "GovernedPaperProtectiveAuthorityApproval",
    "GovernedPaperProtectiveAuthorityError",
    "GovernedPaperProtectiveAuthorityInputs",
    "GovernedPaperProtectiveAuthorityStatus",
    "GovernedPaperProtectiveContext",
    "GovernedPaperProtectiveRevocation",
    "build_governed_paper_protective_authority",
    "build_governed_paper_protective_revocation",
    "governed_paper_protective_authority_context",
    "governed_paper_protective_authority_digest",
    "governed_paper_protective_authority_to_dict",
    "governed_paper_protective_context",
    "governed_paper_protective_revocation_digest",
    "governed_paper_protective_window",
    "verify_governed_paper_protective_authority",
    "verify_governed_paper_protective_revocation",
]
