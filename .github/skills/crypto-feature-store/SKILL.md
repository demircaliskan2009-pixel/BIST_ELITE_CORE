---
name: crypto-feature-store
description: 'Versioned datasets, feature lineage tracking, reproducibility guarantee, immutable snapshots. Central registry for all features feeding edge discovery and signal generation.'
argument-hint: 'Describe the feature task: registration, lookup, versioning, lineage query, or snapshot operation.'
user-invocable: true
---

# Feature Store + Data Versioning

Single source of truth for all features and datasets in the system.

## Design Principles

- Every feature has a unique ID and version.
- Every dataset has an immutable snapshot hash.
- Every computation is reproducible from snapshot + feature definition + code version.
- No mutable state. Append-only registry.

## Feature Registry

### Feature Definition Schema

```json
{
  "feature_id": "feat_ofi_imbalance_1m_v3",
  "name": "ofi_imbalance_1m",
  "version": 3,
  "family": "A",
  "formula": "OFI = Σ(bid_delta - ask_delta) over 1min window",
  "lookback_bars": 60,
  "alignment": "bar_close",
  "source_streams": ["binance:depth@100ms"],
  "normalization": "z-score rolling 480 bars",
  "dependencies": ["feat_bid_delta_raw_v1", "feat_ask_delta_raw_v1"],
  "created_at": "2026-04-01T00:00:00Z",
  "created_by": "edge-discovery-pipeline",
  "status": "ACTIVE | DEPRECATED | EXPERIMENTAL",
  "code_ref": "src/crypto_core/features/order_flow.py:compute_ofi_imbalance:L42"
}
```

### Feature Lifecycle

```
EXPERIMENTAL → VALIDATED → ACTIVE → DEPRECATED
```

- EXPERIMENTAL: Created by edge-discovery, not yet validated
- VALIDATED: Passed walk-forward + PBO checks
- ACTIVE: Used by at least one live edge
- DEPRECATED: Superseded by newer version, retained for reproducibility

### Registry Operations

| Operation | Description | Mutates Registry? |
|-----------|-------------|-------------------|
| `register` | Add new feature definition | Yes (append) |
| `lookup` | Find feature by ID or name | No |
| `list_by_family` | All features for edge family | No |
| `deprecate` | Mark as DEPRECATED (never delete) | Yes (status change) |
| `lineage` | Trace dependency chain to raw data | No |
| `compare_versions` | Diff between feature versions | No |

### Never Delete

Features are NEVER deleted from the registry. Deprecated features remain for:
- Historical reproducibility
- Audit trail
- Experiment comparison

## Dataset Versioning

### Snapshot Schema

```json
{
  "snapshot_id": "snap_20260401_binance_btcusdt_1m",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "start_ts": "2025-01-01T00:00:00Z",
  "end_ts": "2026-04-01T00:00:00Z",
  "row_count": 657000,
  "sha256": "a1b2c3d4...",
  "columns": ["timestamp", "open", "high", "low", "close", "volume", "trades"],
  "created_at": "2026-04-01T12:00:00Z",
  "immutable": true
}
```

### Immutability Rules

- Once a snapshot is created, its content NEVER changes.
- If data is corrected → create new snapshot with new ID and version.
- Old snapshot remains for reproducibility.
- Snapshot hash (SHA-256) is computed on creation and verified on every read.

### Storage Layout

```
data/
  snapshots/
    binance/
      BTCUSDT/
        snap_20260401_1m.parquet
        snap_20260401_1m.meta.json
    bybit/
      BTCUSDT/
        snap_20260401_1m.parquet
        snap_20260401_1m.meta.json
  features/
    registry.jsonl          # append-only feature registry
    computed/
      feat_ofi_imbalance_1m_v3/
        snap_20260401.parquet
        snap_20260401.meta.json
```

## Feature Lineage

### Lineage Graph

```
raw trade stream → trade aggregation → OHLCV 1m → OFI computation → z-score norm → signal
```

Every node in the lineage graph stores:
- Input snapshot IDs
- Code version (git commit hash)
- Feature definition version
- Output snapshot ID
- Computation timestamp

### Lineage Query

Given any feature value at any timestamp:
- Trace back to exact raw data snapshot
- Identify exact code version that computed it
- Reproduce the exact same value

### Reproducibility Guarantee

```
reproduce(feature_id, snapshot_id, code_commit) → identical output
```

If reproduction fails → SYSTEM ERROR → investigate immediately.

## Drift Detection Integration

Feature store provides feature distributions to drift detection:
- PSI (Population Stability Index) computed hourly
- KS (Kolmogorov-Smirnov) test computed hourly
- Drift alerts propagate to telemetry system
- Significant drift (PSI > 0.25) → flag affected edges for review

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-edge-discovery` | Register new features during discovery |
| `crypto-edge-engine` | Look up active features for signal computation |
| `crypto-experiment-tracker` | Reference feature versions in experiments |
| `crypto-data-pipeline` | Source raw data for feature computation |
| `crypto-knowledge-memory` | Record feature performance patterns |
| Contract schema | Drift metrics (PSI, KS) feed telemetry envelope |

## File Locations

| Component | Path |
|-----------|------|
| Feature registry | `data/features/registry.jsonl` |
| Computed features | `data/features/computed/` |
| Raw snapshots | `data/snapshots/` |
| Feature code | `src/crypto_core/features/` |
| Lineage tracker | `src/crypto_core/features/lineage.py` |

## Output

Feature definition + version + lineage chain + snapshot reference + drift status.
