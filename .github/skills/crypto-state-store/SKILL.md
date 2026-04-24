---
name: crypto-state-store
description: 'Global atomic state store — single source of truth for system state, portfolio state, edge state, and execution state. All reads/writes are versioned, atomic, and auditable.'
argument-hint: 'Describe the state domain to read/write, expected version, and reason for state mutation.'
user-invocable: true
---

# Global State Store

One store. One truth. All state changes are atomic, versioned, and auditable.

## Design Principles

- Single source of truth for ALL system state.
- Every state mutation is atomic (read-compute-write with optimistic locking).
- Every state version is stored — full audit trail, no overwrites.
- State is read-only for AI agents (INV-005).
- State reads never block — snapshot isolation.

## State Domains

### 1. System State (`system`)

```json
{
  "domain": "system",
  "version": 1042,
  "timestamp_ms": 1700000000000,
  "data": {
    "shs_value": 0.82,
    "shs_state": "NORMAL",
    "shs_signals": {
      "data_quality": 0.95,
      "execution_quality": 0.88,
      "market_stress": 0.15,
      "book_health": 0.92,
      "latency_score": 0.90,
      "pnl_trend": 0.75,
      "drawdown_distance": 0.85,
      "correlation_stability": 0.80,
      "fill_quality": 0.91,
      "drift_score": 0.88
    },
    "kill_switch_level": 0,
    "active_nt_conditions": [],
    "uptime_ms": 86400000
  }
}
```

### 2. Portfolio State (`portfolio`)

```json
{
  "domain": "portfolio",
  "version": 587,
  "timestamp_ms": 1700000000000,
  "data": {
    "nav_usd": 100000.00,
    "total_exposure_usd": 45000.00,
    "margin_used_usd": 15000.00,
    "margin_available_usd": 85000.00,
    "margin_utilization_pct": 15.0,
    "unrealized_pnl_usd": 1250.00,
    "realized_pnl_today_usd": 340.00,
    "positions": [
      {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "size": 0.023,
        "entry_price": 84250.50,
        "mark_price": 84800.00,
        "unrealized_pnl": 12.64,
        "dtl_pct": 28.5,
        "edge_id": "EDGE-A-007"
      }
    ],
    "correlation_matrix_version": 42,
    "cvar99_pct": 2.3,
    "max_drawdown_pct": 4.1
  }
}
```

### 3. Edge State (`edge`)

```json
{
  "domain": "edge",
  "version": 203,
  "timestamp_ms": 1700000000000,
  "data": {
    "active_edges": [
      {
        "edge_id": "EDGE-A-007",
        "family": "A",
        "ehs": 0.78,
        "activation_state": "ACTIVE",
        "allocation_pct": 12.5,
        "pbo": 0.32,
        "last_signal_ms": 1699999800000,
        "crowding_flag": false,
        "regime_cell": [1, 0, 1, 0]
      }
    ],
    "nursery_count": 5,
    "total_active": 3,
    "meta_layer_version": 18
  }
}
```

### 4. Execution State (`execution`)

```json
{
  "domain": "execution",
  "version": 891,
  "timestamp_ms": 1700000000000,
  "data": {
    "pending_orders": [],
    "recent_fills": [
      {
        "order_id": "ORD-20260415-001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": 0.023,
        "fill_price": 84252.30,
        "slippage_bps": 2.14,
        "latency_ms": 340,
        "timestamp_ms": 1699999500000
      }
    ],
    "daily_order_count": 12,
    "daily_fill_rate_pct": 94.2,
    "exchange_status": {
      "binance": "CONNECTED",
      "bybit": "CONNECTED"
    }
  }
}
```

## State Operations

### Read (Snapshot)

```python
class StateStore:
    def read(self, domain: str) -> StateSnapshot: ...
    def read_at_version(self, domain: str, version: int) -> StateSnapshot: ...
    def read_field(self, domain: str, path: str) -> Any: ...
```

- Reads return immutable snapshots
- Never block on reads
- Include version number in every snapshot

### Write (Atomic)

```python
    def write(self, domain: str, mutation: Mutation, expected_version: int) -> WriteResult: ...
```

- Optimistic concurrency: `expected_version` must match current version
- If version mismatch → `CONFLICT` (caller must re-read and retry)
- Every write increments version
- Every write is logged to audit trail

### History

```python
    def history(self, domain: str, from_version: int, to_version: int) -> list[StateSnapshot]: ...
    def diff(self, domain: str, v1: int, v2: int) -> StateDiff: ...
```

## Versioning Rules

- Versions are monotonically increasing integers per domain.
- Version 0 = initial state (system boot).
- Every mutation increments version by exactly 1.
- No version gaps allowed.
- Version history is immutable — no compaction, no pruning (within retention window).

## Retention Policy

| Domain | Retention | Granularity |
|--------|-----------|-------------|
| `system` | 30 days | Every version |
| `portfolio` | 90 days | Every version |
| `edge` | 90 days | Every version |
| `execution` | 30 days | Every version |

After retention: archive to `data/state_archive/` (compressed JSONL).

## Consistency Guarantees

- **Atomicity**: Each write mutates exactly one domain atomically.
- **Isolation**: Reads see a consistent snapshot (no partial writes).
- **Durability**: Every write is fsynced before acknowledgment.
- **Ordering**: Writes within a domain are strictly ordered by version.

Cross-domain consistency: achieved via correlation IDs in events.
No cross-domain transactions — use saga pattern via event orchestrator.

## Storage Layout

```
data/
  state/
    system/
      current.json          # Latest version
      history/
        v1000-v1099.jsonl   # Versioned history batches
    portfolio/
      current.json
      history/
        v500-v599.jsonl
    edge/
      current.json
      history/
    execution/
      current.json
      history/
  state_archive/
    system_2026-03.jsonl.gz
```

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-event-orchestrator` | Handlers read/write state via store |
| `crypto-scheduler` | Reads system state for task filtering |
| `crypto-message-bus` | State change events published after write |
| `crypto-risk-execution` | Reads portfolio + execution state |
| `crypto-edge-engine` | Reads/writes edge state |

## Anti-Patterns

- Direct state mutation without state store → VIOLATION
- Reading state without version awareness → VIOLATION
- Cross-domain atomic writes → NOT SUPPORTED (use events)
- State reads in hot loops without caching → use snapshot
- Unversioned state changes → VIOLATION
