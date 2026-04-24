# PRDV4 Global Contract Schema

Shared contract for crypto pipeline stage outputs and transitions per PRDV4 §2.

## Global Rules
- Deterministic only: identical inputs → identical contract outputs.
- Fail closed: missing evidence, invalid field, or ambiguous state stops the pipeline.
- No silent mutation: stages may not rename, coerce, drop, or reinterpret fields.
- Strict transitions: downstream runs only when prior stage produced valid output.

## Shared Envelope

| Field | Requirement |
|---|---|
| `stage` | One of `data`, `edge`, `risk` |
| `status` | Stage-specific status value |
| `scope` | Symbols, exchange, timeframe, granularity |
| `system_state` | Current SHS state (§1.29) |
| `validation_evidence` | Validation result or explicit not-run statement |
| `blocking_reason` | Required when status is blocking; otherwise omitted |
| `next_action` | Single best next action |

## DATA Stage Contract

### Allowed Status: `SAFE` | `UNSAFE`

### Required Structure
- `stage: data`
- `status`
- `scope` (exchange, symbols, timeframes)
- `stream_health` (per-stream: latency, gaps, stale count)
- `book_integrity` (CRC32 result, reconciliation status)
- `trade_integrity` (sequence gaps, dedup count)
- `ohlcv_schema` (canonical columns)
- `validation_evidence`
- `blocking_reason` when `UNSAFE`

### Validation Rules (§4)
- WebSocket sequence numbers monotonic
- Order book CRC32 valid
- Trade stream: no sequence gaps
- OHLCV: structurally plausible
- No stale data (>10s)
- NT-D01 through NT-D05 checked

## EDGE Stage Contract

### Allowed Status: `READY` | `BLOCKED`

### Required Structure
- `stage: edge`
- `status`
- `scope`
- `active_edges` (list with family, EHS, activation state)
- `meta_allocation` (per-edge allocation from §1.7)
- `regime_state` (4D regime cell from §1.17)
- `crowding_flags` (from §1.11)
- `validation_evidence`
- `blocking_reason` when `BLOCKED`

### Validation Rules (§1)
- All active edges have EHS > threshold (§1.6)
- Activation matrix satisfied (§1.5)
- No crowding flags active for edge
- PBO < 0.40 for all live edges (§1.20)

## RISK Stage Contract

### Allowed Status: `ALLOWED` | `BLOCKED`

### Required Structure
- `stage: risk`
- `status`
- `scope`
- `position_sizing` (Kelly fraction, drawdown multiplier)
- `risk_check_results` (CVaR, margin, DTL, NT conditions)
- `system_state` (SHS value, current state)
- `kill_switch_level` (KS-0 through KS-4)
- `execution_plan` (order type, splitting, adversarial params)
- `validation_evidence`
- `blocking_reason` when `BLOCKED`

### Validation Rules (§7-§8)
- All 23 NT conditions checked (§1.21)
- CVaR₉₉ < 5% NAV (§1.18)
- Kelly fraction computed and bounded (§1.28)
- DTL > safety threshold (§1.26)
- Margin utilization within tier limits (§1.26)
- System state permits new entries (§1.29)
- Market impact TC < 50% expected return (§1.14)

## Transition Rules

| Transition | Valid When |
|---|---|
| data → edge | data status = `SAFE` and all required fields present |
| edge → risk | edge status = `READY` and all required fields present |
| risk → execution | risk status = `ALLOWED` |

Any missing field → contract mismatch → pipeline STOP.
Any system_state ≥ DEFENSIVE → no new pipeline runs.

## Enforcement
If a stage output does not comply → pipeline stops at that stage with exact mismatch reported.

## TELEMETRY CONTRACT

Every stage MUST emit telemetry as a sidecar to its output.

### Telemetry Envelope

| Field | Requirement |
|---|---|
| `timestamp_ms` | Unix epoch milliseconds |
| `stage` | One of `data`, `edge`, `risk`, `execution` |
| `metrics` | Stage-specific metric object |
| `alerts` | Array of threshold breaches (empty if none) |
| `duration_ms` | Stage execution time |

### Per-Stage Metrics

**DATA stage:**
- `ws_latency_ms` — WebSocket message latency
- `book_crc32_pass_rate` — CRC32 success ratio
- `trade_gap_count` — sequence gaps detected
- `stale_stream_count` — streams exceeding 10s staleness
- `reconnect_count` — WebSocket reconnections this hour

**EDGE stage:**
- `active_edge_count` — edges in ACTIVE state
- `edge_hit_rate` — signal accuracy over trailing 24h
- `ehs_mean` — mean EHS across active edges
- `crowding_flag_count` — active crowding detections
- `pbo_worst` — worst PBO among active edges

**RISK stage:**
- `cvar99_pct` — portfolio CVaR₉₉ as % NAV
- `margin_utilization_pct` — current margin usage
- `dtl_min_pct` — minimum distance-to-liquidation
- `kill_switch_level` — current KS level (0-4)
- `nt_active_count` — active NO-TRADE conditions

**EXECUTION stage:**
- `slippage_bps` — actual vs estimated slippage
- `fill_rate_pct` — fill ratio
- `impact_cost_bps` — market impact cost
- `order_latency_ms` — order submission to ack

### Drift Detection Metrics (cross-stage)

