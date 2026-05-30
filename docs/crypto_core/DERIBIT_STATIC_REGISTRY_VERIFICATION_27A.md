# Deribit Static Registry Verification - Phase 27A

status: STATIC_REGISTRY_VERIFICATION_ONLY
phase: 27A
generated_at: 2026-05-19
NOT_connector_enablement: true
NOT_b5_closure: true
NOT_private_api_credentials_orders: true
NOT_paper_shadow_live_integration: true

## Purpose

Phase 27A verifies the static Deribit public feed dialect registry from
already-approved evidence and policy rows. It does not approve
`separate_connector_enablement`, does not set `enabled_for_connector=True`, and
does not authorize paper, shadow, live, private API, credentials, or orders.

The legacy dialect id `deribit:l2_orderbook:placeholder` remains accepted as a
lookup alias for historical static-contract references. The canonical static
registry dialect is now `deribit:l2_orderbook:book_instrument_interval`.

## Approved Evidence To Registry Mapping

| registry_field | approved source | static value |
|---|---|---|
| `verification_status` | All claim rows approved and Phase 26AF/26AG official docs proof batches. | `VERIFIED_FROM_OFFICIAL_DOCS` |
| `official_doc_refs` | `DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md`, `DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md`, `DERIBIT_POLICY_DECISION_AUDIT_26AM.md`, `DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md`, `DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md`. | populated |
| `requires_rest_snapshot` | `rest_snapshot_requirement` approval plus gap recovery docs. | `False` |
| `supports_delta_stream` | `first_message_snapshot`, `incremental_delta`, `prev_change_id`, `continuity_condition`, and `gap_resubscribe_rule` approvals. | `True` |
| `sequence_model` | Approved snapshot/delta plus `prev_change_id` continuity evidence. Exact Deribit `prev_change_id == previous change_id` has no dedicated enum, so the conservative existing enum is used. | `SNAPSHOT_DELTA_RANGE` |
| `supports_checksum` | `checksum_decision` policy: `NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE`. | `False` |
| `checksum_model` | Same checksum policy. | `NONE` |
| `requires_heartbeat` | `heartbeat_liveness_proof` plus `liveness_policy`. | `True` |
| `requires_ping_pong` | Deribit proof is heartbeat/test-request based, not a generic ping/pong claim. | `False` |
| `supports_resync` | `gap_resubscribe_rule`: resubscribe or reconnect required on gap. | `True` |
| `max_gap_tolerance` | Fail closed on any continuity gap. | `0` |
| `max_staleness_ns` | `MAX_STALENESS_MS_2000`. | `2_000_000_000` |
| `max_receive_lag_ns` | `MAX_RECEIVE_LAG_MS_1000`. | `1_000_000_000` |
| `enabled_for_connector` | `separate_connector_enablement` remains deferred. | `False` |

## Verification Result

| check | value |
|---|---|
| `pending_rows` | `0` |
| `deferred_rows` | `policy_review:separate_connector_enablement` |
| `evidence_review_complete` | `True` |
| `ready_for_engineering_patch` | `True` |
| `deribit_static_registry_verified` | `True` |
| `enabled_for_connector` | `False` |
| `connector_ready_dialects()` | `()` |
| `connector_enablement_ready` | `False` |

## Safety Statement

B4 static registry verification is complete for the Deribit public market data
dialect. B5 remains blocked by the deferred `separate_connector_enablement`
policy row and must be handled in a separate explicitly authorized phase.
