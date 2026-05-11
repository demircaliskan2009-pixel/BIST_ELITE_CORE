---
name: crypto-data-pipeline
description: 'Handle crypto data pipeline tasks: WebSocket stream management, order book construction/validation, trade stream processing, OHLCV construction, data integrity checks, recovery protocol, and fail-closed data admission per PRDV4 §4.'
argument-hint: 'Describe the data task: stream type, exchange, symbol, validation scope, and expected output.'
user-invocable: true
---

# Crypto Data Pipeline

Data entry gate for the crypto trading system per PRDV4 §4.

## Contract

All outputs must comply with `_shared/references/contract-schema.md`.
Only `SAFE` data-stage output permits downstream processing.

## Scope (PRDV4 §4)

### WebSocket Streams (§4.1)

| Exchange | Streams | Rate |
|----------|---------|------|
| Binance (primary) | trade, depth@100ms, kline, forceOrder, markPrice@1s, funding, ticker | Real-time |
| Bybit (secondary) | Same categories | Failover + cross-exchange |
| CoinGecko | REST: market cap, volume rankings | 1h poll |

Kline intervals: 1m, 5m, 15m, 1h, 4h, 1d.

### Order Book (§4.2)

1. Initial REST snapshot on connection
2. Delta updates from WebSocket
3. CRC32 reconciliation every 60s
4. Stale detection: NT-D02 if last L2 update > 10s
5. Sequence validation with gap detection
6. CRC32 mismatch → discard → re-snapshot → log anomaly

### Trade Stream (§4.3)

- Dedup by trade_id
- Gap detection by sequence number
- OHLCV construction from raw trades
- Cross-reference against exchange klines

### Recovery Protocol (§4.5)

1. Heartbeat: ping every 5s, timeout at 15s
2. Reconnect: exponential backoff 1s/2s/4s/8s, max 30s
3. Full snapshot on reconnect
4. Replay deltas from snapshot timestamp
5. Validate consistency (CRC32, sequence continuity)
6. If recovery fails after 120s → KS-3 (§1.19 critical trigger #9)

### Timeframe Hierarchy (§4.6)

| Timeframe | Role | Enforcement |
|-----------|------|-------------|
| HTF (1H-4H) | Regime classification ONLY | No trade triggers |
| MTF (5m-15m) | Setup validation ONLY | No trade initiation |
| LTF (tick/orderbook) | Execution ONLY | Entry timing, order management |

Cross-timeframe trade triggers blocked by enforcement state machine.

## Validation Checklist

- [ ] WebSocket sequence numbers monotonic
- [ ] Order book CRC32 valid after each reconciliation cycle
- [ ] Trade stream: no gaps in sequence
- [ ] OHLCV: open ≤ high, low ≤ close, volume ≥ 0
- [ ] Symbol identity valid and stable
- [ ] No stale data (>10s triggers NT-D02)
- [ ] Timestamps monotonic per stream

## Data Halt Conditions (§1.21)

- NT-D01: Primary data feed gap > 30 seconds
- NT-D02: Order book stale > 10 seconds
- NT-D03: Trade feed desynced > 60 seconds
- NT-D04: Mark price diverges from index > 2%
- NT-D05: Funding rate feed unavailable at settlement

Any active NT-D trigger → no new orders for affected asset.

## Decision Rules

- If stream integrity fails → mark UNSAFE, block downstream
- If CRC32 mismatch persists after re-snapshot → escalate to NT-D02
- If multiple exchanges disagree on price by > 1% → log anomaly, use primary
- If all checks pass → mark SAFE with validated scope

## Output

Contract-compliant data-stage result + validation summary + anomaly list.
