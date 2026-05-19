# Deribit Public Market Data Connector Enablement Audit - Phase 27F

status: PUBLIC_MARKET_DATA_CONNECTOR_ENABLEMENT_AUDIT
phase: 27F
generated_at: 2026-05-19
reviewer_id: demir_operator
reviewed_at_iso: 2026-05-19T00:00:00Z
approval_scope: Phase27F_PUBLIC_MARKET_DATA_ONLY_CONNECTOR_ENABLEMENT
decision: APPROVE
approved_run_mode: PUBLIC_MARKET_DATA_ONLY

## Purpose

Phase 27F is the separate B5 approval phase for the verified Deribit public
market data dialect only. It approves public connector readiness for the static
public feed dialect and does not add a network client, private API capability,
credential handling, orders, deposits, withdrawals, paper execution, shadow
execution, or live trading.

## Prior Proof References

| prerequisite | proof_ref | phase_27f_result |
|---|---|---|
| B3 policy values | `DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | READY |
| Regional public-data operator signoff | `DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md` | READY |
| Post-legal blocker state | `DERIBIT_NEXT_BLOCKER_SUMMARY_26AY.md` | B5 remained deferred |
| Static registry verification | `DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md` | B4 READY |
| Next blocker before B5 | `DERIBIT_NEXT_BLOCKER_SUMMARY_27E.md` | B5 BLOCKED only by separate connector enablement |

## Operator Approval Scope

| field | value |
|---|---|
| `row_to_approve` | `policy_review:separate_connector_enablement` |
| `policy_status` | `APPROVED` |
| `decision` | `APPROVE` |
| `reviewer_id` | `demir_operator` |
| `reviewed_at_iso` | `2026-05-19T00:00:00Z` |
| `approval_scope` | `Phase27F_PUBLIC_MARKET_DATA_ONLY_CONNECTOR_ENABLEMENT` |
| `approved_run_mode` | `PUBLIC_MARKET_DATA_ONLY` |
| `policy_value` | `PUBLIC_MARKET_DATA_ONLY_NO_PRIVATE_API_NO_CREDENTIALS_NO_ORDERS_NO_LIVE_NO_PAPER_SHADOW_EXECUTION` |

## Forbidden Scope

- No private API.
- No credentials.
- No orders.
- No deposits or withdrawals.
- No live trading.
- No paper execution.
- No shadow execution.
- No portfolio, account, allocator, strategy, or execution adapter change.
- No BIST code or assumptions.

## Expected Post-Patch State

| check | expected |
|---|---|
| `enabled_for_connector` | `True` only for `deribit:l2_orderbook:book_instrument_interval` |
| `connector_ready_dialects()` | one Deribit public market data dialect |
| `connector_enablement_ready` | `True` |
| `pending_rows` | `0` |
| `deferred_rows` | `()` |
| `B5` | `READY` |
| trade readiness | `NOT_READY` |

This phase is public-market-data readiness only. Runtime public feed smoke,
normalized `MarketEvent` integration, paper/shadow read-only pipeline work, and
any risk gate before trading remain future phases.
