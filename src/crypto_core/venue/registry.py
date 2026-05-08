from __future__ import annotations

from .contracts import (
    InstrumentSpec,
    InstrumentType,
    PublicFeedHealth,
    PublicFeedType,
    VenueCapability,
    VenueContractError,
    VenueId,
    VenueStatus,
    public_feed_health_rejection_reasons,
)


class VenueRegistryError(VenueContractError):
    """Raised when a read-only venue registry lookup fails closed."""


_VENUE_CAPABILITIES: tuple[VenueCapability, ...] = (
    VenueCapability(
        venue_id=VenueId.DERIBIT,
        display_name="Deribit",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=False,
        avoided_initially_reason=None,
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=False,
        supports_inverse_perp=True,
        supports_dated_futures=True,
        supports_options=True,
        testnet_available=True,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=True,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=True,
        supports_index_price=True,
        supports_funding=True,
        supports_open_interest=True,
        supports_liquidations=True,
        supports_account_stream=True,
        supports_order_stream=True,
        supports_position_stream=True,
        initial_recommendation_rank=1,
        notes=("read-only derivatives and volatility research priority",),
    ),
    VenueCapability(
        venue_id=VenueId.BINANCE_USDM,
        display_name="Binance USD-M Futures",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=False,
        avoided_initially_reason=None,
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=True,
        supports_inverse_perp=False,
        supports_dated_futures=False,
        supports_options=False,
        testnet_available=True,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=True,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=True,
        supports_index_price=True,
        supports_funding=True,
        supports_open_interest=True,
        supports_liquidations=True,
        supports_account_stream=True,
        supports_order_stream=True,
        supports_position_stream=True,
        initial_recommendation_rank=2,
        notes=("L2 reconstruction reference for linear perpetual research",),
    ),
    VenueCapability(
        venue_id=VenueId.BYBIT_USDT_PERP,
        display_name="Bybit USDT Perpetual",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=False,
        avoided_initially_reason=None,
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=True,
        supports_inverse_perp=True,
        supports_dated_futures=False,
        supports_options=False,
        testnet_available=True,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=True,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=True,
        supports_index_price=True,
        supports_funding=True,
        supports_open_interest=True,
        supports_liquidations=True,
        supports_account_stream=True,
        supports_order_stream=True,
        supports_position_stream=True,
        initial_recommendation_rank=3,
        notes=("secondary linear perpetual public-data comparison venue",),
    ),
    VenueCapability(
        venue_id=VenueId.OKX_SWAP,
        display_name="OKX Swap",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=False,
        avoided_initially_reason=None,
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=True,
        supports_inverse_perp=True,
        supports_dated_futures=True,
        supports_options=True,
        testnet_available=True,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=True,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=True,
        supports_index_price=True,
        supports_funding=True,
        supports_open_interest=True,
        supports_liquidations=True,
        supports_account_stream=True,
        supports_order_stream=True,
        supports_position_stream=True,
        initial_recommendation_rank=4,
        notes=("broad derivatives venue for later cross-venue public-data comparison",),
    ),
    VenueCapability(
        venue_id=VenueId.KRAKEN_FUTURES,
        display_name="Kraken Futures",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=False,
        avoided_initially_reason=None,
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=True,
        supports_inverse_perp=True,
        supports_dated_futures=True,
        supports_options=False,
        testnet_available=True,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=True,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=True,
        supports_index_price=True,
        supports_funding=True,
        supports_open_interest=True,
        supports_liquidations=False,
        supports_account_stream=True,
        supports_order_stream=True,
        supports_position_stream=True,
        initial_recommendation_rank=5,
        notes=("regulated futures venue for later public-data comparison",),
    ),
    VenueCapability(
        venue_id=VenueId.COINBASE_DERIVATIVES,
        display_name="Coinbase Derivatives",
        enabled_for_public_data=True,
        enabled_for_private_testnet=False,
        enabled_for_live=False,
        avoided_initially=True,
        avoided_initially_reason="initial research prioritizes perpetual and options venue breadth",
        supports_spot=False,
        supports_margin=False,
        supports_usdt_perp=False,
        supports_inverse_perp=False,
        supports_dated_futures=True,
        supports_options=False,
        testnet_available=False,
        public_ws_available=True,
        rest_snapshot_available=True,
        private_ws_available=False,
        supports_l2_orderbook=True,
        supports_trades=True,
        supports_mark_price=False,
        supports_index_price=False,
        supports_funding=False,
        supports_open_interest=True,
        supports_liquidations=False,
        supports_account_stream=False,
        supports_order_stream=False,
        supports_position_stream=False,
        initial_recommendation_rank=6,
        notes=("marked avoided initially for crypto derivatives research bootstrap",),
        status=VenueStatus.AVOIDED_INITIALLY,
    ),
)


