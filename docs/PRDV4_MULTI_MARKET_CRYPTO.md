# PRDV4 — Multi-Market Algorithmic Trading System

## Product Requirements Document — Version 4.0

| Field | Value |
|-------|-------|
| **Version** | PRDV4 |
| **Date** | 2026-04-15 |
| **Status** | FINAL |
| **Scope** | Multi-market: BIST equities + Crypto perpetual futures |
| **Lineage** | PRD → PRDV2 → PRDV2_ULTIMATE → PRDV3 → **PRDV4** |
| **Classification** | INSTITUTIONAL — PRODUCTION-GRADE |

---

## §0 — Document Constitution & Philosophy

### §0.1 — Scope Declaration

This document defines a **multi-market algorithmic trading system** operating across two markets:

1. **BIST Equities** — governed by PRDV3 (reference-only in this document; full specification: `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md`)
2. **Crypto Perpetual Futures** — fully specified in this document

**Explicit Supersession**: This document supersedes PRDV3 §1 ("BIST-only scope"). All other PRDV3 invariants, constraints, and architectural patterns are preserved without modification.

### §0.2 — Crypto Module Scope

- **Instrument class**: Perpetual futures contracts ONLY. No spot trading. No options. No margin tokens.
- **Exchanges**: Binance (primary execution + data), Bybit (secondary data + failover execution), CoinGecko (discovery + reference pricing)
- **Base currency**: USD. All portfolio accounting, risk calculations, and performance reporting denominated in USD.
- **Maximum leverage**: 3× default. Regime-scaled: 2× in DEGRADED, 1.5× in DEFENSIVE, 1× in CRISIS, 0× in HALT.

### §0.3 — Hard Invariants

Six invariants govern all system behavior. No subsystem, edge, strategy, or operational decision may violate these.

| ID | Invariant | Enforcement | Violation Response |
|----|-----------|-------------|-------------------|
| INV-001 | **Determinism** — identical input stream produces identical output sequence | All signal logic is pure deterministic code; no stochastic elements in decision paths | System halt + audit |
| INV-002 | **Fail-Closed** — missing or invalid data produces HOLD with explicit reason | Every data consumer validates completeness before use; NT conditions gate all orders | Order rejected with reason code |
| INV-003 | **Risk-First** — risk limits override strategy signals unconditionally | Risk engine evaluates AFTER signal generation, BEFORE order submission | Signal discarded, logged |
| INV-004 | **No Hidden State** — all state is persisted, auditable, and recoverable | Every state transition logged to JSONL with full context; crash recovery replays from persisted state | State reconstruction from audit log |
| INV-005 | **AI-Safe** — AI MUST NOT generate orders, modify risk parameters, or execute trades | AI subsystem has read-only access to market data and trade history; no write path to order engine | Integration rejected at compile time |
| INV-006 | **Capital Preservation** — no trade is preferable to a bad trade | All ambiguous signals resolve to NO TRADE; all unknown states resolve to HOLD | Default action = HOLD |

### §0.4 — BIST Module Reference

For the complete BIST equities specification, refer to `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md`. All PRDV3 invariants apply to the BIST module without modification. The BIST module is NOT duplicated in this document.

---

## §1 — Edge Model

The Edge Model defines WHY the system trades, WHEN it is allowed to trade, and HOW edges are managed through their lifecycle. No other section of this PRD may be implemented without this foundation. Every trading decision traces back to a formally defined edge with microstructure justification, persistence argument, invalidation conditions, and validation pipeline completion.

### §1.1 — Alpha Source Taxonomy

Seven alpha families (A–G). Each family has: mathematical definition, microstructure justification, persistence argument, and invalidation conditions.

#### Family A — Order Flow Imbalance

**Definition**:

$$OFI_N = \frac{\sum_{i=1}^{N}(V^{agg}_{buy,i} - V^{agg}_{sell,i})}{\sum_{i=1}^{N} V_{total,i}}$$

Computed over $N$ ticks.

**Microstructure Justification**: Aggressive orders in perpetual futures signal informed flow. L2+ order book transparency enables detection of directional intent before price adjustment.

**Persistence Argument**: Retail leverage traders create predictable aggressive flow patterns. This is structural to perpetual swap markets and persists as long as retail participation dominates aggressive order flow.

**Invalidation Conditions**:
- Fill rate < 40% (execution degradation invalidates the alpha source)
- OFI Sharpe < 0.5 over 30-day rolling window (signal has decayed to noise)
- Matching engine architecture change detected via latency distribution shift (KS-test on order-to-fill latency, p < 0.01)

#### Family B — Funding Rate Mean-Reversion

**Definition**:

$$\text{Signal: } |FR_t| > FR_{threshold}$$

- $FR_{threshold,long} = 0.05\%$ per 8h settlement (enter long when funding is excessively negative)
- $FR_{threshold,short} = -0.03\%$ per 8h settlement (enter short when funding is excessively positive)

**Microstructure Justification**: Extreme funding rates indicate crowded directional positioning. The funding mechanism is a structural feature of perpetual swap contracts that creates predictable unwinding pressure.

**Persistence Argument**: Funding is a structural mechanism of perpetual swap contract design. It cannot be eliminated without changing the contract specification.

**Invalidation Conditions**:
- Funding rate range compresses to < 0.01% per 8h sustained for > 30 consecutive days (the signal source has disappeared)

#### Family C — Liquidation Cascade Exploitation

**Definition**:

$$\Delta OI_{1h} < -5\% \text{ AND } V_{1h} > 3\bar{V}_{24h} \text{ AND price recovery} > 50\% \text{ of sweep range within 30 min}$$

**Microstructure Justification**: Forced liquidations are mechanical (non-informational) order flow. The temporary price impact of liquidation cascades reverts as the forced selling exhausts.

**Persistence Argument**: Leverage is structural to perpetual futures. Cascading liquidations are a mechanical consequence of margin calls at clustered price levels.

**Invalidation Conditions**:
- Exchange implements gradual liquidation mechanisms that eliminate cascading behavior
- $OI / \text{market\_cap} < 20\%$ (insufficient leverage in the system to generate meaningful cascades)

#### Family D — Volatility Regime Transition

**Definition**:

$$ATR_{short} < 0.6 \times ATR_{long} \rightarrow \text{compression detected}$$

Entry when: range exceeds $1.5 \times$ compressed range AND volume exceeds $1.5\bar{V}$.

**Microstructure Justification**: 24/7 trading combined with leverage creates more frequent compression/expansion cycles than equity markets.

**Persistence Argument**: Microstructural consequence of continuous trading and leverage. Not behavioral — driven by market structure.

**Invalidation Conditions**:
- UNKNOWN regime state persists > 30% of the time over a 90-day window
- ATR ratio remains in [0.8, 1.2] for > 60 consecutive days (no compression/expansion cycles)

#### Family E — Cross-Exchange Fragmentation

**Definition**:

$$\frac{|P_{Binance} - P_{Bybit}|}{P_{mid}} > 0.15\% \text{ for } > 5 \text{ seconds}$$

**Microstructure Justification**: Information asymmetry or liquidity imbalance between venues creates temporary mispricings.

**Persistence Argument**: Regulatory jurisdictional fragmentation ensures continued liquidity fragmentation across venues.

**Invalidation Conditions**:
- Mean dislocation duration falls below 1 second (HFT has closed the gap)
- Cross-venue execution is unprofitable net of all costs (spread + commission + slippage + latency penalty)

#### Family F — Session Handoff Patterns

**Definition**:

Sessions: Asia (00:00–08:00 UTC), Europe (08:00–16:00 UTC), US (16:00–00:00 UTC).

Signal: session transition + confirmed directional breakout from prior-session range.

**Microstructure Justification**: Global timezone participation is structural and creates predictable flow transitions at session boundaries.

**Persistence Argument**: Structural to global participation patterns. Degrades only with truly institutional 24/7 even flow distribution.

**Invalidation Conditions**:
- KS-test p-value > 0.10 across session volume distributions over 90 days (sessions have become statistically uniform)

#### Family G — BTC Dominance Regime Shift

**Definition**:

- BTC dominance (BTC.D) rising → altcoins underperform
- BTC.D falling → altcoins outperform
- Trade: long lagging altcoin perpetual vs short BTC perpetual hedge when dominance is declining + catalyst present

**Microstructure Justification**: BTC's reserve-currency status within crypto creates structural correlation regimes that govern capital rotation.

**Persistence Argument**: Structural to crypto market hierarchy. Degrades with institutional altcoin adoption that decouples from BTC.

**Invalidation Conditions**:
- BTC.D 30-day range < 2% sustained for > 90 days (dominance has stabilized, regime shifts no longer occur)

---

### §1.2 — Microstructure Depth Model

Family A (Order Flow) is elevated from single-metric OFI to a 6-component microstructure model.

#### A.1 — Multi-Level Order Book Imbalance (OBI)

Imbalance measured across $K$ price levels:

$$OBI_K = \frac{\sum_{k=1}^{K} w_k (Q^{bid}_k - Q^{ask}_k)}{\sum_{k=1}^{K} w_k (Q^{bid}_k + Q^{ask}_k)}$$

- Level weights: $w_k = e^{-\lambda(k-1)}$ where $\lambda = 0.3$ (exponential decay)
- Default $K = 10$ price levels
- Output range: $[-1, +1]$
- Significance threshold: $|OBI_{10}| > 0.35$
- Update frequency: every order book update (tick-by-tick)

**Justification**: Multi-level imbalance captures depth-of-book pressure that top-of-book misses. Informed traders layer orders across multiple levels.

#### A.2 — Queue Position Model

Estimates effective queue position for limit orders at best bid/ask:

$$QP_{side} = \frac{Q^{ahead}_{side}}{Q^{total}_{side}}$$

Fill probability:

$$P_{fill} = \max\left(0,\ 1 - \frac{QP_{side}}{1 + R_{depletion} \times \Delta t}\right)$$

Where $R_{depletion}$ is the queue depletion rate (§1.2 A.3).

Used by: execution engine (maker vs taker decision), edge activation matrix (execution feasibility check).

#### A.3 — Queue Depletion Rate

Measures how fast the queue at best price is consumed:

$$R_{depletion} = \frac{\sum_{i=1}^{N} (\Delta Q^{consumed}_i)}{\sum_{i=1}^{N} \Delta t_i}$$

- Computed over $N = 100$ most recent queue events at best bid/ask
- Units: contracts/second
- Signal: $R_{depletion} > 2\bar{R}_{depletion,1h}$ = aggressive consumption → imminent price move

**Justification**: Queue depletion acceleration is preceded by informed flow and is a measurable lead indicator of price discovery.

#### A.4 — Cancel-to-Trade Ratio (CTR)

$$CTR = \frac{N_{cancels}}{N_{trades}}$$

Computed over rolling $T = 60$ second window.

| CTR Range | Interpretation |
|-----------|---------------|
| $CTR > 5.0$ | High-frequency quoting / spoofing risk → reduce confidence in displayed depth |
| $CTR < 1.0$ | Genuine resting liquidity → trust displayed depth |
| $CTR \in [1.0, 5.0]$ | Normal market making activity |

Depth trust adjustment when $CTR > 5.0$:

$$\alpha_{CTR} = \frac{1.0}{1 + 0.2 \times (CTR - 5.0)}$$

#### A.5 — Hidden Liquidity / Iceberg Detection

Detection: trade executes at a price level where visible depth was less than trade size → hidden liquidity present.

Iceberg score over rolling 5-minute window:

$$ICE = \frac{\sum V_{hidden\_fills}}{\sum V_{total\_fills}}$$

| ICE Condition | Interpretation |
|---------------|---------------|
| $ICE > 0.20$ on bid side | Institutional buyer absorbing supply → bullish signal |
| $ICE > 0.20$ on ask side | Institutional seller absorbing demand → bearish signal |

**Justification**: Iceberg orders are institutional. Their presence indicates informed flow too large to display without price impact.

#### A.6 — Aggressive Sweep Detection

An aggressive sweep occurs when a market order consumes $\geq 3$ price levels within a single matching cycle:

$$SWEEP_{side} = \begin{cases} 1 & \text{if levels\_consumed} \geq 3 \text{ AND } V_{sweep} > 2\bar{V}_{1min} \\ 0 & \text{otherwise} \end{cases}$$

Sweep rate: $SR = \frac{N_{sweeps,5min}}{N_{sweeps,1h\_avg}}$

- $SR > 2.0$ = elevated sweep activity

Directional sweep imbalance:

$$DSI = \frac{N_{buy\_sweeps} - N_{sell\_sweeps}}{N_{buy\_sweeps} + N_{sell\_sweeps}}$$

- $|DSI| > 0.5$ = directionally informed aggressive flow

**Justification**: Multi-level sweeps indicate urgency and information that cannot be satisfied at a single price level.

#### Composite Microstructure Signal

$$\mu_{composite} = 0.25 \times OBI_{10} + 0.15 \times R_{depletion}^{norm} + 0.15 \times (1 - \alpha_{CTR}) + 0.20 \times ICE_{directional} + 0.25 \times DSI$$

All components normalized to $[-1, +1]$.

**Actionable threshold**: $|\mu_{composite}| > 0.40$.

---

### §1.3 — Liquidation Intelligence System

Family C is elevated from post-facto detection to a 4-component real-time liquidation intelligence system.

#### C.1 — Real-Time Liquidation Feed Model

Data source: Binance Liquidation Order Stream (`forceOrder` WebSocket).

Aggregation: rolling 1-minute, 5-minute, and 60-minute liquidation buckets.

Metrics per bucket:
- $LV_{long}$ = total long liquidation volume
- $LV_{short}$ = total short liquidation volume
- $LN_{long}$ = number of long liquidation events
- $LN_{short}$ = number of short liquidation events
- $L_{avg\_size}$ = average liquidation order size

#### C.2 — Long vs Short Liquidation Imbalance

$$LIQ_{imbalance} = \frac{LV_{long} - LV_{short}}{LV_{long} + LV_{short} + \epsilon}$$

- $\epsilon = 1$ (prevents division by zero)
- Output range: $[-1, +1]$

| Condition | Interpretation |
|-----------|---------------|
| $LIQ_{imbalance} < -0.60$ | Dominant long liquidation → shorts winning → potential bounce after cascade exhaustion |
| $LIQ_{imbalance} > +0.60$ | Dominant short liquidation → longs winning → potential pullback after squeeze exhaustion |

Trade logic: fade the dominant liquidation direction AFTER cascade exhaustion is confirmed (see C.3).

#### C.3 — Cascade Acceleration Detection

Cascade acceleration ratio:

$$CA = \frac{LV_{1min,current}}{LV_{1min,prev}}$$

| CA Value | State | Action |
|----------|-------|--------|
| $CA < 1.5$ | NORMAL | No cascade |
| $1.5 \leq CA < 3.0$ | BUILDING | Cascade forming — DO NOT enter |
| $CA \geq 3.0$ | ACTIVE_CASCADE | Cascade in progress — DO NOT enter |
| $CA < 0.5$ AND $LV_{1min} < 0.3 \times LV_{5min\_peak}$ | EXHAUSTING | Cascade ending — prepare entry |
| $LV_{1min} < 0.1 \times LV_{5min\_peak}$ for 3 consecutive minutes | CASCADE_COMPLETE | Entry allowed |

**INVARIANT**: No entry during BUILDING or ACTIVE_CASCADE states. Zero exceptions.

#### C.4 — Pre-Liquidation Positioning Signals

- **OI Concentration**: when $\frac{\Delta OI_{4h}}{OI_{total}} > 0.08$ AND price approaches a known liquidation cluster → pre-position for cascade
- **Liquidation cluster estimation**: $P_{liq\_long} \approx P_{entry} \times (1 - \frac{1}{\text{leverage}})$; for common 10× leverage: ~10% below entry cluster
- **Funding rate alignment**: $FR > 0.08\%/8h$ AND price declining toward liquidation cluster → high probability of long cascade → prepare short or wait for bounce entry
- **Warning signal timing**: issue PREPARE signal when price is within 2% of estimated liquidation cluster AND cascade state = NORMAL

---

### §1.4 — Cross-Exchange Intelligence System

Family E is elevated from simple dislocation detection to a 4-component cross-venue intelligence system.

#### E.1 — Lead-Lag Relationship Model

Cross-correlation at lag $\tau$:

$$\rho(\tau) = \text{corr}(r^{Binance}_t, r^{Bybit}_{t+\tau})$$

- Compute for $\tau \in [-500ms, +500ms]$ at 50ms resolution
- Leader determination: $\tau^* = \underset{\tau}{\arg\max}\ |\rho(\tau)|$
  - $\tau^* > 0$ → Binance leads
  - $\tau^* < 0$ → Bybit leads
- Leadership stability: compute $\tau^*$ over rolling 1-hour windows
  - Stable: sign of $\tau^*$ consistent $\geq 80\%$ of windows → stable leader
  - Unstable: $< 60\%$ consistency → disable cross-exchange edge

#### E.2 — Latency-Adjusted Arbitrage

Net dislocation after costs:

$$D_{net} = |P_{lead} - P_{lag}| - C_{maker,lead} - C_{taker,lag} - S_{est} - L_{penalty}$$

Where:
- $C_{maker}$: maker fee (2 bps Binance typical)
- $C_{taker}$: taker fee (5 bps Bybit typical)
- $S_{est}$: estimated slippage on lagging venue
- $L_{penalty} = \frac{d_{latency}}{1000} \times \sigma_{1s}$ (latency risk = propagation delay × 1-second volatility)

| Condition | Action |
|-----------|--------|
| $D_{net} > 0$ AND duration > 500ms | Actionable arbitrage opportunity |
| $D_{net} \leq 0$ | Not profitable after costs → no trade |

#### E.3 — Order Book Mirroring Score

Measures structural similarity between venue order books:

$$M_{score} = 1 - \frac{\sum_{k=1}^{K} |Q^{Binance}_k - Q^{Bybit}_k|}{\sum_{k=1}^{K} (Q^{Binance}_k + Q^{Bybit}_k)}$$

| M_score | Interpretation |
|---------|---------------|
| $> 0.80$ | Highly mirrored → arbitrage difficult (market makers synchronized) |
| $< 0.50$ | Divergent books → potential arbitrage or information asymmetry |
| Drop $> 0.20$ in 30 seconds | Structural divergence event → increase monitoring |

#### E.4 — Edge-Tied Smart Routing

Routing decision tree:
1. IF $D_{net} > 0$ AND leader is stable → execute on lagging venue in leader's direction
2. IF depth at primary venue < $2 \times$ order size within 5 bps → route to secondary
3. IF $M_{score} < 0.50$ → split order 60/40 across venues (price improvement capture)
4. IF latency to secondary > 100ms → do not route to secondary (stale risk)

Routing latency budget: 50ms total (decision + submission).

---

### §1.5 — Edge Activation Matrix

No edge fires independently. Every edge passes the activation matrix before generating a signal.

#### Activation Function

$$A_{edge} = f(\mathcal{R}, \sigma, \mathcal{L}, \mathcal{S}, \mathcal{E})$$

Where:
- $\mathcal{R}$ = regime state ∈ {TRENDING, RANGE, HIGH_VOL, CRISIS, UNKNOWN}
- $\sigma$ = volatility bucket ∈ {LOW, MED, HIGH, EXTREME}
- $\mathcal{L}$ = liquidity state ∈ {DEEP, NORMAL, THIN, DRY}
- $\mathcal{S}$ = spread stability ∈ {STABLE, WIDENING, BLOWN}
- $\mathcal{E}$ = execution conditions ∈ {OPTIMAL, DEGRADED, IMPAIRED, HALTED}

#### Volatility Classification

$\sigma_{realized} = \text{std}(r_{5min}, 24)$ (24 five-minute returns)

| Bucket | Range |
|--------|-------|
| LOW | $\sigma_r < 0.005$ |
| MED | $[0.005, 0.015)$ |
| HIGH | $[0.015, 0.035)$ |
| EXTREME | $\geq 0.035$ |

#### Liquidity Classification

$L_{score} = \frac{D_{10bps}}{\bar{D}_{10bps,24h}}$

| State | Range |
|-------|-------|
| DEEP | $L_{score} > 1.5$ |
| NORMAL | $[0.7, 1.5]$ |
| THIN | $[0.3, 0.7)$ |
| DRY | $< 0.3$ |

#### Spread Stability

$CV_{spread} = \frac{\sigma(spread_{5min})}{\bar{spread}_{5min}}$ over 30-minute rolling window

| State | Range |
|-------|-------|
| STABLE | $CV < 0.5$ |
| WIDENING | $[0.5, 1.5)$ |
| BLOWN | $\geq 1.5$ |

#### Execution Conditions

| State | Criteria |
|-------|----------|
| OPTIMAL | Latency < 100ms AND fill rate > 90% (last 20 orders) |
| DEGRADED | Latency ∈ [100ms, 300ms] OR fill rate ∈ [70%, 90%] |
| IMPAIRED | Latency ∈ [300ms, 500ms] OR fill rate ∈ [50%, 70%] |
| HALTED | Latency > 500ms OR fill rate < 50% OR exchange API error |

#### Per-Edge Activation Rules

| Edge | Regime Allows | Vol Allows | Liq Allows | Spread Allows | Exec Allows |
|------|--------------|-----------|-----------|--------------|------------|
| A: Order Flow | TRENDING, RANGE | LOW, MED, HIGH | DEEP, NORMAL | STABLE, WIDENING | OPTIMAL, DEGRADED |
| B: Funding Rate | RANGE, HIGH_VOL | MED, HIGH | DEEP, NORMAL, THIN | STABLE, WIDENING | OPTIMAL, DEGRADED |
| C: Liquidation | HIGH_VOL | HIGH, EXTREME | NORMAL, THIN | any | OPTIMAL, DEGRADED |
| D: Vol Transition | RANGE→any | LOW→MED+ (transition) | DEEP, NORMAL | STABLE | OPTIMAL |
| E: Cross-Exchange | TRENDING, RANGE | LOW, MED | DEEP, NORMAL | STABLE | OPTIMAL |
| F: Session Handoff | TRENDING, RANGE | LOW, MED, HIGH | DEEP, NORMAL | STABLE, WIDENING | OPTIMAL, DEGRADED |
| G: BTC Dominance | any except CRISIS | LOW, MED, HIGH | DEEP, NORMAL | STABLE, WIDENING | OPTIMAL, DEGRADED |

#### Hard Rules

- Regime = CRISIS → ALL edges deactivated (zero allocation)
- Regime = UNKNOWN → ALL edges deactivated except B (funding rate, reduced to 25% allocation)
- Execution = HALTED → ALL edges deactivated immediately
- Liquidity = DRY → ALL edges deactivated except monitoring
- Spread = BLOWN → only edges B and C allowed (at 50% allocation)

#### Deactivation Conditions (per edge, ANY triggers deactivation)

- Edge exits its allowed regime/vol/liq/spread/exec state
- Edge health score (§1.6) drops below 0.30
- Edge drawdown exceeds per-edge max DD threshold
- Manual override (operator kill switch)
- System-wide risk halt (from Risk Engine)

---

### §1.6 — Edge Decay Model

Every active edge maintains a real-time health score that directly controls allocation.

#### Edge Health Score (EHS)

$$EHS = w_1 \times S_{sharpe} + w_2 \times S_{hitrate} + w_3 \times S_{drawdown} + w_4 \times S_{stability}$$

Weights: $w_1 = 0.30$, $w_2 = 0.25$, $w_3 = 0.25$, $w_4 = 0.20$

#### Component 1: Rolling Sharpe Decay ($S_{sharpe}$)

$$\text{Sharpe}_{30d} = \frac{\bar{r}_{30d}}{\sigma_{30d}} \times \sqrt{365}$$

$$S_{sharpe} = \min\left(1.0,\ \max\left(0.0,\ \frac{\text{Sharpe}_{30d}}{2.0}\right)\right)$$

- Sharpe ≥ 2.0 → full score (1.0)
- Sharpe = 0 → zero score (0.0)
- Decay detection: if $\text{Sharpe}_{30d} < 0.5 \times \text{Sharpe}_{90d}$ → DECAY_ALERT

#### Component 2: Hit Rate Degradation ($S_{hitrate}$)

$$HR_{30d} = \frac{N_{win,30d}}{N_{total,30d}}$$

$$S_{hitrate} = \min\left(1.0,\ \max\left(0.0,\ \frac{HR_{30d} - 0.35}{0.30}\right)\right)$$

- HR ≥ 65% → full score; HR = 35% → zero score
- Minimum sample: $N_{total,30d} \geq 10$; if fewer trades → $S_{hitrate} = 0.5$ (neutral)
- Degradation detection: if $HR_{30d} < HR_{90d} - 0.10$ → HIT_RATE_ALERT

#### Component 3: Drawdown-Based Decay ($S_{drawdown}$)

$$S_{drawdown} = \max\left(0.0,\ 1.0 - \frac{DD_{current}}{DD_{max,edge}}\right)$$

Per-edge max DD thresholds:

| Edge | A | B | C | D | E | F | G |
|------|---|---|---|---|---|---|---|
| Max DD | 8% | 5% | 10% | 8% | 3% | 6% | 6% |

$DD_{current} \geq DD_{max,edge}$ → $S_{drawdown} = 0$ → edge DISABLED.

#### Component 4: Parameter Stability ($S_{stability}$)

$$CV_{signal} = \frac{\sigma(signal\_values_{30d})}{\bar{signal}_{30d}}$$

$$S_{stability} = \min\left(1.0,\ \max\left(0.0,\ 1.0 - \frac{CV_{signal}}{2.0}\right)\right)$$

$CV > 2.0$ → zero stability (signal is noise).

#### Health-Based Allocation Adjustment

$$\alpha_{edge} = \begin{cases} 1.0 & \text{if } EHS \geq 0.70 \\ 0.5 + 0.5 \times \frac{EHS - 0.30}{0.40} & \text{if } 0.30 \leq EHS < 0.70 \\ 0.0 & \text{if } EHS < 0.30 \end{cases}$$

#### Edge State Machine

| State | Condition | Allocation |
|-------|-----------|-----------|
| ACTIVE | $EHS \geq 0.70$ | Full allocation |
| WARNING | $0.30 \leq EHS < 0.70$ | Reduced per formula above |
| DISABLED | $EHS < 0.30$ | Zero allocation, monitoring only |
| QUARANTINE | 2+ DISABLED transitions in 30 days | Locked out for 14 days minimum; requires walk-forward revalidation |

**Hysteresis**: Transition from DISABLED → WARNING requires $EHS \geq 0.40$ sustained for 48 hours.

---

### §1.7 — Meta Edge Layer

The Meta Edge Layer sits above individual edges and controls the system-wide edge portfolio.

#### Edge Selection

$$E_{active} = \{e_i : A_{e_i} = \text{PASS} \text{ AND } EHS_{e_i} \geq 0.30\}$$

- Maximum concurrent active edges: 5
- If $|E_{active}| > 5$: select top 5 by $EHS \times \text{Sharpe}_{30d}$

#### Capital Allocation Across Edges

$$w_i = \frac{\max(EHS_i \times \text{Sharpe}_{30d,i},\ 0)}{\sum_{j \in E_{active}} \max(EHS_j \times \text{Sharpe}_{30d,j},\ 0)}$$

- If all numerators = 0 → equal weight: $w_i = \frac{1}{|E_{active}|}$
- Floor per active edge: $w_i \geq 0.05$ (minimum 5%)
- Cap per edge: $w_i \leq 0.40$ (maximum 40%)
- After floor/cap: renormalize to sum to 1.0

#### Dynamic Boost/De-weight Rules

| Condition | Action |
|-----------|--------|
| Sharpe_{30d} > 1.5 AND EHS > 0.80 AND no DECAY_ALERT | BOOST: multiply $w_i$ by 1.2 (before renormalization) |
| DECAY_ALERT active | DE-WEIGHT: multiply $w_i$ by 0.5 |
| $EHS < 0.30$ | DISABLE: $w_i = 0$, edge enters DISABLED state |

#### Portfolio-Level Edge Constraints

- Total edge exposure (sum of allocations × leverage) must not exceed portfolio risk budget
- Edge correlation limit: if pairwise correlation of two edge return streams $> 0.70$ over 60 days → the lower-Sharpe edge has allocation halved
- Maximum drawdown from all edges combined: 15% → if breached, reduce all edge allocations by 50% for 7 days

**Rebalance Frequency**: every 24 hours at 00:00 UTC. Emergency rebalance triggered by any edge state transition.

---

### §1.8 — Edge Interaction Model

Defines how edges interact when multiple edges produce simultaneous signals.

#### Edge Correlation Matrix

Maintained rolling 60-day:

$$\rho_{ij} = \text{corr}(r^{edge_i}_{1:T}, r^{edge_j}_{1:T})$$

- Updated daily
- If $\rho_{ij} > 0.70$ → edges $i, j$ are effectively the same bet → reduce combined allocation by $1 - \rho_{ij}/2$

#### Conflict Resolution

