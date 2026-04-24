---
name: crypto-knowledge-memory
description: 'Persistent knowledge base for failed edges, bug patterns, performance anomalies, and market regime learnings. System learns from its own history.'
argument-hint: 'Describe the knowledge to store or query: failure pattern, edge outcome, regime observation, or performance anomaly.'
user-invocable: true
---

# Knowledge Memory System

The system remembers every failure, every anomaly, every pattern.

## Design Principles

- Knowledge is structured, searchable, and versioned.
- Every decision references historical knowledge.
- Failed approaches are never repeated.
- Patterns accumulate across market regimes.

## Knowledge Categories

### 1. Failed Edges

```json
{
  "category": "FAILED_EDGE",
  "entry_id": "KM-FE-001",
  "edge_family": "A",
  "edge_id": "EDGE-A-012",
  "hypothesis": "Book imbalance momentum predicts 10-min returns",
  "failure_reason": "Crowding detected at 30% decay — signal degrades below cost",
  "failure_stage": "WALK_FORWARD",
  "experiment_id": "EXP-2026-04-10-003",
  "date_failed": "2026-04-10",
  "regime_context": "TRENDING_UP",
  "lesson": "Book imbalance momentum signals decay rapidly during trending regimes",
  "tags": ["book_imbalance", "momentum", "crowding", "trending"],
  "retest_after": "2026-07-10"
}
```

### 2. Bug Patterns

```json
{
  "category": "BUG_PATTERN",
  "entry_id": "KM-BP-001",
  "component": "risk_engine",
  "pattern": "Margin calculation desync during concurrent position updates",
  "root_cause": "Non-atomic read of position state across coroutines",
  "fix_applied": "Lock-free snapshot pattern for position reads",
  "replay_id": "RPL-2026-04-15-001",
  "recurrence_count": 0,
  "preventive_check": "Assert margin snapshot consistency at order creation",
  "tags": ["margin", "concurrency", "position_state"]
}
```

### 3. Performance Anomalies

```json
{
  "category": "PERF_ANOMALY",
  "entry_id": "KM-PA-001",
  "metric": "execution_slippage_bps",
  "expected_range": [3, 8],
  "observed_value": 22.5,
  "timestamp_ms": 1700000000000,
  "symbol": "BTCUSDT",
  "context": "During BTC liquidation cascade, book thinned 80%",
  "correlation": "Liquidation volume > 2× 24h average",
  "action_taken": "Added liquidation-aware slippage multiplier",
  "tags": ["slippage", "liquidation", "book_depth"]
}
```

### 4. Regime Learnings

```json
{
  "category": "REGIME_LEARNING",
  "entry_id": "KM-RL-001",
  "regime": "MEAN_REVERTING",
  "observation": "Funding rate edges (Family D) outperform by 2.3× during mean-reverting BTC",
  "evidence": {
    "sample_period": "2026-01-01 to 2026-03-31",
    "edge_family": "D",
    "sharpe_in_regime": 2.8,
    "sharpe_outside": 1.2
  },
  "confidence": "HIGH",
  "experiment_ids": ["EXP-2026-03-28-001", "EXP-2026-03-28-002"],
  "tags": ["funding_rate", "mean_reverting", "regime_conditional"]
}
```

### 5. System Configuration Learnings

```json
{
  "category": "CONFIG_LEARNING",
  "entry_id": "KM-CL-001",
  "parameter": "kelly_fraction_cap",
  "previous_value": 0.25,
  "current_value": 0.20,
  "reason": "Drawdown analysis showed 25% Kelly caused > 8% portfolio DD in crisis",
  "evidence": "Portfolio simulation EXP-2026-04-05-SIM-001",
  "tags": ["kelly", "drawdown", "risk_sizing"]
}
```

## Knowledge Operations

### Store
```
store(entry: KnowledgeEntry) → entry_id
```

### Query
```
query(category, tags?, family?, regime?, date_range?) → List[KnowledgeEntry]
```

### Check Before Action
```
check_known_failures(edge_family, hypothesis_keywords) → List[FailedEdge]
check_bug_patterns(component) → List[BugPattern]
check_regime_learnings(current_regime) → List[RegimeLearning]
```

### Update
```
update_recurrence(entry_id)  # Increment if pattern recurs
update_retest_status(entry_id, new_result)  # After retest
```

## Integration Points

### Edge Discovery → Knowledge Memory
Before generating any hypothesis:
1. Query `FAILED_EDGE` for similar hypotheses
2. If match found with `retest_after` in future → SKIP
3. If match found with `retest_after` passed → allow with FLAG

### Experiment Tracker → Knowledge Memory
On experiment REJECTED:
1. Store as `FAILED_EDGE` automatically
2. Extract lesson from experiment results
3. Tag with regime context

### Failure Replay → Knowledge Memory
On failure resolved:
1. Store as `BUG_PATTERN`
2. Link to replay record
3. Set preventive check

### Portfolio Simulator → Knowledge Memory
On anomalous simulation result:
1. Store as `PERF_ANOMALY` or `REGIME_LEARNING`
2. Include full simulation parameters

### Walk-Forward → Knowledge Memory
On edge demotion:
1. Store as `FAILED_EDGE` with walk-forward evidence
2. Record regime context at failure

## Storage Layout

```
data/
  knowledge/
    failed_edges/
      KM-FE-001.json
    bug_patterns/
      KM-BP-001.json
    perf_anomalies/
      KM-PA-001.json
    regime_learnings/
      KM-RL-001.json
    config_learnings/
      KM-CL-001.json
    index.jsonl           # Searchable index: entry_id, category, tags, date
```

## Anti-Patterns

- Storing vague observations without evidence → REJECT
- Storing duplicate patterns (check index first) → MERGE
- Storing entries without tags → REJECT
- Ignoring knowledge base before hypothesis generation → VIOLATION

## Output

When queried: matching knowledge entries with relevance ranking.
When storing: entry_id + confirmation + index update.
