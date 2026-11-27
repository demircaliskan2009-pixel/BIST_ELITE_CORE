"""Governed paper incubation authority (S1_TEMPORAL_AUTHORITY_UNIFIED_CONSTRUCTION_V1): one point-in-time interval model.

Design authority: ``docs/crypto_core/s1_paper_incubation_doctrine_adoption_v1.md`` (decision packet r1: the
``PAPER_INCUBATION_RECORD_V1`` schema, lifecycle and evaluation, ``A_max = 21``, ``T_max = 91`` UTC days, ``W_INC = 0.08``)
and ``docs/crypto_core/s1_incubation_authority_registry_doctrine_adoption_v1.md`` (HD-INC-AUTH-1 r2: A1-A9 and the
readings O1-O4), read with PRDV4 §0.3 and §1.21 and the approved companion ``s1_approved_doctrine_adoption_v1.md``
§§3.1-3.5. Paper-only, deterministic, point-in-time and fail-closed. It creates no order, approves nothing and grants no
production authority: the production table admits no row, basis, policy or C2 horizon.

Root-cause escape. This module replaces three defects by architecture, not by patch; their identities stay:

* ``INCUBATION_FUTURE_APPROVAL_REWRITES_PAST`` (B1): every fact is KNOWLEDGE only from its own publication instant. The
  authority at ``t`` reads only rows and bases published at or before ``t``, attempts admitted before ``t`` and trades
  known at or before ``t``, so a publication at ``P`` never changes a state, reading or prefix before ``P``. Every final
  event depends on the record, so none is ever dated before the first approval's publication ``P_A`` (record-causal
  finality): an end row known before ``P_A`` blocks from its own publication (negative evidence kept) but is final no
  earlier than ``P_A``, and a class completion known before ``P_A`` graduates no earlier than ``max(P_A, S)``;
* ``INCUBATION_KNOWN_SIGNAL_BLOCK_DELAYED_UNTIL_EFFECTIVE_TIME`` (B2): a known end signal removes positive authority
  from its publication ``P``. Finality (``REVOKED``, ``TERMINATED``) is a separate fact, dated ``max(P, E, P_A)``: never
  before its publication, its effective instant ``E`` or the record's knowledge;
* ``INCUBATION_ACTIVE_WITH_EMPTY_FILL_WINDOW`` (B3): there is no record-start fill window. Decision eligibility and fill
  permission are both membership in the SAME derived segments, so a basis that starts after ``S`` delays both alike.

The model. Every interval is half-open ``[start, end)`` in UTC nanoseconds. For the lineage-edge key (the genesis digest
and its admitted variant) the authority derives:

1. Establishment, from the first ``RECORD_APPROVAL`` row of the key: the record it embeds must recompute to the row's
   digest and bind this genesis (id, digest, ``G``, bootstrap horizon, scope), its executed edge (variant, strategy
   spec, parameters, paper admission, walk-forward evidence) and its static validation identities (the EF-5 sealed
   preregistration, the EF-7 v2 PASS decision and the trial-count chain head), which the lineage re-derives from the
   verified genesis authority's EF-7 decision through the accepted public serializers and verifiers, never from the
   record; a lineage without that static proof refuses the record, a record naming other identities is TERMINATED;
   the policy must hold exactly r1's values; the row, the
   policy and the C2 horizon must be admitted by the active table (A1, A3, r1 "C2 must independently establish both G and
   H"); ``S + T_max <= G + H``. ``X = min(S + T_max, G + H)``. An approval published or effective after ``S`` is a
   retroactive approval: ``TERMINATED`` at its publication. A second approval row of the key terminates the record at
   that row's publication (r1: "a second approved record for the same key terminates both"); an end row naming the key
   blocks.
2. The base segments: ``[S, X)`` intersected, for each of the four bases A3 (approval provenance), A4 (temporal
   provenance), A5 (complete revocation view) and A6 (per-decision currentness), with the union of that kind's admitted
   bases' validity segments, each clipped to start at its own publication; then truncated at the first known end signal,
   termination or graduation. A basis may start late, stop, resume and be renewed: authority exists only where all four
   hold at once, never in a gap, and no later segment reaches back.
3. Attempts: an entry admitted on the incubation basis is one attempt at its decision instant (r1). The ``A_max``-th
   attempt ends the record at its decision instant (``EXPIRED_HOLD`` unless coverage ended first): a decision reads the
   attempts admitted before it, so the decision that consumes attempt 21 is ACTIVE, and no fill at or after that instant
   is permitted (O4), its own included. The ledger names each admitted decision once, by strictly increasing decision
   sequence at its own reading's instant: a replayed, duplicated, reordered or unmatched identity is refused before any
   attempt is counted, never deduplicated into a valid ledger.
4. Graduation: per selected reading, irreversible. U5 coverage ends at the knowledge instant of the first known closed
   win and the first known closed loss (r1 F-3 under RECORD A); the record graduates at the later of that instant, its
   start ``S`` and its knowledge ``P_A``, never before it was established. Without the own-history authority (rule set
   v12) no producer of the U1-U4 readings exists, so their own history is never proven complete: a record selecting any
   of them never graduates (it reaches ``EXPIRED_HOLD``), and no check owes ``COLD_START_EXCEPTED`` to them.
   With it (``S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1``, rule set v13, evidence v2) the authority also takes the cut
   instant at which each of U1-U4 first held enough own observations (``governed_paper_own_history``: 30 and 90 completed
   known days, 10 and 20 conclusively resolved submissions); the record graduates at the later of the coverage end of
   every selected reading, ``S`` and ``P_A``, and a selected reading whose coverage never ends keeps it from graduating.
   Which check a covered reading excepts is decided by the entry gate, never here.

``ACTIVE`` at a decision instant ``t`` holds exactly when ``t`` is in a base segment and fewer than ``A_max`` attempts
were admitted before the decision. A fill at ``t_f`` of an incubation-basis intent is permitted exactly when ``t_f`` is in
a FILL segment: the base segments cut at the exhaustion instant. Outside ACTIVE the state is ``NOT_ESTABLISHED`` (no
record known, refused or before ``S``), ``HOLD`` (O1 ``UNKNOWN_CURRENTNESS``: a missing basis, or a known end signal whose
finality is not yet reached; never final for that reason alone) or a final state, which is never left.

A missing row never proves anything (A5): an end row of the key, admitted or not, blocks from its publication; only an
admitted end row naming the approved record and carrying a terminal cause makes the record final.
``VALIDATION_NOT_CURRENT`` is authoritative proven loss of validation currentness (``TERMINATED``, O1
``PROVEN_LOSS_OF_CURRENTNESS``); ``REVOKED`` is a verified human revocation (``REVOKED``). ``ADVERSE_SIGNAL`` is immediate
negative eligibility authority (A5) and no proof of a terminal cause: it blocks from its publication and the record
stays ``HOLD`` (O1 ``UNKNOWN_CURRENTNESS``) unless an independent final event ends it.

The evidence binds the context digests, the derived authority, every entry decision's reading and the attempt ledger.
``governed_paper_incubation_prefix_digest`` is its knowledge-stable content before an instant, so a later seal proves it
never rewrote an authority fact, reading or attempt known before.

Non-claims. An ACTIVE state proves only the construction over its inputs: no authenticated approver, signature (O2),
qualified temporal provenance (O3), complete revocation view, currentness, edge, readiness or Stage-4 eligibility.
Exact integers only; no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    edge_leakage_bias_evidence_from_payload,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EdgePaperAdmissionDecision,
    edge_paper_admission_decision_digest,
)
from crypto_core.validation.edge_pre_paper_validation_evidence import (
    edge_pre_paper_validation_evidence_digest,
    edge_pre_paper_validation_evidence_from_payload,
)
from crypto_core.validation.edge_trial_count_chain import (
    edge_trial_count_chain_from_payload,
    verify_edge_trial_count_chain,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    edge_walk_forward_oos_evidence_digest,
    edge_walk_forward_oos_evidence_from_payload,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperGenesis,
    GovernedPaperGenesisAuthority,
)
from crypto_core.validation.governed_paper_kelly_reading import (
    GovernedPaperKellyReading,
    GovernedPaperKellyStatus,
    governed_paper_kelly_reading_digest,
)

GOVERNED_PAPER_INCUBATION_CONTRACT_ID = "S1_TEMPORAL_AUTHORITY_UNIFIED_CONSTRUCTION_V1"
GOVERNED_PAPER_INCUBATION_DECISION_IDS: tuple[str, ...] = (
    "S1_PAPER_INCUBATION_DECISION_PACKET_V1:r1",
    "HD-INC-AUTH-1:r2",
)
GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA = "PAPER_INCUBATION_RECORD_V1"
GOVERNED_PAPER_INCUBATION_POLICY_SCHEMA = "governed-paper-incubation-policy.v1"
GOVERNED_PAPER_INCUBATION_ROW_SCHEMA = "governed-paper-incubation-registry-row.v1"
GOVERNED_PAPER_INCUBATION_BASIS_SCHEMA = "governed-paper-incubation-basis.v1"
GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA = "governed-paper-incubation-evidence.v1"
# Rule set v13 (S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1): the same artifacts, graduating on the U1-U4 coverage ends too.
GOVERNED_PAPER_INCUBATION_OWN_HISTORY_EVIDENCE_SCHEMA = "governed-paper-incubation-evidence.v2"
_OWN_HISTORY_READINGS = ("U1", "U2", "U3", "U4")
GOVERNED_PAPER_INCUBATION_ADMISSION_SCOPE = "LIMITED_S1_PAPER_V1"
# Decision packet r1, items 1.4-1.6: approved values, each still needing its digest-bound policy artifact and approval.
GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND = 21
GOVERNED_PAPER_INCUBATION_DURATION_BOUND_DAYS = 91
GOVERNED_PAPER_INCUBATION_EXPOSURE_FRACTION = Fraction(8, 100)
GOVERNED_PAPER_INCUBATION_READINGS: tuple[str, ...] = ("U1", "U2", "U3", "U4", "U5")
GOVERNED_PAPER_INCUBATION_HUMAN_CHANNEL = "HUMAN_GOVERNANCE"
GOVERNED_PAPER_INCUBATION_TEST_CHANNEL = "TEST_ONLY_SYNTHETIC"
_DAY_NS = 86_400 * 10**9
_PREFIX = "governed_paper_incubation_authority"
_RATIO_UNDEFINED = "KELLY_RATIO_UNDEFINED"


class GovernedPaperIncubationError(EdgeArtifactError):
    """Malformed or foreign input: no incubation authority is ever represented over it."""


class GovernedPaperIncubationRowKind(str, Enum):
    RECORD_APPROVAL = "RECORD_APPROVAL"
    RECORD_END = "RECORD_END"


class GovernedPaperIncubationEndKind(str, Enum):
    ADVERSE_SIGNAL = "ADVERSE_SIGNAL"
    REVOKED = "REVOKED"
    VALIDATION_NOT_CURRENT = "VALIDATION_NOT_CURRENT"


class GovernedPaperIncubationBasisKind(str, Enum):
    A3_APPROVAL_PROVENANCE = "A3_APPROVAL_PROVENANCE"
    A4_TEMPORAL_PROVENANCE = "A4_TEMPORAL_PROVENANCE"
    A5_REVOCATION_VIEW = "A5_REVOCATION_VIEW"
    A6_DECISION_CURRENTNESS = "A6_DECISION_CURRENTNESS"


class GovernedPaperIncubationState(str, Enum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    ACTIVE = "ACTIVE"
    HOLD = "HOLD"
    GRADUATED = "GRADUATED"
    EXPIRED_HOLD = "EXPIRED_HOLD"
    REVOKED = "REVOKED"
    TERMINATED = "TERMINATED"


class GovernedPaperIncubationCoverage(str, Enum):
    """How one decision's U5 (Kelly) reading stands under the record (KD-13)."""

    COLD_START_EXCEPTED = "COLD_START_EXCEPTED"
    ORDINARY = (
        "ORDINARY"  # the reading keeps its ordinary status: defined, proven FAIL, or undefined for another reason
    )
    COVERAGE_ENDED = "COVERAGE_ENDED"  # the first known win and loss are known: ordinary for good
    NOT_COVERED = "NOT_COVERED"  # no ACTIVE record, or U5 not selected