When edges produce opposing signals simultaneously:

1. Priority cascade by EHS: higher-health edge wins
2. If $|EHS_i - EHS_j| < 0.05$ (near-tie) → NO TRADE (ambiguous signal, fail-closed per INV-006)
3. If opposing edges are from different families → NO TRADE (family disagreement = structural ambiguity)
4. If opposing edges are from the same family at different timeframes → shorter timeframe wins for execution, longer timeframe determines sizing

#### Signal Stacking

When $\geq 2$ edges produce same-direction signal within 60-second window:

| Alignment | Multiplier |
|-----------|-----------|
| 2 edges | 1.0× (base case) |
| 3 edges | 1.15× |
| 4+ edges | 1.25× (capped) |

Stacking constraints:
- Stacked position passes all risk gates (max position, max exposure, max drawdown)
- Stacked edges have pairwise $\rho < 0.50$ (independent confirmation only)
- Stacking multiplier × position ≤ single-edge max position × 1.5

**Audit**: every multi-edge interaction event logged with timestamp, edges involved, signal directions, resolution method, final action, allocation impact.

---

### §1.9 — Funding Edge Safety

Family B (Funding Rate Mean-Reversion) receives additional safety gates.

#### Trend Filter

Trend strength: $TS = \frac{EMA_{12h} - EMA_{48h}}{ATR_{24h}}$

- $|TS| > 1.5$ = strong trend
- Rule: if funding is extreme BUT the trend is strongly aligned with the funding direction ($FR > 0$ AND $TS > 1.5$) → DO NOT fade the funding
- Rationale: crowded positioning in a strong trend persists far longer than expected; fading prematurely is a known blow-up pattern

#### Regime Filter

- Funding edge active ONLY in: RANGE, HIGH_VOL (from §1.5)
- Additional gate: if regime was TRENDING within last 4 hours → suppress funding edge for 4 additional hours (transition cooldown)
- CRISIS → funding edge disabled entirely

#### Anti-Trend Protection

Before entry, check: $\text{sign}(signal_{funding}) \neq \text{sign}(r_{4h})$

| Condition | Action |
|-----------|--------|
| Funding says SHORT but $r_{4h} > +2\%$ | BLOCK (price running, do not fight momentum) |
| Funding says LONG but $r_{4h} < -2\%$ | BLOCK (price crashing, do not catch the knife) |

Override: anti-trend protection overridden ONLY if $\mu_{composite}$ (§1.2) confirms the funding signal direction AND cascade state (§1.3) = CASCADE_COMPLETE.

#### Position Management for Funding Trades

- Maximum holding period: 24 hours
- Mandatory stop: $1.5 \times ATR_{4h}$ from entry
- Time-decay stop: tighten stop by 20% every 8 hours (aligned with funding settlement periods)

---

### §1.10 — Persistence Summary

| Family | Structural Basis | Expected Decay Horizon | Degradation Signal |
|--------|-----------------|----------------------|-------------------|
| A: Order Flow | Retail leverage + L2 transparency | > 3 years (structural) | Exchange architecture change |
| B: Funding Rate | Perpetual swap contract design | > 5 years (contract mechanics) | Major DEX disruption of perp design |
| C: Liquidation | Leverage mechanics | > 3 years (leverage is permanent) | Gradual liquidation adoption |
| D: Vol Transition | Continuous 24/7 + leverage cycles | > 5 years (market structure) | Market consolidation to fewer sessions |
| E: Cross-Exchange | Regulatory fragmentation | 1–3 years (declining with HFT) | Single dominant venue emergence |
| F: Session Handoff | Global timezone participation | 2–5 years (declining with adoption) | 24/7 even flow across timezones |
| G: BTC Dominance | BTC reserve-currency role | 3–5 years (declining with altcoin maturation) | BTC dominance permanent stabilization |

---

### §1.11 — Crowding Detection & Avoidance

Six detection mechanisms prevent the system from becoming exit liquidity in crowded trades.

#### Mechanism 1: Open Interest Buildup

- Monitor $\Delta OI_{24h} / OI$ per asset
- Threshold: $\Delta OI_{24h} > 15\%$ = crowding alert
- Action: reduce allocation for affected asset by 50%

#### Mechanism 2: Funding Extremometer

- Absolute funding extremity: $|FR| > 0.08\%/8h$ sustained for > 3 periods = extreme crowding
- Action: disable all directional edges aligned with the crowded side

#### Mechanism 3: Cross-Exchange Flow Divergence

- If net flow direction diverges between Binance and Bybit for > 2 hours → one venue is absorbing a crowd
- Detection: $\text{sign}(OFI_{Binance}) \neq \text{sign}(OFI_{Bybit})$ for > 2 hours
- Action: reduce allocation by 30% until convergence

#### Mechanism 4: Factor Crowding (Correlation)

- Track rolling 60-day correlation between the system's active edges and public factor returns (momentum, carry, mean-reversion)
- If correlation > 0.60 with a public factor → edge is crowded
- Action: de-weight by $1 - \rho_{factor}$

#### Mechanism 5: Sharpe Decay Under Volume

- If edge Sharpe declines while volume increases → classic crowding signature (alpha shared among more participants)
- Detection: $\text{Sharpe}_{30d}$ declining AND $V_{30d} / V_{90d} > 1.3$
- Action: trigger DECAY_ALERT (§1.6)

#### Mechanism 6: Volume Share Monitoring

- Track the system's volume as percentage of total exchange volume per asset
- If system volume > 0.5% of total → self-impact risk
- Action: cap further allocation growth, flag for capacity review (§1.15)

---

### §1.12 — Execution Quality as Edge Component

Six mechanisms ensure execution quality is a measurable alpha contributor.

#### Mechanism 1: Maker/Taker Decision

- If $QP_{side} < 0.30$ (queue position model, §1.2 A.2) AND $R_{depletion} < 1.5\bar{R}$ → use limit order (maker)
- If $QP_{side} > 0.70$ OR $R_{depletion} > 2\bar{R}$ → use market order (taker)
- Cost differential: maker rebate (−2 bps Binance) vs taker fee (+5 bps) = 7 bps edge

#### Mechanism 2: Depth-Aware Sizing

- Order size ≤ 2% of visible depth at 5 bps from mid (hard cap)
- If order size > depth at 5 bps → split into child orders or reduce size
- Depth trust: scale by $\alpha_{CTR}$ (§1.2 A.4) when CTR > 5.0

#### Mechanism 3: Latency Budget Enforcement

- Per-tier latency budgets enforced (§1.16)
- Orders exceeding their tier's latency budget are logged as degraded
- Persistent latency breach → disable the affected edge tier

#### Mechanism 4: Slippage Monitoring

- Track realized vs estimated slippage per order
- EWMA tracking (§1.24) with bounds [5, 500] bps
- If realized slippage > 2× estimated for 5 consecutive orders → execution degradation alert

#### Mechanism 5: Fill Quality Score

- Per-order fill quality: $FQ = 1 - \frac{|\text{fill\_price} - \text{signal\_price}|}{ATR_{1h}}$
- Rolling average $\bar{FQ}_{30d}$ tracked per edge
- If $\bar{FQ} < 0.70$ → edge execution quality is insufficient → flag for review

#### Mechanism 6: Smart Routing Optimization

- Route to venue with best combination of: depth, spread, latency, fee tier
- Routing score: $RS = 0.30 \times \text{depth\_score} + 0.25 \times \text{spread\_score} + 0.25 \times \text{latency\_score} + 0.20 \times \text{fee\_score}$
- Each component normalized to [0, 1] using rolling 24-hour percentiles
- Route to venue with highest RS; if RS difference < 0.05 → route to primary (Binance)

---

### §1.13 — Edge Validation Pipeline

Required before any edge goes live. Five stages, each with explicit pass/fail criteria.

#### Stage 1: Hypothesis → Backtest

- Minimum 12 months in-sample data
- Cost-aware simulation (slippage model from §1.12 + funding costs)
- Next-bar execution (no same-bar fill)
- Minimum 50 trades in backtest
- If any criterion fails → edge rejected at Stage 1

#### Stage 2: Walk-Forward Validation

- Minimum 3 out-of-sample windows (each ≥ 3 months)
- Walk-forward Sharpe ≥ 50% of in-sample Sharpe
- Walk-forward hit rate ≥ in-sample hit rate − 10 percentage points
- Positive expectancy in ≥ 2/3 of out-of-sample windows
- If any criterion fails → edge rejected at Stage 2

#### Stage 3: Stress Testing

| Scenario | Parameters | Pass Criterion |
|----------|-----------|----------------|
| High-vol stress | Returns × 1.5, slippage × 2.0 | Non-negative expectancy |
| Low-liquidity stress | Depth × 0.2, slippage × 3.0 | Non-negative expectancy |
| Flash crash | 10% gap, 5-min recovery, massive liquidation volume | Non-negative expectancy OR documented regime gate |

Each stress scenario produces non-negative expectancy OR the edge is rejected for that stress condition with a documented regime gate.

#### Stage 4: Paper Trading

- Minimum 30 days live paper trading
- Compare paper vs backtest: Sharpe, hit rate, slippage, fill rate
- If paper Sharpe < 50% of backtest Sharpe → edge rejected (execution gap too large)

#### Stage 5: Live Scaled Entry

| Timeline | Allocation | Condition to Advance |
|----------|-----------|---------------------|
| Weeks 1–2 | 10% of target | Metrics hold |
| Weeks 3–4 | 25% of target | Metrics hold |
| Weeks 5–8 | 50% of target | Metrics hold |
| Weeks 9+ | 100% of target | Metrics hold |

Any EHS drop below 0.50 during scaling → freeze at current allocation for 2 additional weeks.

---

### §1.14 — Market Impact Model

Unified Almgren-Chriss-inspired framework replacing all prior fragmented impact models.

#### Temporary Impact (reverts over time)

$$\Delta P_{temp}(t) = \eta \cdot \sigma_d \cdot \left(\frac{v(t)}{V_{ADV}}\right)^{\gamma} \cdot e^{-\lambda(T-t)}$$

| Parameter | Description | Default |
|-----------|-------------|---------|
| $\eta$ | Temporary impact coefficient | 0.1 (calibrated per asset) |
| $\gamma$ | Concavity exponent | 0.6 (crypto, vs 0.5 for equities) |
| $\lambda$ | Decay rate ($1/\tau$, $\tau$ = half-life in minutes) | BTC: $\tau = 5$ min; altcoins: $\tau = 2$ min |

Calibration: rolling 30-day regression of realized slippage vs order size, per asset tier.

#### Permanent Impact (persists — information content)

$$\Delta P_{perm} = \alpha_I \cdot \text{sgn}(q) \cdot \sigma_d \cdot \left(\frac{|q|}{V_{ADV}}\right)^{\delta}$$

| Parameter | Description | Default |
|-----------|-------------|---------|
| $\alpha_I$ | Permanent impact coefficient | BTC: 0.05; altcoins: 0.15 |
| $\delta$ | Exponent | 0.5 (linear in √-volume) |

Information leakage penalty: if permanent impact > 30% of expected edge → REDUCE SIZE.

#### Total Cost Model (per order)

$$TC(q) = \frac{s}{2} + \Delta P_{temp} + \Delta P_{perm} + c_{commission} + c_{funding}$$

- $s$: quoted half-spread (from live L2 book)
- $c_{commission}$: exchange fee tier (maker/taker differentiated)
- $c_{funding}$: pro-rated funding cost for expected holding period

#### Execution Schedule Optimization

For orders > 5% ADV: split into N child orders using TWAP/VWAP schedule.

Optimal participation rate:

$$r^* = \arg\min \left[ \lambda_{risk} \cdot \sigma^2 \cdot T \cdot (1-r) + \eta \cdot \sigma \cdot r^{\gamma} \right]$$

- Urgency parameter $\lambda_{risk}$ set by signal decay rate from §1.5
- Maximum participation rate: 2% of real-time volume (hard cap)

---

### §1.15 — Edge Capacity Constraints

Defines the maximum capital each edge absorbs before alpha decay makes it unprofitable.

#### Capacity Formula

$$K_{max}^{(e)} = \frac{(\mathbb{E}[r_e] - TC_{base}) \cdot V_{ADV}^{(e)} \cdot PR_{max}}{IC_{marginal}}$$

- $\mathbb{E}[r_e]$: expected return of edge $e$ (from bucketed returns in §1.1)
- $TC_{base}$: base transaction cost WITHOUT impact (spread + commission + funding)
- $V_{ADV}^{(e)}$: average daily volume of the asset class
- $PR_{max}$: maximum participation rate (2% of ADV, from §1.14)
- $IC_{marginal}$: marginal impact cost at capacity (from temporary impact model)

#### Alpha Decay Curve

$$\alpha(k) = \alpha_0 \cdot \left(1 - \left(\frac{k}{K_{max}}\right)^2\right) \text{ for } k \leq K_{max}$$

$$\alpha(k) = 0 \text{ for } k > K_{max}$$

Quadratic decay: 75% of alpha survives at 50% capacity, 0% at 100%.

#### Capacity Tiers

| Tier | Utilization | Action |
|------|------------|--------|
| Green | $k < 0.5 \cdot K_{max}$ | Full allocation allowed |
| Yellow | $0.5 \cdot K_{max} \leq k < 0.8 \cdot K_{max}$ | Reduce new entries by 50%, flag for monitoring |
| Red | $k \geq 0.8 \cdot K_{max}$ | No new entries, begin unwinding excess |

#### Per-Asset Capacity

- BTC: $K_{max}$ based on Binance BTC-USDT ADV (~$15B → high capacity)
- ETH: ~40% of BTC capacity
- Altcoins: capacity = $\min(K_{max}^{formula}, \$500K)$ — hard cap due to fragmentation

Capacity utilization tracked real-time. Tier boundary crossing triggers immediate allocation adjustment.

---

### §1.16 — Ultra-Low Latency Requirements

Different edges have different latency sensitivity. Latency budget is defined per tier.

#### Latency Budget Tiers

| Tier | Max Latency | Edge Families | Rationale |
|------|-------------|---------------|-----------|
| T0 — Ultra-Critical | < 10 ms | Microstructure (A), Cross-Exchange (E) | Order book signals decay in milliseconds |
| T1 — Critical | < 100 ms | Funding (B), Liquidation (C) | Event-driven signals with fast crowd response |
| T2 — Standard | < 1 s | Volatility (D), Session (F) | Bar-level signals, less latency-sensitive |
| T3 — Relaxed | < 10 s | Meta-layer rebalancing, BTC Dominance (G), regime transitions | Slow signals, no urgency |

#### Latency Measurement Protocol

