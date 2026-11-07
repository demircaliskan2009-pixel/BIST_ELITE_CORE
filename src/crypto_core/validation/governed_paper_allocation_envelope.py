"""Governed paper allocation envelope (``S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1``): ALLOCATION_ENVELOPE_V1 and
ENVELOPE_FIT, the PRDV4 §1.7 bounded meta-layer allocation and its exposure envelope.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.7 (amendment D9) and the approved companion
``docs/crypto_core/s1_approved_doctrine_adoption_v1.md`` §4.1-§4.6 (ALLOCATION_ENVELOPE_V1, items 2.1-2.3; FCD-07),
adopted by PR #433. Paper-only, deterministic, point-in-time and fail-closed. Arithmetic is exact (``int`` and
``Fraction``; no float, no ``decimal`` context), and there is no IO, clock, randomness, network or environment.

Eligibility at one rebalance (§4.1), per candidate edge:

* MEMBER: activation ``A_e`` proven PASS, EHS defined and at least 0.30, Sharpe_30d defined, and (with more than five
  such edges) inside the top five by ``EHS x Sharpe_30d``, ties broken by the higher EHS, then by the ascending edge id
  compared as UTF-8 bytes;
* NON_MEMBER: ``A_e`` proven FAIL, EHS defined and below 0.30 (DISABLE), or proven outside the top five;
* UNKNOWN: anything else. One UNKNOWN candidate leaves the member count and every weight unproven, so the whole
  allocation is BLOCKED: no unknown is excluded, defaulted or normalized into a weight.
* INCUBATION_MEMBER is not represented: it needs an ACTIVE incubation record whose schema (item 1.7) and parameters
  (A_max, T_max, W_INC) are pending, so no candidate can reach it and no ``COLD_START_EXCEPTED`` is ever produced.

Share vector (§4.2): ``v_i = max(EHS_i x Sharpe_30d_i, 0)``, ``r_i = v_i / sum(v)``, or ``1/n`` when every numerator is
0. BOOST ``beta_i = 6/5`` when "Sharpe_30d > 3/2 AND EHS > 4/5 AND no DECAY_ALERT" is proven true and 1 when it is proven
false; an unknown condition (DECAY_ALERT unknown) is evaluated under every value, and the result stands only when every
value gives identical weights (otherwise BLOCKED). ``t = (r * beta) / sum(r * beta)``.

Bounded projection (§4.3), exact: for ``3 <= n <= 5`` the unique minimizer of ``sum((w_i - t_i)^2)`` subject to
``sum(w_i) = 1`` and ``1/20 <= w_i <= 2/5``, computed by the piecewise-linear breakpoint method of the KKT form
``w_i = min(2/5, max(1/20, t_i + lambda))``; for ``n`` in {1, 2}, ``w_i = min(2/5, max(1/20, t_i))`` and the residual
``1 - sum(w)`` stays unallocated; ``n = 0`` allocates nothing. A proven state reduction (DE-WEIGHT, the correlation
halving, the combined-drawdown reduction) is never applied to a weight here: it is a risk reduction that SCALE-1 reads
(§4.7), so the floor never undoes it and no reduction is redistributed.

Rebalances (§1.7): at every 00:00 UTC and on every edge state transition. On the governed paper path no activation
proof (paper fill-rate, exchange health X-H1), no EHS or Sharpe_30d method (FCD-13), no DECAY_ALERT and no PRDV4 edge
state machine is produced. So ``derive_governed_paper_allocation_timeline`` reads every candidate as UNKNOWN at every UTC
midnight, every allocation is BLOCKED, and because no edge state transition is observable, no rebalance is ever proven
to be the latest one after its own instant: a weight is read only at its rebalance instant. Construction only: these
readings are the absence of the pending methods, never a calibrated value.

ENVELOPE_FIT (§4.6), for an exposure-increasing entry only: with ``usage`` its envelope usage and ``B`` the
publication-visible NAV at the same instant, PASS needs a MEMBER with ``usage <= w x B``; FAIL is a MEMBER with
``usage > w x B``, a NON_MEMBER with ``usage > 0``, or ``usage > 2/5 x B`` for any eligibility; anything else is BLOCKED,
an unproven ``B`` or ``usage`` included. Nothing here creates a capital quantity or a capital commitment.
"""

