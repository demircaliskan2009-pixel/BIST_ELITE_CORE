"""Position and portfolio tracker engine.

Deterministic, fail-closed tracker for paper / dry-run execution.

Design rules:
  - No external I/O — purely in-process state.
  - Deterministic: same fill stream → same state in all replays.
  - Fail-closed on malformed fills: raises FillValidationError.
  - No live broker logic.
  - Thread safety: NOT guaranteed (single-threaded pipeline use only).

PRD reference: §1.21 NT-R rules, §1.26 Margin.
"""

from __future__ import annotations

import dataclasses
import time

from crypto_core.cvar import CVaRConfig, CVaREngine, CVaRSnapshot, ReturnObservation
from crypto_core.execution.models import OrderIntent
from crypto_core.portfolio.fills import FillValidationError, SyntheticFill
from crypto_core.portfolio.models import PortfolioSnapshot, Position, PositionSide

# ---------------------------------------------------------------------------
# Internal mutable position state
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _MutablePosition:
    """Internal mutable state for one symbol/exchange position.

    PositionTracker only exposes immutable snapshots externally.
    """

    symbol: str
    exchange: str
    side: PositionSide
    quantity: float  # base-currency, ≥ 0
    avg_entry_price: float  # USD
    mark_price: float  # USD
    leverage: float  # [1.0, 3.0]
    realized_pnl: float  # USD accumulated today, signed
    liquidation_price: float | None  # from exchange; None = unavailable

    def unrealized_pnl(self) -> float:
        """Mark-to-market PnL in USD."""
        if self.side == PositionSide.FLAT or self.quantity == 0.0:
            return 0.0
        if self.side == PositionSide.LONG:
            return (self.mark_price - self.avg_entry_price) * self.quantity
        # SHORT
        return (self.avg_entry_price - self.mark_price) * self.quantity

    def notional_usd(self) -> float:
        return self.quantity * self.mark_price

    def dtl_pct(self) -> float | None:
        """Distance-to-liquidation as % of mark price.  None if liq unavailable."""
        if self.liquidation_price is None or self.mark_price <= 0.0:
            return None
        return abs(self.mark_price - self.liquidation_price) / self.mark_price * 100.0

    def to_snapshot(self, nav_usd: float | None, snapshot_ns: int) -> Position:
        """Produce an immutable Position snapshot."""
        notional = self.notional_usd()
        risk_pct: float | None = None
        if nav_usd is not None and nav_usd > 0.0:
            risk_pct = notional / nav_usd * 100.0
        return Position(
            symbol=self.symbol,
            exchange=self.exchange,
            side=self.side,
            quantity=self.quantity,
            avg_entry_price=self.avg_entry_price,
            mark_price=self.mark_price,
            leverage=self.leverage,
            unrealized_pnl=self.unrealized_pnl(),
            realized_pnl=self.realized_pnl,
            notional_usd=notional,
            snapshot_ns=snapshot_ns,
            position_risk_pct=risk_pct,
            liquidation_price=self.liquidation_price,
            dtl_pct=self.dtl_pct(),
        )


# ---------------------------------------------------------------------------
# Position tracker
# ---------------------------------------------------------------------------

#: Hard leverage cap enforced by the system.
_MAX_LEVERAGE: float = 3.0
#: Minimum fill price allowed (sanity check).
_MIN_PRICE: float = 1e-8
#: Minimum fill quantity allowed.
_MIN_QUANTITY: float = 1e-12


