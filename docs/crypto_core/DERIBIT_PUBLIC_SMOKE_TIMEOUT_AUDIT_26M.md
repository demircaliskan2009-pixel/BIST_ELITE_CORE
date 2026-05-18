# Deribit Public Smoke Timeout Audit - Phase 26M

status: TIMEOUT_AUDIT_ONLY
phase: 26M
generated_at: 2026-05-18
source_run_id: `26033502712`
source_run_url: `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26033502712`
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true

## Purpose

Phase 26M produces a deterministic technical audit of run `26033502712`,
which was dispatched in Phase 26I and classified as rejected in Phase 26K.
The audit records timing evidence, log evidence, and the exact failure mode
so that Phase 26N can dispatch a retry with explicit understanding of the
prior failure.

## Run Summary

| field | observed_value |
|---|---|
| `run_id` | `26033502712` |
| `run_url` | `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26033502712` |
| `head_branch` | `main` |
| `head_sha` | `30aa40d95ad75f204635766f12f1249387786ac8` |
| `event` | `workflow_dispatch` |
| `run_conclusion` | `failure` |
| `run_created_at_utc` | `2026-05-18T12:28:58Z` |
| `job_started_at_utc` | `2026-05-18T12:29:04Z` |
| `job_completed_at_utc` | `2026-05-18T12:29:57Z` |
| `job_elapsed_seconds` | `53` |

## Dispatch Parameters

| parameter | value |
|---|---|
| `duration_seconds` | `30` |
| `max_messages` | `100` |
| `sample_limit` | `100` |
| `max_receive_lag_ms` | `60000` |
| `ws_url` | `wss://www.deribit.com/ws/api/v2` |
| `channels` | `book.BTC-PERPETUAL.none.10.100ms` |

## Step Timeline

| step | started_utc | completed_utc | conclusion | elapsed_seconds |
|---|---|---|---|---|
| Set up job | `2026-05-18T12:29:05Z` | `2026-05-18T12:29:06Z` | `success` | `1` |
| Checkout | `2026-05-18T12:29:06Z` | `2026-05-18T12:29:08Z` | `success` | `2` |
| Setup Python | `2026-05-18T12:29:08Z` | `2026-05-18T12:29:08Z` | `success` | `0` |
| Install dependencies | `2026-05-18T12:29:08Z` | `2026-05-18T12:29:24Z` | `success` | `16` |
| Run Deribit public WS smoke | `2026-05-18T12:29:24Z` | `2026-05-18T12:29:54Z` | `failure` | `30` |
| Validate smoke result | — | — | `skipped` | — |
| Upload smoke proof artifact | `2026-05-18T12:29:54Z` | `2026-05-18T12:29:55Z` | `success` | `1` |

## Smoke Step Log Evidence

| log_timestamp_utc | log_line |
|---|---|
| `2026-05-18T12:29:24.5875955Z` | `Run Deribit public WS smoke` (step started) |
| `2026-05-18T12:29:24.6409498Z` | `WARNING: PUBLIC MARKET DATA ONLY. NO TRADING. NO CREDENTIALS. NO ORDERS.` |
| `2026-05-18T12:29:54.8839973Z` | `##[error]Process completed with exit code 1.` |

## Artifact Evidence

| field | observed_value |
|---|---|
| `accepted` | `false` |
| `dry_run` | `true` |
| `operator_authorization` | `PUBLIC_MARKET_DATA_ONLY` |
| `rejection_reasons` | `["deribit_ws:timeout"]` |
| `message_count` | `0` |
| `sample_events` | `[]` |
| `ws_url` | `wss://www.deribit.com/ws/api/v2` |
| `channels` | `book.BTC-PERPETUAL.none.10.100ms` |
| `duration_seconds` | `30.0` |
| `started_at_ns` | `1779107364640752570` |
| `completed_at_ns` | `1779107394863923161` |
| `artifact_sha256` | `f41fa6a8a02a678a7d6714f7a9b6a9ced717d234e8e370a3ba42883479f7456d` |

## Failure Mode Analysis

| fact | evidence |
|---|---|
| Script printed WARNING at step start | Log at `12:29:24.6409498Z` |
| Script ran to completion (no crash) | Step elapsed exactly 30 seconds = `duration_seconds` |
| Zero messages received | `message_count=0` |
| Zero sample events | `sample_events=[]` |
| Smoke script exit code 1 | Log at `12:29:54.8839973Z` |
| Validate step skipped | Step conclusion = `skipped` (precondition failed because smoke step failed) |
| Artifact was uploaded despite failure | Upload step conclusion = `success` |

## Root Cause Classification

| candidate | assessment |
|---|---|
| Script crashed before connecting | **EXCLUDED**: WARNING printed at `12:29:24`, process ran full 30 seconds |
| Subscription channel invalid | **UNCONFIRMED**: Script ran; no subscription ack or error in available log lines |
| Runner network cannot reach `wss://www.deribit.com/ws/api/v2` | **PLAUSIBLE**: GitHub runner outbound WS connectivity to Deribit is unverified |
| Deribit server not sending book events for `book.BTC-PERPETUAL.none.10.100ms` | **PLAUSIBLE**: Channel may have been inactive at the time |
| Transient Deribit WS outage at `2026-05-18T12:29:xx Z` | **PLAUSIBLE**: Correlated with exact run window |

**Conclusion**: The script reached Deribit and ran for the full window, but received zero WS messages. The exact sub-cause (runner network, Deribit channel, transient outage) cannot be determined from a single timeout. A retry is required.

## Accumulated Timeout Record

| run_id | dispatched_at_utc | conclusion | message_count | rejection_reason |
|---|---|---|---|---|
| `26033502712` | `2026-05-18T12:28:58Z` | `failure` | `0` | `deribit_ws:timeout` |

## Phase 26N Retry Trigger

| parameter | value |
|---|---|
| `retry_run_dispatched` | `true` |
| `retry_run_id` | `26035089720` |
| `retry_run_url` | `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26035089720` |
| `retry_dispatched_at_utc` | `2026-05-18T13:00:24Z` |
| `retry_duration_seconds` | `30` |
| `retry_max_messages` | `100` |
| `retry_sample_limit` | `100` |
| `retry_max_receive_lag_ms` | `60000` |
| `retry_rationale` | `Per Phase 26L next_action: same settings, single retry to rule out transient outage` |

## Classification Effect

This audit does NOT advance any claim classification.
All raw sequence claims remain WAIT_INSUFFICIENT per Phase 26K.

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