from __future__ import annotations

import bisect
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
)
from crypto_core.validation.historical_execution_economics_policy import (
    historical_execution_decimal_is_canonical,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)

_PREFIX = "governed_paper_allocation_envelope"
_DIGEST_FIELD = "timeline_digest"
_UTC_DAY_NS = 86_400 * 1_000_000_000
_SCALE = 10**18

GOVERNED_PAPER_ALLOCATION_CONTRACT_ID = "ALLOCATION_ENVELOPE_V1"
GOVERNED_PAPER_ALLOCATION_TIMELINE_SCHEMA = "governed-paper-allocation-timeline.v1"
GOVERNED_PAPER_ALLOCATION_FLOOR = Fraction(1, 20)  # §1.7 floor per active edge: 5%
GOVERNED_PAPER_ALLOCATION_CAP = Fraction(2, 5)  # §1.7 cap per edge: 40%
GOVERNED_PAPER_ALLOCATION_MAX_ACTIVE_EDGES = 5  # §1.7 maximum concurrent active edges
_MEMBER_EHS = Fraction(3, 10)  # §1.7 E_active: EHS >= 0.30
_BOOST_FACTOR = Fraction(6, 5)  # §1.7 BOOST: x 1.2
_BOOST_SHARPE = Fraction(3, 2)  # §1.7 BOOST: Sharpe_30d > 1.5
_BOOST_EHS = Fraction(4, 5)  # §1.7 BOOST: EHS > 0.80
_UTC_MIDNIGHT = "UTC_MIDNIGHT"
GOVERNED_PAPER_ALLOCATION_GOVERNED_READING_REASON = (
    "governed_paper_path_produces_no_activation_proof_x_h1_no_ehs_or_sharpe_30d_method_fcd13_and_no_decay_alert"
)
GOVERNED_PAPER_ALLOCATION_EDGE_STATE_REASON = (
    "prdv4_edge_state_machine_not_produced_so_no_rebalance_is_proven_the_latest_after_its_own_instant"
)
GOVERNED_PAPER_ALLOCATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("capital_allocated", False),
    ("incubation_basis_available", False),
    ("ehs_or_sharpe_method_approved", False),
    ("production_use_authorized", False),
)


class GovernedPaperAllocationError(EdgeArtifactError):
    """Malformed input: an allocation is never represented over it."""


