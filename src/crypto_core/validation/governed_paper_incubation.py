"""Governed paper incubation (``S1_PAPER_INCUBATION_RECORD_V1_CONSTRUCTION``): the PAPER_INCUBATION_RECORD_V1 record, its
policy, the source-controlled authority registry and the derived lifecycle of one governed paper lineage.

Design authority: ``docs/crypto_core/s1_incubation_authority_registry_doctrine_adoption_v1.md`` (HD-INC-AUTH-1 r2, adopted
by PR #448), ``docs/crypto_core/s1_paper_incubation_doctrine_adoption_v1.md`` (decision packet r1, PR #446), the approved
companion ``s1_approved_doctrine_adoption_v1.md`` §§3.3-3.5, 4.1 and 4.6, RECORD A's ``KELLY_CLASS_COMPLETION_WINDOW_V1``
and PRDV4 §0.3 and §1.21. Paper-only, deterministic, point-in-time and fail-closed: no IO, clock, randomness, network or
environment, and exact arithmetic.

Authority (r2). One versioned registry in source is the sole POSITIVE authority index: a ``RECORD_APPROVAL`` row carries
the full canonical record and its separate approval, a ``RECORD_END`` row ends or blocks a record, and every row carries its
publication instant. The PRODUCTION registry is empty. A TEST-ONLY registry, installed by tests alone, admits only
``TEST_ONLY_SYNTHETIC`` rows. A row, digest or label is never sufficient by itself (A3-A6): a positive ACTIVE basis also needs,
covering the instant, an approval-provenance basis (A3), a temporal-provenance basis (A4), a complete revocation view (A5) and
a per-decision currentness basis (A6). No qualified source of any of them exists, so the production registry admits no basis
and production ACTIVE is unreachable; the test-only registry admits ``TEST_ONLY_SYNTHETIC`` bases only. A missing row never
proves non-revocation (A5): without a complete revocation view no record is ACTIVE.

Lifecycle at an instant (pre-decision view; the first final transition is permanent). Knowledge is point-in-time: the record
is known only from its approval row's publication ``P``, so every instant before ``P`` keeps the exact no-record state (a
later row never rewrites an earlier decision or prefix) and no final transition lies before ``P``:

* ``TERMINATED`` (final): a verification failure of the record (digest, schema, lineage, edge, validation, coverage, bounds,
  approval before the start, horizon), a second approval for the same lineage-edge key (both records, from the later
  publication) or a ``VALIDATION_NOT_CURRENT`` end, from its effective instant: a PROVEN loss of currentness;
* ``REVOKED`` (final): a ``REVOKED`` end, from its effective instant;
* ``EXPIRED_HOLD`` (final): the end ``X = min(S + T_max, G + H)``, or the admission of the 21st attempt, with a selected
  reading still covered;
* ``GRADUATED`` (final): every selected reading's coverage ended before the bound;
* ``NOT_ESTABLISHED``: no approval row yet, before ``max(S, P)``, the policy not admitted, a missing authority basis, or any
  KNOWN end row of the record (``ADVERSE_SIGNAL``, or a ``REVOKED``/``VALIDATION_NOT_CURRENT`` end before its effective
  instant), from that row's publication. This is UNKNOWN currentness or authority: BLOCKED/HOLD with no ACTIVE basis, never
  final by itself;
* ``ACTIVE``: everything else.

Coverage (PRDV4 §1.21; the adoption record's reading O1 and PIT-5). U5 is covered while the known closed trades hold no win
or no loss (RECORD A), and is BLOCKED while a closed trade is not yet known. U3 and U4 are covered only while the lineage
has sent no order of any kind: every order definition then counts zero, and after it the count depends on the pending
HC-14a/HC-14b method. U1 and U2 are never covered while the FCD-13 method is pending (a method choice is never absence).
An attempt is an entry admitted on the incubation basis, counted at admission whether or not it fills. No permission
survives the end: the incubation fill windows end at the first final instant, which includes the 21st admission, or at the
publication of the first known end row of the record, whichever is earlier.

Nothing here approves a record, a policy or a value, or creates an approval-table or registry entry, an order or capital.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.edge_pre_paper_validation_policy import EDGE_PRE_PAPER_ADMISSION_SCOPE
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperGenesisAuthority
from crypto_core.validation.governed_paper_kelly_reading import GovernedPaperKellyEvidence
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionIncubationWindow,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_wire_int_is_valid

_PREFIX = "governed_paper_incubation"
_DAY_NS = 86_400 * 1_000_000_000
GOVERNED_PAPER_INCUBATION_CONTRACT_ID = "S1_PAPER_INCUBATION_RECORD_V1_CONSTRUCTION"
GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA = "PAPER_INCUBATION_RECORD_V1"
GOVERNED_PAPER_INCUBATION_POLICY_SCHEMA = "governed-paper-incubation-policy.v1"
GOVERNED_PAPER_INCUBATION_ROW_SCHEMA = "governed-paper-incubation-registry-row.v1"
GOVERNED_PAPER_INCUBATION_BASIS_SCHEMA = "governed-paper-incubation-authority-basis.v1"
GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA = "governed-paper-incubation-evidence.v1"
# The human-approved r1 values (items 1.4-1.6), preserved by HD-INC-AUTH-1 r2 A7: fixed by the policy builder, never chosen
# here, and usable only through a policy whose exact digest the active policy table admits.
GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND = 21
GOVERNED_PAPER_INCUBATION_DURATION_DAYS = 91
GOVERNED_PAPER_INCUBATION_ENVELOPE_FRACTION = Fraction(8, 100)
GOVERNED_PAPER_INCUBATION_READINGS = ("U1", "U2", "U3", "U4", "U5")
GOVERNED_PAPER_INCUBATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("production_incubation_authorized", False),
    ("approver_identity_authenticated", False),
    ("signature_verified", False),
    ("revocation_view_complete_proven", False),
    ("per_decision_currentness_proven", False),
    ("temporal_provenance_qualified", False),
    ("stage4_evidence", False),
    ("readiness_evidence", False),
    ("real_paper_execution", False),
)


class GovernedPaperIncubationError(EdgeArtifactError):
    """Malformed input or a binding defect: no record, registry or evidence is represented over it."""


class GovernedPaperIncubationApprovalKind(str, Enum):
    """HUMAN_GOVERNANCE still needs the A3-A6 bases; TEST_ONLY_SYNTHETIC exists for tests only."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperIncubationRowKind(str, Enum):
    RECORD_APPROVAL = "RECORD_APPROVAL"
    RECORD_END = "RECORD_END"


class GovernedPaperIncubationEndCause(str, Enum):
    """Every end blocks the record from its publication (no ACTIVE basis, no new incubation entry, no fill authority).
    REVOKED is then final REVOKED and VALIDATION_NOT_CURRENT a proven loss (final TERMINATED), each from its effective
    instant; ADVERSE_SIGNAL proves no loss (O1: never final by itself)."""

    REVOKED = "REVOKED"
    VALIDATION_NOT_CURRENT = "VALIDATION_NOT_CURRENT"
    ADVERSE_SIGNAL = "ADVERSE_SIGNAL"


