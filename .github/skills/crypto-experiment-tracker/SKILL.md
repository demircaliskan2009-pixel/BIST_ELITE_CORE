---
name: crypto-experiment-tracker
description: 'Track every edge as an experiment: parameters, performance, regime behavior, comparison framework. Full audit trail from hypothesis to live deployment or rejection.'
argument-hint: 'Describe the experiment: edge ID, parameters to track, comparison targets, and analysis scope.'
user-invocable: true
---

# Crypto Experiment Tracking System

Every edge is an experiment. Every experiment is tracked. Nothing is forgotten.

## Design Principles

- Every experiment has a unique ID, immutable once created.
- All parameters, metrics, and decisions are logged.
- Experiments are comparable across time, regime, and family.
- No experiment is deleted — rejected experiments inform future discovery.

## Experiment Schema

```json
{
  "experiment_id": "EXP-2026-04-042",
  "hypothesis_id": "HYP-A-042",
  "edge_family": "A",
  "created_at": "2026-04-01T00:00:00Z",
  "status": "RUNNING | COMPLETED | PROMOTED | REJECTED",

  "parameters": {
    "lookback": 60,
    "threshold": 1.5,
    "decay_lambda": 0.3,
    "normalization": "z-score_480",
    "entry_logic": "ofi_z > 1.5 AND spread_state != WIDE",
    "exit_logic": "ofi_z < 0.3 OR time_stop_4h"
  },

  "features": [
    {"feature_id": "feat_ofi_imbalance_1m_v3", "version": 3},
    {"feature_id": "feat_spread_state_v2", "version": 2}
  ],

  "data_snapshot": "snap_20260401_binance_btcusdt_1m",
  "code_commit": "abc123def456",

  "backtest_results": {
    "sharpe": 1.8,
    "hit_rate": 0.54,
    "max_drawdown": -4.2,
    "profit_factor": 1.6,
    "total_trades": 342,
    "avg_holding_hours": 2.3,
    "slippage_bps": 7.2,
    "commission_bps": 4.0,
    "funding_cost_bps": 1.2
  },

  "pbo_results": {
    "pbo_score": 0.32,
    "dsr": 2.1,
    "monte_carlo_p": 0.003,
    "param_sensitivity_pass": true
  },

  "walk_forward_results": {
    "windows": 3,
    "positive_windows": 3,
    "sharpe_retention": 0.62,
    "verdict": "PASS"
  },

  "shadow_results": {
    "duration_days": 30,
    "shadow_pnl": 2800,
    "tracking_error_pct": 8.2,
    "fill_quality_ok": true,
    "verdict": "PASS"
  },

  "regime_behavior": {
    "low_vol": {"sharpe": 2.1, "trades": 45},
    "normal": {"sharpe": 1.4, "trades": 210},
    "high_vol": {"sharpe": 0.6, "trades": 87},
    "crisis": {"sharpe": -0.3, "trades": 12}
  },

  "decision": "PROMOTED",
  "decision_reason": "All gates passed. PBO 0.32. Walk-forward 3/3 positive.",
  "promoted_at": "2026-05-15T00:00:00Z",
  "rejection_reason": null
}
```

## Experiment Lifecycle

```
CREATED → BACKTEST → PBO_CHECK → WALK_FORWARD → SHADOW → PROMOTED | REJECTED
```

Each transition is logged with timestamp and evidence.

## Comparison Framework

### Compare Two Experiments

```json
{
  "compare": ["EXP-2026-04-042", "EXP-2026-04-043"],
  "dimensions": ["sharpe", "hit_rate", "max_drawdown", "pbo_score", "regime_behavior"],
  "result": {
    "EXP-2026-04-042": {"sharpe": 1.8, "hit_rate": 0.54, "pbo": 0.32},
    "EXP-2026-04-043": {"sharpe": 1.5, "hit_rate": 0.56, "pbo": 0.38},
    "winner": "EXP-2026-04-042",
    "reason": "Higher Sharpe with lower PBO despite slightly lower hit rate"
  }
}
```

### Compare Across Regimes

For any experiment, break down performance by:
- Volatility regime (low / normal / high / crisis)
- Liquidity state (deep / normal / thin)
- Funding state (normal / extreme_positive / extreme_negative)
- Session (Asia / Europe / US)

### Family-Level Analysis

Aggregate experiments by edge family to identify:
- Which families produce most promoted edges
- Average PBO by family
- Regime sensitivity by family
- Feature reuse patterns

## Query Operations

| Query | Description |
|-------|-------------|
| `list_by_family(family)` | All experiments for a family |
| `list_by_status(status)` | All experiments with given status |
| `compare(exp_a, exp_b)` | Side-by-side comparison |
| `family_summary(family)` | Aggregate stats for family |
| `regime_analysis(exp_id)` | Regime breakdown for experiment |
| `best_of_family(family, metric)` | Top N by metric within family |
| `rejection_reasons(family)` | Common rejection patterns |
| `feature_usage()` | Which features appear in successful edges |

## Storage

| Component | Path |
|-----------|------|
| Experiment registry | `data/experiments/registry.jsonl` |
| Experiment details | `data/experiments/<exp_id>.json` |
| Comparison reports | `data/experiments/comparisons/` |
| Family summaries | `data/experiments/summaries/` |

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-edge-discovery` | Creates experiments on hypothesis |
| `crypto-walk-forward-shadow` | Updates walk-forward + shadow results |
| `crypto-edge-engine` | References active experiment for each live edge |
| `crypto-feature-store` | Links feature versions used |
| `crypto-knowledge-memory` | Sends rejection patterns |
| Telemetry | Experiment metrics feed dashboard |

## Output

Experiment record + comparison results + regime analysis + decision trail.
