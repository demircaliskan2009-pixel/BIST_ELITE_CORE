"""Paper order-intent admission — deterministic, paper-only admission verdict over a capacity decision.

A small, immutable, fail-closed *admission gate* that consumes an ``ADMITTED``
``PaperCapacityGateDecision`` and a typed prospective ``PaperOrderIntentRequest`` and renders a
digest-bound ``ADMITTED`` / ``REJECTED`` verdict answering one question: "given this admitted capacity
verdict, is this prospective paper order-intent request admissible to be *constructed later* as an
inert paper order intent?" It is **only** an admission verdict — an inert contract. It does **not**
route an order, create a venue/exchange/client order id, call live/private APIs, create fills, mutate
positions, compute PnL, or reserve/mutate capital — no DB/file/network/env IO, no wall-clock, no
random, no threading, no connector/scheduler/runtime/venue/execution/service/session/portfolio
surface, no Deribit, no BIST. ``ADMITTED`` is a *consideration* verdict, never an execution
permission.

Binding model:
  - The request carries the ``capacity_decision_digest`` it was built against; admission requires it
    to equal the supplied decision's recomputed ``decision_digest`` (no cross-decision reuse).
  - The capacity gate already judged prospective ``requested_notional`` / ``requested_units`` demand;
    admission requires the request's demand to **match** that admitted demand exactly (fail-closed on
    any mismatch). This PR does not redesign the capacity gate.

Design rules:
  - Re-prove before judging: the capacity ``decision`` is re-proven via the PUBLIC
    ``paper_capacity_gate_decision_digest`` (mismatch -> ``REJECTED``); a digest-valid decision is then
    structurally re-proven (schema, ``ADMITTED`` status, paper-safety triple + negative attestations,
    ``ADMITTED`` ⟹ empty reason codes, well-formed ids/digests/decimals) — a self-consistent forged
    decision still fails on those fields. The ``request`` is re-proven via the PUBLIC
    ``paper_order_intent_request_digest`` (mismatch -> ``REJECTED``) and structurally re-proven. A
    caller-supplied digest is never trusted.
  - Deterministic numeric discipline: demand and ``limit_price`` are exact decimal *strings* (no
    float, no NaN/inf, no scientific/whitespace/underscore form, no negatives); ``decimal.Decimal`` is
    used only for exact comparison and canonical plain-string rendering (never scientific).
  - Deterministic digest: canonical SHA-256 over the public serializer output (enum ``.value`` and
    stable ordering) excluding the self-digest. Frozen dataclasses; stable sorted reason codes; no
    input is mutated.
  - Fail closed: a wrong-typed input, an invalid/forbidden ``correlation_id``/metadata, or a malformed
    request at construction raises ``PaperOrderIntentAdmissionError``; an untrustworthy / non-admitted
    / mismatched / malformed input to the gate yields a ``REJECTED`` verdict with sorted reason codes.
    ``ADMITTED`` only when every check passes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_capacity_gate import (
    PaperCapacityGateDecision,
    PaperCapacityGateStatus,
    paper_capacity_gate_decision_digest,
)

_REQUEST_SCHEMA_VERSION = "paper-order-intent-request.v1"
_DECISION_SCHEMA_VERSION = "paper-order-intent-admission-decision.v1"
_EXPECTED_CAPACITY_SCHEMA_VERSION = "paper-capacity-gate-decision.v1"

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling paper-sleeve / capacity-gate modules (word-bounded). A bare
# ``order``/``orders`` token is rejected while ``border``/``reorder`` are spared; market-data terms
# are scrubbed before the scan.
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
_REASON_CAPACITY_DIGEST_MISMATCH = "capacity_decision_digest_mismatch"
_REASON_CAPACITY_MALFORMED = "capacity_decision_malformed"
_REASON_CAPACITY_NOT_ADMITTED = "capacity_not_admitted"
_REASON_CAPACITY_UNSAFE_FLAGS = "capacity_unsafe_flags"
_REASON_REQUEST_DIGEST_MISMATCH = "request_digest_mismatch"
_REASON_REQUEST_MALFORMED = "request_malformed"
_REASON_CAPACITY_BINDING_MISMATCH = "capacity_binding_mismatch"
_REASON_DEMAND_MISMATCH = "demand_mismatch"
_REASON_REQUEST_UNSAFE_FLAGS = "request_unsafe_flags"


class PaperOrderIntentAdmissionError(RuntimeError):
    """Raised when admission inputs are wrong-typed/malformed at construction or invocation (fail-closed)."""


class PaperOrderIntentAdmissionStatus(str, Enum):
    """Order-intent admission verdict. Never an execution permission / order routing / capital action."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