class GovernedPaperIncubationBasisKind(str, Enum):
    """The r2 bases a positive ACTIVE needs, each covering the instant: A3, A4, A5 and A6."""

    APPROVAL_PROVENANCE = "APPROVAL_PROVENANCE"
    TEMPORAL_PROVENANCE = "TEMPORAL_PROVENANCE"
    REVOCATION_VIEW_COMPLETE = "REVOCATION_VIEW_COMPLETE"
    DECISION_CURRENTNESS = "DECISION_CURRENTNESS"


class GovernedPaperIncubationState(str, Enum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    ACTIVE = "ACTIVE"
    GRADUATED = "GRADUATED"
    EXPIRED_HOLD = "EXPIRED_HOLD"
    REVOKED = "REVOKED"
    TERMINATED = "TERMINATED"


class GovernedPaperIncubationReadingStatus(str, Enum):
    """A selected reading's coverage at a decision: COVERED (undefined only for missing own history under ACTIVE), ENDED
    (coverage ended for good: an ordinary reading), BLOCKED (undefined for another reason) or NOT_SELECTED."""

    COVERED = "COVERED"
    ENDED = "ENDED"
    BLOCKED = "BLOCKED"
    NOT_SELECTED = "NOT_SELECTED"


_FINAL_STATES = (
    GovernedPaperIncubationState.TERMINATED,
    GovernedPaperIncubationState.REVOKED,
    GovernedPaperIncubationState.EXPIRED_HOLD,
    GovernedPaperIncubationState.GRADUATED,
)
_RANK = {state: rank for rank, state in enumerate(_FINAL_STATES)}  # equal-instant precedence: TERMINATED first


@dataclass(frozen=True)
class GovernedPaperIncubationPolicy:
    """The one digest-bound policy artifact of the approved values (A_max, T_max, W_INC) and the closed reading universe."""

    schema_version: str
    policy_id: str
    policy_version: str
    attempt_bound: int
    duration_bound_days: int
    envelope_fraction: str
    readings: tuple[str, ...]
    policy_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationPolicyApproval:
    approval_kind: GovernedPaperIncubationApprovalKind
    approver_reference: str
    approved_policy_digest: str
    approval_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationPolicyTable:
    """Which policy approvals may be used: ``production`` lists HUMAN_GOVERNANCE approval digests; ``test_only`` lists
    none and admits only TEST_ONLY_SYNTHETIC approvals."""

    table_id: str
    admitted_kind: GovernedPaperIncubationApprovalKind
    admitted_approval_digests: tuple[str, ...]


# No separate human approval lists any incubation policy for production use, so this table refuses every one.
GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE = GovernedPaperIncubationPolicyTable(
    table_id="production",
    admitted_kind=GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE,
    admitted_approval_digests=(),
)
_POLICY_TABLE = GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperIncubationRecord:
    """PAPER_INCUBATION_RECORD_V1 (companion §3.1): ``record_digest`` covers every other field; the end X and the separate
    approval are not part of it."""

    schema_version: str
    genesis_id: str
    genesis_digest: str
    admission_scope: str
    genesis_start_ns: int
    bootstrap_horizon_days: int
    edge_id: str
    strategy_spec_digest: str
    parameter_digest: str
    ef5_preregistration_digest: str
    ef7_admission_digest: str
    ef7_evidence_digest: str
    trial_chain_digest: str
    covered: tuple[str, ...]
    attempt_bound: int
    duration_bound_days: int
    start_ns: int
    record_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationRow:
    """One append-only registry row. A RECORD_APPROVAL carries its record; a RECORD_END names its record digest, cause and
    effective instant. ``row_digest`` covers every other field."""

    schema_version: str
    row_kind: GovernedPaperIncubationRowKind
    lineage_genesis_digest: str
    edge_id: str
    record_digest: str
    record: GovernedPaperIncubationRecord | None
    end_cause: GovernedPaperIncubationEndCause | None
    effective_at_ns: int | None
    approval_kind: GovernedPaperIncubationApprovalKind
    approver_reference: str
    approval_time_ns: int
    decision_record_digest: str
    published_at_ns: int
    row_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationBasis:
    """One r2 authority basis of one record over ``[valid_from_ns, valid_until_ns)``; only TEST_ONLY_SYNTHETIC exists."""

    schema_version: str
    basis_kind: GovernedPaperIncubationBasisKind
    record_digest: str
    valid_from_ns: int
    valid_until_ns: int
    approval_kind: GovernedPaperIncubationApprovalKind
    basis_reference: str
    basis_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationRegistry:
    """The source-controlled authority registry: ``production`` (HUMAN_GOVERNANCE rows; no basis can be qualified) or
    ``test_only`` (TEST_ONLY_SYNTHETIC rows and bases)."""

    registry_id: str
    admitted_kind: GovernedPaperIncubationApprovalKind
    rows: tuple[GovernedPaperIncubationRow, ...]
    bases: tuple[GovernedPaperIncubationBasis, ...]


# The production registry: empty. No record is approved and no basis source is qualified (A3-A6).
GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY = GovernedPaperIncubationRegistry(
    registry_id="production",
    admitted_kind=GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE,
    rows=(),
    bases=(),
)
_REGISTRY = GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY  # tests alone install a test-only registry


@dataclass(frozen=True)
class GovernedPaperIncubationContext:
    """One lineage's incubation context as the day seal supplies it: the policy and its approval, the same every day.
    The registry is never supplied: the active registry is read."""

    policy: GovernedPaperIncubationPolicy
    policy_approval: GovernedPaperIncubationPolicyApproval | None


@dataclass(frozen=True)
class GovernedPaperIncubationReading:
    reading_id: str
    status: GovernedPaperIncubationReadingStatus
    reason: str


@dataclass(frozen=True)
class GovernedPaperIncubationDecision:
    """The incubation facts of one entry decision at its own instant, before its admission."""

    decision_sequence: int
    decision_time_ns: int
    exposure_increasing: bool
    state: GovernedPaperIncubationState
    state_reason: str
    attempts_before: int
    readings: tuple[GovernedPaperIncubationReading, ...]
    kelly_cold_start_status: str
    kelly_cold_start_reason: str


@dataclass(frozen=True)
class GovernedPaperIncubationEvidence:
    """The derived incubation evidence of one governed evaluation; never accepted."""

    schema_version: str
    contract_id: str
    registry_id: str
    lineage_genesis_digest: str
    edge_id: str
    projection_digest: str
    policy_digest: str
    policy_approval_digest: str
    policy_admitted: bool
    record_digest: str
    record_published_ns: int | None
    start_ns: int | None
    end_ns: int | None
    horizon_ns: int
    covered: tuple[str, ...]
    incubation_entry_decision_sequences: tuple[int, ...]
    kelly_cold_start_cover: bool
    fill_windows: tuple[HistoricalExecutionIncubationWindow, ...]
    final_state: GovernedPaperIncubationState | None
    final_at_ns: int | None
    final_reason: str
    decisions: tuple[GovernedPaperIncubationDecision, ...]
    evidence_digest: str
    paper_only: bool = True
    production_incubation_authorized: bool = False
    approver_identity_authenticated: bool = False
    signature_verified: bool = False
    revocation_view_complete_proven: bool = False
    per_decision_currentness_proven: bool = False
    temporal_provenance_qualified: bool = False
    stage4_evidence: bool = False
    readiness_evidence: bool = False
    real_paper_execution: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _fail(code: str) -> GovernedPaperIncubationError:
    return GovernedPaperIncubationError(f"{_PREFIX}:{code}")


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


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


def _digest(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > 256:
        raise _fail(f"{code}_malformed")
    return value


def _hex(value: object, code: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{code}_malformed")
    return value  # type: ignore[return-value]


def _instant(value: object, code: str) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail(f"{code}_malformed")
    return value  # type: ignore[return-value]


# --- the policy and its approval -----------------------------------------------------------------------------------------


def governed_paper_incubation_policy_digest(policy: GovernedPaperIncubationPolicy) -> str:
    return edge_payload_digest(_to_payload(policy), "policy_digest")


def build_governed_paper_incubation_policy(*, policy_id: str, policy_version: str) -> GovernedPaperIncubationPolicy:
    """The incubation policy: every value is the human-approved r1 value (preserved by r2 A7); only the identity is
    chosen. Using it still needs an approval the active policy table admits."""

    seed = GovernedPaperIncubationPolicy(
        schema_version=GOVERNED_PAPER_INCUBATION_POLICY_SCHEMA,
        policy_id=_text(policy_id, "policy_id"),
        policy_version=_text(policy_version, "policy_version"),
        attempt_bound=GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND,
        duration_bound_days=GOVERNED_PAPER_INCUBATION_DURATION_DAYS,
        envelope_fraction=str(GOVERNED_PAPER_INCUBATION_ENVELOPE_FRACTION),
        readings=GOVERNED_PAPER_INCUBATION_READINGS,
        policy_digest="",
    )
    return replace(seed, policy_digest=governed_paper_incubation_policy_digest(seed))


def governed_paper_incubation_policy_approval_digest(approval: GovernedPaperIncubationPolicyApproval) -> str:
    return edge_payload_digest(_to_payload(approval), "approval_digest")


def build_governed_paper_incubation_policy_approval(
    *, approval_kind: GovernedPaperIncubationApprovalKind, approver_reference: str, approved_policy_digest: str
) -> GovernedPaperIncubationPolicyApproval:
    if type(approval_kind) is not GovernedPaperIncubationApprovalKind:
        raise _fail("policy_approval_kind_malformed")
    seed = GovernedPaperIncubationPolicyApproval(
        approval_kind=approval_kind,
        approver_reference=_text(approver_reference, "policy_approver_reference"),
        approved_policy_digest=_hex(approved_policy_digest, "approved_policy_digest"),
        approval_digest="",
    )
    return replace(seed, approval_digest=governed_paper_incubation_policy_approval_digest(seed))


def _canonical_policy(policy: object) -> GovernedPaperIncubationPolicy:
    if type(policy) is not GovernedPaperIncubationPolicy:
        raise _fail("policy_malformed")
    rebuilt = build_governed_paper_incubation_policy(policy_id=policy.policy_id, policy_version=policy.policy_version)
    if _to_payload(rebuilt) != _to_payload(policy) or rebuilt != policy:
        raise _fail("policy_not_canonical")
    return rebuilt


def _canonical_policy_table(table: object) -> GovernedPaperIncubationPolicyTable:
    if type(table) is not GovernedPaperIncubationPolicyTable:
        raise _fail("policy_table_malformed")
    digests = table.admitted_approval_digests
    if type(digests) is not tuple or any(not edge_is_hex64(item) for item in digests):
        raise _fail("policy_table_malformed")
    if table.table_id == "production" and table.admitted_kind is GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE:
        return table
    if (
        table.table_id == "test_only"
        and table.admitted_kind is GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC
        and not digests
    ):
        return table
    raise _fail("policy_table_malformed")


def governed_paper_incubation_active_policy_table() -> GovernedPaperIncubationPolicyTable:
    """The active policy table (the production table unless a test installed the test-only one)."""

    return _canonical_policy_table(_POLICY_TABLE)


def governed_paper_incubation_policy_admission(
    policy: GovernedPaperIncubationPolicy, approval: GovernedPaperIncubationPolicyApproval | None
) -> str:
    """Why the policy may not be used under the active table (empty when it may)."""

    table = governed_paper_incubation_active_policy_table()
    if approval is None:
        return "policy_approval_missing"
    if type(approval) is not GovernedPaperIncubationPolicyApproval or (
        governed_paper_incubation_policy_approval_digest(approval) != approval.approval_digest
    ):
        raise _fail("policy_approval_not_authentic")
    if approval.approved_policy_digest != policy.policy_digest:
        return "policy_approval_names_another_policy"
    if table.table_id == "production":
        if approval.approval_kind is not GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE:
            return "synthetic_policy_approval_refused_on_the_production_table"
        if approval.approval_digest not in table.admitted_approval_digests:
            return "policy_approval_not_authorized_for_production_use"
        return ""
    if approval.approval_kind is not GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC:
        return "only_test_only_synthetic_policy_approvals_on_the_test_only_table"
    return ""


def governed_paper_incubation_canonical_context(context: object) -> GovernedPaperIncubationContext:
    if type(context) is not GovernedPaperIncubationContext:
        raise _fail("context_malformed")
    approval = context.policy_approval
    if approval is not None and (
        type(approval) is not GovernedPaperIncubationPolicyApproval
        or type(approval.approval_kind) is not GovernedPaperIncubationApprovalKind
        or governed_paper_incubation_policy_approval_digest(approval) != approval.approval_digest
    ):
        raise _fail("policy_approval_not_authentic")
    return GovernedPaperIncubationContext(_canonical_policy(context.policy), approval)


# --- the record ------------------------------------------------------------------------------------------------------------


def governed_paper_incubation_record_digest(record: GovernedPaperIncubationRecord) -> str:
    """The SHA-256 of the record's canonical bytes without its self-digest (companion §3.1)."""

    return edge_payload_digest(_to_payload(record), "record_digest")


def build_governed_paper_incubation_record(  # noqa: PLR0913 - every supplied field of companion §3.1
    *,
    genesis_id: str,
    genesis_digest: str,
    admission_scope: str,
    genesis_start_ns: int,
    bootstrap_horizon_days: int,
    edge_id: str,
    strategy_spec_digest: str,
    parameter_digest: str,
    ef5_preregistration_digest: str,
    ef7_admission_digest: str,
    ef7_evidence_digest: str,
    trial_chain_digest: str,
    covered: tuple[str, ...],
    attempt_bound: int,
    duration_bound_days: int,
    start_ns: int,
) -> GovernedPaperIncubationRecord:
    """One canonical record with its recomputed digest. Structure only: verification against the lineage, the policy and
    the authority happens where the record is used."""

    if type(covered) is not tuple or any(type(item) is not str for item in covered):
        raise _fail("covered_malformed")
    for value, name in ((attempt_bound, "attempt_bound"), (duration_bound_days, "duration_bound_days")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_malformed")
    if not historical_execution_wire_int_is_valid(bootstrap_horizon_days, minimum=0):
        raise _fail("bootstrap_horizon_days_malformed")
    seed = GovernedPaperIncubationRecord(
        schema_version=GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA,
        genesis_id=_text(genesis_id, "genesis_id"),
        genesis_digest=_hex(genesis_digest, "genesis_digest"),
        admission_scope=_text(admission_scope, "admission_scope"),
        genesis_start_ns=_instant(genesis_start_ns, "genesis_start_ns"),
        bootstrap_horizon_days=bootstrap_horizon_days,
        edge_id=_text(edge_id, "edge_id"),
        strategy_spec_digest=_hex(strategy_spec_digest, "strategy_spec_digest"),
        parameter_digest=_hex(parameter_digest, "parameter_digest"),
        ef5_preregistration_digest=_hex(ef5_preregistration_digest, "ef5_preregistration_digest"),
        ef7_admission_digest=_hex(ef7_admission_digest, "ef7_admission_digest"),
        ef7_evidence_digest=_hex(ef7_evidence_digest, "ef7_evidence_digest"),
        trial_chain_digest=_hex(trial_chain_digest, "trial_chain_digest"),
        covered=covered,
        attempt_bound=attempt_bound,
        duration_bound_days=duration_bound_days,
        start_ns=_instant(start_ns, "start_ns"),
        record_digest="",
    )
    return replace(seed, record_digest=governed_paper_incubation_record_digest(seed))


def governed_paper_incubation_record_for_lineage(
    authority: GovernedPaperGenesisAuthority, *, covered: tuple[str, ...], start_ns: int
) -> GovernedPaperIncubationRecord:
    """The record that binds the lineage, edge and validation of ``authority`` exactly, with the approved r1 bounds: a
    construction convenience for the record a human would approve; it approves nothing."""

    genesis, admission = authority.genesis, authority.paper_admission
    return build_governed_paper_incubation_record(
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        admission_scope=EDGE_PRE_PAPER_ADMISSION_SCOPE,
        genesis_start_ns=genesis.genesis_start_ns,
        bootstrap_horizon_days=genesis.bootstrap_horizon_days,
        edge_id=genesis.strategy_id,
        strategy_spec_digest=genesis.strategy_spec_digest,
        parameter_digest=genesis.parameter_assignment_digest,
        ef5_preregistration_digest=admission.preregistration_digest,
        ef7_admission_digest=genesis.paper_admission_digest,
        ef7_evidence_digest=admission.pre_paper_evidence_digest,
        trial_chain_digest=admission.trial_chain_digest,
        covered=covered,
        attempt_bound=GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND,
        duration_bound_days=GOVERNED_PAPER_INCUBATION_DURATION_DAYS,
        start_ns=start_ns,
    )


def _record_failures(
    record: GovernedPaperIncubationRecord,
    row: GovernedPaperIncubationRow,
    authority: GovernedPaperGenesisAuthority,
    policy: GovernedPaperIncubationPolicy,
) -> list[str]:
    """Why the record fails verification against the lineage, its validation, the policy and its approval (empty if it
    verifies). Every digest is recomputed; the static EF-5/EF-7/trial-chain binding is re-derived from the genesis."""

    if type(record) is not GovernedPaperIncubationRecord:
        return ["incubation_record_malformed"]
    if governed_paper_incubation_record_digest(record) != record.record_digest or record.record_digest != (
        row.record_digest
    ):
        return ["incubation_record_digest_mismatch"]
    genesis, admission = authority.genesis, authority.paper_admission
    expected = {
        "schema_version": GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA,
        "genesis_id": genesis.genesis_id,
        "genesis_digest": genesis.genesis_digest,
        "admission_scope": EDGE_PRE_PAPER_ADMISSION_SCOPE,
        "genesis_start_ns": genesis.genesis_start_ns,
        "bootstrap_horizon_days": genesis.bootstrap_horizon_days,
        "edge_id": genesis.strategy_id,
        "strategy_spec_digest": genesis.strategy_spec_digest,
        "parameter_digest": genesis.parameter_assignment_digest,
        "ef5_preregistration_digest": admission.preregistration_digest,
        "ef7_admission_digest": genesis.paper_admission_digest,
        "ef7_evidence_digest": admission.pre_paper_evidence_digest,
        "trial_chain_digest": admission.trial_chain_digest,
        "attempt_bound": policy.attempt_bound,
        "duration_bound_days": policy.duration_bound_days,
    }
    failures = [
        f"incubation_record_{name}_mismatch"
        for name, value in expected.items()
        if type(getattr(record, name)) is not type(value) or getattr(record, name) != value
    ]
    if admission.pre_paper_validation_passed is not True or admission.preregistration_sealed is not True:
        failures.append("incubation_record_validation_not_a_sealed_ef7_pass")
    if not genesis.authorized:
        failures.append("incubation_record_genesis_not_authorized")
    covered = record.covered
    if (
        not covered
        or list(covered) != sorted(set(covered))
        or any(item not in GOVERNED_PAPER_INCUBATION_READINGS for item in covered)
    ):
        failures.append("incubation_class_not_covered")
    if row.approval_time_ns > record.start_ns:
        failures.append("incubation_record_approved_after_its_start")
    if record.start_ns < genesis.genesis_start_ns:
        failures.append("incubation_record_starts_before_its_genesis")
    if record.start_ns + record.duration_bound_days * _DAY_NS > genesis.genesis_start_ns + (
        genesis.bootstrap_horizon_days * _DAY_NS
    ):
        failures.append("incubation_horizon_exceeds_lineage")
    return failures


# --- the registry ----------------------------------------------------------------------------------------------------------


def governed_paper_incubation_row_digest(row: GovernedPaperIncubationRow) -> str:
    return edge_payload_digest(_to_payload(row), "row_digest")


def build_governed_paper_incubation_approval_row(
    *,
    record: GovernedPaperIncubationRecord,
    approval_kind: GovernedPaperIncubationApprovalKind,
    approver_reference: str,
    approval_time_ns: int,
    decision_record_digest: str,
    published_at_ns: int,
) -> GovernedPaperIncubationRow:
    if type(record) is not GovernedPaperIncubationRecord:
        raise _fail("record_malformed")
    seed = GovernedPaperIncubationRow(
        schema_version=GOVERNED_PAPER_INCUBATION_ROW_SCHEMA,
        row_kind=GovernedPaperIncubationRowKind.RECORD_APPROVAL,
        lineage_genesis_digest=record.genesis_digest,
        edge_id=record.edge_id,
        record_digest=record.record_digest,
        record=record,
        end_cause=None,
        effective_at_ns=None,
        approval_kind=approval_kind,
        approver_reference=_text(approver_reference, "approver_reference"),
        approval_time_ns=_instant(approval_time_ns, "approval_time_ns"),
        decision_record_digest=_hex(decision_record_digest, "decision_record_digest"),
        published_at_ns=_instant(published_at_ns, "published_at_ns"),
        row_digest="",
    )
    return replace(seed, row_digest=governed_paper_incubation_row_digest(seed))


def build_governed_paper_incubation_end_row(  # noqa: PLR0913
    *,
    lineage_genesis_digest: str,
    edge_id: str,
    record_digest: str,
    end_cause: GovernedPaperIncubationEndCause,
    effective_at_ns: int,
    approval_kind: GovernedPaperIncubationApprovalKind,
    approver_reference: str,
    approval_time_ns: int,
    decision_record_digest: str,
    published_at_ns: int,
) -> GovernedPaperIncubationRow:
    if type(end_cause) is not GovernedPaperIncubationEndCause:
        raise _fail("end_cause_malformed")
    seed = GovernedPaperIncubationRow(
        schema_version=GOVERNED_PAPER_INCUBATION_ROW_SCHEMA,
        row_kind=GovernedPaperIncubationRowKind.RECORD_END,
        lineage_genesis_digest=_hex(lineage_genesis_digest, "lineage_genesis_digest"),
        edge_id=_text(edge_id, "edge_id"),
        record_digest=_hex(record_digest, "record_digest"),
        record=None,
        end_cause=end_cause,
        effective_at_ns=_instant(effective_at_ns, "effective_at_ns"),
        approval_kind=approval_kind,
        approver_reference=_text(approver_reference, "approver_reference"),
        approval_time_ns=_instant(approval_time_ns, "approval_time_ns"),
        decision_record_digest=_hex(decision_record_digest, "decision_record_digest"),
        published_at_ns=_instant(published_at_ns, "published_at_ns"),
        row_digest="",
    )
    return replace(seed, row_digest=governed_paper_incubation_row_digest(seed))


def governed_paper_incubation_basis_digest(basis: GovernedPaperIncubationBasis) -> str:
    return edge_payload_digest(_to_payload(basis), "basis_digest")


def build_governed_paper_incubation_basis(
    *,
    basis_kind: GovernedPaperIncubationBasisKind,
    record_digest: str,
    valid_from_ns: int,
    valid_until_ns: int,
    basis_reference: str,
) -> GovernedPaperIncubationBasis:
    """A TEST_ONLY_SYNTHETIC basis: no qualified source of any r2 basis exists, so no other kind can be built."""

    if type(basis_kind) is not GovernedPaperIncubationBasisKind:
        raise _fail("basis_kind_malformed")
    if _instant(valid_until_ns, "valid_until_ns") <= _instant(valid_from_ns, "valid_from_ns"):
        raise _fail("basis_window_empty")
    seed = GovernedPaperIncubationBasis(
        schema_version=GOVERNED_PAPER_INCUBATION_BASIS_SCHEMA,
        basis_kind=basis_kind,
        record_digest=_hex(record_digest, "record_digest"),
        valid_from_ns=valid_from_ns,
        valid_until_ns=valid_until_ns,
        approval_kind=GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC,
        basis_reference=_text(basis_reference, "basis_reference"),
        basis_digest="",
    )
    return replace(seed, basis_digest=governed_paper_incubation_basis_digest(seed))


def _canonical_row(row: object, kind: GovernedPaperIncubationApprovalKind) -> GovernedPaperIncubationRow:
    if type(row) is not GovernedPaperIncubationRow or row.schema_version != GOVERNED_PAPER_INCUBATION_ROW_SCHEMA:
        raise _fail("registry_row_malformed")
    if type(row.row_kind) is not GovernedPaperIncubationRowKind or type(row.approval_kind) is not (
        GovernedPaperIncubationApprovalKind
    ):
        raise _fail("registry_row_malformed")
    if governed_paper_incubation_row_digest(row) != row.row_digest:
        raise _fail("registry_row_digest_mismatch")
    if row.approval_kind is not kind:
        raise _fail("registry_row_approval_kind_not_admitted_by_the_registry")
    if row.published_at_ns < row.approval_time_ns:
        raise _fail("registry_row_published_before_its_approval")
    if row.row_kind is GovernedPaperIncubationRowKind.RECORD_APPROVAL:
        if row.record is None or row.end_cause is not None or row.effective_at_ns is not None:
            raise _fail("registry_row_malformed")
    elif (
        row.record is not None
        or type(row.end_cause) is not GovernedPaperIncubationEndCause
        or row.effective_at_ns is None
        or row.effective_at_ns < row.published_at_ns
    ):
        raise _fail("registry_end_row_malformed_or_retroactive")
    return row


def _canonical_registry(registry: object) -> GovernedPaperIncubationRegistry:
    if type(registry) is not GovernedPaperIncubationRegistry:
        raise _fail("registry_malformed")
    if type(registry.rows) is not tuple or type(registry.bases) is not tuple:
        raise _fail("registry_malformed")
    if registry.registry_id == "production":
        if registry.admitted_kind is not GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE:
            raise _fail("registry_malformed")
        if registry.bases:  # A3-A6: no qualified basis source exists, so production admits none
            raise _fail("production_registry_admits_no_unqualified_basis")
    elif registry.registry_id != "test_only" or (
        registry.admitted_kind is not GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC
    ):
        raise _fail("registry_malformed")
    rows = tuple(_canonical_row(row, registry.admitted_kind) for row in registry.rows)
    if [(row.published_at_ns, row.row_digest) for row in rows] != sorted(
        (row.published_at_ns, row.row_digest) for row in rows
    ) or len({row.row_digest for row in rows}) != len(rows):
        raise _fail("registry_rows_not_append_ordered_or_duplicated")
    for basis in registry.bases:
        if (
            type(basis) is not GovernedPaperIncubationBasis
            or type(basis.basis_kind) is not GovernedPaperIncubationBasisKind
            or basis.approval_kind is not GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC
            or governed_paper_incubation_basis_digest(basis) != basis.basis_digest
        ):
            raise _fail("registry_basis_malformed")
    return registry


def governed_paper_incubation_active_registry() -> GovernedPaperIncubationRegistry:
    """The active registry (the production registry unless a test installed the test-only one)."""

    return _canonical_registry(_REGISTRY)


def governed_paper_incubation_projection_digest(
    registry: GovernedPaperIncubationRegistry, *, lineage_genesis_digest: str, edge_id: str, before_ns: int
) -> str:
    """The digest of the key's rows published strictly before ``before_ns`` and of the bases of those rows' records:
    the X1 identity a day seal binds, so no sealed day gains, loses or changes a row after its seal."""

    rows = [
        row
        for row in registry.rows
        if row.lineage_genesis_digest == lineage_genesis_digest
        and row.edge_id == edge_id
        and row.published_at_ns < before_ns
    ]
    digests = {row.record_digest for row in rows}
    bases = [basis.basis_digest for basis in registry.bases if basis.record_digest in digests]
    return _digest(
        {
            "registry_id": registry.registry_id,
            "rows": [row.row_digest for row in rows],
            "bases": sorted(bases),
        }
    )


# --- the lifecycle ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _View:
    """One lineage-edge key's registry view up to the horizon, verified once. The record is known from its approval's
    publication ``P`` only: before ``P`` every instant sees the exact no-record state, and no final transition, end signal
    or block lies before ``P``. ``block`` is the first instant (and reason) at which an end row of the record is KNOWN:
    from its publication it removes every positive incubation basis, while a REVOKED or VALIDATION_NOT_CURRENT row
    becomes final only at its effective instant (``finals``)."""

    record: GovernedPaperIncubationRecord | None
    approval_row: GovernedPaperIncubationRow | None
    end_ns: int | None
    finals: tuple[tuple[int, int, GovernedPaperIncubationState, str], ...]
    block: tuple[int, str] | None
    bases: tuple[GovernedPaperIncubationBasis, ...]

    def known_at(self, time_ns: int) -> bool:
        return self.approval_row is not None and self.approval_row.published_at_ns <= time_ns


def _view(
    registry: GovernedPaperIncubationRegistry,
    authority: GovernedPaperGenesisAuthority,
    policy: GovernedPaperIncubationPolicy,
    horizon_ns: int,
) -> _View:
    genesis = authority.genesis
    rows = [
        row
        for row in registry.rows
        if row.lineage_genesis_digest == genesis.genesis_digest
        and row.edge_id == genesis.strategy_id
        and row.published_at_ns < horizon_ns
    ]
    approvals = [row for row in rows if row.row_kind is GovernedPaperIncubationRowKind.RECORD_APPROVAL]
    if not approvals:
        return _View(None, None, None, (), None, ())
    first = approvals[0]
    record = first.record
    known = first.published_at_ns  # P: nothing about the record is knowledge before its approval's publication
    finals: list[tuple[int, int, GovernedPaperIncubationState, str]] = []
    terminated = _RANK[GovernedPaperIncubationState.TERMINATED]
    failures = _record_failures(record, first, authority, policy)  # type: ignore[arg-type]
    if failures:
        finals.append((known, terminated, GovernedPaperIncubationState.TERMINATED, failures[0]))
    if len(approvals) > 1:  # a second approved record for the same key terminates both, from its publication
        finals.append(
            (
                approvals[1].published_at_ns,
                terminated,
                GovernedPaperIncubationState.TERMINATED,
                "incubation_duplicate_record",
            )
        )
    blocks: list[tuple[int, str]] = []
    for row in rows:
        if row.row_kind is not GovernedPaperIncubationRowKind.RECORD_END or row.record_digest != first.record_digest:
            continue
        # knowledge time: the signal is known at its publication (never before P) and blocks from then on
        published = max(row.published_at_ns, known)
        effective = max(row.effective_at_ns, known)  # type: ignore[type-var]
        if row.end_cause is GovernedPaperIncubationEndCause.REVOKED:
            blocks.append((published, "incubation_revocation_known"))
            finals.append(
                (
                    effective,
                    _RANK[GovernedPaperIncubationState.REVOKED],
                    GovernedPaperIncubationState.REVOKED,
                    "incubation_revoked",
                )
            )  # type: ignore[arg-type]
        elif row.end_cause is GovernedPaperIncubationEndCause.VALIDATION_NOT_CURRENT:
            blocks.append((published, "incubation_validation_loss_known"))
            finals.append(
                (effective, terminated, GovernedPaperIncubationState.TERMINATED, "incubation_validation_not_current")
            )  # type: ignore[arg-type]
        else:  # never final by itself (O1)
            blocks.append((published, "incubation_adverse_signal_known"))
    end_ns: int | None = None
    if not failures:
        end_ns = min(
            record.start_ns + record.duration_bound_days * _DAY_NS,  # type: ignore[union-attr]
            genesis.genesis_start_ns + genesis.bootstrap_horizon_days * _DAY_NS,
        )
    bases = tuple(basis for basis in registry.bases if basis.record_digest == first.record_digest)
    return _View(record, first, end_ns, tuple(sorted(finals)), min(blocks) if blocks else None, bases)


def _class_completion_ns(kelly: GovernedPaperKellyEvidence | None) -> int | None:
    """The first knowledge instant at which a known win and a known loss coexist (RECORD A class completion)."""

    if kelly is None:
        return None
    win = min((item.knowledge_ns for item in kelly.trades if item.trade_class == "WIN"), default=None)
    loss = min((item.knowledge_ns for item in kelly.trades if item.trade_class == "LOSS"), default=None)
    return None if win is None or loss is None else max(win, loss)


def _orders_before(outcome: HistoricalExecutionGovernedPaperOutcome, time_ns: int) -> int:
    """Every order-like event of the lineage strictly before ``time_ns``: decision intents of any outcome, protective
    attempts and protective children. Over-counting is the fail-closed direction (U3/U4 stop being covered)."""

    count = sum(1 for item in outcome.intents if item.decision_time_ns < time_ns)
    count += sum(1 for item in getattr(outcome, "protective_attempts", ()) if item.attempt_time_ns < time_ns)
    count += sum(1 for item in getattr(outcome, "protective_children", ()) if item.attempt_time_ns < time_ns)
    return count


def _missing_bases(view: _View, time_ns: int) -> list[str]:
    return [
        kind.value
        for kind in GovernedPaperIncubationBasisKind
        if not any(
            basis.basis_kind is kind and basis.valid_from_ns <= time_ns < basis.valid_until_ns for basis in view.bases
        )
    ]


def _first_final(
    view: _View, time_ns: int, graduated_ns: int | None, exhausted_ns: int | None
) -> tuple[int, int, GovernedPaperIncubationState, str] | None:
    events = [item for item in view.finals if item[0] <= time_ns]
    record = view.record
    if view.end_ns is not None and record is not None and view.approval_row is not None:
        known = view.approval_row.published_at_ns  # never final before the record is known (no retroactive end)
        if graduated_ns is not None and graduated_ns < view.end_ns and max(graduated_ns, known) <= time_ns:
            events.append(
                (
                    max(graduated_ns, known),
                    _RANK[GovernedPaperIncubationState.GRADUATED],
                    GovernedPaperIncubationState.GRADUATED,
                    "incubation_graduated",
                )
            )
        if max(view.end_ns, known) <= time_ns:
            events.append(
                (
                    max(view.end_ns, known),
                    _RANK[GovernedPaperIncubationState.EXPIRED_HOLD],
                    GovernedPaperIncubationState.EXPIRED_HOLD,
                    "incubation_expired",
                )
            )
        if exhausted_ns is not None and exhausted_ns <= time_ns:
            events.append(
                (
                    exhausted_ns,
                    _RANK[GovernedPaperIncubationState.EXPIRED_HOLD],
                    GovernedPaperIncubationState.EXPIRED_HOLD,
                    "incubation_attempts_exhausted",
                )
            )
    return min(events) if events else None


def _readings(  # noqa: PLR0913
    record: GovernedPaperIncubationRecord | None,
    active: bool,  # noqa: FBT001
    state_reason: str,
    orders: int,
    completion_ns: int | None,
    time_ns: int,
    unknown_closed: bool,  # noqa: FBT001
) -> tuple[GovernedPaperIncubationReading, ...]:
    covered = () if record is None else record.covered
    readings = []
    for reading in GOVERNED_PAPER_INCUBATION_READINGS:
        if reading not in covered:
            readings.append(
                GovernedPaperIncubationReading(reading, GovernedPaperIncubationReadingStatus.NOT_SELECTED, "")
            )
            continue
        ended = reading == "U5" and completion_ns is not None and completion_ns <= time_ns
        if ended:
            status, reason = GovernedPaperIncubationReadingStatus.ENDED, "kelly_class_completion_known"
        elif not active:
            status, reason = GovernedPaperIncubationReadingStatus.BLOCKED, state_reason
        elif reading in ("U1", "U2"):
            status, reason = GovernedPaperIncubationReadingStatus.BLOCKED, "own_history_method_unapproved:FCD-13"
        elif reading in ("U3", "U4"):
            if orders:
                status, reason = (
                    GovernedPaperIncubationReadingStatus.BLOCKED,
                    "own_history_order_definition_unapproved:HC-14a,HC-14b",
                )
            else:
                status, reason = GovernedPaperIncubationReadingStatus.COVERED, "no_order_sent"
        elif unknown_closed:
            status, reason = GovernedPaperIncubationReadingStatus.BLOCKED, "KELLY_TRADE_COUNT_UNPROVEN"
        else:
            status, reason = GovernedPaperIncubationReadingStatus.COVERED, "kelly_class_incomplete"
        readings.append(GovernedPaperIncubationReading(reading, status, reason))
    return tuple(readings)


def derive_governed_paper_incubation_evidence(  # noqa: C901, PLR0913, PLR0915 - one linear derivation
    *,
    context: GovernedPaperIncubationContext,
    authority: GovernedPaperGenesisAuthority,
    decisions: Sequence[tuple[int, int, bool]],
    incubation_admissions: tuple[int, ...],
    outcome: HistoricalExecutionGovernedPaperOutcome,
    kelly: GovernedPaperKellyEvidence | None,
    horizon_ns: int,
) -> GovernedPaperIncubationEvidence:
    """The incubation evidence of one governed evaluation (module docstring), derived and never accepted.

    ``decisions`` are the run's entry decisions ``(sequence, instant, exposure_increasing)`` in time order;
    ``incubation_admissions`` are the decisions the schedule under evaluation admits on the incubation basis (the fixed
    point's own assignment); ``outcome`` and ``kelly`` are the same evaluation's governed re-run and Kelly evidence. Every
    fact of a decision depends only on what precedes it. Pure.
    """

    context = governed_paper_incubation_canonical_context(context)
    if type(authority) is not GovernedPaperGenesisAuthority:
        raise _fail("authority_malformed")
    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome:
        raise _fail("outcome_malformed")
    if kelly is not None and type(kelly) is not GovernedPaperKellyEvidence:
        raise _fail("kelly_evidence_malformed")
    horizon = _instant(horizon_ns, "horizon_ns")
    items = tuple(decisions)
    if any(
        type(item) is not tuple
        or len(item) != 3  # noqa: PLR2004
        or not historical_execution_wire_int_is_valid(item[0], minimum=0)
        or not historical_execution_wire_int_is_valid(item[1], minimum=0)
        or type(item[2]) is not bool
        for item in items
    ):
        raise _fail("decisions_malformed")
    if [(item[1], item[0]) for item in items] != sorted((item[1], item[0]) for item in items):
        raise _fail("decisions_not_in_time_order")
    sequences = [item[0] for item in items]
    if len(set(sequences)) != len(sequences):
        raise _fail("decisions_duplicated")  # a duplicate observation never counts twice (T-INC-16)
    if type(incubation_admissions) is not tuple or not set(incubation_admissions) <= set(sequences):
        raise _fail("incubation_admissions_malformed")
    registry = governed_paper_incubation_active_registry()
    policy = context.policy
    admission_reason = governed_paper_incubation_policy_admission(policy, context.policy_approval)
    genesis = authority.genesis
    view = _view(registry, authority, policy, horizon)
    completion = _class_completion_ns(kelly)
    graduated_ns = (
        completion if view.record is not None and view.record.covered == ("U5",) else None
    )  # only U5 can end while FCD-13 and HC-14a/b are pending
    readings_by_sequence = {} if kelly is None else {item.decision_sequence: item for item in kelly.readings}
    admitted = set(incubation_admissions)
    attempts = 0
    exhausted_ns: int | None = None
    results: list[GovernedPaperIncubationDecision] = []
    for sequence, instant, increasing in items:
        final = _first_final(view, instant, graduated_ns, exhausted_ns)
        record = view.record if view.known_at(instant) else None  # publication-visible only: the past never changes
        if final is not None:
            state, reason = final[2], final[3]
        elif admission_reason:
            state, reason = (
                GovernedPaperIncubationState.NOT_ESTABLISHED,
                f"incubation_policy_not_admitted:{admission_reason}",
            )
        elif record is None or view.approval_row is None:
            state, reason = GovernedPaperIncubationState.NOT_ESTABLISHED, "incubation_record_absent"
        elif instant < max(record.start_ns, view.approval_row.published_at_ns):
            state, reason = GovernedPaperIncubationState.NOT_ESTABLISHED, "incubation_not_started"
        elif view.block is not None and view.block[0] <= instant:  # a known end signal, before any final transition
            state, reason = GovernedPaperIncubationState.NOT_ESTABLISHED, view.block[1]
        elif attempts >= policy.attempt_bound:  # a later decision at the instant of the final admitted attempt
            state, reason = GovernedPaperIncubationState.EXPIRED_HOLD, "incubation_attempts_exhausted"
        else:
            missing = _missing_bases(view, instant)
            if missing:
                state, reason = (
                    GovernedPaperIncubationState.NOT_ESTABLISHED,
                    "incubation_authority_basis_unproven:" + ",".join(missing),
                )
            else:
                state, reason = GovernedPaperIncubationState.ACTIVE, ""
        kelly_reading = readings_by_sequence.get(sequence)
        unknown_closed = kelly_reading is not None and bool(kelly_reading.unknown_trade_ids)
        readings = _readings(
            record,
            state is GovernedPaperIncubationState.ACTIVE,
            reason,
            _orders_before(outcome, instant),
            completion,
            instant,
            unknown_closed,
        )
        results.append(
            GovernedPaperIncubationDecision(
                decision_sequence=sequence,
                decision_time_ns=instant,
                exposure_increasing=increasing,
                state=state,
                state_reason=reason,
                attempts_before=attempts,
                readings=readings,
                kelly_cold_start_status="" if kelly_reading is None else kelly_reading.cold_start_status,
                kelly_cold_start_reason="" if kelly_reading is None else kelly_reading.cold_start_reason,
            )
        )
        if sequence in admitted:  # the schedule under evaluation's own admission (a fixed point makes it ACTIVE)
            attempts += 1
            if attempts >= policy.attempt_bound and exhausted_ns is None:
                exhausted_ns = instant + 1  # the record ends after its final admitted attempt (r2 A8, I14)
    final = _first_final(view, horizon, graduated_ns, exhausted_ns)
    record = view.record
    windows: tuple[HistoricalExecutionIncubationWindow, ...] = ()
    if record is not None and view.approval_row is not None and view.end_ns is not None and not admission_reason:
        start = max(record.start_ns, view.approval_row.published_at_ns)
        end = view.end_ns if final is None else min(view.end_ns, final[0])
        if view.block is not None:  # no fill authority survives a known end signal, whatever its effective instant
            end = min(end, view.block[0])
        # the fill basis survives only where every r2 basis covers the instant (re-checked at fill, A3-A6)
        for kind in GovernedPaperIncubationBasisKind:
            spans = [(b.valid_from_ns, b.valid_until_ns) for b in view.bases if b.basis_kind is kind]
            covering = [span for span in spans if span[0] <= start < span[1]]
            if not covering:
                end = start
                break
            end = min(end, max(span[1] for span in covering))
        if end > start:
            windows = (HistoricalExecutionIncubationWindow(start, end),)
    seed = GovernedPaperIncubationEvidence(
        schema_version=GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_INCUBATION_CONTRACT_ID,
        registry_id=registry.registry_id,
        lineage_genesis_digest=genesis.genesis_digest,
        edge_id=genesis.strategy_id,
        projection_digest=governed_paper_incubation_projection_digest(
            registry, lineage_genesis_digest=genesis.genesis_digest, edge_id=genesis.strategy_id, before_ns=horizon
        ),
        policy_digest=policy.policy_digest,
        policy_approval_digest="" if context.policy_approval is None else context.policy_approval.approval_digest,
        policy_admitted=not admission_reason,
        record_digest="" if view.approval_row is None else view.approval_row.record_digest,
        record_published_ns=None if view.approval_row is None else view.approval_row.published_at_ns,
        start_ns=None if record is None else record.start_ns,
        end_ns=view.end_ns,
        horizon_ns=horizon,
        covered=() if record is None else record.covered,
        incubation_entry_decision_sequences=tuple(sorted(admitted)),
        kelly_cold_start_cover=record is not None and "U5" in record.covered,
        fill_windows=windows,
        final_state=None if final is None else final[2],
        final_at_ns=None if final is None else final[0],
        final_reason="" if final is None else final[3],
        decisions=tuple(results),
        evidence_digest="",
    )
    return replace(seed, evidence_digest=governed_paper_incubation_evidence_digest(seed))


def governed_paper_incubation_evidence_digest(evidence: GovernedPaperIncubationEvidence) -> str:
    return edge_payload_digest(_to_payload(evidence), "evidence_digest")


def governed_paper_incubation_evidence_to_dict(evidence: GovernedPaperIncubationEvidence) -> dict[str, object]:
    return _to_payload(evidence)


def governed_paper_incubation_prefix_digest(evidence: GovernedPaperIncubationEvidence, *, before_ns: int) -> str:
    """The run-independent X1 content before ``before_ns``: the policy, the registry identity, the key's record once its
    approval was published before it, and every decision before it, with the final transition only once it lies before
    it. A later seal re-derives it unchanged: a row published later never enters an earlier prefix."""

    if type(evidence) is not GovernedPaperIncubationEvidence:
        raise _fail("evidence_malformed")
    _instant(before_ns, "prefix_instant")
    final = evidence.final_at_ns is not None and evidence.final_at_ns < before_ns
    known = evidence.record_published_ns is not None and evidence.record_published_ns < before_ns
    payload = {
        "schema_version": evidence.schema_version,
        "registry_id": evidence.registry_id,
        "policy_digest": evidence.policy_digest,
        "policy_approval_digest": evidence.policy_approval_digest,
        "record_digest": evidence.record_digest if known else "",
        "decisions": [_to_payload(item) for item in evidence.decisions if item.decision_time_ns < before_ns],
        "final": [evidence.final_state.value, evidence.final_at_ns, evidence.final_reason] if final else None,  # type: ignore[union-attr]
    }
    return _digest(payload)


def governed_paper_incubation_decision_of(
    evidence: GovernedPaperIncubationEvidence, decision_sequence: int
) -> GovernedPaperIncubationDecision | None:
    return next((item for item in evidence.decisions if item.decision_sequence == decision_sequence), None)


def governed_paper_incubation_reading_status(
    decision: GovernedPaperIncubationDecision, reading_id: str
) -> GovernedPaperIncubationReading:
    return next(item for item in decision.readings if item.reading_id == reading_id)


__all__ = [
    "GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND",
    "GOVERNED_PAPER_INCUBATION_CONTRACT_ID",
    "GOVERNED_PAPER_INCUBATION_DURATION_DAYS",
    "GOVERNED_PAPER_INCUBATION_ENVELOPE_FRACTION",
    "GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE",
    "GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY",
    "GOVERNED_PAPER_INCUBATION_READINGS",
    "GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA",
    "GovernedPaperIncubationApprovalKind",
    "GovernedPaperIncubationBasis",
    "GovernedPaperIncubationBasisKind",
    "GovernedPaperIncubationContext",
    "GovernedPaperIncubationDecision",
    "GovernedPaperIncubationEndCause",
    "GovernedPaperIncubationError",
    "GovernedPaperIncubationEvidence",
    "GovernedPaperIncubationPolicy",
    "GovernedPaperIncubationPolicyApproval",
    "GovernedPaperIncubationPolicyTable",
    "GovernedPaperIncubationReading",
    "GovernedPaperIncubationReadingStatus",
    "GovernedPaperIncubationRecord",
    "GovernedPaperIncubationRegistry",
    "GovernedPaperIncubationRow",
    "GovernedPaperIncubationRowKind",
    "GovernedPaperIncubationState",
    "build_governed_paper_incubation_approval_row",
    "build_governed_paper_incubation_basis",
    "build_governed_paper_incubation_end_row",
    "build_governed_paper_incubation_policy",
    "build_governed_paper_incubation_policy_approval",
    "build_governed_paper_incubation_record",
    "derive_governed_paper_incubation_evidence",
    "governed_paper_incubation_active_policy_table",
    "governed_paper_incubation_active_registry",
    "governed_paper_incubation_canonical_context",
    "governed_paper_incubation_decision_of",
    "governed_paper_incubation_evidence_digest",
    "governed_paper_incubation_evidence_to_dict",
    "governed_paper_incubation_policy_admission",
    "governed_paper_incubation_policy_approval_digest",
    "governed_paper_incubation_policy_digest",
    "governed_paper_incubation_prefix_digest",
    "governed_paper_incubation_projection_digest",
    "governed_paper_incubation_reading_status",
    "governed_paper_incubation_record_digest",
    "governed_paper_incubation_record_for_lineage",
    "governed_paper_incubation_row_digest",
]