_FINAL_STATES = (
    GovernedPaperIncubationState.GRADUATED,
    GovernedPaperIncubationState.EXPIRED_HOLD,
    GovernedPaperIncubationState.REVOKED,
    GovernedPaperIncubationState.TERMINATED,
)
# Equal-instant precedence of final events: failed verification first, then revocation, expiry and graduation.
_FINAL_ORDER = {
    GovernedPaperIncubationState.TERMINATED: 0,
    GovernedPaperIncubationState.REVOKED: 1,
    GovernedPaperIncubationState.EXPIRED_HOLD: 2,
    GovernedPaperIncubationState.GRADUATED: 3,
}
# The end kinds that carry a terminal cause (r1 lifecycle, r2 O1). ADVERSE_SIGNAL is absent on purpose: it is immediate
# negative eligibility authority (A5), never by itself proof of failed verification or of a revocation.
_END_FINAL = {
    GovernedPaperIncubationEndKind.REVOKED: GovernedPaperIncubationState.REVOKED,
    GovernedPaperIncubationEndKind.VALIDATION_NOT_CURRENT: GovernedPaperIncubationState.TERMINATED,
}
_EF7_V2_SCHEMA = "edge-paper-admission-decision.v2"  # r1: "the EF-7 v2 PASS decision digest"
_BASIS_KINDS = tuple(GovernedPaperIncubationBasisKind)


# --- inputs --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperIncubationInterval:
    """One half-open interval ``[start_ns, end_ns)``, nonempty."""

    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class GovernedPaperIncubationRecord:
    """``PAPER_INCUBATION_RECORD_V1`` (r1 "The record and its approval"): the supplied fields; its digest is the SHA-256 of
    their canonical bytes. The derived end ``X`` and the separate approval are not fields, so the digest never covers them.
    """

    schema: str
    genesis_id: str
    genesis_digest: str
    genesis_start_ns: int
    bootstrap_horizon_days: int
    admission_scope: str
    edge_id: str
    strategy_spec_digest: str
    parameter_assignment_digest: str
    paper_admission_digest: str
    walk_forward_evidence_digest: str
    ef5_preregistration_digest: str
    ef7_decision_digest: str
    trial_chain_head_digest: str
    covered: tuple[str, ...]
    attempt_bound: int
    duration_bound_days: int
    start_ns: int
    policy_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationPolicy:
    """The one digest-bound policy artifact holding ``A_max``, ``T_max`` and ``W_INC`` (r1); ``policy_digest`` covers the
    rest. ``channel`` is the approval channel the active table must admit."""

    schema: str
    policy_id: str
    attempt_bound: int
    duration_bound_days: int
    exposure_fraction: str
    channel: str
    policy_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationRow:
    """One append-only registry row (A1, A2); ``row_digest`` covers every other field.

    A ``RECORD_APPROVAL`` embeds the record it approves, with the approver, the channel and the decision-record digest,
    and ``effective_at_ns`` is the approval instant. A ``RECORD_END`` names its ``end_kind``. ``published_at_ns`` is the
    knowledge instant: the row is read only from it, and a seal accepts a new row only inside the day that adds it.
    """

    schema: str
    sequence: int
    kind: GovernedPaperIncubationRowKind
    genesis_digest: str
    edge_id: str
    record_digest: str
    record: GovernedPaperIncubationRecord | None
    approver_id: str
    channel: str
    decision_record_digest: str
    end_kind: GovernedPaperIncubationEndKind | None
    published_at_ns: int
    effective_at_ns: int
    row_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationBasis:
    """One A3-A6 authority basis of a record (r2 A3-A6); ``basis_digest`` covers every other field.

    ``segments`` are its ordered, disjoint, non-adjacent validity intervals. It is knowledge only from
    ``published_at_ns``: a segment never confers authority before the basis is published, and only a basis the active
    table admits confers any.
    """

    schema: str
    kind: GovernedPaperIncubationBasisKind
    record_digest: str
    source_id: str
    channel: str
    published_at_ns: int
    segments: tuple[GovernedPaperIncubationInterval, ...]
    basis_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationContext:
    """The incubation context of one evaluation, known at its horizon: the policy, the registry rows (append-only, in
    sequence and publication order) and the bases (in publication order). Never authority on its own."""

    policy: GovernedPaperIncubationPolicy
    rows: tuple[GovernedPaperIncubationRow, ...]
    bases: tuple[GovernedPaperIncubationBasis, ...]


