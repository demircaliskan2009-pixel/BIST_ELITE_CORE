# Deribit Raw Sequence Capture Trigger Gap - Phase 26E

- status: CAPTURE_TRIGGER_BLOCKED_BY_LOCAL_DISPATCH_TOOLING
- phase: 26E
- generated_at: 2026-05-17
- workflow: `.github/workflows/deribit-public-smoke.yml`
- workflow_accepts_inputs: true
- merged_input_patch_pr: `#55`
- merged_input_patch_main_sha: `c5cff2849b830bb14a76674a96532b6f2e0bd906`
- run_id: NOT_AVAILABLE
- run_url: NOT_AVAILABLE
- artifact_downloaded: false
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_connector_enablement: true

## Trigger Attempt Result

The Phase 26D input patch is merged to `main`, so the manual
`deribit-public-smoke.yml` workflow can accept stronger capture settings.
This workspace could not dispatch the workflow because the local `gh` client is
not authenticated, and the available GitHub connector tools expose fetch, PR,
merge, status, job, log, and artifact reads but no `workflow_dispatch` action.

No raw Deribit smoke artifact was downloaded in this phase. Therefore no
`DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26F.json` is created.

## Required Next Capture

Run the manual workflow on `main` with exactly these public-only settings:

| input | required_value |
|---|---|
| `duration_seconds` | `30` |
| `max_messages` | `100` |
| `sample_limit` | `100` |
| `max_receive_lag_ms` | `60000` |

The smoke script must continue to use:

| field | required_value |
|---|---|
| `authorization` | `PUBLIC_MARKET_DATA_ONLY` |
| `dry_run` | `true` |
| `channel` | `book.BTC-PERPETUAL.none.10.100ms` |
| `artifact_name` | `deribit-public-smoke-proof` |
| `artifact_path` | `smoke_result.json` |

## Proof Conditions After Artifact Download

The downloaded JSON may be used for Phase 26F only if all of these are true:

| proof_check | required_condition |
|---|---|
| raw adjacent samples exist | `sample_events` contains at least two adjacent book events from the same channel. |
| non-null previous change id exists | At least one current event has `payload_sample.prev_change_id` as a non-null integer. |
| continuity equality can be evaluated | A current event with non-null `prev_change_id` has an immediately prior event with `payload_sample.change_id`. |
| continuity proof passes | `current.payload_sample.prev_change_id == prior.payload_sample.change_id`. |

If the artifact is accepted but still has zero non-null `prev_change_id` values,
`prev_change_id` and `continuity_condition` must remain WAIT_INSUFFICIENT and
the exact capture result must be recorded as a proof gap.

## Safety Invariants

- Public market data only.
- No private API.
- No credentials.
- No orders.
- No worksheet final approvals.
- No final reviewer metadata.
- No connector enablement.
- No `public_feed_dialects.py` mutation.
- `connector_ready_dialects()` remains empty.
- B1-B5 remain BLOCKED.
