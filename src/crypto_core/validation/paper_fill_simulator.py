"""Deterministic paper fill simulator — generic, paper-only fill of an inert ``PaperOrderIntent``.

A small, immutable, fail-closed simulator that consumes an inert ``PaperOrderIntent`` plus a
caller-supplied point-in-time ``PaperFillMarketSnapshot`` and ``PaperFillPolicy`` and emits a frozen,
digest-bound ``PaperFillSimulationResult`` (``FILLED`` / ``PARTIALLY_FILLED`` / ``REJECTED``). It is
**generic and deterministic** — it models no venue-realistic Deribit fee/funding/slippage/queue
semantics. It does **not** route an order, create a venue/exchange/client order id, create a route id
or execution instruction, mutate positions, compute PnL, or reserve/mutate capital — no DB/file/
network/env IO, no wall-clock, no random, no threading, no connector/scheduler/runtime/venue/
execution/service/session/portfolio surface, no Deribit, no BIST.

Trading fields (market_symbol/side/intent_type/requested_units/requested_notional/limit_price) are
COPIED from the digest-validated intent; the caller cannot override them. Fill economics use only
caller-supplied deterministic inputs (reference price, optional available units, slippage/fee bps).

Deterministic fill semantics:
  - BUY candidate fill price = reference_price * (1 + slippage_bps / 10000).
  - SELL candidate fill price = reference_price * (1 - slippage_bps / 10000).
  - LIMIT BUY rejects if fill_price > limit_price; LIMIT SELL rejects if fill_price < limit_price;
    MARKET has no limit gate.
  - Liquidity: absent ``available_units`` ⇒ full requested units; ``available_units >= requested`` ⇒
    FILLED; ``0 < available < requested`` with ``allow_partial_fill`` ⇒ PARTIALLY_FILLED; else
    REJECTED (insufficient_liquidity).
  - Reject if filled < ``min_fill_units`` (min_fill_not_met) or if
    ``filled * fill_price > intent.requested_notional`` (gross_notional_exceeds_request — overfill
    guard). ``fee_amount = gross_notional * fee_rate_bps / 10000``. No PnL, no position, no capital.

Numeric discipline: every price/notional/fee is an exact decimal *string*; ``decimal.Decimal`` is used
under an input-derived ``localcontext`` precision so all products/sums are exact (a rounded-down
``gross_notional`` could otherwise bypass the notional cap). No float, no NaN/inf/scientific form.

Fail closed: a wrong-typed/malformed/forged intent/snapshot/policy, an intent digest mismatch, a
non-``CREATED`` or unsafe intent, a symbol mismatch, an invalid/forbidden id/correlation/metadata, or
an invalid decimal raises ``PaperFillSimulationError``. A non-malformed market/policy rejection
(non-marketable limit, insufficient liquidity, min fill not met, notional overflow, non-positive
price) yields a ``REJECTED`` result with sorted reason codes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_order_intent import (
    PaperOrderIntent,
    PaperOrderIntentStatus,
    paper_order_intent_digest,
)
from crypto_core.validation.paper_order_intent_admission import PaperOrderIntentType, PaperOrderSide

_SNAPSHOT_SCHEMA_VERSION = "paper-fill-market-snapshot.v1"
_POLICY_SCHEMA_VERSION = "paper-fill-policy.v1"
_RESULT_SCHEMA_VERSION = "paper-fill-simulation-result.v1"
_EXPECTED_INTENT_SCHEMA_VERSION = "paper-order-intent.v1"

_BPS_DENOMINATOR = Decimal(10000)

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Sign/positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling validation modules (word-bounded). A bare ``order``/``orders`` token
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

# Verdict reason codes (bare snake_case, stable, sorted in the result). Error messages are prefixed.
_REASON_NON_POSITIVE_FILL_PRICE = "non_positive_fill_price"
_REASON_LIMIT_NOT_MARKETABLE = "limit_not_marketable"
_REASON_INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
_REASON_MIN_FILL_NOT_MET = "min_fill_not_met"
_REASON_GROSS_NOTIONAL_EXCEEDS_REQUEST = "gross_notional_exceeds_request"
_REASON_PARTIAL_FILL = "partial_fill"

_VALID_SIDES = frozenset(side.value for side in PaperOrderSide)
_VALID_INTENT_TYPES = frozenset(intent_type.value for intent_type in PaperOrderIntentType)


class PaperFillSimulationError(RuntimeError):
    """Raised when fill-simulation inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperFillSimulationStatus(str, Enum):
    """Deterministic paper fill outcome. Never an execution permission / real order / capital action."""

    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperFillMarketSnapshot:
    """Deterministic, immutable point-in-time market snapshot for paper fill simulation. PAPER ONLY."""

    schema_version: str
    snapshot_id: str
    market_symbol: str
    reference_price: str
    available_units: str | None
    observed_at_ns: int | None
    metadata: tuple[tuple[str, str], ...]
    snapshot_digest: str