@dataclass(frozen=True)
class GovernedPaperIncubationTable:
    """Which rows, bases, policies and C2 horizons may confer positive authority.

    ``production`` admits only listed ``HUMAN_GOVERNANCE`` digests and listed genesis digests for C2; ``test_only``
    admits only ``TEST_ONLY_SYNTHETIC`` artifacts and lists nothing. A table never admits across channels.
    """

    table_id: str
    admitted_channel: str
    admitted_row_digests: tuple[str, ...]
    admitted_basis_digests: tuple[str, ...]
    admitted_policy_digests: tuple[str, ...]
    admitted_horizon_genesis_digests: tuple[str, ...]


# No separate human authorization lists any incubation row, basis, policy or C2 horizon for production use.
GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE = GovernedPaperIncubationTable(
    table_id="production",
    admitted_channel=GOVERNED_PAPER_INCUBATION_HUMAN_CHANNEL,
    admitted_row_digests=(),
    admitted_basis_digests=(),
    admitted_policy_digests=(),
    admitted_horizon_genesis_digests=(),
)
_TABLE = GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperIncubationLineage:
    """The lineage-edge facts of one authenticated genesis the record must bind (derived, never supplied).

    The three static validation identities are re-derived from the verified genesis authority's EF-7 decision (see
    ``governed_paper_incubation_lineage``); each is "" when that static proof is missing, and then no record is ever
    established on the lineage.
    """

    genesis_id: str
    genesis_digest: str
    genesis_start_ns: int
    bootstrap_horizon_days: int
    bootstrap_end_ns: int
    edge_id: str
    strategy_spec_digest: str
    parameter_assignment_digest: str
    paper_admission_digest: str
    walk_forward_evidence_digest: str
    ef5_preregistration_digest: str
    ef7_decision_digest: str
    trial_chain_head_digest: str


# --- derived artifacts -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperIncubationAuthority:
    """The one derived authority of a lineage-edge key over ``[G, horizon)``; ``authority_digest`` covers the rest.

    ``record_digest`` is the first approval row's record ("" when none is known by the horizon). ``refusal_reason`` names
    why the record is refused ("" when established). ``block_from_ns`` is the first known end signal's publication.
    ``final_state`` and ``final_ns`` are the earliest final event (None when none), ``final_effective_ns`` its effective
    instant. ``base_segments`` are where positive authority holds before attempt exhaustion, ``fill_segments`` those cut
    at ``exhaustion_ns`` (the decision instant of the ``A_max``-th attempt). ``attempt_instants`` are the incubation-basis
    admissions in decision order (empty before the evaluation pass completes).
    """

    schema: str
    genesis_digest: str
    edge_id: str
    horizon_ns: int
    table_id: str
    policy_digest: str
    row_digests: tuple[str, ...]
    basis_digests: tuple[str, ...]
    record_digest: str
    approval_published_ns: int | None
    start_ns: int | None
    end_ns: int | None
    covered: tuple[str, ...]
    attempt_bound: int
    refusal_reason: str
    block_from_ns: int | None
    block_reason: str
    final_state: GovernedPaperIncubationState | None
    final_ns: int | None
    final_effective_ns: int | None
    final_reason: str
    u5_completion_ns: int | None
    graduation_ns: int | None
    attempt_instants: tuple[int, ...]
    exhaustion_ns: int | None
    base_segments: tuple[GovernedPaperIncubationInterval, ...]
    fill_segments: tuple[GovernedPaperIncubationInterval, ...]
    authority_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationReading:
    """The incubation reading of one entry decision at its own instant; ``reading_digest`` covers every other field.

    ``state`` reads only knowledge at ``decision_time_ns`` and the ``attempts_before`` admitted before the decision.
    ``u5`` is the KD-13 standing of the decision's Kelly reading (named by ``kelly_reading_digest``).
    """

    decision_sequence: int
    decision_time_ns: int
    target_direction: str
    record_digest: str
    state: GovernedPaperIncubationState
    state_reason: str
    attempts_before: int
    covered: tuple[str, ...]
    u5: GovernedPaperIncubationCoverage
    u5_reason: str
    kelly_reading_digest: str
    reading_digest: str


@dataclass(frozen=True)
class GovernedPaperIncubationAttempt:
    """One admitted incubation-basis entry: its 1-based index, decision sequence and decision instant."""

    index: int
    decision_sequence: int
    decision_time_ns: int


@dataclass(frozen=True)
class GovernedPaperIncubationEvidence:
    """The incubation evidence of one governed evaluation: the final authority, every entry decision's reading and the
    attempt ledger; ``evidence_digest`` covers the rest."""

    schema_version: str
    contract_id: str
    decision_ids: tuple[str, ...]
    authority: GovernedPaperIncubationAuthority
    readings: tuple[GovernedPaperIncubationReading, ...]
    attempts: tuple[GovernedPaperIncubationAttempt, ...]
    evidence_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    production_record_approved: bool = False
    stage4_credit: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False


# --- helpers ---------------------------------------------------------------------------------------------------------


