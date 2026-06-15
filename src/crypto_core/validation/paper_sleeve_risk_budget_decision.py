"""Paper sleeve risk-budget decision — deterministic, paper-only budget eligibility over recorded intents.

A small, immutable, fail-closed *decision* layer that consumes a re-proven ``PaperSleeveState`` (the
append-only intent ledger from the paper sleeve seam) and a ``PaperSleeveRiskBudgetPolicy`` and renders a
digest-bound classification of which RECORDED paper intents are *budget-eligible* (a risk-budget
reservation only) versus BLOCKED / INSUFFICIENT_EVIDENCE. It is *only* a decision/eligibility layer: it
does **not** execute, route, send, fill, simulate fills, compute PnL, open/close positions, connect,
schedule, run a loop, or create any live/shadow capability — no DB/file/network/env IO, no wall-clock, no
random, no threading. "Budget" here means risk-budget eligibility/reservation, never execution permission.

Design rules:
  - Re-prove before deciding: the incoming state is re-proven via the public ``paper_sleeve_state_digest``
    and every record via the public ``paper_sleeve_intent_record_digest``; the policy is re-proven via
    ``paper_sleeve_risk_budget_policy_digest``. A caller-supplied digest is never trusted. A tampered /
    resealed-but-unsafe / inconsistent / duplicate / mis-sequenced state, a sleeve-id mismatch, or a
    paper-safety violation raises ``PaperSleeveRiskBudgetDecisionError`` before any decision is produced.
  - Eligibility is strict and fail-closed: only ``PaperSleeveIntentStatus.RECORDED`` records with
    ``accepted=True``, ``journal_bound=True``, a valid 64-hex ``journal_payload_digest``, and a present,
    positive, strict-decimal price/quantity may become ELIGIBLE. REJECTED records are BLOCKED, an
    INSUFFICIENT_EVIDENCE record is classified INSUFFICIENT_EVIDENCE, and an unbound / unpriced / over-cap
    record is BLOCKED — each with reserved budget ``"0"``. Eligibility is a budget reservation, not an order.
  - Deterministic numeric discipline: budgets are exact decimal *strings* (no float, no NaN/inf, no
    scientific/whitespace/underscore forms, no negatives); ``decimal.Decimal`` is used only for exact
    comparison/addition/multiplication and canonical plain-string rendering (never scientific), so there is
    no float drift. ``total_reserved_budget`` never exceeds ``total_budget`` by construction.
  - Deterministic digests: canonical SHA-256 over the public serializer output (enum ``.value`` and stable
    list ordering) excluding each self-digest. Frozen dataclasses; stable sorted blockers; the input state
    is never mutated. ``paper_only=True`` and no order/route/venue/scheduler/fill/PnL/position field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveIntentRecord,
    PaperSleeveIntentStatus,
    PaperSleeveState,
    paper_sleeve_intent_record_digest,
    paper_sleeve_state_digest,
)

_POLICY_SCHEMA_VERSION = "paper-sleeve-risk-budget-policy.v1"
_RECORD_DECISION_SCHEMA_VERSION = "paper-sleeve-risk-budget-record-decision.v1"
_DECISION_SCHEMA_VERSION = "paper-sleeve-risk-budget-decision.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional fraction.
# Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace, and underscores.
# Budget values additionally must be non-negative and (for caps/total) strictly positive — enforced below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the paper sleeve intent ledger guard (word-bounded). A bare ``order``/``orders`` token
# is rejected while ``border``/``reorder`` are spared; market-data terms are scrubbed before the scan.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector_ready|credential|"
    r"credentials|scheduler|shadow)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperSleeveRiskBudgetDecisionError(RuntimeError):
    """Raised when state/policy inputs are malformed or fail re-proof/safety/consistency before a decision."""


class PaperSleeveRiskBudgetRecordStatus(str, Enum):
    """Terminal budget-eligibility classification of one recorded paper intent. Never an execution action."""

    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSleeveRiskBudgetPolicy:
    """Deterministic, immutable paper risk-budget policy. Budgets are reservation caps only. PAPER ONLY."""

    schema_version: str
    policy_id: str
    sleeve_id: str
    total_budget: str
    per_intent_budget_cap: str
    per_instrument_budget_cap: str | None
    require_journal_bound: bool
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperSleeveRiskBudgetRecordDecision:
    """Deterministic, immutable per-record budget decision. Reservation/eligibility only. PAPER ONLY."""

    schema_version: str
    status: PaperSleeveRiskBudgetRecordStatus
    sequence: int
    record_digest: str
    paper_trade_tick_digest: str
    intent_status: str
    tick_status: str
    instrument_id: str
    action: str
    requested_budget: str
    reserved_budget: str
    blockers: tuple[str, ...]
    record_decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperSleeveRiskBudgetDecision:
    """Deterministic, immutable digest-bound budget decision over a sleeve state. PAPER ONLY."""

    schema_version: str
    policy_id: str
    sleeve_id: str
    state_digest: str
    policy_digest: str
    record_decisions: tuple[PaperSleeveRiskBudgetRecordDecision, ...]
    eligible_count: int
    blocked_count: int
    insufficient_count: int
    total_budget: str
    total_requested_budget: str
    total_reserved_budget: str
    blockers: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    correlation_id: str
    decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _parse_decimal(value: object) -> Decimal | None:
    """Return an exact finite ``Decimal`` for a strict decimal string, else ``None`` (no float/bool path)."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    """Render an exact ``Decimal`` as a canonical plain-decimal string (never scientific notation)."""
    return format(value, "f")


def _budget_arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal context precision large enough to make every budget product/sum exact (input-derived).

    The default ``decimal`` context (28 significant digits) can silently round a high-precision
    ``quantity * price`` product (or running budget sum) down to a cap, letting an over-budget intent
    slip through ELIGIBLE. Summing the significant-digit counts of all operands upper-bounds the exact
    coefficient length of any product or running sum; a fixed guard covers exponent-alignment growth.
    The precision depends only on the inputs, so the decision stays deterministic.
    """
    operand_digits = sum(len(value.as_tuple().digits) for value in operands)
    return max(28, operand_digits + 32)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_sleeve_risk_budget_decision:bist_scope_leakage")
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            reasons.append("paper_sleeve_risk_budget_decision:forbidden_scope_token")
    return tuple(reasons)


