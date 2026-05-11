# Deribit Operational Evidence Review Checklist

Status: manual review gate / operational evidence blocker checklist.

This checklist is an offline evidence acquisition and review gate for the
Deribit public L2 order-book dialect. Completing this document does not create a
connector, authorize network access, enable static registry readiness, or permit
orders or live execution. It only records whether the evidence needed by the
fail-closed operational readiness gate has been acquired and reviewed.

## Gate Status

- `checklist_id`: `deribit-operational-evidence-review-phase22i`
- `venue_id`: `deribit`
- `dialect_id`: `deribit:l2_orderbook:placeholder`
- `feed_type`: `l2_orderbook`
- `operational_status`: `BLOCKED`
- `manual_review_required`: `YES`
- `manual_hash_required`: `YES`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
- `deep_research_dossier_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
- `evidence_status_required`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `official_source_snapshots_supplied`: `false`
- `official_source_snapshot_hashes_validated`: `false`
- `phase22l_source_retrieval_hash_status`: `SUPPLIED_HASHED_PENDING_REVIEW`
- `phase22l_manifest_path`: `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md`
- `phase22l_manual_review_status`: `PENDING`
- `phase22m_claim_review_worksheet_path`: `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md`
- `phase22m_claim_review_status`: `PENDING`
- `phase22n_claim_review_validation_gate`: `src/crypto_core/venue/official_claim_reviews.py`
- `phase22n_claim_review_validation_status`: `BLOCKED_PENDING_MANUAL_APPROVAL`
- `phase22p_operational_acceptance_gate`: `src/crypto_core/venue/operational_evidence_readiness.py`
- `phase22p_operational_acceptance_status`: `BLOCKED_PENDING_POLICY_APPROVALS`
- `phase22r_operational_policy_review_worksheet_path`: `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`
- `phase22r_operational_policy_review_status`: `BLOCKED_PENDING_POLICY_APPROVALS`
- `phase22s_public_connector_enablement_gate`: `src/crypto_core/venue/public_connector_enablement.py`
- `phase22s_public_connector_enablement_status`: `BLOCKED_PENDING_SEPARATE_ENABLEMENT_APPROVAL`
- `phase22u_public_connector_readiness_report`: `src/crypto_core/venue/public_connector_readiness_report.py`
- `phase22u_public_connector_readiness_report_status`: `BLOCKED`
- `phase23b_public_ws_smoke_harness`: `src/crypto_core/data/deribit_public_ws_harness.py`
- `phase23b_public_ws_smoke_script`: `scripts/crypto_core/deribit_public_ws_smoke.py`
- `phase23b_smoke_status`: `QUARANTINED_PUBLIC_MARKET_DATA_ONLY`
- `phase23d_ci_smoke_run_id`: `25658030184`
- `phase23d_ci_smoke_job_conclusion`: `success`
- `phase23d_ci_smoke_classification`: `CI_DERIBIT_SMOKE_ACCEPTED_PROXY`
- `phase23d_ci_smoke_accepted`: `true`
- `phase23d_ci_smoke_message_count`: `19`
- `phase23d_ci_smoke_rejection_reasons`: `[]`
- `phase23d_ci_smoke_b8_status`: `CLOSED_BY_PROXY_CI_PROOF`
- `phase23e_isolated_workflow_file`: `.github/workflows/deribit-public-smoke.yml`
- `phase23e_isolated_workflow_commit`: `dd0e9c6c21894ab731b7ab3542f8e36a516e8ad5`
- `phase23e_isolated_workflow_classification`: `ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER`
- `phase23f_smoke_proof_record`: `docs/crypto_core/DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`
- `phase23f_smoke_proof_record_status`: `ADVISORY_EVIDENCE_ONLY`

## Phase 22J Deep Research Dossier Intake Rules

The Deep Research Deribit dossier may seed an offline evidence table, but it is
not primary evidence. Every DR_REPORTED source remains blocked until it is
locally retrieved, hashed, and manually reviewed.

Each source row must contain:

- `source_id`
- `venue`
- `official_url`
- `retrieved_at_iso`
- `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `manual_review_required`: `YES`
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`

Current dossier corrections:

- `checksum_absence_status`: `UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`
- `heartbeat_ping_pong_liveness_status`: `UNKNOWN_BLOCKED`
- `staleness_budget_status`: `UNSATISFIED`
- `receive_lag_budget_status`: `UNSATISFIED`
- `testnet_prod_semantic_equivalence`: `UNKNOWN`
- `regional_legal_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`
- `turkey_regional_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`
- `deribit_dialect_verification`: `false`
- `enabled_for_connector`: `false`

## Phase 22K Local Snapshot Hash Intake Rules

The local official-source snapshot/hash contract is
`src/crypto_core/venue/official_source_snapshots.py`. It validates only supplied
snapshot metadata and supplied SHA256 hashes. It must not fetch URLs, read files,
start network sessions, enable a connector, or mutate the static registry.

Each accepted local snapshot must include:

- `source_id`
- `venue_id`
- `official_url`
- `retrieved_at_iso`
- `content_sha256`: 64 lowercase hex characters
- `content_size_bytes`: positive integer
- `reviewer_id`
- `reviewed_at_iso`
- `manual_review_status`: `APPROVED`
- `rejection_reasons`: `[]`

## Phase 22L Terminal Documentation Fetch Intake

Phase 22L retrieved the official Deribit documentation URLs already listed in
the draft evidence package with terminal-only documentation fetches. The
manifest is:
`docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md`.

The retrieved documentation payloads are hashed and supplied for manual review,
but they are not manually approved and must not be treated as accepted
operational evidence.

All listed Deribit documentation fragment URLs resolved to the same single-page
documentation payload during Phase 22L terminal retrieval. The shared hash and
byte size do not equal claim-level approval and must not be used to satisfy
manual review by themselves.

| source_id | retrieval_status | content_hash_status | manual_review_status |
|---|---|---|---|
| `DERIBIT_NOTIFICATIONS` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |
| `DERIBIT_ENVIRONMENT` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |
| `DERIBIT_RATE_LIMITS` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |
| `DERIBIT_INSTRUMENTS` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |
| `DERIBIT_TICKER` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |
| `DERIBIT_RESTRICTED` | `SUPPLIED_HASHED_PENDING_REVIEW` | `SUPPLIED_HASHED_PENDING_REVIEW` | `PENDING` |

Outstanding review decisions after Phase 22L:

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

## Phase 22M Claim-Level Review Worksheet

Phase 22M adds a manual claim-level review worksheet:
`docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md`.

The worksheet rows are all `PENDING`, with `reviewer_id`, `reviewed_at_iso`,
and `decision` also left `PENDING`. Every row has
`operational_readiness_effect`: `LEAVES_BLOCKER`. The same-hash documentation
payload caveat remains active: hashed source snapshots do not approve
individual claims, checksum decisions, heartbeat/liveness proofs, operational
budgets, testnet/prod equivalence, legal access, registry readiness, or
connector readiness.

## Phase 22N Claim Review Validation Gate

Phase 22N adds an inert claim-review validation contract:
`src/crypto_core/venue/official_claim_reviews.py`.

The gate validates supplied manual claim-review metadata only. It does not read
files, fetch URLs, perform network access, approve Deribit claims, mutate the
registry, create a connector, or permit orders or live execution.

Current Deribit worksheet rows remain `PENDING`, so the validation gate must
reject the current worksheet with `official_claim_review:pending` and leave
operational readiness blocked.

## Phase 22P Operational Evidence Acceptance Gate

Phase 22P adds an inert operational evidence acceptance gate to
`src/crypto_core/venue/operational_evidence_readiness.py`.

The gate evaluates supplied source snapshot validation results, supplied claim
review validation results, and manual operational policy approvals together. It
does not read files, fetch URLs, perform network access, auto-approve Deribit
claims, verify a dialect, mutate the registry, request connector enablement, or
permit orders or live execution.

Required policy approvals remain:

- `checksum_decision`
- `liveness_policy`
- `staleness_budget`
- `receive_lag_budget`
- `testnet_prod_review`
- `regional_legal_access_review`
- `separate_connector_enablement`

Stable rejection codes for the current blocked state include:

- `operational_evidence:source_snapshot_rejected`
- `operational_evidence:claim_review_rejected`
- `operational_policy:checksum_decision_missing`
- `operational_policy:liveness_policy_missing`
- `operational_policy:staleness_budget_missing`
- `operational_policy:receive_lag_budget_missing`
- `operational_policy:testnet_prod_review_missing`
- `operational_policy:regional_legal_access_review_missing`
- `operational_policy:separate_connector_enablement_required`

Current Deribit source snapshots and claim rows are still pending manual
approval, and the required policy approvals are not recorded. Therefore Phase
22P acceptance must remain blocked and must not make
`connector_ready_dialects()` non-empty.

## Phase 22R Operational Policy Review Worksheet

Phase 22R adds a manual operational policy review worksheet:
`docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`.

All policy rows remain `PENDING` and leave operational readiness blocked:

- `checksum_decision`: `PENDING_MANUAL_REVIEW`
- `liveness_policy`: `PENDING_POLICY_BUDGET`
- `staleness_budget`: `ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL`
- `receive_lag_budget`: `ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL`
- `testnet_prod_review`: `PENDING_MANUAL_REVIEW`
- `regional_legal_access_review`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`
- `separate_connector_enablement`: `REQUIRED_SEPARATE_PHASE`

