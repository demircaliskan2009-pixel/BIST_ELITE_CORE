# Phase 46A - Bounded Repeated Paper Campaign Operator Proposal

status: BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_READY
phase: 46A
generated_at: 2026-05-25
scope: OPERATOR_APPROVAL_PROPOSAL_ONLY
NOT_operator_approval_execution: true
NOT_campaign_execution: true
NOT_automatic_promotion: true
NOT_private_api: true
NOT_credentials: true
NOT_exchange_orders: true
NOT_execution_adapter: true
NOT_order_routing: true
NOT_strategy_alpha: true
NOT_scheduler: true
NOT_automatic_paper_loop: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #88 State

| field | value |
|---|---|
| `main` | `9e66435bbb13d24b25e00f3a1e0904217793d33a` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `phase45_promotion_verdict` | `READY_FOR_OPERATOR_REVIEW` |
| `promotion_granted` | `False` |
| `operator_approval_required` | `True` |
| `automatic_paper_loop_status` | `NO` |
| `scheduler_status` | `NO` |
| `live_or_shadow_status` | `NO` |

## Evidence Chain

- Phase42 hard-capped session:
  `docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json`
- Phase43 promotion criteria:
  `docs/crypto_core/PAPER_SESSION_PROMOTION_CRITERIA_43A.md`
- Phase44 repeated report pack:
  `docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json`
- Phase45 promotion evaluation:
  `docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json`

## Proposed Campaign Scope

- venue: Deribit only
- public market data only
- paper-only
- simulation-only
- explicit operator-triggered only
- no scheduler
- no automatic loop
- no live trading
- no shadow trading
- no private API
- no credentials
- no exchange orders
- no execution adapter
- no strategy or alpha generation

## Proposed Bounds

| bound | value |
|---|---|
| `hard_cap` | `3` |
| `per_session_max_trades` | `2` |
| `max_sessions_proposed` | `3` |
| `max_total_paper_trades_proposed` | `6` |

These bounds are proposal-only. They do not execute a campaign and do not grant
promotion.

## Required Operator Approval Metadata

The proposal is NOT APPROVED YET. Approval execution is blocked until the user
explicitly supplies all required operator metadata in a later approval phase:

| metadata | value |
|---|---|
| `reviewer_id` | `<OPERATOR_REQUIRED>` |
| `reviewed_at_iso` | `<OPERATOR_REQUIRED>` |
| `approval_scope` | `<OPERATOR_REQUIRED>` |
| `approval_decision` | `<OPERATOR_REQUIRED>` |
| `approval_notes` | `<OPERATOR_REQUIRED>` |

Any non-placeholder approval metadata in this phase is invalid and must fail
closed because Phase46 is proposal-only.

## Explicit Non-Scope

This phase does not approve the campaign, grant promotion, execute a campaign,
start a session or run, add private API, add credentials, create exchange
orders, add an execution adapter, route orders, generate strategy signals,
start a scheduler, start an automatic paper loop, enable shadow trading, enable
live trading, or mutate connector policy.

## Next Phase

The next safe phase is operator approval execution only if the user explicitly
provides complete approval metadata. Otherwise STOP and keep the proposal in
`approval_status=NOT_APPROVED`.