$$L_{total} = L_{data} + L_{compute} + L_{network} + L_{exchange}$$

- $L_{data}$: WebSocket message receipt to internal event (measured)
- $L_{compute}$: event to signal to order generation (measured)
- $L_{network}$: order dispatch to exchange ACK (measured)
- $L_{exchange}$: exchange internal matching (assumed per exchange SLA)

All components measured with microsecond-precision timestamps.

#### Latency Degradation Response

| Condition | Action |
|-----------|--------|
| $L > 1.5 \times L_{tier}$ | Log warning, continue |
| $L > 2 \times L_{tier}$ | Reduce position size by 50% |
| $L > 5 \times L_{tier}$ | Disable T0/T1 edges; T2/T3 continue |
| $L > 10 \times L_{tier}$ for > 60 seconds | KILL-SWITCH: close all positions, PAUSE state |

#### Co-location Requirements

- Primary execution: AWS Tokyo / Singapore (nearest to Binance matching engine)
- Data feed: co-located WebSocket receivers with kernel bypass (optional, T0 only)
- Fallback: standard cloud with < 50 ms to exchange — T0 edges disabled on fallback

---

### §1.17 — Advanced Regime Decomposition

Extends the 5-state price regime with 3 independent orthogonal dimensions specific to crypto.

#### Dimension 1: Funding Regime

State space: {NEGATIVE_EXTREME, NEGATIVE, NEUTRAL, POSITIVE, POSITIVE_EXTREME}

Signal: 8-hour rolling average of perpetual funding rate.

| State | Threshold |
|-------|-----------|
| NEGATIVE_EXTREME | FR < −0.03% per 8h |
| NEGATIVE | FR ∈ [−0.03%, −0.01%) |
| NEUTRAL | FR ∈ [−0.01%, +0.01%] |
| POSITIVE | FR ∈ (+0.01%, +0.03%] |
| POSITIVE_EXTREME | FR > +0.03% per 8h |

Hysteresis: 3 funding periods (24 hours) before state transition.

Impact: POSITIVE_EXTREME → short bias (longs pay funding); NEGATIVE_EXTREME → long bias.

#### Dimension 2: Leverage Regime

State space: {LOW_LEVERAGE, NORMAL, HIGH_LEVERAGE, EXTREME_LEVERAGE}

Signal: exchange-reported open interest / market cap ratio (OI/MC).

| State | Threshold |
|-------|-----------|
| LOW_LEVERAGE | OI/MC < 0.02 |
| NORMAL | OI/MC ∈ [0.02, 0.05] |
| HIGH_LEVERAGE | OI/MC ∈ (0.05, 0.10] |
| EXTREME_LEVERAGE | OI/MC > 0.10 |

Secondary signal: estimated leverage ratio from liquidation data.

Impact: EXTREME_LEVERAGE → maximum defensiveness, reduce position sizes by 70%, widen stops.

#### Dimension 3: Liquidity Regime

State space: {DEEP, NORMAL, THIN, CRISIS}

Signal composite:

$$LIQ = 0.4 \times depth\_score + 0.3 \times spread\_score + 0.3 \times arrival\_score$$

Each component normalized to [0, 1] using 30-day rolling percentile.

| State | Threshold |
|-------|-----------|
| DEEP | LIQ > 0.75 |
| NORMAL | LIQ ∈ [0.40, 0.75] |
| THIN | LIQ ∈ [0.15, 0.40) |
| CRISIS | LIQ < 0.15 |

Impact: CRISIS → only T3 edges active, maximum participation rate halved.

#### Regime Tensor

Total state space: 5 (price) × 5 (funding) × 4 (leverage) × 4 (liquidity) = **400 regime cells**.

Hierarchical grouping:
- Price regime: primary filter
- Funding, leverage, liquidity: multiplicative modifiers on position sizing and edge activation

Edge activation: each edge declares which regime cells it is ALLOWED to trade in (sparse permission tensor). Default: if an edge has no explicit permission for a regime cell → NO TRADE.

#### Regime Transition Protocol

- Transitions require confirmation period (hysteresis per dimension)
- During transition: use the MORE CONSERVATIVE of the two adjacent states
- Rapid oscillation (> 3 transitions in 24h on any dimension) → force to most defensive state for 6 hours

---

### §1.18 — Portfolio-Level Risk: CVaR / Expected Shortfall

#### Value at Risk (VaR)

Historical VaR:

$$VaR_{\alpha} = -\text{Percentile}(\{r_t\}_{t=1}^{T},\ \alpha)$$

- Confidence levels: α = 95% (monitoring), α = 99% (hard limit)
- Lookback: T = 252 bars (rolling), exponentially weighted with λ = 0.94 (RiskMetrics decay)

#### Conditional VaR (CVaR / Expected Shortfall)

$$CVaR_{\alpha} = -\frac{1}{1-\alpha} \int_0^{1-\alpha} VaR_u \, du$$

Discrete approximation:

$$CVaR_{\alpha} = -\frac{1}{|\{r_t : r_t \leq -VaR_{\alpha}\}|} \sum_{r_t \leq -VaR_{\alpha}} r_t$$

Portfolio-level: computed on portfolio return stream (not sum of individual CVaRs).

#### Risk Budget Allocation

- Total portfolio CVaR₉₉ budget: **5% of NAV per day**
- Per-edge CVaR budget:

$$CVaR\_budget^{(e)} = CVaR\_total \times \frac{K_{max}^{(e)} \cdot H^{(e)}}{\sum_j K_{max}^{(j)} \cdot H^{(j)}}$$

If any edge exceeds its CVaR budget → reduce position until compliant.

#### Marginal CVaR

Before adding a new position:

$$\Delta CVaR = CVaR(\text{portfolio} + \text{new}) - CVaR(\text{portfolio})$$

If $\Delta CVaR > 0.5 \times CVaR\_budget^{(e)}$ → REJECT new position.

#### Stress CVaR

Three stress scenarios:

| Scenario | Parameters | Hard Limit |
|----------|-----------|-----------|
| High-vol stress | Returns scaled by 1.5× | Stress CVaR₉₉ < 8% NAV |
| Liquidity crisis | Depth × 0.2 | Stress CVaR₉₉ < 8% NAV |
| Correlation breakdown | All correlations → 0.9 | Stress CVaR₉₉ < 8% NAV |

If any stress CVaR₉₉ exceeds 8% of NAV → de-risk immediately.

#### Computation Schedule

- Full recalculation: every 1 hour
- Incremental approximation: on each trade for marginal CVaR check
- Monte Carlo fallback: 10,000 paths if analytical estimate is unreliable (< 50 tail observations)

---

### §1.19 — Black Swan Kill-Switch System

Unified 5-level escalation ladder consolidating all risk circuit breakers.

#### Kill-Switch Levels

| Level | Name | Trigger | Action | Recovery |
|-------|------|---------|--------|----------|
| KS-0 | NORMAL | No triggers | Full operation | N/A |
| KS-1 | CAUTION | Any 1 standard trigger | Reduce new entries by 50%, tighten stops by 25% | Auto after 1h if trigger clears |
| KS-2 | DE-RISK | Any 2 simultaneous triggers | No new entries, reduce positions to 50% | Auto after 4h if all triggers clear |
| KS-3 | EMERGENCY | Any 3 triggers OR any critical trigger | Close all positions (orderly, 30-min TWAP) | Manual approval + 24h cool-down |
| KS-4 | HALT | System integrity threat | Immediate market orders to flatten, cancel all open orders, disable all engines | Manual-only restart with full audit |

#### Standard Triggers

| # | Trigger | Threshold |
|---|---------|-----------|
| 1 | Portfolio drawdown intraday | $\frac{NAV(t) - NAV(session\_start)}{NAV(session\_start)} < -0.05$ |
| 2 | Portfolio drawdown from peak | $\frac{NAV(t) - NAV_{peak}}{NAV_{peak}} < -0.10$ |
| 3 | CVaR breach | Realized loss > 2× CVaR₉₉ estimate |
| 4 | Correlation spike | Average pairwise correlation > 0.85 |
| 5 | Loss streak | ≥ 5 consecutive losing trades |
| 6 | Funding rate spike | $|FR| > 0.1\%$ per 8h for > 3 consecutive periods |
| 7 | Latency degradation | $L > 10 \times L_{tier}$ for > 60 seconds (§1.16) |
| 8 | Liquidity crisis | Liquidity Regime = CRISIS (§1.17) for > 30 minutes |

#### Critical Triggers (immediately escalate to KS-3)

| # | Trigger | Threshold |
|---|---------|-----------|
| 9 | Exchange API unresponsive | > 120 seconds |
| 10 | BTC flash crash | $|\Delta| > 15\%$ in 5 minutes |
| 11 | Portfolio drawdown from peak | > 15% |
| 12 | Data integrity failure | Gap > 60 seconds in critical feed |

#### Escalation Protocol

- Level transitions are MONOTONICALLY INCREASING during an event (no skip-back during active drawdown)
- De-escalation: ALL triggers for current level cleared AND cool-down period elapsed
- Cool-down periods: KS-1→KS-0: 1h, KS-2→KS-1: 4h, KS-3→KS-2: 24h, KS-4→KS-3: manual only
- All transitions logged: timestamp, trigger set, NAV snapshot, position snapshot

#### Position Closure Protocol (KS-3)

1. Close largest positions first (by notional)
2. Method: TWAP over 30 minutes with 2% ADV participation cap
3. If market impact > 1% during closure → pause 5 minutes, reassess
4. If exchange unavailable → queue orders, retry every 30 seconds

---

### §1.20 — Overfitting Protection (PBO / CSCV)

#### Probability of Backtest Overfitting (PBO)

Method: Combinatorially Symmetric Cross-Validation (CSCV).

1. Partition backtest period into $S$ equal sub-periods ($S = 16$, must be even)
2. Generate $\binom{S}{S/2}$ train/test splits (all symmetric combinations)
3. For each split: train on $S/2$ sub-periods, test on remaining $S/2$
4. Rank all parameter sets by in-sample performance

$$PBO = \frac{1}{\binom{S}{S/2}} \sum_{c} \mathbb{1}\left[rank_{OOS}(\theta^*_c) > \frac{N}{2}\right]$$

#### PBO Thresholds

| PBO | Interpretation | Action |
|-----|----------------|--------|
| < 0.20 | Low overfit probability | Edge approved |
| 0.20–0.40 | Moderate risk | Edge approved with 50% allocation cap |
| 0.40–0.60 | High risk | Requires additional OOS period before approval |
| > 0.60 | Likely overfit | Edge REJECTED |

#### Deflated Sharpe Ratio (DSR)

$$DSR = \Phi^{-1}\left(1 - \frac{N_{strategies}}{e^{\hat{SR}_{max}^2 / 2}}\right)$$

- If DSR < 0 after accounting for all strategy variants → REJECT
- $N_{strategies}$: cumulative count of ALL edge variants ever tested (monotonically increasing, never reset)

#### Monte Carlo Permutation Test

- Shuffle trade labels (win/loss) 10,000 times
- Compute Sharpe of each shuffled equity curve
- p-value = fraction of shuffled Sharpes ≥ observed Sharpe
- If p-value > 0.05 → REJECT (indistinguishable from noise)

#### Parameter Sensitivity Analysis

- For each tunable parameter: vary ±20% in 5% steps
- Compute Sharpe at each parameter value
- If Sharpe drops > 50% within ±10% variation → edge is fragile → REJECT
- Parameter sensitivity heatmap stored in audit log

#### Regime-Conditional Overfit Check

Run PBO separately for each price regime (BULL, BEAR, NEUTRAL):
- If PBO > 0.40 in ANY regime → cap allocation in that regime at 25%

#### Validation Gate Integration

- PBO computed AFTER walk-forward (§1.13 Stage 2) and BEFORE stress testing (§1.13 Stage 3)
- PBO rejection → edge does NOT proceed to stress testing
- All PBO results stored in edge audit record with full CSCV matrix

---

### §1.21 — Explicit NO-TRADE Conditions

23 conditions under which the system MUST NOT open new positions. Each condition is deterministic, measurable, and has zero ambiguity.

#### Category 1: Data Integrity

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-D01 | OHLCV feed gap | > 60s for trade stream, > 5 min for kline | Per asset |
| NT-D02 | Order book stale | Last L2 update > 10s ago | Per asset |
| NT-D03 | Trade/book timestamp divergence | $|\Delta t| > 5$ seconds | Per asset |
| NT-D04 | Price vs index deviation | $|price - index| / index > 2\%$ | Per asset |
| NT-D05 | Volume anomaly | 5-min volume < 5% of 30-day 5-min average | Per asset |

#### Category 2: Risk Limits

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-R01 | Kill-switch active | KS-level ≥ 2 (§1.19) | Portfolio |
| NT-R02 | Daily loss limit | Intraday PnL / NAV < −2% | Portfolio |
| NT-R03 | Open risk cap | Σ position risk / equity > 4% | Portfolio |
| NT-R04 | Position concentration | Any single position > 25% of NAV | Per asset |
| NT-R05 | CVaR budget exhausted | Portfolio CVaR₉₉ ≥ 5% of NAV (§1.18) | Portfolio |
| NT-R06 | Margin utilization | Used margin > 80% of available | Portfolio |

#### Category 3: Market Regime

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-M01 | Liquidity regime CRISIS | LIQ < 0.15 sustained > 30 min (§1.17) | Per asset |
| NT-M02 | Leverage regime EXTREME | OI/MC > 0.10 (§1.17) | Market-wide |
| NT-M03 | Regime transition in progress | Any dimension in hysteresis window | Per dimension |
| NT-M04 | Correlation breakdown | Mean pairwise correlation > 0.85 | Portfolio |

#### Category 4: Edge Health

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-E01 | Edge health score | EHS < 0.30 (§1.6) | Per edge |
| NT-E02 | Edge in DISABLED state | Self-healing FSM = DISABLED | Per edge |
| NT-E03 | Edge capacity RED | Utilization ≥ 80% of $K_{max}$ (§1.15) | Per edge |
| NT-E04 | No valid edge for asset | Zero edges with EHS > 0.50 | Per asset |

#### Category 5: Execution Quality

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-X01 | Latency breach | $L > 5 \times L_{tier}$ (§1.16) | Per tier |
| NT-X02 | Fill rate degradation | Last 10 orders fill rate < 50% | Per exchange |
| NT-X03 | Spread anomaly | Current spread > 3× 30-day median | Per asset |
| NT-X04 | Exchange maintenance | Scheduled or detected maintenance window | Per exchange |

#### Category 6: Temporal