The Phase 22P acceptance gate cannot pass current Deribit evidence while these
rows remain pending. Connector enablement is separate, explicitly forbidden in
this phase, and must not be inferred from evidence worksheets or hashes.

## Phase 22S Public Connector Enablement Gate

Phase 22S adds an inert public connector enablement authorization gate:
`src/crypto_core/venue/public_connector_enablement.py`.

The gate evaluates supplied manual connector enablement metadata only. It does
not read files, fetch URLs, perform network access, mutate the registry, create
a connector, start a client, authorize credentials, enable private API access,
permit orders, or permit live execution.

The current Deribit connector enablement request must reject because:

- `operational_evidence_accepted`: `false`
- `static_registry_verified`: `false`
- `connector_enablement_status`: `PENDING`
- `reviewer_id`: `PENDING`
- `reviewed_at_iso`: `PENDING`
- `approved_run_mode`: `REQUIRED_SEPARATE_PHASE`
- `enabled_for_connector`: `false`
- `connector_ready_dialects_expected`: `[]`

Stable rejection codes for the current blocked state include:

- `public_connector_enablement:operational_evidence_not_accepted`
- `public_connector_enablement:static_registry_unverified`
- `public_connector_enablement:pending`
- `public_connector_enablement:missing_reviewer`
- `public_connector_enablement:missing_review_time`
- `public_connector_enablement:invalid_run_mode`

