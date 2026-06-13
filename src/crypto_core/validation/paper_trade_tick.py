"""Paper trade tick / trade-intent contract — deterministic, paper-only trade-intent evidence.

A small, immutable, fail-closed contract that records a *caller-supplied* paper-only trade intent (an
``action`` on an instrument, an ``intent_type``, a quantity, an optional limit price) as a
``PaperTradeTick`` evidence object tied by digest reference to upstream replay/report evidence. It is
*only* a contract layer: it does **not** execute, route, send, schedule, connect, simulate fills, compute
PnL, or mutate any sleeve/portfolio state — no DB/file/network/env IO, no wall-clock, no random, no
threading, no order routing, no connector, no runtime. It defines what was *intended*, deterministically,
and renders a fail-closed verdict on that intent; it never claims a trade occurred.

Design rules:
  - Record, don't act: ``action``/``intent_type``/``quantity``/``limit_price`` are caller-supplied; the
    builder validates shape + paper-safety + intent policy and renders a terminal ``PaperTradeTickStatus``.
    No fill, price improvement, PnL, or position change is computed; the upstream digest is a *reference*,
    shape-validated as 64-hex only (not re-proven against an upstream object in this contract layer).
  - Deterministic numeric discipline: quantities/prices are exact decimal *strings* (no float, no NaN/inf,
    no scientific/whitespace forms); ``decimal.Decimal`` is used only for exact sign/zero comparison, never
    for storage, so there is no float drift. The canonical digest is SHA-256 over the public serializer
    output (enum ``.value`` and stable list ordering) excluding the self-digest field.
  - Paper-safety triple: ``paper_only`` must be exactly ``True`` and ``real_orders_enabled`` /
    ``real_money_enabled`` exactly ``False``; any other value fails closed. The stored attestation is the
    safe constant, and the canonical accepted-tick dict is shaped to pass the EvidenceJournal token guard.
  - Fail closed: an empty ``correlation_id`` or malformed metadata raises ``PaperTradeTickError`` (call
    contract); an unknown action/intent type, a non-decimal/NaN/inf/non-positive quantity or price, a
    missing/malformed upstream digest, a forbidden BIST/live/private/order-router/scheduler/connector/
    shadow token, or an unsafe paper-safety flag yields a REJECTED / INSUFFICIENT_EVIDENCE tick (never an
    exception-leaking partial object). Frozen dataclasses; no order/route/venue/scheduler/runtime field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

_SCHEMA_VERSION = "paper-trade-tick.v1"
_INTENT_SCHEMA_VERSION = "paper-trade-intent.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional fraction.
# Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace, and underscores.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Token guard. This is a deliberate *superset* of the EvidenceJournal token guard so that any ACCEPTED
# tick whose ids/metadata pass here will also pass ``EvidenceJournal``'s guard on append (fail-closed,
# audit-first): every wall-clock / forbidden token the journal rejects is rejected here too. Detection is
# token-based on alphanumeric runs (so ``border``/``reorder`` are spared while a bare ``order`` token is
# not), with market-data terms (``order_book``/``order_flow``/``limit_order_book``) explicitly allowed.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_WALL_CLOCK_TOKENS = ("created_at", "timestamp", "timestamp_ns", "time_ns", "utcnow", "now", "wall_clock")
_FORBIDDEN_TOKENS = (
    "live",
    "private",
    "private_api",
    "credential",
    "credentials",
    "secret",
    "api_key",
    "order_router",
    "place_order",
    "live_order",
    "scheduler",
    "auto_loop",
    "connector_ready",
    "shadow",
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperTradeTickError(RuntimeError):
    """Raised when trade-tick/intent inputs are malformed at the call level (empty id / bad metadata)."""


class PaperTradeIntentAction(str, Enum):
    """Direction of a paper trade intent. Never an order-routing or live-execution action."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    FLATTEN = "FLATTEN"


class PaperTradeIntentType(str, Enum):
    """Shape of a paper trade intent. Records intent only; does not route or cancel anything live."""

    LIMIT = "LIMIT"
    MARKETABLE_LIMIT = "MARKETABLE_LIMIT"
    PASSIVE_LIMIT = "PASSIVE_LIMIT"
    CANCEL_INTENT = "CANCEL_INTENT"


