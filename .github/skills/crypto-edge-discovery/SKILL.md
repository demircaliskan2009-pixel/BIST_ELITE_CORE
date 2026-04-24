---
name: crypto-edge-discovery
description: 'Automatic alpha discovery framework: hypothesis generation, feature engineering, signal construction, validation pipeline, overfitting rejection via PBO/CSCV. Integrates with crypto-edge-engine for promotion to live edge families A-G per PRDV4 §1.13 and §1.22.'
argument-hint: 'Describe the discovery task: target market condition, data available, hypothesis family, and validation constraints.'
user-invocable: true
---

# Crypto Edge Discovery Engine

Systematic alpha discovery pipeline. No guessing. No curve-fitting. Evidence-driven only.

## Architecture Position

```
discovery → validation → edge-engine (promotion) → risk-execution
```

Discovery feeds validated edge candidates INTO `crypto-edge-engine` via the promotion gate.
No discovered edge may bypass the 5-stage validation pipeline (§1.13).

## Discovery Pipeline

### Stage 1: Hypothesis Generation

Sources (deterministic only):
- Microstructure anomalies (order flow, book imbalance, sweep detection)
- Cross-exchange divergences (Binance vs Bybit spread)
- Temporal patterns (session handoff, funding settlement windows)
- Liquidation cascade dynamics
- Volatility regime transitions

Rules:
- Every hypothesis MUST cite a microstructure mechanism (INV-EDGE-001).
- No hypotheses from pattern-matching alone.
- No ML-generated hypotheses. No LLM suggestions.
- Each hypothesis has a written invalidation condition BEFORE testing.

Hypothesis format:
```
{
  "id": "HYP-<family>-<seq>",
  "family": "A-G",
  "mechanism": "<microstructure explanation>",
  "invalidation": "<exact condition that kills this edge>",
  "features": ["<feature_1>", "<feature_2>"],
  "expected_behavior": "<when/how this produces alpha>",
  "crowding_risk": "<how others could exploit same pattern>"
}
```

### Stage 2: Feature Engineering

Rules:
- All features computed from validated SAFE data (contract schema).
- Explicit formula, lookback period, and alignment for every feature.
- No look-ahead bias. Strict point-in-time enforcement.
- Features registered in feature store (`crypto-feature-store` skill).
- Feature lineage tracked: raw data → derived feature → signal.

Feature specification:
```
{
  "name": "ofi_imbalance_1m",
  "formula": "OFI = Σ(bid_delta - ask_delta) over 1min",
  "lookback_bars": 60,
  "alignment": "bar_close",
  "source_streams": ["depth@100ms"],
  "normalization": "z-score rolling 480 bars"
}
```

### Stage 3: Signal Construction

- Combine features into composite signal.
- All combination logic is deterministic code (weighted sum, threshold, etc.).
- No ML models. No neural nets. No gradient-based optimization.
- Signal must produce DIFFERENT values across time (if all identical → REJECT).
- Stable tie-breaking required.

### Stage 4: Backtest (Cost-Aware)

Per edge-validation prompt (§1.13 Stage 1):
- Almgren-Chriss market impact model
- Minimum 5 bps slippage
- Next-bar execution (no same-bar)
- Fill ratio model per ADV bucket
- Time-varying spread from historical L2
- Commission + funding costs included

### Stage 5: Overfitting Rejection

PBO/CSCV gate (§1.20):
- S=16 partitions, all C(16,8)=12,870 splits
- PBO < 0.40 → PASS
- PBO 0.40-0.60 → CAUTION (capped allocation)
- PBO > 0.60 → REJECT
- DSR check
- Monte Carlo permutation (10K shuffles)
- Parameter sensitivity: ±20% perturbation must retain profitability

### Stage 6: Promotion Decision

| Result | Action |
|--------|--------|
| PBO < 0.40 + all stages pass | PROMOTE to edge-engine as CANDIDATE (§1.22 FSM) |
| PBO 0.40-0.60 | PROMOTE with allocation cap |
| Any stage fails | REJECT → log to knowledge memory |
| Walk-forward unstable | REJECT → edge is overfit |

Promoted edges enter `crypto-edge-engine` at CANDIDATE state in the extended FSM.

## Nursery Management

- Max 20 candidates per family (§1.22)
- FIFO eviction when nursery full
- Incubation period: minimum 30 days before ACTIVE promotion
- Kill rate target: >80% of candidates should be rejected

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-feature-store` | Register features, track lineage |
| `crypto-edge-engine` | Promote validated candidates |
| `crypto-experiment-tracker` | Log all experiments |
| `crypto-knowledge-memory` | Record failed hypotheses |
| `crypto-walk-forward-shadow` | Walk-forward validation |

## Anti-Patterns (REJECT immediately)

- Hypothesis without microstructure mechanism
- Feature with no explicit formula
- Backtest without slippage/commission
- Signal that produces constant output
- Optimization without PBO check
- Promotion without walk-forward
- Any ML/LLM-generated signal logic

## Output

```
{
  "hypothesis_id": "HYP-A-042",
  "status": "PROMOTED | REJECTED | CAUTION",
  "pbo_score": 0.32,
  "sharpe_oos": 1.4,
  "hit_rate_oos": 0.54,
  "max_dd_oos": -3.2,
  "rejection_reason": null,
  "promoted_to": "CANDIDATE in family A",
  "experiment_id": "EXP-2026-04-042"
}
```