| ID | Condition | Threshold | Scope |
|----|-----------|-----------|-------|
| NT-T01 | System startup | First 5 minutes after engine start (warm-up) | System |
| NT-T02 | Post-kill-switch cool-down | Within KS cool-down period (§1.19) | System |
| NT-T03 | High-impact event window | ±15 min around known macro event (FOMC, CPI, etc.) | Market-wide |

#### Enforcement

- Every order generation path checks ALL applicable NT conditions before emitting an order
- Evaluation order: Data → Risk → Regime → Edge → Execution → Temporal
- First failing check → REJECT with reason code (e.g., "NT-R02: daily loss limit −2.3%")
- All rejections logged: timestamp, condition ID, measured value, threshold, asset
- NO OVERRIDE mechanism — these are absolute, non-negotiable gates

---

### §1.22 — Adaptive Edge Evolution

Edges are not merely killed when underperforming. They are mutated, incubated, promoted, or replaced through a full evolutionary lifecycle.

#### Extended Edge Lifecycle FSM

```
CANDIDATE → INCUBATION → ACTIVE → WARNING → MUTATION → {ACTIVE | DISABLED}
                                                    ↘ REPLACEMENT → CANDIDATE (new)
```

#### Mutation Protocol

Triggered when edge enters WARNING state.

For edge $e$ with parameter vector $\theta_e \in \Theta_e$:

1. Generate $M = 5$ mutants: $\theta_e^{(m)} = \theta_e + \delta_m$ where $\delta_m \sim \mathcal{U}(-0.1\theta_e, +0.1\theta_e)$ (±10% perturbation)
2. Each mutant satisfies: $\theta_e^{(m)} \in \Theta_e$ (within declared bounds)
3. Evaluate: run walk-forward validation (§1.13 Stage 2) on each mutant using the SAME data windows
4. Selection: mutant with highest cost-adjusted expectancy AND PBO < 0.40 (§1.20) replaces the original
5. If NO mutant passes both criteria → edge transitions to DISABLED

#### Replacement Protocol

Triggered when edge is DISABLED for > 30 days.

- DISABLED edges moved to graveyard with full audit trail
- **Nursery pool**: candidate edges awaiting evaluation
  - Sources: manually submitted edge hypotheses, parameter sweep over existing edge families
  - Maximum nursery size: 20 candidates per edge family
- Candidate evaluation: passes ALL stages of §1.13 validation pipeline
- Promotion: expectancy > 1.5× family median AND PBO < 0.30 → promoted to INCUBATION
- **INCUBATION**: 14-day shadow execution (paper only), compared against family benchmark
  - Incubation Sharpe > 0.8× family median Sharpe → promoted to ACTIVE at 25% allocation
  - Incubation fails → returned to nursery with 60-day cooldown

#### A/B Testing Framework

When a mutant is ready for live deployment:

