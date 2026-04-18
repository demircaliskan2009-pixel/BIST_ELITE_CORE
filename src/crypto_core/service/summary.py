"""Service, session, and per-symbol run summaries — Phase 8B.

Explicit end-of-run and point-in-time summary builders for the
managed paper-live service.

Design rules:
  - All summaries are frozen dataclasses (deterministic, serializable-friendly).
  - Use current runtime data only — never fabricate unavailable metrics.
  - Clear separation: service summary vs. session summary vs. per-symbol summary.
  - Summaries are composable: ServiceRunSummary contains SessionSummary + SymbolSummary.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Per-symbol summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolSummary:
    """Per-symbol run summary.

    Fields:
      symbol:             symbol name (e.g. "BTCUSDT").
      exchange:           exchange name (e.g. "binance").
      feed_key:           DataIngestor feed key.
      feed_connected:     True if feed was connected at summary time.
      feed_ready:         True if feed was in READY state at summary time.
      blocked:            True if this symbol was blocked at summary time.
      block_reason:       reason string if blocked; None otherwise.
      last_event_time_ns: most recent event timestamp for this symbol.
    """

    symbol: str
    exchange: str
    feed_key: str
    feed_connected: bool
    feed_ready: bool
    blocked: bool
    block_reason: str | None
    last_event_time_ns: int


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSummary:
    """Session-level run summary.

    Fields:
      session_id:            session identifier.
      session_mode:          final SessionMode value string.
      start_time_ns:         session start wall-clock (ns); 0 if not started.
      end_time_ns:           summary creation wall-clock (ns).
      duration_seconds:      wall-clock seconds from start to summary.
      total_cycles:          total pipeline cycles processed.
      approved_cycles:       cycles where pipeline approved a trade.
      blocked_cycles:        cycles rejected.
      failed_cycles:         cycles that raised an internal exception.
      approval_rate_pct:     approved / total × 100; None if total=0.
      total_fills:           total fill events applied.
      open_positions_count:  open positions at summary time.
      nav_usd:               NAV at summary time; None if unavailable.
      realized_pnl_usd:     daily realized PnL; None if unavailable.
      unrealized_pnl_usd:   total unrealized PnL; None if unavailable.
      gross_exposure_pct:    gross exposure at summary time; None if unavailable.
      net_exposure_pct:      net exposure at summary time; None if unavailable.
      recovery_status:       recovery status string.
      trading_blocked:       True if session not RUNNING at summary time.
      last_error:            most recent session error; None if clean.
      block_reasons:         tuple of block reasons at summary time.
    """

    session_id: str
    session_mode: str
    start_time_ns: int
    end_time_ns: int
    duration_seconds: float
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
    recovery_status: str
    trading_blocked: bool
    last_error: str | None
    block_reasons: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Service run summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceRunSummary:
    """Top-level service run summary combining service, session, and symbol data.

    Fields:
      summary_time_ns:        wall-clock ns when this summary was produced.
      service_mode:           final ServiceMode value string.
      service_uptime_seconds: wall-clock seconds since service started.
      total_service_restarts: total restart count.
      queue_total_enqueued:   total events enqueued.
      queue_total_dropped:    total events dropped (overflow).
      queue_total_processed:  total events consumed.
      queue_max_observed_depth: max queue depth if tracked; 0 otherwise.
      queue_final_depth:      queue depth at summary time.
      queue_final_pressure:   final queue pressure zone string.
      consumer_alive:         True if consumer thread alive at summary time.
      stall_detected:         True if stall detected at summary time.
      trading_enabled:        True if trading was enabled at summary time.
      last_error:             most recent service error; None if clean.
      session:                SessionSummary snapshot.
      symbols:                per-symbol summaries.
    """

    summary_time_ns: int
    service_mode: str
    service_uptime_seconds: float
    total_service_restarts: int
    queue_total_enqueued: int
    queue_total_dropped: int
    queue_total_processed: int
    queue_max_observed_depth: int
    queue_final_depth: int
    queue_final_pressure: str
    consumer_alive: bool
    stall_detected: bool
    trading_enabled: bool
    last_error: str | None
    session: SessionSummary
    symbols: tuple[SymbolSummary, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def build_session_summary(
    *,
    service_status: object,
    portfolio_snapshot: object | None = None,
) -> SessionSummary:
    """Build a SessionSummary from a ServiceStatus snapshot.

    Args:
        service_status: ServiceStatus from PaperLiveService.status().
        portfolio_snapshot: optional PortfolioSnapshot for detailed PnL.

    Returns:
        Frozen SessionSummary.
    """
    from crypto_core.service.models import ServiceStatus

    ss: ServiceStatus = service_status  # type: ignore[assignment]
    rs = ss.runtime_status
    now_ns = time.time_ns()

    if rs is not None:
        sess = rs.session_status
        session_id = sess.session_id
        session_mode = sess.mode
        start_time_ns = sess.start_time_ns
        total_cycles = sess.total_cycles
        approved_cycles = sess.approved_cycles
        blocked_cycles = sess.blocked_cycles
        failed_cycles = sess.failed_cycles
        total_fills = sess.total_fills
        open_positions = sess.open_positions_count
        nav_usd = sess.nav_usd
        gross_exposure = sess.gross_exposure_pct
        net_exposure = sess.net_exposure_pct
        recovery_status = sess.recovery_status
        trading_blocked = sess.trading_blocked
        last_error = sess.last_error
        block_reasons = sess.block_reasons
    else:
        session_id = "unknown"
        session_mode = "unknown"
        start_time_ns = 0
        total_cycles = 0
        approved_cycles = 0
        blocked_cycles = 0
        failed_cycles = 0
        total_fills = 0
        open_positions = 0
        nav_usd = None
        gross_exposure = None
        net_exposure = None
        recovery_status = "unknown"
        trading_blocked = True
        last_error = None
        block_reasons = ()

    duration = (now_ns - start_time_ns) / 1e9 if start_time_ns > 0 else 0.0
    approval_rate: float | None = None
    if total_cycles > 0:
        approval_rate = round(approved_cycles / total_cycles * 100.0, 2)

    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    if portfolio_snapshot is not None:
        from crypto_core.portfolio.models import PortfolioSnapshot

        ps: PortfolioSnapshot = portfolio_snapshot  # type: ignore[assignment]
        realized_pnl = ps.daily_realized_pnl_usd
        unrealized_pnl = ps.total_unrealized_pnl_usd

    return SessionSummary(
        session_id=session_id,
        session_mode=session_mode,
        start_time_ns=start_time_ns,
        end_time_ns=now_ns,
        duration_seconds=round(duration, 3),
        total_cycles=total_cycles,
        approved_cycles=approved_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        approval_rate_pct=approval_rate,
        total_fills=total_fills,
        open_positions_count=open_positions,
        nav_usd=nav_usd,
        realized_pnl_usd=realized_pnl,
        unrealized_pnl_usd=unrealized_pnl,
        gross_exposure_pct=gross_exposure,
        net_exposure_pct=net_exposure,
        recovery_status=recovery_status,
        trading_blocked=trading_blocked,
        last_error=last_error,
        block_reasons=block_reasons,
    )


def build_symbol_summaries(
    *,
    service_status: object,
) -> tuple[SymbolSummary, ...]:
    """Build per-symbol summaries from a ServiceStatus snapshot.

    Returns:
        Tuple of frozen SymbolSummary instances.
    """
    from crypto_core.service.models import ServiceStatus

    ss: ServiceStatus = service_status  # type: ignore[assignment]

    return tuple(
        SymbolSummary(
            symbol=sh.symbol,
            exchange=sh.exchange,
            feed_key=sh.feed_key,
            feed_connected=sh.feed_connected,
            feed_ready=sh.feed_ready,
            blocked=sh.blocked,
            block_reason=sh.block_reason,
            last_event_time_ns=sh.last_event_time_ns,
        )
        for sh in ss.symbol_health
    )


def build_service_summary(
    *,
    service_status: object,
    uptime_seconds: float = 0.0,
    max_observed_queue_depth: int = 0,
    portfolio_snapshot: object | None = None,
) -> ServiceRunSummary:
    """Build a ServiceRunSummary from a ServiceStatus snapshot.

    Args:
        service_status: ServiceStatus from PaperLiveService.status().
        uptime_seconds: wall-clock seconds since service started.
        max_observed_queue_depth: maximum queue depth seen during the run.
        portfolio_snapshot: optional PortfolioSnapshot for detailed PnL.

    Returns:
        Frozen ServiceRunSummary.
    """
    from crypto_core.service.models import ServiceStatus

    ss: ServiceStatus = service_status  # type: ignore[assignment]

    session_summary = build_session_summary(
        service_status=service_status,
        portfolio_snapshot=portfolio_snapshot,
    )
    symbol_summaries = build_symbol_summaries(service_status=service_status)

    return ServiceRunSummary(
        summary_time_ns=time.time_ns(),
        service_mode=ss.service_mode,
        service_uptime_seconds=round(uptime_seconds, 3),
        total_service_restarts=ss.total_service_restarts,
        queue_total_enqueued=ss.queue.total_enqueued,
        queue_total_dropped=ss.queue.total_dropped,
        queue_total_processed=ss.queue.total_processed,
        queue_max_observed_depth=max_observed_queue_depth,
        queue_final_depth=ss.queue.current_depth,
        queue_final_pressure=ss.queue.pressure.value,
        consumer_alive=ss.watchdog.consumer_alive,
        stall_detected=ss.watchdog.stall_detected,
        trading_enabled=ss.trading_enabled,
        last_error=ss.last_error,
        session=session_summary,
        symbols=symbol_summaries,
    )
