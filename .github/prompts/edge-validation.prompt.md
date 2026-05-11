---
mode: "deterministic"
description: "Edge validation loop for crypto perpetual futures edges per PRDV4 §1.13 and §1.20"
---

# EDGE VALIDATION LOOP

Use when validating, evolving, or testing a crypto trading edge.

## Required Input

- Edge family (A-G per §1.1)
- Hypothesis with microstructure justification
- Invalidation conditions
- Crowding detection mechanism

## Validation Stages (§1.13)

### Stage 1: Hypothesis → Backtest

- Cost-aware backtest with Almgren-Chriss impact model (§1.14)
- Minimum 5 bps slippage
- Next-bar execution (no same-bar)
- Fill ratio model per ADV bucket
- Time-varying spread from historical L2

### Stage 2: Walk-Forward

- Minimum 3 OOS windows, each ≥ 3 months
- Sharpe retention ≥ 50%
- Hit rate retention ≥ -10pp
- Positive expectancy in ≥ 2/3 windows

### Stage 3: Stress Testing

- High-vol: returns ×1.5, slippage ×2.0
- Low-liquidity: depth ×0.2, slippage ×3.0
- Flash crash: 10% gap, 5-min recovery, massive liquidation
- Must survive all three with drawdown < 2× normal

### Stage 4: Paper Trading

- 30-day parallel execution
- Fill quality tracking
- Slippage comparison (estimated vs actual)

### Stage 5: Live Scaled Entry

- 10% → 25% → 50% → 100% allocation
- Each step requires metrics to hold for minimum period

## Overfitting Check (§1.20)

- PBO/CSCV: S=16, all C(16,8)=12,870 splits
- PBO < 0.40 for APPROVED
- PBO 0.40-0.60: CAUTION (capped allocation)
- PBO > 0.60: REJECTED
- DSR, Monte Carlo permutation (10K shuffles)
- Parameter sensitivity: ±20% perturbation must retain profitability

## Decision

| Result | Action |
|--------|--------|
| All stages pass + PBO < 0.40 | APPROVED — enter meta edge layer (§1.7) |
| Stages 1-3 pass, PBO 0.40-0.60 | CAUTION — reduced allocation cap |
| Any stage fails | REJECTED — log reason, return to hypothesis |
| Walk-forward unstable | REJECTED — edge is likely overfit |

## Output

- Hypothesis tested
- Evidence per stage (exact metrics)
- PBO result
- Decision: APPROVED / CAUTION / REJECTED
- If REJECTED: next hypothesis (single deterministic item)

## Guardrails

- No ML signals. Deterministic code only.
- No future data leakage.
- No zero-slippage assumptions.
- All parameters declared in advance with bounds.
