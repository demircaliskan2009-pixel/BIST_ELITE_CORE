---
name: crypto-failure-replay
description: 'Deterministic replay of any trade, execution, or bug. Reproduce failures exactly from recorded state. Integrated with test fixtures for regression testing.'
argument-hint: 'Describe the failure to replay: trade ID, timestamp, affected components, and expected vs actual behavior.'
user-invocable: true
---

# Failure Replay System

Every failure is reproducible. Every anomaly is explainable.

## Design Principles

- All system state is recorded at decision points.
- Any trade, signal, or execution can be replayed from recorded state.
- Replay produces IDENTICAL output given identical input.
- Failures become permanent regression tests.

## State Recording

### What Is Recorded

Every pipeline execution records:

```json
{
  "replay_id": "RPL-2026-04-15-001",
  "timestamp_ms": 1700000000000,
  "pipeline_stage": "edge | risk | execution",
  "input_state": {
    "data_snapshot": "snap_id",
    "book_state": {...},
    "edge_signals": [...],
    "risk_state": {...},
    "system_state": "NORMAL",
    "shs_value": 0.82
  },
  "computation": {
    "edge_id": "EDGE-A-007",
    "signal_value": 1.73,
    "features_used": {...},
    "parameters": {...}
  },
  "output_state": {
    "decision": "ENTER_LONG",
    "position_size": 0.023,
    "order_type": "LIMIT",
    "expected_fill_price": 84250.50
  },
  "actual_outcome": {
    "fill_price": 84252.30,
    "slippage_bps": 2.14,
    "fill_time_ms": 340,
    "status": "FILLED"
  }
}
```

### Recording Triggers

| Event | Recording Level |
|-------|----------------|
| Edge signal generated | Full input state + features |
| Order created | Full risk state + sizing |
| Order filled/rejected | Full execution state + market |
| Kill-switch triggered | Full system state snapshot |
| NT condition activated | Triggering data + all NT states |
| System state change | All 10 SHS signals + weights |
| Anomaly detected | Full pipeline state at anomaly |

## Replay Engine

### Replay Protocol

```python
class ReplayEngine:
    def __init__(self, replay_record: dict, clock: SimClock): ...
    def setup_state(self): ...          # Restore exact input state
    def execute_pipeline(self): ...      # Run pipeline with recorded inputs
    def compare_output(self) -> ReplayResult: ...  # Compare vs recorded output
    def inject_variation(self, **overrides): ...    # "What-if" analysis
```

### Replay Modes

| Mode | Purpose |
|------|---------|
| EXACT | Reproduce exact output from recorded input |
| WHAT_IF | Modify one input, observe output change |
| REGRESSION | Run as test, assert output matches |
| FORENSIC | Step through pipeline stage by stage |

### Exact Replay

1. Load replay record
2. Set SimClock to recorded timestamp
3. Restore all input state (book, features, risk, system state)
4. Execute pipeline with recorded inputs
5. Compare output with recorded output
6. If mismatch → BUG DETECTED

### What-If Analysis

1. Load replay record
2. Override specific input (e.g., change spread, change SHS)
3. Execute pipeline
4. Compare output with original
5. Report: "If X had been Y, decision would have been Z"

## Failure Types

### Trade Failures

```json
{
  "failure_type": "TRADE",
  "failure_id": "TFL-2026-04-15-001",
  "trade_id": "T-A007-20260415-042",
  "symptom": "Unexpected loss on BTCUSDT long",
  "replay_id": "RPL-2026-04-15-001",
  "root_cause": "Liquidation cascade caused 50bp slippage vs 5bp estimate",
  "category": "EXECUTION_MODEL_GAP",
  "remediation": "Increase slippage estimate during high liquidation volume"
}
```

### Execution Failures

```json
{
  "failure_type": "EXECUTION",
  "failure_id": "EFL-2026-04-15-001",
  "symptom": "Order rejected by exchange",
  "replay_id": "RPL-2026-04-15-002",
  "root_cause": "Margin insufficient due to concurrent position not accounted",
  "category": "RISK_STATE_DESYNC"
}
```

### Signal Failures

```json
{
  "failure_type": "SIGNAL",
  "failure_id": "SFL-2026-04-15-001",
  "symptom": "Edge A generated signal in DEFENSIVE state",
  "replay_id": "RPL-2026-04-15-003",
  "root_cause": "SHS state update lagged by 2 compute cycles",
  "category": "STATE_PROPAGATION_DELAY"
}
```

## Regression Test Generation

Every resolved failure becomes a permanent regression test:

```python
# Auto-generated from RPL-2026-04-15-001
def test_replay_rpl_20260415_001():
    clock = SimClock(start_ms=1700000000000)
    engine = ReplayEngine(load_replay("RPL-2026-04-15-001"), clock)
    engine.setup_state()
    result = engine.execute_pipeline()
    engine.compare_output()  # Asserts exact match
```

Storage: `tests/replay/test_replay_<id>.py`

## Storage Layout

```
data/
  replay/
    records/
      RPL-2026-04-15-001.json
      RPL-2026-04-15-002.json
    failures/
      TFL-2026-04-15-001.json
      EFL-2026-04-15-001.json
    regression/
      manifest.jsonl    # List of all replay-based regression tests
```

## Integration Points

| System | Connection |
|--------|------------|
| `crypto-test-fixtures` | SimClock + simulator infrastructure |
| `crypto-knowledge-memory` | Store failure patterns |
| `crypto-experiment-tracker` | Link failures to experiments |
| `crypto-data-pipeline` | Recorded data states |
| `crypto-risk-execution` | Recorded risk states |
| Forensic Debugger agent | Uses replay for root cause analysis |

## Output

Replay result + comparison report + failure classification + regression test (if failure resolved).
