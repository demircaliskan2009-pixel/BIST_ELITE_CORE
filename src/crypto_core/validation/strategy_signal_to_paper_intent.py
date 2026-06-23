"""Strategy signal to paper order-intent bridge — deterministic, paper-only, fail-closed.

The first integration seam of phase-map slice 2 (``docs/crypto_core/paper_trading_phase_map.md``):
convert a digest-bound ``StrategySpec`` plus a caller-supplied deterministic signal into the existing,
inert ``PaperOrderIntentRequest`` contract (merged earlier), binding the produced request by digest. It is
a *bridge / probe*, NOT an engine: it runs no backtest, simulates no fills, mutates no positions, computes
no PnL, runs no episode, evaluates no capacity decision, routes no order, and adds no
runtime/persistence/scheduler/execution/venue path. It answers one question: "given this strategy spec, does
this signal map to a valid, inert paper order-intent request?"

Digest binding (trust boundary): the supplied ``StrategySpec`` is serialized EXACTLY ONCE via the public
serializer and round-tripped through canonical JSON into a single immutable snapshot; the spec digest
recompute, the full ``validate_strategy_spec``, the forbidden-scope scan, and every bound identity/field all
derive from that ONE snapshot (closing a TOCTOU where a stateful/mutable source — e.g. ``risk_caps`` — could
let the digest and validation observe different reads). The recomputed digest must equal the caller-supplied
``expected_spec_digest`` (the caller's INDEPENDENT provenance anchor), AND a matching digest is never
sufficient: the snapshot must pass full validation and equal the validator-normalized canonical payload (so a
noncanonical/whitespace identity cannot be carried READY). A READY bridge also requires the signal to be
consistent with the spec (supported market type, symbol in the spec's instrument universe, clean scope) and
to produce a valid ``PaperOrderIntentRequest`` re-proven by exact type, recomputed digest, lower-contract
paper-safety, and field equality — its ``request_digest`` is bound into the bridge digest. The bridge does
NOT re-derive the spec's economics or prove edge.

Produces the inert ``PaperOrderIntentRequest`` (an explicit demand descriptor — never an order, never
routed) via the existing public builder; it carries the caller-supplied ``capacity_decision_digest`` the
downstream capacity/admission flow will evaluate the request against. This bridge neither creates nor
evaluates that capacity decision.

Non-overclaim: a READY bridge is a deterministic signal-to-intent mapping only. It is NOT PRDV4 Stage 4
completion, NOT live readiness, NOT shadow readiness, NOT proof of profitability, NOT proof of edge, and NOT
an execution / fill / position / PnL proof. Those attestations are carried as explicit ``False`` flags.

Paper only: no fees/PnL/equity/capital/margin/balance; reserves/mutates no capital; routes no order; creates
no venue/exchange/client order id / route id / execution instruction; calls no live/private API; schedules
nothing; runs no auto-loop; performs no wall-clock/random/IO/persistence/network. It does NOT import or use
``crypto_core.service.readiness`` or ``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime/venue
surface), no Deribit, no BIST.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.strategy.spec import (
    StrategySpec,
    StrategySpecMarketType,
    strategy_spec_to_dict,
    validate_strategy_spec,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentRequest,
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    paper_order_intent_request_to_dict,
)

_SCHEMA_VERSION = "strategy-signal-to-paper-intent.v1"
# The lower-contract schema version the produced paper order-intent request must carry.
_EXPECTED_REQUEST_SCHEMA_VERSION = "paper-order-intent-request.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Market types this bridge supports (mirrors the strategy-spec PR1 supported set: perp only).
_SUPPORTED_MARKET_TYPES = (StrategySpecMarketType.USDT_PERP, StrategySpecMarketType.INVERSE_PERP)
_SUPPORTED_MARKET_TYPE_VALUES = tuple(market_type.value for market_type in _SUPPORTED_MARKET_TYPES)

# Strict decimal-string grammar (mirrors the paper order-intent request contract): optional sign, no leading
# zeros (except a bare ``0``), optional fraction. Positivity is enforced separately.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling paper modules (word-bounded). Market-data terms scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class StrategySignalToPaperIntentError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed spec/ids/digests/side/type/decimals/metadata)."""


