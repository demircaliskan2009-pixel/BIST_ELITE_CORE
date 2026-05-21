# Deribit Source Snapshot Acceptance Audit - Phase 27K

status: SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE
phase: 27K
generated_at: 2026-05-21
scope: PUBLIC_MARKET_DATA_OPERATIONAL_EVIDENCE_ONLY
reviewer_id: demir_operator
reviewed_at_iso: 2026-05-19T00:00:00Z
approval_scope: Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE
decision: APPROVE
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_connector_expansion: true

## Root Cause

After PR #69, B3, B4, and B5 were READY and one Deribit public market data
dialect was connector-ready. B1 and B2 remained BLOCKED because
`_validate_manifest()` emitted `REVIEWED` for hashed, non-pending source
snapshot rows. B2 requires every `source_snapshot` and `claim_review` row to
emit `APPROVED`.

Phase 27K fixes that structural blocker by adding explicit source-snapshot
acceptance metadata to the manifest and by requiring that metadata in the
parser. The parser still fails closed: `REVIEWED_APPROVED` retrieval status
alone is never enough to produce `APPROVED`.

## Accepted Source Snapshot Rows

| source_id | official_url | content_sha256_preserved | acceptance_decision | accepted_by | accepted_at_iso | acceptance_scope |
|---|---|---|---|---|---|---|
| `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |
| `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |
| `DERIBIT_RATE_LIMITS` | `https://docs.deribit.com/#rate-limits` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |
| `DERIBIT_INSTRUMENTS` | `https://docs.deribit.com/#public-get_instruments` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |
| `DERIBIT_TICKER` | `https://docs.deribit.com/#ticker-instrument_name-interval` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |
| `DERIBIT_RESTRICTED` | `https://docs.deribit.com/#restricted-countries` | `YES` | `APPROVE` | `demir_operator` | `2026-05-19T00:00:00Z` | `Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE` |

## Fail-Closed Parser Rules

- `retrieval_status` containing `PENDING` remains `PENDING`, even if
  acceptance fields are accidentally populated.
- `acceptance_decision=APPROVE` requires non-pending `accepted_by`,
  `accepted_at_iso`, and `acceptance_scope`.
- Missing or incomplete acceptance metadata leaves a reviewed source snapshot
  at `REVIEWED`, not `APPROVED`.
- `acceptance_decision=REJECT` emits `REJECTED`.
- `acceptance_decision=DEFER` emits `DEFERRED`.
- `REVIEWED_APPROVED` alone is never an approval signal.
- Manifest row-count enforcement remains fail-closed.

## Expected Post-Patch State

| field | expected |
|---|---|
| `source_snapshot_rows_approved` | `6` |
| `claim_rows_approved` | `23` |
| `policy_rows_complete` | `7` |
| `pending_rows` | `0` |
| `deferred_rows` | `()` |
| `rejection_reasons` | `()` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `accepted` | `True` |
| `connector_ready_dialects` | `1` |

This phase does not add or expand a connector, network client, private API,
credentials, orders, deposits, withdrawals, paper execution, shadow execution,
or live trading.
