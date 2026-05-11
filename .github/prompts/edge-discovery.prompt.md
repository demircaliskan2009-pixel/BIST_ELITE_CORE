---
mode: "deterministic"
description: "Edge discovery workflow for generating, evaluating, and promoting new alpha hypotheses per PRDV4 §1.1-§1.13"
---

# EDGE DISCOVERY LOOP

Use when generating new alpha hypotheses, evaluating candidate edges, or managing the discovery nursery.

## Required Input

- Target edge family (A-G per §1.1)
- Market regime context (4D cell from §1.17)
- Knowledge base query results (known failures for this family)

## Pre-Discovery Gate

Before generating ANY hypothesis:

1. Query `crypto-knowledge-memory` for failed edges in this family
2. Check nursery capacity (max 20 candidates per family)
3. Verify feature store has required raw data
4. Confirm current regime is identified

If any gate fails → STOP with reason.

## Discovery Stages

### Stage 1: Hypothesis Generation

Source: microstructure observation, cross-exchange divergence, funding anomaly, or regime transition.

Requirements:
- Explicit microstructure justification (INV-EDGE-001)
- Invalidation conditions defined upfront (INV-EDGE-002)
- Not in known-failure list (or retest period expired)

Output: Hypothesis document with family, mechanism, expected edge, invalidation.

### Stage 2: Feature Engineering

- Define features from `crypto-feature-store` registry
- If new features needed → register with full lineage
- Version-lock feature set for this experiment
- Verify no future-data leakage in feature pipeline

### Stage 3: Signal Construction

- Deterministic code only (no ML, no LLM)
- Next-bar execution enforced
- Clear entry/exit logic with exact thresholds
- Cost-aware from the start (minimum 5 bps slippage)

### Stage 4: Cost-Aware Backtest

- Almgren-Chriss impact model (§1.14)
- Fill ratio model per ADV bucket
- Time-varying spread from historical L2
- Track experiment in `crypto-experiment-tracker`

Required metrics:
- Sharpe ratio (net of all costs)
- Max drawdown
- Win rate
- Profit factor
- Average trade duration

### Stage 5: Overfitting Rejection

Per §1.20:
- PBO/CSCV: S=16, all C(16,8)=12,870 splits
- PBO < 0.40 → PASS
- PBO 0.40-0.60 → CAUTION
- PBO > 0.60 → REJECTED
- Parameter sensitivity: ±20% perturbation must retain profitability
- DSR check, Monte Carlo permutation (10K shuffles)

### Stage 6: Promotion Decision

| Result | Action |
|--------|--------|
| PBO < 0.40 + Sharpe > 1.0 + positive expectancy | → Enter walk-forward (crypto-walk-forward-shadow) |
| PBO 0.40-0.60 + Sharpe > 1.5 | → Enter walk-forward with CAUTION flag |
| PBO > 0.60 | → REJECTED — store in knowledge memory |
| Sharpe < 1.0 | → REJECTED — insufficient edge |
| Backtest unprofitable after costs | → REJECTED — no edge after costs |

## Integration

- `crypto-knowledge-memory` — query before, store after rejection
- `crypto-feature-store` — feature versioning and lineage
- `crypto-experiment-tracker` — full experiment record
- `crypto-walk-forward-shadow` — next stage for promoted candidates
- `crypto-edge-engine` — final destination for validated edges

## Output

- Hypothesis document
- Backtest results with exact metrics
- PBO result
- Decision: PROMOTED / CAUTION / REJECTED
- If REJECTED: failure reason + knowledge memory entry ID
- If PROMOTED: walk-forward configuration

## Guardrails

- No ML signals. Deterministic code only.
- No hypothesis without microstructure justification.
- No backtest without cost model.
- No promotion without PBO check.
- Failed hypotheses stored permanently in knowledge base.
