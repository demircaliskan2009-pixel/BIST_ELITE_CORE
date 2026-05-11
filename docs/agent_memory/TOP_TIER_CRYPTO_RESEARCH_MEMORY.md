# Top-Tier Crypto Quantitative System — Research Memory

This document encodes permanent architecture doctrine for the crypto quantitative
trading engine. All agent runs, skills, and implementation decisions must consult
this file. If any local instruction or prompt conflicts, this memory wins except
where `docs/PRDV4_MULTI_MARKET_CRYPTO.md` (the architecture constitution)
explicitly overrides.

---

## 1. Execution Realism First

Paper PnL is **not trustworthy** unless calibrated against:

- Realistic fees (maker + taker, per venue, tier-aware).
- Partial fills — not all limit orders fill. Fill ratio < 1.0 is the norm.
- Book-walk slippage — large orders consume multiple levels.
- Latency bands — decision-to-fill delay differs between paper and live.
- Maker non-fill risk — passive orders risk adverse selection on non-fill.
- Post-fill markout — positive markout ≠ alpha; negative markout = leak.
- Venue outages / maintenance windows — fills cannot happen.
- Liquidation / mark-price semantics — funding, ADL, insurance fund.
- Stress regimes — all cost assumptions must be re-evaluated.

**Rule:** Treat any execution metric computed from paper mode as an upper bound
on real performance until calibrated against live fills.

---

## 2. TCA Requirements

Every order must produce a Transaction Cost Analysis record containing:

| Field | Description |
|-------|-------------|
| `decision_price` | Mid-price at signal generation time |
| `arrival_price` | Mid-price when order reaches venue |
| `execution_price` | Actual (or simulated) fill price |
| `implementation_shortfall_bps` | `(exec_price - decision_price) / decision_price × 10000` (signed) |
| `arrival_shortfall_bps` | `(exec_price - arrival_price) / arrival_price × 10000` (signed) |
| `expected_slippage_bps` | Pre-trade model estimate |
| `realized_slippage_bps` | Actual cost from mid at fill time |
| `slippage_surprise_bps` | `realized - expected` |
| `spread_cost_bps` | Half-spread component |
| `impact_cost_bps` | Market impact component |
| `fee_cost_bps` | Exchange fee in bps |
| `funding_cost_bps` | Funding rate cost pro-rated to hold period |
| `fill_ratio` | Filled quantity / requested quantity |
| `is_maker` | True if fill was passive (limit) |
| `markout_1s_bps` | Mid-price change 1s after fill |
| `markout_5s_bps` | Mid-price change 5s after fill |
| `markout_30s_bps` | Mid-price change 30s after fill |
| `markout_300s_bps` | Mid-price change 5m after fill |

**Missing data rule:** If any markout horizon cannot be computed (no subsequent
mid-price), the field must be `None` — never zero, never estimated.

---

## 3. Queue / Fill / Markout Realism

### Queue Position

- Limit orders do not fill at TOB instantly. Queue position determines fill
  probability.
- Without exchange-reported queue data, assume worst-case queue position
  (back of queue at submission time).
- Fill probability model: `P(fill) = f(queue_depth_ahead, trade_flow_rate, time_horizon)`.
- Paper mode must not assume 100% fill on limit orders.

### Fill Simulation

- Taker fills: immediate but incur spread + impact.
- Maker fills: delayed, subject to queue, subject to adverse selection.
- Partial fills are normal. The system must handle partial fill accounting
  cleanly — no rounding tricks, no silent top-ups.

### Markout Measurement

- Markout = signed mid-price change after fill.
- Positive markout (for the fill direction) = good execution.
- Negative markout = adverse selection; the fill was toxic.
- Markout must be measured at multiple horizons: 1s, 5s, 30s, 300s minimum.
- Markout is the primary feedback signal for execution quality.
- Aggregate markout by: venue, symbol, time-of-day, regime, maker/taker.

---

## 4. Maker vs Taker Switching Doctrine

- **Taker** = immediate fill, certainty, but higher cost (spread + fee).
- **Maker** = lower cost, but fill uncertainty + queue risk + adverse selection.
- Decision framework:
  - If signal alpha > taker cost → taker is justified.
  - If signal alpha < taker cost but > maker cost → attempt maker.
  - If signal alpha < maker cost → do not trade.
  - If urgency is high (stop-loss, risk reduction) → always taker.
  - If markout history shows adverse selection on maker fills → reduce maker.

