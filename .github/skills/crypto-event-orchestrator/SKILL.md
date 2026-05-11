---
name: crypto-event-orchestrator
description: 'Event-driven orchestration layer replacing passive pipeline coordination. All system actions are triggered by typed events with deterministic routing, priority ordering, and audit trails.'
argument-hint: 'Describe the event type, source component, expected handler, and any state preconditions.'
user-invocable: true
---

# Event-Driven Orchestration

All system behavior is event-triggered. No polling. No passive waiting.

## Design Principles

- Every system action starts from a typed event.
- Events are immutable, timestamped, and logged.
- Event routing is deterministic — same event → same handler chain.
- Events never mutate state directly — handlers read state, compute, then write atomically via state store.

## Event Taxonomy

### Data Events

| Event | Source | Trigger |
|-------|--------|---------|
| `DATA_STREAM_UPDATE` | WebSocket manager | New market data received |
| `DATA_STREAM_STALE` | Health monitor | Stream >10s without update |
| `DATA_STREAM_RECONNECT` | WebSocket manager | Reconnection completed |
| `BOOK_INTEGRITY_FAIL` | CRC32 validator | Order book CRC32 mismatch |
| `TRADE_SEQUENCE_GAP` | Trade processor | Sequence gap detected |
| `OHLCV_BAR_CLOSE` | Bar builder | New OHLCV bar completed |

### Edge Events

| Event | Source | Trigger |
|-------|--------|---------|
| `EDGE_SIGNAL_GENERATED` | Edge engine | New signal from active edge |
| `EDGE_EHS_DEGRADED` | EHS monitor | Edge health below threshold |
| `EDGE_CROWDING_DETECTED` | Crowding detector | Crowding flag raised |
| `EDGE_ACTIVATED` | Activation matrix | Edge entered ACTIVE state |
| `EDGE_DEACTIVATED` | Activation matrix | Edge exited ACTIVE state |

### Risk Events

| Event | Source | Trigger |
|-------|--------|---------|
| `RISK_CHECK_PASSED` | Risk engine | All NT conditions clear |
| `RISK_CHECK_BLOCKED` | Risk engine | NT condition triggered |
| `KILL_SWITCH_ESCALATED` | Kill-switch | KS level increased |
| `KILL_SWITCH_DEESCALATED` | Kill-switch | KS level decreased (hysteresis) |
| `SYSTEM_STATE_CHANGED` | SHS engine | System state transition |
| `MARGIN_THRESHOLD_BREACH` | Margin monitor | DTL or utilization alert |

### Execution Events

| Event | Source | Trigger |
|-------|--------|---------|
| `ORDER_SUBMITTED` | Execution engine | Order sent to exchange |
| `ORDER_FILLED` | Execution engine | Order fill confirmed |
| `ORDER_REJECTED` | Execution engine | Exchange rejected order |
| `ORDER_TIMEOUT` | Execution engine | Order exceeded time limit |
| `POSITION_OPENED` | Position tracker | New position established |
| `POSITION_CLOSED` | Position tracker | Position fully closed |

### Infrastructure Events

| Event | Source | Trigger |
|-------|--------|---------|
| `SCHEDULER_TICK` | Scheduler engine | Scheduled task due |
| `DRIFT_DETECTED` | Drift monitor | PSI/KS threshold breached |
| `CI_RESULT_RECEIVED` | CI pipeline | CI workflow completed |
| `DEPLOYMENT_PROMOTED` | Deployment pipeline | Stage promotion completed |
| `RESOURCE_LIMIT_HIT` | Resource manager | CPU/memory/time budget exceeded |
| `SANDBOX_COMPLETED` | Sandbox layer | Isolated execution finished |

## Event Envelope

```json
{
  "event_id": "EVT-20260415-000001",
  "event_type": "EDGE_SIGNAL_GENERATED",
  "timestamp_ms": 1700000000000,
  "source": "edge_engine",
  "priority": 1,
  "payload": {},
  "correlation_id": "CORR-20260415-001",
  "system_state_at_emit": "NORMAL",
  "version": 1
}
```

## Priority Levels

| Priority | Category | Examples |
|----------|----------|---------|
| 0 (CRITICAL) | Safety | Kill-switch, margin breach, system halt |
| 1 (HIGH) | Trading | Signals, orders, fills, risk checks |
| 2 (NORMAL) | Operational | Data updates, bar closes, scheduler ticks |
| 3 (LOW) | Research | Drift detection, experiment updates |
| 4 (BACKGROUND) | Infrastructure | CI results, deployments, cleanup |

Priority 0 events preempt all other processing.

## Event Router

```python
class EventRouter:
    def __init__(self, state_store, message_bus): ...

    def route(self, event: Event) -> list[Handler]:
        """Deterministic routing: event_type → ordered handler chain."""
        ...

    def dispatch(self, event: Event) -> list[HandlerResult]:
        """Execute handler chain in priority order. Fail-closed on any error."""
        ...
```

### Routing Rules

| Event Type | Handler Chain |
|------------|--------------|
| `DATA_STREAM_UPDATE` | data_validator → book_updater → bar_builder |
| `OHLCV_BAR_CLOSE` | feature_computer → edge_evaluator → signal_router |
| `EDGE_SIGNAL_GENERATED` | risk_checker → position_sizer → order_creator |
| `RISK_CHECK_PASSED` | execution_engine |
| `RISK_CHECK_BLOCKED` | nt_logger → state_recorder |
| `KILL_SWITCH_ESCALATED` | position_reducer → notification_logger |
| `SYSTEM_STATE_CHANGED` | pipeline_reconfigurer → allocation_adjuster |
| `DRIFT_DETECTED` | edge_reviewer → knowledge_updater |
| `SCHEDULER_TICK` | scheduled_task_executor |

### Fail-Closed Routing

- Unknown event type → LOG + DROP (never process untyped events)
- Handler exception → ABORT chain, LOG, escalate to risk
- State store unavailable → HALT all processing
- Message bus unavailable → BUFFER locally (max 1000 events), then HALT

## Event Lifecycle

```
CREATED → ROUTED → DISPATCHED → HANDLED → COMPLETED | FAILED
```

Every event records its full lifecycle in the audit log.

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-message-bus` | Event transport layer |
| `crypto-state-store` | State reads/writes from handlers |
| `crypto-scheduler` | Emits `SCHEDULER_TICK` events |
| `crypto-resource-manager` | Enforces handler execution budgets |
| `crypto-system-orchestrator` | Pipeline stage transitions via events |

## Anti-Patterns

- Polling for state changes → use events
- Direct component calls → use event dispatch
- Untyped events → REJECTED
- Events without correlation IDs → REJECTED
- Handlers that mutate state without state store → VIOLATION
