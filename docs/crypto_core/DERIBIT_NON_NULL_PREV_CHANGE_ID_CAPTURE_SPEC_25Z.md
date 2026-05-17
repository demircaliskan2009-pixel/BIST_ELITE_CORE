# Deribit Non-Null Prev Change Id Capture Spec - Phase 25Z

status: SPEC_ONLY_NO_NETWORK_CHANGE
phase: 25Z
generated_at: 2026-05-17
source_gap_artifact: `docs/crypto_core/DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md`
source_observed_artifact: `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`
script_surface_reviewed: `scripts/crypto_core/deribit_public_ws_smoke.py`
harness_surface_reviewed: `src/crypto_core/data/deribit_public_ws_harness.py`
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_b1_b5_closure: true
NOT_connector_enablement: true
NOT_live_trading: true

## Purpose

This spec defines the exact future public-market-data artifact needed to move
`prev_change_id` and `continuity_condition` from WAIT_INSUFFICIENT to
PROOF_READY_NOT_APPROVED. It does not run a connector, does not add network
implementation, does not edit worksheets, and does not enable
`connector_ready_dialects()`.

## Existing Surface Inspection

| surface | current_capability | phase25z_decision |
|---|---|---|
| `scripts/crypto_core/deribit_public_ws_smoke.py` | Exposes `--duration-seconds`, `--max-messages`, `--max-receive-lag-ms`, public URL, channel, and authorization flags. | No script edit required for this docs/tests proof plan. |
| `src/crypto_core/data/deribit_public_ws_harness.py` | Allows up to `DERIBIT_PUBLIC_WS_MAX_DURATION_SECONDS=30.0` and `DERIBIT_PUBLIC_WS_MAX_MESSAGES=100`; parses `prev_change_id` into `prev_sequence_id`; keeps a bounded sample set. | No source runtime edit authorized or required in this phase. |
| `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | Contains five actual observed book events, all with `prev_change_id=null`. | Not enough to promote `prev_change_id` or `continuity_condition`. |

## Required Future Capture Command

The future artifact should be produced by the existing quarantined public smoke
surface or an equivalent audited CI artifact using the same boundary:

```powershell
python scripts/crypto_core/deribit_public_ws_smoke.py --duration-seconds 30 --max-messages 100 --max-receive-lag-ms 60000
```

If CI hard limits require lower values, the artifact must explicitly record the
CI limit and the lower values used. Otherwise:

- `duration_seconds >= 30`
- `max_messages >= 100`
- channel remains `book.BTC-PERPETUAL.none.10.100ms`
- public unauthenticated book channel only

## Required Artifact Boundary

The committed future artifact must include:

| required_field | requirement |
|---|---|
| `dry_run` | Must be `true`. |
| `operator_authorization` | Must be `PUBLIC_MARKET_DATA_ONLY`. |
| `accepted` | Must be `true`. |
| `rejection_reasons` | Must be `[]`. |
| `ws_url` | Must be `wss://www.deribit.com/ws/api/v2`. |
| `channel` | Must be public book channel `book.BTC-PERPETUAL.none.10.100ms` unless a later prompt explicitly authorizes another public book channel. |
| `observed_events` | Must include at least two adjacent observed book events from the same channel. |
| `payload_sample` | Must contain sanitized public-market-data scalar fields and counts only. |

Forbidden in the artifact and capture path:

- credentials
- private API
- user, account, raw, order, portfolio, position, or authenticated channels
- orders
- service, orchestrator, strategy, paper, shadow, or live integration
- connector enablement or registry mutation

## Required Event Fields

Each adjacent observed event row must include:

| field | requirement |
|---|---|
| `channel` | Same public book channel for the adjacent pair. |
| `payload_kind` | Exact harness payload kind. |
| `type` | Raw observed `type` value if present; null must be explicit. |
| `change_id` | Raw observed integer value. |
| `prev_change_id` | Raw observed integer value for proof; null keeps the row blocked. |
| `sequence_id` | Harness-mapped integer value from `change_id`. |
| `prev_sequence_id` | Harness-mapped integer value from `prev_change_id`. |
| `timestamp` | Raw observed public payload timestamp if present. |
| `receive_lag_ms` | Measured receive lag for the event. |
| `payload_sample` | Sanitized subset including `change_id`, `prev_change_id`, `type`, timestamp, and book-side counts when present. |

## Required Proof Conditions

| target_claim | promotion_condition |
|---|---|
| `prev_change_id` | At least one actual observed event has non-null integer `prev_change_id`. |
| `continuity_condition` | An adjacent observed pair proves `current.prev_change_id == prior.change_id` from raw committed values. |

A non-null but mismatched `prev_change_id` is not continuity proof. It must be
recorded as a gap or sequence mismatch and the `continuity_condition` row must
remain WAIT_INSUFFICIENT.

## Current Phase 25Z Result

No new capture artifact with non-null `prev_change_id` is committed in this
phase. The current Phase 25M observed artifact has:

- `non_null_prev_change_id_observed=false`
- `continuity_pair_missing=true`
- `prev_change_id`: WAIT_INSUFFICIENT
- `continuity_condition`: WAIT_INSUFFICIENT

No Phase 26B operator proposal is allowed unless a future committed artifact
meets the proof conditions above.