**Rule:** Never assume maker fills are free. Account for non-fill opportunity
cost and adverse selection in all maker strategies.

---

## 5. Dynamic Venue Scoring Doctrine

Each venue-symbol pair must carry a composite score reflecting:

| Component | Weight | Source |
|-----------|--------|--------|
| Execution quality (markout, slippage) | High | TCA records |
| Spread + depth quality | High | Book snapshots |
| Fee structure (maker/taker tiers) | Medium | Config + API |
| Funding rate fairness | Medium | Funding snapshots |
| Reliability (uptime, outage history) | High | Monitoring |
| Liquidation design (mark-price, ADL, insurance) | Medium | Exchange docs |
| Manipulation risk prior | Low-Medium | Anomaly detection |
| Regulatory / operational availability | Binary | Config |

**Score states:**

- `PREFERRED` — actively route orders here.
- `AVAILABLE` — usable but not preferred.
- `DEGRADED` — usable with caution, increased slippage assumptions.
- `BLOCKED` — do not route. May be temporary (outage) or permanent (regulatory).
- `UNKNOWN` — insufficient data; treat as DEGRADED.

**Rule:** Default to `UNKNOWN` for any venue-symbol without sufficient history.
Never default to PREFERRED.

---

## 6. Routing by Expected All-In Cost

Order routing must NOT be based on:
- Displayed best price alone
- Reported volume alone
- Lowest nominal spread alone

Order routing MUST be based on:
- Expected all-in cost = spread + impact + fees + funding + expected markout
- Venue score (reliability, design risk)
- Current venue health state

**Formula:**
```
expected_cost_bps = (
    half_spread_bps
    + expected_impact_bps(size, depth)
    + fee_bps(maker_or_taker, tier)
    + funding_rate_bps(hold_period)
    + venue_risk_adjustment_bps(score)
)
```

Route to the venue with lowest expected_cost_bps among non-BLOCKED venues.
If all venues are BLOCKED → NO TRADE (fail-closed).

---

## 7. Venue Integrity as First-Class State

### Outage / Maintenance

- Venue outage = no routing, no assumptions about fills.
- Maintenance windows must be tracked and anticipated.
- During outage, positions on that venue cannot be adjusted — risk engine must
  account for this.

### ADL (Auto-Deleveraging)

- Venues with aggressive ADL policies carry higher tail risk.
- ADL exposure must be tracked as a venue-specific risk factor.
- During high ADL probability: reduce position or hedge.

### Liquidation / Mark-Price

- Mark price ≠ last price. Liquidation is based on mark price.
- Venues differ in mark-price calculation (index price weighting, EMA
  smoothing). This affects liquidation distance.
- Funding rate = `(mark_price - index_price)` component. High funding =
  directional crowd.

### Insurance Fund

- Venues with depleted insurance funds have higher socialized-loss risk.
- Monitor insurance fund as a venue health signal.

---

## 8. Paper-Live Calibration Doctrine

- Paper fills assume instant, full fills at computed prices.
- Live fills involve latency, partial fills, queue position, and rejection.
- Calibration process:
  1. Run paper and live in parallel on same signals.
  2. Measure per-order TCA difference.
  3. Adjust paper slippage model to match live realized costs.
  4. Re-evaluate alpha estimates after calibration.
- **Calibration frequency:** After every 100 live fills or weekly, whichever
  comes first.
- **Calibration threshold:** If paper-live cost gap > 5 bps systematic,
  paper model must be updated.

---

## 9. Options / Event / On-Chain Regime Usage

### Options-Implied State

- IV percentile → volatility regime classification.
- Put/call skew → directional sentiment.
- Term structure slope → anticipation of event.
- High IV + negative skew → defensive regime → reduce aggression.

### Event State

- Scheduled events (FOMC, CPI, ETF deadlines) → regime flag.
- During event windows: widen slippage assumptions, reduce size, or abstain.
- Post-event: wait for regime re-classification before resuming.

### On-Chain State

