"""Deterministic BIST-style execution: vol-based spread, slippage, liquidity, trend pressure (no RNG)."""

from __future__ import annotations

import os
from typing import Any, Optional

from bist_core.execution.tick_size import get_tick_size, round_to_tick

# Depth required per unit size for fill-ratio.
_DEFAULT_DEPTH_PER_UNIT = 200.0

# Reject fills when projected fill ratio below this.
_MIN_FILL_RATIO = 0.22

# Minimum volume proxy vs size.
_LIQUIDITY_FLOOR = 10.0
_VOLUME_PER_UNIT_MULT = 25.0


class RealisticExecutionEngine:
    """Paper execution: spread = vol×0.02, size/vol slippage, trend pressure, deterministic latency."""

    def __init__(
        self,
        *,
        commission_bps: float = 2.0,
        depth_per_unit: float = _DEFAULT_DEPTH_PER_UNIT,
        min_fill_ratio: float = _MIN_FILL_RATIO,
        liquidity_floor: float = _LIQUIDITY_FLOOR,
        volume_per_unit_mult: float = _VOLUME_PER_UNIT_MULT,
    ) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self._seq: int = 0
        self._commission_bps = float(commission_bps)
        try:
            dpu = float(os.environ.get("BIST_REALISM_DEPTH_PER_UNIT", str(depth_per_unit)))
        except ValueError:
            dpu = float(depth_per_unit)
        self._depth_per_unit = max(0.01, min(1_000_000.0, float(dpu)))
        try:
            mfr = float(os.environ.get("BIST_REALISM_MIN_FILL_RATIO", str(min_fill_ratio)))
        except ValueError:
            mfr = float(min_fill_ratio)
        self._min_fill_ratio = max(0.05, min(0.5, float(mfr)))
        try:
            lf = float(os.environ.get("BIST_REALISM_LIQUIDITY_FLOOR", str(liquidity_floor)))
        except ValueError:
            lf = float(liquidity_floor)
        self._liquidity_floor = max(0.0, float(lf))
        try:
            vpu = float(
                os.environ.get("BIST_REALISM_VOLUME_PER_UNIT_MULT", str(volume_per_unit_mult))
            )
        except ValueError:
            vpu = float(volume_per_unit_mult)
        self._volume_per_unit_mult = max(0.01, min(10_000.0, float(vpu)))
        try:
            self._border_fill_max = float(
                os.environ.get("BIST_REALISM_BORDER_FILL_MAX", "0.42")
            )
        except ValueError:
            self._border_fill_max = 0.42
        self._border_fill_max = max(0.0, min(0.9, self._border_fill_max))
        try:
            self._border_miss_mix = float(
                os.environ.get("BIST_REALISM_MISS_MIX_THRESHOLD", "0.48")
            )
        except ValueError:
            self._border_miss_mix = 0.48
        self._border_miss_mix = max(0.0, min(0.95, self._border_miss_mix))
        try:
            self._slippage_mult = float(
                os.environ.get("BIST_REALISM_SLIP_MULT", "1.0")
            )
        except ValueError:
            self._slippage_mult = 1.0
        self._slippage_mult = max(0.5, min(1.5, self._slippage_mult))

    def _next_id(self) -> str:
        self._seq += 1
        return f"rfx:{self._seq:010d}"

    @staticmethod
    def _mix01(symbol: str, salt: int, price: float) -> float:
        """Deterministic scalar in ~[0,1) from symbol + price (no randomness)."""
        sym = str(symbol).strip().upper()
        p = int(round(float(price) * 1_000_000)) & 0xFFFFFFFF
        h = sum((i + 1 + salt) * ord(c) for i, c in enumerate(sym)) & 0xFFFFFFFF
        mix = (p ^ (h * 0x9E3779B9) ^ (salt * 0x85EBCA6B)) & 0xFFFF
        return (mix % 10001) / 10000.0

    def _spread_fraction(self, volatility: float) -> float:
        """Full bid–ask width as fraction of mid: spread = volatility × 0.02 (capped)."""
        v = max(0.0, min(0.5, float(volatility)))
        return min(0.05, max(0.00005, v * 0.02))

    def _slippage_fraction(
        self,
        volatility: float,
        symbol: str,
        price: float,
        *,
        size_fraction: float,
        slippage_extra_frac: float,
    ) -> float:
        """Slippage scales with vol and position size (not constant)."""
        v = max(0.0, min(0.5, float(volatility)))
        k = 0.06 + 0.08 * self._mix01(symbol, 1, price)
        base = v * k
        sf = max(0.01, min(1.0, float(size_fraction)))
        size_boost = 1.0 + 0.22 * max(0.0, sf - 0.5)
        extra = max(0.0, float(slippage_extra_frac))
        slip = (base * size_boost + extra) * self._slippage_mult
        return min(0.15, max(0.0, slip))

    def _trend_price_mult(self, side: str, trend_abs: float) -> float:
        """Order-book pressure: strong trend → worse entry (buy), better exit (sell long)."""
        t = max(-1.0, min(1.0, float(trend_abs)))
        if side == "buy":
            if t > 0.15:
                return 1.0 + 0.10 * t
            if t < -0.15:
                return 1.0 - 0.04 * abs(t)
            return 1.0
        if t > 0.15:
            return 1.0 + 0.06 * t
        if t < -0.15:
            return 1.0 - 0.04 * abs(t)
        return 1.0

    def _effective_volume_proxy(
        self, symbol: str, mid: float, volume_proxy: Optional[float], order_size: int
    ) -> float:
        """When bar volume is missing, use deterministic synthetic depth (not 100% fill)."""
        if volume_proxy is not None and float(volume_proxy) > 0.0:
            return float(volume_proxy)
        mix = self._mix01(str(symbol), 13, float(mid))
        base = float(order_size) * self._depth_per_unit * (0.40 + 0.60 * mix)
        return max(12.0, base * 0.86)

    def _liquidity_ok(self, volume_proxy: float, order_size: int) -> bool:
        vp = float(volume_proxy)
        if vp <= 0.0:
            return False
        need = max(self._liquidity_floor, float(order_size) * self._volume_per_unit_mult)
        return vp >= need

    def _fill_ratio(
        self,
        volume_proxy: float,
        order_size: int,
        size_fraction: float,
    ) -> float:
        if order_size <= 0:
            return 0.0
        vp = float(volume_proxy)
        # Larger effective size → lower fill ratio (illiquidity).
        sf = max(0.01, min(1.0, float(size_fraction)))
        eff = float(order_size) * (0.65 + 0.35 * sf)
        denom = eff * self._depth_per_unit
        if denom <= 0.0:
            return 0.0
        return max(0.0, min(1.0, vp / denom))

    def _execution_delay_ms(self, volatility: float, symbol: str, price: float) -> float:
        """Deterministic delay from volatility (random-like, no RNG)."""
        v = max(0.0, min(0.5, float(volatility)))
        base = v * 85_000.0 * self._mix01(symbol, 8, price)
        return max(1.0, min(600_000.0, base))

    def create_order(self, symbol: str, side: str, price: float, size: int) -> dict[str, Any]:
        oid = self._next_id()
        order: dict[str, Any] = {
            "id": oid,
            "symbol": str(symbol),
            "side": str(side),
            "price": float(price),
            "size": int(size),
            "filled": 0,
            "status": "pending",
        }
        self.orders[oid] = order
        return order

    def process_fill(
        self,
        order: dict[str, Any],
        volatility: float,
        volume_proxy: Optional[float] = None,
        *,
        slippage_extra_frac: float = 0.0,
        size_fraction: float = 1.0,
        trend_abs: float = 0.0,
    ) -> Optional[dict[str, Any]]:
        """
        Mid price = ``order['price']``.

        ``buy``: fill ≈ mid × (1 + spread/2) × (1 + slippage) × trend, then tick.
        ``sell``: fill ≈ mid × (1 − spread/2) × (1 − slippage) × trend, then tick.
        """
        mid = float(order["price"])
        symbol = str(order.get("symbol", ""))
        side = str(order.get("side", ""))

        if mid <= 0:
            return None

        size = int(order["size"])
        if size <= 0:
            return None

        sf = max(0.01, min(1.0, float(size_fraction)))

        eff_vp = self._effective_volume_proxy(symbol, mid, volume_proxy, size)
        if not self._liquidity_ok(eff_vp, size):
            return None

        fill_ratio = self._fill_ratio(eff_vp, size, sf)
        if fill_ratio < self._min_fill_ratio:
            return None

        # Borderline liquidity → deterministic missed trade
        if fill_ratio < self._border_fill_max:
            thr = self._mix01(symbol, 7, float(volatility))
            if thr < self._border_miss_mix:
                return None

        tick = get_tick_size(mid)
        if tick <= 0:
            return None

        spread_frac = self._spread_fraction(volatility)
        half = spread_frac / 2.0

        slip = self._slippage_fraction(
            volatility,
            symbol,
            mid,
            size_fraction=sf,
            slippage_extra_frac=slippage_extra_frac,
        )

        if side == "buy":
            px = mid * (1.0 + half) * (1.0 + slip)
        else:
            px = mid * (1.0 - half) * (1.0 - slip)

        px *= self._trend_price_mult(side, trend_abs)

        exec_price = round_to_tick(px)
        if exec_price <= 0:
            return None

        filled_qty = max(1, int(size * fill_ratio))
        filled_qty = min(filled_qty, size)

        notional = exec_price * float(filled_qty)
        commission = notional * (self._commission_bps / 10_000.0)
        spread_cost = notional * half

        order["filled"] = int(order["filled"]) + filled_qty
        if order["filled"] >= size:
            order["status"] = "filled"
        else:
            order["status"] = "partial"

        delay_bars = int(round((1.0 - min(1.0, fill_ratio)) * 5.0))
        delay_bars = max(0, min(5, delay_bars))

        delay_ms = self._execution_delay_ms(volatility, symbol, mid)
        delay_ms += (1.0 - min(1.0, fill_ratio)) * 2_000.0
        delay_ms = max(1.0, min(650_000.0, delay_ms))

        if os.environ.get("BIST_REALISM_DEBUG", "").strip() in ("1", "true", "yes", "on"):
            print(
                {
                    "symbol": symbol,
                    "mid_price": mid,
                    "executed_price": exec_price,
                    "spread_fraction": spread_frac,
                    "slippage_fraction": slip,
                    "fill_ratio": fill_ratio,
                    "filled_qty": filled_qty,
                    "commission": commission,
                    "spread_cost": spread_cost,
                    "execution_delay_bars": delay_bars,
                    "execution_delay_ms": delay_ms,
                }
            )

        return {
            "price": float(exec_price),
            "mid_price": float(mid),
            "filled_qty": int(filled_qty),
            "status": str(order["status"]),
            "spread_fraction": float(spread_frac),
            "slippage_fraction": float(slip),
            "commission": float(commission),
            "spread_cost": float(spread_cost),
            "fill_ratio": float(fill_ratio),
            "execution_delay_bars": int(delay_bars),
            "execution_delay_ms": float(delay_ms),
        }


__all__ = ["RealisticExecutionEngine"]