class PaperOrderSide(str, Enum):
    """Prospective paper order side. Descriptor only — never routed."""

    BUY = "BUY"
    SELL = "SELL"


class PaperOrderIntentType(str, Enum):
    """Prospective paper order-intent type. Descriptor only — never routed."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class PaperOrderIntentRequest:
    """Deterministic, immutable prospective paper order-intent demand. Inert descriptor. PAPER ONLY.

    Carries the ``capacity_decision_digest`` it was built against and the demand the capacity gate
    already judged. Never an order, never routed, never a venue/exchange/client order id.
    """

    schema_version: str
    request_id: str
    capacity_decision_digest: str
    market_symbol: str
    side: PaperOrderSide
    intent_type: PaperOrderIntentType
    requested_notional: str
    requested_units: str
    limit_price: str | None
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    request_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperOrderIntentAdmissionDecision:
    """Deterministic, immutable digest-bound order-intent admission verdict. Inert. PAPER ONLY.

    ``ADMITTED`` is a consideration verdict, never an execution permission / order routing / venue
    order id / fill / PnL / position / capital action. The explicit negative attestations are always
    False.
    """

    schema_version: str
    status: PaperOrderIntentAdmissionStatus
    request_digest: str
    capacity_decision_digest: str
    market_symbol: str
    side: str
    intent_type: str
    requested_notional: str
    requested_units: str
    limit_price: str | None
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    execution_authorized: bool = False
    fill_created: bool = False
    pnl_computed: bool = False
    position_mutated: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    connector_invoked: bool = False


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


def _require_positive_decimal_str(value: object, field: str) -> str:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperOrderIntentAdmissionError(f"paper_order_intent_admission:{field}_not_decimal_string")
    if not parsed > 0:
        raise PaperOrderIntentAdmissionError(f"paper_order_intent_admission:{field}_not_positive")
    return _render_decimal(parsed)


def _is_positive_decimal(value: object) -> bool:
    parsed = _parse_decimal(value)
    return parsed is not None and parsed > 0


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperOrderIntentAdmissionError("paper_order_intent_admission:metadata_malformed")
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


def _request_payload(
    *,
    schema_version: str,
    request_id: str,
    capacity_decision_digest: str,
    market_symbol: str,
    side_value: str,
    intent_type_value: str,
    requested_notional: str,
    requested_units: str,
    limit_price: str | None,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "request_id": request_id,
        "capacity_decision_digest": capacity_decision_digest,
        "market_symbol": market_symbol,
        "side": side_value,
        "intent_type": intent_type_value,
        "requested_notional": requested_notional,
        "requested_units": requested_units,
        "limit_price": limit_price,
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def build_paper_order_intent_request(
    *,
    request_id: str,
    capacity_decision_digest: str,
    market_symbol: str,
    side: PaperOrderSide,
    intent_type: PaperOrderIntentType,
    requested_notional: str,
    requested_units: str,
    limit_price: str | None = None,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperOrderIntentRequest:
    """Build a deterministic, immutable prospective paper order-intent request with a ``request_digest``.

    ``request_id``/``correlation_id`` must be non-empty token-clean strings; ``capacity_decision_digest``
    a 64-hex string; ``market_symbol`` a non-empty token-clean string; ``side``/``intent_type`` the
    typed enums; ``requested_notional``/``requested_units`` strict, strictly-positive decimal strings.
    ``limit_price`` must be a strict, strictly-positive decimal string for ``LIMIT`` and ``None`` for
    ``MARKET`` (a market intent carrying a limit price fails closed). A malformed/invalid field or a
    forbidden BIST/live/order/scheduler/connector/shadow token raises ``PaperOrderIntentAdmissionError``.
    The request attests paper-safety and is an inert demand descriptor — never an order, never routed.
    """
    if not _is_non_empty_string(request_id):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:request_id_invalid")
    if not _is_hex64_string(capacity_decision_digest):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:capacity_decision_digest_invalid")
    if not _is_non_empty_string(market_symbol):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:market_symbol_invalid")
    if not isinstance(side, PaperOrderSide):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:side_invalid")
    if not isinstance(intent_type, PaperOrderIntentType):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:intent_type_invalid")
    notional = _require_positive_decimal_str(requested_notional, "requested_notional")
    units = _require_positive_decimal_str(requested_units, "requested_units")
    if intent_type is PaperOrderIntentType.LIMIT:
        normalized_limit_price: str | None = _require_positive_decimal_str(limit_price, "limit_price")
    else:
        if limit_price is not None:
            raise PaperOrderIntentAdmissionError("paper_order_intent_admission:market_intent_with_limit_price")
        normalized_limit_price = None
    if not _is_non_empty_string(correlation_id):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(request_id, market_symbol, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:request_scope_violation")
    payload = _request_payload(
        schema_version=_REQUEST_SCHEMA_VERSION,
        request_id=request_id,
        capacity_decision_digest=capacity_decision_digest,
        market_symbol=market_symbol,
        side_value=side.value,
        intent_type_value=intent_type.value,
        requested_notional=notional,
        requested_units=units,
        limit_price=normalized_limit_price,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperOrderIntentRequest(
        schema_version=_REQUEST_SCHEMA_VERSION,
        request_id=request_id,
        capacity_decision_digest=capacity_decision_digest,
        market_symbol=market_symbol,
        side=side,
        intent_type=intent_type,
        requested_notional=notional,
        requested_units=units,
        limit_price=normalized_limit_price,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        request_digest=_canonical_digest(payload),
    )


def paper_order_intent_request_to_dict(request: PaperOrderIntentRequest) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an order-intent request (deterministic shape, includes self-digest)."""
    payload = _request_payload(
        schema_version=request.schema_version,
        request_id=request.request_id,
        capacity_decision_digest=request.capacity_decision_digest,
        market_symbol=request.market_symbol,
        side_value=request.side.value,
        intent_type_value=request.intent_type.value,
        requested_notional=request.requested_notional,
        requested_units=request.requested_units,
        limit_price=request.limit_price,
        correlation_id=request.correlation_id,
        metadata=request.metadata,
        paper_only=request.paper_only,
        real_orders_enabled=request.real_orders_enabled,
        real_money_enabled=request.real_money_enabled,
    )
    payload["request_digest"] = request.request_digest
    return payload


