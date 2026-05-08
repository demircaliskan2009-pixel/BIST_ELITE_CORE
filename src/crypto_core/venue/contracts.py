from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class VenueContractError(ValueError):
    """Raised when read-only venue or market-data contracts are malformed."""


class VenueId(str, Enum):
    DERIBIT = "deribit"
    BINANCE_USDM = "binance_usdm"
    BYBIT_USDT_PERP = "bybit_usdt_perp"
    OKX_SWAP = "okx_swap"
    KRAKEN_FUTURES = "kraken_futures"
    COINBASE_DERIVATIVES = "coinbase_derivatives"


class InstrumentType(str, Enum):
    SPOT = "spot"
    MARGIN = "margin"
    USDT_PERP = "usdt_perp"
    INVERSE_PERP = "inverse_perp"
    DATED_FUTURES = "dated_futures"
    OPTIONS = "options"


class PublicFeedType(str, Enum):
    L2_ORDERBOOK = "l2_orderbook"
    TRADES = "trades"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATIONS = "liquidations"


class VenueStatus(str, Enum):
    ACTIVE = "active"
    AVOIDED_INITIALLY = "avoided_initially"
    DISABLED = "disabled"


def _coerce_enum(enum_type: type[Enum], value: object, field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as exc:
            raise VenueContractError(f"{field_name} is unsupported") from exc
    raise VenueContractError(f"{field_name} is malformed")


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VenueContractError(f"{field_name} must be a non-empty string")
    return value


def _require_finite_positive(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise VenueContractError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise VenueContractError(f"{field_name} must be finite and positive")
    return result


def _require_finite_non_negative(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise VenueContractError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise VenueContractError(f"{field_name} must be finite and non-negative")
    return result


def _require_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise VenueContractError(f"{field_name} must be a positive integer")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VenueContractError(f"{field_name} must be a non-negative integer")
    return value


def _string_tuple(values: object, field_name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, tuple | list):
        result = tuple(_require_non_empty_string(value, field_name) for value in values)
    else:
        raise VenueContractError(f"{field_name} must be a sequence")
    if not allow_empty and not result:
        raise VenueContractError(f"{field_name} must not be empty")
    return result


@dataclass(frozen=True)
class VenueCapability:
    venue_id: VenueId
    display_name: str
    enabled_for_public_data: bool
    enabled_for_private_testnet: bool
    enabled_for_live: bool
    avoided_initially: bool
    avoided_initially_reason: str | None
    supports_spot: bool
    supports_margin: bool
    supports_usdt_perp: bool
    supports_inverse_perp: bool
    supports_dated_futures: bool
    supports_options: bool
    testnet_available: bool
    public_ws_available: bool
    rest_snapshot_available: bool
    private_ws_available: bool
    supports_l2_orderbook: bool
    supports_trades: bool
    supports_mark_price: bool
    supports_index_price: bool
    supports_funding: bool
    supports_open_interest: bool
    supports_liquidations: bool
    supports_account_stream: bool
    supports_order_stream: bool
    supports_position_stream: bool
    initial_recommendation_rank: int
    notes: tuple[str, ...] = ()
    status: VenueStatus = VenueStatus.ACTIVE

    def __post_init__(self) -> None:
        if not isinstance(self.venue_id, VenueId):
            raise VenueContractError("venue_id is unsupported")
        _require_non_empty_string(self.display_name, "display_name")
        _require_positive_int(self.initial_recommendation_rank, "initial_recommendation_rank")
        if self.avoided_initially and not self.avoided_initially_reason:
            raise VenueContractError("avoided_initially_reason is required")
        if self.avoided_initially_reason is not None:
            _require_non_empty_string(self.avoided_initially_reason, "avoided_initially_reason")
        if not isinstance(self.status, VenueStatus):
            raise VenueContractError("status is unsupported")
        _string_tuple(self.notes, "notes")


@dataclass(frozen=True)
class InstrumentSpec:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    instrument_type: InstrumentType
    base_asset: str
    quote_asset: str
    settlement_asset: str
    contract_size: float
    tick_size: float
    lot_size: float
    min_order_size: float
    min_notional: float
    price_precision: int
    quantity_precision: int
    inverse_contract: bool
    linear_contract: bool
    active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.venue_id, VenueId):
            raise VenueContractError("venue_id is unsupported")
        if not isinstance(self.instrument_type, InstrumentType):
            raise VenueContractError("instrument_type is unsupported")
        _require_non_empty_string(self.symbol, "symbol")
        _require_non_empty_string(self.canonical_symbol, "canonical_symbol")
        _require_non_empty_string(self.base_asset, "base_asset")
        _require_non_empty_string(self.quote_asset, "quote_asset")
        _require_non_empty_string(self.settlement_asset, "settlement_asset")
        _require_finite_positive(self.contract_size, "contract_size")
        _require_finite_positive(self.tick_size, "tick_size")
        _require_finite_positive(self.lot_size, "lot_size")
        _require_finite_positive(self.min_order_size, "min_order_size")
        _require_finite_non_negative(self.min_notional, "min_notional")
        _require_non_negative_int(self.price_precision, "price_precision")
        _require_non_negative_int(self.quantity_precision, "quantity_precision")
        if not isinstance(self.inverse_contract, bool) or not isinstance(self.linear_contract, bool):
            raise VenueContractError("contract flags must be booleans")
        if self.instrument_type in {InstrumentType.SPOT, InstrumentType.MARGIN}:
            if self.inverse_contract or self.linear_contract:
                raise VenueContractError("spot and margin instruments cannot be inverse or linear")
        elif self.inverse_contract == self.linear_contract:
            raise VenueContractError("derivative instruments must be exactly one of inverse or linear")
        if self.instrument_type is InstrumentType.INVERSE_PERP and not self.inverse_contract:
            raise VenueContractError("inverse perpetual must be inverse")
        if self.instrument_type is InstrumentType.USDT_PERP and not self.linear_contract:
            raise VenueContractError("USDT perpetual must be linear")
        if not isinstance(self.active, bool):
            raise VenueContractError("active must be a boolean")


@dataclass(frozen=True)
class PublicFeedHealth:
    venue_id: VenueId
    feed_type: PublicFeedType
    symbol: str
    healthy: bool
    stale: bool
    last_event_time_ns: int
    last_receive_time_ns: int
    gap_detected: bool
    resync_required: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.venue_id, VenueId):
            raise VenueContractError("venue_id is unsupported")
        if not isinstance(self.feed_type, PublicFeedType):
            raise VenueContractError("feed_type is unsupported")
        _require_non_empty_string(self.symbol, "symbol")
        for field_name in ("healthy", "stale", "gap_detected", "resync_required"):
            if not isinstance(getattr(self, field_name), bool):
                raise VenueContractError(f"{field_name} must be a boolean")
        _require_positive_int(self.last_event_time_ns, "last_event_time_ns")
        _require_positive_int(self.last_receive_time_ns, "last_receive_time_ns")
        _string_tuple(self.rejection_reasons, "rejection_reasons")


@dataclass(frozen=True)
class PublicMarketDataEvent:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    feed_type: PublicFeedType
    event_time_ns: int
    receive_time_ns: int
    sequence_id: int
    payload_hash: str
    raw_payload_ref: str | None
    normalized: bool

    def __post_init__(self) -> None:
        if not isinstance(self.venue_id, VenueId):
            raise VenueContractError("venue_id is unsupported")
        if not isinstance(self.feed_type, PublicFeedType):
            raise VenueContractError("feed_type is unsupported")
        _require_non_empty_string(self.symbol, "symbol")
        _require_non_empty_string(self.canonical_symbol, "canonical_symbol")
        _require_positive_int(self.event_time_ns, "event_time_ns")
        _require_positive_int(self.receive_time_ns, "receive_time_ns")
        if self.receive_time_ns < self.event_time_ns:
            raise VenueContractError("receive_time_ns cannot precede event_time_ns")
        _require_non_negative_int(self.sequence_id, "sequence_id")
        _require_non_empty_string(self.payload_hash, "payload_hash")
        if self.raw_payload_ref is not None:
            _require_non_empty_string(self.raw_payload_ref, "raw_payload_ref")
        if not isinstance(self.normalized, bool):
            raise VenueContractError("normalized must be a boolean")


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    quantity: float

    def __post_init__(self) -> None:
        _require_finite_positive(self.price, "price")
        _require_finite_non_negative(self.quantity, "quantity")


@dataclass(frozen=True)
class OrderBookSnapshot:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    event_time_ns: int
    receive_time_ns: int
    sequence_id: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    checksum: str | None
    depth: int
    source: str

    def __post_init__(self) -> None:
        _validate_book_header(
            self.venue_id,
            self.symbol,
            self.canonical_symbol,
            self.event_time_ns,
            self.receive_time_ns,
            self.sequence_id,
            self.source,
        )
        bids = _level_tuple(self.bids, "bids")
        asks = _level_tuple(self.asks, "asks")
        if not bids or not asks:
            raise VenueContractError("order book sides must not be empty")
        _require_positive_levels(bids, "bids")
        _require_positive_levels(asks, "asks")
        if max(level.price for level in bids) >= min(level.price for level in asks):
            raise VenueContractError("order book is crossed")
        _require_positive_int(self.depth, "depth")
        if self.depth > min(len(bids), len(asks)):
            raise VenueContractError("depth exceeds available book levels")
        if self.checksum is not None:
            _require_non_empty_string(self.checksum, "checksum")


@dataclass(frozen=True)
class OrderBookDelta:
    venue_id: VenueId
    symbol: str
    canonical_symbol: str
    event_time_ns: int
    receive_time_ns: int
    first_update_id: int
    final_update_id: int
    prev_update_id: int
    bid_updates: tuple[OrderBookLevel, ...]
    ask_updates: tuple[OrderBookLevel, ...]
    checksum: str | None
    source: str

    def __post_init__(self) -> None:
        _validate_book_header(
            self.venue_id,
            self.symbol,
            self.canonical_symbol,
            self.event_time_ns,
            self.receive_time_ns,
            self.final_update_id,
            self.source,
        )
        _require_positive_int(self.first_update_id, "first_update_id")
        _require_positive_int(self.final_update_id, "final_update_id")
        _require_non_negative_int(self.prev_update_id, "prev_update_id")
        if self.first_update_id > self.final_update_id:
            raise VenueContractError("first_update_id cannot exceed final_update_id")
        if self.prev_update_id >= self.first_update_id:
            raise VenueContractError("prev_update_id must be before first_update_id")
        bids = _level_tuple(self.bid_updates, "bid_updates")
        asks = _level_tuple(self.ask_updates, "ask_updates")
        if not bids and not asks:
            raise VenueContractError("delta must contain at least one side update")
        if self.checksum is not None:
            _require_non_empty_string(self.checksum, "checksum")


def _validate_book_header(
    venue_id: object,
    symbol: object,
    canonical_symbol: object,
    event_time_ns: object,
    receive_time_ns: object,
    sequence_id: object,
    source: object,
) -> None:
    if not isinstance(venue_id, VenueId):
        raise VenueContractError("venue_id is unsupported")
    _require_non_empty_string(symbol, "symbol")
    _require_non_empty_string(canonical_symbol, "canonical_symbol")
    _require_positive_int(event_time_ns, "event_time_ns")
    _require_positive_int(receive_time_ns, "receive_time_ns")
    if receive_time_ns < event_time_ns:  # type: ignore[operator]
        raise VenueContractError("receive_time_ns cannot precede event_time_ns")
    _require_non_negative_int(sequence_id, "sequence_id")
    _require_non_empty_string(source, "source")


def _level_tuple(values: object, field_name: str) -> tuple[OrderBookLevel, ...]:
    if not isinstance(values, tuple | list):
        raise VenueContractError(f"{field_name} must be a sequence")
    result: list[OrderBookLevel] = []
    for value in values:
        if not isinstance(value, OrderBookLevel):
            raise VenueContractError(f"{field_name} entries must be OrderBookLevel")
        result.append(value)
    return tuple(result)


def _require_positive_levels(levels: tuple[OrderBookLevel, ...], field_name: str) -> None:
    if any(level.quantity <= 0.0 for level in levels):
        raise VenueContractError(f"{field_name} levels must have positive quantity")


def venue_capability_to_dict(capability: VenueCapability) -> dict[str, object]:
    return {
        "venue_id": capability.venue_id.value,
        "display_name": capability.display_name,
        "enabled_for_public_data": capability.enabled_for_public_data,
        "enabled_for_private_testnet": capability.enabled_for_private_testnet,
        "enabled_for_live": capability.enabled_for_live,
        "avoided_initially": capability.avoided_initially,
        "avoided_initially_reason": capability.avoided_initially_reason,
        "supports_spot": capability.supports_spot,
        "supports_margin": capability.supports_margin,
        "supports_usdt_perp": capability.supports_usdt_perp,
        "supports_inverse_perp": capability.supports_inverse_perp,
        "supports_dated_futures": capability.supports_dated_futures,
        "supports_options": capability.supports_options,
        "testnet_available": capability.testnet_available,
        "public_ws_available": capability.public_ws_available,
        "rest_snapshot_available": capability.rest_snapshot_available,
        "private_ws_available": capability.private_ws_available,
        "supports_l2_orderbook": capability.supports_l2_orderbook,
        "supports_trades": capability.supports_trades,
        "supports_mark_price": capability.supports_mark_price,
        "supports_index_price": capability.supports_index_price,
        "supports_funding": capability.supports_funding,
        "supports_open_interest": capability.supports_open_interest,
        "supports_liquidations": capability.supports_liquidations,
        "supports_account_stream": capability.supports_account_stream,
        "supports_order_stream": capability.supports_order_stream,
        "supports_position_stream": capability.supports_position_stream,
        "initial_recommendation_rank": capability.initial_recommendation_rank,
        "notes": list(capability.notes),
        "status": capability.status.value,
    }


def venue_capability_from_dict(data: object) -> VenueCapability:
    payload = _require_mapping(data)
    return VenueCapability(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        display_name=_require_non_empty_string(payload.get("display_name"), "display_name"),
        enabled_for_public_data=_require_bool(payload.get("enabled_for_public_data"), "enabled_for_public_data"),
        enabled_for_private_testnet=_require_bool(
            payload.get("enabled_for_private_testnet"),
            "enabled_for_private_testnet",
        ),
        enabled_for_live=_require_bool(payload.get("enabled_for_live"), "enabled_for_live"),
        avoided_initially=_require_bool(payload.get("avoided_initially"), "avoided_initially"),
        avoided_initially_reason=_optional_string(payload.get("avoided_initially_reason"), "avoided_initially_reason"),
        supports_spot=_require_bool(payload.get("supports_spot"), "supports_spot"),
        supports_margin=_require_bool(payload.get("supports_margin"), "supports_margin"),
        supports_usdt_perp=_require_bool(payload.get("supports_usdt_perp"), "supports_usdt_perp"),
        supports_inverse_perp=_require_bool(payload.get("supports_inverse_perp"), "supports_inverse_perp"),
        supports_dated_futures=_require_bool(payload.get("supports_dated_futures"), "supports_dated_futures"),
        supports_options=_require_bool(payload.get("supports_options"), "supports_options"),
        testnet_available=_require_bool(payload.get("testnet_available"), "testnet_available"),
        public_ws_available=_require_bool(payload.get("public_ws_available"), "public_ws_available"),
        rest_snapshot_available=_require_bool(payload.get("rest_snapshot_available"), "rest_snapshot_available"),
        private_ws_available=_require_bool(payload.get("private_ws_available"), "private_ws_available"),
        supports_l2_orderbook=_require_bool(payload.get("supports_l2_orderbook"), "supports_l2_orderbook"),
        supports_trades=_require_bool(payload.get("supports_trades"), "supports_trades"),
        supports_mark_price=_require_bool(payload.get("supports_mark_price"), "supports_mark_price"),
        supports_index_price=_require_bool(payload.get("supports_index_price"), "supports_index_price"),
        supports_funding=_require_bool(payload.get("supports_funding"), "supports_funding"),
        supports_open_interest=_require_bool(payload.get("supports_open_interest"), "supports_open_interest"),
        supports_liquidations=_require_bool(payload.get("supports_liquidations"), "supports_liquidations"),
        supports_account_stream=_require_bool(payload.get("supports_account_stream"), "supports_account_stream"),
        supports_order_stream=_require_bool(payload.get("supports_order_stream"), "supports_order_stream"),
        supports_position_stream=_require_bool(payload.get("supports_position_stream"), "supports_position_stream"),
        initial_recommendation_rank=_require_positive_int(
            payload.get("initial_recommendation_rank"),
            "initial_recommendation_rank",
        ),
        notes=_string_tuple(payload.get("notes", ()), "notes"),
        status=_coerce_enum(VenueStatus, payload.get("status", VenueStatus.ACTIVE.value), "status"),  # type: ignore[arg-type]
    )


def instrument_spec_to_dict(spec: InstrumentSpec) -> dict[str, object]:
    return {
        "venue_id": spec.venue_id.value,
        "symbol": spec.symbol,
        "canonical_symbol": spec.canonical_symbol,
        "instrument_type": spec.instrument_type.value,
        "base_asset": spec.base_asset,
        "quote_asset": spec.quote_asset,
        "settlement_asset": spec.settlement_asset,
        "contract_size": spec.contract_size,
        "tick_size": spec.tick_size,
        "lot_size": spec.lot_size,
        "min_order_size": spec.min_order_size,
        "min_notional": spec.min_notional,
        "price_precision": spec.price_precision,
        "quantity_precision": spec.quantity_precision,
        "inverse_contract": spec.inverse_contract,
        "linear_contract": spec.linear_contract,
        "active": spec.active,
    }


def instrument_spec_from_dict(data: object) -> InstrumentSpec:
    payload = _require_mapping(data)
    return InstrumentSpec(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        symbol=_require_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_require_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        instrument_type=_coerce_enum(InstrumentType, payload.get("instrument_type"), "instrument_type"),  # type: ignore[arg-type]
        base_asset=_require_non_empty_string(payload.get("base_asset"), "base_asset"),
        quote_asset=_require_non_empty_string(payload.get("quote_asset"), "quote_asset"),
        settlement_asset=_require_non_empty_string(payload.get("settlement_asset"), "settlement_asset"),
        contract_size=_require_finite_positive(payload.get("contract_size"), "contract_size"),
        tick_size=_require_finite_positive(payload.get("tick_size"), "tick_size"),
        lot_size=_require_finite_positive(payload.get("lot_size"), "lot_size"),
        min_order_size=_require_finite_positive(payload.get("min_order_size"), "min_order_size"),
        min_notional=_require_finite_non_negative(payload.get("min_notional"), "min_notional"),
        price_precision=_require_non_negative_int(payload.get("price_precision"), "price_precision"),
        quantity_precision=_require_non_negative_int(payload.get("quantity_precision"), "quantity_precision"),
        inverse_contract=_require_bool(payload.get("inverse_contract"), "inverse_contract"),
        linear_contract=_require_bool(payload.get("linear_contract"), "linear_contract"),
        active=_require_bool(payload.get("active"), "active"),
    )


def public_feed_health_rejection_reasons(health: PublicFeedHealth) -> tuple[str, ...]:
    reasons: list[str] = []
    if not health.healthy:
        reasons.append("public_feed:unhealthy")
    if health.stale:
        reasons.append("public_feed:stale")
    if health.gap_detected:
        reasons.append("public_feed:gap_detected")
    if health.resync_required:
        reasons.append("public_feed:resync_required")
    reasons.extend(health.rejection_reasons)
    return tuple(dict.fromkeys(reasons))


def public_feed_health_to_dict(health: PublicFeedHealth) -> dict[str, object]:
    return {
        "venue_id": health.venue_id.value,
        "feed_type": health.feed_type.value,
        "symbol": health.symbol,
        "healthy": health.healthy,
        "stale": health.stale,
        "last_event_time_ns": health.last_event_time_ns,
        "last_receive_time_ns": health.last_receive_time_ns,
        "gap_detected": health.gap_detected,
        "resync_required": health.resync_required,
        "rejection_reasons": list(health.rejection_reasons),
    }


def public_feed_health_from_dict(data: object) -> PublicFeedHealth:
    payload = _require_mapping(data)
    return PublicFeedHealth(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        feed_type=_coerce_enum(PublicFeedType, payload.get("feed_type"), "feed_type"),  # type: ignore[arg-type]
        symbol=_require_non_empty_string(payload.get("symbol"), "symbol"),
        healthy=_require_bool(payload.get("healthy"), "healthy"),
        stale=_require_bool(payload.get("stale"), "stale"),
        last_event_time_ns=_require_positive_int(payload.get("last_event_time_ns"), "last_event_time_ns"),
        last_receive_time_ns=_require_positive_int(payload.get("last_receive_time_ns"), "last_receive_time_ns"),
        gap_detected=_require_bool(payload.get("gap_detected"), "gap_detected"),
        resync_required=_require_bool(payload.get("resync_required"), "resync_required"),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons", ()), "rejection_reasons"),
    )


def public_market_data_event_to_dict(event: PublicMarketDataEvent) -> dict[str, object]:
    return {
        "venue_id": event.venue_id.value,
        "symbol": event.symbol,
        "canonical_symbol": event.canonical_symbol,
        "feed_type": event.feed_type.value,
        "event_time_ns": event.event_time_ns,
        "receive_time_ns": event.receive_time_ns,
        "sequence_id": event.sequence_id,
        "payload_hash": event.payload_hash,
        "raw_payload_ref": event.raw_payload_ref,
        "normalized": event.normalized,
    }


def public_market_data_event_from_dict(data: object) -> PublicMarketDataEvent:
    payload = _require_mapping(data)
    return PublicMarketDataEvent(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        symbol=_require_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_require_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        feed_type=_coerce_enum(PublicFeedType, payload.get("feed_type"), "feed_type"),  # type: ignore[arg-type]
        event_time_ns=_require_positive_int(payload.get("event_time_ns"), "event_time_ns"),
        receive_time_ns=_require_positive_int(payload.get("receive_time_ns"), "receive_time_ns"),
        sequence_id=_require_non_negative_int(payload.get("sequence_id"), "sequence_id"),
        payload_hash=_require_non_empty_string(payload.get("payload_hash"), "payload_hash"),
        raw_payload_ref=_optional_string(payload.get("raw_payload_ref"), "raw_payload_ref"),
        normalized=_require_bool(payload.get("normalized"), "normalized"),
    )


def order_book_level_to_dict(level: OrderBookLevel) -> dict[str, object]:
    return {"price": level.price, "quantity": level.quantity}


def order_book_level_from_dict(data: object) -> OrderBookLevel:
    payload = _require_mapping(data)
    return OrderBookLevel(
        price=_require_finite_positive(payload.get("price"), "price"),
        quantity=_require_finite_positive(payload.get("quantity"), "quantity"),
    )


def order_book_snapshot_to_dict(snapshot: OrderBookSnapshot) -> dict[str, object]:
    return {
        "venue_id": snapshot.venue_id.value,
        "symbol": snapshot.symbol,
        "canonical_symbol": snapshot.canonical_symbol,
        "event_time_ns": snapshot.event_time_ns,
        "receive_time_ns": snapshot.receive_time_ns,
        "sequence_id": snapshot.sequence_id,
        "bids": [order_book_level_to_dict(level) for level in snapshot.bids],
        "asks": [order_book_level_to_dict(level) for level in snapshot.asks],
        "checksum": snapshot.checksum,
        "depth": snapshot.depth,
        "source": snapshot.source,
    }


def order_book_snapshot_from_dict(data: object) -> OrderBookSnapshot:
    payload = _require_mapping(data)
    return OrderBookSnapshot(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        symbol=_require_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_require_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        event_time_ns=_require_positive_int(payload.get("event_time_ns"), "event_time_ns"),
        receive_time_ns=_require_positive_int(payload.get("receive_time_ns"), "receive_time_ns"),
        sequence_id=_require_non_negative_int(payload.get("sequence_id"), "sequence_id"),
        bids=tuple(order_book_level_from_dict(level) for level in _require_sequence(payload.get("bids"), "bids")),
        asks=tuple(order_book_level_from_dict(level) for level in _require_sequence(payload.get("asks"), "asks")),
        checksum=_optional_string(payload.get("checksum"), "checksum"),
        depth=_require_positive_int(payload.get("depth"), "depth"),
        source=_require_non_empty_string(payload.get("source"), "source"),
    )


def order_book_delta_to_dict(delta: OrderBookDelta) -> dict[str, object]:
    return {
        "venue_id": delta.venue_id.value,
        "symbol": delta.symbol,
        "canonical_symbol": delta.canonical_symbol,
        "event_time_ns": delta.event_time_ns,
        "receive_time_ns": delta.receive_time_ns,
        "first_update_id": delta.first_update_id,
        "final_update_id": delta.final_update_id,
        "prev_update_id": delta.prev_update_id,
        "bid_updates": [order_book_level_to_dict(level) for level in delta.bid_updates],
        "ask_updates": [order_book_level_to_dict(level) for level in delta.ask_updates],
        "checksum": delta.checksum,
        "source": delta.source,
    }


def order_book_delta_from_dict(data: object) -> OrderBookDelta:
    payload = _require_mapping(data)
    return OrderBookDelta(
        venue_id=_coerce_enum(VenueId, payload.get("venue_id"), "venue_id"),  # type: ignore[arg-type]
        symbol=_require_non_empty_string(payload.get("symbol"), "symbol"),
        canonical_symbol=_require_non_empty_string(payload.get("canonical_symbol"), "canonical_symbol"),
        event_time_ns=_require_positive_int(payload.get("event_time_ns"), "event_time_ns"),
        receive_time_ns=_require_positive_int(payload.get("receive_time_ns"), "receive_time_ns"),
        first_update_id=_require_positive_int(payload.get("first_update_id"), "first_update_id"),
        final_update_id=_require_positive_int(payload.get("final_update_id"), "final_update_id"),
        prev_update_id=_require_non_negative_int(payload.get("prev_update_id"), "prev_update_id"),
        bid_updates=tuple(
            order_book_level_from_dict(level) for level in _require_sequence(payload.get("bid_updates"), "bid_updates")
        ),
        ask_updates=tuple(
            order_book_level_from_dict(level) for level in _require_sequence(payload.get("ask_updates"), "ask_updates")
        ),
        checksum=_optional_string(payload.get("checksum"), "checksum"),
        source=_require_non_empty_string(payload.get("source"), "source"),
    )


def _require_mapping(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise VenueContractError("payload must be a mapping")
    return data


def _require_sequence(data: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(data, tuple | list):
        raise VenueContractError(f"{field_name} must be a sequence")
    return tuple(data)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise VenueContractError(f"{field_name} must be a boolean")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_string(value, field_name)


__all__ = [
    "InstrumentSpec",
    "InstrumentType",
    "OrderBookDelta",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "PublicFeedHealth",
    "PublicFeedType",
    "PublicMarketDataEvent",
    "VenueCapability",
    "VenueContractError",
    "VenueId",
    "VenueStatus",
    "instrument_spec_from_dict",
    "instrument_spec_to_dict",
    "order_book_delta_from_dict",
    "order_book_delta_to_dict",
    "order_book_level_from_dict",
    "order_book_level_to_dict",
    "order_book_snapshot_from_dict",
    "order_book_snapshot_to_dict",
    "public_feed_health_from_dict",
    "public_feed_health_rejection_reasons",
    "public_feed_health_to_dict",
    "public_market_data_event_from_dict",
    "public_market_data_event_to_dict",
    "venue_capability_from_dict",
    "venue_capability_to_dict",
]
