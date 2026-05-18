# Deribit Public Smoke Timeout Retry Matrix - Phase 26P

status: PERSISTENT_TIMEOUT_RECORDED
phase: 26P
generated_at: 2026-05-18
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true

## Purpose

Phase 26P records the persistent timeout pattern across the two consecutive
Deribit public smoke runs dispatched on `main`. Both runs used identical
parameters (`duration_seconds=30`, `max_messages=100`, `sample_limit=100`,
`max_receive_lag_ms=60000`) and both returned `rejection_reasons=["deribit_ws:timeout"]`
with `message_count=0`. No classification advancement is possible until
an accepted artifact is obtained.

## Timeout Run Matrix

| run_id | phase | dispatched_at_utc | head_sha | duration_s | max_msg | conclusion | message_count | rejection_reason |
|---|---|---|---|---|---|---|---|---|
| `26033502712` | 26I/26J | `2026-05-18T12:28:58Z` | `30aa40d9` | `30` | `100` | `failure` | `0` | `deribit_ws:timeout` |
| `26035089720` | 26N | `2026-05-18T13:00:24Z` | `de838f0e` | `30` | `100` | `failure` | `0` | `deribit_ws:timeout` |

## Parameters Used (Both Runs)

| parameter | value |
|---|---|
| `ws_url` | `wss://www.deribit.com/ws/api/v2` |
| `channels` | `book.BTC-PERPETUAL.none.10.100ms` |
| `duration_seconds` | `30` |
| `max_messages` | `100` |
| `sample_limit` | `100` |
| `max_receive_lag_ms` | `60000` |
| `operator_authorization` | `PUBLIC_MARKET_DATA_ONLY` |
| `dry_run` | `true` |

## Common Failure Signatures

| field | run 26033502712 | run 26035089720 |
|---|---|---|
| `accepted` | `false` | `false` |
| `message_count` | `0` | `0` |
| `sample_events` | `[]` | `[]` |
| `rejection_reasons` | `["deribit_ws:timeout"]` | `["deribit_ws:timeout"]` |
| smoke step elapsed (s) | `30` | `31` |

## Root Cause Candidates (Persistent Pattern)

| candidate | assessment_single_run | assessment_two_runs |
|---|---|---|
| Transient Deribit outage | PLAUSIBLE | LESS LIKELY (two separate runs 31 min apart) |
| GitHub runner blocked from Deribit WS | PLAUSIBLE | PLAUSIBLE — persistent pattern is consistent |
| Channel `book.BTC-PERPETUAL.none.10.100ms` inactive | POSSIBLE | POSSIBLE (BTC-PERPETUAL is high-activity, unlikely) |
| Script subscription bug | UNLIKELY (script was used successfully in prior smoke runs) | UNLIKELY (same codebase) |

**Conclusion**: The two-run pattern strongly suggests either a persistent network
connectivity issue from GitHub Actions runners to `wss://www.deribit.com/ws/api/v2`,
or an environmental change at Deribit requiring different subscription semantics.
The prior successful run (`25671516104`, `2026-05-11`) is the baseline reference:
it was accepted, so the channel and script were valid at that time.

## Prior Successful Run (Baseline Reference)

| field | value |
|---|---|
| `run_id` | `25671516104` |
| `dispatched_at_utc` | `2026-05-11T12:56:55Z` |
| `conclusion` | `success` |
| `message_count` | see Phase 26G batch |

## Classification Effect

All raw sequence claims remain WAIT_INSUFFICIENT.
No new classification advances.

| claim_id | classification | reason |
|---|---|---|
| `prev_change_id` | WAIT_INSUFFICIENT | Both retry runs returned `message_count=0`; no observed `prev_change_id` value. |
| `continuity_condition` | WAIT_INSUFFICIENT | Both retry runs returned `message_count=0`; no adjacent pair. |
| `first_message_snapshot` | WAIT_INSUFFICIENT | Both retry runs returned `message_count=0`; no first event. |
| `incremental_delta` | WAIT_INSUFFICIENT | Both retry runs returned `message_count=0`; no later event. |

## Required Next Step

To advance past the persistent timeout:

1. **Verify GitHub Actions outbound WS connectivity** — check if GitHub
   Actions runners can reach `wss://www.deribit.com/ws/api/v2`.  
   This is outside the scope of the current repo and requires operator
   investigation of GitHub runner network policy or Deribit WS endpoint access.

2. **Alternative: extend retry window** — try dispatching with
   `max_receive_lag_ms=60000` and `duration_seconds=30` at a different time
   of day to rule out time-of-day Deribit maintenance windows.

3. **Do not classify** until `accepted=true`, `rejection_reasons=[]`,
   `message_count >= 1`, and `sample_events` is non-empty in a committed artifact.

## Safety Invariants

| check | status |
|---|---|
| public_market_data_only | true |
| dry_run | true |
| no_private_api | true |
| no_credentials | true |
| no_orders | true |
| no_worksheet_approval | true |
| no_connector_enablement | true |
| no_registry_mutation | true |
