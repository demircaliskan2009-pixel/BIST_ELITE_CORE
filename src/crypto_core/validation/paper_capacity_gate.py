"""Paper capacity gate — deterministic, paper-only admissibility verdict over an allocator-intent draft.

A small, immutable, fail-closed *verdict gate* that consumes a ``DRAFT_READY``
``PaperAllocatorIntentDraft`` and a ``PaperCapacityGatePolicy`` and renders a digest-bound
``ADMITTED`` / ``REJECTED`` verdict answering one question: "is this draft admissible as a basis for
*future* paper order-intent construction under this capacity policy?" It is **only** a verdict layer:
it reserves no capital, allocates nothing, creates/routes/fills no order, opens/mutates no position,
computes no PnL, appends to no journal, and mutates no input — no DB/file/network/env IO, no
wall-clock, no random, no threading, no connector/scheduler/runtime/venue/execution/service/session
surface, no Deribit, no BIST. ``ADMITTED`` is a *consideration* verdict, never an execution
permission and never a capital reservation.

Capacity model (the allocator-intent draft is verdict-only and carries no notional/units — only an
``eligible_count``):
  - ``max_open_intents`` is checked against the draft's digest-validated ``eligible_count`` (the count
    of eligible intents the draft would carry forward — draft-driven).
  - ``max_notional`` / ``max_units`` are checked against caller-supplied *prospective* demand
    (``requested_notional`` / ``requested_units``): a hypothetical "if a future order-intent of this
    size were constructed, would the policy admit it?" range-check. Nothing is reserved or mutated;
    the demand is a non-binding descriptor, not an allocation.

Design rules:
  - Re-prove before judging: the ``policy`` is re-proven (paper-safety triple, positive caps, scope,
    ``policy_digest``) and a malformed/misconfigured policy raises ``PaperCapacityGateError`` (the gate
    refuses to run against a broken configuration). The draft's ``draft_digest`` is recomputed via the
    PUBLIC ``paper_allocator_intent_draft_digest`` and a mismatch fails closed to ``REJECTED`` — a
    self-consistent forged draft (digest recomputes, but unsafe flags / non-DRAFT_READY status /
    identity mismatch / scope leakage) is still rejected on those fields. A caller-supplied digest is
    never trusted.
  - Deterministic numeric discipline: caps and demand are exact decimal *strings* (no float, no
    NaN/inf, no scientific/whitespace/underscore form, no negatives); ``decimal.Decimal`` is used only
    for exact comparison and canonical plain-string rendering (never scientific). Capacity comparison
    is exact (no multiplication, so no rounding path).
  - Deterministic digest: canonical SHA-256 over the public serializer output (enum ``.value`` and
    stable ordering) excluding the self-digest. Frozen dataclasses; stable sorted reason codes; no
    input is mutated.
  - Fail closed: a wrong-typed input, an invalid/forbidden ``correlation_id``/metadata, a
    non-decimal demand, or a misconfigured policy raises ``PaperCapacityGateError``; an untrustworthy
    or over-capacity draft yields a ``REJECTED`` verdict with sorted reason codes. ``ADMITTED`` only
    when every check passes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)

_POLICY_SCHEMA_VERSION = "paper-capacity-gate-policy.v1"
_DECISION_SCHEMA_VERSION = "paper-capacity-gate-decision.v1"
_EXPECTED_DRAFT_SCHEMA_VERSION = "paper-allocator-intent-draft.v1"

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Non-negativity / positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling paper-sleeve modules (word-bounded). A bare ``order``/``orders``
# token is rejected while ``border``/``reorder`` are spared; market-data terms are scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector_ready|credential|"
    r"credentials|scheduler|shadow)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")

# Verdict reason codes (bare snake_case, stable, sorted in the decision). Error messages are prefixed.
_REASON_DRAFT_DIGEST_MISMATCH = "draft_digest_mismatch"
_REASON_DRAFT_MALFORMED = "draft_malformed"
_REASON_DRAFT_NOT_READY = "draft_not_ready"
_REASON_DRAFT_UNSAFE_FLAGS = "draft_unsafe_flags"
_REASON_DRAFT_SCOPE_VIOLATION = "draft_scope_violation"
_REASON_IDENTITY_MISMATCH = "identity_mismatch"
_REASON_OPEN_INTENTS_OVER_CAPACITY = "open_intents_over_capacity"
_REASON_NOTIONAL_OVER_CAPACITY = "notional_over_capacity"
_REASON_UNITS_OVER_CAPACITY = "units_over_capacity"

_DRAFT_DIGEST_FIELDS = (
    "readiness_digest",
    "promotion_readiness_journal_entry_digest",
    "promotion_readiness_payload_digest",
    "promotion_candidate_journal_entry_digest",
    "decision_journal_entry_digest",
    "decision_journal_payload_digest",
)


class PaperCapacityGateError(RuntimeError):
    """Raised when gate inputs are wrong-typed/malformed or the policy fails re-proof (misconfigured)."""


class PaperCapacityGateStatus(str, Enum):
    """Capacity-gate admissibility verdict. Never an execution permission / capital reservation."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperCapacityGatePolicy:
    """Deterministic, immutable paper capacity policy. Caps are admissibility bounds only. PAPER ONLY."""

    schema_version: str
    policy_id: str
    sleeve_id: str
    max_notional: str
    max_units: str
    max_open_intents: int
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperCapacityGateDecision:
    """Deterministic, immutable digest-bound capacity verdict over an allocator-intent draft. PAPER ONLY.

    ``ADMITTED`` is a consideration verdict, never an execution permission / capital reservation /
    order. The explicit negative attestations are always False.
    """

    schema_version: str
    status: PaperCapacityGateStatus
    draft_digest: str
    sleeve_id: str
    policy_id: str
    policy_digest: str
    max_notional: str
    max_units: str
    max_open_intents: int
    requested_notional: str
    requested_units: str
    eligible_count: int
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    execution_authorized: bool = False
    order_created: bool = False
    fill_created: bool = False
    position_mutated: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


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


