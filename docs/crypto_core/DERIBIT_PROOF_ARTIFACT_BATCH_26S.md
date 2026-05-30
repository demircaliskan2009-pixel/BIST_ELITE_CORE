# Deribit Proof Artifact Batch - Phase 26S

- status: ARTIFACT_ACCEPTED_CLAIMS_WAIT_INSUFFICIENT
- phase: 26S
- generated_at: 2026-05-18
- source_proof: `docs/crypto_core/DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json`
- source_run_id: `26038507233`
- source_run_url: `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26038507233`
- source_artifact_name: `deribit-public-smoke-proof`
- source_artifact_sha256: `f6b0dd2b3a2f6c122aecbf8c3b0522e0a72120d92d98324a55653e667b4c8101`
- newly_proof_ready_not_approved_count: 0
- operator_proposal_created: NO
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_connector_enablement: true

## Summary

Phase 26R dispatched the Deribit public smoke workflow with reduced parameters
(`duration_seconds=10`, `max_messages=10`, `sample_limit=10`,
`max_receive_lag_ms=60000`) and the run concluded with `success` and
`accepted=true`. This resolves the persistent timeout pattern recorded in Phase
26P: the prior timeouts (runs `26033502712` and `26035089720`, both 30s/100/100)
were transient. A 10-second window with a lower message cap succeeded.

The artifact contains 9 observed events from `book.BTC-PERPETUAL.none.10.100ms`.
However, all 9 events return `payload_sample.prev_change_id=null` and
`payload_sample.type=null`. These two fields are required to advance the four
remaining open raw-sequence claims. The artifact is accepted for classification
review but yields no new proof-ready rows.

| artifact_field | observed_value |
|---|---|
| `accepted` | `true` |
| `dry_run` | `true` |
| `operator_authorization` | `PUBLIC_MARKET_DATA_ONLY` |
| `rejection_reasons` | `[]` |
| `message_count` | `9` |
| `channels` | `["book.BTC-PERPETUAL.none.10.100ms"]` |

## Strict Classification Table

| claim_id | surface | classification | evidence_source | strict_reason |
|---|---|---|---|---|
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json` | `non_null_prev_change_id_observed=false`; all 9 events show `payload_sample.prev_change_id=null`. The channel `book.BTC-PERPETUAL.none.10.100ms` does not emit a non-null `prev_change_id`. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json` | `continuity_pair_missing=true`; all `prev_change_id` values are null so no adjacent pair satisfies `current.payload_sample.prev_change_id == prior.payload_sample.change_id`. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json` | `snapshot_type_observed=false`; all 9 events show `payload_sample.type=null`. The channel does not emit a `type` discriminator. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json` | `delta_type_observed=false`; all 9 events show `payload_sample.type=null`. The channel does not emit a `type` discriminator. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves the gap recovery or resubscribe rule. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | none | No committed official environment or heartbeat excerpt proves heartbeat, ping-pong, or liveness semantics. |

## Computed Counts

| count_name | value |
|---|---|
| `non_null_prev_change_id_count` | `0` |
| `adjacent_pair_count` | `8` |
| `continuity_match_count` | `0` |
| `snapshot_type_count` | `0` |
| `delta_or_change_type_count` | `0` |

## Non-Promotion Checks

| evidence_check | result | effect |
|---|---|---|
| workflow dispatch succeeded | true | Capture attempted and completed. |
| artifact accepted for classification | true | 9 events available for inspection; does NOT promote any claim by itself. |
| artifact has at least one `sample_events` item | true | 9 observed events present. |
| non-null `payload_sample.prev_change_id` observed | false | `prev_change_id` remains WAIT_INSUFFICIENT; channel emits null for this field. |
| adjacent equality `current.prev_change_id == prior.change_id` proven | false | `continuity_condition` remains WAIT_INSUFFICIENT. |
| first event `payload_sample.type` proves snapshot | false | `first_message_snapshot` remains WAIT_INSUFFICIENT; `type` is null. |
| later event `payload_sample.type` proves change or delta | false | `incremental_delta` remains WAIT_INSUFFICIENT; `type` is null. |

## Channel Limitation Finding

The `book.BTC-PERPETUAL.none.10.100ms` subscription (aggregated top-10 book,
100ms interval) does not emit:
- `prev_change_id` (always null in this subscription format)
- `type` (always null in this subscription format)

These fields are required to prove `prev_change_id`, `continuity_condition`,
`first_message_snapshot`, and `incremental_delta` claims. A different channel
subscription (e.g. `book.BTC-PERPETUAL.raw` or `book.BTC-PERPETUAL.100ms`)
may emit these fields. Operator must verify the correct channel and subscription
format before re-running the smoke workflow with a channel that exposes these
fields. No channel change may be made without operator authorization.

## Safety Invariants

- No worksheet row is edited.
- No final `APPROVE`, `REJECT`, or `DEFER` decision is written.
- No reviewer_id or reviewed_at_iso value is filled.
- No operator-fill proposal is created because zero rows are newly proof-ready.
- `connector_ready_dialects()` must remain empty.
- B1-B5 remain BLOCKED.
- `public_feed_dialects.py` remains unchanged.