class GovernedPaperAllocationActivation(str, Enum):
    PASS = "PASS"  # noqa: S105 - activation status label, not a credential.
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class GovernedPaperAllocationDecayAlert(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class GovernedPaperAllocationEligibility(str, Enum):
    MEMBER = "MEMBER"
    NON_MEMBER = "NON_MEMBER"
    UNKNOWN = "UNKNOWN"


class GovernedPaperAllocationStatus(str, Enum):
    ALLOCATED = "ALLOCATED"
    NO_ALLOCATION = "NO_ALLOCATION"
    BLOCKED = "BLOCKED"


class GovernedPaperEnvelopeFitStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GovernedPaperAllocationCandidate:
    """One candidate edge's readings at one rebalance; ``ehs`` and ``sharpe_30d`` are canonical decimals or None."""

    edge_id: str
    activation: GovernedPaperAllocationActivation
    ehs: str | None
    sharpe_30d: str | None
    decay_alert: GovernedPaperAllocationDecayAlert
    reading_reason: str


@dataclass(frozen=True)
class GovernedPaperAllocationWeight:
    """One candidate's eligibility and, for a member of a proven allocation, its exact weight.

    ``weight`` is a canonical exact rational text (``str(Fraction)``); ``rendered`` is its scale-18 truncation, which
    never crosses the floor or the cap.
    """

    edge_id: str
    eligibility: GovernedPaperAllocationEligibility
    reason: str
    weight: str | None
    rendered: str | None


@dataclass(frozen=True)
class GovernedPaperAllocationResult:
    """The allocation of one rebalance: one weight entry per candidate, in candidate order."""

    status: GovernedPaperAllocationStatus
    reason: str
    member_count: int | None
    boost: str
    weights: tuple[GovernedPaperAllocationWeight, ...]
    residual: str | None


@dataclass(frozen=True)
class GovernedPaperAllocationRebalance:
    instant_ns: int
    trigger: str
    candidates: tuple[GovernedPaperAllocationCandidate, ...]
    result: GovernedPaperAllocationResult


@dataclass(frozen=True)
class GovernedPaperAllocationTimeline:
    """The derived allocation readings of one governed horizon ``[start_ns, horizon_ns)``; never accepted."""

    schema_version: str
    contract_id: str
    genesis_digest: str
    candidate_edge_ids: tuple[str, ...]
    start_ns: int
    horizon_ns: int
    rebalances: tuple[GovernedPaperAllocationRebalance, ...]
    edge_state_transitions_proven: bool
    edge_state_reason: str
    timeline_digest: str
    paper_only: bool = True
    capital_allocated: bool = False
    incubation_basis_available: bool = False
    ehs_or_sharpe_method_approved: bool = False
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperAllocationReading:
    """One edge's eligibility and weight as read at ``time_ns`` from the latest rebalance at or before it."""

    edge_id: str
    time_ns: int
    rebalance_ns: int | None
    eligibility: GovernedPaperAllocationEligibility
    weight: str | None
    reason: str


@dataclass(frozen=True)
class GovernedPaperEnvelopeFit:
    """One ENVELOPE_FIT reading: status, the observed usage share of B (empty when unavailable) and the reason."""

    status: GovernedPaperEnvelopeFitStatus
    observed: str
    reason: str


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperAllocationError:
    return GovernedPaperAllocationError(_reason(code))


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


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def governed_paper_allocation_rational(value: Fraction) -> str:
    """The canonical exact rational text of a weight (``str(Fraction)``)."""

    return str(value)


def _render_truncated(value: Fraction) -> str:
    """The scale-18 decimal truncated toward zero: never above the value, so never above the cap or below a floor of
    two decimal places (T-ALLOC-20)."""

    if value < 0:  # pragma: no cover - weights are never negative
        raise _fail("weight_negative")
    units = value.numerator * _SCALE // value.denominator
    return f"{units // _SCALE}.{units % _SCALE:018d}"


# --- the bounded projection (§4.3) -------------------------------------------------------------------------------------


def _clip(value: Fraction) -> Fraction:
    return min(GOVERNED_PAPER_ALLOCATION_CAP, max(GOVERNED_PAPER_ALLOCATION_FLOOR, value))


def governed_paper_bounded_projection(shares: Sequence[Fraction]) -> tuple[Fraction, ...]:
    """The D9 bounded weights of a share vector ``t`` (exact; see the module docstring).

    ``t`` holds exact non-negative ``Fraction`` shares summing to 1 (empty for ``n = 0``). For ``3 <= n <= 20`` (where
    the constraint set is nonempty) it returns the unique Euclidean projection onto ``sum(w) = 1``, ``1/20 <= w <= 2/5``
    by the breakpoint method; for ``n`` in {1, 2} the clipped shares, whose residual stays unallocated. Anything else
    raises ``GovernedPaperAllocationError``. Pure.
    """

    if type(shares) is not tuple or any(type(item) is not Fraction or item < 0 for item in shares):
        raise _fail("shares_malformed")
    count = len(shares)
    if count == 0:
        return ()
    if sum(shares) != 1:
        raise _fail("shares_do_not_sum_to_1")
    if count <= 2:
        return tuple(_clip(item) for item in shares)
    if count * GOVERNED_PAPER_ALLOCATION_FLOOR > 1:
        raise _fail("projection_infeasible")
    floor, cap = GOVERNED_PAPER_ALLOCATION_FLOOR, GOVERNED_PAPER_ALLOCATION_CAP
    points = sorted({floor - item for item in shares} | {cap - item for item in shares})

    def total(shift: Fraction) -> Fraction:
        return sum((_clip(item + shift) for item in shares), Fraction(0))

    previous, shift = points[0], points[0]  # total(points[0]) == count x floor <= 1
    if total(previous) != 1:
        for point in points[1:]:
            value = total(point)
            if value >= 1:
                if value == 1:
                    shift = point
                else:  # inside (previous, point) no breakpoint lies, so each coordinate is clipped or free throughout
                    free = [item for item in shares if floor - item <= previous and cap - item >= point]
                    low = sum(1 for item in shares if floor - item >= point)
                    high = sum(1 for item in shares if cap - item <= previous)
                    shift = (1 - low * floor - high * cap - sum(free, Fraction(0))) / len(free)
                break
            previous = point
    weights = tuple(_clip(item + shift) for item in shares)
    if sum(weights) != 1:  # pragma: no cover - the breakpoint method is exact
        raise _fail("projection_not_exact")
    return weights


# --- one rebalance (§4.1, §4.2) ----------------------------------------------------------------------------------------


def _decimal(value: object, name: str) -> Fraction | None:
    if value is None:
        return None
    if type(value) is not str or not historical_execution_decimal_is_canonical(value):
        raise _fail(f"candidate_malformed:{name}")
    return Fraction(value)


def _canonical_candidates(candidates: object) -> tuple[GovernedPaperAllocationCandidate, ...]:
    if type(candidates) is not tuple or any(type(item) is not GovernedPaperAllocationCandidate for item in candidates):
        raise _fail("candidates_malformed")
    seen: set[str] = set()
    for item in candidates:
        _require_text(item.edge_id, "edge_id")
        _require_text(item.reading_reason, "reading_reason")
        if item.edge_id in seen:
            raise _fail("candidate_edge_id_duplicated")
        seen.add(item.edge_id)
        if type(item.activation) is not GovernedPaperAllocationActivation:
            raise _fail("candidate_malformed:activation")
        if type(item.decay_alert) is not GovernedPaperAllocationDecayAlert:
            raise _fail("candidate_malformed:decay_alert")
        ehs = _decimal(item.ehs, "ehs")
        if ehs is not None and not 0 <= ehs <= 1:
            raise _fail("candidate_malformed:ehs_outside_0_1")
        _decimal(item.sharpe_30d, "sharpe_30d")
    return candidates  # type: ignore[return-value]


def _boost(ehs: Fraction, sharpe: Fraction, decay: GovernedPaperAllocationDecayAlert) -> Fraction | None:
    """beta: 6/5 proven true, 1 proven false, None unknown (the DECAY_ALERT leg alone can be unknown)."""

    if sharpe <= _BOOST_SHARPE or ehs <= _BOOST_EHS or decay is GovernedPaperAllocationDecayAlert.ACTIVE:
        return Fraction(1)
    if decay is GovernedPaperAllocationDecayAlert.INACTIVE:
        return _BOOST_FACTOR
    return None


def _weights(shares: tuple[Fraction, ...], betas: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    boosted = tuple(share * beta for share, beta in zip(shares, betas, strict=True))
    scale = sum(boosted, Fraction(0))
    return governed_paper_bounded_projection(tuple(item / scale for item in boosted))


def derive_governed_paper_allocation(
    candidates: tuple[GovernedPaperAllocationCandidate, ...],
) -> GovernedPaperAllocationResult:
    """The ALLOCATION_ENVELOPE_V1 allocation of one rebalance over ``candidates`` (see the module docstring). Pure."""

    candidates = _canonical_candidates(candidates)
    eligibility: dict[str, tuple[GovernedPaperAllocationEligibility, str]] = {}
    active: list[tuple[GovernedPaperAllocationCandidate, Fraction, Fraction]] = []
    unknown: list[str] = []
    for item in candidates:
        ehs, sharpe = _decimal(item.ehs, "ehs"), _decimal(item.sharpe_30d, "sharpe_30d")
        if item.activation is GovernedPaperAllocationActivation.FAIL:
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.NON_MEMBER, "activation_proven_fail")
        elif ehs is not None and ehs < _MEMBER_EHS:
            reason = "edge_health_score_below_0_30_disabled"
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.NON_MEMBER, reason)
        elif item.activation is not GovernedPaperAllocationActivation.PASS:
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.UNKNOWN, "activation_unproven")
            unknown.append(item.edge_id)
        elif ehs is None:
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.UNKNOWN, "edge_health_score_undefined")
            unknown.append(item.edge_id)
        elif sharpe is None:
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.UNKNOWN, "sharpe_30d_undefined")
            unknown.append(item.edge_id)
        else:
            active.append((item, ehs, sharpe))

    def entries(weights: dict[str, Fraction]) -> tuple[GovernedPaperAllocationWeight, ...]:
        rows: list[GovernedPaperAllocationWeight] = []
        for item in candidates:
            state, why = eligibility[item.edge_id]
            weight = weights.get(item.edge_id)
            rows.append(
                GovernedPaperAllocationWeight(
                    edge_id=item.edge_id,
                    eligibility=state,
                    reason=why,
                    weight=None if weight is None else governed_paper_allocation_rational(weight),
                    rendered=None if weight is None else _render_truncated(weight),
                )
            )
        return tuple(rows)

    if unknown:
        for item, _, _ in active:  # n is unproven, so no provisional member's weight or selection is proven
            reason = "allocation_unproven_another_candidate_is_unknown"
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.UNKNOWN, reason)
        return GovernedPaperAllocationResult(
            status=GovernedPaperAllocationStatus.BLOCKED,
            reason=f"eligibility_unknown:{','.join(unknown)}",
            member_count=None,
            boost="NOT_EVALUATED",
            weights=entries({}),
            residual=None,
        )
    ranked = sorted(active, key=lambda row: (-(row[1] * row[2]), -row[1], row[0].edge_id.encode("utf-8")))
    members = ranked[:GOVERNED_PAPER_ALLOCATION_MAX_ACTIVE_EDGES]
    for item, _, _ in ranked[GOVERNED_PAPER_ALLOCATION_MAX_ACTIVE_EDGES:]:
        eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.NON_MEMBER, "proven_outside_the_top_five")
    for item, _, _ in members:
        eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.MEMBER, "proven_member")
    if not members:
        return GovernedPaperAllocationResult(
            status=GovernedPaperAllocationStatus.NO_ALLOCATION,
            reason="no_proven_member",
            member_count=0,
            boost="NOT_EVALUATED",
            weights=entries({}),
            residual=None,
        )
    numerators = tuple(max(ehs * sharpe, Fraction(0)) for _, ehs, sharpe in members)
    total = sum(numerators, Fraction(0))
    shares = (
        tuple(Fraction(1, len(members)) for _ in members) if total == 0 else tuple(item / total for item in numerators)
    )
    betas = [_boost(ehs, sharpe, item.decay_alert) for item, ehs, sharpe in members]
    open_legs = [index for index, beta in enumerate(betas) if beta is None]
    outcomes: set[tuple[Fraction, ...]] = set()
    for values in itertools.product((Fraction(1), _BOOST_FACTOR), repeat=len(open_legs)):
        chosen = list(betas)
        for index, value in zip(open_legs, values, strict=True):
            chosen[index] = value
        outcomes.add(_weights(shares, tuple(chosen)))  # type: ignore[arg-type]
    if len(outcomes) != 1:
        for item, _, _ in members:
            eligibility[item.edge_id] = (GovernedPaperAllocationEligibility.MEMBER, "proven_member_weight_unproven")
        return GovernedPaperAllocationResult(
            status=GovernedPaperAllocationStatus.BLOCKED,
            reason="boost_condition_unknown_and_the_weights_differ_under_its_values",
            member_count=len(members),
            boost="UNRESOLVED",
            weights=entries({}),
            residual=None,
        )
    (weights,) = outcomes
    boost = "IDENTICAL_UNDER_EVERY_VALUE" if open_legs else "PROVEN"
    return GovernedPaperAllocationResult(
        status=GovernedPaperAllocationStatus.ALLOCATED,
        reason="allocated",
        member_count=len(members),
        boost=boost,
        weights=entries({item.edge_id: weight for (item, _, _), weight in zip(members, weights, strict=True)}),
        residual=governed_paper_allocation_rational(1 - sum(weights, Fraction(0))),
    )