_INSTRUMENT_SPECS: tuple[InstrumentSpec, ...] = (
    InstrumentSpec(
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        instrument_type=InstrumentType.INVERSE_PERP,
        base_asset="BTC",
        quote_asset="USD",
        settlement_asset="BTC",
        contract_size=10.0,
        tick_size=0.5,
        lot_size=10.0,
        min_order_size=10.0,
        min_notional=10.0,
        price_precision=1,
        quantity_precision=0,
        inverse_contract=True,
        linear_contract=False,
        active=True,
    ),
    InstrumentSpec(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        instrument_type=InstrumentType.USDT_PERP,
        base_asset="BTC",
        quote_asset="USDT",
        settlement_asset="USDT",
        contract_size=1.0,
        tick_size=0.1,
        lot_size=0.001,
        min_order_size=0.001,
        min_notional=5.0,
        price_precision=1,
        quantity_precision=3,
        inverse_contract=False,
        linear_contract=True,
        active=True,
    ),
    InstrumentSpec(
        venue_id=VenueId.COINBASE_DERIVATIVES,
        symbol="BTC-MONTHLY",
        canonical_symbol="BTC-USD-DATED-FUTURE",
        instrument_type=InstrumentType.DATED_FUTURES,
        base_asset="BTC",
        quote_asset="USD",
        settlement_asset="USD",
        contract_size=1.0,
        tick_size=5.0,
        lot_size=1.0,
        min_order_size=1.0,
        min_notional=1.0,
        price_precision=0,
        quantity_precision=0,
        inverse_contract=False,
        linear_contract=True,
        active=False,
    ),
)


def venue_capabilities() -> tuple[VenueCapability, ...]:
    return _VENUE_CAPABILITIES


def instrument_specs() -> tuple[InstrumentSpec, ...]:
    return _INSTRUMENT_SPECS


def get_venue_capability(venue_id: VenueId | str) -> VenueCapability:
    venue = _coerce_venue_id(venue_id)
    for capability in _VENUE_CAPABILITIES:
        if capability.venue_id is venue:
            return capability
    raise VenueRegistryError(f"unknown venue: {venue.value}")


def get_instrument_spec(venue_id: VenueId | str, symbol: str) -> InstrumentSpec:
    venue = _coerce_venue_id(venue_id)
    if not isinstance(symbol, str) or not symbol.strip():
        raise VenueRegistryError("symbol must be non-empty")
    normalized_symbol = symbol.strip().upper()
    for spec in _INSTRUMENT_SPECS:
        if spec.venue_id is venue and spec.symbol.upper() == normalized_symbol:
            return spec
    raise VenueRegistryError(f"unknown instrument: {venue.value}:{normalized_symbol}")