class StrategySignalToPaperIntentStatus(str, Enum):
    """Terminal bridge verdict. Never an execution permission / order routing / capital / readiness action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class StrategySignalToPaperIntent:
    """Deterministic, immutable, digest-bound mapping from a strategy signal to an inert paper order-intent request.

    Records the READY/REJECTED verdict, the spec it was decided against (and the caller's independent expected
    anchor), the produced ``PaperOrderIntentRequest`` digest (or empty on rejection), and the normalized
    signal/request descriptor by value. Paper only; routes no order; creates no fill/position/PnL/capital.
    ``paper_only`` True; every safety attestation False; every non-overclaim attestation False. PAPER ONLY —
    NOT PRDV4 Stage 4 completion, NOT live/shadow readiness, NOT profitability/edge proof, NOT an execution
    proof.
    """

    schema_version: str
    status: StrategySignalToPaperIntentStatus
    ready: bool
    strategy_id: str
    strategy_version: str
    signal_id: str
    run_id: str
    correlation_id: str
    expected_spec_digest: str
    spec_digest: str
    market_symbol: str
    side: str
    intent_type: str
    requested_units: str
    requested_notional: str
    limit_price: str | None
    capacity_decision_digest: str
    paper_order_intent_request_digest: str
    rejection_reasons: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    bridge_digest: str
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
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    # Non-overclaim attestations (a READY bridge proves none of these).
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    """Exact plain ``str`` (no subclass) that is non-empty after strip.

    Caller-supplied ids/symbol/side/type are validated with ``type(value) is str`` (not ``isinstance``) so a
    ``str`` subclass overriding ``strip()``/``__eq__``/``__hash__`` cannot smuggle an empty/scope-violating
    value past the gate.
    """
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


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


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        # Exact plain ``str`` only (no subclass) so a custom-hash/eq/strip subclass cannot bypass uniqueness
        # or the scope guard or collapse into a collision-prone key.
        if type(key) is not str or type(value) is not str:
            raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:metadata_malformed")
        items.append((str(key), str(value)))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


def _positive_decimal(value: object) -> Decimal | None:
    """Return an exact finite, strictly-positive ``Decimal`` for a strict decimal string, else ``None``."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def build_strategy_signal_to_paper_intent(
    spec: StrategySpec,
    *,
    expected_spec_digest: str,
    signal_id: str,
    run_id: str,
    correlation_id: str,
    market_symbol: str,
    side: PaperOrderSide,
    intent_type: PaperOrderIntentType,
    requested_units: str,
    requested_notional: str,
    capacity_decision_digest: str,
    limit_price: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> StrategySignalToPaperIntent:
    """Bridge one strategy signal over a digest-bound ``StrategySpec`` into an inert paper order-intent request.

    ``spec`` must be a ``StrategySpec`` and ``expected_spec_digest`` / ``capacity_decision_digest`` exact plain
    64-lowercase-hex ``str``. ``signal_id`` / ``run_id`` / ``correlation_id`` / ``market_symbol`` must be exact
    plain non-empty ``str``; ``side`` / ``intent_type`` must be the exact ``PaperOrderSide`` /
    ``PaperOrderIntentType`` enum members (a raw/lookalike string is rejected); ``requested_units`` /
    ``requested_notional`` exact ``str``; ``limit_price`` ``str`` or ``None``; ``metadata``
    ``Mapping[str, str]`` or ``None``. A wrong-typed input, an empty id, a malformed digest/decimal/metadata,
    or a forbidden BIST/live/order/scheduler/shadow token raises ``StrategySignalToPaperIntentError``.

    READY only when the spec re-digests to ``expected_spec_digest``, the spec passes the repo's full
    ``validate_strategy_spec`` (a matching digest alone is never sufficient), the full spec payload is
    scope-clean (no BIST/live/venue tokens such as ``deribit``), the spec market type is supported, the signal
    symbol is in the spec's instrument universe, the decimals are valid, and a valid ``PaperOrderIntentRequest``
    is produced AND re-proven by exact type, recomputed digest, and field-by-field equality with the signal
    (its ``request_digest`` is bound here). Every other outcome maps fail-closed to REJECTED. Deterministic and
    immutable; no wall-clock/random/IO; paper only; NOT PRDV4 Stage 4 / live / shadow readiness and NOT a
    profitability/edge/execution proof.
    """
    if not isinstance(spec, StrategySpec):
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:spec_malformed")
    if not _is_hex64_string(expected_spec_digest):
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:expected_spec_digest_invalid")
    if not _is_hex64_string(capacity_decision_digest):
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:capacity_decision_digest_invalid")
    for name, value in (
        ("signal_id", signal_id),
        ("run_id", run_id),
        ("correlation_id", correlation_id),
        ("market_symbol", market_symbol),
    ):
        if not _is_plain_non_empty_string(value):
            raise StrategySignalToPaperIntentError(f"strategy_signal_to_paper_intent:{name}_invalid")
    # Strict enum boundary: a raw/lookalike string ("BUY"/"buy"/"market") never passes — exact enum only.
    if type(side) is not PaperOrderSide:
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:side_invalid")
    if type(intent_type) is not PaperOrderIntentType:
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:intent_type_invalid")
    if type(requested_units) is not str or type(requested_notional) is not str:
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:decimal_field_malformed")
    if limit_price is not None and type(limit_price) is not str:
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:limit_price_malformed")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(signal_id, run_id, correlation_id, market_symbol, *_metadata_texts(metadata_pairs)):
        raise StrategySignalToPaperIntentError("strategy_signal_to_paper_intent:scope_violation")

    hard: list[str] = []
    request_digest = ""

    # Single canonical StrategySpec snapshot: serialize the (possibly mutable/stateful) spec EXACTLY ONCE via
    # the public serializer and round-trip through canonical JSON into immutable primitives. The digest
    # recompute, full validation, scope scan, and every bound identity/field read all derive from this ONE
    # snapshot — closing a TOCTOU where digest and validation could otherwise observe different reads of a
    # mutable source (e.g. stateful ``risk_caps``).
    snapshot = _capture_spec_snapshot(spec)
    strategy_id = ""
    strategy_version = ""
    spec_digest_value = ""
    universe: tuple[str, ...] = ()
    if snapshot is None:
        hard.append("strategy_signal_to_paper_intent:spec_invalid")
    else:
        strategy_id = snapshot.get("strategy_id") if isinstance(snapshot.get("strategy_id"), str) else ""
        strategy_version = snapshot.get("strategy_version") if isinstance(snapshot.get("strategy_version"), str) else ""

        # Digest boundary: recompute the spec digest FROM the single snapshot (the same canonical SHA-256 over
        # the public serializer output as ``strategy_spec_digest``) and require equality with the caller's
        # independent expected anchor. A matching digest alone is never sufficient (see validation below).
        spec_digest_value = _canonical_digest(snapshot)
        if spec_digest_value != expected_spec_digest:
            hard.append("strategy_signal_to_paper_intent:spec_digest_mismatch")

        # Full validation of the SAME snapshot, then require the validator-normalized canonical payload to
        # equal the snapshot exactly. A digest-valid but invalid spec fails closed; a noncanonical supplied
        # spec (e.g. whitespace ``strategy_id``) is normalized by the validator and must not be carried READY.
        try:
            validation = validate_strategy_spec(snapshot)
        except Exception:  # noqa: BLE001 - any validator failure is a fail-closed rejection
            validation = None
        if validation is None or not validation.accepted or validation.spec is None:
            hard.append("strategy_signal_to_paper_intent:spec_invalid")
        else:
            try:
                normalized = strategy_spec_to_dict(validation.spec)
            except Exception:  # noqa: BLE001 - an unserializable normalized spec is a fail-closed rejection
                normalized = None
            if normalized != snapshot:
                hard.append("strategy_signal_to_paper_intent:spec_noncanonical")

        # Full-payload forbidden scope scan over the SAME snapshot (catches ``deribit``/BIST/live anywhere the
        # spec validator does not itself reject, e.g. inside ``venue_assumptions``).
        if _spec_payload_scope_violation(snapshot):
            hard.append("strategy_signal_to_paper_intent:spec_scope_violation")

        # Supportedness re-proof from the snapshot's market type (specific reason code; also covered by
        # spec_invalid for unsupported types).
        if snapshot.get("market_type") not in _SUPPORTED_MARKET_TYPE_VALUES:
            hard.append("strategy_signal_to_paper_intent:spec_market_type_unsupported")

        raw_universe = snapshot.get("instrument_universe")
        universe = (
            tuple(item for item in raw_universe if isinstance(item, str)) if isinstance(raw_universe, list) else ()
        )

    # Signal-vs-spec consistency: the traded symbol must be in the snapshot's instrument universe.
    if market_symbol not in universe:
        hard.append("strategy_signal_to_paper_intent:signal_symbol_not_in_universe")

    # Signal decimal validation (value-level -> REJECTED reason codes, not raises).
    if _positive_decimal(requested_units) is None:
        hard.append("strategy_signal_to_paper_intent:signal_units_invalid")
    if _positive_decimal(requested_notional) is None:
        hard.append("strategy_signal_to_paper_intent:signal_notional_invalid")
    if intent_type is PaperOrderIntentType.LIMIT:
        if _positive_decimal(limit_price) is None:
            hard.append("strategy_signal_to_paper_intent:signal_limit_price_invalid")
    elif intent_type is PaperOrderIntentType.MARKET and limit_price is not None:
        hard.append("strategy_signal_to_paper_intent:signal_limit_price_invalid")

    # Produce the real inert paper order-intent request only when the signal is fully valid, then re-prove the
    # builder output by exact type, recomputed digest, and field-by-field equality with the validated signal —
    # a foreign / wrong-typed / digest-mismatched / payload-divergent request can never bind a READY bridge.
    # Any builder failure (defensive) maps fail-closed to REJECTED rather than crashing.
    if not hard:
        try:
            request = build_paper_order_intent_request(
                request_id=signal_id,
                capacity_decision_digest=capacity_decision_digest,
                market_symbol=market_symbol,
                side=side,
                intent_type=intent_type,
                requested_notional=requested_notional,
                requested_units=requested_units,
                limit_price=limit_price,
                correlation_id=correlation_id,
                metadata=dict(metadata_pairs),
            )
        except Exception:  # noqa: BLE001 - any builder failure is a fail-closed rejection, never a crash
            hard.append("strategy_signal_to_paper_intent:paper_order_intent_request_construction_failed")
        else:
            request_digest, reproof_reason = _reprove_request(
                request,
                signal_id=signal_id,
                correlation_id=correlation_id,
                market_symbol=market_symbol,
                side=side,
                intent_type=intent_type,
                requested_units=requested_units,
                requested_notional=requested_notional,
                limit_price=limit_price,
                capacity_decision_digest=capacity_decision_digest,
                metadata=metadata_pairs,
            )
            if reproof_reason is not None:
                hard.append(reproof_reason)

    rejection_reasons = tuple(sorted(set(hard)))
    status = (
        StrategySignalToPaperIntentStatus.REJECTED if rejection_reasons else StrategySignalToPaperIntentStatus.READY
    )

    return _finalize_bridge(
        status=status,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        signal_id=signal_id,
        run_id=run_id,
        correlation_id=correlation_id,
        expected_spec_digest=expected_spec_digest,
        spec_digest=spec_digest_value,
        market_symbol=market_symbol,
        # Store canonical plain-string enum VALUES (never enum objects) in the dataclass / serializer / digest.
        side=side.value,
        intent_type=intent_type.value,
        requested_units=requested_units,
        requested_notional=requested_notional,
        limit_price=limit_price,
        capacity_decision_digest=capacity_decision_digest,
        paper_order_intent_request_digest=request_digest,
        rejection_reasons=rejection_reasons,
        metadata=metadata_pairs,
    )


