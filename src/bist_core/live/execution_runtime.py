"""Paper execution against :class:`LiveState` — deterministic, no network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bist_core.execution.market_realism_metrics import MarketRealismMetrics
from bist_core.execution.realistic_execution_engine import RealisticExecutionEngine
from bist_core.execution.tick_size import round_to_tick
from bist_core.live.stop_target_risk import compute_atr_stop_target
from bist_core.live.state_store import LiveState
from bist_core.models.ohlcv import OHLCVBar


def _validate_exit_reason_pnl(reason: str, pnl_fraction: float) -> None:
    """Enforce sign vs exit reason (target must win, stop must lose)."""
    r = str(reason).lower()
    p = float(pnl_fraction)
    if "target_hit" in r and p <= 0:
        raise RuntimeError("INVALID PNL: target_hit but pnl <= 0")
    if ("stop_loss" in r or "stop_hit" in r) and p >= 0:
        raise RuntimeError("INVALID PNL: stop_hit but pnl >= 0")


def _leg_pnl_fraction(entry: float, exit_px: float, *, is_short: bool) -> float:
    e = float(entry)
    x = float(exit_px)
    if e <= 0:
        return 0.0
    if is_short:
        return (e - x) / e
    return (x - e) / e


def _leg_dollar_pnl(entry: float, exit_px: float, take: float, *, is_short: bool) -> float:
    e = float(entry)
    x = float(exit_px)
    t = float(take)
    if is_short:
        return (e - x) * t
    return (x - e) * t


class PaperExecution:
    """Apply enter/exit using :class:`RealisticExecutionEngine` (spread, slip, liquidity, trend)."""

    def __init__(self, state: LiveState) -> None:
        self.state = state
        self.fill_engine = RealisticExecutionEngine()
        self.realism_metrics = MarketRealismMetrics()
        self.fill_attempts = 0
        self.fills_ok = 0
        self._max_total_positions: int = 3
        self._max_symbol_fraction: float = 1.0
        self._daily_loss_limit: float = -0.2

    def _forced_sell_fill(
        self,
        symbol: str,
        mid: float,
        volatility: float,
        *,
        slippage_extra_frac: float,
        size_fraction: float,
        trend_abs: float,
    ) -> dict[str, Any]:
        """Deterministic exit price when process_fill misses (border/liquidity) — position must close."""
        eng = self.fill_engine
        spread_frac = eng._spread_fraction(volatility)
        half = spread_frac / 2.0
        sf = max(0.01, min(1.0, float(size_fraction)))
        slip = eng._slippage_fraction(
            volatility,
            str(symbol),
            float(mid),
            size_fraction=sf,
            slippage_extra_frac=float(slippage_extra_frac),
        )
        px = float(mid) * (1.0 - half) * (1.0 - slip)
        px *= eng._trend_price_mult("sell", trend_abs)
        exec_price = round_to_tick(px)
        if exec_price <= 0:
            exec_price = round_to_tick(float(mid) * (1.0 - half)) or float(mid)
        dms = eng._execution_delay_ms(volatility, str(symbol), float(mid))
        return {
            "price": float(exec_price),
            "mid_price": float(mid),
            "spread_fraction": float(spread_frac),
            "slippage_fraction": float(slip),
            "execution_delay_ms": float(dms),
        }

    def _forced_buy_fill(
        self,
        symbol: str,
        mid: float,
        volatility: float,
        *,
        slippage_extra_frac: float,
        size_fraction: float,
        trend_abs: float,
    ) -> dict[str, Any]:
        """Deterministic buy fill when process_fill misses — mirrors engine buy path, no RNG."""
        eng = self.fill_engine
        spread_frac = eng._spread_fraction(volatility)
        half = spread_frac / 2.0
        sf = max(0.01, min(1.0, float(size_fraction)))
        slip = eng._slippage_fraction(
            volatility,
            str(symbol),
            float(mid),
            size_fraction=sf,
            slippage_extra_frac=float(slippage_extra_frac),
        )
        px = float(mid) * (1.0 + half) * (1.0 + slip)
        px *= eng._trend_price_mult("buy", trend_abs)
        exec_price = round_to_tick(px)
        if exec_price <= 0:
            exec_price = round_to_tick(float(mid) * (1.0 + half)) or float(mid)
        dms = eng._execution_delay_ms(volatility, str(symbol), float(mid))
        return {
            "price": float(exec_price),
            "mid_price": float(mid),
            "spread_fraction": float(spread_frac),
            "slippage_fraction": float(slip),
            "execution_delay_ms": float(dms),
        }

    def _enter_reject(
        self,
        symbol: str,
        reason: str,
        edge_val: Any,
    ) -> None:
        print(
            {
                "EXECUTION_REJECT_REASON": {
                    "symbol": symbol,
                    "reason": reason,
                    "edge": edge_val,
                    "position_count": len(self.state.positions or {}),
                }
            },
            flush=True,
        )

    def execute(
        self,
        symbol: str,
        action: str,
        price: float,
        *,
        reason: str = "",
        wall_ts: float | None = None,
        volatility: float = 0.02,
        volume_proxy: float | None = None,
        slippage_extra_frac: float = 0.0,
        size_fraction: float = 1.0,
        trend_abs: float = 0.0,
        stop_loss: float | None = None,
        target: float | None = None,
        ohlcv_bars: list[OHLCVBar] | None = None,
        vol_norm: float | None = None,
        position_side: str = "long",
        edge_score: float | None = None,
        is_replacement: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Mid ``price``; engine applies spread/slippage/trend. Returns ``None`` on miss/no fill."""
        if not hasattr(self, "fills_ok"):
            self.fills_ok = 0
        if not hasattr(self, "fill_attempts"):
            self.fill_attempts = 0
        print({
            "EXECUTION_PROOF": {
                "symbol": symbol,
                "action": action,
                "price": price,
                "edge_score": edge_score
            }
        }, flush=True)
        print({"EXECUTOR_ENTER": symbol})
        self.fill_attempts += 1
        if price <= 0:
            return None

        ts_iso = datetime.now(timezone.utc).isoformat()
        if wall_ts is not None:
            ts_iso = datetime.fromtimestamp(float(wall_ts), tz=timezone.utc).isoformat()

        qty_scale = max(0.01, min(1.0, float(size_fraction)))
        ta = max(-1.0, min(1.0, float(trend_abs)))

        action = str(action).strip().lower()
        if action in ("enter_long", "enter_short", "aggressive_enter"):
            action = "enter"

        if action == "enter":
            try:
                edge = float(edge_score)
            except Exception:
                raise RuntimeError("EDGE_SSOT_VIOLATION") from None

            if edge != edge or edge in (float("inf"), float("-inf")):
                self._enter_reject(symbol, "INVALID_EDGE", edge_score)
                return None

            if not (edge >= 0.60):
                self._enter_reject(symbol, "EDGE_BELOW_THRESHOLD", edge)
                return None

            print(
                {
                    "EXECUTION_EDGE_CHECK": {
                        "edge": edge,
                        "passed": edge >= 0.60,
                    }
                },
                flush=True,
            )

            _enter_out: Optional[dict[str, Any]] = None

            print(
                {
                    "POSITION_CHECK": {
                        "symbol": symbol,
                        "current_positions": list(self.state.positions.keys()),
                        "position_count": len(self.state.positions),
                        "max_allowed": (
                            self.max_positions
                            if hasattr(self, "max_positions")
                            else (
                                self._max_total_positions
                                if hasattr(self, "_max_total_positions")
                                else "unknown"
                            )
                        ),
                    }
                },
                flush=True,
            )

            _existing_legs = self.state.positions.get(symbol, [])
            if _existing_legs and any(
                int(p.get("size", 0) or 0) > 0 for p in _existing_legs
            ):
                active_legs = [
                    p
                    for p in _existing_legs
                    if int(p.get("size", 0) or 0) > 0
                ]
                old_edges: list[float] = []
                for p in active_legs:
                    try:
                        oe = float(p.get("edge_score", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        oe = 0.0
                    if oe == oe:
                        old_edges.append(oe)
                edge_old = max(old_edges) if old_edges else 0.0
                allow_update = bool(edge > edge_old)
                print(
                    {
                        "POSITION_UPDATE_CHECK": {
                            "symbol": symbol,
                            "edge_old": edge_old,
                            "edge_new": edge,
                            "decision": ("allow" if allow_update else "skip"),
                            "is_replacement": bool(is_replacement),
                        }
                    },
                    flush=True,
                )
                if (not bool(is_replacement)) and (not allow_update):
                    self._enter_reject(
                        symbol, "POSITION_ALREADY_EXISTS", edge
                    )
                    return None
            if len(self.state.positions.get(symbol, [])) > 5:
                self._enter_reject(
                    symbol, "MAX_POSITIONS_REACHED", edge
                )
                return None
            open_syms = [s for s, p in self.state.positions.items() if p]
            if (
                symbol not in open_syms
                and len(open_syms) >= self._max_total_positions
            ):
                self._enter_reject(
                    symbol, "MAX_POSITIONS_REACHED", edge
                )
                return None
            existing = sum(
                float(p.get("qty", 1.0)) for p in self.state.positions.get(symbol, [])
            )
            # Clip to per-symbol headroom (risk layer may pass size_fraction=1.0 while cap is e.g. 0.30).
            headroom = max(0.0, float(self._max_symbol_fraction) - float(existing))
            qty_scale = min(qty_scale, headroom)
            if qty_scale < 0.01 - 1e-12:
                self._enter_reject(symbol, "SIZE_TOO_SMALL", edge_score)
                return None
            if self.state.daily_pnl <= self._daily_loss_limit:
                self._enter_reject(symbol, "CAPITAL_LIMIT", edge_score)
                return None

            mid = float(price)
            self.realism_metrics.record_attempt()
            order = self.fill_engine.create_order(symbol, "buy", mid, 1)
            fill = self.fill_engine.process_fill(
                order,
                float(volatility),
                volume_proxy,
                slippage_extra_frac=float(slippage_extra_frac),
                size_fraction=qty_scale,
                trend_abs=ta,
            )
            if fill is None:
                fill = self._forced_buy_fill(
                    symbol,
                    mid,
                    float(volatility),
                    slippage_extra_frac=float(slippage_extra_frac),
                    size_fraction=qty_scale,
                    trend_abs=ta,
                )

            exec_px = float(fill["price"])
            if exec_px <= 0:
                self.realism_metrics.record_miss()
                self._enter_reject(symbol, "FILL_FAILED", edge)
                return None

            slip_f = float(fill.get("slippage_fraction", 0.0))
            dms = float(fill.get("execution_delay_ms", 0.0))
            self.realism_metrics.record_fill(
                slippage_fraction=slip_f,
                delay_ms=dms,
            )

            self.state.order_seq += 1
            order_id = str(order.get("id", f"{symbol}-{self.state.order_seq}"))
            _side = (
                "short" if str(position_side).strip().lower() == "short" else "long"
            )
            pos = {
                "entry_price": exec_px,
                "size": 1,
                "qty": float(qty_scale),
                "order_id": order_id,
                "side": _side,
                "edge_score": float(edge),
            }
            sl_use: float | None = None
            tg_use: float | None = None
            bars_ok: list[OHLCVBar] | None = None
            if ohlcv_bars is not None:
                bars_ok = [b for b in ohlcv_bars if isinstance(b, OHLCVBar)]
            if bars_ok is not None and len(bars_ok) >= 15:
                is_short = str(position_side).strip().lower() == "short"
                dbg = compute_atr_stop_target(
                    float(exec_px),
                    is_short=is_short,
                    bars=bars_ok,
                    vol_norm=vol_norm,
                )
                if dbg is not None:
                    sl_use = float(dbg["stop"])
                    tg_use = float(dbg["target"])
                    print({"STOP_DEBUG": dbg}, flush=True)
            if sl_use is None and stop_loss is not None:
                try:
                    slv = float(stop_loss)
                    if slv > 0:
                        sl_use = slv
                except (TypeError, ValueError):
                    pass
            if tg_use is None and target is not None:
                try:
                    tgv = float(target)
                    if tgv > 0:
                        tg_use = tgv
                except (TypeError, ValueError):
                    pass
            if sl_use is not None and sl_use > 0:
                pos["stop_loss"] = float(sl_use)
            if tg_use is not None and tg_use > 0:
                pos["target"] = float(tg_use)

            _enter_out = {
                "ok": False,
                "action": "enter",
                "symbol": symbol,
                "actual_fill_price": exec_px,
                "mid_price": float(fill.get("mid_price", mid)),
                "spread_fraction": float(fill.get("spread_fraction", 0.0)),
                "slippage_fraction": slip_f,
                "execution_delay_ms": dms,
            }

            _enter_out["ok"] = True

            if locals().get("_enter_out", {}).get("ok", False):
                self.state.positions.setdefault(symbol, []).append(pos)

                print(
                    {
                        "POSITION_STORED": {
                            "symbol": symbol,
                            "price": float(fill["price"]),
                        }
                    },
                    flush=True,
                )

                print(
                    {
                        "symbol": symbol,
                        "action": action,
                        "mid_price": float(fill.get("mid_price", mid)),
                        "price": exec_px,
                        "actual_fill_price": exec_px,
                        "size": 1,
                        "pnl": None,
                        "reason": reason,
                        "timestamp": ts_iso,
                        "order_id": order_id,
                        "equity": self.state.equity,
                        "spread_fraction": fill.get("spread_fraction"),
                        "slippage_fraction": slip_f,
                        "execution_delay_ms": dms,
                    }
                )
            if _enter_out is None:
                print(
                    {
                        "EXECUTION_REJECT_REASON": {
                            "symbol": symbol,
                            "reason": "UNKNOWN_BLOCK",
                            "edge": edge_score,
                            "position_count": len(self.state.positions or {}),
                        }
                    },
                    flush=True,
                )
                return None
            self.fills_ok += 1
            return _enter_out

        elif action == "exit":
            positions = list(self.state.positions.get(symbol, []))
            if not positions:
                return None
            total_q = sum(float(p.get("qty", 1.0)) for p in positions)
            close_target = total_q * qty_scale
            if close_target <= 1e-12:
                return None

            mid = float(price)

            sorted_pos = sorted(
                positions,
                key=lambda p: str(p.get("order_id", "")),
            )

            legs: list[tuple[dict[str, Any], float, float]] = []
            remaining = close_target
            new_positions: list[dict[str, Any]] = []

            for pos in sorted_pos:
                q = float(pos.get("qty", 1.0))
                if q <= 0:
                    continue
                if remaining <= 1e-12:
                    new_positions.append(pos)
                    continue
                take = min(q, remaining)
                entry = float(pos["entry_price"])
                if entry <= 0:
                    new_positions.append(pos)
                    continue

                self.realism_metrics.record_attempt()
                sell = self.fill_engine.create_order(symbol, "sell", mid, 1)
                fill = self.fill_engine.process_fill(
                    sell,
                    float(volatility),
                    volume_proxy,
                    slippage_extra_frac=float(slippage_extra_frac),
                    size_fraction=max(qty_scale, take),
                    trend_abs=ta,
                )
                if fill is None:
                    fill = self._forced_sell_fill(
                        symbol,
                        mid,
                        float(volatility),
                        slippage_extra_frac=float(slippage_extra_frac),
                        size_fraction=max(qty_scale, take),
                        trend_abs=ta,
                    )
                exit_px = float(fill["price"])
                if exit_px <= 0:
                    self.realism_metrics.record_miss()
                    return None
                slip_f = float(fill.get("slippage_fraction", 0.0))
                dms = float(fill.get("execution_delay_ms", 0.0))
                self.realism_metrics.record_fill(
                    slippage_fraction=slip_f,
                    delay_ms=dms,
                )
                legs.append((pos, exit_px, take))
                remaining -= take
                if take + 1e-12 < q:
                    pos2 = dict(pos)
                    pos2["qty"] = q - take
                    new_positions.append(pos2)

            if not legs:
                return None

            agg_pnl = 0.0
            dollar_pnl = 0.0
            for _pos, exit_px, take in legs:
                entry = float(_pos["entry_price"])
                is_short = (
                    str(_pos.get("side", "long")).strip().lower() == "short"
                )
                pnl = _leg_pnl_fraction(entry, exit_px, is_short=is_short)
                agg_pnl += float(pnl) * take
                dollar_pnl += _leg_dollar_pnl(entry, exit_px, take, is_short=is_short)
                self.state.equity *= 1.0 + float(pnl) * take
                self.state.daily_pnl += float(pnl) * take

            _validate_exit_reason_pnl(str(reason), float(agg_pnl))

            self.state.order_seq += 1
            order_id = f"{symbol}-x-{self.state.order_seq}"
            self.state.positions[symbol] = new_positions

            w = sum(t for _p, _e, t in legs)
            mean_entry = (
                sum(float(p["entry_price"]) * t for p, _e, t in legs) / w
                if w > 0
                else 0.0
            )
            avg_exit = sum(ex for _p, ex, _t in legs) / len(legs)
            print(
                {
                    "symbol": symbol,
                    "action": action,
                    "mid_price": mid,
                    "price": avg_exit,
                    "actual_fill_price": avg_exit,
                    "size": float(w),
                    "pnl": agg_pnl,
                    "reason": reason,
                    "timestamp": ts_iso,
                    "order_id": order_id,
                    "equity": self.state.equity,
                }
            )
            self.fills_ok += 1
            return {
                "ok": True,
                "action": "exit",
                "symbol": symbol,
                "pnl": float(agg_pnl),
                "entry_price": float(mean_entry),
                "exit_price": float(avg_exit),
                "actual_fill_price": float(avg_exit),
                "mid_price": float(mid),
                "size": float(w),
                "dollar_pnl": float(dollar_pnl),
                "reason": str(reason),
            }

        return None

    def close_position(self, symbol: str) -> Optional[dict[str, Any]]:
        """Close entire symbol position deterministically using average entry as exit mid."""
        legs = list(self.state.positions.get(symbol, []))
        if not legs:
            return None
        qty_total = 0.0
        weighted_entry = 0.0
        for p in legs:
            try:
                q = float(p.get("qty", 1.0) or 0.0)
                e = float(p.get("entry_price", 0.0) or 0.0)
            except (TypeError, ValueError):
                q = 0.0
                e = 0.0
            if q <= 0 or e <= 0:
                continue
            qty_total += q
            weighted_entry += q * e
        if qty_total <= 0:
            return None
        mid = weighted_entry / qty_total
        return self.execute(str(symbol), "exit", float(mid), reason="portfolio_replacement")

    def get_open_positions(self) -> set[str]:
        """Uppercase symbols with at least one open leg (``size`` > 0), aligned with enter skip rules."""
        out: set[str] = set()
        for sym, legs in {
            k: v
            for k, v in (self.state.positions or {}).items()
            if v and isinstance(v, list)
        }.items():
            if not any(int(p.get("size", 0) or 0) > 0 for p in legs):
                continue
            out.add(str(sym).strip().upper())
        return out

    def execute_trade(
        self,
        symbol: str,
        action: str,
        size: float,
        price: float,
        **kwargs: Any,
    ) -> Optional[dict[str, Any]]:
        """Execute trade with explicit logging.

        Wrapper around execute() that logs EXECUTION_CALLED and size.
        Called from portfolio loop for each entry decision.
        Deterministic path — no RNG, all decisions are from portfolio_engine.
        """
        print(
            {
                "EXECUTION_CALLED": {
                    "symbol": str(symbol),
                    "action": str(action),
                    "size": float(size),
                    "price": float(price),
                }
            },
            flush=True,
        )
        result = self.execute(str(symbol), str(action), float(price), **kwargs)
        return result

    def configure_risk(
        self,
        *,
        max_total_positions: int = 3,
        max_symbol_fraction: float = 1.0,
        daily_loss_limit: float = -0.2,
    ) -> None:
        self._max_total_positions = max(1, int(max_total_positions))
        self._max_symbol_fraction = max(0.01, min(1.0, float(max_symbol_fraction)))
        self._daily_loss_limit = float(daily_loss_limit)


__all__ = ["PaperExecution"]