def _require_positive_decimal(value: object, field: str) -> Decimal:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperCapacityGateError(f"paper_capacity_gate:policy_{field}_not_decimal_string")
    if not parsed > 0:
        raise PaperCapacityGateError(f"paper_capacity_gate:policy_{field}_not_positive")
    return parsed


def _require_nonneg_demand(value: object, field: str) -> Decimal:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperCapacityGateError(f"paper_capacity_gate:{field}_not_decimal_string")
    if parsed < 0:
        raise PaperCapacityGateError(f"paper_capacity_gate:{field}_negative")
    return parsed


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperCapacityGateError("paper_capacity_gate:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperCapacityGateError("paper_capacity_gate:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _is_metadata_tuple(metadata: object) -> bool:
    if not isinstance(metadata, tuple):
        return False
    for pair in metadata:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            return False
    return metadata == tuple(sorted(metadata))


def _is_blockers_tuple(blockers: object) -> bool:
    return (
        isinstance(blockers, tuple)
        and all(isinstance(blocker, str) for blocker in blockers)
        and blockers == _sorted_unique(blockers)
    )


def _draft_status_from_counts(
    eligible_count: int, blocked_count: int, insufficient_count: int
) -> PaperAllocatorIntentDraftStatus:
    if eligible_count > 0:
        return PaperAllocatorIntentDraftStatus.DRAFT_READY
    if blocked_count == 0 and insufficient_count > 0:
        return PaperAllocatorIntentDraftStatus.INSUFFICIENT_EVIDENCE
    return PaperAllocatorIntentDraftStatus.BLOCKED


def _safe_eligible_count(draft: PaperAllocatorIntentDraft) -> int:
    return draft.eligible_count if _is_int(draft.eligible_count) and draft.eligible_count >= 0 else 0


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _policy_payload(
    *,
    schema_version: str,
    policy_id: str,
    sleeve_id: str,
    max_notional: str,
    max_units: str,
    max_open_intents: int,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "policy_id": policy_id,
        "sleeve_id": sleeve_id,
        "max_notional": max_notional,
        "max_units": max_units,
        "max_open_intents": max_open_intents,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def build_paper_capacity_gate_policy(
    *,
    policy_id: str,
    sleeve_id: str,
    max_notional: str,
    max_units: str,
    max_open_intents: int,
    metadata: Mapping[str, str] | None = None,
) -> PaperCapacityGatePolicy:
    """Build a deterministic, immutable paper capacity policy with a canonical ``policy_digest``.

    ``policy_id``/``sleeve_id`` must be non-empty token-clean strings; ``max_notional``/``max_units``
    must be strict, strictly-positive decimal strings (no float/NaN/inf/scientific/whitespace/
    underscore/negative form); ``max_open_intents`` must be a strictly-positive ``int`` (not ``bool``);
    ``metadata`` (if given) a ``Mapping[str, str]``. A malformed id/cap/metadata or a forbidden
    BIST/live/order/scheduler/connector/shadow token raises ``PaperCapacityGateError``. The policy
    attests paper-safety (``paper_only`` True, real orders/money False) and admits/executes nothing —
    caps are admissibility bounds only.
    """
    if not _is_non_empty_string(policy_id):
        raise PaperCapacityGateError("paper_capacity_gate:policy_id_invalid")
    if not _is_non_empty_string(sleeve_id):
        raise PaperCapacityGateError("paper_capacity_gate:policy_sleeve_id_invalid")
    _require_positive_decimal(max_notional, "max_notional")
    _require_positive_decimal(max_units, "max_units")
    if not _is_int(max_open_intents) or not max_open_intents > 0:
        raise PaperCapacityGateError("paper_capacity_gate:policy_max_open_intents_not_positive_int")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(policy_id, sleeve_id, *_metadata_texts(metadata_pairs)):
        raise PaperCapacityGateError("paper_capacity_gate:policy_scope_violation")
    payload = _policy_payload(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        sleeve_id=sleeve_id,
        max_notional=max_notional,
        max_units=max_units,
        max_open_intents=max_open_intents,
        metadata=metadata_pairs,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperCapacityGatePolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        sleeve_id=sleeve_id,
        max_notional=max_notional,
        max_units=max_units,
        max_open_intents=max_open_intents,
        metadata=metadata_pairs,
        policy_digest=_canonical_digest(payload),
    )


def _reprove_policy(policy: PaperCapacityGatePolicy) -> tuple[Decimal, Decimal, int]:
    """Re-prove a policy's paper-safety, ids, positive caps, scope, and digest (never trusting the digest)."""
    if not isinstance(policy, PaperCapacityGatePolicy):
        raise PaperCapacityGateError("paper_capacity_gate:policy_malformed")
    if policy.paper_only is not True:
        raise PaperCapacityGateError("paper_capacity_gate:policy_not_paper_only")
    if policy.real_orders_enabled is not False:
        raise PaperCapacityGateError("paper_capacity_gate:policy_real_orders_enabled")
    if policy.real_money_enabled is not False:
        raise PaperCapacityGateError("paper_capacity_gate:policy_real_money_enabled")
    if not _is_non_empty_string(policy.policy_id):
        raise PaperCapacityGateError("paper_capacity_gate:policy_id_invalid")
    if not _is_non_empty_string(policy.sleeve_id):
        raise PaperCapacityGateError("paper_capacity_gate:policy_sleeve_id_invalid")
    max_notional = _require_positive_decimal(policy.max_notional, "max_notional")
    max_units = _require_positive_decimal(policy.max_units, "max_units")
    if not _is_int(policy.max_open_intents) or not policy.max_open_intents > 0:
        raise PaperCapacityGateError("paper_capacity_gate:policy_max_open_intents_not_positive_int")
    if _has_scope_violation(policy.policy_id, policy.sleeve_id, *_metadata_texts(policy.metadata)):
        raise PaperCapacityGateError("paper_capacity_gate:policy_scope_violation")
    if paper_capacity_gate_policy_digest(policy) != policy.policy_digest:
        raise PaperCapacityGateError("paper_capacity_gate:policy_digest_mismatch")
    return max_notional, max_units, policy.max_open_intents


def _draft_is_paper_safe(draft: PaperAllocatorIntentDraft) -> bool:
    return (
        draft.paper_only is True
        and draft.real_orders_enabled is False
        and draft.real_money_enabled is False
        and draft.capital_reserved is False
        and draft.execution_authorized is False
        and draft.order_created is False
        and draft.fill_created is False
        and draft.position_mutated is False
    )


def _draft_structural_reasons(draft: PaperAllocatorIntentDraft) -> tuple[str, ...]:
    malformed = False
    if draft.schema_version != _EXPECTED_DRAFT_SCHEMA_VERSION:
        malformed = True
    if not isinstance(draft.status, PaperAllocatorIntentDraftStatus):
        malformed = True
    if not _is_non_empty_string(draft.sleeve_id) or not _is_non_empty_string(draft.policy_id):
        malformed = True
    if not _is_non_empty_string(draft.correlation_id):
        malformed = True
    if any(not _is_hex64_string(getattr(draft, field, None)) for field in _DRAFT_DIGEST_FIELDS):
        malformed = True

    counts_are_valid = (
        _is_int(draft.eligible_count)
        and draft.eligible_count >= 0
        and _is_int(draft.blocked_count)
        and draft.blocked_count >= 0
        and _is_int(draft.insufficient_count)
        and draft.insufficient_count >= 0
    )
    if not counts_are_valid:
        malformed = True
    blockers_are_valid = _is_blockers_tuple(draft.blockers)
    if not blockers_are_valid:
        malformed = True
    if not _is_metadata_tuple(draft.metadata):
        malformed = True
    if counts_are_valid and isinstance(draft.status, PaperAllocatorIntentDraftStatus):
        expected_status = _draft_status_from_counts(draft.eligible_count, draft.blocked_count, draft.insufficient_count)
        if draft.status is not expected_status:
            malformed = True
    if (
        counts_are_valid
        and blockers_are_valid
        and draft.blocked_count == 0
        and draft.insufficient_count == 0
        and len(draft.blockers) != 0
    ):
        malformed = True
    return (_REASON_DRAFT_MALFORMED,) if malformed else ()


def evaluate_paper_capacity_gate(
    draft: PaperAllocatorIntentDraft,
    policy: PaperCapacityGatePolicy,
    *,
    requested_notional: str,
    requested_units: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperCapacityGateDecision:
    """Render a deterministic, digest-bound paper capacity verdict over an allocator-intent draft.

    The ``policy`` is re-proven (paper-safety + positive caps + scope + digest) and the gate-level
    ``correlation_id``/``metadata`` and prospective ``requested_notional``/``requested_units`` demand
    are validated; any of these being wrong-typed/malformed/misconfigured raises
    ``PaperCapacityGateError``. The ``draft`` is then judged (never mutated): its ``draft_digest`` is
    recomputed via the public ``paper_allocator_intent_draft_digest`` (mismatch -> ``REJECTED``), and a
    digest-valid draft is checked for ``DRAFT_READY`` status, the paper-safety/negative-attestation
    triple+, identity binding to the policy, scope cleanliness, and the three capacity bounds
    (``eligible_count`` vs ``max_open_intents``; prospective notional/units vs ``max_notional``/
    ``max_units``). Returns ``ADMITTED`` only when every check passes, else ``REJECTED`` with sorted
    reason codes. Reserves no capital, allocates nothing, routes/fills no order, opens no position,
    computes no PnL, and appends to no journal.
    """
    if not isinstance(draft, PaperAllocatorIntentDraft):
        raise PaperCapacityGateError("paper_capacity_gate:draft_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperCapacityGateError("paper_capacity_gate:correlation_id_invalid")
    decision_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(correlation_id, *_metadata_texts(decision_metadata)):
        raise PaperCapacityGateError("paper_capacity_gate:scope_violation")

    requested_notional_dec = _require_nonneg_demand(requested_notional, "requested_notional")
    requested_units_dec = _require_nonneg_demand(requested_units, "requested_units")

    max_notional, max_units, max_open_intents = _reprove_policy(policy)

    # Digest boundary: recompute the upstream draft self-digest via its PUBLIC serializer. A malformed
    # draft (non-serializable / non-enum status) surfaces as a clean error, never a raw AttributeError.
    try:
        expected_draft_digest = paper_allocator_intent_draft_digest(draft)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed gate error; BaseException not caught
        raise PaperCapacityGateError("paper_capacity_gate:draft_malformed") from exc

    reasons: list[str] = []
    if not isinstance(draft.draft_digest, str) or draft.draft_digest != expected_draft_digest:
        # The draft's self-digest is the trust anchor; if it does not re-prove, nothing else is trusted.
        return _finalize_decision(
            status=PaperCapacityGateStatus.REJECTED,
            draft_digest=draft.draft_digest if isinstance(draft.draft_digest, str) else "",
            policy=policy,
            requested_notional=_render_decimal(requested_notional_dec),
            requested_units=_render_decimal(requested_units_dec),
            eligible_count=_safe_eligible_count(draft),
            reasons=(_REASON_DRAFT_DIGEST_MISMATCH,),
            correlation_id=correlation_id,
            metadata=decision_metadata,
        )

    # Digest re-proved -> re-prove the digest-carrying draft's canonical structure before judging it.
    structural_reasons = _draft_structural_reasons(draft)
    reasons.extend(structural_reasons)
    draft_malformed = _REASON_DRAFT_MALFORMED in structural_reasons
    if draft.status is not PaperAllocatorIntentDraftStatus.DRAFT_READY:
        reasons.append(_REASON_DRAFT_NOT_READY)
    if not _draft_is_paper_safe(draft):
        reasons.append(_REASON_DRAFT_UNSAFE_FLAGS)
    if not draft_malformed and _has_scope_violation(
        draft.sleeve_id,
        draft.policy_id,
        draft.correlation_id,
        *_metadata_texts(draft.metadata),
        *draft.blockers,
    ):
        reasons.append(_REASON_DRAFT_SCOPE_VIOLATION)
    if draft.sleeve_id != policy.sleeve_id or draft.policy_id != policy.policy_id:
        reasons.append(_REASON_IDENTITY_MISMATCH)
    if not draft_malformed and draft.eligible_count > max_open_intents:
        reasons.append(_REASON_OPEN_INTENTS_OVER_CAPACITY)
    if requested_notional_dec > max_notional:
        reasons.append(_REASON_NOTIONAL_OVER_CAPACITY)
    if requested_units_dec > max_units:
        reasons.append(_REASON_UNITS_OVER_CAPACITY)

    status = PaperCapacityGateStatus.REJECTED if reasons else PaperCapacityGateStatus.ADMITTED
    return _finalize_decision(
        status=status,
        draft_digest=draft.draft_digest,
        policy=policy,
        requested_notional=_render_decimal(requested_notional_dec),
        requested_units=_render_decimal(requested_units_dec),
        eligible_count=_safe_eligible_count(draft),
        reasons=tuple(reasons),
        correlation_id=correlation_id,
        metadata=decision_metadata,
    )


def _finalize_decision(
    *,
    status: PaperCapacityGateStatus,
    draft_digest: str,
    policy: PaperCapacityGatePolicy,
    requested_notional: str,
    requested_units: str,
    eligible_count: int,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperCapacityGateDecision:
    reason_codes = _sorted_unique(reasons)
    decision = PaperCapacityGateDecision(
        schema_version=_DECISION_SCHEMA_VERSION,
        status=status,
        draft_digest=draft_digest,
        sleeve_id=policy.sleeve_id,
        policy_id=policy.policy_id,
        policy_digest=policy.policy_digest,
        max_notional=policy.max_notional,
        max_units=policy.max_units,
        max_open_intents=policy.max_open_intents,
        requested_notional=requested_notional,
        requested_units=requested_units,
        eligible_count=eligible_count,
        reason_codes=reason_codes,
        correlation_id=correlation_id,
        metadata=metadata,
        decision_digest="",
    )
    object_digest = paper_capacity_gate_decision_digest(decision)
    return PaperCapacityGateDecision(
        schema_version=decision.schema_version,
        status=decision.status,
        draft_digest=decision.draft_digest,
        sleeve_id=decision.sleeve_id,
        policy_id=decision.policy_id,
        policy_digest=decision.policy_digest,
        max_notional=decision.max_notional,
        max_units=decision.max_units,
        max_open_intents=decision.max_open_intents,
        requested_notional=decision.requested_notional,
        requested_units=decision.requested_units,
        eligible_count=decision.eligible_count,
        reason_codes=decision.reason_codes,
        correlation_id=decision.correlation_id,
        metadata=decision.metadata,
        decision_digest=object_digest,
    )


def paper_capacity_gate_policy_to_dict(policy: PaperCapacityGatePolicy) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a capacity policy (deterministic shape, includes self-digest)."""
    payload = _policy_payload(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        sleeve_id=policy.sleeve_id,
        max_notional=policy.max_notional,
        max_units=policy.max_units,
        max_open_intents=policy.max_open_intents,
        metadata=policy.metadata,
        paper_only=policy.paper_only,
        real_orders_enabled=policy.real_orders_enabled,
        real_money_enabled=policy.real_money_enabled,
    )
    payload["policy_digest"] = policy.policy_digest
    return payload


def paper_capacity_gate_policy_digest(policy: PaperCapacityGatePolicy) -> str:
    """Recompute the canonical policy digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _policy_payload(
            schema_version=policy.schema_version,
            policy_id=policy.policy_id,
            sleeve_id=policy.sleeve_id,
            max_notional=policy.max_notional,
            max_units=policy.max_units,
            max_open_intents=policy.max_open_intents,
            metadata=policy.metadata,
            paper_only=policy.paper_only,
            real_orders_enabled=policy.real_orders_enabled,
            real_money_enabled=policy.real_money_enabled,
        )
    )


def _decision_payload(
    *,
    schema_version: str,
    status_value: str,
    draft_digest: str,
    sleeve_id: str,
    policy_id: str,
    policy_digest: str,
    max_notional: str,
    max_units: str,
    max_open_intents: int,
    requested_notional: str,
    requested_units: str,
    eligible_count: int,
    reason_codes: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
    capital_reserved: bool,
    execution_authorized: bool,
    order_created: bool,
    fill_created: bool,
    position_mutated: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "draft_digest": draft_digest,
        "sleeve_id": sleeve_id,
        "policy_id": policy_id,
        "policy_digest": policy_digest,
        "max_notional": max_notional,
        "max_units": max_units,
        "max_open_intents": max_open_intents,
        "requested_notional": requested_notional,
        "requested_units": requested_units,
        "eligible_count": eligible_count,
        "reason_codes": list(reason_codes),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
        "capital_reserved": capital_reserved,
        "execution_authorized": execution_authorized,
        "order_created": order_created,
        "fill_created": fill_created,
        "position_mutated": position_mutated,
    }


def paper_capacity_gate_decision_to_dict(decision: PaperCapacityGateDecision) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a capacity decision (deterministic shape, includes self-digest)."""
    payload = _decision_payload(
        schema_version=decision.schema_version,
        status_value=decision.status.value,
        draft_digest=decision.draft_digest,
        sleeve_id=decision.sleeve_id,
        policy_id=decision.policy_id,
        policy_digest=decision.policy_digest,
        max_notional=decision.max_notional,
        max_units=decision.max_units,
        max_open_intents=decision.max_open_intents,
        requested_notional=decision.requested_notional,
        requested_units=decision.requested_units,
        eligible_count=decision.eligible_count,
        reason_codes=decision.reason_codes,
        correlation_id=decision.correlation_id,
        metadata=decision.metadata,
        paper_only=decision.paper_only,
        real_orders_enabled=decision.real_orders_enabled,
        real_money_enabled=decision.real_money_enabled,
        capital_reserved=decision.capital_reserved,
        execution_authorized=decision.execution_authorized,
        order_created=decision.order_created,
        fill_created=decision.fill_created,
        position_mutated=decision.position_mutated,
    )
    payload["decision_digest"] = decision.decision_digest
    return payload


def paper_capacity_gate_decision_digest(decision: PaperCapacityGateDecision) -> str:
    """Recompute the canonical decision digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _decision_payload(
            schema_version=decision.schema_version,
            status_value=decision.status.value,
            draft_digest=decision.draft_digest,
            sleeve_id=decision.sleeve_id,
            policy_id=decision.policy_id,
            policy_digest=decision.policy_digest,
            max_notional=decision.max_notional,
            max_units=decision.max_units,
            max_open_intents=decision.max_open_intents,
            requested_notional=decision.requested_notional,
            requested_units=decision.requested_units,
            eligible_count=decision.eligible_count,
            reason_codes=decision.reason_codes,
            correlation_id=decision.correlation_id,
            metadata=decision.metadata,
            paper_only=decision.paper_only,
            real_orders_enabled=decision.real_orders_enabled,
            real_money_enabled=decision.real_money_enabled,
            capital_reserved=decision.capital_reserved,
            execution_authorized=decision.execution_authorized,
            order_created=decision.order_created,
            fill_created=decision.fill_created,
            position_mutated=decision.position_mutated,
        )
    )


__all__ = [
    "PaperCapacityGateDecision",
    "PaperCapacityGateError",
    "PaperCapacityGatePolicy",
    "PaperCapacityGateStatus",
    "build_paper_capacity_gate_policy",
    "evaluate_paper_capacity_gate",
    "paper_capacity_gate_decision_digest",
    "paper_capacity_gate_decision_to_dict",
    "paper_capacity_gate_policy_digest",
    "paper_capacity_gate_policy_to_dict",
]