def _capture_spec_snapshot(spec: StrategySpec) -> dict[str, object] | None:
    """Serialize the spec via the PUBLIC serializer EXACTLY ONCE and ROUND-TRIP through canonical JSON.

    The (possibly mutable/stateful) spec is read once here and never again — neither for digest, validation,
    scope, nor identity. The returned dict is exact immutable primitives, so the digest recompute, full
    validation, scope scan, and every bound field all derive from this single snapshot (closing a TOCTOU where
    a second read of a stateful source — e.g. ``risk_caps`` — could diverge). The canonical JSON round-trip
    matches ``strategy_spec_digest``'s serializer exactly for finite specs. Returns ``None`` (fail-closed) on
    any serialization failure or a non-finite (``NaN``/``Infinity``) payload.
    """
    try:
        raw = strategy_spec_to_dict(spec)
        snapshot = json.loads(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        )
    except Exception:  # noqa: BLE001 - any serialization failure / non-finite payload is a fail-closed rejection
        return None
    return snapshot if isinstance(snapshot, dict) else None


def _spec_payload_scope_violation(payload: object) -> bool:
    """Recursively scope-scan the full canonical spec payload (exact plain strings only).

    Catches forbidden BIST/live/venue tokens (e.g. ``deribit`` in ``venue_assumptions``) anywhere in the
    spec — keys, list/tuple items, and nested mappings — that the spec validator does not itself reject.
    Non-string leaves are ignored (never coerced); the digest/validation gates already cover their shape.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if isinstance(key, str) and _has_scope_violation(key):
                return True
            if _spec_payload_scope_violation(value):
                return True
        return False
    if isinstance(payload, (list, tuple)):
        return any(_spec_payload_scope_violation(item) for item in payload)
    if isinstance(payload, str):
        return _has_scope_violation(payload)
    return False


# Exact JSON-safe shape the PUBLIC ``paper_order_intent_request_to_dict`` emits for a genuine request, used to
# exact-type validate the RAW serializer output BEFORE any canonical-JSON normalization. String + bool field
# groups, plus ``limit_price`` (str | None) and ``metadata`` (list of [str, str]) special cases.
_RAW_REQUEST_STRING_FIELDS = (
    "schema_version",
    "request_id",
    "capacity_decision_digest",
    "market_symbol",
    "side",
    "intent_type",
    "requested_notional",
    "requested_units",
    "correlation_id",
    "request_digest",
)
_RAW_REQUEST_BOOL_FIELDS = ("paper_only", "real_orders_enabled", "real_money_enabled")
_RAW_REQUEST_KEYS = frozenset((*_RAW_REQUEST_STRING_FIELDS, *_RAW_REQUEST_BOOL_FIELDS, "limit_price", "metadata"))


def _raw_request_payload(request: PaperOrderIntentRequest) -> object | None:
    """Serialize the request via its PUBLIC serializer EXACTLY ONCE (no JSON normalization yet).

    The (possibly stateful) request is read once here and never again — every later proof derives from this one
    raw payload. Returns ``None`` (fail-closed) on any serialization failure (e.g. a tampered non-enum side).
    """
    try:
        return paper_order_intent_request_to_dict(request)
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None


def _is_exact_raw_request_payload(raw: object) -> bool:
    """Exact-type validate the RAW public-serializer output BEFORE canonical-JSON normalization.

    A genuine ``build_paper_order_intent_request`` emits only plain JSON primitives/containers, so this rejects
    ANY non-plain type using ``type(x) is ...`` (never ``isinstance``): ``str`` subclasses (even with correct
    content, e.g. ``LiarStr(real.request_digest)``), ``dict``/``list``/``tuple`` subclasses, arbitrary
    ``Mapping``/``Sequence`` objects, ``Decimal``/``Enum``, ``float``/NaN/Infinity, ``bool`` where a string is
    expected, and unexpected/missing keys. This closes the gap where the later canonical-JSON round-trip would
    otherwise launder a subclass into a plain ``str`` that then passes the content equality. Metadata must be
    the lower serializer's exact canonical shape: an outer plain ``list`` of exact-length-2 plain ``list`` pairs
    of plain ``str`` key/value. (The lower serializer rebuilds metadata via a list comprehension, so an
    outer/pair container subclass is already normalized to a plain ``list`` there; only the surviving key/value
    element types remain to be exact-checked here.) No coercion; the JSON round-trip is never relied on to
    sanitize types.
    """
    if type(raw) is not dict:
        return False
    if {key for key in raw if type(key) is str} != _RAW_REQUEST_KEYS:
        return False
    for field in _RAW_REQUEST_STRING_FIELDS:
        if type(raw[field]) is not str:
            return False
    for field in _RAW_REQUEST_BOOL_FIELDS:
        if type(raw[field]) is not bool:
            return False
    limit_price = raw["limit_price"]
    if limit_price is not None and type(limit_price) is not str:
        return False
    metadata = raw["metadata"]
    if type(metadata) is not list:
        return False
    for pair in metadata:
        if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            return False
    return True


def _canonical_request_snapshot(raw: object) -> dict[str, object] | None:
    """Round-trip the exact-type-validated RAW payload through canonical JSON into plain primitives.

    Only ever called after ``_is_exact_raw_request_payload`` has proven ``raw`` is exact JSON-safe primitives,
    so this is a deterministic canonicalization (stable key order), not a type sanitizer. Returns ``None``
    (fail-closed) on any serialization failure.
    """
    try:
        snapshot = json.loads(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        )
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None
    return snapshot if isinstance(snapshot, dict) else None


def _request_snapshot_digest(snapshot: dict[str, object]) -> str:
    """Recompute the request digest FROM the single captured snapshot (excluding the self-digest field).

    Applies the same canonical SHA-256 over the public-serializer payload as the lower-contract helper
    ``paper_order_intent_request_digest`` — but over the ONE already-captured snapshot, never a second read of
    the (possibly stateful) request object. A regression proves this equals
    ``paper_order_intent_request_digest(request)`` for a canonical request, so the digest the bridge binds and
    the payload it proves equal both derive from the same single read (closing the request-boundary TOCTOU).
    """
    payload = {key: value for key, value in snapshot.items() if key != "request_digest"}
    return _canonical_digest(payload)


def _reprove_request(
    request: object,
    *,
    signal_id: str,
    correlation_id: str,
    market_symbol: str,
    side: PaperOrderSide,
    intent_type: PaperOrderIntentType,
    requested_units: str,
    requested_notional: str,
    limit_price: str | None,
    capacity_decision_digest: str,
    metadata: tuple[tuple[str, str], ...],
) -> tuple[str, str | None]:
    """Re-prove the builder output against ONE canonical request snapshot: exact type, snapshot-derived digest,
    lower-contract safety, and field equality with the validated signal.

    The (possibly stateful) request is read EXACTLY ONCE — via ``_raw_request_payload`` (public serializer) —
    and the raw payload is exact-type validated as plain JSON primitives BEFORE being canonicalized through a
    JSON round-trip. The bound digest is recomputed FROM that snapshot, and the carried digest, schema/paper-
    safety attestations, and every field comparison also derive from that ONE snapshot. No second read of the
    live request occurs (only the exact ``type`` is inspected before capture), so a request whose digest read
    and equality read could otherwise diverge (e.g. mutating ``metadata``) cannot bind a foreign payload digest
    into a READY bridge.

    Returns ``(request_digest, None)`` only when the request is the exact ``PaperOrderIntentRequest`` type, its
    raw serializer payload is exact JSON-safe primitives (no ``str``/container subclass — even with correct
    content), its carried ``request_digest`` is an exact plain lowercase-hex64 string equal to the snapshot-
    derived digest, its snapshot schema/paper-safety attestations are correct, and every bound field equals the
    validated signal; else ``("", <reason>)``. The proofs run on plain primitives, so a foreign / wrong-typed /
    digest-tampered / unsafe / equality-liar / ``str``-subclass / stateful / payload-divergent request can
    never bind a READY bridge.
    """
    # Exact type is the ONLY raw attribute inspected; every value below derives from the single serializer read.
    if type(request) is not PaperOrderIntentRequest:
        return "", "strategy_signal_to_paper_intent:request_type_mismatch"

    # Single PUBLIC serializer read of the (possibly stateful) request — stored once; every proof below derives
    # from this one raw payload (no second read, no public digest helper on the live object).
    raw = _raw_request_payload(request)
    if raw is None:
        return "", "strategy_signal_to_paper_intent:request_payload_mismatch"

    # Raw exact-type boundary BEFORE any JSON normalization: a genuine builder emits only plain JSON
    # primitives/containers, so reject ANY non-plain type (str/list/dict subclass — even with correct content
    # such as ``LiarStr(real.request_digest)`` — Decimal/Enum/float, bool-as-string, unexpected/missing keys).
    # This closes the gap where the canonical-JSON round-trip would otherwise launder a subclass into a plain
    # ``str`` that then passes the content equality.
    if not _is_exact_raw_request_payload(raw):
        return "", "strategy_signal_to_paper_intent:request_payload_type_violation"

    # Canonical snapshot from the exact-type-validated raw payload (deterministic key order, plain primitives).
    snapshot = _canonical_request_snapshot(raw)
    if snapshot is None:
        return "", "strategy_signal_to_paper_intent:request_payload_mismatch"

    # Digest boundary: recompute the request digest FROM the single snapshot and require the snapshot-carried
    # ``request_digest`` to be an exact plain lowercase-hex64 string equal to it. Both the digest the bridge
    # binds and the payload it proves equal come from this one read, so a stateful request cannot show foreign
    # metadata to the digest and expected metadata to the equality reproof.
    carried_digest = snapshot.get("request_digest")
    snapshot_digest = _request_snapshot_digest(snapshot)
    if type(carried_digest) is not str or not _is_hex64_string(carried_digest) or carried_digest != snapshot_digest:
        return "", "strategy_signal_to_paper_intent:request_digest_mismatch"

    # Lower-contract schema + paper-safety re-proof from the same single snapshot (exact values).
    if (
        snapshot.get("schema_version") != _EXPECTED_REQUEST_SCHEMA_VERSION
        or snapshot.get("paper_only") is not True
        or snapshot.get("real_orders_enabled") is not False
        or snapshot.get("real_money_enabled") is not False
    ):
        return "", "strategy_signal_to_paper_intent:request_safety_violation"

    # Field equality vs the validated bridge inputs — both sides are plain primitives (the snapshot from the
    # canonical round-trip, the expected values from the already-validated signal).
    expected_metadata = [[key, value] for key, value in metadata]
    if (
        snapshot.get("request_id") != signal_id
        or snapshot.get("correlation_id") != correlation_id
        or snapshot.get("market_symbol") != market_symbol
        or snapshot.get("side") != side.value
        or snapshot.get("intent_type") != intent_type.value
        or snapshot.get("requested_units") != requested_units
        or snapshot.get("requested_notional") != requested_notional
        or snapshot.get("limit_price") != limit_price
        or snapshot.get("capacity_decision_digest") != capacity_decision_digest
        or snapshot.get("metadata") != expected_metadata
    ):
        return "", "strategy_signal_to_paper_intent:request_payload_mismatch"
    return snapshot_digest, None


def _finalize_bridge(
    *,
    status: StrategySignalToPaperIntentStatus,
    strategy_id: str,
    strategy_version: str,
    signal_id: str,
    run_id: str,
    correlation_id: str,
    expected_spec_digest: str,
    spec_digest: str,
    market_symbol: str,
    side: str,
    intent_type: str,
    requested_units: str,
    requested_notional: str,
    limit_price: str | None,
    capacity_decision_digest: str,
    paper_order_intent_request_digest: str,
    rejection_reasons: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> StrategySignalToPaperIntent:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "ready": status is StrategySignalToPaperIntentStatus.READY,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "signal_id": signal_id,
        "run_id": run_id,
        "correlation_id": correlation_id,
        "expected_spec_digest": expected_spec_digest,
        "spec_digest": spec_digest,
        "market_symbol": market_symbol,
        "side": side,
        "intent_type": intent_type,
        "requested_units": requested_units,
        "requested_notional": requested_notional,
        "limit_price": limit_price,
        "capacity_decision_digest": capacity_decision_digest,
        "paper_order_intent_request_digest": paper_order_intent_request_digest,
        "rejection_reasons": rejection_reasons,
        "metadata": metadata,
    }
    seed = StrategySignalToPaperIntent(bridge_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, strategy_signal_to_paper_intent_digest(seed))


def _replace_digest(bridge: StrategySignalToPaperIntent, digest: str) -> StrategySignalToPaperIntent:
    fields = _bridge_fields(bridge)
    fields["bridge_digest"] = digest
    return StrategySignalToPaperIntent(**fields)  # type: ignore[arg-type]


def _bridge_fields(bridge: StrategySignalToPaperIntent) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "status": bridge.status,
        "ready": bridge.ready,
        "strategy_id": bridge.strategy_id,
        "strategy_version": bridge.strategy_version,
        "signal_id": bridge.signal_id,
        "run_id": bridge.run_id,
        "correlation_id": bridge.correlation_id,
        "expected_spec_digest": bridge.expected_spec_digest,
        "spec_digest": bridge.spec_digest,
        "market_symbol": bridge.market_symbol,
        "side": bridge.side,
        "intent_type": bridge.intent_type,
        "requested_units": bridge.requested_units,
        "requested_notional": bridge.requested_notional,
        "limit_price": bridge.limit_price,
        "capacity_decision_digest": bridge.capacity_decision_digest,
        "paper_order_intent_request_digest": bridge.paper_order_intent_request_digest,
        "rejection_reasons": bridge.rejection_reasons,
        "metadata": bridge.metadata,
    }


def _bridge_payload_from(bridge: StrategySignalToPaperIntent) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "status": bridge.status.value,
        "ready": bridge.ready,
        "strategy_id": bridge.strategy_id,
        "strategy_version": bridge.strategy_version,
        "signal_id": bridge.signal_id,
        "run_id": bridge.run_id,
        "correlation_id": bridge.correlation_id,
        "expected_spec_digest": bridge.expected_spec_digest,
        "spec_digest": bridge.spec_digest,
        "market_symbol": bridge.market_symbol,
        "side": bridge.side,
        "intent_type": bridge.intent_type,
        "requested_units": bridge.requested_units,
        "requested_notional": bridge.requested_notional,
        "limit_price": bridge.limit_price,
        "capacity_decision_digest": bridge.capacity_decision_digest,
        "paper_order_intent_request_digest": bridge.paper_order_intent_request_digest,
        "rejection_reasons": list(bridge.rejection_reasons),
        "metadata": _serialize_metadata(bridge.metadata),
        "paper_only": bridge.paper_only,
        "real_orders_enabled": bridge.real_orders_enabled,
        "real_money_enabled": bridge.real_money_enabled,
        "capital_reserved": bridge.capital_reserved,
        "order_routed": bridge.order_routed,
        "venue_order_id_created": bridge.venue_order_id_created,
        "execution_authorized": bridge.execution_authorized,
        "fill_created": bridge.fill_created,
        "pnl_computed": bridge.pnl_computed,
        "position_mutated": bridge.position_mutated,
        "live_api_called": bridge.live_api_called,
        "scheduler_enabled": bridge.scheduler_enabled,
        "auto_loop_enabled": bridge.auto_loop_enabled,
        "connector_invoked": bridge.connector_invoked,
        "prdv4_stage4_complete": bridge.prdv4_stage4_complete,
        "live_ready": bridge.live_ready,
        "shadow_ready": bridge.shadow_ready,
        "profitability_proven": bridge.profitability_proven,
        "edge_proven": bridge.edge_proven,
    }


def strategy_signal_to_paper_intent_to_dict(bridge: StrategySignalToPaperIntent) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a bridge (deterministic shape, includes self-digest)."""
    payload = _bridge_payload_from(bridge)
    payload["bridge_digest"] = bridge.bridge_digest
    return payload


def strategy_signal_to_paper_intent_digest(bridge: StrategySignalToPaperIntent) -> str:
    """Recompute the canonical bridge digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_bridge_payload_from(bridge))


__all__ = [
    "StrategySignalToPaperIntent",
    "StrategySignalToPaperIntentError",
    "StrategySignalToPaperIntentStatus",
    "build_strategy_signal_to_paper_intent",
    "strategy_signal_to_paper_intent_digest",
    "strategy_signal_to_paper_intent_to_dict",
]