# --- the governed timeline ---------------------------------------------------------------------------------------------


def governed_paper_allocation_timeline_digest(timeline: GovernedPaperAllocationTimeline) -> str:
    """Recompute the canonical timeline digest, excluding only ``timeline_digest``."""

    return edge_payload_digest(_to_payload(timeline), _DIGEST_FIELD)


def governed_paper_allocation_timeline_to_dict(timeline: GovernedPaperAllocationTimeline) -> dict[str, object]:
    return _to_payload(timeline)


def derive_governed_paper_allocation_timeline(
    *,
    genesis_digest: str,
    candidate_edge_ids: tuple[str, ...],
    start_ns: int,
    horizon_ns: int,
) -> GovernedPaperAllocationTimeline:
    """The allocation readings of the governed paper path over ``[start_ns, horizon_ns)`` (see the module docstring).

    ``candidate_edge_ids`` are the sleeves the genesis portfolio envelope declares. Every UTC midnight of the horizon is a
    rebalance; every candidate is UNKNOWN there, because none of the readings membership needs is produced. Pure.
    """

    if not edge_is_hex64(genesis_digest):
        raise _fail("genesis_digest_invalid")
    if type(candidate_edge_ids) is not tuple or not candidate_edge_ids:
        raise _fail("candidate_edge_ids_malformed")
    if not historical_execution_wire_int_is_valid(start_ns, minimum=0):
        raise _fail("start_ns_invalid")
    if not historical_execution_wire_int_is_valid(horizon_ns, minimum=0):
        raise _fail("horizon_ns_invalid")
    if horizon_ns <= start_ns:
        raise _fail("horizon_not_after_start")
    candidates = tuple(
        GovernedPaperAllocationCandidate(
            edge_id=edge_id,
            activation=GovernedPaperAllocationActivation.UNKNOWN,
            ehs=None,
            sharpe_30d=None,
            decay_alert=GovernedPaperAllocationDecayAlert.UNKNOWN,
            reading_reason=GOVERNED_PAPER_ALLOCATION_GOVERNED_READING_REASON,
        )
        for edge_id in candidate_edge_ids
    )
    result = derive_governed_paper_allocation(candidates)  # validates the edge ids
    first = -(-start_ns // _UTC_DAY_NS) * _UTC_DAY_NS
    rebalances = tuple(
        GovernedPaperAllocationRebalance(instant, _UTC_MIDNIGHT, candidates, result)
        for instant in range(first, horizon_ns, _UTC_DAY_NS)
    )
    seed = GovernedPaperAllocationTimeline(
        schema_version=GOVERNED_PAPER_ALLOCATION_TIMELINE_SCHEMA,
        contract_id=GOVERNED_PAPER_ALLOCATION_CONTRACT_ID,
        genesis_digest=genesis_digest,
        candidate_edge_ids=candidate_edge_ids,
        start_ns=start_ns,
        horizon_ns=horizon_ns,
        rebalances=rebalances,
        edge_state_transitions_proven=False,
        edge_state_reason=GOVERNED_PAPER_ALLOCATION_EDGE_STATE_REASON,
        timeline_digest="",
    )
    return replace(seed, timeline_digest=governed_paper_allocation_timeline_digest(seed))


def governed_paper_allocation_reading_at(
    timeline: GovernedPaperAllocationTimeline, *, edge_id: str, time_ns: int
) -> GovernedPaperAllocationReading:
    """``edge_id``'s eligibility and weight at ``time_ns``: from the latest rebalance at or before it, and only while no
    later rebalance can lie between them (a proven edge-state record); otherwise UNKNOWN. Pure."""

    if type(timeline) is not GovernedPaperAllocationTimeline or edge_id not in timeline.candidate_edge_ids:
        raise _fail("timeline_or_edge_malformed")
    if not historical_execution_wire_int_is_valid(time_ns, minimum=0):
        raise _fail("time_ns_invalid")
    instants = [item.instant_ns for item in timeline.rebalances]
    index = bisect.bisect_right(instants, time_ns) - 1
    if index < 0:
        return GovernedPaperAllocationReading(
            edge_id,
            time_ns,
            None,
            GovernedPaperAllocationEligibility.UNKNOWN,
            None,
            "no_rebalance_at_or_before_the_instant",
        )
    rebalance = timeline.rebalances[index]
    entry = next(item for item in rebalance.result.weights if item.edge_id == edge_id)
    unknown = GovernedPaperAllocationEligibility.UNKNOWN
    if rebalance.result.status is GovernedPaperAllocationStatus.BLOCKED:
        reason = f"allocation_blocked_at_the_rebalance:{rebalance.result.reason}"
        return GovernedPaperAllocationReading(edge_id, time_ns, rebalance.instant_ns, unknown, None, reason)
    if time_ns > rebalance.instant_ns and not timeline.edge_state_transitions_proven:
        reason = "edge_state_transitions_since_the_rebalance_unproven"
        return GovernedPaperAllocationReading(edge_id, time_ns, rebalance.instant_ns, unknown, None, reason)
    return GovernedPaperAllocationReading(
        edge_id, time_ns, rebalance.instant_ns, entry.eligibility, entry.weight, entry.reason
    )


# --- ENVELOPE_FIT (§4.6) -----------------------------------------------------------------------------------------------


def evaluate_governed_paper_envelope_fit(
    *,
    eligibility: GovernedPaperAllocationEligibility,
    weight: Fraction | None,
    nav: Fraction | None,
    usage_lower: Fraction | None,
    usage_exact: bool,
) -> GovernedPaperEnvelopeFit:
    """ENVELOPE_FIT of one exposure-increasing entry at one instant (§4.6 status table). Pure.

    ``usage_lower`` is a proven lower bound of the usage (its exact value when ``usage_exact``), ``nav`` the
    publication-visible NAV ``B`` at the same instant and ``weight`` the edge's weight there. A FAIL needs only a proven
    bound: a NON_MEMBER with a positive usage, a usage above 2/5 of ``B`` for any eligibility, or a MEMBER above its
    weight. A PASS needs a MEMBER, a proven weight, a positive ``B`` and the exact usage within ``w x B``.
    """

    if type(eligibility) is not GovernedPaperAllocationEligibility or type(usage_exact) is not bool:
        raise _fail("envelope_inputs_malformed")
    for name, value in (("weight", weight), ("nav", nav), ("usage_lower", usage_lower)):
        if value is not None and type(value) is not Fraction:
            raise _fail(f"envelope_inputs_malformed:{name}")
    if usage_lower is not None and usage_lower < 0:
        raise _fail("envelope_inputs_malformed:usage_negative")
    if weight is not None and not GOVERNED_PAPER_ALLOCATION_FLOOR <= weight <= GOVERNED_PAPER_ALLOCATION_CAP:
        raise _fail("envelope_inputs_malformed:weight_outside_the_bounds")
    if usage_exact and usage_lower is None:
        raise _fail("envelope_inputs_malformed:exact_usage_missing")
    fail, blocked, passed = (
        GovernedPaperEnvelopeFitStatus.FAIL,
        GovernedPaperEnvelopeFitStatus.BLOCKED,
        GovernedPaperEnvelopeFitStatus.PASS,
    )
    observed = ""
    if usage_lower is not None and nav is not None and nav > 0:
        observed = historical_execution_render_amount(usage_lower / nav) or ""
    if eligibility is GovernedPaperAllocationEligibility.NON_MEMBER and usage_lower is not None and usage_lower > 0:
        return GovernedPaperEnvelopeFit(fail, observed, "non_member_with_a_positive_usage")
    if nav is None:
        return GovernedPaperEnvelopeFit(blocked, observed, "publication_visible_nav_unavailable")
    if nav <= 0:
        return GovernedPaperEnvelopeFit(blocked, observed, "publication_visible_nav_not_positive")
    if usage_lower is not None and usage_lower > GOVERNED_PAPER_ALLOCATION_CAP * nav:
        return GovernedPaperEnvelopeFit(fail, observed, "usage_above_0_40_of_nav_for_any_eligibility")
    if eligibility is GovernedPaperAllocationEligibility.MEMBER and weight is not None:
        if usage_lower is not None and usage_lower > weight * nav:
            return GovernedPaperEnvelopeFit(fail, observed, "member_usage_above_its_weight_times_nav")
        if usage_exact:
            return GovernedPaperEnvelopeFit(passed, observed, "member_usage_within_its_weight_times_nav")
        return GovernedPaperEnvelopeFit(blocked, observed, "usage_not_proven_exactly")
    if usage_lower is None:
        return GovernedPaperEnvelopeFit(blocked, observed, "usage_unavailable")
    if eligibility is GovernedPaperAllocationEligibility.MEMBER:
        return GovernedPaperEnvelopeFit(blocked, observed, "member_weight_unproven")
    return GovernedPaperEnvelopeFit(blocked, observed, "eligibility_unknown_and_usage_within_0_40_of_nav")


__all__ = [
    "GOVERNED_PAPER_ALLOCATION_CAP",
    "GOVERNED_PAPER_ALLOCATION_CONTRACT_ID",
    "GOVERNED_PAPER_ALLOCATION_EDGE_STATE_REASON",
    "GOVERNED_PAPER_ALLOCATION_FLOOR",
    "GOVERNED_PAPER_ALLOCATION_GOVERNED_READING_REASON",
    "GOVERNED_PAPER_ALLOCATION_MAX_ACTIVE_EDGES",
    "GOVERNED_PAPER_ALLOCATION_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_ALLOCATION_TIMELINE_SCHEMA",
    "GovernedPaperAllocationActivation",
    "GovernedPaperAllocationCandidate",
    "GovernedPaperAllocationDecayAlert",
    "GovernedPaperAllocationEligibility",
    "GovernedPaperAllocationError",
    "GovernedPaperAllocationReading",
    "GovernedPaperAllocationRebalance",
    "GovernedPaperAllocationResult",
    "GovernedPaperAllocationStatus",
    "GovernedPaperAllocationTimeline",
    "GovernedPaperAllocationWeight",
    "GovernedPaperEnvelopeFit",
    "GovernedPaperEnvelopeFitStatus",
    "derive_governed_paper_allocation",
    "derive_governed_paper_allocation_timeline",
    "evaluate_governed_paper_envelope_fit",
    "governed_paper_allocation_rational",
    "governed_paper_allocation_reading_at",
    "governed_paper_allocation_timeline_digest",
    "governed_paper_allocation_timeline_to_dict",
    "governed_paper_bounded_projection",
]
