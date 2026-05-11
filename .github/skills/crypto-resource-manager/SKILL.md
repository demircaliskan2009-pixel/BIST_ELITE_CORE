---
name: crypto-resource-manager
description: 'Resource management layer enforcing execution time limits, retry budgets, CPU/memory awareness, and runaway loop termination. Prevents resource exhaustion in autonomous operation.'
argument-hint: 'Describe the resource concern: execution budget, memory limit, retry exhaustion, or runaway process detection.'
user-invocable: true
---

# Resource Manager

Every computation has a budget. Every budget is enforced. No runaway processes.

## Design Principles

- Every task has explicit resource limits (time, retries, memory).
- Limits are enforced at the infrastructure level — components cannot override.
- Resource exhaustion triggers graceful degradation, not crashes.
- All resource usage is monitored and logged.

## Resource Budgets

### Execution Time Budgets

| Operation | Max Duration | On Exceed |
|-----------|-------------|-----------|
| Data pipeline tick | 500ms | WARN + skip tick |
| Edge signal computation | 1000ms | ABORT + log |
| Risk check | 200ms | ABORT + default to BLOCKED |
| Order submission | 2000ms | TIMEOUT + cancel |
| Order fill wait | 30000ms | CANCEL order |
| SHS computation | 100ms | WARN + use last value |
| Feature computation | 5000ms | ABORT + use cached |
| PBO computation | 300000ms (5min) | ABORT + mark experiment FAILED |
| Walk-forward window | 600000ms (10min) | ABORT + mark window FAILED |
| Portfolio simulation | 1800000ms (30min) | ABORT + partial results |

### Retry Budgets

| Operation | Max Retries | Backoff | On Exhaustion |
|-----------|-------------|---------|---------------|
| WebSocket reconnect | 10 | Exponential (1s-60s) | HALT data pipeline |
| Order submission | 3 | Linear (500ms) | Cancel + log |
| State store write | 5 | Exponential (100ms-5s) | HALT system |
| Message bus publish | 3 | Linear (200ms) | Dead-letter |
| Exchange API call | 3 | Exponential (1s-30s) | Mark exchange DEGRADED |
| CI pipeline check | 5 | Fixed (30s) | Report as BLOCKED |

### Memory Budgets

| Component | Max Memory | On Exceed |
|-----------|-----------|-----------|
| Order book (per symbol) | 100MB | Prune oldest levels |
| Trade buffer (per symbol) | 50MB | Flush to disk |
| Feature cache | 500MB | Evict LRU features |
| State store in-memory | 200MB | Force snapshot + compact |
| Replay engine | 1GB | Abort replay |
| Total system | 4GB | SYSTEM_STATE → CRISIS |

## Resource Monitor

```python
class ResourceManager:
    def __init__(self, state_store, event_bus): ...

    def create_budget(self, task_id: str, limits: ResourceLimits) -> Budget: ...
    def check_budget(self, budget: Budget) -> BudgetStatus: ...
    def enforce(self, budget: Budget) -> None: ...
    def get_system_resources(self) -> SystemResources: ...
    def kill_runaway(self, task_id: str, reason: str) -> bool: ...
```

### Budget Status

```json
{
  "task_id": "edge_computation_BTCUSDT",
  "status": "ACTIVE",
  "time_used_ms": 450,
  "time_limit_ms": 1000,
  "retries_used": 0,
  "retries_limit": 3,
  "memory_used_bytes": 15000000,
  "memory_limit_bytes": 100000000,
  "started_ms": 1700000000000
}
```

## Runaway Detection

### Detection Rules

| Condition | Classification | Action |
|-----------|---------------|--------|
| Task exceeds 2× time budget | RUNAWAY | Kill task, emit `RESOURCE_LIMIT_HIT` |
| Retry loop with identical failures | STUCK | Kill after 3 identical failures |
| Memory growing >10% per second | LEAK | Kill task, trigger GC |
| CPU >95% for >30s | OVERLOAD | Reduce concurrent tasks to 1 |
| Disk write >100MB/s sustained | DISK_FLOOD | Throttle logging, warn |
| Event queue growing unbounded | CASCADE | Backpressure + DEGRADED state |

### Kill Protocol

1. Send cancellation signal to task
2. Wait 5s for graceful shutdown
3. Force-kill if still running
4. Log kill event with full context
5. Emit `RESOURCE_LIMIT_HIT` event
6. Record in knowledge memory if recurring

## System Health Metrics

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU usage | <70% | 70-90% | >90% |
| Memory usage | <60% | 60-85% | >85% |
| Disk usage | <70% | 70-90% | >90% |
| Event queue depth | <1000 | 1000-5000 | >5000 |
| Active tasks | <20 | 20-50 | >50 |
| Failed tasks/hour | <5 | 5-20 | >20 |

Metrics feed into SHS computation (§1.29).

## Concurrency Limits

| Category | Max Concurrent |
|----------|---------------|
| Data pipeline ticks | 1 per symbol |
| Edge computations | 1 per edge |
| Risk checks | 1 per signal |
| Order submissions | 3 total |
| Experiment backtests | 2 total |
| Portfolio simulations | 1 total |
| Replay executions | 1 total |

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-event-orchestrator` | Enforces handler budgets |
| `crypto-scheduler` | Enforces task execution limits |
| `crypto-state-store` | Reports resource metrics to system state |
| `crypto-message-bus` | Monitors queue health |
| SHS engine (§1.29) | Resource metrics feed SHS computation |

## Audit Trail

```json
{
  "timestamp_ms": 1700000000000,
  "event": "BUDGET_EXCEEDED",
  "task_id": "edge_computation_BTCUSDT",
  "limit_type": "TIME",
  "limit_value_ms": 1000,
  "actual_value_ms": 2150,
  "action": "KILLED",
  "system_impact": "Edge signal skipped for this tick"
}
```

Storage: `logs/resources/resources_YYYY-MM-DD.jsonl`
