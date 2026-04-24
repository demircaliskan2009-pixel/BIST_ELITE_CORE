---
name: crypto-sandbox
description: 'Isolated execution sandbox for patches, experiments, and simulations. Full state isolation prevents untested changes from affecting production. Rollback-safe by design.'
argument-hint: 'Describe what to sandbox: a code patch, experiment run, simulation, or configuration change. Specify isolation requirements.'
user-invocable: true
---

# Sandbox Layer

Nothing untested touches production. Every change runs in isolation first.

## Design Principles

- Patches, experiments, and simulations run in isolated sandboxes.
- Sandboxes have their own state store snapshot — no production state mutation.
- Sandbox results are compared against production before promotion.
- Failed sandboxes are discarded with full audit trail.
- Sandboxes have strict resource budgets (time, memory, disk).

## Sandbox Types

### 1. Patch Sandbox

For testing code changes before production deployment.

```json
{
  "sandbox_id": "SBX-PATCH-20260415-001",
  "type": "PATCH",
  "created_ms": 1700000000000,
  "state_snapshot_version": {
    "system": 1042,
    "portfolio": 587,
    "edge": 203,
    "execution": 891
  },
  "code_diff": "git diff hash",
  "test_plan": ["unit", "integration", "replay"],
  "resource_budget": {
    "max_duration_ms": 300000,
    "max_memory_bytes": 1073741824
  },
  "status": "RUNNING"
}
```

**Execution flow:**
1. Snapshot current state store versions
2. Apply code change in isolation
3. Run lint (ruff check + format)
4. Run targeted tests
5. Run regression replays
6. Compare outputs vs production
7. If all pass → PROMOTE_READY
8. If any fail → DISCARD with evidence

### 2. Experiment Sandbox

For running edge discovery experiments without risk.

```json
{
  "sandbox_id": "SBX-EXP-20260415-001",
  "type": "EXPERIMENT",
  "experiment_id": "EXP-2026-04-15-001",
  "data_snapshot_id": "SNAP-20260415",
  "feature_versions": {"FEAT-A-001-v3": "locked"},
  "resource_budget": {
    "max_duration_ms": 1800000,
    "max_memory_bytes": 2147483648
  },
  "status": "RUNNING"
}
```

**Execution flow:**
1. Lock feature versions from feature store
2. Load data snapshot (immutable)
3. Run backtest with frozen parameters
4. Run PBO/CSCV check
5. Record results to experiment tracker
6. No state store mutations — results written to experiment log only

### 3. Simulation Sandbox

For portfolio simulation and stress testing.

```json
{
  "sandbox_id": "SBX-SIM-20260415-001",
  "type": "SIMULATION",
  "simulation_mode": "STRESS",
  "portfolio_snapshot_version": 587,
  "scenarios": ["high_vol", "low_liquidity", "flash_crash"],
  "resource_budget": {
    "max_duration_ms": 3600000,
    "max_memory_bytes": 4294967296
  },
  "status": "RUNNING"
}
```

**Execution flow:**
1. Snapshot portfolio state
2. Configure simulation parameters
3. Run multi-scenario simulation
4. Collect results per scenario
5. Compare against thresholds
6. Report to portfolio simulator skill

## Sandbox Lifecycle

```
CREATED → PROVISIONED → RUNNING → COMPLETED | FAILED | TIMEOUT
                                       ↓
                              PROMOTE_READY | DISCARDED
```

| State | Meaning |
|-------|---------|
| CREATED | Sandbox definition registered |
| PROVISIONED | State snapshots loaded, resources allocated |
| RUNNING | Execution in progress |
| COMPLETED | Execution finished normally |
| FAILED | Execution error or test failure |
| TIMEOUT | Resource budget exceeded |
| PROMOTE_READY | All checks passed, eligible for production |
| DISCARDED | Failed or rejected, resources freed |

## Isolation Guarantees

| Resource | Isolation Method |
|----------|-----------------|
| State | Copy-on-write from production snapshot |
| Files | Temporary directory (`tmp/sandbox/<id>/`) |
| Database | In-memory shadow copy |
| Network | No external calls (exchange APIs mocked) |
| Events | Sandbox-local message bus (no production bus) |
| Logs | Separate log file (`logs/sandbox/<id>.jsonl`) |

## Promotion Rules

### Patch Promotion

| Check | Required |
|-------|----------|
| Lint clean | YES |
| All tests pass | YES |
| Regression replays match | YES |
| No new warnings | YES |
| Performance not degraded >5% | YES |
| Resource usage within budget | YES |

### Experiment Promotion

| Check | Required |
|-------|----------|
| PBO < 0.60 | YES |
| Walk-forward pass | YES |
| No feature leakage | YES |
| Cost-aware profitability | YES |

### Simulation Promotion

Not applicable — simulations produce reports, not deployable code.

## Resource Limits (Hard Caps)

| Sandbox Type | Max Duration | Max Memory | Max Disk |
|-------------|-------------|-----------|----------|
| PATCH | 5 min | 1 GB | 500 MB |
| EXPERIMENT | 30 min | 2 GB | 2 GB |
| SIMULATION | 60 min | 4 GB | 5 GB |

On exceed → TIMEOUT, resource freed, sandbox discarded.

## Cleanup

- Completed/Discarded sandboxes: cleaned after 24h
- PROMOTE_READY sandboxes: retained until promotion decision (max 7 days)
- Sandbox logs: retained for 30 days

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-state-store` | Provides state snapshots for isolation |
| `crypto-resource-manager` | Enforces sandbox resource budgets |
| `crypto-event-orchestrator` | Emits `SANDBOX_COMPLETED` events |
| `crypto-experiment-tracker` | Receives experiment sandbox results |
| `crypto-deployment-pipeline` | Receives patch sandbox promotion decisions |
| `crypto-failure-replay` | Runs replays inside sandbox |

## Anti-Patterns

- Running experiments against live state → use sandbox
- Testing patches in production → use sandbox
- Sandboxes without resource budgets → REJECTED
- Sandboxes that call exchange APIs → VIOLATION
- Promoting without all checks passing → BLOCKED