def _fail(code: str) -> GovernedPaperIncubationError:
    return GovernedPaperIncubationError(f"{_PREFIX}:{code}")


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _payload(artifact: object) -> dict[str, object]:
    return _serialize(artifact)  # type: ignore[return-value]


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _is_int(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _text(value: object) -> bool:
    return type(value) is str and value != ""


def _hex(value: object) -> bool:
    return type(value) is str and edge_is_hex64(value)


def _merge(intervals: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """The union of half-open intervals as ordered, disjoint, non-adjacent ones (empty ones dropped)."""

    merged: list[tuple[int, int]] = []
    for start, end in sorted(item for item in intervals if item[0] < item[1]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _intersect(left: Sequence[tuple[int, int]], right: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    found = [(max(a, c), min(b, d)) for a, b in left for c, d in right]
    return _merge(found)


def _before(intervals: Sequence[tuple[int, int]], bound: int | None) -> tuple[tuple[int, int], ...]:
    """The intervals cut at ``bound`` (kept whole when it is None)."""

    if bound is None:
        return tuple(intervals)
    return _merge([(start, min(end, bound)) for start, end in intervals])


def _contains(intervals: Sequence[GovernedPaperIncubationInterval], instant: int) -> bool:
    return any(item.start_ns <= instant < item.end_ns for item in intervals)


def _typed(intervals: Sequence[tuple[int, int]]) -> tuple[GovernedPaperIncubationInterval, ...]:
    return tuple(GovernedPaperIncubationInterval(start, end) for start, end in intervals)


# --- digests and canonical forms ------------------------------------------------------------------------------------------


def governed_paper_incubation_record_digest(record: GovernedPaperIncubationRecord) -> str:
    """The record digest: SHA-256 of the canonical bytes of its supplied fields (r1)."""

    if type(record) is not GovernedPaperIncubationRecord:
        raise _fail("record_malformed")
    return _digest_of(_payload(record))


def governed_paper_incubation_policy_digest(policy: GovernedPaperIncubationPolicy) -> str:
    return edge_payload_digest(_payload(policy), "policy_digest")


def governed_paper_incubation_row_digest(row: GovernedPaperIncubationRow) -> str:
    return edge_payload_digest(_payload(row), "row_digest")


def governed_paper_incubation_basis_digest(basis: GovernedPaperIncubationBasis) -> str:
    return edge_payload_digest(_payload(basis), "basis_digest")


def _canonical_record(record: object) -> GovernedPaperIncubationRecord:
    if type(record) is not GovernedPaperIncubationRecord:
        raise _fail("record_malformed")
    for name in (
        "schema",
        "genesis_id",
        "admission_scope",
        "edge_id",
    ):
        if not _text(getattr(record, name)):
            raise _fail(f"record_malformed:{name}")
    for name in (
        "genesis_digest",
        "strategy_spec_digest",
        "parameter_assignment_digest",
        "paper_admission_digest",
        "walk_forward_evidence_digest",
        "ef5_preregistration_digest",
        "ef7_decision_digest",
        "trial_chain_head_digest",
        "policy_digest",
    ):
        if not _hex(getattr(record, name)):
            raise _fail(f"record_malformed:{name}")
    for name in ("genesis_start_ns", "start_ns"):
        if not _is_int(getattr(record, name)):
            raise _fail(f"record_malformed:{name}")
    for name in ("bootstrap_horizon_days", "attempt_bound", "duration_bound_days"):
        if not _is_int(getattr(record, name), minimum=1):
            raise _fail(f"record_malformed:{name}")
    covered = record.covered
    if (
        type(covered) is not tuple
        or not covered
        or any(type(item) is not str or item not in GOVERNED_PAPER_INCUBATION_READINGS for item in covered)
        or covered != tuple(item for item in GOVERNED_PAPER_INCUBATION_READINGS if item in covered)
    ):
        raise _fail("record_malformed:covered")  # a nonempty subset of U1-U5, in order, each once
    return record


def _canonical_policy(policy: object) -> GovernedPaperIncubationPolicy:
    if type(policy) is not GovernedPaperIncubationPolicy:
        raise _fail("policy_malformed")
    if policy.schema != GOVERNED_PAPER_INCUBATION_POLICY_SCHEMA or not _text(policy.policy_id):
        raise _fail("policy_malformed:identity")
    if not _is_int(policy.attempt_bound, 1) or not _is_int(policy.duration_bound_days, 1):
        raise _fail("policy_malformed:bounds")
    if type(policy.exposure_fraction) is not str or not _text(policy.channel):
        raise _fail("policy_malformed:fields")
    try:
        exposure = Fraction(policy.exposure_fraction)
    except (ValueError, ZeroDivisionError) as exc:
        raise _fail("policy_malformed:exposure_fraction") from exc
    if (
        policy.attempt_bound != GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND
        or policy.duration_bound_days != GOVERNED_PAPER_INCUBATION_DURATION_BOUND_DAYS
        or exposure != GOVERNED_PAPER_INCUBATION_EXPOSURE_FRACTION
        or policy.exposure_fraction != "0.08"
    ):
        raise _fail("policy_values_not_the_approved_r1_values")  # a changed value needs a new version and approval
    if not _hex(policy.policy_digest) or governed_paper_incubation_policy_digest(policy) != policy.policy_digest:
        raise _fail("policy_digest_mismatch")
    return policy


def _canonical_interval(value: object, name: str) -> GovernedPaperIncubationInterval:
    if (
        type(value) is not GovernedPaperIncubationInterval
        or not _is_int(value.start_ns)
        or not _is_int(value.end_ns)
        or value.end_ns <= value.start_ns
    ):
        raise _fail(f"{name}_malformed:segment")
    return value


def _canonical_row(row: object, index: int) -> GovernedPaperIncubationRow:
    if type(row) is not GovernedPaperIncubationRow or row.schema != GOVERNED_PAPER_INCUBATION_ROW_SCHEMA:
        raise _fail("row_malformed")
    if row.sequence != index or type(row.sequence) is not int:
        raise _fail("row_malformed:sequence_not_append_only")
    if type(row.kind) is not GovernedPaperIncubationRowKind:
        raise _fail("row_malformed:kind")
    for name in ("genesis_digest", "record_digest", "decision_record_digest"):
        if not _hex(getattr(row, name)):
            raise _fail(f"row_malformed:{name}")
    if not _text(row.edge_id) or not _text(row.channel):
        raise _fail("row_malformed:identity")
    if not _is_int(row.published_at_ns) or not _is_int(row.effective_at_ns):
        raise _fail("row_malformed:instants")
    if row.kind is GovernedPaperIncubationRowKind.RECORD_APPROVAL:
        if row.end_kind is not None or not _text(row.approver_id):
            raise _fail("row_malformed:approval_fields")
        _canonical_record(row.record)
    elif row.record is not None or type(row.end_kind) is not GovernedPaperIncubationEndKind or row.approver_id != "":
        raise _fail("row_malformed:end_fields")
    if not _hex(row.row_digest) or governed_paper_incubation_row_digest(row) != row.row_digest:
        raise _fail("row_digest_mismatch")
    return row


def _canonical_basis(basis: object) -> GovernedPaperIncubationBasis:
    if type(basis) is not GovernedPaperIncubationBasis or basis.schema != GOVERNED_PAPER_INCUBATION_BASIS_SCHEMA:
        raise _fail("basis_malformed")
    if type(basis.kind) is not GovernedPaperIncubationBasisKind:
        raise _fail("basis_malformed:kind")
    if not _hex(basis.record_digest) or not _text(basis.source_id) or not _text(basis.channel):
        raise _fail("basis_malformed:identity")
    if not _is_int(basis.published_at_ns):
        raise _fail("basis_malformed:published_at_ns")
    segments = basis.segments
    if type(segments) is not tuple or not segments:
        raise _fail("basis_malformed:segments")
    previous: int | None = None
    for item in segments:
        _canonical_interval(item, "basis")
        if previous is not None and item.start_ns <= previous:
            raise _fail("basis_malformed:segments_not_ordered_disjoint_non_adjacent")
        previous = item.end_ns
    if not _hex(basis.basis_digest) or governed_paper_incubation_basis_digest(basis) != basis.basis_digest:
        raise _fail("basis_digest_mismatch")
    return basis


def canonical_governed_paper_incubation_context(context: object) -> GovernedPaperIncubationContext:
    """Validate one context: exact types, self-digests, append-only rows in publication order, bases in publication
    order and each artifact once. Malformed input raises ``GovernedPaperIncubationError``."""

    if type(context) is not GovernedPaperIncubationContext:
        raise _fail("context_malformed")
    _canonical_policy(context.policy)
    if type(context.rows) is not tuple or type(context.bases) is not tuple:
        raise _fail("context_malformed:collections")
    previous = -1
    for index, row in enumerate(context.rows):
        _canonical_row(row, index)
        if row.published_at_ns < previous:
            raise _fail("context_malformed:rows_not_in_publication_order")
        previous = row.published_at_ns
    previous = -1
    seen: set[str] = set()
    for basis in context.bases:
        _canonical_basis(basis)
        if basis.published_at_ns < previous:
            raise _fail("context_malformed:bases_not_in_publication_order")
        if basis.basis_digest in seen:
            raise _fail("context_malformed:basis_repeated")
        seen.add(basis.basis_digest)
        previous = basis.published_at_ns
    return context


def _canonical_table(table: object) -> GovernedPaperIncubationTable:
    if type(table) is not GovernedPaperIncubationTable or table.table_id not in ("production", "test_only"):
        raise _fail("table_malformed")
    expected = (
        GOVERNED_PAPER_INCUBATION_HUMAN_CHANNEL
        if table.table_id == "production"
        else GOVERNED_PAPER_INCUBATION_TEST_CHANNEL
    )
    lists = (
        table.admitted_row_digests,
        table.admitted_basis_digests,
        table.admitted_policy_digests,
        table.admitted_horizon_genesis_digests,
    )
    if table.admitted_channel != expected or any(type(item) is not tuple for item in lists):
        raise _fail("table_malformed:channel")
    if table.table_id == "test_only" and any(lists):
        raise _fail("table_malformed:test_only_lists_nothing")
    return table


def _admits(table: GovernedPaperIncubationTable, channel: str, digest: str, listed: tuple[str, ...]) -> bool:
    if channel != table.admitted_channel:
        return False
    return table.table_id == "test_only" or digest in listed


def governed_paper_incubation_active_table() -> GovernedPaperIncubationTable:
    """The active admission table (production unless a test installed its test-only table)."""

    return _canonical_table(_TABLE)


_UNPROVEN_STATIC = ("", "", "")


def _static_validation(authority: GovernedPaperGenesisAuthority) -> tuple[str, str, str]:  # noqa: PLR0911 - one chain
    """The static validation identities of the lineage (r1 "Edge and validation", companion §3.1), re-derived from the
    verified genesis authority's own EF-7 decision, never from a record: the EF-5 sealed preregistration digest, the EF-7
    v2 PASS decision digest and the trial-count chain head digest.

    Each link is re-proved through the accepted public serializers and verifiers: the EF-7 decision recomputes to the
    genesis's paper admission digest and is a READY, advancing EF-7 v2 PASS; its EF-6 predecessor recomputes to its
    predecessor digest and the genesis's walk-forward digest; that EF-6's EF-5 predecessor verifies intact, READY, PASS,
    advancing and sealed, recomputing to both the EF-6 predecessor digest and the EF-7 preregistration digest; the EF-7
    pre-paper evidence recomputes to its digest and binds the same preregistration and trial-count chain; and that chain
    verifies intact to the bound chain digest. The chain head (the last link, or the chain genesis) is a different
    identity from the chain digest and is read only from the verified chain. ``("", "", "")`` when any link fails:
    missing static proof confers nothing.
    """

    genesis, ef7 = authority.genesis, authority.paper_admission
    if type(ef7) is not EdgePaperAdmissionDecision:
        return _UNPROVEN_STATIC
    try:
        ef7_digest = edge_paper_admission_decision_digest(ef7)
        if (
            ef7_digest != genesis.paper_admission_digest
            or ef7_digest != ef7.paper_admission_decision_digest
            or ef7.schema_version != _EF7_V2_SCHEMA
            or ef7.status is not EdgeEvidenceStatus.READY
            or ef7.gate_verdict is not EdgeGateVerdict.PASS
            or ef7.advances is not True
        ):
            return _UNPROVEN_STATIC
        ef6 = edge_walk_forward_oos_evidence_from_payload(edge_authority_binding_snapshot(ef7.predecessor_binding))
        ef6_digest = edge_walk_forward_oos_evidence_digest(ef6)
        if ef6_digest != ef7.predecessor_digest or ef6_digest != genesis.walk_forward_evidence_digest:
            return _UNPROVEN_STATIC
        ef5 = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(ef6.predecessor_binding))
        ef5_verification = verify_edge_leakage_bias_evidence(ef5)
        if (
            not ef5_verification.intact
            or ef5_verification.recomputed_digest != ef6.predecessor_digest
            or ef5_verification.recomputed_digest != ef7.preregistration_digest
            or ef5.status is not EdgeEvidenceStatus.READY
            or ef5.gate_verdict is not EdgeGateVerdict.PASS
            or ef5.advances is not True
            or ef5.preregistration_sealed is not True
        ):
            return _UNPROVEN_STATIC
        pre_paper = edge_pre_paper_validation_evidence_from_payload(
            edge_authority_binding_snapshot(ef7.pre_paper_evidence_binding)
        )
        if (
            edge_pre_paper_validation_evidence_digest(pre_paper) != ef7.pre_paper_evidence_digest
            or pre_paper.preregistration_digest != ef7.preregistration_digest
            or pre_paper.trial_chain_digest != ef7.trial_chain_digest
        ):
            return _UNPROVEN_STATIC
        chain = edge_trial_count_chain_from_payload(edge_authority_binding_snapshot(pre_paper.trial_chain_binding))
        chain_verification = verify_edge_trial_count_chain(chain)
        if not chain_verification.intact or chain_verification.recomputed_digest != pre_paper.trial_chain_digest:
            return _UNPROVEN_STATIC
    except (EdgeArtifactError, ValueError, TypeError, KeyError):
        return _UNPROVEN_STATIC
    if not all(_hex(item) for item in (ef5_verification.recomputed_digest, ef7_digest, chain.head_digest)):
        return _UNPROVEN_STATIC
    return ef5_verification.recomputed_digest, ef7_digest, chain.head_digest


def _static_proven(lineage: GovernedPaperIncubationLineage) -> bool:
    return all(
        _hex(item)
        for item in (lineage.ef5_preregistration_digest, lineage.ef7_decision_digest, lineage.trial_chain_head_digest)
    )


def governed_paper_incubation_lineage(authority: GovernedPaperGenesisAuthority) -> GovernedPaperIncubationLineage:
    """The lineage-edge facts a record must bind, from the canonical reconstructions of a verified genesis (the genesis
    authority, never a caller's genesis alone): its identity, executed edge and re-derived static validation identities.
    """

    if type(authority) is not GovernedPaperGenesisAuthority or type(authority.genesis) is not GovernedPaperGenesis:
        raise _fail("genesis_authority_malformed")
    genesis = authority.genesis
    ef5_digest, ef7_digest, chain_head_digest = _static_validation(authority)
    return GovernedPaperIncubationLineage(
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        genesis_start_ns=genesis.genesis_start_ns,
        bootstrap_horizon_days=genesis.bootstrap_horizon_days,
        bootstrap_end_ns=genesis.bootstrap_end_ns,
        edge_id=genesis.admitted_variant_id,
        strategy_spec_digest=genesis.strategy_spec_digest,
        parameter_assignment_digest=genesis.parameter_assignment_digest,
        paper_admission_digest=genesis.paper_admission_digest,
        walk_forward_evidence_digest=genesis.walk_forward_evidence_digest,
        ef5_preregistration_digest=ef5_digest,
        ef7_decision_digest=ef7_digest,
        trial_chain_head_digest=chain_head_digest,
    )


# --- the one derivation ----------------------------------------------------------------------------------------------


def _record_failure(  # noqa: PLR0911 - one linear verification, every failure named
    record: GovernedPaperIncubationRecord,
    row: GovernedPaperIncubationRow,
    lineage: GovernedPaperIncubationLineage,
    policy: GovernedPaperIncubationPolicy,
) -> str:
    """Why the approval row's record fails verification ("" when it verifies): a forged binding, another lineage or
    edge, static validation identities other than the lineage's verified ones, a policy mismatch or a retroactive
    approval. Each is TERMINATED at the row's publication (r1). Without the lineage's static proof the identities are not
    compared here: the derivation refuses the record instead (missing proof is never a proven failure)."""

    if governed_paper_incubation_record_digest(record) != row.record_digest:
        return "incubation_record_digest_mismatch"
    if (
        record.schema != GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA
        or record.admission_scope != GOVERNED_PAPER_INCUBATION_ADMISSION_SCOPE
        or row.genesis_digest != lineage.genesis_digest
        or record.genesis_id != lineage.genesis_id
        or record.genesis_digest != lineage.genesis_digest
        or record.genesis_start_ns != lineage.genesis_start_ns
        or record.bootstrap_horizon_days != lineage.bootstrap_horizon_days
    ):
        return "incubation_record_wrong_lineage"
    if (
        row.edge_id != lineage.edge_id
        or record.edge_id != lineage.edge_id
        or record.strategy_spec_digest != lineage.strategy_spec_digest
        or record.parameter_assignment_digest != lineage.parameter_assignment_digest
        or record.paper_admission_digest != lineage.paper_admission_digest
        or record.walk_forward_evidence_digest != lineage.walk_forward_evidence_digest
    ):
        return "incubation_record_not_the_executed_edge"
    if _static_proven(lineage) and (
        record.ef5_preregistration_digest != lineage.ef5_preregistration_digest
        or record.ef7_decision_digest != lineage.ef7_decision_digest
        or record.trial_chain_head_digest != lineage.trial_chain_head_digest
    ):
        return "incubation_record_validation_identity_mismatch"
    if (
        record.policy_digest != policy.policy_digest
        or record.attempt_bound != policy.attempt_bound
        or record.duration_bound_days != policy.duration_bound_days
    ):
        return "incubation_record_policy_mismatch"
    if row.published_at_ns > record.start_ns or row.effective_at_ns > record.start_ns:
        return "incubation_record_approval_retroactive"
    return ""


def _u5_completion(trades: Sequence[tuple[int, str]]) -> int | None:
    """The knowledge instant of class completion: the later of the first known win and the first known loss."""

    wins = [known for known, label in trades if label == "WIN"]
    losses = [known for known, label in trades if label == "LOSS"]
    if not wins or not losses:
        return None
    return max(min(wins), min(losses))


def derive_governed_paper_incubation_authority(  # noqa: C901, PLR0912, PLR0915 - one linear derivation
    context: GovernedPaperIncubationContext,
    *,
    lineage: GovernedPaperIncubationLineage,
    horizon_ns: int,
    known_trades: Sequence[tuple[int, str]] = (),
    attempt_instants: Sequence[int] = (),
    coverage_ends: Mapping[str, int | None] | None = None,
) -> GovernedPaperIncubationAuthority:
    """The one incubation authority of the lineage-edge key over ``[G, horizon_ns)`` (see the module docstring).

    ``known_trades`` are the lineage's closed trades as ``(knowledge instant, class)`` with class WIN, LOSS or ZERO;
    ``attempt_instants`` are the decision instants of the admitted incubation-basis entries in decision order (empty for
    the static authority a decision pass reads). ``coverage_ends`` (rule set v13 only) maps each of U1-U4 to the cut
    instant at which its coverage ended, or None, from the one own-history authority; without it the authority is the
    accepted v1 one. Only artifacts published before ``horizon_ns`` may appear. Pure.
    """

    context = canonical_governed_paper_incubation_context(context)
    table = governed_paper_incubation_active_table()
    if type(lineage) is not GovernedPaperIncubationLineage:
        raise _fail("lineage_malformed")
    if coverage_ends is not None and (
        set(coverage_ends) != set(_OWN_HISTORY_READINGS)
        or any(value is not None and not _is_int(value) for value in coverage_ends.values())
    ):
        raise _fail("coverage_ends_malformed")
    if not _is_int(horizon_ns) or horizon_ns < lineage.genesis_start_ns:
        raise _fail("horizon_invalid")
    for item in (*context.rows, *context.bases):
        if item.published_at_ns > horizon_ns:
            raise _fail("context_carries_an_artifact_published_after_the_horizon")
    instants = tuple(attempt_instants)
    if any(not _is_int(item) for item in instants) or any(b < a for a, b in zip(instants, instants[1:], strict=False)):
        raise _fail("attempt_instants_malformed")
    trades = tuple(known_trades)
    for item in trades:
        if type(item) is not tuple or len(item) != 2 or not _is_int(item[0]) or item[1] not in ("WIN", "LOSS", "ZERO"):  # noqa: PLR2004
            raise _fail("known_trades_malformed")
    policy = context.policy
    key_rows = [
        row for row in context.rows if row.genesis_digest == lineage.genesis_digest and row.edge_id == lineage.edge_id
    ]
    approvals = [row for row in key_rows if row.kind is GovernedPaperIncubationRowKind.RECORD_APPROVAL]
    ends = [row for row in key_rows if row.kind is GovernedPaperIncubationRowKind.RECORD_END]
    finals: list[
        tuple[int, int, GovernedPaperIncubationState, int, str]
    ] = []  # (final_ns, order, state, effective, why)
    record: GovernedPaperIncubationRecord | None = None
    first = approvals[0] if approvals else None
    knowledge = None if first is None else first.published_at_ns  # P_A: the record's knowledge instant

    def final(state: GovernedPaperIncubationState, at: int, effective: int, why: str) -> None:
        # B1, record-causal finality: every final event is a fact about the record, so it exists no earlier than the
        # record's knowledge. A pre-P_A instant would rewrite a prefix sealed before the record was known.
        dated = at if knowledge is None else max(at, knowledge)
        finals.append((dated, _FINAL_ORDER[state], state, effective, why))

    refusal = "incubation_no_record_known" if first is None else ""
    start = end = None
    covered: tuple[str, ...] = ()
    if first is not None:
        record = first.record
        covered = record.covered  # type: ignore[union-attr]
        failure = _record_failure(record, first, lineage, policy)  # type: ignore[arg-type]
        if failure:
            final(GovernedPaperIncubationState.TERMINATED, first.published_at_ns, first.published_at_ns, failure)
        if not _static_proven(lineage):
            refusal = "incubation_static_validation_unproven"  # missing static proof blocks; it proves no failure
        elif not _admits(table, first.channel, first.row_digest, table.admitted_row_digests):
            refusal = "incubation_record_approval_not_admitted"
        elif not _admits(table, policy.channel, policy.policy_digest, table.admitted_policy_digests):
            refusal = "incubation_policy_not_admitted"
        elif not (table.table_id == "test_only" or lineage.genesis_digest in table.admitted_horizon_genesis_digests):
            refusal = "incubation_lineage_horizon_c2_unestablished"
        else:
            start = record.start_ns  # type: ignore[union-attr]
            if start + policy.duration_bound_days * _DAY_NS > lineage.bootstrap_end_ns:
                refusal, start = "incubation_horizon_exceeds_lineage", None
        if start is not None:
            end = min(start + policy.duration_bound_days * _DAY_NS, lineage.bootstrap_end_ns)
            final(GovernedPaperIncubationState.EXPIRED_HOLD, end, end, "incubation_duration_bound_reached")
        for duplicate in approvals[1:]:
            final(
                GovernedPaperIncubationState.TERMINATED,
                duplicate.published_at_ns,
                duplicate.published_at_ns,
                "incubation_second_record_for_the_lineage_edge_key",
            )
    record_digest = "" if first is None else first.record_digest
    block_from: int | None = None
    block_reason = ""
    for row in ends:  # A5: a known end signal blocks from its publication, admitted or not
        if block_from is None or row.published_at_ns < block_from:
            block_from, block_reason = row.published_at_ns, f"incubation_known_end_signal:{row.end_kind.value.lower()}"  # type: ignore[union-attr]
        terminal = _END_FINAL.get(row.end_kind)  # type: ignore[arg-type]
        if (
            terminal is not None
            and first is not None
            and row.record_digest == record_digest
            and _admits(table, row.channel, row.row_digest, table.admitted_row_digests)
        ):
            at = max(row.published_at_ns, row.effective_at_ns)  # never before its publication or its effect
            final(
                terminal,
                at,
                row.effective_at_ns,
                f"incubation_end_row:{row.end_kind.value.lower()}",  # type: ignore[union-attr]
            )
    completion = _u5_completion(trades)
    # only an established record graduates, never before it was known (P_A) or started (S), and only before its end
    # (r1: "before the bound"); a completion known earlier is the class history the record starts from, not a past event
    established = end is not None and not refusal
    graduation = None
    if coverage_ends is None:  # rule set v12: no producer of U1-U4 exists, so only a U5-only record graduates
        if established and covered == ("U5",) and completion is not None:
            graduation = max(completion, start, knowledge)  # type: ignore[type-var]
            if graduation >= end:  # type: ignore[operator]
                graduation = None
    elif established:  # rule set v13: every selected reading's coverage must have ended, irreversibly
        reading_ends = [completion if reading == "U5" else coverage_ends[reading] for reading in covered]
        if reading_ends and all(item is not None for item in reading_ends):
            graduation = max(*reading_ends, start, knowledge)  # type: ignore[type-var]
            if graduation >= end:  # type: ignore[operator]
                graduation = None
    if graduation is not None:
        final(
            GovernedPaperIncubationState.GRADUATED,
            graduation,
            graduation,
            "incubation_coverage_ended_for_every_reading",
        )
    exhaustion = instants[policy.attempt_bound - 1] if len(instants) >= policy.attempt_bound else None
    static_finals = sorted(finals)
    if exhaustion is not None:
        final(GovernedPaperIncubationState.EXPIRED_HOLD, exhaustion, exhaustion, "incubation_attempt_bound_reached")
    earliest = min(finals) if finals else None
    base: tuple[tuple[int, int], ...] = ()
    if start is not None and end is not None and not refusal:
        base = ((max(start, first.published_at_ns), end),)  # type: ignore[union-attr]
        for kind in _BASIS_KINDS:
            union = _merge(
                [
                    (max(segment.start_ns, basis.published_at_ns), segment.end_ns)
                    for basis in context.bases
                    if basis.kind is kind
                    and basis.record_digest == record_digest
                    and _admits(table, basis.channel, basis.basis_digest, table.admitted_basis_digests)
                    for segment in basis.segments
                ]
            )
            base = _intersect(base, union)
        cut = [item for item in (block_from, *(item[0] for item in static_finals)) if item is not None]
        base = _before(base, min(cut) if cut else None)
    fill = _before(base, exhaustion)
    seed = GovernedPaperIncubationAuthority(
        schema=GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA
        if coverage_ends is None
        else GOVERNED_PAPER_INCUBATION_OWN_HISTORY_EVIDENCE_SCHEMA,
        genesis_digest=lineage.genesis_digest,
        edge_id=lineage.edge_id,
        horizon_ns=horizon_ns,
        table_id=table.table_id,
        policy_digest=policy.policy_digest,
        row_digests=tuple(row.row_digest for row in context.rows),
        basis_digests=tuple(basis.basis_digest for basis in context.bases),
        record_digest=record_digest,
        approval_published_ns=None if first is None else first.published_at_ns,
        start_ns=None if record is None else record.start_ns,
        end_ns=end,
        covered=covered,
        attempt_bound=policy.attempt_bound,
        refusal_reason=refusal,
        block_from_ns=block_from,
        block_reason=block_reason,
        final_state=None if earliest is None else earliest[2],
        final_ns=None if earliest is None else earliest[0],
        final_effective_ns=None if earliest is None else earliest[3],
        final_reason="" if earliest is None else earliest[4],
        u5_completion_ns=completion,
        graduation_ns=graduation,
        attempt_instants=instants,
        exhaustion_ns=exhaustion,
        base_segments=_typed(base),
        fill_segments=_typed(fill),
        authority_digest="",
    )
    return replace(seed, authority_digest=edge_payload_digest(_payload(seed), "authority_digest"))


def governed_paper_incubation_authority_digest(authority: GovernedPaperIncubationAuthority) -> str:
    return edge_payload_digest(_payload(authority), "authority_digest")


def _missing_bases(
    context_bases: Sequence[GovernedPaperIncubationBasis], record_digest: str, instant: int
) -> tuple[str, ...]:
    table = governed_paper_incubation_active_table()
    missing = []
    for kind in _BASIS_KINDS:
        holds = any(
            basis.kind is kind
            and basis.record_digest == record_digest
            and basis.published_at_ns <= instant
            and _admits(table, basis.channel, basis.basis_digest, table.admitted_basis_digests)
            and any(segment.start_ns <= instant < segment.end_ns for segment in basis.segments)
            for basis in context_bases
        )
        if not holds:
            missing.append(kind.value.split("_")[0].lower())
    return tuple(missing)


def governed_paper_incubation_state_at(  # noqa: PLR0911 - one linear reading, every state named
    authority: GovernedPaperIncubationAuthority,
    instant: int,
    *,
    attempts_before: Sequence[int] = (),
    context: GovernedPaperIncubationContext | None = None,
) -> tuple[GovernedPaperIncubationState, str]:
    """The state at a decision instant from knowledge at that instant and the attempts admitted before the decision.

    ``context`` (the evaluation's own) only names the missing bases of a HOLD. Pure.
    """

    if type(authority) is not GovernedPaperIncubationAuthority or not _is_int(instant):
        raise _fail("state_query_malformed")
    attempts = tuple(attempts_before)
    if authority.approval_published_ns is None or instant < authority.approval_published_ns:
        return GovernedPaperIncubationState.NOT_ESTABLISHED, "incubation_no_record_known"
    finals: list[tuple[int, int, GovernedPaperIncubationState, str]] = []
    if authority.final_ns is not None and authority.final_ns <= instant and authority.final_state is not None:
        if authority.final_state is not GovernedPaperIncubationState.EXPIRED_HOLD or authority.final_reason != (
            "incubation_attempt_bound_reached"
        ):
            finals.append(
                (authority.final_ns, _FINAL_ORDER[authority.final_state], authority.final_state, authority.final_reason)
            )
    if len(attempts) >= authority.attempt_bound:
        exhausted = attempts[authority.attempt_bound - 1]
        finals.append(
            (
                exhausted,
                _FINAL_ORDER[GovernedPaperIncubationState.EXPIRED_HOLD],
                GovernedPaperIncubationState.EXPIRED_HOLD,
                "incubation_attempt_bound_reached",
            )
        )
    if finals:
        _, _, state, why = min(finals)
        return state, why
    if authority.refusal_reason:
        return GovernedPaperIncubationState.NOT_ESTABLISHED, authority.refusal_reason
    if authority.start_ns is None or instant < authority.start_ns:
        return GovernedPaperIncubationState.NOT_ESTABLISHED, "incubation_before_record_start"
    if authority.block_from_ns is not None and authority.block_from_ns <= instant:
        return GovernedPaperIncubationState.HOLD, f"{authority.block_reason}_finality_not_reached"
    if _contains(authority.base_segments, instant):
        return GovernedPaperIncubationState.ACTIVE, "incubation_authority_segment"
    missing = () if context is None else _missing_bases(context.bases, authority.record_digest, instant)
    names = "_".join(missing) if missing else "basis_segment"
    return GovernedPaperIncubationState.HOLD, f"incubation_authority_unproven:{names}"


def governed_paper_incubation_fill_permitted(authority: GovernedPaperIncubationAuthority, instant: int) -> bool:
    """Whether a fill of an incubation-basis intent at ``instant`` has incubation permission: membership in the same
    derived segments, cut at the attempt exhaustion (O4). Every ordinary fill-time rule stays binding on its own."""

    if type(authority) is not GovernedPaperIncubationAuthority or not _is_int(instant):
        raise _fail("fill_query_malformed")
    return _contains(authority.fill_segments, instant)


# --- the decision reading ------------------------------------------------------------------------------------------


def _u5(
    authority: GovernedPaperIncubationAuthority,
    state: GovernedPaperIncubationState,
    instant: int,
    kelly: GovernedPaperKellyReading,
) -> tuple[GovernedPaperIncubationCoverage, str]:
    if state is not GovernedPaperIncubationState.ACTIVE:
        return GovernedPaperIncubationCoverage.NOT_COVERED, f"incubation_{state.value.lower()}"
    if "U5" not in authority.covered:
        return GovernedPaperIncubationCoverage.NOT_COVERED, "u5_not_selected_by_the_record"
    if authority.u5_completion_ns is not None and authority.u5_completion_ns <= instant:
        return GovernedPaperIncubationCoverage.COVERAGE_ENDED, "u5_first_known_win_and_loss_known"
    if (
        kelly.status is GovernedPaperKellyStatus.BLOCKED
        and kelly.failures == ()
        and kelly.blocks == (_RATIO_UNDEFINED,)
        and kelly.reason == _RATIO_UNDEFINED
    ):
        # undefined only for missing own history; the solvency domain and the G-window product are defined components
        # that would FAIL here, and an unproven rho, outcome or unknown trade would block
        return GovernedPaperIncubationCoverage.COLD_START_EXCEPTED, "u5_kelly_ratio_undefined_missing_own_history"
    return GovernedPaperIncubationCoverage.ORDINARY, f"u5_ordinary:{kelly.reason.lower()}"


def _record_known(authority: GovernedPaperIncubationAuthority, instant: int) -> bool:
    return authority.approval_published_ns is not None and authority.approval_published_ns <= instant


def build_governed_paper_incubation_reading(
    authority: GovernedPaperIncubationAuthority,
    *,
    kelly: GovernedPaperKellyReading,
    attempts_before: Sequence[int],
    context: GovernedPaperIncubationContext | None = None,
) -> GovernedPaperIncubationReading:
    """The reading of one entry decision (the Kelly reading's decision) at its own instant. Pure."""

    if (
        type(kelly) is not GovernedPaperKellyReading
        or governed_paper_kelly_reading_digest(kelly) != kelly.reading_digest
    ):
        raise _fail("kelly_reading_not_authentic")
    instant = kelly.decision_time_ns
    attempts = tuple(item for item in attempts_before)
    if any(item > instant for item in attempts):
        raise _fail("attempts_after_the_decision")
    state, why = governed_paper_incubation_state_at(authority, instant, attempts_before=attempts, context=context)
    u5, u5_reason = _u5(authority, state, instant, kelly)
    known = _record_known(authority, instant)  # B1: a record published later is never part of an earlier reading
    seed = GovernedPaperIncubationReading(
        decision_sequence=kelly.decision_sequence,
        decision_time_ns=instant,
        target_direction=kelly.target_direction,
        record_digest=authority.record_digest if known else "",
        state=state,
        state_reason=why,
        attempts_before=len(attempts),
        covered=authority.covered if known else (),
        u5=u5,
        u5_reason=u5_reason,
        kelly_reading_digest=kelly.reading_digest,
        reading_digest="",
    )
    return replace(seed, reading_digest=edge_payload_digest(_payload(seed), "reading_digest"))


def governed_paper_incubation_reading_digest(reading: GovernedPaperIncubationReading) -> str:
    return edge_payload_digest(_payload(reading), "reading_digest")


# --- the evidence ----------------------------------------------------------------------------------------------------


def build_governed_paper_incubation_evidence(
    context: GovernedPaperIncubationContext,
    *,
    lineage: GovernedPaperIncubationLineage,
    horizon_ns: int,
    known_trades: Sequence[tuple[int, str]],
    readings: Sequence[GovernedPaperIncubationReading],
    attempts: Sequence[tuple[int, int]],
    coverage_ends: Mapping[str, int | None] | None = None,
) -> GovernedPaperIncubationEvidence:
    """The evidence of one completed evaluation pass: the authority re-derived with the attempt ledger ``attempts``
    (``(decision sequence, decision instant)`` of every admitted incubation-basis entry, in decision order) and the
    pass's readings. Every reading must be the one the final authority gives its decision. ``coverage_ends`` (rule set
    v13 only) are the U1-U4 coverage ends of the one own-history authority; the evidence is then v2. Pure.

    Attempt identity is verified BEFORE any attempt is counted: the readings name distinct decisions in decision order
    (strictly increasing sequence, non-decreasing instant); each ledger entry names one of those decisions exactly once,
    at that reading's own instant, in the same order. A replayed, duplicated, reordered, unmatched or re-timed identity is
    refused, never deduplicated, so it can add no attempt and cut no fill authority. Distinct decisions at the same
    nanosecond stay distinct attempts.
    """

    ledger = tuple(attempts)
    for item in ledger:
        if type(item) is not tuple or len(item) != 2 or not _is_int(item[0]) or not _is_int(item[1]):  # noqa: PLR2004
            raise _fail("attempt_ledger_malformed")
    found = tuple(readings)
    for reading in found:
        if type(reading) is not GovernedPaperIncubationReading:
            raise _fail("reading_malformed")
    for left, right in zip(found, found[1:], strict=False):
        if right.decision_sequence <= left.decision_sequence or right.decision_time_ns < left.decision_time_ns:
            raise _fail("readings_not_distinct_decisions_in_decision_order")
    decisions = {item.decision_sequence: item for item in found}
    for index, (sequence, instant) in enumerate(ledger):
        if index and sequence <= ledger[index - 1][0]:
            raise _fail("attempt_ledger_identity_replayed_or_reordered")  # each admitted decision counts once (r1)
        reading = decisions.get(sequence)
        if reading is None or reading.decision_time_ns != instant:
            raise _fail("attempt_not_an_active_decision")
    authority = derive_governed_paper_incubation_authority(
        context,
        lineage=lineage,
        horizon_ns=horizon_ns,
        known_trades=known_trades,
        attempt_instants=tuple(item[1] for item in ledger),
        coverage_ends=coverage_ends,
    )
    for reading in found:
        before = tuple(instant for sequence, instant in ledger if sequence < reading.decision_sequence)
        state, _ = governed_paper_incubation_state_at(authority, reading.decision_time_ns, attempts_before=before)
        if (
            governed_paper_incubation_reading_digest(reading) != reading.reading_digest
            or state is not reading.state
            or len(before) != reading.attempts_before
            or reading.record_digest
            != (authority.record_digest if _record_known(authority, reading.decision_time_ns) else "")
        ):
            raise _fail("reading_not_the_authoritys")
    for sequence, _ in ledger:  # an attempt is an ACTIVE decision of this pass
        if decisions[sequence].state is not GovernedPaperIncubationState.ACTIVE:
            raise _fail("attempt_not_an_active_decision")
    seed = GovernedPaperIncubationEvidence(
        schema_version=authority.schema,
        contract_id=GOVERNED_PAPER_INCUBATION_CONTRACT_ID,
        decision_ids=GOVERNED_PAPER_INCUBATION_DECISION_IDS,
        authority=authority,
        readings=found,
        attempts=tuple(
            GovernedPaperIncubationAttempt(index + 1, sequence, instant)
            for index, (sequence, instant) in enumerate(ledger)
        ),
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_payload(seed), "evidence_digest"))


def governed_paper_incubation_evidence_to_dict(evidence: GovernedPaperIncubationEvidence) -> dict[str, object]:
    return _payload(evidence)


def governed_paper_incubation_evidence_digest(evidence: GovernedPaperIncubationEvidence) -> str:
    return edge_payload_digest(_payload(evidence), "evidence_digest")


def governed_paper_incubation_prefix_digest(evidence: GovernedPaperIncubationEvidence, *, before_ns: int) -> str:
    """The knowledge-stable X1 content of the evidence before ``before_ns``: the artifacts published before it, the
    authority segments and final event cut at it, and every reading and attempt before it. A fact published at or after
    ``before_ns`` cannot change it (the module docstring's B1)."""

    if type(evidence) is not GovernedPaperIncubationEvidence or not _is_int(before_ns):
        raise _fail("prefix_query_malformed")
    authority = evidence.authority

    def cut(intervals: tuple[GovernedPaperIncubationInterval, ...]) -> list[list[int]]:
        return [list(item) for item in _before([(x.start_ns, x.end_ns) for x in intervals], before_ns)]

    known = authority.approval_published_ns is not None and authority.approval_published_ns < before_ns
    payload = {
        "schema": evidence.schema_version,  # v1 for rule set v12 (its accepted bytes), v2 for rule set v13
        "genesis_digest": authority.genesis_digest,
        "edge_id": authority.edge_id,
        "record_digest": authority.record_digest if known else "",
        "base_segments": cut(authority.base_segments),
        "fill_segments": cut(authority.fill_segments),
        "block_from_ns": authority.block_from_ns
        if authority.block_from_ns is not None and authority.block_from_ns < before_ns
        else None,
        "final": [authority.final_state.value, authority.final_ns, authority.final_reason]  # type: ignore[union-attr]
        if authority.final_ns is not None and authority.final_ns < before_ns
        else None,
        "readings": [
            {key: value for key, value in _payload(item).items() if key != "reading_digest"}
            for item in evidence.readings
            if item.decision_time_ns < before_ns
        ],
        "attempts": [_payload(item) for item in evidence.attempts if item.decision_time_ns < before_ns],
    }
    return _digest_of(payload)


def governed_paper_incubation_schedule_bounds(
    evidence: GovernedPaperIncubationEvidence,
) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...], bool]:
    """The schedule v9 fields this evidence implies: the incubation-basis decision sequences (increasing), the FILL
    segments of the one authority as ``(start, end)`` pairs and whether U5 is covered inside them. U5 coverage is
    declared only together with a fill segment: a record that confers no fill permission (unknown, refused, never
    authorized) leaves the schedule exactly as without it, so no later publication changes an earlier schedule fact."""

    if type(evidence) is not GovernedPaperIncubationEvidence:
        raise _fail("evidence_malformed")
    authority = evidence.authority
    return (
        tuple(sorted(item.decision_sequence for item in evidence.attempts)),
        tuple((item.start_ns, item.end_ns) for item in authority.fill_segments),
        "U5" in authority.covered and bool(authority.fill_segments),
    )