class PaperTradeTickStatus(str, Enum):
    """Terminal verdict of a paper trade tick. Never an order/live action."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


_EXECUTABLE_ACTIONS = frozenset(
    {
        PaperTradeIntentAction.BUY,
        PaperTradeIntentAction.SELL,
        PaperTradeIntentAction.REDUCE,
        PaperTradeIntentAction.FLATTEN,
    }
)
_PRICED_TYPES = frozenset(
    {
        PaperTradeIntentType.LIMIT,
        PaperTradeIntentType.MARKETABLE_LIMIT,
        PaperTradeIntentType.PASSIVE_LIMIT,
    }
)


@dataclass(frozen=True)
class PaperTradeIntent:
    """Deterministic, immutable, normalized paper trade-intent spec (no verdict). PAPER ONLY."""

    schema_version: str
    action: str
    intent_type: str
    instrument_id: str
    quantity: str
    limit_price: str | None
    strategy_id: str
    run_plan_id: str
    upstream_report_digest: str
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    intent_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class PaperTradeTick:
    """Deterministic, immutable verdict over a caller-supplied paper trade intent. PAPER ONLY."""

    schema_version: str
    status: PaperTradeTickStatus
    accepted: bool
    tick_id: str
    run_plan_id: str
    upstream_report_digest: str
    instrument_id: str
    action: str
    intent_type: str
    quantity: str
    limit_price: str | None
    strategy_id: str
    intent_digest: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    paper_trade_tick_digest: str
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
    """Return an exact finite ``Decimal`` for a strict decimal string, else ``None`` (no float path)."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _identifier_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    token_chars: list[str] = []
    for char in text:
        if char.isalnum():
            token_chars.append(char)
            continue
        if token_chars:
            tokens.append("".join(token_chars))
            token_chars = []
    if token_chars:
        tokens.append("".join(token_chars))
    return tuple(tokens)