- Exchange inflow/outflow → selling/buying pressure proxy.
- Stablecoin flow → risk-on/risk-off signal.
- Whale wallet movements → potential liquidation / manipulation signal.
- These are activation/deactivation/throttling inputs, not direct signals.

**Rule:** Options, event, and on-chain states are never used as standalone
trading signals. They modulate aggression, exposure, and venue selection.

---

## 10. Attribution Doctrine

Every realized trade must be decomposed into:

| Component | Definition |
|-----------|------------|
| Forecast alpha | Signal strength at decision time |
| Fees | Exchange fees (maker/taker) |
| Funding | Funding rate cost/benefit over hold period |
| Slippage | Decision price to execution price gap |
| Markout | Post-fill price movement (adverse selection measure) |
| Venue contribution | Venue-specific execution quality vs average |
| Execution-mode contribution | Maker vs taker choice quality |
| Regime tag | Which regime was active at entry/exit |
| Event tag | Whether entry/exit occurred during event window |

**Aggregation levels:**
- Per-trade
- Per-symbol
- Per-venue
- Per-regime
- Per-time-bucket (hourly, daily)
- Per-execution-mode (maker vs taker)

**Rule:** Total attributed PnL must reconcile with actual PnL within
rounding tolerance (< 0.01 bps). If decomposition does not sum to total,
flag as ATTRIBUTION_DRIFT.

---

## 11. Multi-Sleeve Portfolio Doctrine

Future portfolio structure:

| Sleeve | Strategy Type | Allocation | Rebalance |
|--------|--------------|------------|-----------|
| Momentum | Trend-following edges | Dynamic | Daily |
| Mean-Revert | Microstructure edges | Dynamic | Intraday |
| Funding | Funding rate arbitrage | Fixed | Per cycle |
| Liquidation | Liquidation flow edges | Opportunistic | Event-driven |

**Rules:**
- Each sleeve is independently risk-managed.
- Cross-sleeve correlation is monitored.
- Total portfolio exposure ≤ 3× leverage.
- Sleeve allocation is attribution-driven: allocate more to sleeves with
  better markout and lower adverse selection.

---

## 12. Tiny Live Canary Doctrine

Before any edge goes full-size live:

1. Shadow trade (paper alongside live feed) for minimum 7 days.
2. TCA comparison: paper vs expected cost model.
3. Canary deployment: 1/10th target size for minimum 50 fills.
4. Canary TCA must show:
   - Markout positive at 30s horizon.
   - Slippage surprise < 3 bps.
   - Fill ratio > 0.7 (maker) or > 0.95 (taker).
5. Only then: promote to target size with gradual ramp (25% → 50% → 100%).

**Rule:** Never skip canary. Never skip shadow. No exceptions.

---

## 13. Explicit Mistakes to Forbid

| # | Mistake | Why It Is Forbidden |
|---|---------|---------------------|
| 1 | Assuming paper fills = live fills | Paper overstates alpha by 10-50 bps |
| 2 | Ignoring funding costs in PnL | Funding can exceed alpha on many pairs |
| 3 | Routing on displayed price alone | Hidden costs dominate displayed price |
| 4 | Ignoring maker non-fill risk | Non-fills are invisible losses |
| 5 | Using volume as liquidity proxy | Volume ≠ available depth; wash trading |
| 6 | Ignoring post-fill markout | Negative markout = adverse selection leak |
| 7 | Treating all venues as equivalent | Venue design differences affect tail risk |
| 8 | Skipping canary deployment | First live fills reveal hidden model errors |
| 9 | Backdating alpha measurement | TCA must measure from decision time, not fill time |
| 10 | Ignoring ADL / socialized-loss | Tail risk is venue-specific and material |
| 11 | Optimizing fill cost without markout | Low-cost fills with bad markout are toxic |
| 12 | Assuming constant fee tiers | Fee tiers change with volume; re-check monthly |
| 13 | Treating funding rate as noise | Funding rate IS the crowd positioning signal |
| 14 | Skipping stress-regime TCA segmentation | Normal-regime TCA hides stress-regime blowup |
| 15 | Fabricating missing data | Missing = None; never zero, never estimated |

---

## Version

- Created: 2026-04-18
- Scope: Crypto perpetual futures system per PRDV4
- Authority: Subordinate to `docs/PRDV4_MULTI_MARKET_CRYPTO.md`