def _require_positive_budget(value: object, field: str) -> Decimal:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperSleeveRiskBudgetDecisionError(f"paper_sleeve_risk_budget_decision:policy_{field}_not_decimal_string")
    if not parsed > 0:
        raise PaperSleeveRiskBudgetDecisionError(f"paper_sleeve_risk_budget_decision:policy_{field}_not_positive")
    return parsed


def _policy_payload(
    *,
    schema_version: str,
    policy_id: str,
    sleeve_id: str,
    total_budget: str,
    per_intent_budget_cap: str,
    per_instrument_budget_cap: str | None,
    require_journal_bound: bool,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "policy_id": policy_id,
        "sleeve_id": sleeve_id,
        "total_budget": total_budget,
        "per_intent_budget_cap": per_intent_budget_cap,
        "per_instrument_budget_cap": per_instrument_budget_cap,
        "require_journal_bound": require_journal_bound,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def build_paper_sleeve_risk_budget_policy(
    *,
    policy_id: str,
    sleeve_id: str,
    total_budget: str,
    per_intent_budget_cap: str,
    per_instrument_budget_cap: str | None = None,
    require_journal_bound: bool = True,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleeveRiskBudgetPolicy:
    """Build a deterministic, immutable paper risk-budget policy with a canonical ``policy_digest``.

    ``policy_id``/``sleeve_id`` must be non-empty token-clean strings; ``total_budget`` and
    ``per_intent_budget_cap`` (and ``per_instrument_budget_cap`` when given) must be strict, strictly
    positive decimal strings (no float/NaN/inf/scientific/whitespace/underscore/negative form);
    ``require_journal_bound`` must be exactly ``True`` — the seam only admits journal-bound intents to
    budget eligibility, so a ``False`` value fails closed at construction rather than silently keeping
    unbound records blocked while changing the policy digest; ``metadata`` (if given) a
    ``Mapping[str, str]``. A malformed id/budget/flag/metadata or a forbidden
    BIST/live/order/scheduler/connector/shadow token raises ``PaperSleeveRiskBudgetDecisionError``. The
    policy attests paper-safety (``paper_only`` True, real orders/money False) and allocates/executes
    nothing — budgets are risk-budget reservation caps only.
    """
    if not _is_non_empty_string(policy_id):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_id_invalid")
    if not _is_non_empty_string(sleeve_id):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_sleeve_id_invalid")
    if require_journal_bound is not True:
        raise PaperSleeveRiskBudgetDecisionError(
            "paper_sleeve_risk_budget_decision:policy_require_journal_bound_must_be_true"
        )
    _require_positive_budget(total_budget, "total_budget")
    _require_positive_budget(per_intent_budget_cap, "per_intent_budget_cap")
    if per_instrument_budget_cap is not None:
        _require_positive_budget(per_instrument_budget_cap, "per_instrument_budget_cap")
    metadata_pairs = _normalize_metadata(metadata)
    if _scope_violations(policy_id, sleeve_id, *_metadata_texts(metadata_pairs)):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_scope_violation")
    payload = _policy_payload(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        sleeve_id=sleeve_id,
        total_budget=total_budget,
        per_intent_budget_cap=per_intent_budget_cap,
        per_instrument_budget_cap=per_instrument_budget_cap,
        require_journal_bound=require_journal_bound,
        metadata=metadata_pairs,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperSleeveRiskBudgetPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        sleeve_id=sleeve_id,
        total_budget=total_budget,
        per_intent_budget_cap=per_intent_budget_cap,
        per_instrument_budget_cap=per_instrument_budget_cap,
        require_journal_bound=require_journal_bound,
        metadata=metadata_pairs,
        policy_digest=_canonical_digest(payload),
    )


def _reprove_policy(policy: PaperSleeveRiskBudgetPolicy) -> tuple[Decimal, Decimal, Decimal | None]:
    """Re-prove a policy's paper-safety, digest, and budgets (never trusting the stored digest)."""
    if not isinstance(policy, PaperSleeveRiskBudgetPolicy):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_malformed")
    if policy.paper_only is not True:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_not_paper_only")
    if policy.real_orders_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_real_orders_enabled")
    if policy.real_money_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_real_money_enabled")
    if policy.require_journal_bound is not True:
        raise PaperSleeveRiskBudgetDecisionError(
            "paper_sleeve_risk_budget_decision:policy_require_journal_bound_must_be_true"
        )
    if not _is_non_empty_string(policy.policy_id) or not _is_non_empty_string(policy.sleeve_id):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_id_invalid")
    total = _require_positive_budget(policy.total_budget, "total_budget")
    per_intent = _require_positive_budget(policy.per_intent_budget_cap, "per_intent_budget_cap")
    per_instrument = (
        _require_positive_budget(policy.per_instrument_budget_cap, "per_instrument_budget_cap")
        if policy.per_instrument_budget_cap is not None
        else None
    )
    if _scope_violations(policy.policy_id, policy.sleeve_id, *_metadata_texts(policy.metadata)):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_scope_violation")
    if paper_sleeve_risk_budget_policy_digest(policy) != policy.policy_digest:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_digest_mismatch")
    return total, per_intent, per_instrument


def _reprove_state(state: PaperSleeveState, sleeve_id: str) -> None:
    """Re-prove an incoming sleeve state's safety, consistency, sequencing, and digest (fail-closed)."""
    if not isinstance(state, PaperSleeveState):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_malformed")
    # Paper-safety triple before digest: a resealed state can still attest unsafe flags.
    if state.paper_only is not True:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_not_paper_only")
    if state.real_orders_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_real_orders_enabled")
    if state.real_money_enabled is not False:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_real_money_enabled")
    if state.sleeve_id != sleeve_id:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:policy_sleeve_id_mismatch")
    if any(
        record.paper_only is not True
        or record.real_orders_enabled is not False
        or record.real_money_enabled is not False
        for record in state.records
    ):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_record_not_paper_safe")
    if any(record.sleeve_id != state.sleeve_id for record in state.records):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:record_sleeve_id_mismatch")
    if any(paper_sleeve_intent_record_digest(record) != record.record_digest for record in state.records):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:record_digest_mismatch")
    record_digests = [record.record_digest for record in state.records]
    if len(set(record_digests)) != len(record_digests):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:duplicate_record_digest")
    tick_digests = [record.paper_trade_tick_digest for record in state.records]
    if len(set(tick_digests)) != len(tick_digests):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:duplicate_tick_digest")
    if any(record.sequence != index for index, record in enumerate(state.records)):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:sequence_invalid")
    if state.record_count != len(state.records):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_record_count_mismatch")
    recorded = sum(1 for record in state.records if record.intent_status is PaperSleeveIntentStatus.RECORDED)
    if state.recorded_count != recorded:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_recorded_count_mismatch")
    if paper_sleeve_state_digest(state) != state.state_digest:
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:state_digest_mismatch")


def _classify_record(
    record: PaperSleeveIntentRecord,
    *,
    total_budget: Decimal,
    per_intent_cap: Decimal,
    per_instrument_cap: Decimal | None,
    total_reserved: Decimal,
    instrument_reserved: dict[str, Decimal],
) -> tuple[PaperSleeveRiskBudgetRecordStatus, Decimal, Decimal, tuple[str, ...]]:
    """Classify one record into (status, requested, reserved, blockers). Reserves only when fully eligible."""
    zero = Decimal(0)
    if record.intent_status is PaperSleeveIntentStatus.REJECTED:
        return PaperSleeveRiskBudgetRecordStatus.BLOCKED, zero, zero, ("record_rejected",)
    if record.intent_status is PaperSleeveIntentStatus.INSUFFICIENT_EVIDENCE:
        return (
            PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE,
            zero,
            zero,
            ("record_insufficient_evidence",),
        )

    # RECORDED candidate: enforce eligibility preconditions (fail-closed before any reservation).
    blockers: list[str] = []
    if record.accepted is not True:
        blockers.append("record_not_accepted")
    if record.journal_bound is not True:
        blockers.append("record_not_journal_bound")
    elif not _is_sha256_hex(record.journal_payload_digest):
        blockers.append("journal_payload_digest_invalid")

    if record.limit_price is None:
        blockers.append("missing_price")
        return PaperSleeveRiskBudgetRecordStatus.BLOCKED, zero, zero, _sorted_unique(tuple(blockers))

    quantity = _parse_decimal(record.quantity)
    price = _parse_decimal(record.limit_price)
    if quantity is None or not quantity > 0:
        blockers.append("quantity_not_positive_decimal")
    if price is None or not price > 0:
        blockers.append("limit_price_not_positive_decimal")
    if quantity is None or price is None or not quantity > 0 or not price > 0:
        return PaperSleeveRiskBudgetRecordStatus.BLOCKED, zero, zero, _sorted_unique(tuple(blockers))

    requested = quantity * price
    if requested > per_intent_cap:
        blockers.append("per_intent_budget_cap_exceeded")
    if total_reserved + requested > total_budget:
        blockers.append("total_budget_exceeded")
    if per_instrument_cap is not None:
        prior_instrument = instrument_reserved.get(record.instrument_id, zero)
        if prior_instrument + requested > per_instrument_cap:
            blockers.append("per_instrument_budget_cap_exceeded")

    if blockers:
        return PaperSleeveRiskBudgetRecordStatus.BLOCKED, requested, zero, _sorted_unique(tuple(blockers))
    return PaperSleeveRiskBudgetRecordStatus.ELIGIBLE, requested, requested, ()


def _finalize_record_decision(
    record: PaperSleeveIntentRecord,
    *,
    status: PaperSleeveRiskBudgetRecordStatus,
    requested: Decimal,
    reserved: Decimal,
    blockers: tuple[str, ...],
) -> PaperSleeveRiskBudgetRecordDecision:
    payload = _record_decision_payload(
        schema_version=_RECORD_DECISION_SCHEMA_VERSION,
        status_value=status.value,
        sequence=record.sequence,
        record_digest=record.record_digest,
        paper_trade_tick_digest=record.paper_trade_tick_digest,
        intent_status=record.intent_status.value,
        tick_status=record.tick_status,
        instrument_id=record.instrument_id,
        action=record.action,
        requested_budget=_render_decimal(requested),
        reserved_budget=_render_decimal(reserved),
        blockers=blockers,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperSleeveRiskBudgetRecordDecision(
        schema_version=_RECORD_DECISION_SCHEMA_VERSION,
        status=status,
        sequence=record.sequence,
        record_digest=record.record_digest,
        paper_trade_tick_digest=record.paper_trade_tick_digest,
        intent_status=record.intent_status.value,
        tick_status=record.tick_status,
        instrument_id=record.instrument_id,
        action=record.action,
        requested_budget=_render_decimal(requested),
        reserved_budget=_render_decimal(reserved),
        blockers=blockers,
        record_decision_digest=_canonical_digest(payload),
    )


def evaluate_paper_sleeve_risk_budget(
    state: PaperSleeveState,
    policy: PaperSleeveRiskBudgetPolicy,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSleeveRiskBudgetDecision:
    """Render a deterministic, digest-bound paper risk-budget decision over a re-proven sleeve state.

    The ``policy`` is re-proven (paper-safety + digest + positive budgets) and the ``state`` is re-proven
    (paper-safety triple, per-record safety, sleeve-id match, record/state digests, contiguous sequencing,
    no duplicate record/tick digests, count consistency) before any decision; a failure raises
    ``PaperSleeveRiskBudgetDecisionError`` and the input state is never mutated. Only RECORDED + accepted +
    journal-bound + priced records within the per-intent / total / per-instrument caps become ELIGIBLE (a
    risk-budget reservation, not an order); everything else is BLOCKED / INSUFFICIENT_EVIDENCE with reserved
    budget ``"0"``. ``total_reserved_budget`` never exceeds ``total_budget``. Decides eligibility only — no
    execution, routing, fill, PnL, position, scheduler, connector, or live/shadow capability.
    """
    if not _is_non_empty_string(correlation_id):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:correlation_id_invalid")
    decision_metadata = _normalize_metadata(metadata)
    if _scope_violations(correlation_id, *_metadata_texts(decision_metadata)):
        raise PaperSleeveRiskBudgetDecisionError("paper_sleeve_risk_budget_decision:scope_violation")

    total_budget, per_intent_cap, per_instrument_cap = _reprove_policy(policy)
    _reprove_state(state, policy.sleeve_id)

    # Exact budget arithmetic: derive a precision wide enough that no product/sum is rounded (which could
    # otherwise round an over-budget notional down to a cap and bypass it). Precision is input-derived only.
    operands: list[Decimal] = [total_budget, per_intent_cap]
    if per_instrument_cap is not None:
        operands.append(per_instrument_cap)
    for record in state.records:
        for raw in (record.quantity, record.limit_price):
            parsed = _parse_decimal(raw) if isinstance(raw, str) else None
            if parsed is not None:
                operands.append(parsed)
    precision = _budget_arithmetic_precision(tuple(operands))

    zero = Decimal(0)
    total_reserved = zero
    total_requested = zero
    instrument_reserved: dict[str, Decimal] = {}
    record_decisions: list[PaperSleeveRiskBudgetRecordDecision] = []
    eligible_count = 0
    blocked_count = 0
    insufficient_count = 0
    all_blockers: list[str] = []

    with localcontext() as ctx:
        ctx.prec = precision
        for record in state.records:
            status, requested, reserved, blockers = _classify_record(
                record,
                total_budget=total_budget,
                per_intent_cap=per_intent_cap,
                per_instrument_cap=per_instrument_cap,
                total_reserved=total_reserved,
                instrument_reserved=instrument_reserved,
            )
            if status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE:
                total_reserved += reserved
                instrument_reserved[record.instrument_id] = (
                    instrument_reserved.get(record.instrument_id, zero) + reserved
                )
                eligible_count += 1
            elif status is PaperSleeveRiskBudgetRecordStatus.INSUFFICIENT_EVIDENCE:
                insufficient_count += 1
            else:
                blocked_count += 1
            total_requested += requested
            all_blockers.extend(blockers)
            record_decisions.append(
                _finalize_record_decision(
                    record, status=status, requested=requested, reserved=reserved, blockers=blockers
                )
            )

    decision_blockers = _sorted_unique(tuple(all_blockers))
    record_decisions_tuple = tuple(record_decisions)
    payload = _decision_payload(
        schema_version=_DECISION_SCHEMA_VERSION,
        policy_id=policy.policy_id,
        sleeve_id=state.sleeve_id,
        state_digest=state.state_digest,
        policy_digest=policy.policy_digest,
        record_decision_dicts=[
            paper_sleeve_risk_budget_record_decision_to_dict(decision) for decision in record_decisions_tuple
        ],
        eligible_count=eligible_count,
        blocked_count=blocked_count,
        insufficient_count=insufficient_count,
        total_budget=_render_decimal(total_budget),
        total_requested_budget=_render_decimal(total_requested),
        total_reserved_budget=_render_decimal(total_reserved),
        blockers=decision_blockers,
        metadata=decision_metadata,
        correlation_id=correlation_id,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperSleeveRiskBudgetDecision(
        schema_version=_DECISION_SCHEMA_VERSION,
        policy_id=policy.policy_id,
        sleeve_id=state.sleeve_id,
        state_digest=state.state_digest,
        policy_digest=policy.policy_digest,
        record_decisions=record_decisions_tuple,
        eligible_count=eligible_count,
        blocked_count=blocked_count,
        insufficient_count=insufficient_count,
        total_budget=_render_decimal(total_budget),
        total_requested_budget=_render_decimal(total_requested),
        total_reserved_budget=_render_decimal(total_reserved),
        blockers=decision_blockers,
        metadata=decision_metadata,
        correlation_id=correlation_id,
        decision_digest=_canonical_digest(payload),
    )


def paper_sleeve_risk_budget_policy_to_dict(policy: PaperSleeveRiskBudgetPolicy) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a risk-budget policy (deterministic shape, includes self-digest)."""
    payload = _policy_payload(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        sleeve_id=policy.sleeve_id,
        total_budget=policy.total_budget,
        per_intent_budget_cap=policy.per_intent_budget_cap,
        per_instrument_budget_cap=policy.per_instrument_budget_cap,
        require_journal_bound=policy.require_journal_bound,
        metadata=policy.metadata,
        paper_only=policy.paper_only,
        real_orders_enabled=policy.real_orders_enabled,
        real_money_enabled=policy.real_money_enabled,
    )
    payload["policy_digest"] = policy.policy_digest
    return payload


def paper_sleeve_risk_budget_policy_digest(policy: PaperSleeveRiskBudgetPolicy) -> str:
    """Recompute the canonical policy digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _policy_payload(
            schema_version=policy.schema_version,
            policy_id=policy.policy_id,
            sleeve_id=policy.sleeve_id,
            total_budget=policy.total_budget,
            per_intent_budget_cap=policy.per_intent_budget_cap,
            per_instrument_budget_cap=policy.per_instrument_budget_cap,
            require_journal_bound=policy.require_journal_bound,
            metadata=policy.metadata,
            paper_only=policy.paper_only,
            real_orders_enabled=policy.real_orders_enabled,
            real_money_enabled=policy.real_money_enabled,
        )
    )


def _record_decision_payload(
    *,
    schema_version: str,
    status_value: str,
    sequence: int,
    record_digest: str,
    paper_trade_tick_digest: str,
    intent_status: str,
    tick_status: str,
    instrument_id: str,
    action: str,
    requested_budget: str,
    reserved_budget: str,
    blockers: tuple[str, ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "sequence": sequence,
        "record_digest": record_digest,
        "paper_trade_tick_digest": paper_trade_tick_digest,
        "intent_status": intent_status,
        "tick_status": tick_status,
        "instrument_id": instrument_id,
        "action": action,
        "requested_budget": requested_budget,
        "reserved_budget": reserved_budget,
        "blockers": list(blockers),
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def paper_sleeve_risk_budget_record_decision_to_dict(
    decision: PaperSleeveRiskBudgetRecordDecision,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a per-record budget decision (includes self-digest)."""
    payload = _record_decision_payload(
        schema_version=decision.schema_version,
        status_value=decision.status.value,
        sequence=decision.sequence,
        record_digest=decision.record_digest,
        paper_trade_tick_digest=decision.paper_trade_tick_digest,
        intent_status=decision.intent_status,
        tick_status=decision.tick_status,
        instrument_id=decision.instrument_id,
        action=decision.action,
        requested_budget=decision.requested_budget,
        reserved_budget=decision.reserved_budget,
        blockers=decision.blockers,
        paper_only=decision.paper_only,
        real_orders_enabled=decision.real_orders_enabled,
        real_money_enabled=decision.real_money_enabled,
    )
    payload["record_decision_digest"] = decision.record_decision_digest
    return payload


def paper_sleeve_risk_budget_record_decision_digest(decision: PaperSleeveRiskBudgetRecordDecision) -> str:
    """Recompute the canonical per-record decision digest, excluding the self-digest field."""
    return _canonical_digest(
        _record_decision_payload(
            schema_version=decision.schema_version,
            status_value=decision.status.value,
            sequence=decision.sequence,
            record_digest=decision.record_digest,
            paper_trade_tick_digest=decision.paper_trade_tick_digest,
            intent_status=decision.intent_status,
            tick_status=decision.tick_status,
            instrument_id=decision.instrument_id,
            action=decision.action,
            requested_budget=decision.requested_budget,
            reserved_budget=decision.reserved_budget,
            blockers=decision.blockers,
            paper_only=decision.paper_only,
            real_orders_enabled=decision.real_orders_enabled,
            real_money_enabled=decision.real_money_enabled,
        )
    )


def _decision_payload(
    *,
    schema_version: str,
    policy_id: str,
    sleeve_id: str,
    state_digest: str,
    policy_digest: str,
    record_decision_dicts: list[dict[str, object]],
    eligible_count: int,
    blocked_count: int,
    insufficient_count: int,
    total_budget: str,
    total_requested_budget: str,
    total_reserved_budget: str,
    blockers: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
    correlation_id: str,
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "policy_id": policy_id,
        "sleeve_id": sleeve_id,
        "state_digest": state_digest,
        "policy_digest": policy_digest,
        "record_decisions": record_decision_dicts,
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "insufficient_count": insufficient_count,
        "total_budget": total_budget,
        "total_requested_budget": total_requested_budget,
        "total_reserved_budget": total_reserved_budget,
        "blockers": list(blockers),
        "metadata": [list(pair) for pair in metadata],
        "correlation_id": correlation_id,
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def paper_sleeve_risk_budget_decision_to_dict(decision: PaperSleeveRiskBudgetDecision) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a risk-budget decision (deterministic shape, includes self-digest)."""
    payload = _decision_payload(
        schema_version=decision.schema_version,
        policy_id=decision.policy_id,
        sleeve_id=decision.sleeve_id,
        state_digest=decision.state_digest,
        policy_digest=decision.policy_digest,
        record_decision_dicts=[
            paper_sleeve_risk_budget_record_decision_to_dict(record) for record in decision.record_decisions
        ],
        eligible_count=decision.eligible_count,
        blocked_count=decision.blocked_count,
        insufficient_count=decision.insufficient_count,
        total_budget=decision.total_budget,
        total_requested_budget=decision.total_requested_budget,
        total_reserved_budget=decision.total_reserved_budget,
        blockers=decision.blockers,
        metadata=decision.metadata,
        correlation_id=decision.correlation_id,
        paper_only=decision.paper_only,
        real_orders_enabled=decision.real_orders_enabled,
        real_money_enabled=decision.real_money_enabled,
    )
    payload["decision_digest"] = decision.decision_digest
    return payload


def paper_sleeve_risk_budget_decision_digest(decision: PaperSleeveRiskBudgetDecision) -> str:
    """Recompute the canonical decision digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _decision_payload(
            schema_version=decision.schema_version,
            policy_id=decision.policy_id,
            sleeve_id=decision.sleeve_id,
            state_digest=decision.state_digest,
            policy_digest=decision.policy_digest,
            record_decision_dicts=[
                paper_sleeve_risk_budget_record_decision_to_dict(record) for record in decision.record_decisions
            ],
            eligible_count=decision.eligible_count,
            blocked_count=decision.blocked_count,
            insufficient_count=decision.insufficient_count,
            total_budget=decision.total_budget,
            total_requested_budget=decision.total_requested_budget,
            total_reserved_budget=decision.total_reserved_budget,
            blockers=decision.blockers,
            metadata=decision.metadata,
            correlation_id=decision.correlation_id,
            paper_only=decision.paper_only,
            real_orders_enabled=decision.real_orders_enabled,
            real_money_enabled=decision.real_money_enabled,
        )
    )


__all__ = [
    "PaperSleeveRiskBudgetDecision",
    "PaperSleeveRiskBudgetDecisionError",
    "PaperSleeveRiskBudgetPolicy",
    "PaperSleeveRiskBudgetRecordDecision",
    "PaperSleeveRiskBudgetRecordStatus",
    "build_paper_sleeve_risk_budget_policy",
    "evaluate_paper_sleeve_risk_budget",
    "paper_sleeve_risk_budget_decision_digest",
    "paper_sleeve_risk_budget_decision_to_dict",
    "paper_sleeve_risk_budget_policy_digest",
    "paper_sleeve_risk_budget_policy_to_dict",
    "paper_sleeve_risk_budget_record_decision_digest",
    "paper_sleeve_risk_budget_record_decision_to_dict",
]