def venue_supports_public_feed(capability: VenueCapability, feed_type: PublicFeedType | str) -> bool:
    feed = _coerce_feed_type(feed_type)
    if feed is PublicFeedType.L2_ORDERBOOK:
        return capability.supports_l2_orderbook
    if feed is PublicFeedType.TRADES:
        return capability.supports_trades
    if feed is PublicFeedType.MARK_PRICE:
        return capability.supports_mark_price
    if feed is PublicFeedType.INDEX_PRICE:
        return capability.supports_index_price
    if feed is PublicFeedType.FUNDING:
        return capability.supports_funding
    if feed is PublicFeedType.OPEN_INTEREST:
        return capability.supports_open_interest
    if feed is PublicFeedType.LIQUIDATIONS:
        return capability.supports_liquidations
    return False


def instrument_downstream_rejection_reasons(spec: InstrumentSpec) -> tuple[str, ...]:
    reasons: list[str] = []
    if not spec.active:
        reasons.append("instrument:inactive")
    try:
        capability = get_venue_capability(spec.venue_id)
    except VenueRegistryError:
        reasons.append("instrument:venue_unknown")
    else:
        if spec.instrument_type is InstrumentType.USDT_PERP and not capability.supports_usdt_perp:
            reasons.append("instrument:unsupported_type")
        if spec.instrument_type is InstrumentType.INVERSE_PERP and not capability.supports_inverse_perp:
            reasons.append("instrument:unsupported_type")
        if spec.instrument_type is InstrumentType.DATED_FUTURES and not capability.supports_dated_futures:
            reasons.append("instrument:unsupported_type")
        if spec.instrument_type is InstrumentType.OPTIONS and not capability.supports_options:
            reasons.append("instrument:unsupported_type")
        if spec.instrument_type is InstrumentType.SPOT and not capability.supports_spot:
            reasons.append("instrument:unsupported_type")
        if spec.instrument_type is InstrumentType.MARGIN and not capability.supports_margin:
            reasons.append("instrument:unsupported_type")
    return tuple(dict.fromkeys(reasons))


def ensure_instrument_usable_for_downstream(spec: InstrumentSpec) -> InstrumentSpec:
    reasons = instrument_downstream_rejection_reasons(spec)
    if reasons:
        raise VenueRegistryError(";".join(reasons))
    return spec


def public_feed_downstream_rejection_reasons(health: PublicFeedHealth) -> tuple[str, ...]:
    reasons = list(public_feed_health_rejection_reasons(health))
    try:
        capability = get_venue_capability(health.venue_id)
    except VenueRegistryError:
        reasons.append("public_feed:venue_unknown")
    else:
        if not venue_supports_public_feed(capability, health.feed_type):
            reasons.append("public_feed:unsupported")
    return tuple(dict.fromkeys(reasons))


def ensure_public_feed_usable_for_downstream(health: PublicFeedHealth) -> PublicFeedHealth:
    reasons = public_feed_downstream_rejection_reasons(health)
    if reasons:
        raise VenueRegistryError(";".join(reasons))
    return health


def _coerce_venue_id(venue_id: VenueId | str) -> VenueId:
    if isinstance(venue_id, VenueId):
        return venue_id
    if isinstance(venue_id, str):
        try:
            return VenueId(venue_id)
        except ValueError as exc:
            raise VenueRegistryError(f"unknown venue: {venue_id}") from exc
    raise VenueRegistryError("venue_id is malformed")


def _coerce_feed_type(feed_type: PublicFeedType | str) -> PublicFeedType:
    if isinstance(feed_type, PublicFeedType):
        return feed_type
    if isinstance(feed_type, str):
        try:
            return PublicFeedType(feed_type)
        except ValueError as exc:
            raise VenueRegistryError(f"unknown public feed: {feed_type}") from exc
    raise VenueRegistryError("feed_type is malformed")


__all__ = [
    "VenueRegistryError",
    "ensure_instrument_usable_for_downstream",
    "ensure_public_feed_usable_for_downstream",
    "get_instrument_spec",
    "get_venue_capability",
    "instrument_downstream_rejection_reasons",
    "instrument_specs",
    "public_feed_downstream_rejection_reasons",
    "venue_capabilities",
    "venue_supports_public_feed",
]
