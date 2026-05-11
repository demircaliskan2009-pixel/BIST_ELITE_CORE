---
name: crypto-scheduler
description: 'Deterministic scheduler engine for time-based triggers: funding cycles, drift checks, walk-forward windows, portfolio rebalance, and maintenance tasks. All schedules logged and auditable.'
argument-hint: 'Describe the scheduled task, interval, priority, and dependencies on system state.'
user-invocable: true
---

# Scheduler Engine

All time-based system behavior is driven by the scheduler. No ad-hoc timers.

## Design Principles

- All scheduled tasks are registered, deterministic, and logged.
- Scheduler emits `SCHEDULER_TICK` events — it never executes tasks directly.
- Task execution is mediated by the event router.
- Missed ticks are detected and handled (catch-up or skip based on policy).
- Scheduler respects system state — tasks are suppressed in HALT state.

## Schedule Registry

### Crypto-Specific Schedules

| Task ID | Interval | Description | Priority |
|---------|----------|-------------|----------|
| `SCHED-FUNDING-CHECK` | 8h (00:00, 08:00, 16:00 UTC) | Funding rate settlement cycle check | HIGH |
| `SCHED-FUNDING-PRE` | 7h 45m (15min before settlement) | Pre-funding position review | HIGH |
| `SCHED-DRIFT-CHECK` | 1h | PSI/KS drift detection on active features | NORMAL |
| `SCHED-SHS-COMPUTE` | 10s | System Health Score recomputation | CRITICAL |
| `SCHED-BOOK-HEALTH` | 30s | Order book health check (staleness, CRC32 rate) | HIGH |
| `SCHED-EHS-UPDATE` | 5m | Edge Health Score rolling update | NORMAL |

### Research Schedules

| Task ID | Interval | Description | Priority |
|---------|----------|-------------|----------|
| `SCHED-WALKFORWARD-EVAL` | 24h (02:00 UTC) | Walk-forward window evaluation | LOW |
| `SCHED-SHADOW-EVAL` | 24h (03:00 UTC) | Shadow trading daily metrics | LOW |
| `SCHED-EXPERIMENT-REVIEW` | 24h (04:00 UTC) | Active experiment status review | LOW |
| `SCHED-KNOWLEDGE-RETEST` | 7d (Sunday 05:00 UTC) | Retest eligible failed edges | BACKGROUND |

### Portfolio Schedules

| Task ID | Interval | Description | Priority |
|---------|----------|-------------|----------|
| `SCHED-PORTFOLIO-REBALANCE` | 4h | Correlation matrix update + allocation review | NORMAL |
| `SCHED-RISK-SNAPSHOT` | 1h | Portfolio risk metrics snapshot | HIGH |
| `SCHED-MARGIN-CHECK` | 5m | Margin utilization and DTL check | HIGH |
| `SCHED-PNL-RECONCILE` | 1h | P&L reconciliation vs exchange | NORMAL |

### Infrastructure Schedules

| Task ID | Interval | Description | Priority |
|---------|----------|-------------|----------|
| `SCHED-TELEMETRY-FLUSH` | 1m | Flush telemetry buffer to disk | BACKGROUND |
| `SCHED-STATE-SNAPSHOT` | 15m | Global state store snapshot | NORMAL |
| `SCHED-LOG-ROTATE` | 24h (00:30 UTC) | Rotate and compress log files | BACKGROUND |
| `SCHED-RESOURCE-CHECK` | 30s | CPU/memory/disk usage check | NORMAL |
| `SCHED-CLEANUP` | 24h (01:00 UTC) | Clean temporary files and expired caches | BACKGROUND |

## Schedule Definition Schema

```json
{
  "task_id": "SCHED-FUNDING-CHECK",
  "interval_seconds": 28800,
  "anchor_utc": "00:00:00",
  "priority": "HIGH",
  "system_state_filter": ["NORMAL", "DEGRADED"],
  "missed_tick_policy": "CATCH_UP_ONCE",
  "max_execution_ms": 5000,
  "enabled": true,
  "last_run_ms": 1700000000000,
  "next_run_ms": 1700028800000,
  "run_count": 0,
  "failure_count": 0
}
```

## Missed Tick Policies

| Policy | Behavior |
|--------|----------|
| `CATCH_UP_ONCE` | Execute once immediately, then resume normal schedule |
| `SKIP` | Skip missed tick, wait for next scheduled time |
| `CATCH_UP_ALL` | Execute for each missed tick sequentially |

Default: `CATCH_UP_ONCE`

## System State Interaction

| System State | Scheduler Behavior |
|-------------|-------------------|
| NORMAL | All tasks execute normally |
| DEGRADED | Skip LOW and BACKGROUND tasks |
| DEFENSIVE | Only CRITICAL and HIGH tasks execute |
| CRISIS | Only CRITICAL tasks execute |
| HALT | Scheduler suspended — only `SCHED-SHS-COMPUTE` runs |

## Scheduler Engine Interface

```python
class SchedulerEngine:
    def __init__(self, state_store, event_bus): ...

    def register(self, schedule: ScheduleDefinition) -> str: ...
    def unregister(self, task_id: str) -> bool: ...
    def tick(self, now_ms: int) -> list[Event]: ...
    def list_due(self, now_ms: int) -> list[ScheduleDefinition]: ...
    def get_status(self) -> dict: ...
```

### `tick()` Behavior

1. Read current time
2. Check all registered schedules for due tasks
3. Filter by current system state
4. Emit `SCHEDULER_TICK` event per due task (via message bus)
5. Update `last_run_ms` and `next_run_ms`
6. Log tick summary

## Audit Trail

Every scheduler tick produces:

```json
{
  "timestamp_ms": 1700000000000,
  "task_id": "SCHED-FUNDING-CHECK",
  "status": "EMITTED",
  "system_state": "NORMAL",
  "latency_ms": 2,
  "next_run_ms": 1700028800000
}
```

Storage: `logs/scheduler/scheduler_YYYY-MM-DD.jsonl`

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-event-orchestrator` | Receives `SCHEDULER_TICK` events |
| `crypto-state-store` | Reads system state for filtering |
| `crypto-message-bus` | Publishes tick events |
| `crypto-resource-manager` | Enforces `max_execution_ms` per task |

## Anti-Patterns

- `time.sleep()` or `asyncio.sleep()` anywhere in the system → use scheduler
- Hard-coded intervals in code → register in scheduler
- Tasks that bypass system state filtering → VIOLATION
- Unlogged schedule execution → VIOLATION
