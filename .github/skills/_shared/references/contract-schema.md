# PRDV3 Global Contract Schema

This file defines the single shared contract for PRDV3 stage outputs and stage-to-stage transitions. All stage skills and the orchestrator must emit, validate, and enforce outputs against this schema.

## Global Rules
- Deterministic only: identical inputs must produce identical contract outputs.
- Fail closed: any missing evidence, invalid field, malformed structure, or ambiguous state stops the current stage and blocks downstream propagation.
- No silent mutation: a stage may not silently rename, coerce, drop, or reinterpret contract fields.
- Strict transitions: a downstream stage may run only when the prior stage produced a valid contract-compliant output for the same scope.
- Scope consistency: `symbol`, `universe`, `timeframe`, `granularity`, and `dataset_scope` must remain consistent across transitions unless a stage explicitly emits a new validated scope.
- Validation evidence required: every stage output must include a concise validation statement or an explicit statement that validation was not run.

## Shared Envelope
Every stage output must include these top-level fields.

| Field | Requirement |
|---|---|
| `stage` | One of `data`, `strategy`, `risk` |
| `status` | Stage-specific status value from the allowed set below |
| `dataset_scope` | Declared scope for symbols, timeframe, and granularity |
| `validation_evidence` | Concise validation result or explicit not-run statement |
| `blocking_reason` | Required when the status is blocking or unsafe; otherwise empty or omitted |
| `next_action` | Single best next action |

## DATA Stage Contract

### Allowed Status
- `SAFE`
- `UNSAFE`

### Required Structure
- `stage: data`
- `status`
- `dataset_scope`
- `ohlcv_schema`
- `validation_summary`
- `anomaly_summary`
- `validation_evidence`
- `next_action`
- `blocking_reason` when `status = UNSAFE`

### `ohlcv_schema`
- Must define the canonical normalized structure actually approved for downstream use.
- Minimum columns:
  - `timestamp`
  - `symbol`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`
- Column meanings must remain stable and explicit.

### Validation Rules
- Timestamp order is monotonic for the declared granularity.
- Symbol identity is valid and stable within scope.
- OHLCV values are structurally plausible and internally consistent.
- Duplicate, gap, corruption, and truncation checks are summarized explicitly.
- `SAFE` may be emitted only when downstream eligibility is explicitly approved.
- `UNSAFE` blocks all downstream stages.

## STRATEGY Stage Contract

### Allowed Status
- `READY`
- `BLOCKED`

### Required Structure
- `stage: strategy`
- `status`
- `dataset_scope`
- `input_eligibility`
- `feature_summary`
- `ranking_summary` when ranking is in scope
- `signal_summary`
- `validation_evidence`
- `next_action`
- `blocking_reason` when `status = BLOCKED`

### Strategy Rules
- Input must be a contract-compliant `SAFE` data-stage output.
- Features, ranking, scoring, regime logic, and signals must be deterministic and inspectable.
- Signal output may be emitted only from fully defined rules.
- `READY` means strategy output is approved for downstream risk gating.
- `BLOCKED` prevents transition to the risk stage.

## RISK Stage Contract

### Allowed Status
- `ALLOWED`
- `BLOCKED`

### Required Structure
- `stage: risk`
- `status`
- `dataset_scope`
- `input_eligibility`
- `decision_summary`
- `constraint_summary`
- `auditability_summary`
- `validation_evidence`
- `next_action`
- `blocking_reason` when `status = BLOCKED`

### Risk Rules
- Input must be a contract-compliant `READY` strategy-stage output.
- The decision must name the enforced rule, limit, or constraint.
- Auditability must cover the decision path and resulting execution intent.
- `ALLOWED` means the path passed explicit downstream gates.
- `BLOCKED` means the path must not proceed.

## Transition Rules
- `data -> strategy` is valid only when the data-stage output is contract-compliant and `status = SAFE`.
- `strategy -> risk` is valid only when the strategy-stage output is contract-compliant and `status = READY`.
- Any missing required field is a contract mismatch.
- Any incompatible scope is a contract mismatch.
- Any blocking or unsafe status stops the full pipeline.

## Enforcement Rule
If a stage output does not comply with this schema, the pipeline must stop at that stage and report the exact contract mismatch.