def paper_order_intent_request_digest(request: PaperOrderIntentRequest) -> str:
    """Recompute the canonical request digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _request_payload(
            schema_version=request.schema_version,
            request_id=request.request_id,
            capacity_decision_digest=request.capacity_decision_digest,
            market_symbol=request.market_symbol,
            side_value=request.side.value if isinstance(request.side, PaperOrderSide) else request.side,
            intent_type_value=(
                request.intent_type.value
                if isinstance(request.intent_type, PaperOrderIntentType)
                else request.intent_type
            ),
            requested_notional=request.requested_notional,
            requested_units=request.requested_units,
            limit_price=request.limit_price,
            correlation_id=request.correlation_id,
            metadata=request.metadata,
            paper_only=request.paper_only,
            real_orders_enabled=request.real_orders_enabled,
            real_money_enabled=request.real_money_enabled,
        )
    )


def _capacity_is_paper_safe(decision: PaperCapacityGateDecision) -> bool:
    return (
        decision.paper_only is True
        and decision.real_orders_enabled is False
        and decision.real_money_enabled is False
        and decision.capital_reserved is False
        and decision.execution_authorized is False
        and decision.order_created is False
        and decision.fill_created is False
        and decision.position_mutated is False
    )


def _capacity_structural_reasons(decision: PaperCapacityGateDecision) -> tuple[str, ...]:
    """Re-prove a digest-valid capacity decision's canonical structure (self-consistent forge guard)."""
    malformed = False
    if decision.schema_version != _EXPECTED_CAPACITY_SCHEMA_VERSION:
        malformed = True
    if not isinstance(decision.status, PaperCapacityGateStatus):
        malformed = True
    if not _is_non_empty_string(decision.sleeve_id) or not _is_non_empty_string(decision.policy_id):
        malformed = True
    if not _is_non_empty_string(decision.correlation_id):
        malformed = True
    if not _is_hex64_string(decision.draft_digest) or not _is_hex64_string(decision.policy_digest):
        malformed = True
    if not _is_positive_decimal(decision.max_notional) or not _is_positive_decimal(decision.max_units):
        malformed = True
    if _parse_decimal(decision.requested_notional) is None or _parse_decimal(decision.requested_units) is None:
        malformed = True
    if not _is_int(decision.eligible_count) or decision.eligible_count < 0:
        malformed = True
    if not _is_int(decision.max_open_intents) or decision.max_open_intents <= 0:
        malformed = True
    if not isinstance(decision.reason_codes, tuple) or decision.reason_codes != _sorted_unique(decision.reason_codes):
        malformed = True
    metadata_is_canonical = _is_metadata_tuple(decision.metadata)
    if not metadata_is_canonical:
        malformed = True
    if _has_scope_violation(
        decision.sleeve_id,
        decision.policy_id,
        decision.correlation_id,
        *(_metadata_texts(decision.metadata) if metadata_is_canonical else ()),
    ):
        malformed = True
    # ADMITTED must carry no reason codes; a forged "ADMITTED + reasons" decision is inconsistent.
    if (
        isinstance(decision.status, PaperCapacityGateStatus)
        and decision.status is PaperCapacityGateStatus.ADMITTED
        and isinstance(decision.reason_codes, tuple)
        and len(decision.reason_codes) != 0
    ):
        malformed = True
    # An ADMITTED capacity decision must satisfy its own embedded caps: the capacity gate only emits
    # ADMITTED when demand <= caps and eligible_count <= max_open_intents. A forged self-consistent
    # ADMITTED decision with demand above its embedded caps would bypass the very limit this consumer
    # enforces, so re-prove the cap invariant fail-closed (exact Decimal comparison, no rounding path).
    if isinstance(decision.status, PaperCapacityGateStatus) and decision.status is PaperCapacityGateStatus.ADMITTED:
        admitted_max_notional = _parse_decimal(decision.max_notional)
        admitted_max_units = _parse_decimal(decision.max_units)
        admitted_requested_notional = _parse_decimal(decision.requested_notional)
        admitted_requested_units = _parse_decimal(decision.requested_units)
        if None in (
            admitted_max_notional,
            admitted_max_units,
            admitted_requested_notional,
            admitted_requested_units,
        ):
            malformed = True
        elif admitted_requested_notional > admitted_max_notional or admitted_requested_units > admitted_max_units:
            malformed = True
        if not (_is_int(decision.eligible_count) and _is_int(decision.max_open_intents)):
            malformed = True
        elif decision.eligible_count > decision.max_open_intents:
            malformed = True
    return (_REASON_CAPACITY_MALFORMED,) if malformed else ()