| Metric | Method | Alert Threshold |
|--------|--------|----------------|
| `psi_<feature>` | Population Stability Index | >0.25 |
| `ks_<feature>` | Kolmogorov-Smirnov test | p < 0.01 |

Drift checks run every 1 hour on all features feeding active edges.

### Telemetry Rules

- Telemetry writes MUST be async (never block pipeline).
- Output: `logs/telemetry/telemetry_YYYY-MM-DD.jsonl` (one line per emission).
- Alerts are threshold breaches requiring investigation.
- Telemetry is read-only for AI agents (INV-005 applies).

## EXPERIMENT CONTRACT

Every experiment MUST produce this contract on completion.

### Required Structure
- `experiment_id` — Unique ID (EXP-YYYY-MM-DD-NNN)
- `edge_family` — A-G
- `hypothesis` — Explicit microstructure hypothesis
- `status` — One of `CREATED`, `BACKTEST`, `PBO_CHECK`, `WALK_FORWARD`, `SHADOW`, `PROMOTED`, `REJECTED`
- `parameters` — Frozen parameter set
- `features` — Version-locked feature references from feature store
- `backtest_results` — Sharpe, max DD, win rate, profit factor, avg duration
- `pbo_results` — PBO value, DSR, sensitivity pass/fail
- `walk_forward_results` — OOS Sharpe retention, hit rate retention, window results
- `shadow_results` — Signal accuracy, tracking error, fill quality
- `decision` — PROMOTED / REJECTED with reason
- `knowledge_entry_id` — Link to knowledge memory (if rejected)

### Validation Rules
- No experiment without frozen parameters
- No experiment without version-locked features
- No PBO check without completed backtest
- No walk-forward without PBO < 0.60
- No shadow without walk-forward pass
- Rejected experiments MUST have knowledge memory entry

## FEATURE STORE CONTRACT

Every registered feature MUST comply with this contract.

### Required Structure
- `feature_id` — Unique ID (FEAT-FAMILY-NNN-vN)
- `name` — Human-readable name
- `family` — Edge family (A-G)
- `version` — Semantic version
- `status` — One of `EXPERIMENTAL`, `VALIDATED`, `ACTIVE`, `DEPRECATED`
- `inputs` — Raw data sources with exact field references
- `computation` — Deterministic transformation (code reference)
- `output_schema` — Exact output dtype, range, units
- `lineage` — Parent features or raw sources
- `hash` — SHA-256 of computation code

### Validation Rules
- No feature without lineage to raw data
- No feature with non-deterministic computation
- No ACTIVE feature without drift monitoring (PSI/KS)
- Deprecated features MUST NOT be used in new experiments
- Feature version changes require new experiment

## REPLAY CONTRACT

Every replay record MUST comply with this contract.

### Required Structure
- `replay_id` — Unique ID (RPL-YYYY-MM-DD-NNN)
- `timestamp_ms` — Unix epoch at event
- `pipeline_stage` — Stage where event occurred
- `input_state` — Complete input state snapshot
- `computation` — Edge, parameters, features used
- `output_state` — Decision, sizing, order details
- `actual_outcome` — Fill, slippage, status

### Validation Rules
- Replay of recorded input MUST produce identical output
- If mismatch detected → classify as BUG
- Resolved replays MUST generate regression test

## STATE STORE CONTRACT

Every state mutation MUST comply with this contract.

### Required Structure
- `domain` — One of `system`, `portfolio`, `edge`, `execution`
- `version` — Monotonically increasing integer
- `timestamp_ms` — Unix epoch at mutation
- `data` — Domain-specific state object
- `mutation_source` — Component that triggered the write
- `correlation_id` — Event correlation ID

### Validation Rules
- Writes MUST use optimistic concurrency (expected_version check)
- Version MUST increment by exactly 1 per write
- No cross-domain atomic writes (use saga pattern)
- All writes MUST be fsynced before acknowledgment
- State history MUST be retained per retention policy

## EVENT CONTRACT

Every system event MUST comply with this contract.

### Required Structure
- `event_id` — Unique ID (EVT-YYYYMMDD-NNNNNN)
- `event_type` — From event taxonomy (typed, no free-form)
- `timestamp_ms` — Unix epoch at emission
- `source` — Publishing component
- `priority` — 0 (CRITICAL) to 4 (BACKGROUND)
- `payload` — Event-type-specific data
- `correlation_id` — For request tracing across components
- `version` — Event schema version

### Validation Rules
- Untyped events → REJECTED
- Events without correlation IDs → REJECTED
- Events without timestamps → REJECTED
- Priority 0 events MUST preempt all other processing

## DEPLOYMENT CONTRACT

Every deployment MUST comply with this contract.

### Required Structure
- `deployment_id` — Unique ID (DEP-YYYYMMDD-NNN)
- `stage` — One of `DEV`, `STAGING`, `PRODUCTION`
- `commit_hash` — Exact commit being deployed
- `gate_results` — Pass/fail per promotion gate
- `rollback_version` — Previous known-good deployment ID
- `health_check_status` — Current health state

### Validation Rules
- No deployment skips stages (DEV→STAGING→PRODUCTION)
- No deployment without passing all stage gates
- No deployment without rollback plan
- No deployment during CRISIS or HALT state
