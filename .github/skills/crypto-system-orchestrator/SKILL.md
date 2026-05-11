---
name: crypto-system-orchestrator
description: 'Coordinate the crypto pipeline across crypto-data-pipeline, crypto-edge-engine, and crypto-risk-execution using contract enforcement, strict stage order, and fail-closed transitions per PRDV4 §2.'
argument-hint: 'Describe the current pipeline stage, available upstream outputs, target outcome, and evidence of completed stages.'
user-invocable: true
---

# Crypto System Orchestrator

Central coordination for the crypto trading pipeline per PRDV4 §2.

## Contract

Contract reference: `_shared/references/contract-schema.md`.
Every stage output must comply before the pipeline can transition.

## Managed Skills

### Core Pipeline
1. `crypto-data-pipeline` — Stage 1: data admission gate
2. `crypto-edge-engine` — Stage 2: signal generation gate
3. `crypto-risk-execution` — Stage 3: risk and execution gate
4. `crypto-test-fixtures` — Test infrastructure (fixtures, mocks, replay)

### Research Pipeline
5. `crypto-edge-discovery` — Alpha hypothesis generation and nursery
6. `crypto-walk-forward-shadow` — Walk-forward validation and shadow trading
7. `crypto-feature-store` — Feature versioning and data lineage
8. `crypto-experiment-tracker` — Experiment lifecycle and comparison
9. `crypto-portfolio-simulator` — Multi-edge portfolio simulation
10. `crypto-failure-replay` — Failure reproduction and regression tests
11. `crypto-knowledge-memory` — Persistent knowledge base

### Infrastructure Pipeline
12. `crypto-event-orchestrator` — Event-driven orchestration and routing
13. `crypto-scheduler` — Time-based task scheduling
14. `crypto-state-store` — Global atomic state management
15. `crypto-message-bus` — Pub/sub inter-component messaging
16. `crypto-resource-manager` — Resource budgets and enforcement
17. `crypto-sandbox` — Isolated execution environments
18. `crypto-deployment-pipeline` — Multi-stage deployment and rollback

## Strict Execution Order

```
data (SAFE) → edge (READY) → risk (ALLOWED | BLOCKED)
```

No stage may be skipped. No downstream stage runs on invalid upstream output.

## Transition Rules

| Transition | Valid When |
|-----------|-----------|
| data → edge | Data stage output is `SAFE` and contract-compliant |
| edge → risk | Edge stage output is `READY` and contract-compliant |
| risk → execution | Risk stage output is `ALLOWED` |

If any required field is missing → STOP.
If any status mismatch → STOP.
If scope fields conflict across stages → STOP.

## System State Integration (§1.29)

The system state engine (SHS) overrides pipeline behavior:

| State | Pipeline Effect |
|-------|----------------|
| NORMAL (SS-0) | Full pipeline operation |
| DEGRADED (SS-1) | Skip T0/T1 edges, reduce allocation 30% |
| DEFENSIVE (SS-2) | No new entries — pipeline blocked at risk stage |
| CRISIS (SS-3) | Pipeline suspended — exit-only mode |
| HALT (SS-4) | Pipeline disabled — manual restart required |

## Multi-Market Architecture (§2)

### Shared Components
- Risk engine core, portfolio state, audit logger, system state engine, backtest framework, execution FSM

### Market-Specific Components
- Data providers, execution adapters, regime dimensions, tick/lot rules, session rules, edge definitions

### Cross-Market Rules
- Monitor 60-day correlation between market equity curves
- If correlation > 0.6 → reduce smaller market allocation by 20%
- Total NAV tracks across all markets

## Standard Procedure

1. **Identify current stage** — where is the pipeline right now?
2. **Validate upstream** — are all prior stages complete with valid contracts?
3. **Check transition** — is the next step reachable without skipping?
4. **Route to skill** — delegate to the matching stage skill
5. **Prevent redundancy** — don't repeat a valid completed stage
6. **Stop on failure** — name the blocking stage and reason

## Pipeline State Tracking

Track: `{current_stage, data_status, edge_status, risk_status, system_state, blocking_reason}`

## Decision Rules

- Missing upstream → BLOCKED
- Invalid contract → BLOCKED with field mismatch
- System state ≥ DEFENSIVE → no new pipeline runs
- Scope change after stage completion → revalidate from earliest affected stage
- Uncertainty → STOP and request minimum evidence

## Output

1. Current stage
2. Pipeline validity statement
3. Transition decision
4. Contract status per completed stage
5. Blocking stage and reason (if any)
6. Telemetry summary (per-stage metrics snapshot)
7. Single best next action

## Telemetry Integration

Every pipeline run MUST:

1. Emit telemetry envelope per stage (see contract schema Telemetry Contract).
2. Check drift metrics (PSI, KS) on features feeding active edges.
3. Aggregate stage latencies for pipeline-level monitoring.
4. Log alerts when any threshold is breached.

Pipeline telemetry flow:
```
data_telemetry → edge_telemetry → risk_telemetry → execution_telemetry
```

If any stage telemetry shows alert → log but do NOT block pipeline (telemetry is observability, not a gate).
Exception: If drift PSI > 0.50 → flag edge for review (potential regime change).

## Research Pipeline Flow

In addition to the core trading pipeline, the orchestrator coordinates the research loop:

```
discovery → backtest → PBO → walk-forward → shadow → live
```

### Research Stage Routing

| Stage | Skill | Trigger |
|-------|-------|---------|
| Hypothesis | `crypto-edge-discovery` | Manual or scheduled scan |
| Feature prep | `crypto-feature-store` | New hypothesis accepted |
| Experiment | `crypto-experiment-tracker` | Backtest started |
| Walk-forward | `crypto-walk-forward-shadow` | PBO passed |
| Shadow | `crypto-walk-forward-shadow` | Walk-forward passed |
| Portfolio sim | `crypto-portfolio-simulator` | Before live allocation |
| Failure analysis | `crypto-failure-replay` | Any anomaly or loss |
| Knowledge update | `crypto-knowledge-memory` | Any rejection or failure |

Research stages are NOT gated by the core pipeline contract (they operate offline).
But promoted edges MUST enter the core pipeline through the edge engine gate.

## Event-Driven Execution Model

The orchestrator is now fully event-driven. All pipeline transitions are triggered by events, not polling.

### Core Event Flow

```
DATA_STREAM_UPDATE → data_validator → OHLCV_BAR_CLOSE
    → feature_computer → EDGE_SIGNAL_GENERATED
    → risk_checker → RISK_CHECK_PASSED
    → execution_engine → ORDER_SUBMITTED → ORDER_FILLED
```

### Infrastructure Layer

```
crypto-message-bus      ← transport for all events
crypto-event-orchestrator ← routes events to handlers
crypto-state-store      ← single source of truth for all state
crypto-scheduler        ← emits time-based SCHEDULER_TICK events
crypto-resource-manager ← enforces budgets on all handlers
crypto-sandbox          ← isolates experiments and patches
crypto-deployment-pipeline ← manages dev→staging→prod flow
```

All components interact only through the message bus. No direct calls.