@dataclass(frozen=True)
class PaperFillPolicy:
    """Deterministic, immutable generic paper fill policy (slippage/fee/partial). PAPER ONLY."""

    schema_version: str
    policy_id: str
    slippage_bps: str
    fee_rate_bps: str
    allow_partial_fill: bool
    min_fill_units: str | None
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str


@dataclass(frozen=True)
class PaperFillSimulationResult:
    """Deterministic, immutable digest-bound paper fill result. Inert. PAPER ONLY.

    Reports simulated fill economics only — never a routed order, venue/exchange/client order id, route
    id, execution instruction, position, PnL, or capital action. The negative attestations are always
    False.
    """

    schema_version: str
    status: PaperFillSimulationStatus
    fill_simulation_id: str
    intent_digest: str
    market_snapshot_digest: str
    fill_policy_digest: str
    market_symbol: str
    side: str
    intent_type: str
    fill_price: str
    filled_units: str
    unfilled_units: str
    gross_notional: str
    fee_amount: str
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    result_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    execution_authorized: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    connector_invoked: bool = False
    position_mutated: bool = False
    pnl_computed: bool = False
    capital_reserved: bool = False


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
    """Render an exact ``Decimal`` as a canonical plain-decimal string.

    Trailing zeros are removed without ``normalize`` so economically-identical amounts computed from
    differently-scaled inputs render to the same canonical string (and the same digest); ``format(…,
    "f")`` keeps it in plain fixed-point (never scientific), and signed zero is pinned to ``"0"``.
    """
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _is_positive_decimal(value: object) -> bool:
    parsed = _parse_decimal(value)
    return parsed is not None and parsed > 0


def _is_nonneg_decimal(value: object) -> bool:
    parsed = _parse_decimal(value)
    return parsed is not None and parsed >= 0


def _require_positive_decimal_str(value: object, field: str) -> str:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperFillSimulationError(f"paper_fill_simulator:{field}_not_decimal_string")
    if not parsed > 0:
        raise PaperFillSimulationError(f"paper_fill_simulator:{field}_not_positive")
    return _render_decimal(parsed)


