# Deribit Next Observed Sequence Proof Spec - Phase 25T

status: SPEC_ONLY_NO_NETWORK_CHANGE

This document defines the exact future observed-proof artifact needed to prove
`prev_change_id`, `first_message_snapshot`, `incremental_delta`, and
`continuity_condition`. It does not add network code, does not run a connector,
does not enable `connector_ready_dialects()`, and does not authorize paper,
shadow, live, private API, credentials, or orders.

## Required Runtime Boundary

The future artifact must be produced only by the quarantined public smoke
harness or an equivalent CI artifact with these guards:

- `dry_run=true`
- `operator_authorization=PUBLIC_MARKET_DATA_ONLY`
- `accepted=true`
- `rejection_reasons=[]`
- public unauthenticated book channel only
- no credentials, private API, user channel, raw channel, account channel, or order path
- no service/orchestrator/strategy integration

## Required Artifact Shape

The future committed artifact must include:

| required_field | requirement |
|---|---|
| `run_id` | GitHub Actions run id or equivalent audited run id. |
| `run_url` | URL to the run that produced the artifact. |
| `source_artifact_name` | Artifact name containing the recorded payload samples. |
| `dry_run` | Must be `true`. |
| `operator_authorization` | Must be `PUBLIC_MARKET_DATA_ONLY`. |
| `accepted` | Must be `true`. |
| `rejection_reasons` | Must be `[]`. |
| `observed_events` | At least two adjacent book events from the same channel. |
| `payload_sample` | Sanitized public-market-data subset only. |

## Required Observed Event Fields

Each adjacent observed event row must include:

| field | requirement |
|---|---|
| `channel` | Same public book channel for each adjacent event. |
| `payload_kind` | Exact harness payload kind. |
| `type` | Raw observed `type` value if present; null must be explicitly recorded. |
| `change_id` | Raw observed integer value. |
| `prev_change_id` | Raw observed integer value for continuity proof; null keeps `prev_change_id` and `continuity_condition` blocked. |
| `sequence_id` | Harness-mapped integer value. |
| `prev_sequence_id` | Harness-mapped previous sequence value. |
| `timestamp` | Raw observed public payload timestamp if present. |
| `receive_lag_ms` | Measured lag for the event. |
| `payload_sample` | Sanitized subset including counts and public scalar fields only. |

## Required Proof Assertions

| target_claim | proof condition |
|---|---|
| `prev_change_id` | At least one observed event has non-null integer `prev_change_id`. |
| `first_message_snapshot` | First observed book event proves snapshot semantics by `type=snapshot`, or an official excerpt explains the observed snapshotless aggregated book channel behavior. |
| `incremental_delta` | A later observed event proves delta/change semantics by `type=change`, or an official excerpt explains the observed `type=null` aggregated book update semantics. |
| `continuity_condition` | For adjacent events `i-1` and `i`, `prev_change_id[i] == change_id[i-1]` must be asserted from raw observed values. |

## Fail-Closed Outcomes

- If `prev_change_id` remains null, `prev_change_id` and `continuity_condition`
  remain WAIT_INSUFFICIENT.
- If `type` remains null and no official excerpt explains the channel behavior,
  `first_message_snapshot` and `incremental_delta` remain WAIT_INSUFFICIENT.
- If adjacent events are missing or from different channels, continuity remains
  WAIT_INSUFFICIENT.
- If the future artifact lacks `dry_run=true` or
  `operator_authorization=PUBLIC_MARKET_DATA_ONLY`, the artifact must be
  rejected.

## Current Phase 25R State

`change_id` is approved in the claim worksheet under
`Phase25R_CHANGE_ID_ONLY`. This spec is only for the remaining observed-sequence
rows and does not approve them.