def _request_structural_reasons(request: PaperOrderIntentRequest) -> tuple[str, ...]:
    """Re-prove a digest-valid request's canonical structure (self-consistent forge guard)."""
    malformed = False
    if request.schema_version != _REQUEST_SCHEMA_VERSION:
        malformed = True
    if not _is_non_empty_string(request.request_id):
        malformed = True
    if not _is_hex64_string(request.capacity_decision_digest):
        malformed = True
    if not _is_non_empty_string(request.market_symbol):
        malformed = True
    if not isinstance(request.side, PaperOrderSide):
        malformed = True
    if not isinstance(request.intent_type, PaperOrderIntentType):
        malformed = True
    if not _is_positive_decimal(request.requested_notional) or not _is_positive_decimal(request.requested_units):
        malformed = True
    if isinstance(request.intent_type, PaperOrderIntentType):
        if request.intent_type is PaperOrderIntentType.LIMIT and not _is_positive_decimal(request.limit_price):
            malformed = True
        if request.intent_type is PaperOrderIntentType.MARKET and request.limit_price is not None:
            malformed = True
    if not _is_non_empty_string(request.correlation_id):
        malformed = True
    if not _is_metadata_tuple(request.metadata):
        malformed = True
    if _has_scope_violation(
        request.request_id,
        request.market_symbol,
        request.correlation_id,
        *(_metadata_texts(request.metadata) if _is_metadata_tuple(request.metadata) else ()),
    ):
        malformed = True
    return (_REASON_REQUEST_MALFORMED,) if malformed else ()


