# Deribit Proof Artifact Batch - Phase 26K

- status: WAIT_INSUFFICIENT_ARTIFACT_REJECTED
- phase: 26K
- generated_at: 2026-05-18
- source_proof: `docs/crypto_core/DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json`
- source_run_id: `26033502712`
- source_run_url: `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26033502712`
- source_artifact_name: `deribit-public-smoke-proof`
- source_artifact_sha256: `f41fa6a8a02a678a7d6714f7a9b6a9ced717d234e8e370a3ba42883479f7456d`
- newly_proof_ready_not_approved_count: 0
- operator_proposal_created: NO
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_connector_enablement: true

## Summary

Phase 26I successfully dispatched the manual Deribit public smoke workflow with
`duration_seconds=30`, `max_messages=100`, `sample_limit=100`, and
`max_receive_lag_ms=60000`. The workflow uploaded `smoke_result.json`, but the
artifact is not acceptable for sequence classification:

| artifact_field | observed_value |
|---|---|
| `accepted` | `false` |
| `dry_run` | `true` |
| `operator_authorization` | `PUBLIC_MARKET_DATA_ONLY` |
| `rejection_reasons` | `["deribit_ws:timeout"]` |
| `message_count` | `0` |
| `sample_events` | `[]` |

Because the artifact contains zero observed book events, every raw sequence row
remains WAIT_INSUFFICIENT.

## Strict Classification Table

| claim_id | surface | classification | evidence_source | strict_reason |
|---|---|---|---|---|
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json` | `non_null_prev_change_id_observed=false`; artifact was rejected and contains no `sample_events`. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json` | `continuity_pair_missing=true`; no adjacent pair exists, so `current.payload_sample.prev_change_id == prior.payload_sample.change_id` is not proven. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json` | `first_observed_event_missing=true`; no first event exists to prove snapshot semantics. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json` | `later_change_event_missing=true`; no later event exists to prove change or delta semantics. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves the gap recovery or resubscribe rule. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | none | No committed official environment or heartbeat excerpt proves heartbeat, ping-pong, or liveness semantics. |

## Computed Counts

| count_name | value |
|---|---|
| `non_null_prev_change_id_count` | `0` |
| `adjacent_pair_count` | `0` |
| `continuity_match_count` | `0` |
| `snapshot_type_count` | `0` |
| `delta_or_change_type_count` | `0` |

## Non-Promotion Checks

| evidence_check | result | effect |
|---|---|---|
| workflow dispatch succeeded | true | Capture attempted; no claim promotion by itself. |
| artifact accepted for classification | false | All raw sequence classifications remain WAIT_INSUFFICIENT. |
| artifact has at least one `sample_events` item | false | No observed book event can be used as proof. |
| non-null `payload_sample.prev_change_id` observed | false | `prev_change_id` remains WAIT_INSUFFICIENT. |
| adjacent equality `current.prev_change_id == prior.change_id` proven | false | `continuity_condition` remains WAIT_INSUFFICIENT. |
| first event `payload_sample.type` proves snapshot | false | `first_message_snapshot` remains WAIT_INSUFFICIENT. |
| later event `payload_sample.type` proves change or delta | false | `incremental_delta` remains WAIT_INSUFFICIENT. |

## Safety Invariants

- No worksheet row is edited.
- No final `APPROVE`, `REJECT`, or `DEFER` decision is written.
- No reviewer_id or reviewed_at_iso value is filled.
- No operator-fill proposal is created because zero rows are newly proof-ready.
- `connector_ready_dialects()` must remain empty.
- B1-B5 remain BLOCKED.
- `public_feed_dialects.py` remains unchanged.
