"""Runtime metrics and performance snapshot — Phase 8B.

Provides operator-facing operational and trading performance metrics
derived from the managed paper-live service runtime.

Design rules:
  - All metric models are frozen dataclasses (thread-safe snapshots).
  - Clear separation: operational metrics vs. trading/performance metrics.
  - Only use data already available from service/session/portfolio status.
  - Never fabricate unavailable metrics — use None.
  - Deterministic: same inputs → same outputs.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Operational metrics (service/queue/watchdog layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationalMetrics:
    """Operational health metrics for the managed paper-live service.

    Derived from: ServiceStatus, QueueSnapshot, WatchdogStatus.

    Fields:
      service_mode:          current ServiceMode value string.
      uptime_seconds:        wall-clock seconds since service started; 0.0 if not started.
      consumer_alive:        True if consumer thread is running.
      queue_current_depth:   current queue depth.
      queue_max_size:        configured queue capacity.
      queue_pressure:        current QueuePressure value string.
      queue_total_enqueued:  total events successfully enqueued.
      queue_total_dropped:   total events dropped due to overflow.
      queue_total_processed: total events consumed from the queue.
      queue_utilization_pct: queue depth / max_size × 100 (%).
      stall_detected:        True if watchdog detected a consumer stall.
      seconds_since_last_event: seconds since last event; 0.0 if no events.
      seconds_since_last_cycle: seconds since last cycle; 0.0 if no cycles.
      total_service_restarts: total service restart count.
      symbol_count:          number of registered symbols.
      symbols_connected:     number of symbols with feed_connected=True.
      symbols_ready:         number of symbols with feed_ready=True.
      symbols_blocked:       number of symbols currently blocked.
      recovery_in_progress:  True if any feed is not in READY state.
      last_error:            most recent service-level error; None if clean.
    """

    service_mode: str
    uptime_seconds: float
    consumer_alive: bool
    queue_current_depth: int
    queue_max_size: int
    queue_pressure: str
    queue_total_enqueued: int
    queue_total_dropped: int
    queue_total_processed: int
    queue_utilization_pct: float
    stall_detected: bool
    seconds_since_last_event: float
    seconds_since_last_cycle: float
    total_service_restarts: int
    symbol_count: int
    symbols_connected: int
    symbols_ready: int
    symbols_blocked: int
    recovery_in_progress: bool
    last_error: str | None


# ---------------------------------------------------------------------------
# Trading / performance metrics (session/portfolio layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradingMetrics:
    """Trading and portfolio performance metrics for the paper-live session.

    Derived from: PaperSessionStatus, PortfolioSnapshot (via session status).

    Fields:
      session_id:            session identifier.
      session_mode:          current SessionMode value string.
      total_cycles:          total pipeline cycles processed.
      approved_cycles:       cycles where pipeline approved a trade.
      blocked_cycles:        cycles rejected (session not running, etc.).
      failed_cycles:         cycles that raised an internal exception.
      approval_rate_pct:     approved / total × 100; None if total=0.
      total_fills:           total fill events applied.
      open_positions_count:  number of currently open positions.
      nav_usd:               current NAV in USD; None if unavailable.
      realized_pnl_usd:     daily realized PnL in USD; None if unavailable.
      unrealized_pnl_usd:   total unrealized PnL in USD; None if unavailable.
      gross_exposure_pct:    gross exposure as % of NAV; None if unavailable.
      net_exposure_pct:      net exposure as % of NAV; None if unavailable.
      concentration_max_pct: largest single position as % of NAV; None if unavailable.
      margin_used_pct:       margin usage %; None if unavailable.
      recovery_status:       recovery status string from session.
      unresolved_orders:     orders from recovery that could not be reconciled.
      trading_blocked:       True if session is not in RUNNING mode.
      block_reasons:         tuple of current block reasons.
      last_error:            most recent session-level error; None if clean.
    """

    session_id: str
    session_mode: str
    total_cycles: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    approval_rate_pct: float | None
    total_fills: int
    open_positions_count: int
    nav_usd: float | None
    realized_pnl_usd: float | None
    unrealized_pnl_usd: float | None
    gross_exposure_pct: float | None
    net_exposure_pct: float | None
    concentration_max_pct: float | None
    margin_used_pct: float | None
    recovery_status: str
    unresolved_orders: int
    trading_blocked: bool
    block_reasons: tuple[str, ...] = field(default_factory=tuple)
    last_error: str | None = None


# ---------------------------------------------------------------------------
# Combined performance snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceSnapshot:
    """Combined operator-facing performance snapshot.

    Joins operational and trading metrics into a single point-in-time snapshot.
    """

    timestamp_ns: int
    operational: OperationalMetrics
    trading: TradingMetrics


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def build_operational_metrics(
    *,
    service_status: object,
    uptime_seconds: float = 0.0,
) -> OperationalMetrics:
    """Build OperationalMetrics from a ServiceStatus snapshot.

    Args:
        service_status: ServiceStatus instance from PaperLiveService.status().
        uptime_seconds: wall-clock seconds since service started.

    Returns:
        Frozen OperationalMetrics snapshot.
    """
    from crypto_core.service.models import ServiceStatus

    ss: ServiceStatus = service_status  # type: ignore[assignment]

    queue = ss.queue
    wd = ss.watchdog
    utilization = (queue.current_depth / queue.max_size * 100.0) if queue.max_size > 0 else 0.0

    symbols_connected = sum(1 for sh in ss.symbol_health if sh.feed_connected)
    symbols_ready = sum(1 for sh in ss.symbol_health if sh.feed_ready)
    symbols_blocked = sum(1 for sh in ss.symbol_health if sh.blocked)
    recovery = any(not sh.feed_ready for sh in ss.symbol_health) if ss.symbol_health else False

    return OperationalMetrics(
        service_mode=ss.service_mode,
        uptime_seconds=uptime_seconds,
        consumer_alive=wd.consumer_alive,
        queue_current_depth=queue.current_depth,
        queue_max_size=queue.max_size,
        queue_pressure=queue.pressure.value,
        queue_total_enqueued=queue.total_enqueued,
        queue_total_dropped=queue.total_dropped,
        queue_total_processed=queue.total_processed,
        queue_utilization_pct=round(utilization, 2),
        stall_detected=wd.stall_detected,
        seconds_since_last_event=wd.seconds_since_event,
        seconds_since_last_cycle=wd.seconds_since_cycle,
        total_service_restarts=ss.total_service_restarts,
        symbol_count=ss.symbol_count,
        symbols_connected=symbols_connected,
        symbols_ready=symbols_ready,
        symbols_blocked=symbols_blocked,
        recovery_in_progress=recovery,
        last_error=ss.last_error,
    )


def build_trading_metrics(
    *,
    service_status: object,
    portfolio_snapshot: object | None = None,
) -> TradingMetrics:
    """Build TradingMetrics from a ServiceStatus snapshot.

    Args:
        service_status: ServiceStatus instance from PaperLiveService.status().
        portfolio_snapshot: optional PortfolioSnapshot for detailed PnL data.

    Returns:
        Frozen TradingMetrics snapshot.
    """
    from crypto_core.service.models import ServiceStatus

    ss: ServiceStatus = service_status  # type: ignore[assignment]
    rs = ss.runtime_status

    if rs is not None:
        sess = rs.session_status
        session_id = sess.session_id
        session_mode = sess.mode
        total_cycles = sess.total_cycles
        approved_cycles = sess.approved_cycles
        blocked_cycles = sess.blocked_cycles
        failed_cycles = sess.failed_cycles
        total_fills = sess.total_fills
        open_positions_count = sess.open_positions_count
        nav_usd = sess.nav_usd
        gross_exposure_pct = sess.gross_exposure_pct
        net_exposure_pct = sess.net_exposure_pct
        recovery_status = sess.recovery_status
        unresolved_orders = sess.unresolved_order_count
        trading_blocked = sess.trading_blocked
        block_reasons = sess.block_reasons
        last_error = sess.last_error
    else:
        session_id = "unknown"
        session_mode = "unknown"
        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        total_fills = 0
        open_positions_count = 0
        nav_usd = None
        gross_exposure_pct = None
        net_exposure_pct = None
        recovery_status = "unknown"
        unresolved_orders = 0
        trading_blocked = True
        block_reasons = ("no_runtime_status",)
        last_error = None

    approval_rate: float | None = None
    if total_cycles > 0:
        approval_rate = round(approved_cycles / total_cycles * 100.0, 2)

    # Extract detailed PnL from portfolio snapshot if available.
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    concentration_max: float | None = None
    margin_used: float | None = None

    if portfolio_snapshot is not None:
        from crypto_core.portfolio.models import PortfolioSnapshot

        ps: PortfolioSnapshot = portfolio_snapshot  # type: ignore[assignment]
        realized_pnl = ps.daily_realized_pnl_usd
        unrealized_pnl = ps.total_unrealized_pnl_usd
        concentration_max = ps.concentration_max_pct
        margin_used = ps.margin_used_pct

    return TradingMetrics(
        session_id=session_id,
        session_mode=session_mode,
        total_cycles=total_cycles,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        approval_rate_pct=approval_rate,
        total_fills=total_fills,
        open_positions_count=open_positions_count,
        nav_usd=nav_usd,
        realized_pnl_usd=realized_pnl,
        unrealized_pnl_usd=unrealized_pnl,
        gross_exposure_pct=gross_exposure_pct,
        net_exposure_pct=net_exposure_pct,
        concentration_max_pct=concentration_max,
        margin_used_pct=margin_used,
        recovery_status=recovery_status,
        unresolved_orders=unresolved_orders,
        trading_blocked=trading_blocked,
        block_reasons=block_reasons,
        last_error=last_error,
    )
