---
name: crypto-edge-engine
description: 'Handle crypto edge engine tasks: edge families A-G implementation, microstructure depth model, liquidation intelligence, cross-exchange analysis, activation matrix, EHS lifecycle, meta edge layer, interaction model, crowding detection, decay model, and edge evolution per PRDV4 §1.'
argument-hint: 'Describe the edge task: family, target signal, features involved, validation scope.'
user-invocable: true
---

# Crypto Edge Engine

Signal generation and edge lifecycle management per PRDV4 §1.

## Contract

All outputs must comply with `_shared/references/contract-schema.md`.
Only `READY` strategy-stage output permits downstream risk gating.
Input must be a contract-compliant `SAFE` data-stage output.

## Edge Families (§1.1)

| Family | Alpha Source | Key Formula |
|--------|-------------|-------------|
| A | Order Flow Imbalance | OFI = Σ(bid_size_delta - ask_size_delta) |
| B | Funding Rate Mean-Reversion | z_FR = (FR - μ_FR) / σ_FR |
| C | Liquidation Cascade | L/S_imbalance = (liq_long - liq_short) / total_liq |
| D | Volatility Regime Transition | σ_transition = σ_fast / σ_slow |
| E | Cross-Exchange Fragmentation | D_net = (P_binance - P_bybit) - c_total |
| F | Session Handoff | Patterns at Asia/Europe/US session transitions |
| G | BTC Dominance | D_btc = BTC_mcap / total_crypto_mcap |

Every edge MUST have:
- Microstructure justification (INV-EDGE-001)
- Invalidation conditions (INV-EDGE-002)
- Crowding detection mechanisms (INV-EDGE-003)
- Validation pipeline completion (INV-EDGE-004)

## Microstructure Depth Model (§1.2)

6 components: OBI (λ=0.3 decay), Queue Position, Queue Depletion Rate, CTR (depth trust), Iceberg Detection, Sweep Detection (DSI).

Composite: `S_micro = Σ w_i * component_i` with declared weights summing to 1.0.

## Edge Activation Matrix (§1.5)

5 dimensions: volatility_regime, liquidity_state, spread_state, execution_tier, funding_state.
Hard rules: CRISIS → all edges off. EXTREME_LEVERAGE → reduce 70%.

## Edge Health Score (§1.6)

`EHS = 0.30*S_sharpe + 0.25*S_hit + 0.25*S_dd + 0.20*S_stab`

4-state FSM: ACTIVE → WARNING → DISABLED → QUARANTINE.
Hysteresis: ACTIVE→WARNING at EHS<0.40, WARNING→ACTIVE at EHS>0.55.

## Meta Edge Layer (§1.7)

- Max 5 concurrent active edges
- Allocation: `alloc_e = (EHS_e × Sharpe_e) / Σ(EHS_i × Sharpe_i)`
- Floor 5%, cap 40% per edge
- 24h rebalance cycle

## Crowding Detection (§1.11)

6 mechanisms: OI buildup, funding extremometer, cross-exchange divergence, factor correlation, Sharpe decay under volume, volume share concentration.

## Edge Evolution (§1.22)

Extended FSM: CANDIDATE → INCUBATION → ACTIVE → WARNING → MUTATION.
- 5 mutants, ±10% perturbation
- A/B testing: 14-day parallel, Welch's t-test p<0.10
- Nursery pool: max 20 candidates/family

## Validation Pipeline (§1.13)

5 stages:
1. Hypothesis → Backtest (costs, slippage, walk-forward)
2. Walk-Forward (≥3 OOS windows, ≥3 months each)
3. Stress Testing (high-vol ×1.5, low-liq ×0.2, flash crash)
4. Paper Trading (30 days)
5. Live Scaled Entry (10% → 25% → 50% → 100%)

## Overfitting Protection (§1.20)

- PBO/CSCV: S=16, all C(16,8)=12,870 splits
- PBO < 0.40 required
- DSR, Monte Carlo permutation (10K), parameter sensitivity (±20%)

## Implementation Rules

- All signal logic deterministic code. No ML. No LLM.
- Features must be explicitly defined with formula, lookback, alignment.
- No look-ahead bias. No future data leakage.
- Ranking produces DIFFERENT scores. If all equal → SYSTEM ERROR.
- Stable tie-breaking required for all rankings.

## Output

Contract-compliant strategy-stage result + feature summary + edge health states.
