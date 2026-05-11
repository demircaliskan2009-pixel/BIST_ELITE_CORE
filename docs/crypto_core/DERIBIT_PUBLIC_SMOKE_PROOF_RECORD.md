# Deribit Public Smoke Proof Record

Status: advisory evidence record / cloud reachability proof only.

This document records the outcome of the Deribit PUBLIC_MARKET_DATA_ONLY smoke
proof produced in Phase 23D via the GitHub Actions CI pipeline. It is an
advisory evidence artifact only.

This document does NOT:
- clear operational readiness blockers B1–B5
- make `connector_ready_dialects()` non-empty
- mark `operational_evidence_ready: true`
- mark `Deribit dialect verified: true`
- authorize paper/shadow integration
- authorize live trading
- enable private API, credentials, or order routing
- mutate the static registry
- change `operational_status` from BLOCKED

---

## Proof Classifications

- `phase23d_smoke_classification`: `CI_DERIBIT_SMOKE_ACCEPTED_PROXY`
- `phase23e_isolated_workflow_classification`: `ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER`

---

## Phase 23D CI Smoke Proof

### Run Metadata

- `ci_run_id`: `25658030184`
- `ci_run_url`: `https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/25658030184`
- `ci_run_event`: `workflow_dispatch`
- `ci_run_branch`: `chore/hard-deterministic-enforcement`
- `ci_run_commit`: `74298a70d8499b2b304cb2b704832b849ec81313`
- `ci_run_created_at`: `2026-05-11T08:05:22Z`
- `ci_run_updated_at`: `2026-05-11T08:06:34Z`
- `ci_run_status`: `completed`
- `ci_run_overall_conclusion`: `failure` (legacy BIST tests, unrelated to smoke)
- `deribit_public_smoke_job_conclusion`: `success`
- `workflow_file`: `.github/workflows/ci.yml`
- `phase`: `23D`

### Smoke Result

```
accepted: true
channels:
  - book.BTC-PERPETUAL.none.10.100ms
dry_run: true
duration_seconds: 10.0
max_messages: 20
message_count: 19
operator_authorization: PUBLIC_MARKET_DATA_ONLY
rejection_reasons: []
ws_url: wss://www.deribit.com/ws/api/v2
receive_lag_ms_max: 176
```

- `classification`: `CI_DERIBIT_SMOKE_ACCEPTED_PROXY`
- `artifact_name`: `deribit-public-smoke-proof`
- `artifact_retention_days`: `90`

### What This Proof Establishes

1. The GitHub Actions ubuntu runner has unrestricted HTTPS access to
   `wss://www.deribit.com/ws/api/v2`.
2. The public WebSocket subscription to `book.BTC-PERPETUAL.none.10.100ms`
   succeeds and delivers live market data messages.
3. The `deribit_public_ws_harness.py` quarantine harness correctly receives,
   parses, and serialises bounded public order-book events.
4. All 19 received events passed the harness validation with
   `rejection_reasons: []`.
5. The local network block (B8) is closed: the endpoint is reachable from
   cloud infrastructure.

### What This Proof Does NOT Establish

- It does not verify checksum model, heartbeat/liveness protocol, or rate limits.
- It does not prove testnet/production semantic equivalence.
- It does not prove regional or legal access for all jurisdictions.
- It does not approve any manual claim review row.
- It does not satisfy B1–B5 requirements.
- It does not authorize paper or shadow trading.
- It does not make `connector_ready_dialects()` non-empty.

---

## Phase 23E Isolated Workflow

### Workflow File

- `workflow_file`: `.github/workflows/deribit-public-smoke.yml`
- `commit`: `dd0e9c6c21894ab731b7ab3542f8e36a516e8ad5`
- `branch`: `chore/hard-deterministic-enforcement`
- `trigger`: `workflow_dispatch` only
- `classification`: `ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER`

### Reason Not Run

GitHub's `workflow_dispatch` REST API requires the workflow file to be present
on the default branch (`main`). The `deribit-public-smoke.yml` workflow was
committed only to the feature branch `chore/hard-deterministic-enforcement`.
The GitHub API returns HTTP 404 for any `workflow_dispatch` trigger targeting a
workflow file not registered on the default branch.

- `trigger_attempted`: `true`
- `trigger_result`: `HTTP 404 — workflow not registered on default branch`
- `gh_command`: `gh workflow run deribit-public-smoke.yml --ref chore/hard-deterministic-enforcement`
- `gh_api_command`: `gh api -X POST repos/.../actions/workflows/deribit-public-smoke.yml/dispatches`
- `unblocking_path`: `Merge chore/hard-deterministic-enforcement → main via PR`

### Safety State (Phase 23E)

- `permissions`: `contents: read` only
- `trigger`: `workflow_dispatch` (manual) only — no push, no schedule, no PR
- `no_secrets`: `true`
- `no_credentials`: `true`
- `no_private_channel`: `true`
- `no_orders`: `true`
- `no_live_trading`: `true`
- `no_registry_mutation`: `true`
- `no_connector_ready_dialects_mutation`: `true`
- `dry_run_hardcoded`: `true` (enforced in `scripts/crypto_core/deribit_public_ws_smoke.py`)

---

## Blocker Summary

### B8 — Cloud Reachability

- `blocker_id`: `B8`
- `description`: Local network blocks Deribit HTTPS/WSS
- `status`: `CLOSED_BY_PROXY_CI_PROOF`
- `evidence`: Phase 23D run 25658030184, job `deribit-public-smoke`, conclusion `success`
- `note`: Local block remains (DNS `::1`, TCP timeout to `213.14.227.50:443`);
  cloud infrastructure has unrestricted access.

### Remaining Blockers (B1–B5) — All Still Open

- `B1`: `operational_status: BLOCKED` — manual policy approval required
- `B2`: `phase22n_claim_review_validation_status: BLOCKED_PENDING_MANUAL_APPROVAL`
- `B3`: `phase22p_operational_acceptance_status: BLOCKED_PENDING_POLICY_APPROVALS`
- `B4`: `static_registry_verified: false`
- `B5`: `connector_ready_dialects() returns ()` — blocked by B1–B4

None of B1–B5 are affected by this smoke proof. All must be resolved through
the manual policy and review process defined in
`docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md`.

---

## Safety Contract

```
operational_status:                     BLOCKED
connector_ready_dialects:               []
operational_evidence_ready:             false
deribit_dialect_verified:               false
paper_shadow_integration_ready:         false
live_trading_ready:                     false
private_api:                            FORBIDDEN
credentials_env_api_key_reads:          FORBIDDEN
orders:                                 FORBIDDEN
live_execution:                         FORBIDDEN
strategy_integration:                   FORBIDDEN
service_orchestrator_integration:       FORBIDDEN
```

---

## Source Reference

- Harness: `src/crypto_core/data/deribit_public_ws_harness.py`
- Script: `scripts/crypto_core/deribit_public_ws_smoke.py`
- Checklist: `docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md`
- Isolated workflow: `.github/workflows/deribit-public-smoke.yml`
- CI workflow: `.github/workflows/ci.yml`
- Phase 23B tests: `tests/crypto_core/data/test_phase23b_deribit_public_ws_harness.py`
- Phase 23F tests: `tests/crypto_core/data/test_phase23f_deribit_smoke_proof_record.py`
