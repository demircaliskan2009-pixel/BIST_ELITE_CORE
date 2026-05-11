---
name: crypto-deployment-pipeline
description: 'Multi-stage deployment pipeline (dev → staging → production) with promotion rules, rollback system, health checks, and canary validation. Zero-downtime for 24/7 crypto operation.'
argument-hint: 'Describe the deployment target: stage to promote to, change description, rollback plan, and health check expectations.'
user-invocable: true
---

# Deployment Pipeline

Every change follows the pipeline. No shortcuts. No manual deploys.

## Design Principles

- Three stages: DEV → STAGING → PRODUCTION.
- Promotion requires explicit gate checks at each stage.
- Rollback is always available and tested.
- Health checks run continuously after deployment.
- Zero downtime — 24/7 crypto markets never close.

## Deployment Stages

### DEV

| Property | Value |
|----------|-------|
| Environment | Local + sandbox |
| Data | Historical snapshots only |
| Exchange | Mocked (test fixtures) |
| State store | Ephemeral (reset per run) |
| Validation | Unit tests + lint + type check |
| Auto-promote | If all checks pass |

### STAGING

| Property | Value |
|----------|-------|
| Environment | Shadow mode with live data |
| Data | Live WebSocket feeds (read-only) |
| Exchange | Paper trading (no real orders) |
| State store | Persistent (staging copy) |
| Validation | Integration tests + shadow metrics + regression replays |
| Auto-promote | NO — requires manual approval |

### PRODUCTION

| Property | Value |
|----------|-------|
| Environment | Live trading |
| Data | Live WebSocket feeds |
| Exchange | Real order submission |
| State store | Production store |
| Validation | Continuous health checks |
| Rollback | Automatic on health check failure |

## Promotion Gates

### DEV → STAGING

| Gate | Condition |
|------|-----------|
| Lint | Ruff clean, no warnings |
| Types | Pylance clean, no errors |
| Tests | All pass, no SKIP/XFAIL without justification |
| Sandbox | Patch sandbox PROMOTE_READY |
| Diff | Atomic, <200 lines, single-purpose |
| CI | Green on feature branch |

### STAGING → PRODUCTION

| Gate | Condition |
|------|-----------|
| Shadow period | ≥24h in staging |
| Shadow metrics | Signal accuracy ≥80%, tracking error <15% |
| Regression | All replay tests pass |
| Performance | No latency regression >10% |
| Risk | No risk metric degradation |
| Rollback tested | Rollback procedure verified in staging |
| Approval | Manual review + sign-off |

## Deployment Record

```json
{
  "deployment_id": "DEP-20260415-001",
  "stage": "STAGING",
  "previous_stage": "DEV",
  "timestamp_ms": 1700000000000,
  "change_description": "Add liquidation-aware slippage model",
  "commit_hash": "abc123",
  "branch": "feat/liquidation-slippage",
  "gate_results": {
    "lint": "PASS",
    "types": "PASS",
    "tests": "PASS",
    "sandbox": "PASS",
    "diff_size": 87,
    "ci": "PASS"
  },
  "status": "DEPLOYED",
  "health_check_status": "HEALTHY",
  "rollback_version": "DEP-20260414-003"
}
```

## Health Checks

### Continuous Checks (every 30s after deploy)

| Check | Healthy | Degraded | Critical |
|-------|---------|----------|----------|
| Data pipeline latency | <500ms | 500-2000ms | >2000ms |
| Edge computation time | <1000ms | 1000-3000ms | >3000ms |
| Order fill rate | >90% | 70-90% | <70% |
| System state | NORMAL | DEGRADED | DEFENSIVE+ |
| Error rate | <1/min | 1-10/min | >10/min |
| Memory usage | <70% | 70-85% | >85% |

### Health Check Actions

| Status | Action |
|--------|--------|
| HEALTHY for 1h | Deployment confirmed |
| DEGRADED for >5m | Alert + prepare rollback |
| CRITICAL for >1m | AUTO-ROLLBACK |
| Any crash | IMMEDIATE ROLLBACK |

## Rollback System

### Rollback Procedure

1. Load previous deployment record (`rollback_version`)
2. Verify rollback target is available
3. Switch to rollback version (blue-green swap)
4. Run health checks on rolled-back version
5. If healthy → rollback complete
6. If unhealthy → HALT system, manual intervention required

### Rollback Guarantees

- Rollback is always to a known-good state (previously deployed + healthy).
- Rollback preserves state store data — no state loss.
- Rollback completes in <30s.
- Maximum rollback chain: 3 versions back.

### Rollback Triggers

| Trigger | Automatic | Manual |
|---------|-----------|--------|
| Health check CRITICAL | YES | — |
| Error rate spike | YES | — |
| System crash | YES | — |
| Performance regression | NO | Review first |
| Bug discovered | NO | After investigation |

## Blue-Green Deployment

For zero-downtime deploys:

```
Active (v1) ──→ [deploy v2 to inactive]
                        ↓
              [health check v2]
                        ↓
              [swap active to v2]
                        ↓
              [monitor 1h]
                        ↓
              [confirm or rollback to v1]
```

- Both versions share the same state store.
- Only one version processes events at any time.
- Swap is atomic (single event router reconfiguration).

## Canary Deployment (Edge Promotion)

For new edges entering production:

```
New edge → 10% allocation → monitor 7d → 25% → monitor 7d → 50% → monitor 14d → 100%
```

Canary abort conditions:
- Sharpe drops below 0.5 at any stage
- Max drawdown exceeds 2× historical
- Any NT condition triggered by the edge

## Deployment History

Storage: `data/deployments/`

```
data/
  deployments/
    DEP-20260415-001.json
    DEP-20260415-002.json
    history.jsonl           # Searchable index
    rollback_log.jsonl      # All rollback events
```

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-sandbox` | DEV stage uses sandbox for validation |
| `crypto-event-orchestrator` | Emits `DEPLOYMENT_PROMOTED` events |
| `crypto-state-store` | Shared across blue-green instances |
| `crypto-resource-manager` | Monitors deployment health metrics |
| `crypto-walk-forward-shadow` | STAGING uses shadow trading mode |
| `repo-hygiene-ci-guardian` | CI gates feed promotion decisions |

## Anti-Patterns

- Direct deploys to production → BLOCKED
- Deploys without rollback plan → BLOCKED
- Deploys during CRISIS or HALT state → BLOCKED
- Deploys with failing tests → BLOCKED
- Manual state mutations during deploy → VIOLATION
- Skipping staging for "small changes" → BLOCKED (all changes go through pipeline)