Even if operational evidence later becomes accepted, public connector
enablement requires a separate explicit approval with
`approved_run_mode`: `PUBLIC_MARKET_DATA_ONLY`, reviewer metadata, evidence
references, and verified static registry readiness. Phase 22S does not approve
Deribit connector readiness and must not make `connector_ready_dialects()`
non-empty.

## Phase 22U Public Connector Readiness Report

Phase 22U adds an inert deterministic public connector readiness report:
`src/crypto_core/venue/public_connector_readiness_report.py`.

The report composes supplied source snapshot validation results, supplied claim
review validation results, supplied operational evidence acceptance, supplied
connector enablement decision, static registry verification status, and evidence
references into a JSON-safe audit surface. It does not read files, fetch URLs,
perform network access, mutate the registry, create a connector, start a client,
authorize credentials, enable private API access, permit orders, or permit live
execution.

The current Deribit readiness report must remain `BLOCKED` because:

- source snapshots are hashed but not manually approved
- claim reviews remain `PENDING`
- operational policy approvals remain `PENDING`
- operational evidence acceptance remains rejected
- public connector enablement remains rejected
- `static_registry_verified`: `false`
- `enabled_for_connector`: `false`
- `connector_ready_dialects_expected`: `[]`

Stable blocker codes for the current blocked report include:

- `public_connector_readiness:source_snapshots_not_ready`
- `public_connector_readiness:claim_reviews_not_ready`
- `public_connector_readiness:operational_evidence_not_ready`
- `public_connector_readiness:connector_enablement_not_ready`
- `public_connector_readiness:static_registry_unverified`

The report is an audit surface only. It must not mark current Deribit
`connector_ready`, must not mark operational evidence ready, must not mark the
static registry verified, must not mark the Deribit dialect verified, and must
not make `connector_ready_dialects()` non-empty.

## Phase 23B Quarantined Public WebSocket Smoke Harness

