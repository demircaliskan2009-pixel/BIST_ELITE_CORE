---
name: crypto-walk-forward-shadow
description: 'Rolling walk-forward validation, out-of-sample enforcement, shadow trading (paper with live data), and promotion rules. Ensures no edge reaches live without OOS proof per PRDV4 §1.13.'
argument-hint: 'Describe the edge to validate, available data range, walk-forward parameters, and current shadow status.'
user-invocable: true
---

# Walk-Forward + Shadow Trading System

No edge reaches live capital without passing this gate.

## Walk-Forward Validation

### Rolling Window Protocol

```
|--- IS Window ---|--- OOS Window ---|
|    Training     |    Validation     |
         ↓ slide forward ↓
         |--- IS ---|--- OOS ---|
```

Parameters (§1.13 Stage 2):
- Minimum 3 OOS windows
- Each OOS window ≥ 3 months (90 days of 24/7 crypto data)
- IS:OOS ratio = 3:1 (e.g., 9 months IS, 3 months OOS)
- Anchored expanding window variant also supported

### Retention Thresholds

| Metric | Threshold | Action on Failure |
|--------|-----------|-------------------|
| Sharpe retention | ≥ 50% of IS Sharpe | REJECT |
| Hit rate retention | ≥ IS hit rate - 10pp | REJECT |
| Positive expectancy | ≥ 2/3 OOS windows | REJECT if < 2/3 |
| Max drawdown | < 2× IS max drawdown | REJECT |
| Profit factor | > 1.0 in ≥ 2/3 windows | REJECT |

### Walk-Forward Report

```
{
  "edge_id": "EDGE-A-007",
  "windows": [
    {"oos_start": "2025-01-01", "oos_end": "2025-03-31", "sharpe": 1.2, "hit_rate": 0.53, "pnl": 4200},
    {"oos_start": "2025-04-01", "oos_end": "2025-06-30", "sharpe": 0.8, "hit_rate": 0.51, "pnl": 1800},
    {"oos_start": "2025-07-01", "oos_end": "2025-09-30", "sharpe": 1.1, "hit_rate": 0.52, "pnl": 3100}
  ],
  "sharpe_retention": 0.62,
  "hit_rate_retention": -0.04,
  "positive_windows": 3,
  "total_windows": 3,
  "verdict": "PASS"
}
```

## Out-of-Sample Enforcement

Hard rules:
- No parameter tuning on OOS data. EVER.
- OOS data is read-once, write-never.
- If OOS is peeked during development → entire experiment is CONTAMINATED → restart.
- OOS windows are defined BEFORE any IS optimization begins.
- Feature selection MUST be frozen before OOS evaluation.

Contamination detection:
- Track all data access timestamps.
- If OOS data accessed before IS optimization completes → flag CONTAMINATED.
- Contaminated experiments logged to knowledge memory and permanently rejected.

## Shadow Trading (Paper Trading with Live Data)

### Shadow Mode Protocol

Purpose: Validate edge behavior on live market conditions without capital risk.

```
LIVE DATA → edge signal → shadow order → shadow fill simulation → shadow P&L tracking
                                                                          ↕
                                                              comparison with live market
```

Configuration:
- Duration: minimum 30 days (§1.13 Stage 4)
- Data: real-time WebSocket feeds (same as production)
- Execution: simulated fills using actual L2 book state
- Slippage: estimated from real book depth at signal time
- Funding: real funding rates applied to shadow positions

### Shadow Metrics

| Metric | Target | Purpose |
|--------|--------|---------|
| Signal accuracy vs backtest | ≥ 80% match | Implementation correctness |
| Fill quality | Estimated slippage within 2× of actual | Execution model validity |
| P&L tracking error | < 15% vs backtest expectation | Model-reality gap |
| Regime behavior | Consistent with backtest regime analysis | Regime model validity |
| Drawdown | < 1.5× backtest max drawdown | Risk model validity |

### Shadow State Machine

```
INACTIVE → RUNNING → EVALUATING → PROMOTED | FAILED
```

- INACTIVE: Edge not in shadow mode
- RUNNING: Accumulating shadow trading data (min 30 days)
- EVALUATING: 30-day window complete, computing metrics
- PROMOTED: All metrics pass → eligible for live scaled entry
- FAILED: Any metric fails → return to edge-discovery for analysis

### Promotion Gate (Shadow → Live)

ALL must pass:
1. Shadow P&L positive over 30-day window
2. Fill quality within tolerance
3. No regime mismatch detected
4. Drawdown within bounds
5. PBO still valid (re-check with shadow data window)

If promoted → enter live scaled entry sequence (§1.13 Stage 5):
```
10% allocation → 7 days → if metrics hold →
25% allocation → 14 days → if metrics hold →
50% allocation → 14 days → if metrics hold →
100% allocation
```

Any step failure → reduce back to previous step or withdraw entirely.

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-data-pipeline` | Live data feed for shadow mode |
| `crypto-edge-engine` | Edge definition and EHS tracking |
| `crypto-edge-discovery` | Candidate edges for validation |
| `crypto-experiment-tracker` | Log walk-forward + shadow results |
| `crypto-knowledge-memory` | Record failures and anomalies |
| `crypto-test-fixtures` | Replay fixtures for regression testing |

## Output

Walk-forward verdict + shadow trading report + promotion decision.
