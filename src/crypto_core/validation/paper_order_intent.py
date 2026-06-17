"""Inert paper order intent — deterministic, paper-only artifact materialized from an admission decision.

A small, immutable, fail-closed *artifact* that materializes an ``ADMITTED``
``PaperOrderIntentAdmissionDecision`` into a frozen, digest-bound, **inert** paper order intent — a
deterministic contract artifact for a *later* deterministic fill simulator. It is not executable: it
does **not** route an order, create a venue/exchange/client order id, create a route id or execution
instruction, call live/private APIs, create fills, mutate positions, compute PnL, or reserve/mutate
capital — no DB/file/network/env IO, no wall-clock, no random, no threading, no
connector/scheduler/runtime/venue/execution/service/session/portfolio surface, no Deribit, no BIST.
``CREATED`` is the only artifact state: the admission decision already gated creation, so this builder
fails closed (raises) on any unsafe/inconsistent input rather than emitting an unsafe artifact.

Design rules:
  - Admission already gates: ``build_paper_order_intent`` consumes only an ``ADMITTED`` admission
    decision. The decision's ``decision_digest`` is recomputed via the PUBLIC
    ``paper_order_intent_admission_decision_digest`` and a mismatch fails closed; a digest-valid
    decision is then structurally re-proven (schema, ``ADMITTED`` status, ``ADMITTED`` ⟹ empty reason
    codes, paper-safety + negative attestations, well-formed digests/demand, no forbidden tokens) — a
    self-consistent forged decision still fails on those fields. A caller-supplied digest is never
    trusted.
  - No drift: the artifact's market/side/intent_type/demand/limit_price are COPIED from the
    digest-validated admission decision, not from the caller. The caller supplies only ``intent_id``,
    ``correlation_id`` (artifact provenance), and inert ``metadata``.
  - Deterministic numeric discipline: demand and ``limit_price`` are exact decimal *strings* (no
    float, no NaN/inf, no scientific/whitespace/underscore form, no negatives).
  - Deterministic digest: canonical SHA-256 over the public serializer output (enum ``.value`` and
    stable ordering) excluding the self-digest. Frozen dataclass; no input is mutated.
  - Fail closed: a wrong-typed/invalid/forbidden ``intent_id``/``correlation_id``/metadata, an
    admission-decision digest mismatch, a non-``ADMITTED`` / malformed / unsafe / token-leaking
    decision raises ``PaperOrderIntentError``. The artifact carries explicit negative attestations so
    the non-execution contract is auditable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentAdmissionDecision,
    PaperOrderIntentAdmissionStatus,
    PaperOrderIntentType,
    PaperOrderSide,
    paper_order_intent_admission_decision_digest,
)

_INTENT_SCHEMA_VERSION = "paper-order-intent.v1"
_EXPECTED_ADMISSION_SCHEMA_VERSION = "paper-order-intent-admission-decision.v1"

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling paper-sleeve / capacity / admission modules (word-bounded). A bare
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

_VALID_SIDES = frozenset(side.value for side in PaperOrderSide)
_VALID_INTENT_TYPES = frozenset(intent_type.value for intent_type in PaperOrderIntentType)


class PaperOrderIntentError(RuntimeError):
    """Raised when artifact inputs are wrong-typed/malformed or the admission decision fails re-proof."""


class PaperOrderIntentStatus(str, Enum):
    """Inert paper order intent state. ``CREATED`` only — never an execution permission."""

    CREATED = "CREATED"


@dataclass(frozen=True)
class PaperOrderIntent:
    """Deterministic, immutable inert paper order intent artifact. Non-executable. PAPER ONLY.

    Materialized from an ``ADMITTED`` ``PaperOrderIntentAdmissionDecision``. Never an order, never
    routed; carries no venue/exchange/client order id, route id, or execution instruction. The
    explicit negative attestations are always False.
    """

    schema_version: str
    status: PaperOrderIntentStatus
    intent_id: str
    admission_decision_digest: str
    request_digest: str
    capacity_decision_digest: str
    market_symbol: str
    side: str
    intent_type: str
    requested_notional: str
    requested_units: str
    limit_price: str | None
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    intent_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
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


def _is_hex64_string(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_positive_decimal(value: object) -> bool:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and parsed > 0


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperOrderIntentError("paper_order_intent:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperOrderIntentError("paper_order_intent:metadata_malformed")
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


def _admission_is_paper_safe(decision: PaperOrderIntentAdmissionDecision) -> bool:
    return (
        decision.paper_only is True
        and decision.real_orders_enabled is False
        and decision.real_money_enabled is False
        and decision.capital_reserved is False
        and decision.order_routed is False
        and decision.venue_order_id_created is False
        and decision.execution_authorized is False
        and decision.fill_created is False
        and decision.pnl_computed is False
        and decision.position_mutated is False
        and decision.live_api_called is False
        and decision.scheduler_enabled is False
        and decision.connector_invoked is False
    )


def _require_valid_admission_decision(decision: PaperOrderIntentAdmissionDecision) -> None:
    """Re-prove a digest-valid admission decision is ADMITTED, paper-safe, well-formed, and token-clean."""
    if decision.schema_version != _EXPECTED_ADMISSION_SCHEMA_VERSION:
        raise PaperOrderIntentError("paper_order_intent:admission_decision_schema_unexpected")
    if not isinstance(decision.status, PaperOrderIntentAdmissionStatus):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if decision.status is not PaperOrderIntentAdmissionStatus.ADMITTED:
        raise PaperOrderIntentError("paper_order_intent:admission_decision_not_admitted")
    # ADMITTED must carry no reason codes; a forged "ADMITTED + reasons" decision is inconsistent.
    if not isinstance(decision.reason_codes, tuple) or decision.reason_codes != _sorted_unique(decision.reason_codes):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if len(decision.reason_codes) != 0:
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if not _admission_is_paper_safe(decision):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_unsafe_flags")
    if not _is_hex64_string(decision.request_digest) or not _is_hex64_string(decision.capacity_decision_digest):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if not _is_non_empty_string(decision.market_symbol) or not _is_non_empty_string(decision.correlation_id):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if decision.side not in _VALID_SIDES or decision.intent_type not in _VALID_INTENT_TYPES:
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if not _is_positive_decimal(decision.requested_notional) or not _is_positive_decimal(decision.requested_units):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if decision.intent_type == PaperOrderIntentType.LIMIT.value:
        if not _is_positive_decimal(decision.limit_price):
            raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    elif decision.limit_price is not None:
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if not _is_metadata_tuple(decision.metadata):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")
    if _has_scope_violation(
        decision.market_symbol,
        decision.correlation_id,
        *_metadata_texts(decision.metadata),
    ):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_scope_violation")


def build_paper_order_intent(
    admission_decision: PaperOrderIntentAdmissionDecision,
    *,
    intent_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperOrderIntent:
    """Materialize an inert ``PaperOrderIntent`` from an ``ADMITTED`` admission decision (fail-closed).

    ``intent_id``/``correlation_id`` must be non-empty token-clean strings; ``metadata`` (if given) a
    ``Mapping[str, str]``. The ``admission_decision`` is re-proven via the PUBLIC
    ``paper_order_intent_admission_decision_digest`` (mismatch raises) and structurally re-proven
    (ADMITTED, paper-safe, well-formed, token-clean); a wrong-typed/forged/non-admitted decision raises
    ``PaperOrderIntentError``. The artifact COPIES market/side/intent_type/demand/limit_price from the
    decision (no caller drift), attests paper-safety + negative attestations, and never mutates the
    input. Routes no order; creates no venue/exchange/client order id, route id, execution instruction,
    fill, PnL, or position; reserves no capital; calls no live API.
    """
    if not _is_non_empty_string(intent_id):
        raise PaperOrderIntentError("paper_order_intent:intent_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperOrderIntentError("paper_order_intent:correlation_id_invalid")
    intent_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(intent_id, correlation_id, *_metadata_texts(intent_metadata)):
        raise PaperOrderIntentError("paper_order_intent:scope_violation")
    if not isinstance(admission_decision, PaperOrderIntentAdmissionDecision):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed")

    # Digest boundary: recompute the admission decision's self-digest via its PUBLIC serializer.
    try:
        expected_admission_digest = paper_order_intent_admission_decision_digest(admission_decision)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperOrderIntentError("paper_order_intent:admission_decision_malformed") from exc
    if not isinstance(admission_decision.decision_digest, str) or (
        admission_decision.decision_digest != expected_admission_digest
    ):
        raise PaperOrderIntentError("paper_order_intent:admission_decision_digest_mismatch")

    # Digest re-proved -> re-prove canonical structure / admission invariants before materializing.
    _require_valid_admission_decision(admission_decision)

    intent = PaperOrderIntent(
        schema_version=_INTENT_SCHEMA_VERSION,
        status=PaperOrderIntentStatus.CREATED,
        intent_id=intent_id,
        admission_decision_digest=admission_decision.decision_digest,
        request_digest=admission_decision.request_digest,
        capacity_decision_digest=admission_decision.capacity_decision_digest,
        market_symbol=admission_decision.market_symbol,
        side=admission_decision.side,
        intent_type=admission_decision.intent_type,
        requested_notional=admission_decision.requested_notional,
        requested_units=admission_decision.requested_units,
        limit_price=admission_decision.limit_price,
        correlation_id=correlation_id,
        metadata=intent_metadata,
        intent_digest="",
    )
    return PaperOrderIntent(
        schema_version=intent.schema_version,
        status=intent.status,
        intent_id=intent.intent_id,
        admission_decision_digest=intent.admission_decision_digest,
        request_digest=intent.request_digest,
        capacity_decision_digest=intent.capacity_decision_digest,
        market_symbol=intent.market_symbol,
        side=intent.side,
        intent_type=intent.intent_type,
        requested_notional=intent.requested_notional,
        requested_units=intent.requested_units,
        limit_price=intent.limit_price,
        correlation_id=intent.correlation_id,
        metadata=intent.metadata,
        intent_digest=paper_order_intent_digest(intent),
    )


def _intent_payload(
    *,
    schema_version: str,
    status_value: str,
    intent_id: str,
    admission_decision_digest: str,
    request_digest: str,
    capacity_decision_digest: str,
    market_symbol: str,
    side: str,
    intent_type: str,
    requested_notional: str,
    requested_units: str,
    limit_price: str | None,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    real_orders_enabled: bool,
    real_money_enabled: bool,
    capital_reserved: bool,
    order_routed: bool,
    venue_order_id_created: bool,
    exchange_id_created: bool,
    client_order_id_created: bool,
    route_id_created: bool,
    execution_instruction_created: bool,
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
        "intent_id": intent_id,
        "admission_decision_digest": admission_decision_digest,
        "request_digest": request_digest,
        "capacity_decision_digest": capacity_decision_digest,
        "market_symbol": market_symbol,
        "side": side,
        "intent_type": intent_type,
        "requested_notional": requested_notional,
        "requested_units": requested_units,
        "limit_price": limit_price,
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "real_orders_enabled": real_orders_enabled,
        "real_money_enabled": real_money_enabled,
        "capital_reserved": capital_reserved,
        "order_routed": order_routed,
        "venue_order_id_created": venue_order_id_created,
        "exchange_id_created": exchange_id_created,
        "client_order_id_created": client_order_id_created,
        "route_id_created": route_id_created,
        "execution_instruction_created": execution_instruction_created,
        "execution_authorized": execution_authorized,
        "fill_created": fill_created,
        "pnl_computed": pnl_computed,
        "position_mutated": position_mutated,
        "live_api_called": live_api_called,
        "scheduler_enabled": scheduler_enabled,
        "connector_invoked": connector_invoked,
    }


def _intent_payload_from(intent: PaperOrderIntent) -> dict[str, object]:
    return _intent_payload(
        schema_version=intent.schema_version,
        status_value=intent.status.value,
        intent_id=intent.intent_id,
        admission_decision_digest=intent.admission_decision_digest,
        request_digest=intent.request_digest,
        capacity_decision_digest=intent.capacity_decision_digest,
        market_symbol=intent.market_symbol,
        side=intent.side,
        intent_type=intent.intent_type,
        requested_notional=intent.requested_notional,
        requested_units=intent.requested_units,
        limit_price=intent.limit_price,
        correlation_id=intent.correlation_id,
        metadata=intent.metadata,
        paper_only=intent.paper_only,
        real_orders_enabled=intent.real_orders_enabled,
        real_money_enabled=intent.real_money_enabled,
        capital_reserved=intent.capital_reserved,
        order_routed=intent.order_routed,
        venue_order_id_created=intent.venue_order_id_created,
        exchange_id_created=intent.exchange_id_created,
        client_order_id_created=intent.client_order_id_created,
        route_id_created=intent.route_id_created,
        execution_instruction_created=intent.execution_instruction_created,
        execution_authorized=intent.execution_authorized,
        fill_created=intent.fill_created,
        pnl_computed=intent.pnl_computed,
        position_mutated=intent.position_mutated,
        live_api_called=intent.live_api_called,
        scheduler_enabled=intent.scheduler_enabled,
        connector_invoked=intent.connector_invoked,
    )


def paper_order_intent_to_dict(intent: PaperOrderIntent) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an inert paper order intent (deterministic shape, self-digest)."""
    payload = _intent_payload_from(intent)
    payload["intent_digest"] = intent.intent_digest
    return payload


def paper_order_intent_digest(intent: PaperOrderIntent) -> str:
    """Recompute the canonical intent digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_intent_payload_from(intent))


__all__ = [
    "PaperOrderIntent",
    "PaperOrderIntentError",
    "PaperOrderIntentStatus",
    "build_paper_order_intent",
    "paper_order_intent_digest",
    "paper_order_intent_to_dict",
]
