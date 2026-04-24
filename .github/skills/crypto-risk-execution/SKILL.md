---
name: crypto-risk-execution
description: 'Handle crypto risk engine, execution engine, margin management, kill-switch, Kelly sizing, CVaR, system state engine, NO-TRADE conditions, adversarial execution, and self-liquidation risk per PRDV4 §1.14-§1.29 and §7-§8.'
argument-hint: 'Describe the risk/execution task: risk parameter, position context, system state, and validation scope.'
user-invocable: true
---

# Crypto Risk & Execution Gate

Downstream risk enforcement, execution safety, and system state management per PRDV4 §7-§8.

## Contract

All outputs must comply with `_shared/references/contract-schema.md`.
Input must be a contract-compliant `READY` strategy-stage output.
`ALLOWED` permits execution. `BLOCKED` prevents it.

## Risk Engine (§8)

### Portfolio Risk Limits (§8.2)

| Parameter | Hard Limit |
|-----------|-----------|
| Daily loss | 2% NAV (NT-R02) |
| Max drawdown from peak | 15% → KS-3 |
| Portfolio CVaR₉₉ | 5% NAV/day (§1.18) |
| Total open risk | 4% equity (NT-R03) |
| Single position | 25% NAV (NT-R04) |
| Margin utilization | 80% → no new entries (NT-R06) |

### CVaR / Expected Shortfall (§1.18)

- Historical VaR₉₉ from 250-day rolling
- CVaR = mean of losses exceeding VaR threshold
- Risk budget: 5% NAV daily
- Marginal CVaR gate on every new position
- Stress CVaR: 3 scenarios, <8% limit

### Kill-Switch System (§1.19)

| Level | Trigger | Action |
|-------|---------|--------|
| KS-0 | Healthy | Full operation |
| KS-1 | -3% daily or Sharpe <0.5 | Reduce 50%, no new entries |
| KS-2 | -5% daily or latency 5× | Close all, no trading 24h |
| KS-3 | -10% weekly or exchange outage | Orderly exit TWAP 30-min |
| KS-4 | System integrity breach | Immediate flatten, manual restart |

Escalation: monotonically increasing during events. Cool-down periods enforced.

### Kelly Criterion (§1.28)

- Single-edge: f* = (pb - q) / b
- Half-Kelly default. Quarter-Kelly under uncertainty.
- Portfolio: f* = Σ⁻¹μ with sum constraint ≤ 0.04
- Log-utility check: G(f) > 0 required

### Self-Liquidation Risk (§1.26)

DTL safety bands:

| DTL | State | Action |
|-----|-------|--------|
| >15% | SAFE | Normal |
| 10-15% | MONITOR | Warn, tighten stop |
| 5-10% | DANGER | Reduce 50%, no new entries |
| 3-5% | CRITICAL | Close entirely, 24h NO-TRADE |
| <3% | EMERGENCY | Market close, KS-2 |

Margin utilization: Normal <50%, Caution 50-70%, Reduce 70-85%, Emergency >85%.

## Execution Engine (§7)

### Market Impact (§1.14, §7.1)

- Temporary: η·σ·(v/ADV)^γ·e^(-λt)
- Permanent: α·σ·(q/ADV)^δ
- Total cost: spread/2 + temp + perm + commission + funding
- If TC > 50% expected return → order blocked

### Adversarial Execution (§1.25, §7.6)

- Timing: HMAC-derived delay per tier
- Size: ±5% jitter, HMAC-derived
- Iceberg: split if >1% ADV, max 10 children
- Price: offset 0/1/2 ticks (60%/30%/10%)
- Pattern decorrelation on autocorrelation >0.3

### Order State Machine (§7.7)

CREATED → SUBMITTED → PARTIAL → FILLED / REJECTED / CANCELLED.
Partial fill timeout: MICRO 30s, INTRA 5min, SWING 30min.

## NO-TRADE Conditions (§1.21)

All 23 conditions in 6 categories enforced (INV-EXEC-001):

**Data (5)**: NT-D01 through NT-D05
**Risk (6)**: NT-R01 through NT-R06
**Regime (4)**: NT-G01 through NT-G04
**Edge (4)**: NT-E01 through NT-E04
**Execution (4)**: NT-X01 through NT-X04
**Temporal (3)**: NT-T01 through NT-T03

Ordered evaluation. NO OVERRIDE. Absolute gates.

## System State Engine (§1.29)

5 states: NORMAL (SS-0) → DEGRADED (SS-1) → DEFENSIVE (SS-2) → CRISIS (SS-3) → HALT (SS-4).

SHS = 1 - Σ(w_i · s_i) from 10 weighted signals.
Weights: [0.20, 0.15, 0.15, 0.10, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05].

Hysteresis thresholds for de-escalation. Immediate escalation.
ANY single s_i = 1.0 → CRISIS. KS-4 → HALT.

## Per-State Rules

- **NORMAL**: Full operation, 1-min monitoring
- **DEGRADED**: T0/T1 suspended, MICRO paused, -30% allocation, 10s monitoring
- **DEFENSIVE**: No new entries, tighten stops 50%, begin reducing
- **CRISIS**: Exit MICRO immediately, INTRA 15-min TWAP, cancel all pending
- **HALT**: Flatten all market orders, disable all engines, manual restart

## Decision Rules

- Risk overrides strategy unconditionally (INV-003)
- Unknown state → HOLD (INV-002)
- No trade preferable to bad trade (INV-006)
- If any NT condition active → BLOCKED with NT code
- If any risk limit breached → BLOCKED with limit reference

## Output

Contract-compliant risk-stage result + decision summary + enforced rules + audit trail.