1. Run original (full allocation) and mutant (10% shadow allocation, paper) in parallel for 14 days
2. If mutant expectancy > original by > 15% with p < 0.10 (Welch's t-test) → swap
3. If no significant difference → keep original (no unnecessary churn)
4. Maximum 2 concurrent A/B tests per edge family

#### Evolution Rate Limits

| Constraint | Limit |
|-----------|-------|
| Mutation attempts per edge | Maximum 1 per 30-day window |
| Nursery promotions | Maximum 3 per quarter |
| Family-level parameter sweeps | Maximum 1 per quarter |

All mutations and replacements logged: timestamp, parameter delta, validation results, promotion/rejection reason.

---

### §1.23 — Feature / Data Drift Detection

#### Population Stability Index (PSI)

For each feature $f$ used by any active edge:

- Baseline distribution: feature values from training/validation period, binned into $B = 10$ equal-frequency bins
- Live distribution: rolling 30-day window, binned using the SAME bin edges

$$PSI_f = \sum_{i=1}^{B} (p_i^{live} - p_i^{base}) \cdot \ln\left(\frac{p_i^{live}}{p_i^{base}}\right)$$

Smoothing: replace zero-count bins with $\epsilon = 10^{-4}$.

| PSI | Interpretation | Action |
|-----|----------------|--------|
| < 0.10 | No significant drift | Continue |
| 0.10–0.25 | Moderate drift | Log warning, monitoring frequency → hourly |
| 0.25–0.50 | Significant drift | Reduce allocation for affected edges by 50%, trigger re-validation |
| > 0.50 | Severe drift | DISABLE all edges using feature $f$, require full re-validation |

#### Kolmogorov–Smirnov Test

Two-sample KS test between baseline (training) and live (30-day rolling):

$$D_n = \sup_x |F_{base}(x) - F_{live}(x)|$$

Reject null (no drift) if $D_n > c(\alpha) \cdot \sqrt{\frac{n_1 + n_2}{n_1 \cdot n_2}}$ at $\alpha = 0.01$.

**Joint decision logic** (PSI + KS):

| PSI | KS | Action |
|-----|----|--------|
| > 0.25 | Rejects | Edge disabled |
| > 0.25 | Does not reject | Warning only (PSI sensitive to binning artifacts) |
| < 0.25 | Rejects | Investigate manually (possible tail shift) |

#### Feature Monitoring Pipeline

- Baseline snapshot: stored at edge validation time (§1.13 Stage 2 completion)
  - Per-feature: empirical CDF, bin edges, mean, std, skewness, kurtosis
  - Stored immutably in edge audit record
- Live computation: every 4 hours for T2/T3 edges, every 1 hour for T0/T1 edges
- Features monitored: ALL features declared in any active edge's `feature_set`

#### Covariate Shift Index (multi-feature)

$$CSI = \frac{1}{|F|} \sum_{f \in F} PSI_f$$

If $CSI > 0.30$ → system-wide alert: edge family requires recalibration.

#### EWMA Drift Tracker (fast detection)

For each feature:

$$\mu_t = \alpha \cdot x_t + (1 - \alpha) \cdot \mu_{t-1} \quad (\alpha = 0.05)$$
$$\sigma^2_t = \alpha \cdot (x_t - \mu_t)^2 + (1 - \alpha) \cdot \sigma^2_{t-1}$$

Alert conditions:
- Mean shift: $|\mu_t - \mu_{base}| > 3\sigma_{base}$
- Variance explosion: $\sigma^2_t / \sigma^2_{base} > 2.0$

Provides fast day-to-day detection between slower PSI/KS batch checks.

---

### §1.24 — Online Learning (EWMA Execution Calibration)

Parameters are NOT learned by ML. They are calibrated from observed data using exponentially weighted moving averages. All updates are deterministic given the input stream.

#### Slippage Model

Replaces static base slippage constant.

Track realized slippage per asset tier:

$$s_t^{obs} = \frac{|fill\_price - signal\_price|}{signal\_price} \times 10^4 \text{ (bps)}$$

EWMA update:

$$\hat{s}_t = \alpha_s \cdot s_t^{obs} + (1 - \alpha_s) \cdot \hat{s}_{t-1} \quad (\alpha_s = 0.05)$$

- Bounds: $\hat{s}_t \in [5, 500]$ bps — clamp and flag anomaly if exceeded
- Initialization: $\hat{s}_0 = 20$ bps

#### Fill Rate Model

Track actual fill ratios per order size bucket:

| Bucket | % ADV Range |
|--------|------------|
| 1 | 0–1% |
| 2 | 1–2% |
| 3 | 2–5% |
| 4 | 5–10% |
| 5 | 10%+ |

EWMA per bucket: $\hat{r}_t^{(b)} = \alpha_r \cdot r_t^{obs} + (1 - \alpha_r) \cdot \hat{r}_{t-1}^{(b)} \quad (\alpha_r = 0.03)$

- Minimum observations before EWMA replaces default: 30 fills per bucket
- Bounds: $\hat{r}_t^{(b)} \in [0, 1]$

#### Commission Model

$$\hat{c}_t = 0.01 \cdot c_t^{obs} + 0.99 \cdot \hat{c}_{t-1}$$

Very slow α (commissions change rarely). Alert if $|\hat{c}_t - c_{configured}| > 0.5$ bps.

#### Edge Scoring Calibration

EWMA of ratio between predicted and realized edge return:

$$calibration_t^{(e)} = \alpha_c \cdot \frac{r_t^{real}}{r_t^{pred}} + (1 - \alpha_c) \cdot calibration_{t-1}^{(e)} \quad (\alpha_c = 0.02)$$

| Calibration | Interpretation | Action |
|-------------|---------------|--------|
| Drifts below 0.5 | Edge systematically over-predicting | Reduce allocation by calibration factor |
| Drifts above 2.0 | Edge under-predicting | Investigate (do NOT auto-increase) |

#### Regime Threshold Calibration

NOT adapted online — changing online would violate determinism for signal generation. Regime thresholds are re-calibrated quarterly in offline mode, validated via PBO (§1.20), then deployed as new constants.

#### Safety Constraints

- All EWMA states persisted to disk every cycle (crash recovery)
- All EWMA updates are deterministic given input stream order (replayable)
- Adaptation NEVER changes signal generation logic — only execution cost estimates and sizing
- Hard override: any EWMA estimate frozen by setting $\alpha = 0$ in config
- Audit: every parameter update logged with (timestamp, old_value, new_value, observation_count)

---

### §1.25 — Adversarial Execution

Full anti-detection execution framework to make the system's execution footprint statistically indistinguishable from noise.

#### Threat Model

- Adversary: HFT firms, exchange surveillance systems, other algorithmic traders
- Detection vectors: order timing patterns, order size clustering, venue preference, predictable entry/exit levels, correlated cross-asset order flow

#### Order Timing Randomization

- Base signal arrives at $t_{signal}$
- Execution delay: $\Delta t = \Delta t_{base} + \Delta t_{random}$
- $\Delta t_{base}$: tier-specific minimum latency (§1.16)
- $\Delta t_{random}$: deterministic pseudo-random delay from HMAC-SHA256(signal_id, secret_salt, timestamp)

| Edge Tier | $\Delta t_{random}$ Range |
|-----------|-------------------------|
| T0/T1 | [0, 50] ms |
| T2 | [0, 2000] ms |
| T3 | [0, 10000] ms |

Determinism preserved: same (signal_id, salt, timestamp) → same delay (replayable).

#### Order Size Obfuscation

$$Q_{exec} = Q_{target} \times (1 + \epsilon_Q)$$

$\epsilon_Q = \text{HMAC\_uniform}(order\_id, salt) \in [-0.05, +0.05]$ (±5% size jitter)

- Round to valid lot size AFTER jitter
- Constraint: $|Q_{exec} - Q_{target}| \leq 0.05 \cdot Q_{target}$

#### Iceberg/Parent-Child Splitting

If $Q_{target} > 1\%$ ADV:

- $N = \lceil Q_{target} / (0.5\% \cdot ADV) \rceil$, capped at $N \leq 10$
- Child sizes: $Q_i = Q_{target} / N + \epsilon_i$ with $\sum \epsilon_i = 0$ (zero-sum jitter)
- Inter-child delay: $\Delta t_{child} \in [500, 5000]$ ms (HMAC-derived)
- Visible size on book: only $Q_1$ — remaining children submitted as hidden/iceberg

#### Price Level Obfuscation

Submitted price: $P_{submit} = P_{target} \pm k \cdot tick\_size$

- $k \in \{0, 1, 2\}$ selected by HMAC: $k=0$ at 60%, $k=1$ at 30%, $k=2$ at 10% probability
- Direction: always IMPROVES fill probability (buy → higher, sell → lower)
- Constraint: if offset cost > 20% of expected return → $k = 0$ forced

#### Pattern Decorrelation

- Track sliding window of last 20 orders: timing, size, ticker, direction
- Compute autocorrelation of (time_deltas, size_sequence, direction_sequence)
- If autocorrelation > 0.3 at lag 1–5 → inject additional randomization on next order
- Metric logged but does NOT block execution (informational defense layer)

---

### §1.26 — Self-Liquidation Risk Control

Full margin/liquidation safety layer for leveraged perpetual futures positions.

#### Distance-to-Liquidation (DTL)

For a long position:

$$DTL_{long} = \frac{P_{mark} - P_{liq}}{P_{mark}}$$

For a short position:

$$DTL_{short} = \frac{P_{liq} - P_{mark}}{P_{mark}}$$

Liquidation price calculations:

$$P_{liq,long} = P_{entry} \times \left(1 - \frac{1}{leverage} + MM\_rate\right)$$

$$P_{liq,short} = P_{entry} \times \left(1 + \frac{1}{leverage} - MM\_rate\right)$$

$MM\_rate$: maintenance margin rate (exchange-specific, per-tier).

#### DTL Safety Bands

| DTL | State | Action |
|-----|-------|--------|
| > 15% | SAFE | Normal operation |
| 10%–15% | MONITOR | Log warning every 5 min, tighten stop to DTL × 0.6 |
| 5%–10% | DANGER | Reduce position by 50% immediately, no new entries for this asset |
| 3%–5% | CRITICAL | Close position entirely via market order, NO-TRADE for asset for 24h |
| < 3% | EMERGENCY | Immediate market close, KS-2 triggered (§1.19) |

#### Margin Utilization Model

$$MU = \frac{\sum_i |notional_i| \times IM\_rate_i}{wallet\_balance}$$

| MU Range | State | Action |
|----------|-------|--------|
| < 50% | Normal | Full operation |
| 50%–70% | Caution | No new entries |
| 70%–85% | Reduce | Close weakest positions |
| > 85% | Emergency | Flatten to MU < 50% |

#### Cross-Margin vs Isolated-Margin

- Default: ISOLATED margin mode (each position has independent liquidation price)
- Cross-margin allowed ONLY if: total portfolio leverage < 2× AND $DTL_{min} > 10\%$ across all positions
- If cross-margin and any position DTL drops below 7% → switch to isolated and close the endangered position

#### Funding Rate Liquidation Risk

- Cumulative funding cost: $F_{cum} = \sum_{k=1}^{N} f_k \times notional_k$
- $F_{cum} > 0.5\% \times notional$ for a single 8h period → high funding warning
- $F_{cum} > 2\%$ over expected holding period → position unprofitable after funding, reduce by 50%
- Funding rate flips direction → re-evaluate edge hypothesis

#### Stress Liquidation Simulation

Every 4 hours: simulate portfolio under {−10%, −15%, −20%, −25%} instant price shocks.

For each shock: compute positions liquidated, total liquidation loss, remaining equity.

If 20% shock liquidates > 30% of positions → portfolio is fragile → reduce overall leverage to max 1.5×.

Results stored in audit log with full position snapshot.

---

### §1.27 — Strategy Horizon Bucketing

Formal horizon separation framework with independent risk budgets.

#### Horizon Definitions

| Horizon | Holding Period | Data Resolution | Edge Families | Risk Budget |
|---------|---------------|-----------------|---------------|-------------|
| MICRO | < 1 hour | 1s to 1-min bars + L2 ticks | Microstructure (A), Cross-Exchange (E) | 20% of total |
| INTRADAY | 1h – 24h | 5-min to 1-hour bars | Funding (B), Liquidation (C), Volatility (D) | 40% of total |
| SWING | 1d – 14d | 4-hour to daily bars | Session (F), BTC Dominance (G), Meta combinations | 40% of total |

#### Horizon Isolation Rules

- Each horizon has an INDEPENDENT risk budget allocation
- Risk limits from §1.18 (CVaR) and §1.19 (kill-switch) applied PER-HORIZON before portfolio-level
- Drawdown breach in MICRO does NOT affect INTRADAY or SWING allocations (isolation)
- Exception: KS-3 and KS-4 override all horizons (portfolio-level emergency)

#### Horizon Assignment Protocol

- Each edge declares its horizon at definition time (immutable property of `EdgeDefinition`)
- Assignment criteria: > 75% of trades within the horizon's holding period range
- Multi-horizon edges → assign to the LONGEST horizon (conservative)
- Re-assignment: only during quarterly re-validation, never online

#### Per-Horizon Position Limits

| Parameter | MICRO | INTRADAY | SWING |
|-----------|-------|----------|-------|
| Max concurrent positions | 5 | 8 | 10 |
| Max single position (% NAV) | 3% | 8% | 15% |
| Max total exposure (% NAV) | 15% | 40% | 60% |
| Max turnover per day | 50 trades | 20 trades | 5 trades |
| Stop-loss from entry | 0.3% | 1.5% | 5% |

#### Horizon-Specific Execution

| Horizon | Order Type | Latency Tier | Splitting Threshold |
|---------|-----------|-------------|-------------------|
| MICRO | Limit orders only | T0 | > 0.2% ADV |
| INTRADAY | Limit preferred, market for exits | T1 | > 1% ADV |
| SWING | Market or limit | T2 | > 3% ADV |

#### Cross-Horizon Correlation

- Rolling 30-day correlation between horizon-level equity curves
- If correlation > 0.7 between any two horizons → horizons not truly independent
- Action: reduce allocation of the SMALLER horizon by 30% until decorrelation (< 0.5)

---

### §1.28 — Capital Growth Optimization (Kelly Criterion)

#### Single-Edge Kelly Fraction

$$f^*_e = \frac{p_e \cdot b_e - q_e}{b_e}$$

- $p_e$: win rate (rolling 100-trade window, EWMA-weighted, $\alpha = 0.05$)
- $q_e = 1 - p_e$
- $b_e$: average win / average loss ratio (same window)
- If $f^*_e \leq 0$ → NO ALLOCATION (edge has negative expectancy)

#### Fractional Kelly Scaling

| Condition | Fraction |
|-----------|----------|
| Default | Half-Kelly: $f_e = 0.5 \times f^*_e$ |
| < 100 trades in window | Quarter-Kelly: $f_e = 0.25 \times f^*_e$ |
| High estimation error ($\hat{\sigma}(f^*_e) > 0.3 \times f^*_e$) | Quarter-Kelly forced |

Estimation error: bootstrap 95% CI of $f^*_e$ from 1,000 resamples of trade history.

#### Portfolio-Level Kelly (multi-edge)

Correlation-adjusted portfolio Kelly:

$$\mathbf{f}^* = \Sigma^{-1} \boldsymbol{\mu}$$

- $\boldsymbol{\mu}$: vector of edge expected returns
- $\Sigma$: covariance matrix of edge returns (rolling 60-trade pairwise)
- Apply fractional scaling: $\mathbf{f} = 0.5 \times \mathbf{f}^*$
- Constraint: $\sum_e f_e \leq 0.04$ (total risk cap)
- If unconstrained sum exceeds cap → proportionally scale down all fractions

#### Log-Utility Verification

For the chosen allocation vector $\mathbf{f}$:

$$G(\mathbf{f}) = \mathbb{E}\left[\ln(1 + \mathbf{f}^T \mathbf{r})\right] \approx \mathbf{f}^T \boldsymbol{\mu} - \frac{1}{2} \mathbf{f}^T \Sigma \mathbf{f}$$

Verify $G(\mathbf{f}) > 0$. If not → reduce allocations until $G > 0$. This is the FINAL check before position sizing dispatch.

#### Integration with Risk Limits

- Kelly fraction provides the UPPER BOUND on per-edge allocation
- Drawdown bands (§1.19) provide multiplicative reduction
- Final size: $size_e = \min(f_e \times equity,\ drawdown\_mult \times max\_position)$
- Kelly NEVER overrides risk limits

#### Recalibration Schedule

| Component | Frequency |
|-----------|-----------|
| Per-edge Kelly | Every 10 trades OR daily (whichever first) |
| Portfolio Kelly | Hourly (requires covariance matrix update) |

All estimates logged: timestamp, edge_id, $f^*$, $f$, estimation_error, trade_count.

---

### §1.29 — Global System State Engine

The single source of truth for system operational state. Replaces all fragmented state machines with a unified 5-state health engine integrating risk, data, execution, and infrastructure signals.

#### System States

| State | ID | Description | Operational Impact |
|-------|----|-------------|-------------------|
| NORMAL | SS-0 | All subsystems healthy | Full operation, all edges and horizons active |
| DEGRADED | SS-1 | Partial subsystem impairment | Disable T0/T1 edges, reduce allocation by 30%, increase monitoring |
| DEFENSIVE | SS-2 | Multiple signals of stress | No new entries, tighten all stops by 50%, prepare for exit |
| CRISIS | SS-3 | Systemic threat detected | Orderly exit of all positions (TWAP 30-min), cancel all pending orders |
| HALT | SS-4 | System integrity compromised | Immediate flatten (market orders), disable all engines, manual restart required |

#### State Derivation (computed every 10 seconds)

Ten input signals, each produces severity score $s_i \in [0, 1]$:

| Signal | Source | Severity Formula |
|--------|--------|-----------------|
| S1: Kill-switch level | §1.19 | $s_1 = KS\_level / 4$ |
| S2: Drawdown severity | Live risk engine | $s_2 = \min(1, DD / 0.15)$ |
| S3: CVaR breach ratio | §1.18 | $s_3 = \min(1, CVaR_{99} / (0.05 \times NAV))$ |
| S4: Data feed health | §1.21 NT-D01..D05 | $s_4 = \text{fraction of active NT-D triggers}$ |
| S5: Execution health | §1.21 NT-X01..X04 | $s_5 = \text{fraction of active NT-X triggers}$ |
| S6: Liquidity regime | §1.17 | $s_6 = 1 - LIQ$ |
| S7: Feature drift | §1.23 | $s_7 = \min(1, CSI / 0.50)$ |
| S8: Correlation spike | §1.19 trigger #4 | $s_8 = \min(1, \bar{\rho}_{portfolio} / 0.85)$ |
| S9: Leverage exposure | §1.26 | $s_9 = \min(1, MU / 0.85)$ |
| S10: Latency health | §1.16 | $s_{10} = \max_{tier} \min(1, L / (5 \times L_{tier}))$ |

#### Composite System Health Score (SHS)

$$SHS = 1 - \sum_{i=1}^{10} w_i \cdot s_i$$

Weights:

| $w_1$ | $w_2$ | $w_3$ | $w_4$ | $w_5$ | $w_6$ | $w_7$ | $w_8$ | $w_9$ | $w_{10}$ |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|---------|
| 0.20 | 0.15 | 0.15 | 0.10 | 0.10 | 0.08 | 0.07 | 0.05 | 0.05 | 0.05 |

Sum = 1.0. SHS ∈ [0, 1] where 1 = perfectly healthy, 0 = maximum stress.

#### State Thresholds (with hysteresis)

| State | SHS Entry | SHS Exit (to lower severity) | Minimum Duration |
|-------|-----------|------------------------------|-----------------|
| NORMAL | SHS > 0.80 | N/A | 0 |
| DEGRADED | 0.60 < SHS ≤ 0.80 | SHS > 0.85 for 30 min | 10 min minimum |
| DEFENSIVE | 0.35 < SHS ≤ 0.60 | SHS > 0.70 for 2 hours | 30 min minimum |
| CRISIS | 0.15 < SHS ≤ 0.35 | SHS > 0.50 for 6 hours | 2 hours minimum |
| HALT | SHS ≤ 0.15 | Manual approval + SHS > 0.60 | Manual only |

#### Critical Override Rules

- ANY single $s_i = 1.0$ → immediate CRISIS regardless of SHS
- Kill-switch KS-4 → immediate HALT regardless of SHS
- Data feed complete loss ($S4 = 1.0$) → immediate DEFENSIVE minimum

#### State Transition Protocol

- **Escalation** (to higher severity): IMMEDIATE — no delay allowed
- **De-escalation** (to lower severity): requires exit threshold sustained for minimum duration (hysteresis)
- During transition: use the MORE SEVERE of the two states
- All transitions logged: timestamp, old_state, new_state, SHS, all $s_i$ values, trigger reason

#### Per-State Operational Rules

**NORMAL (SS-0)**: All edges active, all horizons active, full allocation, standard monitoring (1-minute interval).

**DEGRADED (SS-1)**: T0/T1 edges suspended, MICRO horizon paused, remaining allocation reduced by 30%, monitoring interval → 10 seconds, alert dispatched to operator.

**DEFENSIVE (SS-2)**: No new entries across all horizons. Existing positions: tighten trailing stops to 50% of normal width. Begin reducing MICRO and INTRADAY positions (TWAP). SWING positions held with tight stops. Monitoring → 5 seconds.

**CRISIS (SS-3)**: Exit ALL MICRO positions immediately (market orders). Exit INTRADAY positions via 15-min TWAP. SWING positions: close unless DTL > 15% and EHS > 0.70. Cancel ALL pending orders. Monitoring → 1 second.

**HALT (SS-4)**: Flatten ALL positions via market orders (no TWAP — urgency overrides impact). Cancel ALL orders. Disable ALL engines (data, edge, execution, risk recalculation stops). Persist full state snapshot. Require manual restart with audit sign-off.

#### System State Integration

- Kill-switch (§1.19) feeds into S1 signal — NOT a separate FSM
- Regime engine (§1.17) feeds into S6 signal
- CVaR (§1.18) feeds into S3 signal
- Feature drift (§1.23) feeds into S7 signal
- This engine is the **SINGLE SOURCE OF TRUTH** for system operational state

---

## §2 — Multi-Market Architecture

### §2.1 — Core Engine (Market-Agnostic)

The core engine provides shared infrastructure consumed by all market modules:

| Component | Scope | Description |
|-----------|-------|-------------|
| Risk Engine Core | Shared | CVaR computation (§1.18), kill-switch (§1.19), capital allocation (§1.28) |
| Portfolio State | Shared | NAV tracking, position inventory, margin accounting, P&L |
| System State Engine | Shared | Global SHS computation (§1.29), state transitions, operational rules |
| Audit Logger | Shared | Structured JSONL logging, every decision/order/fill/rejection/state-change |
| Backtest Framework | Shared | Walk-forward, stress testing, PBO/CSCV (§1.20) |
| Execution FSM | Shared | Order state machine: CREATED → SUBMITTED → PARTIAL → FILLED / REJECTED / CANCELLED |

### §2.2 — Market Module Protocol

Each market registers a `MarketConfig` dataclass:

```
@dataclass(frozen=True)
class MarketConfig:
    market_id: str                    # "bist" | "crypto"
    session_rules: SessionRules       # 24/7 vs scheduled
    tick_rules: TickRules             # per-instrument tick/lot tables
    currency: str                     # "TRY" | "USD"
    data_providers: list[str]         # registered provider keys
    execution_providers: list[str]    # registered adapter keys
    risk_overrides: dict[str, Any]    # market-specific risk parameters
    edge_families: list[str]          # which edge families apply
    regime_dimensions: list[str]      # which regime dimensions apply
```

### §2.3 — BIST Module

For BIST equities specification: see `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md`.

All PRDV3 invariants apply without modification. The BIST module is NOT replicated here.

BIST MarketConfig:
- `market_id`: "bist"
- `session_rules`: scheduled (09:40–18:10 TRT), tavan/taban, circuit breakers
- `currency`: "TRY"
- `edge_families`: as defined in PRDV3 §8
- `regime_dimensions`: ["price"]

### §2.4 — Crypto Module

Fully specified in this document. Crypto MarketConfig:
- `market_id`: "crypto"
- `session_rules`: 24/7, no market hours, no price limits
- `tick_rules`: per-exchange, per-instrument (from exchange API)
- `currency`: "USD"
- `data_providers`: ["binance_ws", "bybit_ws", "coingecko_rest"]
- `execution_providers`: ["binance_futures", "bybit_futures"]
- `edge_families`: ["A", "B", "C", "D", "E", "F", "G"] (§1.1)
- `regime_dimensions`: ["price", "funding", "leverage", "liquidity"] (§1.17)

### §2.5 — Module Isolation Rules

| Scope | Components |
|-------|-----------|
| **SHARED** | Risk engine core, portfolio state, audit logger, system state engine (§1.29), backtest framework, execution FSM |
| **MARKET-SPECIFIC** | Data providers, execution adapters, regime dimensions, tick/lot rules, session rules, edge definitions |
| **CROSS-MARKET** | Correlation monitoring, total NAV aggregation, cross-market risk budgets |

Cross-market risk: monitor rolling 60-day correlation between BIST and crypto portfolio equity curves. If correlation > 0.6 → reduce the smaller market's allocation by 20%.

---

## §3 — System Invariants

Full enumeration of system invariants with enforcement and violation response.

| ID | Statement | Enforcement | Violation Response |
|----|-----------|-------------|-------------------|
| INV-001 | Identical input stream produces identical output sequence | All signal logic is pure functions; PRNG seeded deterministically; no floating-point non-determinism | System halt + audit reconstruction |
| INV-002 | Missing or invalid data produces HOLD with explicit reason | Every data consumer validates before use; NT-D conditions gate orders | Reject with reason code |
| INV-003 | Risk limits override strategy signals unconditionally | Risk engine evaluates AFTER signal, BEFORE order submission | Signal discarded |
| INV-004 | All state is persisted, auditable, and recoverable | JSONL logging of every transition; crash recovery from persisted state | Reconstruct from audit log |
| INV-005 | AI MUST NOT generate orders, modify risk parameters, or execute | AI has read-only access; no write path to order engine | Integration rejected |
| INV-006 | No trade is preferable to a bad trade | Ambiguous signals → NO TRADE; unknown states → HOLD | Default = HOLD |
| INV-EDGE-001 | No edge without microstructure justification | Edge validation pipeline (§1.13) Stage 1 requires justification field | Edge rejected at validation |
| INV-EDGE-002 | No edge without invalidation conditions | EdgeDefinition requires non-empty `invalidation_conditions` | Edge rejected at definition |
| INV-EDGE-003 | No edge without crowding detection | Edge must declare applicable crowding mechanisms from §1.11 | Edge rejected at definition |
| INV-EDGE-004 | No edge without validation pipeline completion | Edge must pass all 5 stages of §1.13 | Edge blocked from live |
| INV-EXEC-001 | All orders pass NT conditions before submission | Order generation path checks all 23 NT conditions (§1.21) | Order rejected with NT code |
| INV-RISK-001 | System state engine (§1.29) is the single source of truth | All operational decisions reference SHS state | Override logged as violation |

---

## §4 — Data System

### §4.1 — WebSocket Architecture

#### Binance (Primary)

| Stream | Channel | Update Rate |
|--------|---------|-------------|
| Trades | `<symbol>@trade` | Real-time |
| L2 Depth | `<symbol>@depth@100ms` | 100ms |
| Kline | `<symbol>@kline_<interval>` | Per bar close |
| Liquidations | `<symbol>@forceOrder` | Real-time |
| Mark Price | `<symbol>@markPrice@1s` | 1 second |
| Funding Rate | Funding rate endpoint | Per settlement (8h) |
| Ticker | `<symbol>@ticker` | 1 second |

Intervals subscribed: 1m, 5m, 15m, 1h, 4h, 1d.

#### Bybit (Secondary)

Same stream categories for failover and cross-exchange analysis. Used as data source only unless Binance execution fails.

#### CoinGecko (Discovery)

REST API for market discovery: top coins by market cap, volume rankings, listing/delisting events. Polled every 1 hour.

### §4.2 — Order Book Management

1. **Initial snapshot**: REST API full order book on connection
2. **Delta updates**: WebSocket stream applies incremental changes
3. **Reconciliation**: full snapshot every 60 seconds, CRC32 checksum validation
4. **Stale detection**: NT-D02 triggers if last L2 update > 10 seconds ago
5. **Sequence validation**: per-stream sequence numbers with gap detection

If CRC32 mismatch → discard local book, re-snapshot, log anomaly.

### §4.3 — Trade Stream

- Dedup by `trade_id`
- Gap detection by sequence number
- OHLCV construction from raw trades
- Validation against exchange klines (cross-reference check)

### §4.4 — Data Halt Conditions

NT-D01 through NT-D05 (§1.21) define all data integrity halt conditions. Any active NT-D trigger prevents new orders for the affected asset.

### §4.5 — Recovery Protocol

1. Detect disconnection (heartbeat timeout: ping every 5s, timeout at 15s)
2. Reconnect with exponential backoff: 1s, 2s, 4s, 8s, max 30s
3. Request full snapshot on reconnection
4. Replay delta updates from snapshot timestamp
5. Validate state consistency (book CRC32, trade sequence continuity)
6. Resume normal operation

If recovery fails after 120 seconds → escalate to KS-3 (§1.19 critical trigger #9).

### §4.6 — Timeframe Hierarchy Enforcement

| Timeframe | Role | Enforcement |
|-----------|------|-------------|
| HTF (1H–4H) | Regime classification ONLY | State machine prevents trade trigger from HTF signals |
| MTF (5m–15m) | Setup validation ONLY | MTF confirms/denies setups; does not initiate trades |
| LTF (tick/orderbook) | Execution ONLY | LTF handles entry timing, order management |

Cross-timeframe trade triggers are blocked by the enforcement state machine. HTF regime determines what IS allowed; MTF validates conditions; LTF executes.

---

## §5 — Regime Engine

### §5.1 — Four-Dimensional Regime Model

The crypto regime engine operates across 4 orthogonal dimensions:

1. **Price Regime** (5-state): SUPER_BULL, BULL, NEUTRAL, BEAR, CHAOS — inherited from PRDV3 `market_regime_v2.py`
2. **Funding Regime** (5-state): as defined in §1.17 Dimension 1
3. **Leverage Regime** (4-state): as defined in §1.17 Dimension 2
4. **Liquidity Regime** (4-state): as defined in §1.17 Dimension 3

Total: 400 regime cells (§1.17).

### §5.2 — Mathematical Definitions

**Volatility**: $\sigma_r = \text{std}(r_{5min}, 24)$ — 24 five-minute returns (§1.5)

**Trend strength**: $TS = \frac{EMA_{12h} - EMA_{48h}}{ATR_{24h}}$ (§1.9)

**Liquidity composite**: $LIQ = 0.4 \times depth\_score + 0.3 \times spread\_score + 0.3 \times arrival\_score$ (§1.17)

### §5.3 — Transition Rules

- All dimensions have independent hysteresis periods (§1.17)
- During transition: use MORE CONSERVATIVE state
- Rapid oscillation (> 3 transitions in 24h) → force to most defensive state for 6 hours
- Regime state persisted every 10 seconds

### §5.4 — Per-Regime Effects

Each regime cell determines:
- Trade permission (edge activation matrix, §1.5)
- Position size multipliers (from §1.17 dimension impacts)
- Edge activation/deactivation (from §1.5 hard rules)
- Leverage limit (from §0.2: 3×/2×/1.5×/1×/0× by system state)

---

## §6 — Strategy Framework

### §6.1 — Allowed Signal Types

| Signal Type | Edge Family | Source |
|-------------|-------------|--------|
| Order flow imbalance | A | §1.2 composite microstructure signal |
| Funding rate mean-reversion | B | §1.1 Family B with §1.9 safety gates |
| Liquidation cascade exploitation | C | §1.3 liquidation intelligence system |
| Volatility regime transition | D | §1.1 Family D |
| Cross-exchange fragmentation | E | §1.4 cross-venue intelligence |
| Session handoff patterns | F | §1.1 Family F |
| BTC dominance regime shift | G | §1.1 Family G |

### §6.2 — Strategy Requirements

Every strategy:
1. Maps to one or more edge families (§1.1)
2. Has microstructure justification (INV-EDGE-001)
3. Has invalidation conditions (INV-EDGE-002)
4. Has crowding detection mechanisms (INV-EDGE-003)
5. Passes full validation pipeline (§1.13) including PBO (§1.20)

### §6.3 — Strategy Portfolio Management

- Meta Edge Layer (§1.7) controls allocation across active edges
- Maximum 5 concurrent active edges
- Correlation-aware exposure (§1.8): pairwise $\rho > 0.70$ → lower-Sharpe edge halved
- Dynamic enable/disable via EHS thresholds (§1.6)
- Evolutionary lifecycle (§1.22) for strategy replacement

### §6.4 — Strategy Isolation

No brute-force parameter search. All parameters declared in advance with bounds. Sensitivity analysis (§1.20) required for all tunable parameters. No strategy may access another strategy's internal state.

---

## §7 — Execution Engine

### §7.1 — Market Impact Model

Unified Almgren-Chriss framework as defined in §1.14:
- Temporary impact: $\Delta P_{temp}(t) = \eta \cdot \sigma_d \cdot (v/V_{ADV})^{\gamma} \cdot e^{-\lambda(T-t)}$
- Permanent impact: $\Delta P_{perm} = \alpha_I \cdot \text{sgn}(q) \cdot \sigma_d \cdot (|q|/V_{ADV})^{\delta}$
- Total cost: $TC(q) = s/2 + \Delta P_{temp} + \Delta P_{perm} + c_{commission} + c_{funding}$

### §7.2 — Order Book-Driven Entry

1. **Depth validation**: order size < 2% of visible depth at 5 bps from mid
2. **Spread validation**: spread < 3× 30-day median (NT-X03)
3. **Queue position model**: §1.2 A.2 determines maker vs taker decision
4. **CTR adjustment**: when CTR > 5.0, effective depth scaled by $\alpha_{CTR}$ (§1.2 A.4)

### §7.3 — Pre-Trade Slippage Estimation

EWMA-calibrated slippage estimate (§1.24) fed into total cost model (§1.14). If estimated TC > 50% of expected edge return → order blocked.

### §7.4 — Maker vs Taker Decision Tree

| Condition | Decision |
|-----------|----------|
| $QP < 0.30$ AND $R_{depletion} < 1.5\bar{R}$ | Limit order (maker) |
| $QP > 0.70$ OR $R_{depletion} > 2\bar{R}$ | Market order (taker) |
| Urgency (T0/T1 signal decay) | Market order (taker) |
| Otherwise | Limit order at best bid/ask |

### §7.5 — Latency Budget

Per-tier budgets enforced (§1.16). Degradation ladder applied. Co-location required for T0 edges.

### §7.6 — Adversarial Execution

Full implementation of §1.25: timing randomization, size obfuscation, iceberg splitting, price obfuscation, pattern decorrelation.

### §7.7 — Order State Machine

```
CREATED → SUBMITTED → PARTIAL → FILLED
                   ↘ REJECTED
       SUBMITTED → CANCELLED
```

- Partial fill: accept partial, cancel remainder after timeout (MICRO: 30s, INTRA: 5min, SWING: 30min)
- Cancel/replace: if price moves > 0.5× expected return before fill → cancel and reassess

### §7.8 — Execution Schedule

For orders > 5% ADV:
- Split into N child orders
- TWAP/VWAP schedule per §1.14
- Maximum participation rate: 2% of real-time volume
- Inter-child delay: HMAC-derived (§1.25)

---

## §8 — Risk Engine

### §8.1 — Per-Trade Risk

- Kelly-bounded (§1.28): half-Kelly default, quarter-Kelly under uncertainty
- Drawdown-scaled: multiplicative reduction per §1.19 KS levels
- Regime-scaled: per §1.17 dimension impacts

### §8.2 — Portfolio Risk Limits

| Parameter | Hard Limit |
|-----------|-----------|
| Daily loss limit | 2% of NAV (NT-R02) |
| Maximum drawdown from peak | 15% → KS-3 (§1.19 critical trigger #11) |
| Portfolio CVaR₉₉ | 5% of NAV per day (§1.18) |
| Total open risk | 4% of equity (NT-R03) |
| Single position concentration | 25% of NAV (NT-R04) |
| Margin utilization | 80% → no new entries (NT-R06) |

### §8.3 — Stop Logic

| Stop Type | Specification |
|-----------|--------------|
| Initial stop (per-horizon) | MICRO: 0.3%, INTRA: 1.5%, SWING: 5% (§1.27) |
| Trailing stop | Tightened per system state: NORMAL ×1.0, DEGRADED ×0.85, DEFENSIVE ×0.50 |
| Volatility-based | $1.5 \times ATR_{4h}$ from entry |
| Time-decay (funding trades) | Tighten 20% every 8h (§1.9) |

### §8.4 — Liquidation Risk

Full §1.26 implementation:
- DTL monitoring with 5 safety bands
- Margin utilization 4-tier model
- Cross/isolated margin rules
- Funding rate cumulative cost tracking
- Stress liquidation simulation every 4 hours

### §8.5 — Kill-Switch System

Full §1.19 implementation:
- 5-level escalation ladder (KS-0 through KS-4)
- 8 standard + 4 critical triggers
- Monotonic escalation during events
- Cool-down periods enforced
- Position closure protocol for KS-3

### §8.6 — Unknown State Handling

Any data gap, unrecognizable state, or unclassifiable condition → HOLD (INV-002). No trade proceeds when the system cannot fully characterize the market state.

---

## §9 — Capital Allocation Engine

### §9.1 — Kelly Criterion

Full §1.28 implementation:
- Single-edge: $f^* = (pb - q) / b$
- Portfolio-level: $\mathbf{f}^* = \Sigma^{-1}\boldsymbol{\mu}$
- Half-Kelly default, quarter-Kelly under uncertainty
- Log-utility verification: $G(\mathbf{f}) > 0$ required

### §9.2 — Drawdown-Based De-risking

Kill-switch levels (§1.19) impose multiplicative reductions:

| KS Level | Allocation Multiplier |
|----------|---------------------|
| KS-0 | 1.0 |
| KS-1 | 0.50 |
| KS-2 | 0.0 (no new entries) |
| KS-3+ | Closing positions |

### §9.3 — Regime-Based Scaling

Per §1.17 dimension impacts:
- EXTREME_LEVERAGE → reduce by 70%
- CRISIS liquidity → halve maximum participation rate
- Price regime CRISIS → zero allocation

### §9.4 — Horizon Risk Budget

Per §1.27: MICRO 20%, INTRADAY 40%, SWING 40%. Independent budgets with isolation.

### §9.5 — CVaR Risk Budget

Per §1.18: 5% daily CVaR₉₉ total. Allocated proportionally to edge capacity × health score. Marginal CVaR gate on every new position.

### §9.6 — Edge Capacity Constraints

Per §1.15: Green/Yellow/Red tiers. Real-time tracking. Tier crossing triggers immediate adjustment.

---

## §10 — Performance Governance

### §10.1 — Rolling Performance Windows

Metrics computed on 7-day, 30-day, and 90-day rolling windows:
- Sharpe ratio (annualized)
- Hit rate
- Average win / average loss
- Maximum drawdown
- Profit factor
- Trade count

### §10.2 — Edge Health Monitoring

EHS (§1.6) computed continuously for all active edges. Four-component score with state machine: ACTIVE → WARNING → DISABLED → QUARANTINE.

### §10.3 — Decay Detection

| Signal | Detection | Action |
|--------|-----------|--------|
| Sharpe degradation | $\text{Sharpe}_{30d} < 0.5 \times \text{Sharpe}_{90d}$ | DECAY_ALERT → de-weight by 0.5× |
| Hit rate decline | $HR_{30d} < HR_{90d} - 0.10$ | HIT_RATE_ALERT → increase monitoring |
| Drawdown acceleration | $DD > DD_{max,edge}$ | DISABLED transition |

### §10.4 — Feature Drift Detection

Full §1.23 implementation:
- PSI with 10-bin equal-frequency binning
- KS-test supplementary validation
- EWMA fast tracker ($\alpha = 0.05$) between batch checks
- CSI > 0.30 → system-wide recalibration alert

### §10.5 — De-weighting

EHS-based allocation curve (§1.6). Boost at EHS > 0.80 + Sharpe > 1.5. De-weight on DECAY_ALERT. Disable at EHS < 0.30.

### §10.6 — Edge Evolution

Full §1.22 implementation:
- Mutation when WARNING (5 mutants, ±10% perturbation)
- A/B testing framework (14-day parallel run)
- Nursery pool (20 candidates/family)
- Rate limits enforced

### §10.7 — Online Learning Calibration

Full §1.24 implementation:
- Slippage EWMA ($\alpha = 0.05$, bounds [5, 500] bps)
- Fill rate EWMA per bucket ($\alpha = 0.03$)
- Commission tracking ($\alpha = 0.01$)
- Edge scoring calibration ($\alpha = 0.02$)

### §10.8 — Overfitting Re-validation

PBO/CSCV (§1.20) re-run quarterly on all active edges. If PBO degrades above 0.40 → allocation capped. If above 0.60 → edge disabled pending re-development.

---

## §11 — Failure Taxonomy

Every failure mode: detection, response, recovery, and recovery time objective (RTO).

| ID | Failure | Detection | Response | Recovery | RTO |
|----|---------|-----------|----------|----------|-----|
| F-001 | WebSocket disconnection | Heartbeat timeout (15s) | Reconnect protocol (§4.5) | Exponential backoff 1s/2s/4s/8s max 30s | 30s |
| F-002 | Exchange API outage | 120s unresponsive | Switch to secondary; if both fail → KS-3 | Queue orders, retry 30s intervals | 5 min |
| F-003 | Order rejection | Exchange rejection message | Log reason, retry once | If persistent → disable edge | 1s |
| F-004 | Latency spike | $L > 2 \times L_{tier}$ | Degradation ladder (§1.16) | Auto-recover when latency normalizes | 60s |
| F-005 | State desync | Reconciliation mismatch | Query exchange, resolve discrepancy | Re-snapshot positions | 2 min |
| F-006 | Data corruption | CRC32 mismatch, gap detection | Halt affected asset (NT-D triggers) | Re-snapshot and replay | 1 min |
| F-007 | Extreme volatility | Regime engine detects | System state adjusts (§1.29) | Auto via regime transition | Regime-dependent |
| F-008 | Funding rate spike | $|FR| > 0.1\%/8h$ for 3 periods | §1.9 safety gates, §1.26 funding risk | Auto when funding normalizes | 24h |
| F-009 | Liquidation cascade | §1.3 cascade FSM = BUILDING | No entry during BUILDING/ACTIVE | Wait for CASCADE_COMPLETE | Event-dependent |
| F-010 | Margin call | DTL < 3% (§1.26 EMERGENCY) | Immediate market close, KS-2 | Manual review | 1s (close) |
| F-011 | Feature drift | PSI > 0.25 (§1.23) | Reduce/disable affected edges | Full re-validation | Hours |
| F-012 | System state HALT (SS-4) | SHS ≤ 0.15 (§1.29) | Flatten all, disable all engines | Manual restart with audit | Manual |

---

## §12 — Backtest & Simulation

### §12.1 — Realistic Simulation Requirements

| Component | Implementation |
|-----------|---------------|
| Market impact | Almgren-Chriss model (§1.14): temporary + permanent |
| Slippage | EWMA-calibrated (§1.24) or static 20 bps default |
| Latency | Per-tier simulation (§1.16) |
| Partial fills | Fill ratio model per ADV bucket (§1.24) or linear interpolation default |
| Order rejection | Based on spread/depth conditions that would trigger NT-X |
| Spread dynamics | Time-varying spread from historical L2 data |
| Funding rate costs | Actual historical funding stream applied |

### §12.2 — Prohibited Assumptions

The following assumptions are FORBIDDEN in any backtest:

1. No same-bar execution (next-bar minimum)
2. No guaranteed fills (fill ratio model required)
3. No zero-slippage (minimum 5 bps)
4. No zero-latency (minimum tier latency applied)
5. No infinite depth (order size capped at 2% visible depth)
6. No static spread (time-varying spread required)

### §12.3 — Walk-Forward Framework

As specified in §1.13 Stage 2:
- Minimum 3 OOS windows (each ≥ 3 months)
- Sharpe retention ≥ 50%
- Hit rate retention ≥ −10pp
- Positive expectancy in ≥ 2/3 windows

### §12.4 — PBO/CSCV

As specified in §1.20:
- $S = 16$ sub-periods
- All $\binom{16}{8} = 12,870$ symmetric splits
- PBO < 0.40 required for approval

### §12.5 — Stress Scenarios

As specified in §1.13 Stage 3:
- High-vol: returns × 1.5, slippage × 2.0
- Low-liquidity: depth × 0.2, slippage × 3.0
- Flash crash: 10% gap, 5-min recovery, massive liquidation

---

## §13 — AI & Agent System

### §13.1 — AI Roles

| Role | Capability | Constraint |
|------|-----------|-----------|
| Research Agent | Literature review, hypothesis generation | Suggestions only — no execution |
| Post-Trade Analyst | Trade review, pattern identification | Read-only access to trade history |
| Feature Discovery Agent | Feature candidate generation | Candidates enter nursery pool (§1.22) |

### §13.2 — Hard Constraint (INV-005)

**AI MUST NOT execute trades, generate orders, or modify risk parameters.**

AI has read-only access to:
- Historical market data
- Trade history and audit logs
- Edge performance metrics
- System state (read-only)

AI has NO write access to:
- Order engine
- Risk parameters
- Edge definitions (can suggest, not modify)
- System state

### §13.3 — Agent Architecture

- JSON-serializable request/response contracts
- Versioned interfaces (semantic versioning)
- Deterministic fallback: system operates identically if all AI agents are disabled
- Cost tracking: per-agent token usage budgets
- All agent suggestions pass through deterministic validation gate before system integration

---

## §14 — Operational System

### §14.1 — Logging

- Format: structured JSONL
- Every event logged: decision, order, fill, rejection, state-change, regime transition, edge state transition
- Fields: timestamp (μs), event_type, source, payload, context_snapshot
- Retention: 1 year minimum, compressed after 30 days

### §14.2 — Reconciliation

- Exchange positions vs internal state: every 60 seconds
- Method: query exchange REST API, compare against portfolio state
- Mismatch handling: log discrepancy, use exchange as source of truth, investigate root cause
- If mismatch > 1% of NAV → alert + investigation

### §14.3 — Monitoring Dashboards

| Dashboard | Key Metrics |
|-----------|------------|
| System State (§1.29) | SHS, all 10 signals, current state, state history |
| Edge Health | Per-edge EHS, activation status, allocation, PnL |
| Risk Metrics | NAV, drawdown, CVaR, margin utilization, KS level |
| Data Health | Per-stream latency, gap count, stale count, reconnect count |
| Execution Quality | Fill rate, slippage (actual vs estimated), latency distribution |

### §14.4 — Alerting

| Level | Criteria | Action |
|-------|----------|--------|
| INFO | Normal operational events | Log only |
| WARNING | EHS decline, moderate drift, latency spike | Dashboard highlight |
| CRITICAL | KS-1+, significant drift, execution degradation | Operator notification |
| EMERGENCY | KS-3+, system integrity | Immediate operator page |

### §14.5 — State Recovery

Idempotent restart protocol:
1. Persist all state to disk every cycle
2. On crash: reload state from persisted snapshot
3. Validate: check portfolio vs exchange, check timestamps
4. Reconcile: resolve any discrepancies
5. Resume: restart engines in dependency order (data → regime → edge → execution → risk)

---

## §15 — Deployment Architecture

### §15.1 — Container Architecture

Services (Docker Compose):

| Service | Responsibility |
|---------|---------------|
| data-feed | WebSocket management, book/trade aggregation |
| edge-engine | Signal generation, edge health, meta layer |
| execution | Order management, adversarial execution |
| risk | CVaR, kill-switch, position sizing, margin monitoring |
| state-engine | SHS computation, system state transitions |
| monitoring | Dashboard serving, alerting, reconciliation |
| gateway | API gateway, authentication |

### §15.2 — Co-location

- Primary: AWS ap-northeast-1 (Tokyo) or ap-southeast-1 (Singapore) — nearest Binance matching engine
- Data feed: co-located WebSocket receivers
- Execution: same region as data feed for minimum internal latency
- Fallback: standard cloud (T0 edges disabled)

### §15.3 — Network

- Private VPC for all inter-service communication
- Dedicated WebSocket connections to exchanges (no shared proxy)
- TLS 1.3 for all external connections

### §15.4 — Failover & Redundancy

- Dual data feeds: Binance primary, Bybit failover
- Dual execution paths: primary and standby
- Shared state: PostgreSQL (persistent) + Redis (low-latency cache)
- Active-passive failover with < 30s switchover

---

## §16 — Implementation Roadmap

### Phase 1: Data Pipeline (Months 1–3)

**Milestone**: All crypto data streams operational and validated.

- Binance/Bybit WebSocket integration
- Order book management with CRC32 validation
- Trade stream with gap detection
- OHLCV construction and cross-validation
- Data halt conditions (NT-D01–D05)
- Recovery protocol implementation

**Gate**: All data streams pass 7-day stability test with < 0.1% gap rate.

### Phase 2: Edge Engine (Months 3–5)

**Milestone**: All 7 edge families implemented and backtested.

- Edge families A–G implementation (§1.1)
- Microstructure depth model (§1.2)
- Liquidation intelligence (§1.3)
- Cross-exchange intelligence (§1.4)
- Activation matrix (§1.5)
- EHS and state machine (§1.6)
- Meta edge layer (§1.7)

**Gate**: All edges pass §1.13 Stages 1–3 with PBO < 0.40.

### Phase 3: Execution & Risk (Months 5–7)

**Milestone**: Execution and risk engines fully operational.

- Market impact model (§1.14)
- Adversarial execution (§1.25)
- Kill-switch system (§1.19)
- CVaR engine (§1.18)
- Self-liquidation risk (§1.26)
- Kelly sizing (§1.28)
- System state engine (§1.29)

**Gate**: Risk engine passes all stress scenarios. Kill-switch tested under simulation.

### Phase 4: Paper Trading (Months 7–9)

**Milestone**: System running in paper mode with full monitoring.

- §1.13 Stage 4: 30-day paper trading all edges
- Online learning calibration (§1.24)
- Feature drift detection (§1.23)
- Monitoring dashboards operational
- Reconciliation running
- Performance governance active

**Gate**: Paper Sharpe ≥ 50% of backtest Sharpe for each active edge.

### Phase 5: Live Scaled Entry (Months 9–11)

**Milestone**: System trading live with progressive capital deployment.

- §1.13 Stage 5: 10% → 25% → 50% → 100% allocation
- A/B testing framework (§1.22) active
- Full operational monitoring
- Alert escalation tested

**Gate**: Each scaling step requires metrics to hold for minimum period.

### Phase 6: Full Production (Months 11–12)

**Milestone**: System at full production capacity with all features active.

- All edges at full allocation
- Adaptive evolution active (§1.22)
- Cross-market correlation monitoring
- Quarterly re-validation cycle established

**Gate**: All monitoring, alerting, and recovery procedures documented and tested.

---

## §17 — Performance Targets

### §17.1 — Regime-Conditional Return Bands

| Regime | Monthly Return Target | Sharpe Target |
|--------|---------------------|---------------|
| BULL | 10–20% | 2.5 |
| NEUTRAL | 3–8% | 1.5 |
| BEAR | 0–5% (capital preservation) | 1.0 |
| CRISIS | 0% (no trading) | N/A |

### §17.2 — Risk-Adjusted Targets

| Metric | Target |
|--------|--------|
| Sharpe Ratio | > 2.0 |
| Sortino Ratio | > 3.0 |
| Maximum Drawdown | < 15% |
| Calmar Ratio | > 1.5 |
| Win Rate | > 55% |

### §17.3 — Sustainability

- Targets validated across walk-forward windows (§1.13 Stage 2)
- PBO < 0.40 confirms targets are not artifacts of overfitting (§1.20)
- Regime-conditional targets verified independently per regime period

### §17.4 — Disclaimer

Performance targets are aspirational engineering objectives, not guarantees. Actual performance depends on market conditions, edge persistence, execution quality, and regime dynamics. No trading system guarantees returns. Capital preservation (INV-006) takes absolute precedence over return targets.

---

## Appendix A — Cross-Reference Index

| Section | Key Dependencies |
|---------|-----------------|
| §1.1 Alpha Taxonomy | Foundational — no dependencies |
| §1.2 Microstructure | §1.1 Family A |
| §1.3 Liquidation | §1.1 Family C |
| §1.4 Cross-Exchange | §1.1 Family E |
| §1.5 Activation Matrix | §1.1–§1.4 |
| §1.6 Edge Decay | §1.5 |
| §1.7 Meta Edge Layer | §1.5, §1.6 |
| §1.8 Interaction Model | §1.6, §1.7 |
| §1.9 Funding Safety | §1.1 Family B, §1.2, §1.3 |
| §1.11 Crowding | §1.1 all families |
| §1.12 Execution Quality | §1.2, §1.5 |
| §1.13 Validation Pipeline | §1.12, §1.14 |
| §1.14 Market Impact | §1.5, §1.15 |
| §1.15 Edge Capacity | §1.14 |
| §1.16 Latency | §1.1 (tier assignment) |
| §1.17 Regime Decomposition | §1.5 |
| §1.18 CVaR | §1.15, §1.17 |
| §1.19 Kill-Switch | §1.16, §1.17, §1.18 |
| §1.20 Overfitting | §1.13 |
| §1.21 NO-TRADE | §1.16, §1.17, §1.18, §1.19 |
| §1.22 Adaptive Evolution | §1.6, §1.13, §1.20 |
| §1.23 Feature Drift | §1.13 |
| §1.24 Online Learning | §1.14 |
| §1.25 Adversarial Execution | §1.16 |
| §1.26 Self-Liquidation | §1.19 |
| §1.27 Horizon Bucketing | §1.1, §1.16 |
| §1.28 Kelly Criterion | §1.6, §1.19 |
| §1.29 System State | §1.16, §1.17, §1.18, §1.19, §1.21, §1.23, §1.26 |
| §2 Architecture | §1 all |
| §4 Data System | §1.21 NT-D conditions |
| §5 Regime Engine | §1.17 |
| §6 Strategy | §1.1, §1.7, §1.13, §1.22 |
| §7 Execution | §1.14, §1.16, §1.25 |
| §8 Risk | §1.18, §1.19, §1.26, §1.28 |
| §9 Capital | §1.15, §1.27, §1.28 |
| §10 Performance | §1.6, §1.22, §1.23, §1.24 |
| §11 Failure | §1.3, §1.9, §1.16, §1.19, §1.23, §1.26, §1.29 |

---

*End of PRDV4 — Multi-Market Algorithmic Trading System PRD*