def governed_paper_incubation_admitted_basis(decision_statuses: Sequence[str]) -> bool:
    """Whether a permitted entry decision is on the PAPER_INCUBATION basis: at least one check is COLD_START_EXCEPTED."""

    return any(item == GovernedPaperIncubationCoverage.COLD_START_EXCEPTED.value for item in decision_statuses)


__all__ = [
    "GOVERNED_PAPER_INCUBATION_ADMISSION_SCOPE",
    "GOVERNED_PAPER_INCUBATION_ATTEMPT_BOUND",
    "GOVERNED_PAPER_INCUBATION_BASIS_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_CONTRACT_ID",
    "GOVERNED_PAPER_INCUBATION_DECISION_IDS",
    "GOVERNED_PAPER_INCUBATION_DURATION_BOUND_DAYS",
    "GOVERNED_PAPER_INCUBATION_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_EXPOSURE_FRACTION",
    "GOVERNED_PAPER_INCUBATION_HUMAN_CHANNEL",
    "GOVERNED_PAPER_INCUBATION_OWN_HISTORY_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_POLICY_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE",
    "GOVERNED_PAPER_INCUBATION_READINGS",
    "GOVERNED_PAPER_INCUBATION_RECORD_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_ROW_SCHEMA",
    "GOVERNED_PAPER_INCUBATION_TEST_CHANNEL",
    "GovernedPaperIncubationAttempt",
    "GovernedPaperIncubationAuthority",
    "GovernedPaperIncubationBasis",
    "GovernedPaperIncubationBasisKind",
    "GovernedPaperIncubationContext",
    "GovernedPaperIncubationCoverage",
    "GovernedPaperIncubationEndKind",
    "GovernedPaperIncubationError",
    "GovernedPaperIncubationEvidence",
    "GovernedPaperIncubationInterval",
    "GovernedPaperIncubationLineage",
    "GovernedPaperIncubationPolicy",
    "GovernedPaperIncubationReading",
    "GovernedPaperIncubationRecord",
    "GovernedPaperIncubationRow",
    "GovernedPaperIncubationRowKind",
    "GovernedPaperIncubationState",
    "GovernedPaperIncubationTable",
    "build_governed_paper_incubation_evidence",
    "build_governed_paper_incubation_reading",
    "canonical_governed_paper_incubation_context",
    "derive_governed_paper_incubation_authority",
    "governed_paper_incubation_active_table",
    "governed_paper_incubation_admitted_basis",
    "governed_paper_incubation_authority_digest",
    "governed_paper_incubation_basis_digest",
    "governed_paper_incubation_evidence_digest",
    "governed_paper_incubation_evidence_to_dict",
    "governed_paper_incubation_fill_permitted",
    "governed_paper_incubation_lineage",
    "governed_paper_incubation_policy_digest",
    "governed_paper_incubation_prefix_digest",
    "governed_paper_incubation_reading_digest",
    "governed_paper_incubation_record_digest",
    "governed_paper_incubation_row_digest",
    "governed_paper_incubation_schedule_bounds",
    "governed_paper_incubation_state_at",
]