class PositionTracker:
    """Deterministic in-process position and portfolio tracker.

    Usage::

        tracker = PositionTracker(initial_nav_usd=10_000.0)
        tracker.apply_fill(fill)
        snapshot = tracker.portfolio_snapshot()

    Invariants:
      - apply_fill raises FillValidationError on malformed fills.
      - Deterministic replay: identical fill stream → identical snapshot.
      - update_mark never raises; silently ignores unknown symbols.
      - reset_day_pnl resets only today's realized PnL counters.
    """

    def __init__(
        self,
        initial_nav_usd: float = 10_000.0,
        margin_used_pct: float | None = None,
        cvar_config: CVaRConfig | None = None,
    ) -> None:
        """Initialize the tracker.

        Args:
            initial_nav_usd: starting NAV / equity in USD.
            margin_used_pct: optional exchange-supplied margin usage %; None = unavailable.
        """
        if initial_nav_usd <= 0.0:
            raise ValueError(f"initial_nav_usd must be positive; got {initial_nav_usd}")
        self._nav_usd: float = initial_nav_usd
        self._cash_usd: float = initial_nav_usd  # all cash at start
        # key: (symbol, exchange) → _MutablePosition
        self._positions: dict[tuple[str, str], _MutablePosition] = {}
        # today's total realized PnL in USD
        self._daily_realized_pnl: float = 0.0
        # optional margin data from exchange (updated externally)
        self._margin_used_pct: float | None = margin_used_pct
        # bounded historical CVaR return stream state
        self._cvar_engine = CVaREngine(cvar_config)
        self._last_cvar_snapshot_ns: int | None = None
        self._last_cvar_nav_usd: float | None = None
        self._prev_cvar_nav_usd: float | None = None

    # -----------------------------------------------------------------------
    # Fill application
    # -----------------------------------------------------------------------

    def apply_fill(self, fill: SyntheticFill) -> None:
        """Update position state from one synthetic fill.

        Raises:
            FillValidationError: if the fill is malformed or creates an
                                  impossible state transition.
        """
        self._validate_fill(fill)
        key = (fill.symbol, fill.exchange)
        pos = self._positions.get(key)
        if pos is None:
            pos = _MutablePosition(
                symbol=fill.symbol,
                exchange=fill.exchange,
                side=PositionSide.FLAT,
                quantity=0.0,
                avg_entry_price=0.0,
                mark_price=fill.fill_price,
                leverage=fill.leverage,
                realized_pnl=0.0,
                liquidation_price=None,
            )
            self._positions[key] = pos

        if fill.intent == OrderIntent.BUY:
            self._apply_buy(pos, fill)
        else:
            self._apply_sell(pos, fill)

        # Update mark price to fill price (paper tracking — no separate tick yet)
        pos.mark_price = fill.fill_price
        # Remove flat positions to keep dict clean
        if pos.quantity == 0.0:
            pos.side = PositionSide.FLAT

    def _apply_buy(self, pos: _MutablePosition, fill: SyntheticFill) -> None:
        qty = fill.quantity
        price = fill.fill_price

        if pos.side == PositionSide.FLAT or pos.quantity == 0.0:
            # Open long
            pos.side = PositionSide.LONG
            pos.quantity = qty
            pos.avg_entry_price = price
            pos.leverage = fill.leverage
        elif pos.side == PositionSide.LONG:
            # Increase long — weighted average entry
            total_qty = pos.quantity + qty
            pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + price * qty) / total_qty
            pos.quantity = total_qty
            pos.leverage = fill.leverage
        elif pos.side == PositionSide.SHORT:
            # Reduce / close / flip short
            if qty < pos.quantity:
                # Partial close of short
                closed_qty = qty
                pnl = (pos.avg_entry_price - price) * closed_qty
                self._book_realized_pnl(pos, pnl)
                pos.quantity -= closed_qty
            elif qty == pos.quantity:
                # Full close of short
                pnl = (pos.avg_entry_price - price) * pos.quantity
                self._book_realized_pnl(pos, pnl)
                pos.quantity = 0.0
                pos.side = PositionSide.FLAT
                pos.avg_entry_price = 0.0
            else:
                # Flip: close short, open long with remainder
                close_qty = pos.quantity
                pnl = (pos.avg_entry_price - price) * close_qty
                self._book_realized_pnl(pos, pnl)
                remainder = qty - close_qty
                pos.side = PositionSide.LONG
                pos.quantity = remainder
                pos.avg_entry_price = price
                pos.leverage = fill.leverage

    def _apply_sell(self, pos: _MutablePosition, fill: SyntheticFill) -> None:
        qty = fill.quantity
        price = fill.fill_price

        if pos.side == PositionSide.FLAT or pos.quantity == 0.0:
            # Open short
            pos.side = PositionSide.SHORT
            pos.quantity = qty
            pos.avg_entry_price = price
            pos.leverage = fill.leverage
        elif pos.side == PositionSide.SHORT:
            # Increase short
            total_qty = pos.quantity + qty
            pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + price * qty) / total_qty
            pos.quantity = total_qty
            pos.leverage = fill.leverage
        elif pos.side == PositionSide.LONG:
            # Reduce / close / flip long
            if qty < pos.quantity:
                # Partial close of long
                closed_qty = qty
                pnl = (price - pos.avg_entry_price) * closed_qty
                self._book_realized_pnl(pos, pnl)
                pos.quantity -= closed_qty
            elif qty == pos.quantity:
                # Full close of long
                pnl = (price - pos.avg_entry_price) * pos.quantity
                self._book_realized_pnl(pos, pnl)
                pos.quantity = 0.0
                pos.side = PositionSide.FLAT
                pos.avg_entry_price = 0.0
            else:
                # Flip: close long, open short with remainder
                close_qty = pos.quantity
                pnl = (price - pos.avg_entry_price) * close_qty
                self._book_realized_pnl(pos, pnl)
                remainder = qty - close_qty
                pos.side = PositionSide.SHORT
                pos.quantity = remainder
                pos.avg_entry_price = price
                pos.leverage = fill.leverage

    def _book_realized_pnl(self, pos: _MutablePosition, pnl: float) -> None:
        pos.realized_pnl += pnl
        self._daily_realized_pnl += pnl

    # -----------------------------------------------------------------------
    # Mark price update
    # -----------------------------------------------------------------------

    def update_mark(self, symbol: str, exchange: str, mark_price: float) -> None:
        """Update mark price for unrealized PnL recalculation.

        Silently ignores unknown symbols (no position = no update needed).
        """
        key = (symbol, exchange)
        pos = self._positions.get(key)
        if pos is not None and mark_price > 0.0:
            pos.mark_price = mark_price

    # -----------------------------------------------------------------------
    # Margin data injection (from exchange — optional)
    # -----------------------------------------------------------------------

    def set_margin_used_pct(self, margin_used_pct: float | None) -> None:
        """Inject exchange-supplied margin utilization %.

        Args:
            margin_used_pct: used_margin / available_margin × 100, or None.
        """
        self._margin_used_pct = margin_used_pct

    # -----------------------------------------------------------------------
    # NAV update
    # -----------------------------------------------------------------------

    def update_nav(self, nav_usd: float) -> None:
        """Update NAV / equity from external P&L settlement.

        Only call this if you have a settled equity figure from the exchange.
        For paper trading, NAV tracks initial_nav + realized_pnl + unrealized_pnl.
        """
        if nav_usd <= 0.0:
            raise ValueError(f"nav_usd must be positive; got {nav_usd}")
        self._nav_usd = nav_usd

    # -----------------------------------------------------------------------
    # Day reset
    # -----------------------------------------------------------------------

    def reset_day_pnl(self) -> None:
        """Reset intraday realized PnL counters to zero.

        Call at the start of each UTC trading day.
        """
        self._daily_realized_pnl = 0.0
        for pos in self._positions.values():
            pos.realized_pnl = 0.0

    # -----------------------------------------------------------------------
    # Snapshot production
    # -----------------------------------------------------------------------

    def portfolio_snapshot(self, snapshot_ns: int | None = None) -> PortfolioSnapshot:
        """Produce an immutable PortfolioSnapshot from current state.

        Args:
            snapshot_ns: override timestamp; defaults to time.time_ns().
        """
        ts = snapshot_ns if snapshot_ns is not None else time.time_ns()
        nav = self._effective_nav()

        open_positions = [p for p in self._positions.values() if p.quantity > 0.0]

        # Compute aggregate metrics
        total_notional = sum(p.notional_usd() for p in open_positions)
        total_unrealized = sum(p.unrealized_pnl() for p in open_positions)
        long_notional = sum(p.notional_usd() for p in open_positions if p.side == PositionSide.LONG)
        short_notional = sum(p.notional_usd() for p in open_positions if p.side == PositionSide.SHORT)

        gross_exp_pct = (total_notional / nav * 100.0) if nav > 0.0 else 0.0
        net_exp_pct = ((long_notional - short_notional) / nav * 100.0) if nav > 0.0 else 0.0

        daily_pnl_usd = self._daily_realized_pnl
        daily_pnl_pct = (daily_pnl_usd / nav * 100.0) if nav > 0.0 else 0.0

        # Concentration: largest single position as % of NAV
        notionals_pct: list[float] = []
        for p in open_positions:
            if nav > 0.0:
                notionals_pct.append(p.notional_usd() / nav * 100.0)
        concentration_max = max(notionals_pct) if notionals_pct else 0.0

        # Max leverage in use
        max_leverage = max((p.leverage for p in open_positions), default=0.0)

        # Open risk pct: sum of position_risk_pct — only if ALL have nav
        open_risk_pct: float | None = None
        if nav > 0.0:
            open_risk_pct = total_notional / nav * 100.0

        # DTL count
        dtl_available = sum(1 for p in open_positions if p.dtl_pct() is not None)

        # Build Position snapshots
        pos_snapshots = tuple(p.to_snapshot(nav if nav > 0.0 else None, ts) for p in open_positions)

        return PortfolioSnapshot(
            nav_usd=nav,
            cash_usd=self._cash_usd,
            total_notional_usd=total_notional,
            gross_exposure_pct=gross_exp_pct,
            net_exposure_pct=net_exp_pct,
            daily_realized_pnl_usd=daily_pnl_usd,
            daily_realized_pnl_pct=daily_pnl_pct,
            total_unrealized_pnl_usd=total_unrealized,
            concentration_max_pct=concentration_max,
            active_position_count=len(open_positions),
            max_leverage_in_use=max_leverage,
            snapshot_ns=ts,
            open_risk_pct=open_risk_pct,
            margin_used_pct=self._margin_used_pct,
            dtl_available_count=dtl_available,
            positions=pos_snapshots,
        )

    # -----------------------------------------------------------------------
    # Conversion helpers for downstream consumers
    # -----------------------------------------------------------------------

    def to_risk_guard_input(
        self,
        kill_switch_level: int = 0,
        snapshot_ns: int | None = None,
        cvar_snapshot: CVaRSnapshot | None = None,
    ):  # → RiskGuardInput
        """Produce a RiskGuardInput from current portfolio state.

        Populates all fields that the tracker can compute, including
        portfolio CVaR when sufficient return history exists.

        Args:
            kill_switch_level: caller-supplied KS level (from KS engine).
            snapshot_ns: override snapshot timestamp.
        """
        from crypto_core.guard.models import RiskGuardInput

        snap = self.portfolio_snapshot(snapshot_ns)
        cvar = cvar_snapshot if cvar_snapshot is not None else self.cvar_snapshot(snapshot_ns)
        return RiskGuardInput(
            kill_switch_level=kill_switch_level,
            daily_pnl_pct=snap.daily_realized_pnl_pct,
            open_risk_pct=snap.open_risk_pct,
            max_single_position_pct=snap.concentration_max_pct if snap.active_position_count > 0 else None,
            portfolio_cvar99_pct=cvar.cvar99_pct if cvar.available else None,
            margin_used_pct=snap.margin_used_pct,
        )

    def to_cvar_input(
        self,
        snapshot_ns: int | None = None,
        cvar_limit_pct: float = 5.0,
        cvar_snapshot: CVaRSnapshot | None = None,
    ):
        """Produce a real CVaRInput from tracked portfolio return history."""
        from crypto_core.risk.contracts import CVaRInput

        snapshot = cvar_snapshot if cvar_snapshot is not None else self.cvar_snapshot(snapshot_ns)
        return CVaRInput(
            cvar99_pct=snapshot.cvar99_pct if snapshot.available else None,
            cvar_limit_pct=cvar_limit_pct,
            var99_pct=snapshot.var99_pct if snapshot.available else None,
            history_count=snapshot.history_count,
            available=snapshot.available,
        )

    def to_portfolio_risk_snapshot(self, snapshot_ns: int | None = None):  # → PortfolioRiskSnapshot
        """Produce a PortfolioRiskSnapshot for RiskEngine v2 gate.

        Args:
            snapshot_ns: override snapshot timestamp.
        """
        from crypto_core.risk.contracts import PortfolioRiskSnapshot

        snap = self.portfolio_snapshot(snapshot_ns)
        return PortfolioRiskSnapshot(
            total_exposure_usd=snap.total_notional_usd,
            active_position_count=snap.active_position_count,
            max_leverage_in_use=snap.max_leverage_in_use,
        )

    def cvar_snapshot(self, snapshot_ns: int | None = None) -> CVaRSnapshot:
        """Produce the current bounded historical CVaR snapshot.

        Sampling rules:
          - one observation per unique snapshot timestamp
          - duplicate timestamps replace the latest observation baseline
          - return_pct = (nav_t / nav_t-1 - 1) * 100
          - zero or invalid NAV raises fail-closed
        """
        ts = snapshot_ns if snapshot_ns is not None else time.time_ns()
        nav = self._effective_nav()
        self._record_cvar_observation(snapshot_ns=ts, nav_usd=nav)
        return self._cvar_engine.snapshot(timestamp_ns=ts)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _effective_nav(self) -> float:
        """Compute effective NAV: initial + realized + unrealized PnL."""
        unrealized = sum(p.unrealized_pnl() for p in self._positions.values())
        return self._nav_usd + self._daily_realized_pnl + unrealized

    def _record_cvar_observation(self, snapshot_ns: int, nav_usd: float) -> None:
        if snapshot_ns <= 0:
            raise ValueError(f"snapshot_ns must be > 0; got {snapshot_ns}")
        if nav_usd <= 0.0:
            raise ValueError(f"effective NAV must be positive for CVaR sampling; got {nav_usd}")

        if self._last_cvar_snapshot_ns is None:
            self._last_cvar_snapshot_ns = snapshot_ns
            self._last_cvar_nav_usd = nav_usd
            return

        if snapshot_ns < self._last_cvar_snapshot_ns:
            raise ValueError(
                "snapshot_ns must be monotonically non-decreasing for CVaR sampling; "
                f"got {snapshot_ns} after {self._last_cvar_snapshot_ns}"
            )

        if snapshot_ns == self._last_cvar_snapshot_ns:
            if self._prev_cvar_nav_usd is not None:
                self._cvar_engine.observe(
                    ReturnObservation(
                        timestamp_ns=snapshot_ns,
                        return_pct=self._compute_return_pct(self._prev_cvar_nav_usd, nav_usd),
                        nav_usd=nav_usd,
                    )
                )
            self._last_cvar_nav_usd = nav_usd
            return

        previous_nav = self._last_cvar_nav_usd
        if previous_nav is None or previous_nav <= 0.0:
            raise ValueError(f"previous NAV must be positive for CVaR sampling; got {previous_nav}")

        self._cvar_engine.observe(
            ReturnObservation(
                timestamp_ns=snapshot_ns,
                return_pct=self._compute_return_pct(previous_nav, nav_usd),
                nav_usd=nav_usd,
            )
        )
        self._prev_cvar_nav_usd = previous_nav
        self._last_cvar_snapshot_ns = snapshot_ns
        self._last_cvar_nav_usd = nav_usd

    @staticmethod
    def _compute_return_pct(previous_nav_usd: float, current_nav_usd: float) -> float:
        if previous_nav_usd <= 0.0:
            raise ValueError(f"previous_nav_usd must be positive for CVaR sampling; got {previous_nav_usd}")
        if current_nav_usd <= 0.0:
            raise ValueError(f"current_nav_usd must be positive for CVaR sampling; got {current_nav_usd}")
        return (current_nav_usd / previous_nav_usd - 1.0) * 100.0

    # -----------------------------------------------------------------------
    # Persistence — Phase 6E
    # -----------------------------------------------------------------------

    def to_persistence_dict(self, snapshot_ns: int) -> dict:
        """Serialize internal tracker state to a persistence-safe dict.

        The returned dict is suitable for PortfolioStateStore.save().
        CVaR engine history is NOT persisted — it will restart empty on
        restore (conservative: no stale CVaR history carried across restarts).

        Args:
            snapshot_ns: wall-clock timestamp for this snapshot (ns).

        Returns:
            dict conforming to portfolio store schema v1.
        """
        positions_data = []
        for pos in self._positions.values():
            positions_data.append(
                {
                    "symbol": pos.symbol,
                    "exchange": pos.exchange,
                    "side": str(pos.side),
                    "quantity": pos.quantity,
                    "avg_entry_price": pos.avg_entry_price,
                    "mark_price": pos.mark_price,
                    "leverage": pos.leverage,
                    "realized_pnl": pos.realized_pnl,
                    "liquidation_price": pos.liquidation_price,
                }
            )
        return {
            "schema_version": "1",
            "snapshot_ns": snapshot_ns,
            "nav_usd": self._nav_usd,
            "daily_realized_pnl": self._daily_realized_pnl,
            "positions": positions_data,
        }

    @classmethod
    def restore_from_dict(
        cls,
        d: dict,
        cvar_config: CVaRConfig | None = None,
    ) -> PositionTracker:
        """Restore a PositionTracker from a persistence dict.

        This is the inverse of to_persistence_dict().
        Validation is fail-closed: any missing or invalid field raises
        PortfolioRestoreError (imported lazily to avoid circular imports).

        Args:
            d:           dict produced by to_persistence_dict() and validated
                         by PortfolioStateStore.load().
            cvar_config: optional CVaR config; CVaR engine starts empty
                         (no historical data carried across restarts).

        Returns:
            Fully-initialized PositionTracker with restored position state.

        Raises:
            PortfolioRestoreError: if the dict is malformed or invalid.
        """
        from crypto_core.portfolio.store import PortfolioRestoreError

        # Top-level fields already validated by PortfolioStateStore._validate_snapshot
        try:
            nav_usd = float(d["nav_usd"])
            daily_realized_pnl = float(d["daily_realized_pnl"])
            positions_raw = d["positions"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PortfolioRestoreError(f"Cannot read portfolio snapshot fields: {exc}") from exc

        tracker = cls(initial_nav_usd=nav_usd, cvar_config=cvar_config)
        tracker._daily_realized_pnl = daily_realized_pnl

        from crypto_core.portfolio.models import PositionSide

        for idx, pos_d in enumerate(positions_raw):
            try:
                symbol = str(pos_d["symbol"])
                exchange = str(pos_d["exchange"])
                side = PositionSide(str(pos_d["side"]))
                quantity = float(pos_d["quantity"])
                avg_entry_price = float(pos_d["avg_entry_price"])
                mark_price = float(pos_d["mark_price"])
                leverage = float(pos_d["leverage"])
                realized_pnl = float(pos_d["realized_pnl"])
                liquidation_price = pos_d.get("liquidation_price")
                if liquidation_price is not None:
                    liquidation_price = float(liquidation_price)
            except (KeyError, TypeError, ValueError) as exc:
                raise PortfolioRestoreError(f"Cannot read position[{idx}] from snapshot: {exc}") from exc

            if quantity < 0.0:
                raise PortfolioRestoreError(f"Position[{idx}] quantity must be >= 0; got {quantity}")
            if leverage < 1.0 or leverage > _MAX_LEVERAGE:
                raise PortfolioRestoreError(
                    f"Position[{idx}] leverage must be in [1.0, {_MAX_LEVERAGE}]; got {leverage}"
                )

            pos = _MutablePosition(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                avg_entry_price=avg_entry_price,
                mark_price=mark_price,
                leverage=leverage,
                realized_pnl=realized_pnl,
                liquidation_price=liquidation_price,
            )
            tracker._positions[(symbol, exchange)] = pos

        return tracker

    @staticmethod
    def _validate_fill(fill: SyntheticFill) -> None:
        """Validate fill fields. Raises FillValidationError on failure."""
        errors: list[str] = []

        if not fill.symbol:
            errors.append("symbol must be non-empty")
        if not fill.exchange:
            errors.append("exchange must be non-empty")
        if fill.quantity <= _MIN_QUANTITY:
            errors.append(f"quantity must be > {_MIN_QUANTITY}; got {fill.quantity}")
        if fill.fill_price < _MIN_PRICE:
            errors.append(f"fill_price must be >= {_MIN_PRICE}; got {fill.fill_price}")
        if fill.leverage < 1.0 or fill.leverage > _MAX_LEVERAGE:
            errors.append(f"leverage must be in [1.0, {_MAX_LEVERAGE}]; got {fill.leverage}")
        if fill.intent not in (OrderIntent.BUY, OrderIntent.SELL):
            errors.append(f"intent must be BUY or SELL; got {fill.intent!r}")
        if not fill.order_id:
            errors.append("order_id must be non-empty")

        if errors:
            raise FillValidationError("; ".join(errors))
