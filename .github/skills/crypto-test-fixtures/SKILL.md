---
name: crypto-test-fixtures
description: 'Deterministic test fixtures for crypto system: WebSocket simulator, order book replay, funding rate tracker, liquidation feed simulator. All replayable, deterministic, time-controlled.'
argument-hint: 'Describe the fixture needed: exchange, stream type, scenario, duration, and expected behavior.'
user-invocable: true
---

# Crypto Test Fixtures

Deterministic, replayable test infrastructure for the crypto trading system.

## Design Principles

- ALL fixtures produce identical output given identical input.
- ALL time is injectable — no real clocks in tests.
- ALL network I/O is mocked — no real connections.
- ALL scenarios are defined as JSON/JSONL replay files.
- ALL fixtures support fault injection.

## Core: SimClock (Time Controller)

Purpose: Deterministic time source for all fixtures.

```python
class SimClock:
    def __init__(self, start_ms: int): ...
    def now_ms(self) -> int: ...
    def advance(self, ms: int): ...
    def advance_to(self, target_ms: int): ...
```

ALL fixtures accept SimClock. No `datetime.now()` or `time.time()` in test code.

## Fixture 1: WebSocket Simulator

Purpose: Replay recorded or synthetic WebSocket messages for any exchange stream.

```python
class WSSimulator:
    def __init__(self, replay_file: Path, clock: SimClock): ...
    def next_message(self) -> dict | None: ...
    def inject_disconnect(self, after_msg: int): ...
    def inject_latency(self, ms: int, for_msgs: int): ...
    def inject_gap(self, skip_seq: list[int]): ...
    def messages_remaining(self) -> int: ...
```

Replay format (JSONL):
```json
{"ts_ms": 1700000000000, "stream": "trade", "exchange": "binance", "data": {...}, "seq": 1}
{"ts_ms": 1700000000050, "stream": "depth", "exchange": "binance", "data": {...}, "seq": 2}
```

Scenarios:
| File | Description |
|------|-------------|
| `normal_flow.jsonl` | Clean 1-hour stream, no anomalies |
| `gap_recovery.jsonl` | 30-second gap, then recovery |
| `stale_book.jsonl` | Book update stops for 15 seconds |
| `disconnect_reconnect.jsonl` | 3 disconnects with backoff |
| `high_frequency.jsonl` | 10K messages/second burst |
| `cross_exchange.jsonl` | Binance + Bybit interleaved |

## Fixture 2: Order Book Replay

Purpose: Deterministic L2 order book state from snapshot + deltas.

```python
class BookReplay:
    def __init__(self, snapshot: dict, deltas: list[dict]): ...
    def apply_next(self) -> BookState: ...
    def inject_crc32_mismatch(self, at_delta: int): ...
    def get_state(self) -> BookState: ...
    def get_spread(self) -> Decimal: ...
    def get_depth(self, levels: int) -> dict: ...
```

CRC32 validation after every delta application.

Scenarios:
| File | Description |
|------|-------------|
| `thin_book.json` | <$10K depth each side |
| `deep_book.json` | >$1M depth each side |
| `sweep_event.json` | Aggressive taker removes 5 levels |
| `iceberg_detection.json` | Refill pattern at same price |
| `crc32_failure.json` | Mismatch at delta 47 |

## Fixture 3: Funding Rate Tracker

Purpose: Replay funding rate history for mean-reversion edge testing.

```python
class FundingReplay:
    def __init__(self, history: list[dict], clock: SimClock): ...
    def current_rate(self) -> Decimal: ...
    def next_settlement_ms(self) -> int: ...
    def inject_extreme(self, rate: Decimal): ...
    def history_window(self, lookback_hours: int) -> list[Decimal]: ...
```

Scenarios:
| File | Description |
|------|-------------|
| `normal_funding.json` | 30 days, typical ±0.01% |
| `extreme_positive.json` | Sustained >0.1% (crowded long) |
| `extreme_negative.json` | Sustained <-0.1% (crowded short) |
| `settlement_spike.json` | Rate spike at settlement window |

## Fixture 4: Liquidation Feed Simulator

Purpose: Replay forced liquidation events for cascade detection.

```python
class LiquidationReplay:
    def __init__(self, events: list[dict], clock: SimClock): ...
    def next_event(self) -> LiquidationEvent | None: ...
    def inject_cascade(self, count: int, side: str, duration_ms: int): ...
    def total_volume(self, window_ms: int) -> Decimal: ...
```

Scenarios:
| File | Description |
|------|-------------|
| `isolated_liquidation.json` | Single 50K liquidation |
| `cascade_long.json` | 20 sequential long liquidations in 60s |
| `cascade_short.json` | 15 sequential short liquidations in 45s |
| `mixed_cascade.json` | Both sides cascading (market chaos) |

## Fixture 5: Market Impact Simulator

Purpose: Simulate execution cost for Almgren-Chriss model validation.

```python
class MarketImpactSim:
    def __init__(self, book: BookReplay, clock: SimClock): ...
    def estimate_cost(self, side: str, size: Decimal, urgency: float) -> CostEstimate: ...
    def simulate_fill(self, order: Order) -> FillResult: ...
    def inject_slippage(self, bps: int): ...
```

## Composition Pattern

```python
clock = SimClock(start_ms=1700000000000)
ws = WSSimulator("normal_flow.jsonl", clock)
book = BookReplay(snapshot, deltas)
funding = FundingReplay(history, clock)
liq = LiquidationReplay(events, clock)
impact = MarketImpactSim(book, clock)

# Advance time, process messages, verify system state
clock.advance(1000)
msg = ws.next_message()
book.apply_next()
# Assert system response matches expected behavior
```

## File Locations

| Type | Path |
|------|------|
| Replay data | `tests/fixtures/crypto/` |
| Scenario JSONL | `tests/fixtures/crypto/scenarios/` |
| Simulators | `src/crypto_core/testing/simulators.py` |
| SimClock | `src/crypto_core/testing/clock.py` |
| Fixture conftest | `tests/conftest_crypto.py` |

## Validation Rules

- All fixtures MUST produce byte-identical output on replay.
- All fixtures MUST support fault injection.
- No fixture may make network calls.
- No fixture may use system clock.
- All fixtures MUST be composable via SimClock.
- All scenarios MUST have corresponding test cases.
- Scenario files are version-controlled, never generated at runtime.