Phase 23B adds a quarantined public WebSocket smoke harness:
`src/crypto_core/data/deribit_public_ws_harness.py`, with an operator script at
`scripts/crypto_core/deribit_public_ws_smoke.py`.

The harness is authorized only for `PUBLIC_MARKET_DATA_ONLY` observation of
bounded, unauthenticated, aggregated public Deribit WebSocket channels. It is not
a connector, not a connector-ready dialect, not strategy integration, not
service/orchestrator integration, not private API access, not order routing, and
not live trading.

Required safety state remains:

- `operational_status`: `BLOCKED`
- `phase23b_smoke_status`: `QUARANTINED_PUBLIC_MARKET_DATA_ONLY`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
- `deribit_dialect_verification`: `false`
- `strategy_integration`: `FORBIDDEN`
- `service_orchestrator_integration`: `FORBIDDEN`
- `private_api`: `FORBIDDEN`
- `credentials_env_api_key_reads`: `FORBIDDEN`
- `orders`: `FORBIDDEN`
- `live_execution`: `FORBIDDEN`

## Required Evidence Acquisition Fields

Every Deribit operational evidence claim remains blocked until all fields below
are populated from official Deribit sources, independently reviewed, and mapped
back to the evidence package.

- `official_source_url_per_claim`: `SUPPLIED_HASHED_PENDING_REVIEW`
  - Requirement: every claim has a real official source URL.
- `retrieval_timestamp`: `SUPPLIED_HASHED_PENDING_REVIEW`
  - Requirement: every source snapshot has a positive retrieval timestamp.
- `reproducible_sha256_content_hash`: `SUPPLIED_HASHED_PENDING_REVIEW`
  - Requirement: every source snapshot has a reproducible SHA256/content hash.
- `reviewer_id`: `BLOCKER`
  - Requirement: a reviewer id is recorded for the manual review.
- `review_timestamp`: `BLOCKER`
  - Requirement: a positive review timestamp is recorded.
- `manual_approval_status`: `PENDING`
  - Requirement: manual approval status is explicit and approved before use.
- `sequence_change_id_prev_change_id_proof_reviewed`: `PENDING`
  - Requirement: sequence, `change_id`, and `prev_change_id` proof reviewed.
- `snapshot_delta_resync_proof_reviewed`: `PENDING`
  - Requirement: snapshot, delta, and resync proof reviewed.
- `checksum_decision_reviewed`: `PENDING`
  - Requirement: checksum model or fail-closed checksum absence reviewed.
- `heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`
  - Requirement: heartbeat, ping-pong, and liveness proof reviewed.
- `rate_subscription_limit_proof_reviewed`: `PENDING`
  - Requirement: rate and subscription limit proof reviewed.
- `staleness_budget_defined`: `PENDING`
  - Requirement: max staleness budget is defined from official evidence.
- `receive_lag_budget_defined`: `PENDING`
  - Requirement: max receive-lag budget is defined from official evidence.
- `testnet_prod_difference_reviewed`: `PENDING`
  - Requirement: testnet and production differences are reviewed.
- `regional_legal_access_reviewed`: `PENDING`
  - Requirement: regional, legal, and access constraints are reviewed.

## Safety Review Fields

These safety checks must remain true while the checklist is incomplete.

- `no_secrets_api_keys_in_docs`: `REQUIRED`
  - Requirement: docs contain no secrets, API keys, tokens, passphrases, private
    keys, account identifiers, or environment-variable based credentials.
- `static_registry_remains_unverified`: `REQUIRED`
  - Requirement: the Deribit static dialect remains unverified and disabled.
- `connector_ready_dialects_remains_empty`: `REQUIRED`
  - Requirement: `connector_ready_dialects()` remains empty.
- `no_real_connector_network_client_orders_live`: `REQUIRED`
  - Requirement: no real connector, network, REST, WebSocket client, endpoint,
    private API, order path, or live execution path is introduced.

## Completion Rule

The Deribit evidence package remains operationally blocked until every
`BLOCKER` or `PENDING` item above is satisfied with official-source evidence,
reproducible hashes, retrieval timestamps, reviewer metadata, manual approval,
and explicit budget decisions. Even after completion, a separate registry
enablement and connector implementation phase is required before any runtime
connector can exist.