def _request_is_paper_safe(request: PaperOrderIntentRequest) -> bool:
    return request.paper_only is True and request.real_orders_enabled is False and request.real_money_enabled is False


def _demand_matches(request: PaperOrderIntentRequest, decision: PaperCapacityGateDecision) -> bool:
    request_notional = _parse_decimal(request.requested_notional)
    request_units = _parse_decimal(request.requested_units)
    decision_notional = _parse_decimal(decision.requested_notional)
    decision_units = _parse_decimal(decision.requested_units)
    if None in (request_notional, request_units, decision_notional, decision_units):
        return False
    return request_notional == decision_notional and request_units == decision_units


def evaluate_paper_order_intent_admission(
    capacity_decision: PaperCapacityGateDecision,
    request: PaperOrderIntentRequest,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperOrderIntentAdmissionDecision:
    """Render a deterministic, digest-bound paper order-intent admission verdict.

    The gate-level ``correlation_id``/``metadata`` are validated (wrong-typed/forbidden -> raise). The
    ``capacity_decision`` and ``request`` digests are recomputed via their PUBLIC helpers (mismatch ->
    ``REJECTED``); digest-valid inputs are structurally re-proven, and the gate requires the capacity
    decision to be ``ADMITTED`` + paper-safe, the request to bind to this decision's digest, and the
    request demand to match the admitted demand. Returns ``ADMITTED`` only when every check passes,
    else ``REJECTED`` with sorted reason codes. Never mutates inputs; routes no order; creates no
    venue/order id, fill, PnL, or position; reserves no capital; calls no live API.
    """
    if not isinstance(capacity_decision, PaperCapacityGateDecision):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:capacity_decision_malformed")
    if not isinstance(request, PaperOrderIntentRequest):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:request_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:correlation_id_invalid")
    decision_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(correlation_id, *_metadata_texts(decision_metadata)):
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:scope_violation")

    # Digest boundary 1: the capacity decision's self-digest is a trust anchor.
    try:
        expected_capacity_digest = paper_capacity_gate_decision_digest(capacity_decision)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed gate error; BaseException not caught
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:capacity_decision_malformed") from exc
    if not isinstance(capacity_decision.decision_digest, str) or capacity_decision.decision_digest != (
        expected_capacity_digest
    ):
        return _finalize_decision(
            status=PaperOrderIntentAdmissionStatus.REJECTED,
            request=request,
            reasons=(_REASON_CAPACITY_DIGEST_MISMATCH,),
            correlation_id=correlation_id,
            metadata=decision_metadata,
        )

    # Digest boundary 2: the request's self-digest is a trust anchor.
    try:
        expected_request_digest = paper_order_intent_request_digest(request)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed gate error; BaseException not caught
        raise PaperOrderIntentAdmissionError("paper_order_intent_admission:request_malformed") from exc
    if not isinstance(request.request_digest, str) or request.request_digest != expected_request_digest:
        return _finalize_decision(
            status=PaperOrderIntentAdmissionStatus.REJECTED,
            request=request,
            reasons=(_REASON_REQUEST_DIGEST_MISMATCH,),
            correlation_id=correlation_id,
            metadata=decision_metadata,
        )

    # Both digests re-proved -> re-prove canonical structure and admission invariants.
    reasons: list[str] = []
    reasons.extend(_capacity_structural_reasons(capacity_decision))
    if capacity_decision.status is not PaperCapacityGateStatus.ADMITTED:
        reasons.append(_REASON_CAPACITY_NOT_ADMITTED)
    if not _capacity_is_paper_safe(capacity_decision):
        reasons.append(_REASON_CAPACITY_UNSAFE_FLAGS)

    reasons.extend(_request_structural_reasons(request))
    if not _request_is_paper_safe(request):
        reasons.append(_REASON_REQUEST_UNSAFE_FLAGS)
    if request.capacity_decision_digest != capacity_decision.decision_digest:
        reasons.append(_REASON_CAPACITY_BINDING_MISMATCH)
    if not _demand_matches(request, capacity_decision):
        reasons.append(_REASON_DEMAND_MISMATCH)

    status = PaperOrderIntentAdmissionStatus.REJECTED if reasons else PaperOrderIntentAdmissionStatus.ADMITTED
    return _finalize_decision(
        status=status,
        request=request,
        reasons=tuple(reasons),
        correlation_id=correlation_id,
        metadata=decision_metadata,
    )


def _finalize_decision(
    *,
    status: PaperOrderIntentAdmissionStatus,
    request: PaperOrderIntentRequest,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperOrderIntentAdmissionDecision:
    reason_codes = _sorted_unique(reasons)
    side_value = request.side.value if isinstance(request.side, PaperOrderSide) else str(request.side)
    intent_type_value = (
        request.intent_type.value if isinstance(request.intent_type, PaperOrderIntentType) else str(request.intent_type)
    )
    request_digest = request.request_digest if isinstance(request.request_digest, str) else ""
    capacity_decision_digest = (
        request.capacity_decision_digest if isinstance(request.capacity_decision_digest, str) else ""
    )
    market_symbol = request.market_symbol if isinstance(request.market_symbol, str) else ""
    requested_notional = request.requested_notional if isinstance(request.requested_notional, str) else ""
    requested_units = request.requested_units if isinstance(request.requested_units, str) else ""
    limit_price = request.limit_price if (request.limit_price is None or isinstance(request.limit_price, str)) else ""
    decision = PaperOrderIntentAdmissionDecision(
        schema_version=_DECISION_SCHEMA_VERSION,
        status=status,
        request_digest=request_digest,
        capacity_decision_digest=capacity_decision_digest,
        market_symbol=market_symbol,
        side=side_value,
        intent_type=intent_type_value,
        requested_notional=requested_notional,
        requested_units=requested_units,
        limit_price=limit_price,
        reason_codes=reason_codes,
        correlation_id=correlation_id,
        metadata=metadata,
        decision_digest="",
    )
    object_digest = paper_order_intent_admission_decision_digest(decision)
    return PaperOrderIntentAdmissionDecision(
        schema_version=decision.schema_version,
        status=decision.status,
        request_digest=decision.request_digest,
        capacity_decision_digest=decision.capacity_decision_digest,
        market_symbol=decision.market_symbol,
        side=decision.side,
        intent_type=decision.intent_type,
        requested_notional=decision.requested_notional,
        requested_units=decision.requested_units,
        limit_price=decision.limit_price,
        reason_codes=decision.reason_codes,
        correlation_id=decision.correlation_id,
        metadata=decision.metadata,
        decision_digest=object_digest,
    )


def _decision_payload(
    *,
    schema_version: str,
    status_value: str,
    request_digest: str,
    capacity_decision_digest: str,
    market_symbol: str,
    side: str,
    intent_type: str,
    requested_notional: str,
    requested_units: str,
    limit_price: str | None,
    reason_codes: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
    capital_reserved: bool,
    order_routed: bool,
    venue_order_id_created: bool,
    execution_authorized: bool,
    fill_created: bool,
    pnl_computed: bool,
    position_mutated: bool,
    live_api_called: bool,
    scheduler_enabled: bool,
    connector_invoked: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "request_digest": request_digest,
        "capacity_decision_digest": capacity_decision_digest,
        "market_symbol": market_symbol,
        "side": side,
        "intent_type": intent_type,
        "requested_notional": requested_notional,
        "requested_units": requested_units,
        "limit_price": limit_price,
        "reason_codes": list(reason_codes),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
        "capital_reserved": capital_reserved,
        "order_routed": order_routed,
        "venue_order_id_created": venue_order_id_created,
        "execution_authorized": execution_authorized,
        "fill_created": fill_created,
        "pnl_computed": pnl_computed,
        "position_mutated": position_mutated,
        "live_api_called": live_api_called,
        "scheduler_enabled": scheduler_enabled,
        "connector_invoked": connector_invoked,
    }


def paper_order_intent_admission_decision_to_dict(
    decision: PaperOrderIntentAdmissionDecision,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an admission decision (deterministic shape, includes self-digest)."""
    payload = _decision_payload(
        schema_version=decision.schema_version,
        status_value=decision.status.value,
        request_digest=decision.request_digest,
        capacity_decision_digest=decision.capacity_decision_digest,
        market_symbol=decision.market_symbol,
        side=decision.side,
        intent_type=decision.intent_type,
        requested_notional=decision.requested_notional,
        requested_units=decision.requested_units,
        limit_price=decision.limit_price,
        reason_codes=decision.reason_codes,
        correlation_id=decision.correlation_id,
        metadata=decision.metadata,
        paper_only=decision.paper_only,
        real_orders_enabled=decision.real_orders_enabled,
        real_money_enabled=decision.real_money_enabled,
        capital_reserved=decision.capital_reserved,
        order_routed=decision.order_routed,
        venue_order_id_created=decision.venue_order_id_created,
        execution_authorized=decision.execution_authorized,
        fill_created=decision.fill_created,
        pnl_computed=decision.pnl_computed,
        position_mutated=decision.position_mutated,
        live_api_called=decision.live_api_called,
        scheduler_enabled=decision.scheduler_enabled,
        connector_invoked=decision.connector_invoked,
    )
    payload["decision_digest"] = decision.decision_digest
    return payload


def paper_order_intent_admission_decision_digest(decision: PaperOrderIntentAdmissionDecision) -> str:
    """Recompute the canonical decision digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _decision_payload(
            schema_version=decision.schema_version,
            status_value=decision.status.value,
            request_digest=decision.request_digest,
            capacity_decision_digest=decision.capacity_decision_digest,
            market_symbol=decision.market_symbol,
            side=decision.side,
            intent_type=decision.intent_type,
            requested_notional=decision.requested_notional,
            requested_units=decision.requested_units,
            limit_price=decision.limit_price,
            reason_codes=decision.reason_codes,
            correlation_id=decision.correlation_id,
            metadata=decision.metadata,
            paper_only=decision.paper_only,
            real_orders_enabled=decision.real_orders_enabled,
            real_money_enabled=decision.real_money_enabled,
            capital_reserved=decision.capital_reserved,
            order_routed=decision.order_routed,
            venue_order_id_created=decision.venue_order_id_created,
            execution_authorized=decision.execution_authorized,
            fill_created=decision.fill_created,
            pnl_computed=decision.pnl_computed,
            position_mutated=decision.position_mutated,
            live_api_called=decision.live_api_called,
            scheduler_enabled=decision.scheduler_enabled,
            connector_invoked=decision.connector_invoked,
        )
    )


__all__ = [
    "PaperOrderIntentAdmissionDecision",
    "PaperOrderIntentAdmissionError",
    "PaperOrderIntentAdmissionStatus",
    "PaperOrderIntentRequest",
    "PaperOrderIntentType",
    "PaperOrderSide",
    "build_paper_order_intent_request",
    "evaluate_paper_order_intent_admission",
    "paper_order_intent_admission_decision_digest",
    "paper_order_intent_admission_decision_to_dict",
    "paper_order_intent_request_digest",
    "paper_order_intent_request_to_dict",
]
