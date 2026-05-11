---
name: crypto-portfolio-simulator
description: 'Multi-edge portfolio simulation: correlation-aware allocation, drawdown interaction modeling, realistic constraints (slippage, latency, liquidity, funding). Full portfolio-level backtest per PRDV4 §1.7 and §1.28.'
argument-hint: 'Describe the simulation: edge set, allocation method, constraints, time range, and target metrics.'
user-invocable: true
---

# Portfolio Simulation Engine

No edge runs in isolation. Portfolio-level simulation is mandatory.

## Design Principle

Individual edge backtests are NECESSARY but NOT SUFFICIENT.
Portfolio simulation captures:
- Edge interaction effects
- Correlation-driven drawdowns
- Capital allocation competition
- Margin consumption under concurrent positions
- Funding cost accumulation across positions

## Simulation Architecture

```
Edge A signals ─┐
Edge B signals ─┤→ Portfolio Allocator → Position Sizer → Execution Simulator → P&L
Edge C signals ─┤     (§1.7 meta)        (§1.28 Kelly)     (§7 impact model)
Edge D signals ─┘
```

## Multi-Edge Allocation (§1.7 Meta Layer)

Allocation formula:
```
alloc_e = (EHS_e × Sharpe_e) / Σ(EHS_i × Sharpe_i)
```

Constraints:
- Max 5 concurrent active edges
- Per-edge floor: 5% of portfolio allocation
- Per-edge cap: 40% of portfolio allocation
- Rebalance cycle: 24 hours

## Correlation-Aware Allocation

### Rolling Correlation Matrix

- Compute pairwise edge return correlations over 60-day rolling window
- Update daily before rebalance

### Correlation Adjustments

| Pairwise Correlation | Adjustment |
|---------------------|------------|
| < 0.3 | No adjustment |
| 0.3 - 0.6 | Reduce combined allocation by 15% |
| > 0.6 | Reduce smaller edge allocation by 30% |
| > 0.8 | FLAG: edges are likely redundant — review |

### Cross-Market Correlation (§2)

- Monitor 60-day correlation between market-level equity curves
- If cross-market correlation > 0.6 → reduce smaller market allocation by 20%
- Total NAV tracks across all markets

## Drawdown Interaction Modeling

### Concurrent Drawdown Detection

```python
def portfolio_drawdown(edge_equity_curves: dict[str, Series]) -> Series:
    """Combined portfolio equity curve accounting for capital sharing."""
    combined = sum(curves.values())  # weighted by allocation
    peak = combined.cummax()
    drawdown = (combined - peak) / peak
    return drawdown
```

### Drawdown Rules

| Portfolio Drawdown | Action |
|-------------------|--------|
| < 5% | NORMAL — continue |
| 5-10% | CAUTION — reduce weakest edge by 50% |
| 10-15% | DEFENSIVE — no new entries, tighten all stops 50% |
| > 15% | CRISIS — exit all, KS-3 trigger (§1.19) |

### Correlated Drawdown Amplification

If ≥ 3 edges are in drawdown simultaneously:
- Portfolio risk is AMPLIFIED (correlation effect)
- Reduce total allocation by 30% immediately
- Re-evaluate after recovery

## Realistic Execution Constraints

### Slippage Model

Per-order slippage from Almgren-Chriss (§1.14):
```
temporary_impact = η · σ · (v/ADV)^γ · e^(-λt)
permanent_impact = α · σ · (q/ADV)^δ
total_cost = spread/2 + temporary + permanent + commission + funding
```

### Latency Model

| Component | Simulated Latency |
|-----------|------------------|
| Signal computation | 50-200ms |
| Order submission | 10-50ms |
| Exchange ack | 20-100ms |
| Fill notification | 10-50ms |

Total simulated latency: 90-400ms per order.
During high-vol events: multiply by 2-5×.

### Liquidity Constraints

- Max order size: 1% of trailing 24h ADV
- If size > 1% ADV → split into iceberg children
- Max 10 children per parent order
- Fill probability decreases with size:

| Order Size (% ADV) | Fill Probability |
|--------------------|------------------|
| < 0.1% | 99% |
| 0.1-0.5% | 95% |
| 0.5-1.0% | 85% |
| > 1.0% | Split required |

### Funding Cost Model

- 8-hour settlement cycles
- Real historical funding rates from data pipeline
- Applied to all open positions at settlement
- Net funding P&L tracked separately

## Simulation Modes

| Mode | Description |
|------|-------------|
| BACKTEST | Historical data, all edges, full constraints |
| WALK_FORWARD | Rolling IS/OOS at portfolio level |
| STRESS | Amplified vol (1.5×), reduced liquidity (0.2×), flash crash |
| MONTE_CARLO | 10K path simulations with parameter perturbation |

## Output Schema

```json
{
  "simulation_id": "SIM-2026-04-001",
  "mode": "BACKTEST",
  "edges": ["EDGE-A-007", "EDGE-B-003", "EDGE-C-012"],
  "period": "2025-01-01 to 2026-03-31",
  "portfolio_metrics": {
    "total_return_pct": 42.3,
    "sharpe": 1.6,
    "max_drawdown_pct": -8.7,
    "calmar": 4.86,
    "win_rate": 0.53,
    "profit_factor": 1.45,
    "total_trades": 1847,
    "avg_holding_hours": 3.2,
    "total_slippage_bps": 6.8,
    "total_commission_bps": 3.5,
    "total_funding_bps": -1.2,
    "max_concurrent_positions": 4,
    "margin_utilization_peak_pct": 62
  },
  "correlation_matrix": {...},
  "drawdown_episodes": [...],
  "regime_breakdown": {...},
  "stress_results": {...}
}
```

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-edge-engine` | Edge signals and EHS for allocation |
| `crypto-risk-execution` | Risk limits, Kelly sizing, margin |
| `crypto-feature-store` | Feature data for signal computation |
| `crypto-experiment-tracker` | Log simulation as experiment |
| `crypto-data-pipeline` | Historical data for backtest |
| `crypto-test-fixtures` | Deterministic replay for regression |

## Output

Portfolio simulation report + correlation analysis + drawdown episodes + regime breakdown.
