# Deribit Official Source Snapshot Manifest

Status: terminal documentation fetch / hashes supplied / manual review pending.

This manifest records Phase 22L terminal retrieval of official Deribit
documentation URLs already listed in
`docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md`. It is not a
connector authorization, does not enable registry readiness, and does not
permit network, private API, order, or live execution behavior in source code.

Raw fetched HTML snapshots were written only to the local temporary directory
`.tmp_official_sources/deribit/20260510/` for hashing. The raw HTML snapshots
are intentionally not committed; the committed artifact is this hash manifest.

## Gate Status

- `venue_id`: `deribit`
- `manifest_id`: `deribit-official-source-snapshots-20260510`
- `retrieval_scope`: `OFFICIAL_DOCUMENTATION_URLS_LISTED_IN_REPO_ONLY`
- `retrieval_method`: `TERMINAL_DOC_FETCH`
- `retrieval_tool`: `PowerShell Invoke-WebRequest`
- `operational_status`: `BLOCKED`
- `manual_review_required`: `YES`
- `manual_review_status`: `PENDING`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
- `official_source_snapshot_hashes_validated`: `false`
- `evidence_status`: `SUPPLIED_HASHED_PENDING_MANUAL_REVIEW`
- `claim_review_worksheet_path`: `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md`

## Source Snapshots

| source_id | official_url | retrieved_at_iso | retrieval_status | content_sha256 | content_size_bytes | local_temp_path |
|---|---|---|---|---|---:|---|
| `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `2026-05-10T07:51:21Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_NOTIFICATIONS.html` |
| `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `2026-05-10T07:51:22Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_ENVIRONMENT.html` |
| `DERIBIT_RATE_LIMITS` | `https://docs.deribit.com/#rate-limits` | `2026-05-10T07:51:23Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_RATE_LIMITS.html` |
| `DERIBIT_INSTRUMENTS` | `https://docs.deribit.com/#public-get_instruments` | `2026-05-10T07:51:24Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_INSTRUMENTS.html` |
| `DERIBIT_TICKER` | `https://docs.deribit.com/#ticker-instrument_name-interval` | `2026-05-10T07:51:25Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_TICKER.html` |
| `DERIBIT_RESTRICTED` | `https://docs.deribit.com/#restricted-countries` | `2026-05-10T07:51:25Z` | `SUPPLIED_HASHED_PENDING_REVIEW` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | 939778 | `.tmp_official_sources/deribit/20260510/DERIBIT_RESTRICTED.html` |

## Review Blockers

- `manual_approval_status`: `PENDING`
- `sequence_change_id_prev_change_id_proof_reviewed`: `PENDING`
- `snapshot_delta_resync_proof_reviewed`: `PENDING`
- `checksum_decision_reviewed`: `PENDING`
- `heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`
- `rate_subscription_limit_proof_reviewed`: `PENDING`
- `staleness_budget_defined`: `PENDING`
- `receive_lag_budget_defined`: `PENDING`
- `testnet_prod_difference_reviewed`: `PENDING`
- `regional_legal_access_reviewed`: `PENDING`

## Safety Notes

- Fragment anchors on `docs.deribit.com` resolve to the same documentation page
  payload during terminal retrieval, so the six source snapshots currently have
  the same content hash and byte size.
- These hashes prove only that the documentation payload was retrieved and
  hashed locally. They do not prove claim-level manual review.
- The claim-level review worksheet remains pending and every worksheet row
  leaves operational readiness blocked.
- No raw HTML snapshot is committed.
- No connector, network client, exchange endpoint implementation, private API,
  credentials, orders, live execution, registry enablement, or
  `connector_ready_dialects()` enablement is authorized by this manifest.