def _subsequence_start_indexes(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> tuple[int, ...]:
    if not sequence or len(sequence) > len(tokens):
        return ()
    starts: list[int] = []
    for start in range(len(tokens) - len(sequence) + 1):
        if tokens[start : start + len(sequence)] == sequence:
            starts.append(start)
    return tuple(starts)


def _token_matches(tokens: tuple[str, ...], lowered: str, marker: str) -> bool:
    if "_" in marker:
        return marker in lowered or bool(_subsequence_start_indexes(tokens, tuple(marker.split("_"))))
    return marker in tokens


def _contains_forbidden_order(tokens: tuple[str, ...]) -> bool:
    # A bare ``order``/``orders`` token is forbidden unless it is covered by an allowed market-data term.
    covered: set[int] = set()
    for safe_term in _SAFE_MARKET_DATA_TERMS:
        safe_tokens = tuple(safe_term.split("_"))
        for start in _subsequence_start_indexes(tokens, safe_tokens):
            covered.update(range(start, start + len(safe_tokens)))
    return any(token in {"order", "orders"} and index not in covered for index, token in enumerate(tokens))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        lowered = text.lower()
        tokens = _identifier_tokens(lowered)
        if "bist" in lowered or _BIST_PATTERN.search(text):
            reasons.append("paper_trade_tick:bist_scope_leakage")
        if any(_token_matches(tokens, lowered, marker) for marker in _WALL_CLOCK_TOKENS):
            reasons.append("paper_trade_tick:wall_clock_token")
        forbidden = any(_token_matches(tokens, lowered, marker) for marker in _FORBIDDEN_TOKENS)
        if forbidden or _contains_forbidden_order(tokens):
            reasons.append("paper_trade_tick:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperTradeTickError("paper_trade_tick:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperTradeTickError("paper_trade_tick:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _coerce_action(value: object) -> PaperTradeIntentAction | None:
    if isinstance(value, PaperTradeIntentAction):
        return value
    if isinstance(value, str):
        try:
            return PaperTradeIntentAction(value)
        except ValueError:
            return None
    return None


def _coerce_intent_type(value: object) -> PaperTradeIntentType | None:
    if isinstance(value, PaperTradeIntentType):
        return value
    if isinstance(value, str):
        try:
            return PaperTradeIntentType(value)
        except ValueError:
            return None
    return None


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _intent_payload(
    *,
    schema_version: str,
    action_value: str,
    intent_type_value: str,
    instrument_id: str,
    quantity: str,
    limit_price: str | None,
    strategy_id: str,
    run_plan_id: str,
    upstream_report_digest: str,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "action": action_value,
        "intent_type": intent_type_value,
        "instrument_id": instrument_id,
        "quantity": quantity,
        "limit_price": limit_price,
        "strategy_id": strategy_id,
        "run_plan_id": run_plan_id,
        "upstream_report_digest": upstream_report_digest,
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def build_paper_trade_intent(
    *,
    action: PaperTradeIntentAction | str,
    intent_type: PaperTradeIntentType | str,
    instrument_id: str,
    quantity: str,
    strategy_id: str,
    run_plan_id: str,
    upstream_report_digest: str,
    correlation_id: str,
    limit_price: str | None = None,
    metadata: Mapping[str, str] | None = None,
    paper_only: bool = True,
    real_orders_enabled: bool = False,
    real_money_enabled: bool = False,
) -> PaperTradeIntent:
    """Build a normalized, immutable paper trade-intent spec, raising on call-level malformed types.

    This is the strict, shape-only constructor: an unknown ``action``/``intent_type``, a non-string id,
    a non-string ``quantity``/``limit_price``, a non 64-hex ``upstream_report_digest``, an unsafe
    paper-safety flag, a forbidden BIST/live/order-routing/scheduler/connector/shadow token, or malformed
    metadata raises ``PaperTradeTickError``. It records intent shape only and does not apply trade policy
    (positivity / priced-requires-price); rendering an ACCEPTED/REJECTED verdict is ``build_paper_trade_tick``.
    """
    action_enum = _coerce_action(action)
    if action_enum is None:
        raise PaperTradeTickError("paper_trade_tick:intent_action_invalid")
    type_enum = _coerce_intent_type(intent_type)
    if type_enum is None:
        raise PaperTradeTickError("paper_trade_tick:intent_type_invalid")
    for name, value in (
        ("instrument_id", instrument_id),
        ("strategy_id", strategy_id),
        ("run_plan_id", run_plan_id),
        ("correlation_id", correlation_id),
    ):
        if not _is_non_empty_string(value):
            raise PaperTradeTickError(f"paper_trade_tick:intent_{name}_invalid")
    if not isinstance(quantity, str):
        raise PaperTradeTickError("paper_trade_tick:intent_quantity_not_string")
    if limit_price is not None and not isinstance(limit_price, str):
        raise PaperTradeTickError("paper_trade_tick:intent_limit_price_not_string")
    if not _is_sha256_hex(upstream_report_digest):
        raise PaperTradeTickError("paper_trade_tick:intent_upstream_report_digest_invalid")
    if paper_only is not True:
        raise PaperTradeTickError("paper_trade_tick:intent_not_paper_only")
    if real_orders_enabled is not False:
        raise PaperTradeTickError("paper_trade_tick:intent_real_orders_enabled")
    if real_money_enabled is not False:
        raise PaperTradeTickError("paper_trade_tick:intent_real_money_enabled")

    metadata_pairs = _normalize_metadata(metadata)
    if _scope_violations(
        instrument_id,
        strategy_id,
        run_plan_id,
        correlation_id,
        action_enum.value,
        type_enum.value,
        *_metadata_texts(metadata_pairs),
    ):
        raise PaperTradeTickError("paper_trade_tick:intent_scope_violation")

    payload = _intent_payload(
        schema_version=_INTENT_SCHEMA_VERSION,
        action_value=action_enum.value,
        intent_type_value=type_enum.value,
        instrument_id=instrument_id,
        quantity=quantity,
        limit_price=limit_price,
        strategy_id=strategy_id,
        run_plan_id=run_plan_id,
        upstream_report_digest=upstream_report_digest,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperTradeIntent(
        schema_version=_INTENT_SCHEMA_VERSION,
        action=action_enum.value,
        intent_type=type_enum.value,
        instrument_id=instrument_id,
        quantity=quantity,
        limit_price=limit_price,
        strategy_id=strategy_id,
        run_plan_id=run_plan_id,
        upstream_report_digest=upstream_report_digest,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        intent_digest=_canonical_digest(payload),
    )


def paper_trade_intent_to_dict(intent: PaperTradeIntent) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper trade intent (deterministic shape, includes self-digest)."""
    payload = _intent_payload(
        schema_version=intent.schema_version,
        action_value=intent.action,
        intent_type_value=intent.intent_type,
        instrument_id=intent.instrument_id,
        quantity=intent.quantity,
        limit_price=intent.limit_price,
        strategy_id=intent.strategy_id,
        run_plan_id=intent.run_plan_id,
        upstream_report_digest=intent.upstream_report_digest,
        correlation_id=intent.correlation_id,
        metadata=intent.metadata,
        paper_only=intent.paper_only,
        real_orders_enabled=intent.real_orders_enabled,
        real_money_enabled=intent.real_money_enabled,
    )
    payload["intent_digest"] = intent.intent_digest
    return payload


def paper_trade_intent_digest(intent: PaperTradeIntent) -> str:
    """Recompute the canonical intent digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _intent_payload(
            schema_version=intent.schema_version,
            action_value=intent.action,
            intent_type_value=intent.intent_type,
            instrument_id=intent.instrument_id,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            strategy_id=intent.strategy_id,
            run_plan_id=intent.run_plan_id,
            upstream_report_digest=intent.upstream_report_digest,
            correlation_id=intent.correlation_id,
            metadata=intent.metadata,
            paper_only=intent.paper_only,
            real_orders_enabled=intent.real_orders_enabled,
            real_money_enabled=intent.real_money_enabled,
        )
    )


def _tick_payload(
    *,
    schema_version: str,
    status_value: str,
    accepted: bool,
    tick_id: str,
    run_plan_id: str,
    upstream_report_digest: str,
    instrument_id: str,
    action_value: str,
    intent_type_value: str,
    quantity: str,
    limit_price: str | None,
    strategy_id: str,
    intent_digest: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "status": status_value,
        "accepted": accepted,
        "tick_id": tick_id,
        "run_plan_id": run_plan_id,
        "upstream_report_digest": upstream_report_digest,
        "instrument_id": instrument_id,
        "action": action_value,
        "intent_type": intent_type_value,
        "quantity": quantity,
        "limit_price": limit_price,
        "strategy_id": strategy_id,
        "intent_digest": intent_digest,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
    }


def build_paper_trade_tick(
    *,
    tick_id: str,
    action: PaperTradeIntentAction | str,
    intent_type: PaperTradeIntentType | str,
    instrument_id: str,
    quantity: str,
    strategy_id: str,
    run_plan_id: str,
    upstream_report_digest: str,
    correlation_id: str,
    limit_price: str | None = None,
    metadata: Mapping[str, str] | None = None,
    paper_only: bool = True,
    real_orders_enabled: bool = False,
    real_money_enabled: bool = False,
) -> PaperTradeTick:
    """Render a deterministic, fail-closed verdict over a caller-supplied paper trade intent.

    An empty ``correlation_id`` or non ``Mapping[str, str]`` metadata raises ``PaperTradeTickError``. The
    tick is ACCEPTED only when ids are non-empty, ``action``/``intent_type`` are known, ``quantity`` is a
    strict decimal string with the right sign for the action (zero for HOLD, positive for BUY/SELL/REDUCE/
    FLATTEN), any ``limit_price`` is a positive decimal string (required for a priced executable intent and
    absent for HOLD), the ``upstream_report_digest`` is 64-hex, no forbidden BIST/live/order-routing/
    scheduler/connector/shadow token appears, and the paper-safety triple holds; a missing upstream digest
    yields INSUFFICIENT_EVIDENCE and every other violation yields REJECTED. Records intent evidence only —
    no execution, routing, fill, or PnL. Deterministic and immutable.
    """
    if not _is_non_empty_string(correlation_id):
        raise PaperTradeTickError("paper_trade_tick:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)

    action_enum = _coerce_action(action)
    type_enum = _coerce_intent_type(intent_type)
    action_value = action_enum.value if action_enum is not None else (action if isinstance(action, str) else "")
    intent_type_value = (
        type_enum.value if type_enum is not None else (intent_type if isinstance(intent_type, str) else "")
    )
    instrument_value = instrument_id if isinstance(instrument_id, str) else ""
    strategy_value = strategy_id if isinstance(strategy_id, str) else ""
    run_plan_value = run_plan_id if isinstance(run_plan_id, str) else ""
    quantity_value = quantity if isinstance(quantity, str) else ""
    limit_price_value = limit_price if isinstance(limit_price, str) else None
    upstream_value = upstream_report_digest if isinstance(upstream_report_digest, str) else ""

    hard: list[str] = []
    insufficient: list[str] = []
    needs: list[str] = []

    if not _is_non_empty_string(tick_id):
        hard.append("paper_trade_tick:tick_id_invalid")
    if not _is_non_empty_string(instrument_id):
        hard.append("paper_trade_tick:instrument_id_invalid")
    if not _is_non_empty_string(strategy_id):
        hard.append("paper_trade_tick:strategy_id_invalid")
    if not _is_non_empty_string(run_plan_id):
        hard.append("paper_trade_tick:run_plan_id_invalid")
    if action_enum is None:
        hard.append("paper_trade_tick:action_unknown")
    if type_enum is None:
        hard.append("paper_trade_tick:intent_type_unknown")

    if not _is_non_empty_string(upstream_report_digest):
        insufficient.append("paper_trade_tick:upstream_report_digest_missing")
    elif not _is_sha256_hex(upstream_report_digest):
        hard.append("paper_trade_tick:upstream_report_digest_invalid")

    quantity_decimal = _parse_decimal(quantity)
    if quantity_decimal is None:
        hard.append("paper_trade_tick:quantity_not_decimal_string")
    elif action_enum is PaperTradeIntentAction.HOLD:
        if quantity_decimal != 0:
            hard.append("paper_trade_tick:hold_quantity_not_zero")
    elif action_enum in _EXECUTABLE_ACTIONS and not quantity_decimal > 0:
        hard.append("paper_trade_tick:quantity_not_positive")

    if limit_price is not None:
        price_decimal = _parse_decimal(limit_price)
        if price_decimal is None:
            hard.append("paper_trade_tick:limit_price_not_decimal_string")
        elif not price_decimal > 0:
            hard.append("paper_trade_tick:limit_price_not_positive")
    if action_enum in _EXECUTABLE_ACTIONS and type_enum in _PRICED_TYPES and limit_price is None:
        hard.append("paper_trade_tick:limit_price_required")
    if action_enum is PaperTradeIntentAction.HOLD and limit_price is not None:
        hard.append("paper_trade_tick:hold_limit_price_present")

    hard.extend(
        _scope_violations(
            tick_id if isinstance(tick_id, str) else "",
            instrument_value,
            strategy_value,
            run_plan_value,
            correlation_id,
            action_value,
            intent_type_value,
            *_metadata_texts(metadata_pairs),
        )
    )

    if paper_only is not True:
        hard.append("paper_trade_tick:tick_not_paper_only")
    if real_orders_enabled is not False:
        hard.append("paper_trade_tick:tick_real_orders_enabled")
    if real_money_enabled is not False:
        hard.append("paper_trade_tick:tick_real_money_enabled")

    rejection_reasons = _sorted_unique(tuple(hard))
    insufficient_reasons = _sorted_unique(tuple(insufficient))
    needs_research_reasons = _sorted_unique(tuple(needs))

    if rejection_reasons:
        status = PaperTradeTickStatus.REJECTED
    elif insufficient_reasons:
        status = PaperTradeTickStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperTradeTickStatus.NEEDS_RESEARCH
    else:
        status = PaperTradeTickStatus.ACCEPTED
    accepted = status is PaperTradeTickStatus.ACCEPTED
    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons

    tick_id_value = tick_id if isinstance(tick_id, str) else ""
    intent_digest = _canonical_digest(
        _intent_payload(
            schema_version=_INTENT_SCHEMA_VERSION,
            action_value=action_value,
            intent_type_value=intent_type_value,
            instrument_id=instrument_value,
            quantity=quantity_value,
            limit_price=limit_price_value,
            strategy_id=strategy_value,
            run_plan_id=run_plan_value,
            upstream_report_digest=upstream_value,
            correlation_id=correlation_id,
            metadata=metadata_pairs,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
    )

    payload = _tick_payload(
        schema_version=_SCHEMA_VERSION,
        status_value=status.value,
        accepted=accepted,
        tick_id=tick_id_value,
        run_plan_id=run_plan_value,
        upstream_report_digest=upstream_value,
        instrument_id=instrument_value,
        action_value=action_value,
        intent_type_value=intent_type_value,
        quantity=quantity_value,
        limit_price=limit_price_value,
        strategy_id=strategy_value,
        intent_digest=intent_digest,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        paper_only=True,
        real_orders_enabled=False,
        real_money_enabled=False,
    )
    return PaperTradeTick(
        schema_version=_SCHEMA_VERSION,
        status=status,
        accepted=accepted,
        tick_id=tick_id_value,
        run_plan_id=run_plan_value,
        upstream_report_digest=upstream_value,
        instrument_id=instrument_value,
        action=action_value,
        intent_type=intent_type_value,
        quantity=quantity_value,
        limit_price=limit_price_value,
        strategy_id=strategy_value,
        intent_digest=intent_digest,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        paper_trade_tick_digest=_canonical_digest(payload),
    )


def paper_trade_tick_to_dict(tick: PaperTradeTick) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper trade tick (deterministic shape, includes self-digest)."""
    payload = _tick_payload(
        schema_version=tick.schema_version,
        status_value=tick.status.value,
        accepted=tick.accepted,
        tick_id=tick.tick_id,
        run_plan_id=tick.run_plan_id,
        upstream_report_digest=tick.upstream_report_digest,
        instrument_id=tick.instrument_id,
        action_value=tick.action,
        intent_type_value=tick.intent_type,
        quantity=tick.quantity,
        limit_price=tick.limit_price,
        strategy_id=tick.strategy_id,
        intent_digest=tick.intent_digest,
        metadata=tick.metadata,
        rejection_reasons=tick.rejection_reasons,
        needs_research_reasons=tick.needs_research_reasons,
        correlation_id=tick.correlation_id,
        paper_only=tick.paper_only,
        real_orders_enabled=tick.real_orders_enabled,
        real_money_enabled=tick.real_money_enabled,
    )
    payload["paper_trade_tick_digest"] = tick.paper_trade_tick_digest
    return payload


def paper_trade_tick_digest(tick: PaperTradeTick) -> str:
    """Recompute the canonical tick digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(
        _tick_payload(
            schema_version=tick.schema_version,
            status_value=tick.status.value,
            accepted=tick.accepted,
            tick_id=tick.tick_id,
            run_plan_id=tick.run_plan_id,
            upstream_report_digest=tick.upstream_report_digest,
            instrument_id=tick.instrument_id,
            action_value=tick.action,
            intent_type_value=tick.intent_type,
            quantity=tick.quantity,
            limit_price=tick.limit_price,
            strategy_id=tick.strategy_id,
            intent_digest=tick.intent_digest,
            metadata=tick.metadata,
            rejection_reasons=tick.rejection_reasons,
            needs_research_reasons=tick.needs_research_reasons,
            correlation_id=tick.correlation_id,
            paper_only=tick.paper_only,
            real_orders_enabled=tick.real_orders_enabled,
            real_money_enabled=tick.real_money_enabled,
        )
    )


__all__ = [
    "PaperTradeIntent",
    "PaperTradeIntentAction",
    "PaperTradeIntentType",
    "PaperTradeTick",
    "PaperTradeTickError",
    "PaperTradeTickStatus",
    "build_paper_trade_intent",
    "build_paper_trade_tick",
    "paper_trade_intent_digest",
    "paper_trade_intent_to_dict",
    "paper_trade_tick_digest",
    "paper_trade_tick_to_dict",
]
