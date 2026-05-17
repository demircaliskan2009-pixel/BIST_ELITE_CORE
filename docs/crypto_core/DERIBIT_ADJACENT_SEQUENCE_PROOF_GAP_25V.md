# Deribit Adjacent Sequence Proof Gap - Phase 25V

status: OBSERVED_ADJACENT_PROOF_GAP
phase: 25V
generated_at: 2026-05-17
source_observed_artifact: `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`
source_artifact_name: `deribit-public-smoke-proof`
source_artifact_id: 6919007152
source_artifact_digest: `sha256:326f763d075881fc2a3584c03d4b5a369f59bc3ae35242807d3bfc303717b2ba`
run_id: 25671516104
run_url: `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/25671516104`
operator_authorization: `PUBLIC_MARKET_DATA_ONLY`
dry_run: true
accepted: true
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_b1_b5_closure: true
NOT_connector_enablement: true
NOT_live_trading: true

## Summary

The Phase 25M artifact contains five actual observed Deribit public book events
from the same public unauthenticated channel. They are adjacent in the committed
sample order, but none of the current events contains a non-null
`prev_change_id`. Therefore no adjacent pair proves
`prev_change_id[current] == change_id[previous]`.

## Observed Adjacent Pair Check

| pair_index | channel | prior.change_id | current.prev_change_id | current.change_id | current.timestamp | current.payload_kind | current.receive_lag_ms | continuity_proven |
|---|---|---:|---|---:|---:|---|---:|---|
| 1 | `book.BTC-PERPETUAL.none.10.100ms` | 154673956305 | null | 154673956448 | 1778504249710 | `market_data` | 63 | NO |
| 2 | `book.BTC-PERPETUAL.none.10.100ms` | 154673956448 | null | 154673957143 | 1778504250021 | `market_data` | 82 | NO |
| 3 | `book.BTC-PERPETUAL.none.10.100ms` | 154673957143 | null | 154673957512 | 1778504250361 | `market_data` | 73 | NO |
| 4 | `book.BTC-PERPETUAL.none.10.100ms` | 154673957512 | null | 154673958252 | 1778504250703 | `market_data` | 61 | NO |

## Exact Missing Evidence

| blocked_claim | exact_missing_field_or_event | required_future_artifact |
|---|---|---|
| `prev_change_id` | At least one actual observed book event with a non-null integer `prev_change_id`. | PUBLIC_MARKET_DATA_ONLY artifact containing sanitized adjacent `observed_events` with raw `change_id`, raw `prev_change_id`, timestamps, channel, payload kind, receive lag, and payload sample. |
| `continuity_condition` | At least one adjacent actual observed pair where `current.prev_change_id == prior.change_id`. | PUBLIC_MARKET_DATA_ONLY artifact proving the equality from committed raw observed values, not from harness-only synthetic values. |
| `first_message_snapshot` | First observed event has `type=null`; no snapshot semantics are proven. | Observed first event with `type=snapshot` or an official excerpt explaining snapshotless aggregated book channel behavior. |
| `incremental_delta` | Observed events have `type=null`; no delta/change semantics are proven. | Observed later event with `type=change` or an official excerpt explaining the observed aggregated update semantics. |

## Capture Improvement Requirement

The next artifact must keep the Phase 25T public-market-data boundary and add
payload samples for an adjacent book sequence where at least the current event
has non-null `prev_change_id`. The artifact must preserve:

- `dry_run=true`
- `operator_authorization=PUBLIC_MARKET_DATA_ONLY`
- `accepted=true`
- `rejection_reasons=[]`
- public unauthenticated book channel only
- no credentials, private API, account channel, order path, connector
  enablement, paper/shadow integration, or live execution

## Classification Effect

- `prev_change_id`: WAIT_INSUFFICIENT
- `continuity_condition`: WAIT_INSUFFICIENT
- `first_message_snapshot`: WAIT_INSUFFICIENT
- `incremental_delta`: WAIT_INSUFFICIENT
- `gap_resubscribe_rule`: WAIT_INSUFFICIENT
- `heartbeat_liveness_proof`: WAIT_INSUFFICIENT

No Phase 25X operator-fill proposal is created because there are zero newly
proof-ready rows.
