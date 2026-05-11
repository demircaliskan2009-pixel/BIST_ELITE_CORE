from __future__ import annotations

import math

from bist_core.execution.paper_engine import OrderSide
from bist_core.models.ohlcv import OHLCVBar
from bist_core.providers.base import FailClosedError


def _fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _normalize_side(side: OrderSide | str) -> OrderSide:
    if isinstance(side, OrderSide):
        return side
    try:
        return OrderSide(str(side).strip().upper())
    except ValueError as exc:
        raise FailClosedError("invalid_side") from exc


def _validate_fill_price(fill_price: float) -> float:
    if isinstance(fill_price, bool):
        _fail_closed("invalid_fill_price")
    try:
        normalized = float(fill_price)
    except (TypeError, ValueError) as exc:
        raise FailClosedError("invalid_fill_price") from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        _fail_closed("invalid_fill_price")
    return normalized


def _validate_bar(market_bar: OHLCVBar) -> tuple[float, float]:
    if not isinstance(market_bar, OHLCVBar):
        _fail_closed("invalid_market_bar:type")
    try:
        high_price = float(market_bar.high)
        low_price = float(market_bar.low)
    except (TypeError, ValueError) as exc:
        raise FailClosedError("invalid_spread") from exc
    if not math.isfinite(high_price) or not math.isfinite(low_price):
        _fail_closed("invalid_spread")
    spread = high_price - low_price
    if spread <= 0.0:
        _fail_closed("invalid_spread")
    return high_price, low_price


class SlippageEngine:
    def apply_slippage(self, fill_price: float, side: OrderSide | str, market_bar: OHLCVBar) -> float:
        normalized_fill_price = _validate_fill_price(fill_price)
        normalized_side = _normalize_side(side)
        high_price, low_price = _validate_bar(market_bar)
        spread = high_price - low_price
        slippage = spread * 0.25

        if normalized_side is OrderSide.BUY:
            adjusted_price = normalized_fill_price + slippage
        else:
            adjusted_price = normalized_fill_price - slippage

        if not math.isfinite(adjusted_price) or adjusted_price <= 0.0:
            _fail_closed("invalid_slippage_price")
        return round(adjusted_price, 6)


__all__ = ["SlippageEngine"]