def _require_nonneg_decimal_str(value: object, field: str) -> str:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise PaperFillSimulationError(f"paper_fill_simulator:{field}_not_decimal_string")
    if parsed < 0:
        raise PaperFillSimulationError(f"paper_fill_simulator:{field}_negative")
    return _render_decimal(parsed)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperFillSimulationError("paper_fill_simulator:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperFillSimulationError("paper_fill_simulator:metadata_malformed")
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


def _decimal_span(value: Decimal) -> int:
    """Positional span of an exact Decimal: significant digits PLUS the magnitude implied by the exponent.

    ``len(as_tuple().digits)`` counts only significant digits, never the exponent gap, so a value such as
    ``1e-100`` (one significant digit) would be sized as width 1 while it actually spans 101 fixed-point
    places. Summing this span keeps the working precision wide enough that products/sums over high-scale
    (many leading/trailing zero) inputs stay exact instead of being silently context-rounded — e.g. a
    tiny-slippage fill price ``1.000…0001`` must not collapse to ``1``.
    """
    tup = value.as_tuple()
    return len(tup.digits) + abs(int(tup.exponent))


def _arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal precision wide enough that every product/sum over the inputs is exact (input-derived)."""
    span = sum(_decimal_span(value) for value in operands)
    return max(28, span + 40)


# --------------------------------------------------------------------------------------------------
# Market snapshot
# --------------------------------------------------------------------------------------------------


def _snapshot_payload(
    *,
    schema_version: str,
    snapshot_id: str,
    market_symbol: str,
    reference_price: str,
    available_units: str | None,
    observed_at_ns: int | None,
    metadata: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "snapshot_id": snapshot_id,
        "market_symbol": market_symbol,
        "reference_price": reference_price,
        "available_units": available_units,
        "observed_at_ns": observed_at_ns,
        "metadata": [list(pair) for pair in metadata],
    }


def build_paper_fill_market_snapshot(
    *,
    snapshot_id: str,
    market_symbol: str,
    reference_price: str,
    available_units: str | None = None,
    observed_at_ns: int | None = None,
    metadata: Mapping[str, str] | None = None,
) -> PaperFillMarketSnapshot:
    """Build a deterministic, immutable PIT market snapshot with a canonical ``snapshot_digest``.

    ``snapshot_id``/``market_symbol`` must be non-empty token-clean strings; ``reference_price`` a
    strict, strictly-positive decimal string; ``available_units`` (if given) a strict non-negative
    decimal string; ``observed_at_ns`` (if given) a non-negative ``int`` (not ``bool``). A malformed
    or forbidden-token field raises ``PaperFillSimulationError``.
    """
    if not _is_non_empty_string(snapshot_id):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_id_invalid")
    if not _is_non_empty_string(market_symbol):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_market_symbol_invalid")
    reference = _require_positive_decimal_str(reference_price, "reference_price")
    available = _require_nonneg_decimal_str(available_units, "available_units") if available_units is not None else None
    if observed_at_ns is not None and (not _is_int(observed_at_ns) or observed_at_ns < 0):
        raise PaperFillSimulationError("paper_fill_simulator:observed_at_ns_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(snapshot_id, market_symbol, *_metadata_texts(metadata_pairs)):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_scope_violation")
    payload = _snapshot_payload(
        schema_version=_SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        market_symbol=market_symbol,
        reference_price=reference,
        available_units=available,
        observed_at_ns=observed_at_ns,
        metadata=metadata_pairs,
    )
    return PaperFillMarketSnapshot(
        schema_version=_SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        market_symbol=market_symbol,
        reference_price=reference,
        available_units=available,
        observed_at_ns=observed_at_ns,
        metadata=metadata_pairs,
        snapshot_digest=_canonical_digest(payload),
    )


def paper_fill_market_snapshot_to_dict(snapshot: PaperFillMarketSnapshot) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a market snapshot (deterministic shape, includes self-digest)."""
    payload = _snapshot_payload(
        schema_version=snapshot.schema_version,
        snapshot_id=snapshot.snapshot_id,
        market_symbol=snapshot.market_symbol,
        reference_price=snapshot.reference_price,
        available_units=snapshot.available_units,
        observed_at_ns=snapshot.observed_at_ns,
        metadata=snapshot.metadata,
    )
    payload["snapshot_digest"] = snapshot.snapshot_digest
    return payload


def paper_fill_market_snapshot_digest(snapshot: PaperFillMarketSnapshot) -> str:
    """Recompute the canonical snapshot digest from the serializer output, excluding the self-digest."""
    return _canonical_digest(
        _snapshot_payload(
            schema_version=snapshot.schema_version,
            snapshot_id=snapshot.snapshot_id,
            market_symbol=snapshot.market_symbol,
            reference_price=snapshot.reference_price,
            available_units=snapshot.available_units,
            observed_at_ns=snapshot.observed_at_ns,
            metadata=snapshot.metadata,
        )
    )


# --------------------------------------------------------------------------------------------------
# Fill policy
# --------------------------------------------------------------------------------------------------


def _policy_payload(
    *,
    schema_version: str,
    policy_id: str,
    slippage_bps: str,
    fee_rate_bps: str,
    allow_partial_fill: bool,
    min_fill_units: str | None,
    metadata: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "policy_id": policy_id,
        "slippage_bps": slippage_bps,
        "fee_rate_bps": fee_rate_bps,
        "allow_partial_fill": allow_partial_fill,
        "min_fill_units": min_fill_units,
        "metadata": [list(pair) for pair in metadata],
    }


def build_paper_fill_policy(
    *,
    policy_id: str,
    slippage_bps: str,
    fee_rate_bps: str,
    allow_partial_fill: bool,
    min_fill_units: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> PaperFillPolicy:
    """Build a deterministic, immutable generic paper fill policy with a canonical ``policy_digest``.

    ``policy_id`` must be a non-empty token-clean string; ``slippage_bps``/``fee_rate_bps`` strict
    non-negative decimal strings; ``allow_partial_fill`` a ``bool``; ``min_fill_units`` (if given) a
    strict, strictly-positive decimal string. A malformed/forbidden field raises
    ``PaperFillSimulationError``.
    """
    if not _is_non_empty_string(policy_id):
        raise PaperFillSimulationError("paper_fill_simulator:policy_id_invalid")
    slippage = _require_nonneg_decimal_str(slippage_bps, "slippage_bps")
    fee_rate = _require_nonneg_decimal_str(fee_rate_bps, "fee_rate_bps")
    if not isinstance(allow_partial_fill, bool):
        raise PaperFillSimulationError("paper_fill_simulator:allow_partial_fill_not_bool")
    min_fill = _require_positive_decimal_str(min_fill_units, "min_fill_units") if min_fill_units is not None else None
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(policy_id, *_metadata_texts(metadata_pairs)):
        raise PaperFillSimulationError("paper_fill_simulator:policy_scope_violation")
    payload = _policy_payload(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        slippage_bps=slippage,
        fee_rate_bps=fee_rate,
        allow_partial_fill=allow_partial_fill,
        min_fill_units=min_fill,
        metadata=metadata_pairs,
    )
    return PaperFillPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        slippage_bps=slippage,
        fee_rate_bps=fee_rate,
        allow_partial_fill=allow_partial_fill,
        min_fill_units=min_fill,
        metadata=metadata_pairs,
        policy_digest=_canonical_digest(payload),
    )


def paper_fill_policy_to_dict(policy: PaperFillPolicy) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a fill policy (deterministic shape, includes self-digest)."""
    payload = _policy_payload(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        slippage_bps=policy.slippage_bps,
        fee_rate_bps=policy.fee_rate_bps,
        allow_partial_fill=policy.allow_partial_fill,
        min_fill_units=policy.min_fill_units,
        metadata=policy.metadata,
    )
    payload["policy_digest"] = policy.policy_digest
    return payload


def paper_fill_policy_digest(policy: PaperFillPolicy) -> str:
    """Recompute the canonical policy digest from the serializer output, excluding the self-digest."""
    return _canonical_digest(
        _policy_payload(
            schema_version=policy.schema_version,
            policy_id=policy.policy_id,
            slippage_bps=policy.slippage_bps,
            fee_rate_bps=policy.fee_rate_bps,
            allow_partial_fill=policy.allow_partial_fill,
            min_fill_units=policy.min_fill_units,
            metadata=policy.metadata,
        )
    )


# --------------------------------------------------------------------------------------------------
# Upstream re-proof
# --------------------------------------------------------------------------------------------------


def _intent_is_paper_safe(intent: PaperOrderIntent) -> bool:
    return (
        intent.paper_only is True
        and intent.real_orders_enabled is False
        and intent.real_money_enabled is False
        and intent.capital_reserved is False
        and intent.order_routed is False
        and intent.venue_order_id_created is False
        and intent.exchange_id_created is False
        and intent.client_order_id_created is False
        and intent.route_id_created is False
        and intent.execution_instruction_created is False
        and intent.execution_authorized is False
        and intent.fill_created is False
        and intent.pnl_computed is False
        and intent.position_mutated is False
        and intent.live_api_called is False
        and intent.scheduler_enabled is False
        and intent.connector_invoked is False
    )


def _reprove_intent(intent: PaperOrderIntent) -> tuple[Decimal, Decimal, Decimal | None]:
    """Re-prove a digest-valid intent is CREATED, paper-safe, well-formed, token-clean. Return demand."""
    if intent.schema_version != _EXPECTED_INTENT_SCHEMA_VERSION:
        raise PaperFillSimulationError("paper_fill_simulator:intent_schema_unexpected")
    if not isinstance(intent.status, PaperOrderIntentStatus) or intent.status is not PaperOrderIntentStatus.CREATED:
        raise PaperFillSimulationError("paper_fill_simulator:intent_not_created")
    if not _intent_is_paper_safe(intent):
        raise PaperFillSimulationError("paper_fill_simulator:intent_unsafe_flags")
    if not _is_non_empty_string(intent.intent_id) or not _is_non_empty_string(intent.correlation_id):
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if not (
        _is_hex64_string(intent.admission_decision_digest)
        and _is_hex64_string(intent.request_digest)
        and _is_hex64_string(intent.capacity_decision_digest)
    ):
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if not _is_non_empty_string(intent.market_symbol):
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if intent.side not in _VALID_SIDES or intent.intent_type not in _VALID_INTENT_TYPES:
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    requested_units = _parse_decimal(intent.requested_units)
    requested_notional = _parse_decimal(intent.requested_notional)
    if requested_units is None or not requested_units > 0:
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if requested_notional is None or not requested_notional > 0:
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    limit_price: Decimal | None = None
    if intent.intent_type == PaperOrderIntentType.LIMIT.value:
        limit_price = _parse_decimal(intent.limit_price)
        if limit_price is None or not limit_price > 0:
            raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    elif intent.limit_price is not None:
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if not _is_metadata_tuple(intent.metadata):
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")
    if _has_scope_violation(
        intent.intent_id,
        intent.market_symbol,
        intent.correlation_id,
        *_metadata_texts(intent.metadata),
    ):
        raise PaperFillSimulationError("paper_fill_simulator:intent_scope_violation")
    return requested_units, requested_notional, limit_price


def _reprove_snapshot(snapshot: PaperFillMarketSnapshot) -> tuple[Decimal, Decimal | None]:
    """Re-prove a snapshot's digest and structure (fail-closed). Return (reference_price, available_units)."""
    if not isinstance(snapshot, PaperFillMarketSnapshot):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    if snapshot.schema_version != _SNAPSHOT_SCHEMA_VERSION:
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    if not _is_non_empty_string(snapshot.snapshot_id) or not _is_non_empty_string(snapshot.market_symbol):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    reference_price = _parse_decimal(snapshot.reference_price)
    if reference_price is None or not reference_price > 0:
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    available_units: Decimal | None = None
    if snapshot.available_units is not None:
        available_units = _parse_decimal(snapshot.available_units)
        if available_units is None or available_units < 0:
            raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    if snapshot.observed_at_ns is not None and (not _is_int(snapshot.observed_at_ns) or snapshot.observed_at_ns < 0):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    if not _is_metadata_tuple(snapshot.metadata):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_malformed")
    if _has_scope_violation(snapshot.snapshot_id, snapshot.market_symbol, *_metadata_texts(snapshot.metadata)):
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_scope_violation")
    if paper_fill_market_snapshot_digest(snapshot) != snapshot.snapshot_digest:
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_digest_mismatch")
    return reference_price, available_units


def _reprove_policy(policy: PaperFillPolicy) -> tuple[Decimal, Decimal, bool, Decimal | None]:
    """Re-prove a policy's digest and structure (fail-closed). Return (slippage, fee, partial, min_fill)."""
    if not isinstance(policy, PaperFillPolicy):
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if policy.schema_version != _POLICY_SCHEMA_VERSION:
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if not _is_non_empty_string(policy.policy_id):
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    slippage_bps = _parse_decimal(policy.slippage_bps)
    fee_rate_bps = _parse_decimal(policy.fee_rate_bps)
    if slippage_bps is None or slippage_bps < 0:
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if fee_rate_bps is None or fee_rate_bps < 0:
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if not isinstance(policy.allow_partial_fill, bool):
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    min_fill_units: Decimal | None = None
    if policy.min_fill_units is not None:
        min_fill_units = _parse_decimal(policy.min_fill_units)
        if min_fill_units is None or not min_fill_units > 0:
            raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if not _is_metadata_tuple(policy.metadata):
        raise PaperFillSimulationError("paper_fill_simulator:policy_malformed")
    if _has_scope_violation(policy.policy_id, *_metadata_texts(policy.metadata)):
        raise PaperFillSimulationError("paper_fill_simulator:policy_scope_violation")
    if paper_fill_policy_digest(policy) != policy.policy_digest:
        raise PaperFillSimulationError("paper_fill_simulator:policy_digest_mismatch")
    return slippage_bps, fee_rate_bps, policy.allow_partial_fill, min_fill_units


# --------------------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------------------


def simulate_paper_fill(
    intent: PaperOrderIntent,
    market_snapshot: PaperFillMarketSnapshot,
    policy: PaperFillPolicy,
    *,
    fill_simulation_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperFillSimulationResult:
    """Deterministically simulate a paper fill of an inert ``PaperOrderIntent`` (generic semantics).

    The ``intent`` is re-proven via the PUBLIC ``paper_order_intent_digest`` (mismatch raises) and
    structurally re-proven (CREATED, paper-safe, well-formed, token-clean); the ``market_snapshot`` and
    ``policy`` are re-proven via their public digests. Trading fields are copied from the intent; fill
    economics use only the caller's deterministic inputs. Returns ``FILLED`` / ``PARTIALLY_FILLED`` /
    ``REJECTED`` with sorted reason codes. Wrong-typed/malformed/forged inputs raise
    ``PaperFillSimulationError``. Routes no order; creates no venue/order id, route, execution
    instruction, fill record, position, or PnL; reserves no capital; calls no live API; mutates nothing.
    """
    if not _is_non_empty_string(fill_simulation_id):
        raise PaperFillSimulationError("paper_fill_simulator:fill_simulation_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperFillSimulationError("paper_fill_simulator:correlation_id_invalid")
    result_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(fill_simulation_id, correlation_id, *_metadata_texts(result_metadata)):
        raise PaperFillSimulationError("paper_fill_simulator:scope_violation")
    if not isinstance(intent, PaperOrderIntent):
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed")

    # Digest boundary: re-prove the upstream intent self-digest via its PUBLIC serializer.
    try:
        expected_intent_digest = paper_order_intent_digest(intent)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperFillSimulationError("paper_fill_simulator:intent_malformed") from exc
    if not isinstance(intent.intent_digest, str) or intent.intent_digest != expected_intent_digest:
        raise PaperFillSimulationError("paper_fill_simulator:intent_digest_mismatch")

    requested_units, requested_notional, limit_price = _reprove_intent(intent)
    reference_price, available_units = _reprove_snapshot(market_snapshot)
    slippage_bps, fee_rate_bps, allow_partial_fill, min_fill_units = _reprove_policy(policy)

    if market_snapshot.market_symbol != intent.market_symbol:
        raise PaperFillSimulationError("paper_fill_simulator:snapshot_symbol_mismatch")

    operands = [
        requested_units,
        requested_notional,
        reference_price,
        slippage_bps,
        fee_rate_bps,
        _BPS_DENOMINATOR,
    ]
    if available_units is not None:
        operands.append(available_units)
    if limit_price is not None:
        operands.append(limit_price)
    if min_fill_units is not None:
        operands.append(min_fill_units)

    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(tuple(operands))
        if intent.side == PaperOrderSide.BUY.value:
            fill_price = reference_price * (Decimal(1) + slippage_bps / _BPS_DENOMINATOR)
        else:
            fill_price = reference_price * (Decimal(1) - slippage_bps / _BPS_DENOMINATOR)

        status, filled, unfilled, gross, fee, reasons = _decide_fill(
            side=intent.side,
            intent_type=intent.intent_type,
            fill_price=fill_price,
            limit_price=limit_price,
            requested_units=requested_units,
            requested_notional=requested_notional,
            available_units=available_units,
            allow_partial_fill=allow_partial_fill,
            min_fill_units=min_fill_units,
            fee_rate_bps=fee_rate_bps,
        )
        rendered = (
            _render_decimal(fill_price),
            _render_decimal(filled),
            _render_decimal(unfilled),
            _render_decimal(gross),
            _render_decimal(fee),
        )

    return _finalize_result(
        status=status,
        intent=intent,
        market_snapshot=market_snapshot,
        policy=policy,
        fill_price=rendered[0],
        filled_units=rendered[1],
        unfilled_units=rendered[2],
        gross_notional=rendered[3],
        fee_amount=rendered[4],
        reasons=reasons,
        fill_simulation_id=fill_simulation_id,
        correlation_id=correlation_id,
        metadata=result_metadata,
    )


def _decide_fill(
    *,
    side: str,
    intent_type: str,
    fill_price: Decimal,
    limit_price: Decimal | None,
    requested_units: Decimal,
    requested_notional: Decimal,
    available_units: Decimal | None,
    allow_partial_fill: bool,
    min_fill_units: Decimal | None,
    fee_rate_bps: Decimal,
) -> tuple[PaperFillSimulationStatus, Decimal, Decimal, Decimal, Decimal, tuple[str, ...]]:
    """Pure deterministic fill decision. Returns (status, filled, unfilled, gross, fee, reasons)."""
    zero = Decimal(0)
    rejected = (PaperFillSimulationStatus.REJECTED, zero, requested_units, zero, zero)

    if not fill_price > 0:
        return (*rejected, (_REASON_NON_POSITIVE_FILL_PRICE,))

    if intent_type == PaperOrderIntentType.LIMIT.value and limit_price is not None:
        if side == PaperOrderSide.BUY.value and fill_price > limit_price:
            return (*rejected, (_REASON_LIMIT_NOT_MARKETABLE,))
        if side == PaperOrderSide.SELL.value and fill_price < limit_price:
            return (*rejected, (_REASON_LIMIT_NOT_MARKETABLE,))

    effective_available = available_units if available_units is not None else requested_units
    if effective_available >= requested_units:
        candidate = requested_units
        is_partial = False
    elif effective_available > 0 and allow_partial_fill:
        candidate = effective_available
        is_partial = True
    else:
        return (*rejected, (_REASON_INSUFFICIENT_LIQUIDITY,))

    post_reasons: list[str] = []
    if min_fill_units is not None and candidate < min_fill_units:
        post_reasons.append(_REASON_MIN_FILL_NOT_MET)
    gross = candidate * fill_price
    if gross > requested_notional:
        post_reasons.append(_REASON_GROSS_NOTIONAL_EXCEEDS_REQUEST)
    if post_reasons:
        return (*rejected, tuple(post_reasons))

    fee = gross * fee_rate_bps / _BPS_DENOMINATOR
    unfilled = requested_units - candidate
    if is_partial:
        return PaperFillSimulationStatus.PARTIALLY_FILLED, candidate, unfilled, gross, fee, (_REASON_PARTIAL_FILL,)
    return PaperFillSimulationStatus.FILLED, candidate, unfilled, gross, fee, ()


def _finalize_result(
    *,
    status: PaperFillSimulationStatus,
    intent: PaperOrderIntent,
    market_snapshot: PaperFillMarketSnapshot,
    policy: PaperFillPolicy,
    fill_price: str,
    filled_units: str,
    unfilled_units: str,
    gross_notional: str,
    fee_amount: str,
    reasons: tuple[str, ...],
    fill_simulation_id: str,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperFillSimulationResult:
    result = PaperFillSimulationResult(
        schema_version=_RESULT_SCHEMA_VERSION,
        status=status,
        fill_simulation_id=fill_simulation_id,
        intent_digest=intent.intent_digest,
        market_snapshot_digest=market_snapshot.snapshot_digest,
        fill_policy_digest=policy.policy_digest,
        market_symbol=intent.market_symbol,
        side=intent.side,
        intent_type=intent.intent_type,
        fill_price=fill_price,
        filled_units=filled_units,
        unfilled_units=unfilled_units,
        gross_notional=gross_notional,
        fee_amount=fee_amount,
        reason_codes=_sorted_unique(reasons),
        correlation_id=correlation_id,
        metadata=metadata,
        result_digest="",
    )
    object_digest = paper_fill_simulation_result_digest(result)
    return PaperFillSimulationResult(
        schema_version=result.schema_version,
        status=result.status,
        fill_simulation_id=result.fill_simulation_id,
        intent_digest=result.intent_digest,
        market_snapshot_digest=result.market_snapshot_digest,
        fill_policy_digest=result.fill_policy_digest,
        market_symbol=result.market_symbol,
        side=result.side,
        intent_type=result.intent_type,
        fill_price=result.fill_price,
        filled_units=result.filled_units,
        unfilled_units=result.unfilled_units,
        gross_notional=result.gross_notional,
        fee_amount=result.fee_amount,
        reason_codes=result.reason_codes,
        correlation_id=result.correlation_id,
        metadata=result.metadata,
        result_digest=object_digest,
    )


def _result_payload(
    *,
    schema_version: str,
    status_value: str,
    fill_simulation_id: str,
    intent_digest: str,
    market_snapshot_digest: str,
    fill_policy_digest: str,
    market_symbol: str,
    side: str,
    intent_type: str,
    fill_price: str,
    filled_units: str,
    unfilled_units: str,
    gross_notional: str,
    fee_amount: str,
    reason_codes: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
    order_routed: bool,
    venue_order_id_created: bool,
    exchange_order_id_created: bool,
    client_order_id_created: bool,
    route_id_created: bool,
    execution_instruction_created: bool,
    execution_authorized: bool,
    live_api_called: bool,
    scheduler_enabled: bool,
    connector_invoked: bool,
    position_mutated: bool,
    pnl_computed: bool,
    capital_reserved: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "fill_simulation_id": fill_simulation_id,
        "intent_digest": intent_digest,
        "market_snapshot_digest": market_snapshot_digest,
        "fill_policy_digest": fill_policy_digest,
        "market_symbol": market_symbol,
        "side": side,
        "intent_type": intent_type,
        "fill_price": fill_price,
        "filled_units": filled_units,
        "unfilled_units": unfilled_units,
        "gross_notional": gross_notional,
        "fee_amount": fee_amount,
        "reason_codes": list(reason_codes),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
        "order_routed": order_routed,
        "venue_order_id_created": venue_order_id_created,
        "exchange_order_id_created": exchange_order_id_created,
        "client_order_id_created": client_order_id_created,
        "route_id_created": route_id_created,
        "execution_instruction_created": execution_instruction_created,
        "execution_authorized": execution_authorized,
        "live_api_called": live_api_called,
        "scheduler_enabled": scheduler_enabled,
        "connector_invoked": connector_invoked,
        "position_mutated": position_mutated,
        "pnl_computed": pnl_computed,
        "capital_reserved": capital_reserved,
    }


def _result_payload_from(result: PaperFillSimulationResult) -> dict[str, object]:
    return _result_payload(
        schema_version=result.schema_version,
        status_value=result.status.value,
        fill_simulation_id=result.fill_simulation_id,
        intent_digest=result.intent_digest,
        market_snapshot_digest=result.market_snapshot_digest,
        fill_policy_digest=result.fill_policy_digest,
        market_symbol=result.market_symbol,
        side=result.side,
        intent_type=result.intent_type,
        fill_price=result.fill_price,
        filled_units=result.filled_units,
        unfilled_units=result.unfilled_units,
        gross_notional=result.gross_notional,
        fee_amount=result.fee_amount,
        reason_codes=result.reason_codes,
        correlation_id=result.correlation_id,
        metadata=result.metadata,
        paper_only=result.paper_only,
        real_orders_enabled=result.real_orders_enabled,
        real_money_enabled=result.real_money_enabled,
        order_routed=result.order_routed,
        venue_order_id_created=result.venue_order_id_created,
        exchange_order_id_created=result.exchange_order_id_created,
        client_order_id_created=result.client_order_id_created,
        route_id_created=result.route_id_created,
        execution_instruction_created=result.execution_instruction_created,
        execution_authorized=result.execution_authorized,
        live_api_called=result.live_api_called,
        scheduler_enabled=result.scheduler_enabled,
        connector_invoked=result.connector_invoked,
        position_mutated=result.position_mutated,
        pnl_computed=result.pnl_computed,
        capital_reserved=result.capital_reserved,
    )


def paper_fill_simulation_result_to_dict(result: PaperFillSimulationResult) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a fill result (deterministic shape, includes self-digest)."""
    payload = _result_payload_from(result)
    payload["result_digest"] = result.result_digest
    return payload


def paper_fill_simulation_result_digest(result: PaperFillSimulationResult) -> str:
    """Recompute the canonical result digest from the serializer output, excluding the self-digest."""
    return _canonical_digest(_result_payload_from(result))


__all__ = [
    "PaperFillMarketSnapshot",
    "PaperFillPolicy",
    "PaperFillSimulationError",
    "PaperFillSimulationResult",
    "PaperFillSimulationStatus",
    "build_paper_fill_market_snapshot",
    "build_paper_fill_policy",
    "paper_fill_market_snapshot_digest",
    "paper_fill_market_snapshot_to_dict",
    "paper_fill_policy_digest",
    "paper_fill_policy_to_dict",
    "paper_fill_simulation_result_digest",
    "paper_fill_simulation_result_to_dict",
    "simulate_paper_fill",
]
